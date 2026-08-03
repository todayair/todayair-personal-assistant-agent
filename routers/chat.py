"""对话路由：/api/chat/{sid}（SSE 流式）"""

import asyncio
import os
import time
from typing import Any, AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agent import agent, chat_stream as agent_chat_stream
from web_state import (
    CHAT_TIMEOUT,
    _TEXT_EXTENSIONS,
    _TEXT_INJECT_MAX,
    _histories,
    logger,
    memory,
    store,
)

from .common import _iso, _mid, _sse

router = APIRouter(tags=["chat"])


class ChatBody(BaseModel):
    content: str
    attachments: list[dict[str, Any]] = []


@router.post("/api/chat/{sid}")
async def chat_stream(sid: str, body: ChatBody) -> StreamingResponse:
    # 会话可能已被空会话清理删除；首次发消息时由 save_messages 自动重建
    message = body.content.strip()
    if not message and not body.attachments:
        raise HTTPException(400, "消息不能为空")
    history = _histories.get(sid)
    if history is None:
        history = store.load_messages(sid) or []
    return StreamingResponse(
        _chat_events(sid, message, history, body.attachments),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _chat_events(
    sid: str,
    message: str,
    history: list[Any],
    attachments: list[dict[str, Any]] | None = None,
) -> AsyncIterator[str]:
    # 小文本附件直接读出内容，避免 Agent 用 Shell/FileSystem 工具读取时卡死
    def read_text_attachment(a: dict[str, Any]) -> str | None:
        try:
            path = a.get("path") or ""
            if not path or os.path.getsize(path) > _TEXT_INJECT_MAX:
                return None
            if os.path.splitext(path)[1].lower() not in _TEXT_EXTENSIONS:
                return None
            with open(path, "rb") as f:
                data = f.read()
            if b"\x00" in data:
                return None
            return data.decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            return None

    new_msgs: list[Any] = []
    prompt = message
    if attachments:
        injected: list[str] = []
        pending: list[str] = []
        for a in attachments:
            content = read_text_attachment(a)
            if content is not None:
                injected.append(
                    f"- {a.get('name', '文件')}：内容如下，直接使用即可：\n```\n{content}\n```"
                )
            else:
                pending.append(f"- {a.get('name', '文件')}: {a.get('path', '')}")
        parts = [message]
        if injected:
            parts.append(
                "[用户上传了附件，以下文件内容已直接附上，请基于内容回答，"
                "无需再调用工具读取：\n" + "\n".join(injected) + "\n]"
            )
        if pending:
            parts.append(
                "[用户上传了附件（二进制/大文件，内容未附上），"
                "如需使用请用 FileSystem 工具读取：\n" + "\n".join(pending) + "\n]"
            )
        prompt = "\n\n".join(parts)

    # 真流式：chat_stream 逐块产出事件（文本增量/工具调用/工具完成）
    gen = agent_chat_stream(agent, prompt, history, memory=memory, original_message=message)
    assistant_text = ""
    try:
        try:
            async with asyncio.timeout(CHAT_TIMEOUT):
                while True:
                    try:
                        evt = await gen.__anext__()
                    except StopAsyncIteration:
                        break
                    etype = evt.get("type")
                    if etype == "tool":
                        yield _sse({"type": "tool", "toolName": evt.get("toolName", "tool")})
                    elif etype == "toolResult":
                        yield _sse(
                            {"type": "toolResult", "toolName": evt.get("toolName", "")}
                        )
                    elif etype == "text":
                        text = evt.get("text", "")
                        assistant_text += text
                        yield _sse({"type": "chunk", "text": text})
                    elif etype == "done":
                        new_msgs = evt.get("new_msgs") or []
                        break
        except asyncio.TimeoutError:
            yield _sse(
                {
                    "type": "error",
                    "message": f"对话处理超时（>{CHAT_TIMEOUT // 60} 分钟），请重试",
                }
            )
            return
        except Exception as e:  # noqa: BLE001
            yield _sse({"type": "error", "message": str(e)})
            return
    finally:
        # 无论正常结束、超时还是客户端断开，都显式关闭流式生成器，
        # 确保 agent run 与 MCP 工具集会话被正确清理
        await gen.aclose()
    combined = history + new_msgs
    _histories[sid] = combined
    try:
        store.save_messages(sid, combined, title_hint=message)
    except Exception as e:  # noqa: BLE001
        logger.error("保存会话失败: %s", e)

    final_msg = {
        "id": _mid(),
        "role": "assistant",
        "content": assistant_text,
        "timestamp": _iso(time.time()),
    }
    yield _sse({"type": "done", "message": final_msg})
