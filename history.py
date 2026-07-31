"""
历史会话管理（MySQL 持久化）
============================

历史会话统一存储在 MySQL 单表 sessions 中（首次连接自动建库建表）。
消息序列化使用 pydantic-ai 官方 ModelMessagesTypeAdapter，序列化结果写入
messages 列（LONGTEXT），加载后可直接作为 Agent.run(message_history=...)
恢复上下文继续对话。

首次启动若 sessions 表为空，会自动把旧版 .agent_history/ 下的存量数据
一次性迁移进库。

支持：
- create_session / save_messages / load_messages / delete_session
- list_sessions：按更新时间倒序，可按关键词搜索标题与消息内容
- messages_to_display：把消息转成 [(role, content)] 供 CLI / UI 展示
"""

import json
import os
import time
import uuid
from datetime import datetime
from typing import Any

try:
    from pydantic_ai.messages import (
        ModelMessagesTypeAdapter,
        ModelRequest,
        ModelResponse,
        RetryPromptPart,
        SystemPromptPart,
        TextPart,
        ToolCallPart,
        ToolReturnPart,
        UserPromptPart,
    )

    _has_pydantic_ai = True
except ImportError:  # pragma: no cover
    _has_pydantic_ai = False
    # pydantic_ai 缺失时为全部名字兜底，避免“可能未绑定”（仅影响静态检查，
    # 运行时这些函数都有 _has_pydantic_ai 守卫，不会走到 isinstance）
    ModelMessagesTypeAdapter = None
    ModelRequest = None
    ModelResponse = None
    RetryPromptPart = None
    SystemPromptPart = None
    TextPart = None
    ToolCallPart = None
    ToolReturnPart = None
    UserPromptPart = None

try:
    import pymysql

    _has_pymysql = True
except ImportError:  # pragma: no cover
    pymysql = None
    _has_pymysql = False

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".agent_history")

# 标题截断长度
TITLE_MAX = 20


def _content_to_str(content: Any) -> str:
    """把消息 part 的 content 统一转为可显示文本（兼容多模态 list）"""
    return content if isinstance(content, str) else str(content)


def _make_title(messages: list[Any]) -> str | None:
    """用第一条用户消息生成会话标题；找不到返回 None"""
    if not _has_pydantic_ai:
        return None
    assert ModelRequest is not None and UserPromptPart is not None
    for m in messages:
        if not isinstance(m, ModelRequest):
            continue
        for p in m.parts:
            if isinstance(p, UserPromptPart) and isinstance(p.content, str):
                text = " ".join(p.content.split())
                if not text:
                    continue
                return text[:TITLE_MAX] + ("…" if len(text) > TITLE_MAX else "")
    return None


def _dump_messages(messages: list[Any]) -> list[Any]:
    """把 pydantic-ai 消息序列化为可 JSON 存储的数据（写入 MySQL messages 列）"""
    if not _has_pydantic_ai:
        return []
    assert ModelMessagesTypeAdapter is not None
    try:
        return json.loads(ModelMessagesTypeAdapter.dump_json(messages))
    except Exception:  # noqa: BLE001  # 序列化失败不阻塞对话
        return []


def _parse_messages(raw: list[Any]) -> list[Any] | None:
    """把序列化数据反序列化为 pydantic-ai 消息（从 MySQL messages 列读出）"""
    if not _has_pydantic_ai:
        return None
    assert ModelMessagesTypeAdapter is not None
    try:
        return ModelMessagesTypeAdapter.validate_python(raw)
    except Exception:  # noqa: BLE001  # 版本不兼容时提示重新创建会话
        return None


