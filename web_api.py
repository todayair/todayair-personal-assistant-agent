"""
Web API 后端（FastAPI）
======================

为 Next.js 前端（personal-assistant-agent-web-console）提供 REST API：
对话（SSE 流式）、待办、笔记、提醒、历史会话、状态、附件上传、邮箱。

拆分后的结构：
    web_state.py    共享状态（存储/记忆/日志/会话缓存/常量）
    routers/        按业务域拆分的路由模块
    chat_logic.py   对话逻辑（chat / chat_stream）

启动：python web_api.py
默认监听 http://127.0.0.1:8000，前端通过 NEXT_PUBLIC_API_BASE 指向本服务。

与 CLI（agent.py）共享同一套全局 agent / personal 存储，数据完全互通。
"""

import asyncio
import os
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from agent import agent, personal, wake_event
from chat_logic import chat
from routers import (
    chat as chat_router,
    history as history_router,
    mail as mail_router,
    notes as notes_router,
    reminders as reminders_router,
    sessions as sessions_router,
    status as status_router,
    todos as todos_router,
    uploads as uploads_router,
)
from web_state import (
    LOG_DIR,
    LOG_FILE,
    UPLOAD_DIR,
    VERSION,
    _FIRED_KEEP_SECONDS,
    _fired_events,
    _task_lock,
    logger,
    memory,
)


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
                _fired_events.append({
                    "ts": time.time(),
                    "id": r["id"],
                    "text": r["text"],
                    "when": r.get("when"),
                })
                task_text = r.get("task")
                if task_text:
                    async with _task_lock:
                        try:
                            logger.info("[定时任务] 执行 #%s: %s", r["id"], task_text)
                            await chat(agent, task_text, memory=memory)
                            logger.info("[定时任务] 完成 #%s", r["id"])
                        except Exception as e:  # noqa: BLE001
                            logger.error("[定时任务] 失败 #%s: %s", r["id"], e)
            _fired_events[:] = [
                e for e in _fired_events if e["ts"] > time.time() - _FIRED_KEEP_SECONDS
            ]
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
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# ---------- 路由（按业务域拆分自原 web_api.py） ----------
app.include_router(sessions_router.router)
app.include_router(uploads_router.router)
app.include_router(chat_router.router)
app.include_router(todos_router.router)
app.include_router(notes_router.router)
app.include_router(reminders_router.router)
app.include_router(mail_router.router)
app.include_router(history_router.router)
app.include_router(status_router.router)


def _start_stack_dumper(interval: float = 120.0) -> None:
    """后台线程定期转储主线程（asyncio 事件循环）调用栈到 stdout。

    Windows 不支持 faulthandler 定时器；服务一旦卡死（事件循环被同步调用阻塞），
    日志里仍能看到主线程卡在哪个函数，便于定位问题。可通过
    STACK_DUMP_INTERVAL=0 关闭。
    """
    import sys
    import threading
    import traceback

    def dump() -> None:
        while True:
            time.sleep(interval)
            frames = sys._current_frames()  # noqa: SLF001
            main_id = threading.main_thread().ident
            lines = [f"===== 线程栈转储 {time.strftime('%H:%M:%S')} ====="]
            for tid, frame in frames.items():
                if tid == main_id:
                    lines.append("--- 主线程（事件循环） ---")
                    lines.extend(traceback.format_stack(frame))
            lines.append("===== 转储结束 =====")
            print("\n".join(lines), flush=True)

    threading.Thread(target=dump, daemon=True).start()


if __name__ == "__main__":
    import uvicorn

    os.makedirs(LOG_DIR, exist_ok=True)
    if int(os.getenv("STACK_DUMP_INTERVAL", "120")) > 0:
        _start_stack_dumper(float(os.getenv("STACK_DUMP_INTERVAL", "120")))
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
