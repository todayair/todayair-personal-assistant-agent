"""历史会话路由：/api/history"""

from typing import Any

from fastapi import APIRouter

from web_state import _histories, store

from .common import _session_dict

router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("")
async def history_search(keyword: str = "") -> list[dict[str, Any]]:
    return [_session_dict(s) for s in store.list_sessions(keyword=keyword.strip(), limit=100)]


@router.delete("/{sid}")
async def history_delete(sid: str) -> dict[str, bool]:
    _histories.pop(sid, None)
    return {"ok": store.delete_session(sid)}