_CREATE_TABLE = """
    CREATE TABLE IF NOT EXISTS sessions (
        session_id VARCHAR(32) PRIMARY KEY,
        title TEXT NOT NULL,
        message_count INT NOT NULL DEFAULT 0,
        created_at DOUBLE NOT NULL,
        updated_at DOUBLE NOT NULL,
        messages LONGTEXT NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""


class MySQLSessionStore:
    """历史会话的 MySQL 持久化管理器（唯一存储后端）。

    设计要点：
    - 单表 sessions（首次连接自动建库建表）
    - messages 列存 pydantic-ai ModelMessagesTypeAdapter 序列化结果，
      加载后可直接作为 Agent.run(message_history=...) 恢复上下文继续对话
    - 时间戳统一存 DOUBLE（秒）
    - 首次启动自动把 .agent_history/ 下的存量数据迁移进库（一次性）
    - 关键词搜索用 SQL LIKE（建库指定 utf8mb4_unicode_ci，大小写不敏感），
      用户输入中的 % / _ \\ 通配符先转义，与旧版包含匹配等价

    配置（.env）：MYSQL_HOST / MYSQL_PORT / MYSQL_USER / MYSQL_PASSWORD /
    MYSQL_DATABASE（MYSQL_DATABASE 未设置时默认使用独立库 agent_history）。
    """

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        user: str | None = None,
        password: str | None = None,
        database: str | None = None,
        data_dir: str = DATA_DIR,
    ):
        if not _has_pymysql:
            raise RuntimeError("未安装 pymysql，无法使用 MySQL 历史会话存储，请执行 pip install pymysql")
        env = os.environ
        self._host = host or env.get("MYSQL_HOST", "127.0.0.1")
        self._port = port or int(env.get("MYSQL_PORT", "3306"))
        self._user = user or env.get("MYSQL_USER", "root")
        self._password = password if password is not None else env.get("MYSQL_PASSWORD", "")
        self._database = database or env.get("MYSQL_DATABASE", "agent_history")
        self._pymysql: Any = pymysql
        self.data_dir = data_dir
        self._ensure_database()
        self._ensure_tables()
        self._maybe_migrate_from_json()

    # ---------- 连接 ----------
    def _connect(self, with_db: bool = True):
        kwargs: dict[str, Any] = {
            "host": self._host,
            "port": self._port,
            "user": self._user,
            "password": self._password,
            "charset": "utf8mb4",
            "autocommit": True,
        }
        if with_db:
            kwargs["database"] = self._database
        return self._pymysql.connect(**kwargs)

    def _fetch(self, sql: str, args: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
        """执行查询并返回全部结果行（短连接，用完即关）"""
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, args)
                return list(cur.fetchall())
        finally:
            conn.close()

    def _execute(self, sql: str, args: tuple[Any, ...] = ()) -> int:
        """执行写语句，返回受影响行数（短连接，用完即关）"""
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, args)
                return cur.rowcount
        finally:
            conn.close()

    def _ensure_database(self) -> None:
        conn = self._connect(with_db=False)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"CREATE DATABASE IF NOT EXISTS `{self._database}` "
                    "DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
        finally:
            conn.close()

    def _ensure_tables(self) -> None:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(_CREATE_TABLE)
        finally:
            conn.close()

    def _maybe_migrate_from_json(self) -> None:
        """首次使用（sessions 表为空）时，把 .agent_history/ 下的存量数据导入"""
        if self._fetch("SELECT COUNT(*) FROM sessions")[0][0]:
            return
        files = [
            name
            for name in os.listdir(self.data_dir)
            if name.endswith(".json") and os.path.isfile(os.path.join(self.data_dir, name))
        ]
        if not files:
            return
        conn = self._connect()
        imported = 0
        try:
            with conn.cursor() as cur:
                for name in files:
                    try:
                        with open(
                            os.path.join(self.data_dir, name), "r", encoding="utf-8"
                        ) as f:
                            data = json.load(f)
                    except (json.JSONDecodeError, OSError):
                        continue
                    if not isinstance(data, dict) or not data.get("id"):
                        continue
                    cur.execute(
                        "INSERT INTO sessions (session_id, title, message_count, "
                        "created_at, updated_at, messages) VALUES (%s, %s, %s, %s, %s, %s)",
                        (
                            data["id"],
                            data.get("title") or "",
                            data.get("message_count", 0),
                            data.get("created_at", time.time()),
                            data.get("updated_at", time.time()),
                            json.dumps(data.get("messages") or [], ensure_ascii=False),
                        ),
                    )
                    imported += 1
        finally:
            conn.close()
        print(
            f"[MySQL 存储] 已从旧版 .agent_history/ 迁移历史会话 {imported} 个",
            flush=True,
        )

    # ---------- 会话生命周期 ----------
    @staticmethod
    def _row_to_dict(row: tuple[Any, ...]) -> dict[str, object]:
        messages: list[object] = []
        if row[5]:
            try:
                messages = json.loads(row[5])
            except (json.JSONDecodeError, TypeError):
                messages = []
        return {
            "id": row[0],
            "title": row[1],
            "message_count": row[2],
            "created_at": row[3],
            "updated_at": row[4],
            "messages": messages,
        }

    def create_session(self) -> str:
        """新建一个空会话，返回会话 ID"""
        sid = uuid.uuid4().hex[:12]
        now = time.time()
        self._execute(
            "INSERT INTO sessions (session_id, title, message_count, created_at, "
            "updated_at, messages) VALUES (%s, '', 0, %s, %s, '[]')",
            (sid, now, now),
        )
        return sid

    def get_session(self, session_id: str) -> dict[str, object] | None:
        """返回会话元数据（含消息原始数据），不存在返回 None"""
        rows = self._fetch(
            "SELECT session_id, title, message_count, created_at, updated_at, messages "
            "FROM sessions WHERE session_id = %s",
            (session_id,),
        )
        if not rows:
            return None
        return self._row_to_dict(rows[0])

    def delete_session(self, session_id: str) -> bool:
        """删除一个会话，成功返回 True"""
        return self._execute(
            "DELETE FROM sessions WHERE session_id = %s", (session_id,)
        ) > 0

    def list_sessions(
        self, keyword: str = "", limit: int | None = None
    ) -> list[dict[str, object]]:
        """列出所有会话，按更新时间倒序。

        keyword 非空时匹配标题或消息内容（大小写不敏感），% / _ / \\ 通配符
        转义为字面量，与旧版包含匹配语义一致。
        """
        kw = (keyword or "").strip().lower()
        sql = (
            "SELECT session_id, title, message_count, created_at, updated_at, messages "
            "FROM sessions"
        )
        args: list[object] = []
        if kw:
            escaped = (
                kw.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            )
            like = "%" + escaped + "%"
            sql += " WHERE title LIKE %s ESCAPE '\\\\' OR messages LIKE %s ESCAPE '\\\\'"
            args.extend([like, like])
        sql += " ORDER BY updated_at DESC"
        if limit is not None:
            sql += " LIMIT %s"
            args.append(int(limit))
        return [self._row_to_dict(r) for r in self._fetch(sql, tuple(args))]

    # ---------- 消息存取 ----------
    def save_messages(
        self,
        session_id: str,
        messages: list[object] | None,
        title_hint: str | None = None,
    ) -> None:
        """保存会话消息（全量覆盖）。

        title_hint: 会话尚无标题时，优先用它生成标题（调用方传原始用户输入，
        避免标题带上记忆注入前缀）。
        """
        if not messages:
            return
        rows = self._fetch(
            "SELECT title FROM sessions WHERE session_id = %s", (session_id,)
        )
        if not rows:
            return
        title = rows[0][0] or ""
        if not title:
            new_title: str | None = None
            if title_hint:
                text = " ".join(title_hint.split())
                if text:
                    new_title = text[:TITLE_MAX] + (
                        "…" if len(text) > TITLE_MAX else ""
                    )
            if not new_title:
                new_title = _make_title(messages)
            title = new_title or ""
        self._execute(
            "UPDATE sessions SET title = %s, message_count = %s, updated_at = %s, "
            "messages = %s WHERE session_id = %s",
            (
                title,
                len(messages),
                time.time(),
                json.dumps(_dump_messages(messages), ensure_ascii=False),
                session_id,
            ),
        )

    def load_messages(self, session_id: str) -> list[object] | None:
        """加载会话消息（反序列化为 pydantic-ai 消息）；不存在/为空返回 None"""
        rows = self._fetch(
            "SELECT messages FROM sessions WHERE session_id = %s", (session_id,)
        )
        if not rows or not rows[0][0]:
            return None
        try:
            raw = json.loads(rows[0][0])
        except (json.JSONDecodeError, TypeError):
            return None
        if not raw:
            return None
        return _parse_messages(raw)


def messages_to_display(messages: list[Any] | None) -> list[tuple[str, str]]:
    """把 pydantic-ai 消息转成 [(role, content), ...]，供 CLI / UI 展示历史。

    工具调用与返回合并进对应轮次并加 [调用工具 xxx] / [工具返回 xxx] 标注，
    系统提示词不展示。
    """
    pairs: list[tuple[str, str]] = []
    if not _has_pydantic_ai or not messages:
        return pairs
    assert (
        ModelRequest is not None
        and ModelResponse is not None
        and UserPromptPart is not None
        and RetryPromptPart is not None
        and SystemPromptPart is not None
        and ToolReturnPart is not None
        and TextPart is not None
        and ToolCallPart is not None
    )
    for m in messages:
        if isinstance(m, ModelRequest):
            parts: list[str] = []
            for p in m.parts:
                if isinstance(p, (UserPromptPart, RetryPromptPart)):
                    parts.append(_content_to_str(p.content))
                elif isinstance(p, SystemPromptPart):
                    continue  # 系统提示词不展示
                elif isinstance(p, ToolReturnPart):  # pyright: ignore[reportUnnecessaryIsInstance]  # 部分 pydantic-ai 版本中 ToolSearch/LoadCapability 亦继承此类，isinstance 检查不可省
                    parts.append(f"[工具 {p.tool_name}] {p.content}")
            text = "\n".join(x for x in parts if x)
            if text:
                pairs.append(("user", text))
        elif isinstance(m, ModelResponse):
            parts = []
            for p in m.parts:
                if isinstance(p, TextPart):
                    parts.append(p.content)
                elif isinstance(p, ToolCallPart):
                    parts.append(f"[调用工具 {p.tool_name}]")
            text = "\n".join(x for x in parts if x)
            if text:
                pairs.append(("assistant", text))
    return pairs


def format_session_row(s: dict[str, Any]) -> str:
    """CLI 列表单行格式化"""
    updated = datetime.fromtimestamp(s.get("updated_at", 0.0)).strftime("%m-%d %H:%M")
    title = (s.get("title") or "(无标题)").strip()[:TITLE_MAX]
    return (
        f"{s.get('id', ''):<14} {title:<{TITLE_MAX + 2}} "
        f"{s.get('message_count', 0):>4} 条  更新于 {updated}"
    )
