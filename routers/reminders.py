"""提醒路由：/api/reminders"""

import time
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agent import personal
from web_state import _FIRED_KEEP_SECONDS, _fired_events

from .common import _parse_iso, _reminder_dict

router = APIRouter(prefix="/api/reminders", tags=["reminders"])


@router.get("")
async def list_reminders() -> list[dict[str, Any]]:
    return [_reminder_dict(r) for r in personal.list_reminders()]


@router.get("/fired")
async def fired_reminders(after: float = 0.0) -> list[dict[str, Any]]:
    """返回 after（epoch 秒）之后触发的提醒事件，供前端轮询展示全屏确认。"""
    _fired_events[:] = [
        e for e in _fired_events if e["ts"] > time.time() - _FIRED_KEEP_SECONDS
    ]
    return [e for e in _fired_events if e["ts"] > after]


class ReminderBody(BaseModel):
    text: str
    fireAt: str = ""
    repeat: str = ""
    task: str = ""


@router.post("")
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
        return _reminder_dict(
            personal.add_reminder(
                text, when, repeat_rule=body.repeat or None, task=body.task.strip() or None
            )
        )
    except ValueError as e:
        msg = str(e)
        if "早于当前时间" in msg:
            raise HTTPException(400, msg) from e
        raise HTTPException(400, "时间解析失败: " + msg) from e


@router.put("/{rid}")
async def update_reminder(rid: int, body: ReminderBody) -> dict[str, Any]:
    """更新提醒（内容 / 时间 / 重复规则 / 定时任务）"""
    text = body.text.strip()
    if not text:
        raise HTTPException(400, "内容不能为空")
    if not body.fireAt:
        raise HTTPException(400, "触发时间不能为空")
    ts = _parse_iso(body.fireAt)
    when = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
    try:
        item = personal.update_reminder(
            rid,
            text=text,
            when=when,
            repeat_rule=body.repeat or None,
            task=body.task.strip() or None,
        )
    except ValueError as e:
        msg = str(e)
        if "早于当前时间" in msg:
            raise HTTPException(400, msg) from e
        raise HTTPException(400, "时间解析失败: " + msg) from e
    if item is None:
        raise HTTPException(404, "提醒不存在")
    return _reminder_dict(item)


@router.delete("/{rid}")
async def delete_reminder(rid: int) -> dict[str, bool]:
    return {"ok": personal.delete_reminder(rid)}
