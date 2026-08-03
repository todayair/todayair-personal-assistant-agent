"""待办路由：/api/todos"""

import time
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agent import personal
from personal import extract_time

from .common import _iso, _parse_iso, _todo_dict

router = APIRouter(prefix="/api/todos", tags=["todos"])


@router.get("")
async def list_todos() -> list[dict[str, Any]]:
    return [_todo_dict(t) for t in personal.list_todos()]


class TodoBody(BaseModel):
    content: str
    due: str = ""


@router.post("")
async def add_todo(body: TodoBody) -> dict[str, Any]:
    text = body.content.strip()
    if not text:
        raise HTTPException(400, "内容不能为空")
    due = ""
    if body.due.strip():
        try:
            ts = _parse_iso(body.due.strip())
            due = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
        except Exception as e:
            raise HTTPException(400, "截止时间解析失败: " + str(e)) from e
    else:
        # 未显式指定截止时间时，尝试从内容中提取（如“明天出门”→“明天 09:00”）
        text, ts = extract_time(text)
        if ts is not None:
            due = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
    return _todo_dict(personal.add_todo(text, due or None))


@router.post("/{tid}/complete")
async def complete_todo(tid: int) -> dict[str, Any]:
    if not personal.complete_todo(tid):
        raise HTTPException(404, "待办不存在")
    row = next((t for t in personal.list_todos() if t["id"] == tid), None)
    return _todo_dict(row) if row else {"id": tid, "content": "", "completed": True, "createdAt": _iso(time.time())}


class TodoUpdateBody(BaseModel):
    content: str | None = None
    due: str | None = None


@router.put("/{tid}")
async def update_todo(tid: int, body: TodoUpdateBody) -> dict[str, Any]:
    text = body.content.strip() if body.content is not None else None
    if text is not None and not text:
        raise HTTPException(400, "内容不能为空")
    due: str | None = None
    if body.due is not None:
        if body.due.strip():
            try:
                ts = _parse_iso(body.due.strip())
                due = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
            except Exception as e:
                raise HTTPException(400, "截止时间解析失败: " + str(e)) from e
        else:
            due = ""
    elif text is not None:
        # 未显式指定截止时间时，尝试从新内容中提取（如“明天出门”→“明天 09:00”）
        new_text, ts = extract_time(text)
        if ts is not None:
            text = new_text
            due = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
    if not personal.update_todo(tid, text=text, due=due):
        raise HTTPException(404, "待办不存在")
    row = next((t for t in personal.list_todos() if t["id"] == tid), None)
    if row is None:
        raise HTTPException(404, "待办不存在")
    return _todo_dict(row)


@router.delete("/{tid}")
async def delete_todo(tid: int) -> dict[str, bool]:
    return {"ok": personal.delete_todo(tid)}
