"""
命令行交互界面（CLI）
=====================

从 agent.py 拆分而来。提供交互式对话、/ 命令处理与后台提醒调度。

用法：
    python agent.py        （或 python -m cli）
"""

import asyncio
import os

from agent_core import (
    MODEL,
    PROMPT_CACHING_ENABLED,
    SUMMARY_MODEL,
    SUMMARY_TARGET_TOKENS,
    EMAIL_ENABLED,
    agent,
    calendar_summary,
    personal,
    personal_summary,
    reminder_task_lock,
    toolsets,
    wake_event,
)
from chat_logic import chat
from history import format_session_row, messages_to_display
from memory import get_memory
from personal import format_fired_reminder
from storage import create_session_store


def print_header():
    print()
    print("═" * 52)
    print(f"  Pydantic AI 交互式 Agent 对话")
    print(f"  模型: {MODEL}")
    print(f"  输入 /help 查看全部指令与能力 | /exit 退出")
    print("═" * 52)


async def main():
    # 初始化外部记忆系统（模型本地优先：已有缓存秒开，仅首次需要联网下载）
    print("正在初始化记忆系统...", flush=True)
    memory = get_memory()

    print_header()
    if memory.enabled:
        print(f"外部记忆: 已启用 (ChromaDB, {memory.count} 条)", flush=True)
    else:
        reason = f" ({memory.init_error})" if memory.init_error else " (已关闭)"
        print(f"外部记忆: 未启用{reason}", flush=True)
        if not memory.init_error:
            print("      设置 MEMORY_ENABLED=true 并 pip install chromadb sentence-transformers", flush=True)
    print()

    all_messages: list | None = None  # pyright: ignore[reportMissingTypeArgument]

    # 历史会话存储：统一使用 MySQL 持久化（每轮对话自动保存，/history 查找、
    # /load 恢复继续对话；初始化失败直接报错终止）
    store = create_session_store()
    current_session_id = store.create_session()
    print(f"当前会话: {current_session_id}（/history 查看历史，/load <ID> 加载历史会话）", flush=True)

    # 后台提醒调度任务：按最小堆休眠到下一个到期提醒（或 60s 兜底），
    # 新增提醒通过 wake_event 立即唤醒，避免睡过头
    stop_event = asyncio.Event()

    async def reminder_loop():
        while not stop_event.is_set():
            wait = personal.seconds_until_next()
            if wait is None:
                wait = 60.0  # 无提醒时兜底轮询，防事件丢失
            try:
                # 等 wake_event 被 set，或休眠到下一提醒到期时间（封顶 60s）
                await asyncio.wait_for(wake_event.wait(), timeout=min(wait, 60.0))
            except asyncio.TimeoutError:
                pass
            wake_event.clear()
            fired = personal.check_reminders()
            for r in fired:
                print()
                print("═" * 40)
                print(format_fired_reminder(r))
                print("═" * 40, flush=True)
                task_text = r.get("task")
                if task_text:
                    async with reminder_task_lock:
                        try:
                            print(f"[定时任务] 执行: {task_text}", flush=True)
                            await chat(agent, task_text, memory=memory)
                            print("[定时任务] 已完成", flush=True)
                        except Exception as e:  # noqa: BLE001
                            print(f"[定时任务] 失败: {e}", flush=True)

    # 在 agent 生命周期上下文中运行整个对话，确保 MCP 连接持续可用
    async with agent:
        reminder_task = asyncio.create_task(reminder_loop())
        try:
            # 退出方式统一为 /exit（exit / quit 亦可）：Ctrl+C 在 Windows 终端中是
            # 复制快捷键，这里捕获中断信号并忽略，退出不会误触发，复制也不会误退出
            while True:
                try:
                    user_input = (await asyncio.to_thread(input, "\n你: ")).strip()
                except (EOFError, asyncio.CancelledError):
                    print("退出中.....", flush=True)
                    print("\n[对话已结束]", flush=True)
                    break
                except KeyboardInterrupt:
                    print(
                        "\n[提示] Ctrl+C 不会退出程序（复制文本请先选中再按 Ctrl+C）。"
                        + "退出请输入 /exit。",
                        flush=True,
                    )
                    continue

                if not user_input:
                    continue

                if user_input.lower() in ("/exit", "/quit", "exit", "quit"):
                    print("退出中.....", flush=True)
                    print("\n[对话已结束]", flush=True)
                    break

                if user_input.lower() == "/clear":
                    all_messages = None
                    current_session_id = store.create_session()
                    print(f"\n[对话历史已清空，已开始新会话 {current_session_id}]", flush=True)
                    continue

                if user_input.lower() == "/new":
                    all_messages = None
                    current_session_id = store.create_session()
                    print(f"\n[已开始新会话 {current_session_id}]", flush=True)
                    continue

                if user_input.lower().startswith("/history"):
                    parts = user_input.split(maxsplit=1)
                    kw = parts[1].strip() if len(parts) > 1 else ""
                    sessions = store.list_sessions(keyword=kw, limit=20)
                    if not sessions:
                        suffix = f"（关键词: {kw}）" if kw else ""
                        print(f"\n没有找到历史会话{suffix}", flush=True)
                    else:
                        suffix = f"，关键词: {kw}" if kw else ""
                        print(f"\n历史会话（共 {len(sessions)} 个{suffix}）:", flush=True)
                        for s in sessions:
                            print("  " + format_session_row(s), flush=True)
                        print("\n用 /load <会话ID> 加载某个会话继续对话", flush=True)
                    continue

                if user_input.lower().startswith("/load"):
                    parts = user_input.split(maxsplit=1)
                    if len(parts) < 2 or not parts[1].strip():
                        print("\n用法: /load <会话ID>（用 /history 查看）", flush=True)
                        continue
                    sid = parts[1].strip()
                    loaded = store.load_messages(sid)
                    if loaded is None:
                        print(f"\n未找到会话 {sid}（用 /history 查看）", flush=True)
                        continue
                    meta = store.get_session(sid) or {}
                    title = meta.get("title") or "(无标题)"
                    pairs = messages_to_display(loaded)
                    all_messages = loaded
                    current_session_id = sid
                    print(f"\n已加载历史会话 {sid}: {title}（共 {len(pairs)} 轮）", flush=True)
                    for role, text in pairs[-4:]:
                        tag = "你" if role == "user" else "AI"
                        print(f"  {tag}: {text[:120]}", flush=True)
                    print("\n[已恢复该会话上下文，直接输入即可继续对话]", flush=True)
                    continue

                if user_input.lower() == "/memory":
                    print(f"\n外部记忆 (ChromaDB): {memory.count} 条", flush=True)
                    print(f"   存储路径: {os.path.abspath('.agent_memory')}", flush=True)
                    print(f"   嵌入模型: intfloat/multilingual-e5-small", flush=True)
                    print(f"   相似度阈值: ≥{os.getenv('MEMORY_MIN_SIMILARITY', '0.4')} 才注入", flush=True)
                    print(f"   会话记忆: {'已启用' if memory.enabled else '已关闭'}", flush=True)
                    print(f"", flush=True)
                    print(f"   隐私保护:", flush=True)
                    print(f"   手机号/密码/银行卡/身份证 → 自动跳过，不存记忆", flush=True)
                    print(f"   低价值对话（寒暄/天气/短回答）→ 自动跳过，不存记忆", flush=True)
                    print(f"   可用 /forget 清空所有记忆", flush=True)
                    continue

                if user_input.lower() == "/forget":
                    cleared = memory.clear()
                    print(f"\n已清空 {cleared} 条记忆", flush=True)
                    continue

                if user_input.lower() == "/todos":
                    print(personal_summary(personal, "todos"), flush=True)
                    continue

                if user_input.lower() == "/notes":
                    print(personal_summary(personal, "notes"), flush=True)
                    continue

                if user_input.lower() == "/reminders":
                    print(personal_summary(personal, "reminders"), flush=True)
                    continue

                if user_input.lower() == "/calendar":
                    print(calendar_summary(personal), flush=True)
                    continue

                if user_input.lower() in ("/help", "/tools"):
                    print("\n── 可用指令 ──", flush=True)
                    print("  /help      查看全部指令与能力", flush=True)
                    print("  /memory    查看记忆状态与隐私规则", flush=True)
                    print("  /todos     查看待办列表", flush=True)
                    print("  /notes     查看笔记列表", flush=True)
                    print("  /reminders 查看提醒列表", flush=True)
                    print("  /calendar  查看日历日程（待办+提醒按日期分组）", flush=True)
                    print("  /forget    清空所有长期记忆", flush=True)
                    print("  /history   查看历史会话（可带关键词）", flush=True)
                    print("  /load <ID> 加载历史会话继续对话", flush=True)
                    print("  /new       开始新会话", flush=True)
                    print("  /clear     清空当前对话", flush=True)
                    print("  /exit      退出程序（exit / quit 亦可）", flush=True)
                    print("", flush=True)
                    print("── 已注册能力 ──", flush=True)
                    print("  • WebSearch              — 联网搜索（DuckDuckGo）", flush=True)
                    print("  • FileSystem             — 文件读写、编辑、搜索", flush=True)
                    print("  • Shell                  — 执行系统命令", flush=True)
                    print("  • Todo/Note/Reminder     — 待办、笔记、提醒（10 个工具）", flush=True)
                    print("      \"添加待办：周三交报告\" / \"记笔记：…\" / \"提醒我 30 分钟后喝水\"", flush=True)
                    print("  • 日历 Calendar          — /calendar 查看；带截止时间的待办与提醒自动汇入日历", flush=True)
                    print("", flush=True)
                    print("外部记忆系统 (ChromaDB):", flush=True)
                    print(f"      状态: {'已启用' if memory.enabled else '已关闭'}", flush=True)
                    print(f"      嵌入模型: intfloat/multilingual-e5-small", flush=True)
                    print(f"      记忆数: {memory.count} 条", flush=True)
                    print(f"      相似度阈值: ≥{os.getenv('MEMORY_MIN_SIMILARITY', '0.4')} 才注入", flush=True)
                    if memory.enabled:
                        print("      每次对话前自动检索 top-3 相似记忆注入上下文", flush=True)
                    print("      低价值/敏感对话自动过滤，不存记忆", flush=True)
                    print("", flush=True)
                    print("个人效率 (存储: MySQL):", flush=True)
                    print(f"      待办: {len(personal.list_todos())} 条 | 笔记: {len(personal.list_notes())} 条 | 提醒: {len(personal.list_reminders(only_pending=True))} 条", flush=True)
                    print("      命令: /todos /notes /reminders /calendar 查看", flush=True)
                    print("", flush=True)
                    print("历史会话 (存储: MySQL):", flush=True)
                    print(f"      会话: {len(store.list_sessions(limit=10000))} 个（每轮对话自动保存）", flush=True)
                    print("      命令: /history [关键词] /load <ID> 查看与恢复", flush=True)
                    print("", flush=True)
                    print("上下文压缩 (TieredCompaction):", flush=True)
                    print(f"      目标: {SUMMARY_TARGET_TOKENS} tokens", flush=True)
                    print("      第一层: ClearToolResults — 清空最旧工具结果（零成本）", flush=True)
                    print(f"      第二层: SummarizingCompaction — LLM 摘要旧对话", flush=True)
                    print(f"        ├─ 摘要模型: {SUMMARY_MODEL}", flush=True)
                    print(f"        ├─ 触发阈值: > 20 条消息", flush=True)
                    print(f"        └─ 保留: 最近 10 条 + 摘要", flush=True)
                    print("", flush=True)
                    if PROMPT_CACHING_ENABLED:
                        print("  DeepSeek Prompt Caching: 已启用（自动，无需配置）", flush=True)
                        print("      系统提示词和对话前缀会被自动缓存，降低延迟和费用。", flush=True)
                    print("", flush=True)
                    print("  • MCP 外部工具集：", flush=True)
                    if toolsets:
                        for ts in toolsets:
                            print(f"      └─ {ts}", flush=True)
                    print("  • 国内邮箱（mail_* 工具，QQ/163/126/Outlook）：", flush=True)
                    if EMAIL_ENABLED:
                        print("      状态: 已启用", flush=True)
                        print("      收信: \"查看收件箱\" / \"搜索 xxx 的未读邮件\" → mail_search_emails", flush=True)
                        print("      读信: \"读一下最新那封邮件\" → mail_read_email（附件自动保存到本机）", flush=True)
                        print("      发信: \"发邮件给 a@b.com，主题…，内容…\" → mail_send_email", flush=True)
                        print("      回信: \"回复刚才那封邮件：…\" → mail_reply_email", flush=True)
                        print("      管理: \"标为已读\" / \"移到 xx 文件夹\" / \"删除这封邮件\" → mail_mark_read / mail_move_email / mail_delete_email", flush=True)
                        print("      其他: \"看有哪些文件夹\" → mail_list_folders", flush=True)
                    else:
                        print("      状态: 未启用（在 .env 配置 EMAIL_ADDRESS / EMAIL_PASSWORD 授权码后重启启用）", flush=True)
                    continue

                print("AI: ", end="", flush=True)
                try:
                    new_msgs = await chat(agent, user_input, all_messages, memory=memory)
                    if all_messages is None:
                        all_messages = new_msgs
                    else:
                        all_messages.extend(new_msgs)
                    # 自动保存当前会话到历史存储，供 /history /load 使用
                    store.save_messages(current_session_id, all_messages, title_hint=user_input)
                except Exception as e:
                    print(f"\n[错误] {e}")
                    print("[提示] 请检查 API Key、模型名称和网络连接。")
        finally:
            stop_event.set()
            wake_event.set()  # 唤醒休眠中的调度循环，使其立即退出
            reminder_task.cancel()
