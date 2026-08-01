"""
Web API 后端（FastAPI）
======================
为 v0 生成的 Next.js 前端（personal-assistant-agent-web-console）提供 REST API：
对话（SSE 流式）、待办、笔记、提醒、历史会话、状态。

启动：python web_api.py
默认监听 http://127.0.0.1:8000，前端通过 NEXT_PUBLIC_API_BASE 指向本服务。

与 CLI（agent.py）共享同一套全局 agent / personal 存储，数据完全互通。
"""

import asyncio
import json
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# 复用 agent.py 的全局 agent / personal / wake_event 与对话逻辑
from agent import MODEL, agent, chat, personal, wake_event
from history import (
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    SystemPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from memory import EMBED_MODEL, get_memory
from storage import create_session_store

store = create_session_store()
memory = get_memory()

# 每个会话在内存中的消息历史缓存（首查 DB，之后维护在内存，避免重复反序列化）
_histories: dict[str, list[Any]] = {}

_start_time = time.time()
VERSION = "1.0.0"

# ---------- 日志 ----------
# 统一写入 logs/web-api.log（自动轮转），同时保留终端输出
logger = logging.getLogger("app")
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
LOG_FILE = os.path.join(LOG_DIR, "web-api.log")

# 固定能力清单（供状态页展示；工具名随后端真实工具集变化）
CAPABILITIES: list[dict[str, str]] = [
    {"name": "网页搜索", "description": "通过 WebSearch 实时搜索网页内容", "icon": "Globe"},
    {"name": "文件系统", "description": "读写本地文件，浏览目录结构", "icon": "FolderOpen"},
    {"name": "Shell 执行", "description": "运行 Shell 命令和脚本", "icon": "Terminal"},
    {"name": "GitHub MCP", "description": "通过 MCP 工具集管理 GitHub 数据", "icon": "GitBranch"},
    {"name": "向量记忆", "description": "ChromaDB 语义检索与上下文压缩", "icon": "Brain"},
    {"name": "个人数据", "description": "待办、笔记、提醒（MySQL 持久化）", "icon": "Database"},
]


# ---------- 工具函数 ----------
def _mid() -> str:
    """生成前端消息 ID"""
    return uuid.uuid4().hex[:8]


def _iso(ts: float) -> str:
    """时间戳（秒）→ ISO 字符串（带本地时区，前端可直接 new Date 解析）"""
    try:
        return datetime.fromtimestamp(ts).astimezone().isoformat()
    except (OverflowError, OSError, ValueError):
        return datetime.now().astimezone().isoformat()


def _parse_iso(iso: str) -> float:
    """ISO 字符串（前端 datetime-local 转出的）→ 时间戳（秒）"""
    s = iso.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        dt = datetime.now()
    return dt.timestamp()


def _msgs_to_frontend(messages: list[Any] | None) -> list[dict[str, Any]]:
    """pydantic-ai 消息 → 前端 ChatMessage 列表（保留工具调用/返回条目）"""
    out: list[dict[str, Any]] = []
    if not messages:
        return out
    for m in messages:
        ts = time.time()
        if isinstance(m, ModelRequest):
            for p in m.parts:
                if isinstance(p, (UserPromptPart, RetryPromptPart)):
                    content = p.content if isinstance(p.content, str) else str(p.content)
                    if content.strip():
                        out.append(
                            {"id": _mid(), "role": "user", "content": content, "timestamp": _iso(ts)}
                        )
                elif isinstance(p, SystemPromptPart):
                    continue
                elif isinstance(p, ToolReturnPart):  # pyright: ignore[reportUnnecessaryIsInstance]
                    content = p.content if isinstance(p.content, str) else str(p.content)
                    out.append(
                        {
                            "id": _mid(),
                            "role": "tool",
                            "toolName": p.tool_name,
                            "content": content,
                            "timestamp": _iso(ts),
                        }
                    )
        elif isinstance(m, ModelResponse):
            for p in m.parts:
                if isinstance(p, TextPart):
                    out.append(
                        {"id": _mid(), "role": "assistant", "content": p.content, "timestamp": _iso(ts)}
                    )
                elif isinstance(p, ToolCallPart):
                    out.append(
                        {
                            "id": _mid(),
                            "role": "tool",
                            "toolName": p.tool_name,
                            "content": "[调用工具]",
                            "timestamp": _iso(ts),
                        }
                    )
    return out


def _session_dict(s: dict[str, Any]) -> dict[str, Any]:
    """会话行 → 前端 ChatSession"""
    msgs = store.load_messages(s["id"])  # 反序列化为 pydantic-ai 消息
    return {
        "id": s["id"],
        "title": s["title"],
        "messageCount": s["message_count"],
        "updatedAt": _iso(float(s["updated_at"])),
        "messages": _msgs_to_frontend(msgs),
    }


def _empty_session(sid: str) -> dict[str, Any]:
    return {
        "id": sid,
        "title": "",
        "messageCount": 0,
        "updatedAt": _iso(time.time()),
        "messages": [],
    }


def _todo_dict(t: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": t["id"],
        "content": t["text"],
        "completed": bool(t["done"]),
        "createdAt": _iso(float(t["created_at"])),
    }


def _note_dict(n: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": n["id"],
        "title": n["title"],
        "content": n["content"],
        "createdAt": _iso(float(n["created_at"])),
        "updatedAt": _iso(float(n["created_at"])),
    }


def _reminder_dict(r: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": r["id"],
        "text": r["text"],
        "fireAt": _iso(float(r["when"])),
        "status": "fired" if r["done"] else "pending",
        "createdAt": _iso(float(r["created_at"])),
    }


def _sse(data: dict[str, Any]) -> str:
    return "data: " + json.dumps(data, ensure_ascii=False) + "\n\n"


# ---------- 提醒调度（后台任务，与 CLI 共用同一套 MySQL 原子触发） ----------
async def _reminder_loop() -> None:
    while True:
        try:
            wait = personal.seconds_until_next()
            if wait is None:
                await asyncio.sleep(5)
            else:
                await asyncio.sleep(min(wait, 30))
            fired = personal.check_reminders()
            for r in fired:
                logger.info("提醒触发 #%s: %s", r["id"], r["text"])
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            await asyncio.sleep(10)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    reminder_task = asyncio.create_task(_reminder_loop())
    await agent.__aenter__()  # 进入 agent 生命周期（连接 MCP 工具集）
    logger.info("[Web API] agent 就绪，服务启动于 http://127.0.0.1:8000")
    try:
        yield
    finally:
        wake_event.set()
        reminder_task.cancel()
        try:
            await reminder_task
        except asyncio.CancelledError:
            pass
        await agent.__aexit__(None, None, None)


app = FastAPI(title="Personal Assistant Agent Web API", version=VERSION, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- 会话 ----------
@app.get("/api/sessions")
async def list_sessions() -> list[dict[str, Any]]:
    return [_session_dict(s) for s in store.list_sessions(limit=100)]


@app.get("/api/sessions/{sid}")
async def get_session(sid: str) -> dict[str, Any]:
    s = store.get_session(sid)
    if not s:
        raise HTTPException(404, "会话不存在")
    return _session_dict(s)


@app.post("/api/sessions")
async def create_session() -> dict[str, Any]:
    sid = store.create_session()
    _histories[sid] = []
    return _empty_session(sid)


@app.delete("/api/sessions/{sid}")
async def delete_session(sid: str) -> dict[str, bool]:
    _histories.pop(sid, None)
    return {"ok": store.delete_session(sid)}


# ---------- 对话（SSE 流式） ----------
class ChatBody(BaseModel):
    content: str


@app.post("/api/chat/{sid}")
async def chat_stream(sid: str, body: ChatBody) -> StreamingResponse:
    if not store.get_session(sid):
        raise HTTPException(404, "会话不存在")
    message = body.content.strip()
    if not message:
        raise HTTPException(400, "消息不能为空")
    history = _histories.get(sid)
    if history is None:
        history = store.load_messages(sid) or []
    return StreamingResponse(
        _chat_events(sid, message, history),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _chat_events(sid: str, message: str, history: list[Any]) -> AsyncIterator[str]:
    new_msgs: list[Any] = []
    try:
        new_msgs = await chat(agent, message, history, memory=memory)
    except Exception as e:  # noqa: BLE001
        yield _sse({"type": "error", "message": str(e)})
        return
    combined = history + new_msgs
    _histories[sid] = combined
    try:
        store.save_messages(sid, combined, title_hint=message)
    except Exception as e:  # noqa: BLE001
        logger.error("保存会话失败: %s", e)

    # 按顺序发送工具调用事件
    assistant_text = ""
    for m in new_msgs:
        if isinstance(m, ModelResponse):
            for p in m.parts:
                if isinstance(p, ToolCallPart):
                    yield _sse({"type": "tool", "toolName": p.tool_name})
                elif isinstance(p, TextPart):
                    assistant_text += p.content
        elif isinstance(m, ModelRequest):
            for p in m.parts:
                if isinstance(p, ToolReturnPart):  # pyright: ignore[reportUnnecessaryIsInstance]
                    yield _sse({"type": "toolResult", "toolName": p.tool_name})

    # 模拟流式：将助手文本分块下发
    for i in range(0, len(assistant_text), 4):
        yield _sse({"type": "chunk", "text": assistant_text[i : i + 4]})
        await asyncio.sleep(0.012)

    final_msg = {
        "id": _mid(),
        "role": "assistant",
        "content": assistant_text,
        "timestamp": _iso(time.time()),
    }
    yield _sse({"type": "done", "message": final_msg})


# ---------- 待办 ----------
@app.get("/api/todos")
async def list_todos() -> list[dict[str, Any]]:
    return [_todo_dict(t) for t in personal.list_todos()]


class TodoBody(BaseModel):
    content: str


@app.post("/api/todos")
async def add_todo(body: TodoBody) -> dict[str, Any]:
    text = body.content.strip()
    if not text:
        raise HTTPException(400, "内容不能为空")
    return _todo_dict(personal.add_todo(text))


@app.post("/api/todos/{tid}/complete")
async def complete_todo(tid: int) -> dict[str, Any]:
    if not personal.complete_todo(tid):
        raise HTTPException(404, "待办不存在")
    row = next((t for t in personal.list_todos() if t["id"] == tid), None)
    return _todo_dict(row) if row else {"id": tid, "content": "", "completed": True, "createdAt": _iso(time.time())}


@app.delete("/api/todos/{tid}")
async def delete_todo(tid: int) -> dict[str, bool]:
    return {"ok": personal.delete_todo(tid)}


# ---------- 笔记 ----------
@app.get("/api/notes")
async def list_notes() -> list[dict[str, Any]]:
    return [_note_dict(n) for n in personal.list_notes()]


class NoteBody(BaseModel):
    title: str = ""
    content: str = ""


@app.post("/api/notes")
async def add_note(body: NoteBody) -> dict[str, Any]:
    title = body.title.strip()
    if not title:
        raise HTTPException(400, "标题不能为空")
    return _note_dict(personal.add_note(title, body.content))


@app.delete("/api/notes/{nid}")
async def delete_note(nid: int) -> dict[str, bool]:
    return {"ok": personal.delete_note(nid)}


# ---------- 提醒 ----------
@app.get("/api/reminders")
async def list_reminders() -> list[dict[str, Any]]:
    return [_reminder_dict(r) for r in personal.list_reminders()]


class ReminderBody(BaseModel):
    text: str
    fireAt: str = ""


@app.post("/api/reminders")
async def add_reminder(body: ReminderBody) -> dict[str, Any]:
    text = body.text.strip()
    if not text:
        raise HTTPException(400, "内容不能为空")
    if body.fireAt:
        # 前端传 ISO 时间 → "YYYY-MM-DD HH:MM"（parse_time 可解析的格式）
        ts = _parse_iso(body.fireAt)
        when = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
    else:
        raise HTTPException(400, "触发时间不能为空")
    try:
        return _reminder_dict(personal.add_reminder(text, when))
    except ValueError as e:
        raise HTTPException(400, "时间解析失败: " + str(e)) from e


@app.delete("/api/reminders/{rid}")
async def delete_reminder(rid: int) -> dict[str, bool]:
    return {"ok": personal.delete_reminder(rid)}


# ---------- 历史 ----------
@app.get("/api/history")
async def history_search(keyword: str = "") -> list[dict[str, Any]]:
    return [_session_dict(s) for s in store.list_sessions(keyword=keyword.strip(), limit=100)]


@app.delete("/api/history/{sid}")
async def history_delete(sid: str) -> dict[str, bool]:
    _histories.pop(sid, None)
    return {"ok": store.delete_session(sid)}


# ---------- 状态 ----------
def _capabilities() -> list[dict[str, str]]:
    names: set[str] = set()
    try:
        names |= {t.name for t in agent._function_tools.values()}  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass
    try:
        for ts in agent._toolsets:  # type: ignore[attr-defined]
            names |= {t.name for t in ts.get_tools()}  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass
    if names:
        return CAPABILITIES + [
            {"name": n, "description": "Agent 内置工具", "icon": "Wrench"} for n in sorted(names)
        ]
    return CAPABILITIES


@app.get("/api/status")
async def status_endpoint() -> dict[str, Any]:
    all_todos = personal.list_todos()
    up = int(time.time() - _start_time)
    return {
        "model": MODEL,
        "provider": "DeepSeek（OpenAI 兼容接口）",
        "memoryStatus": {
            "vectorCount": memory.count,
            "collectionName": "agent_memory",
            "status": (
                "healthy"
                if memory.enabled and not memory.init_error
                else ("degraded" if memory.init_error else "offline")
            ),
            "embeddingModel": EMBED_MODEL,
        },
        "personalData": {
            "todos": len([t for t in all_todos if not t["done"]]),
            "completedTodos": len([t for t in all_todos if t["done"]]),
            "notes": len(personal.list_notes()),
            "reminders": len(personal.list_reminders()),
            "sessions": len(store.list_sessions()),
        },
        "capabilities": _capabilities(),
        "uptime": f"{up // 3600} 小时 {up % 3600 // 60} 分",
        "version": VERSION,
    }


if __name__ == "__main__":
    import uvicorn

    os.makedirs(LOG_DIR, exist_ok=True)
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8000,
        log_config={
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "()": "uvicorn.logging.DefaultFormatter",
                    "fmt": "%(levelprefix)s %(asctime)s %(message)s",
                    "datefmt": "%Y-%m-%d %H:%M:%S",
                    "use_colors": None,
                },
                "access": {
                    "()": "uvicorn.logging.AccessFormatter",
                    "fmt": '%(levelprefix)s %(client_addr)s - "%(request_line)s" %(status_code)s',
                },
            },
            "handlers": {
                "default": {
                    "formatter": "default",
                    "class": "logging.StreamHandler",
                    "stream": "ext://sys.stderr",
                },
                "access": {
                    "formatter": "access",
                    "class": "logging.StreamHandler",
                    "stream": "ext://sys.stdout",
                },
                "file": {
                    "formatter": "default",
                    "class": "logging.handlers.RotatingFileHandler",
                    "filename": LOG_FILE,
                    "maxBytes": 5 * 1024 * 1024,
                    "backupCount": 3,
                    "encoding": "utf-8",
                },
            },
            "loggers": {
                "uvicorn": {"handlers": ["default", "file"], "level": "INFO", "propagate": False},
                "uvicorn.error": {"handlers": ["default", "file"], "level": "INFO", "propagate": False},
                "uvicorn.access": {"handlers": ["access", "file"], "level": "INFO", "propagate": False},
                "app": {"handlers": ["default", "file"], "level": "INFO", "propagate": False},
            },
        },
    )
