"""
Web API 共享状态：存储、记忆、日志与会话缓存
============================================

从 web_api.py 拆分而来。供 web_api.py（应用装配/生命周期）与 routers/*
各路由模块共用，避免循环导入。
"""

import asyncio
import logging
import os
import time
from typing import Any

from memory import get_memory
from storage import create_session_store

store = create_session_store()
memory = get_memory()

# 每个会话在内存中的消息历史缓存（首查 DB，之后维护在内存，避免重复反序列化）
_histories: dict[str, list[Any]] = {}

_start_time = time.time()
VERSION = "1.0"

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
    {"name": "邮箱", "description": " 支持QQ/163/126/Outlook邮箱收发", "icon": "Mail"},
    {"name": "向量记忆", "description": "ChromaDB 语义检索与上下文压缩", "icon": "Brain"},
    {"name": "个人数据", "description": "待办、笔记、提醒（MySQL 持久化）", "icon": "Database"},
]

# ---------- 提醒调度共享状态（_reminder_loop 与 /api/reminders/fired 共用） ----------
# 已触发提醒的实时事件缓冲（供前端轮询拉取并全屏确认；保留 1 小时）
_fired_events: list[dict[str, Any]] = []
_FIRED_KEEP_SECONDS = 3600.0
# 定时任务执行串行锁（避免多个到点任务并发跑 Agent）
_task_lock = asyncio.Lock()

# ---------- 上传与对话常量 ----------
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
UPLOAD_MAX_BYTES = 20 * 1024 * 1024  # 20MB

# 单次对话处理超时（秒）：超时后向 SSE 下发错误，避免前端无限等待
CHAT_TIMEOUT = int(os.getenv("CHAT_TIMEOUT", "900"))

# 小文本附件直接注入 prompt，避免 Agent 用 Shell/FileSystem 读取时卡死事件循环
_TEXT_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".json", ".csv", ".tsv", ".log",
    ".py", ".js", ".ts", ".tsx", ".html", ".htm", ".css",
    ".yaml", ".yml", ".xml", ".ini", ".cfg", ".conf", ".toml",
}
_TEXT_INJECT_MAX = 20 * 1024  # 20KB
