"""笔记路由：/api/notes"""

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agent import personal

from .common import _note_dict

router = APIRouter(prefix="/api/notes", tags=["notes"])


@router.get("")
async def list_notes() -> list[dict[str, Any]]:
    return [_note_dict(n) for n in personal.list_notes()]


class NoteBody(BaseModel):
    title: str = ""
    content: str = ""


@router.post("")
async def add_note(body: NoteBody) -> dict[str, Any]:
    title = body.title.strip()
    if not title:
        raise HTTPException(400, "标题不能为空")
    return _note_dict(personal.add_note(title, body.content))


@router.delete("/{nid}")
async def delete_note(nid: int) -> dict[str, bool]:
    return {"ok": personal.delete_note(nid)}


class NoteUpdateBody(BaseModel):
    title: str | None = None
    content: str | None = None


@router.put("/{nid}")
async def update_note(nid: int, body: NoteUpdateBody) -> dict[str, Any]:
    title = body.title.strip() if body.title is not None else None
    if title is not None and not title:
        raise HTTPException(400, "标题不能为空")
    if title is None and body.content is None:
        raise HTTPException(400, "没有可更新的内容")
    if not personal.update_note(nid, title=title, content=body.content):
        raise HTTPException(404, "笔记不存在")
    row = next((n for n in personal.list_notes() if n["id"] == nid), None)
    if row is None:
        raise HTTPException(404, "笔记不存在")
    return _note_dict(row)
