"""会话路由：/api/sessions"""

from typing import Any

from fastapi import APIRouter, HTTPException

from web_state import _histories, store

from .common import _empty_session, _session_dict

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.get("")
async def list_sessions() -> list[dict[str, Any]]:
    store.delete_empty_sessions()  # 顺带清理历史遗留的空会话
    return [_session_dict(s) for s in store.list_sessions(limit=100)]


@router.get("/{sid}")
async def get_session(sid: str) -> dict[str, Any]:
    s = store.get_session(sid)
    if not s:
        raise HTTPException(404, "会话不存在")
    return _session_dict(s)


@router.post("")
async def create_session() -> dict[str, Any]:
    store.delete_empty_sessions()  # 旧空会话无保留价值，先清理
    sid = store.create_session()
    _histories[sid] = []
    return _empty_session(sid)


@router.delete("/{sid}")
async def delete_session(sid: str) -> dict[str, bool]:
    _histories.pop(sid, None)
    return {"ok": store.delete_session(sid)}
