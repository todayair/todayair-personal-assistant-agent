"""状态路由：/api/status"""

import time
from typing import Any

from fastapi import APIRouter

from agent import MODEL, agent, personal
from memory import EMBED_MODEL
from web_state import CAPABILITIES, VERSION, _start_time, memory, store

router = APIRouter(tags=["status"])


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


@router.get("/api/status")
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
