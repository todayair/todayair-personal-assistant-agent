"""
基于 pydantic-ai + Harness 的交互式 Agent 对话程序（入口与兼容导出）
====================================================================

代码拆分后的职责：
    agent_core.py   配置、工具集、agent 实例、LLM 工具注册、展示辅助
    chat_logic.py   chat() / chat_stream() 对话逻辑（含全局运行锁）
    cli.py          命令行交互界面 main()

本文件保留对外导出（web_api.py 等仍从 agent 导入），并作为 CLI 入口。

用法：
    python agent.py
"""

import asyncio

from agent_core import (
    MODEL,
    SYSTEM_PROMPT,
    SUMMARY_MODEL,
    SUMMARY_TARGET_TOKENS,
    PROMPT_CACHING_ENABLED,
    EMAIL_ENABLED,
    agent,
    calendar_summary,
    personal,
    personal_summary,
    reminder_task_lock,
    toolsets,
    wake_event,
)
from chat_logic import chat, chat_stream
from cli import main, print_header

if __name__ == "__main__":
    asyncio.run(main())
