"""
个人效率工具：MySQL 存储后端（唯一存储后端）

公开接口：add_todo / list_todos / complete_todo / delete_todo / add_note /
list_notes / delete_note / add_reminder / list_reminders / delete_reminder /
seconds_until_next / check_reminders，以及 todos / notes / reminders 属性
（与旧版 personal.py 的 PersonalManager 保持一致，便于调用方无感切换）。

设计要点：
- 三张表 todos / notes / reminders（首次连接自动建库建表）
- 时间戳统一存 DOUBLE（秒），parse_time / format_time 等纯函数直接复用
- 提醒调度仍基于最小堆（内存加速）；触发时用
  UPDATE ... WHERE is_done = 0 + rowcount 原子标记，CLI 与 UI 双进程
  同时到点也只有一方真正触发，杜绝重复通知
- 首次启动自动把旧版 .agent_personal/ 下的存量数据迁移进库（一次性）

配置（.env）：
    MYSQL_HOST / MYSQL_PORT / MYSQL_USER / MYSQL_PASSWORD / MYSQL_DATABASE
"""

import heapq
import os
import time

import pymysql

from personal import DATA_DIR, Item, load_items, parse_time

# 表名 → 建表 SQL（时间戳用 DOUBLE 秒，兼容 time.time() 语义）
_TABLES: dict[str, str] = {
    "todos": """
        CREATE TABLE IF NOT EXISTS todos (
            id INT AUTO_INCREMENT PRIMARY KEY,
            text TEXT NOT NULL,
            is_done TINYINT(1) NOT NULL DEFAULT 0,
            created_at DOUBLE NOT NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    "notes": """
        CREATE TABLE IF NOT EXISTS notes (
            id INT AUTO_INCREMENT PRIMARY KEY,
            title TEXT NOT NULL,
            content LONGTEXT NOT NULL,
            created_at DOUBLE NOT NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    "reminders": """
        CREATE TABLE IF NOT EXISTS reminders (
            id INT AUTO_INCREMENT PRIMARY KEY,
            text TEXT NOT NULL,
            when_ts DOUBLE NOT NULL,
            is_done TINYINT(1) NOT NULL DEFAULT 0,
            created_at DOUBLE NOT NULL,
            KEY idx_when_done (when_ts, is_done)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
}


class MySQLPersonalManager:
    """待办 / 笔记 / 提醒 的 MySQL 持久化管理器（接口与旧版一致）"""

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        user: str | None = None,
        password: str | None = None,
        database: str | None = None,
        data_dir: str = DATA_DIR,
    ):
        env = os.environ
        self._host = host or env.get("MYSQL_HOST", "127.0.0.1")
        self._port = port or int(env.get("MYSQL_PORT", "3306"))
        self._user = user or env.get("MYSQL_USER", "root")
        self._password = password if password is not None else env.get("MYSQL_PASSWORD", "")
        self._database = database or env.get("MYSQL_DATABASE", "agent_personal")
        self.data_dir = data_dir
        self._ensure_database()
        self._ensure_tables()
        self._maybe_migrate_from_json()
        self._reload_heap()

    # ---------- 连接 ----------
    def _connect(self, with_db: bool = True):
        kwargs = {
            "host": self._host,
            "port": self._port,
            "user": self._user,
            "password": self._password,
            "charset": "utf8mb4",
            "autocommit": True,
        }
        if with_db:
            kwargs["database"] = self._database
        return pymysql.connect(**kwargs)

    def _fetch(self, sql: str, args: tuple = ()) -> list[tuple]:
        """执行查询并返回全部结果行（短连接，用完即关）"""
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, args)
                return list(cur.fetchall())
        finally:
            conn.close()

    def _execute(self, sql: str, args: tuple = ()) -> int:
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
                for ddl in _TABLES.values():
                    cur.execute(ddl)
        finally:
            conn.close()

    def _maybe_migrate_from_json(self) -> None:
        """首次使用（库中三表皆空）时，把 .agent_personal/ 下的存量数据导入"""
        if self._fetch("SELECT COUNT(*) FROM todos")[0][0]:
            return
        if self._fetch("SELECT COUNT(*) FROM notes")[0][0]:
            return
        if self._fetch("SELECT COUNT(*) FROM reminders")[0][0]:
            return
        todos = load_items(os.path.join(self.data_dir, "todos.json"))
        notes = load_items(os.path.join(self.data_dir, "notes.json"))
        reminders = load_items(os.path.join(self.data_dir, "reminders.json"))
        if not (todos or notes or reminders):
            return
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                for t in todos:
                    cur.execute(
                        "INSERT INTO todos (id, text, is_done, created_at) "
                        "VALUES (%s, %s, %s, %s)",
                        (t["id"], t["text"], 1 if t.get("done") else 0,
                         t.get("created_at", time.time())),
                    )
                for n in notes:
                    cur.execute(
                        "INSERT INTO notes (id, title, content, created_at) "
                        "VALUES (%s, %s, %s, %s)",
                        (n["id"], n["title"], n["content"],
                         n.get("created_at", time.time())),
                    )
                for r in reminders:
                    cur.execute(
                        "INSERT INTO reminders (id, text, when_ts, is_done, created_at) "
                        "VALUES (%s, %s, %s, %s, %s)",
                        (r["id"], r["text"], r["when"],
                         1 if r.get("done") else 0,
                         r.get("created_at", time.time())),
                    )
        finally:
            conn.close()
        print(
            f"[MySQL 存储] 已从旧版 .agent_personal/ 迁移存量数据："
            f"待办 {len(todos)} 条、笔记 {len(notes)} 条、提醒 {len(reminders)} 条",
            flush=True,
        )

    # ---------- 待办 ----------
    def add_todo(self, text: str) -> Item:
        created = time.time()
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO todos (text, is_done, created_at) VALUES (%s, 0, %s)",
                    (text, created),
                )
                rid = cur.lastrowid
        finally:
            conn.close()
        return {"id": rid, "text": text, "done": False, "created_at": created}

    def list_todos(self, only_pending: bool = False) -> list[Item]:
        sql = (
            "SELECT id, text, is_done, created_at FROM todos"
            + (" WHERE is_done = 0" if only_pending else "")
            + " ORDER BY is_done ASC, created_at DESC"
        )
        return [
            {"id": r[0], "text": r[1], "done": bool(r[2]), "created_at": r[3]}
            for r in self._fetch(sql)
        ]

    def complete_todo(self, todo_id: int) -> bool:
        return self._execute("UPDATE todos SET is_done = 1 WHERE id = %s", (todo_id,)) > 0

    def delete_todo(self, todo_id: int) -> bool:
        return self._execute("DELETE FROM todos WHERE id = %s", (todo_id,)) > 0

    # ---------- 笔记 ----------
    def add_note(self, title: str, content: str) -> Item:
        created = time.time()
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO notes (title, content, created_at) VALUES (%s, %s, %s)",
                    (title, content, created),
                )
                rid = cur.lastrowid
        finally:
            conn.close()
        return {"id": rid, "title": title, "content": content, "created_at": created}

    def list_notes(self) -> list[Item]:
        rows = self._fetch("SELECT id, title, content, created_at FROM notes ORDER BY created_at DESC")
        return [
            {"id": r[0], "title": r[1], "content": r[2], "created_at": r[3]}
            for r in rows
        ]

    def delete_note(self, note_id: int) -> bool:
        return self._execute("DELETE FROM notes WHERE id = %s", (note_id,)) > 0

    # ---------- 提醒 ----------
    def add_reminder(self, text: str, when: str) -> Item:
        ts = parse_time(when)
        created = time.time()
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO reminders (text, when_ts, is_done, created_at) "
                    "VALUES (%s, %s, 0, %s)",
                    (text, ts, created),
                )
                rid = cur.lastrowid
        finally:
            conn.close()
        reminder = {"id": rid, "text": text, "when": ts, "done": False, "created_at": created}
        heapq.heappush(self._heap, (ts, rid))
        return reminder

    def list_reminders(self, only_pending: bool = False) -> list[Item]:
        sql = (
            "SELECT id, text, when_ts, is_done, created_at FROM reminders"
            + (" WHERE is_done = 0" if only_pending else "")
            + " ORDER BY when_ts ASC"
        )
        return [
            {"id": r[0], "text": r[1], "when": r[2], "done": bool(r[3]), "created_at": r[4]}
            for r in self._fetch(sql)
        ]

    def delete_reminder(self, reminder_id: int) -> bool:
        return self._execute("DELETE FROM reminders WHERE id = %s", (reminder_id,)) > 0

    # ---------- 调度：最小堆 + 原子触发 ----------
    def _reload_heap(self) -> None:
        rows = self._fetch("SELECT when_ts, id FROM reminders WHERE is_done = 0")
        self._heap: list[tuple[float, int]] = [(r[0], r[1]) for r in rows]
        heapq.heapify(self._heap)

    def _claim(self, reminder_id: int) -> Item | None:
        """原子触发一条提醒：仅当它仍处于未触发状态时置为已触发并返回该条。

        用 UPDATE ... WHERE is_done = 0 + rowcount 判断，保证 CLI / UI 多进程
        同时到点时只有一方真正触发，杜绝重复通知。
        """
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE reminders SET is_done = 1 WHERE id = %s AND is_done = 0",
                    (reminder_id,),
                )
                if cur.rowcount == 0:
                    return None
                cur.execute(
                    "SELECT id, text, when_ts, is_done, created_at "
                    "FROM reminders WHERE id = %s",
                    (reminder_id,),
                )
                row = cur.fetchone()
        finally:
            conn.close()
        if row is None:
            return None
        return {
            "id": row[0], "text": row[1], "when": row[2],
            "done": bool(row[3]), "created_at": row[4],
        }

    def seconds_until_next(self) -> float | None:
        """距下一条未触发提醒的剩余秒数；没有任何待触发提醒时返回 None。

        以数据库最早到期时间兜底：其他进程新增的更早提醒会被同步进堆，
        保证多进程场景下也能精确休眠到正确时刻。
        """
        rows = self._fetch("SELECT MIN(when_ts) FROM reminders WHERE is_done = 0")
        db_next = rows[0][0] if rows and rows[0][0] is not None else None
        heap_next = self._heap[0][0] if self._heap else None
        if db_next is not None and (heap_next is None or db_next < heap_next):
            self._reload_heap()  # 库里有更早的到期项 → 全量重建堆（数据量小，简单可靠）
            heap_next = self._heap[0][0] if self._heap else None
        if heap_next is None:
            return None
        return max(0.0, heap_next - time.time())

    def check_reminders(self) -> list[Item]:
        """弹出并返回所有已到时间且未通知的提醒（堆顶调度），标记为已通知。"""
        now = time.time()
        fired: list[Item] = []
        # 1) 堆顶弹出到期项（已删除/已触发的脏元素由 _claim 的原子条件跳过）
        while self._heap and self._heap[0][0] <= now:
            _, rid = heapq.heappop(self._heap)
            r = self._claim(rid)
            if r is not None:
                fired.append(r)
        # 2) 兜底：数据库里仍有到期未触发的（如其他进程新增的提醒）→ 原子触发
        rows = self._fetch(
            "SELECT id FROM reminders WHERE is_done = 0 AND when_ts <= %s ORDER BY when_ts",
            (now,),
        )
        for (rid,) in rows:
            r = self._claim(rid)
            if r is not None:
                fired.append(r)
        return fired

    # ---------- 只读属性（兼容 gradio_ui 的 len(personal.todos) 用法） ----------
    @property
    def todos(self) -> list[Item]:
        return self.list_todos()

    @property
    def notes(self) -> list[Item]:
        return self.list_notes()

    @property
    def reminders(self) -> list[Item]:
        return self.list_reminders()
