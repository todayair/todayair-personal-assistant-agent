"""共享辅助函数（消息/会话/数据行转换、SSE 编码等）"""

import json
import time
import uuid
from datetime import datetime
from typing import Any

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
from web_state import store


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
        "dueAt": _iso(float(t["due"])) if t.get("due") else None,
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
        "repeatRule": r.get("repeat_rule") or "once",
        "task": r.get("task") or "",
        "createdAt": _iso(float(r["created_at"])),
    }


def _sse(data: dict[str, Any]) -> str:
    return "data: " + json.dumps(data, ensure_ascii=False) + "\n\n"
