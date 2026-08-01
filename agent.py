"""
基于 pydantic-ai + Harness 的交互式 Agent 对话程序

提供命令行交互界面，支持：
- 多轮对话历史管理
- 系统提示词自定义
- Harness 能力：WebSearch、FileSystem、Shell
- 上下文压缩：TieredCompaction（分级策略：清旧工具结果 → LLM 摘要）
- DeepSeek Prompt Caching（默认启用，前缀自动缓存）
- MCP 外部工具：通过 mcp_config.json 配置
- 国内邮箱（可选）：QQ / 163 / 126 / Outlook 收信与发信（IMAP/SMTP + 授权码，国内直连）

用法：
    python agent.py
"""

import asyncio
import sys

# 确保 stdout 能输出 Unicode（Windows GBK 编码兼容）
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')  # pyright: ignore[reportAttributeAccessIssue]
    except Exception:
        pass
import os

from dotenv import load_dotenv
from pydantic_ai import Agent

# 核心内置能力
from pydantic_ai.capabilities import WebSearch

# MCP 配置文件加载 + 进程内 FastMCP 服务（国内邮箱）
from pydantic_ai.mcp import MCPToolset, load_mcp_toolsets

# Pydantic AI Harness 能力
from pydantic_ai_harness.filesystem import FileSystem
from pydantic_ai_harness.shell import Shell

# 外部记忆系统（ChromaDB 向量数据库）
from memory import get_memory
from personal import format_fired_reminder, format_time
from personal_mysql import MySQLPersonalManager
from storage import create_personal_manager, create_session_store
from history import format_session_row, messages_to_display
from pydantic_ai_harness.compaction import (
    ClearToolResults,
    SummarizingCompaction,
    TieredCompaction,
)

# 加载 .env 文件
load_dotenv()

# ---------- 配置 ----------
MODEL = os.getenv("LLM_MODEL")
SYSTEM_PROMPT = os.getenv("SYSTEM_PROMPT")
assert MODEL is not None
assert SYSTEM_PROMPT is not None

# 上下文压缩配置
# 用于摘要的模型（默认与主模型相同，可设为更便宜的模型如 deepseek:deepseek-v3）
SUMMARY_MODEL = os.getenv("SUMMARY_MODEL") or MODEL
# 压缩目标：将上下文控制在多少 token 以内
SUMMARY_TARGET_TOKENS = int(os.getenv("SUMMARY_TARGET_TOKENS", "100000"))

# DeepSeek Prompt Caching 
PROMPT_CACHING_ENABLED = True

# ---------- 从配置文件加载 MCP 工具集 ----------
# load_mcp_toolsets 自动替换配置中的 ${VAR} 为环境变量值
toolsets = load_mcp_toolsets('mcp_config.json')

# ---------- 国内邮箱（可选：IMAP/SMTP + 授权码，支持 QQ / 163 / 126 / Outlook） ----------
# 在 .env 配置 EMAIL_ADDRESS / EMAIL_PASSWORD（授权码）后自动启用，
# 提供 mail_* 工具：搜索/阅读/发送/回复/标记/移动/删除，国内网络可直接使用。
EMAIL_ENABLED = False
if os.getenv('EMAIL_ADDRESS') and os.getenv('EMAIL_PASSWORD'):
    try:
        from email_tools import server as email_server
        toolsets = [*toolsets, MCPToolset(email_server).prefixed('mail_')]
        EMAIL_ENABLED = True
    except Exception as e:
        print(f'[警告] 国内邮箱工具初始化失败，本次未启用：{e}', flush=True)
# ---------- 创建 Agent ----------
agent = Agent[None](  # pyright: ignore[reportCallIssue]
    model=MODEL,
    system_prompt=SYSTEM_PROMPT,
    deps_type=type(None),  # 显式匹配泛型参数，消除 reportArgumentType
    model_settings={'max_retries': 2, 'timeout': 60},  # pyright: ignore[reportArgumentType]
    capabilities=[
        WebSearch(local=True),
        FileSystem(),
        Shell(),
        # 分层压缩编排：先清旧工具结果（零成本），再 LLM 摘要
        TieredCompaction(
            tiers=[
                # 第一层：清空最旧工具调用的结果（零 LLM 开销）
                ClearToolResults(max_tokens=10000, keep_pairs=3),
                # 第二层：用 LLM 摘要压缩旧对话（仅当第一层不够时触发）
                SummarizingCompaction(
                    model=SUMMARY_MODEL,
                    max_messages=20,   # 超过 20 条消息触发
                    keep_messages=10,  # 保留最近 10 条
                ),
            ],
            target_tokens=SUMMARY_TARGET_TOKENS,
        ),
    ],
    toolsets=toolsets,
)

# 个人效率管理（待办/笔记/提醒）：统一使用 MySQL 持久化
# （初始化失败直接报错终止）
personal = create_personal_manager()

# 提醒调度唤醒事件：新增提醒时 set，让后台调度循环立即按新堆顶重算休眠时间
wake_event = asyncio.Event()


# ---------- 个人效率工具（LLM 可调用） ----------
@agent.tool_plain
def add_todo(text: str) -> str:
    """添加一条待办事项。例：'买牛奶'、'周三提交报告'"""
    t = personal.add_todo(text)
    return f"已添加待办 #{t['id']}: {t['text']}"


@agent.tool_plain
def list_todos(only_pending: bool = False) -> str:
    """查看待办事项列表。only_pending=True 只显示未完成的"""
    items = personal.list_todos(only_pending)
    if not items:
        return "当前没有待办事项"
    lines = ["待办事项："]
    for t in items:
        mark = "[x]" if t["done"] else "[ ]"
        lines.append(f"  {mark} #{t['id']} {t['text']}")
    return "\n".join(lines)


@agent.tool_plain
def complete_todo(todo_id: int) -> str:
    """把待办标记为已完成，参数为待办编号"""
    return "已标记完成" if personal.complete_todo(todo_id) else f"未找到待办 #{todo_id}"


@agent.tool_plain
def delete_todo(todo_id: int) -> str:
    """删除一条待办，参数为待办编号"""
    return "已删除" if personal.delete_todo(todo_id) else f"未找到待办 #{todo_id}"


@agent.tool_plain
def add_note(title: str, content: str) -> str:
    """保存一条笔记。例：title='会议纪要', content='周一 10 点例会，议题：预算'"""
    n = personal.add_note(title, content)
    return f"已保存笔记 #{n['id']}: {n['title']}"


@agent.tool_plain
def list_notes() -> str:
    """查看所有笔记标题和内容"""
    notes = personal.list_notes()
    if not notes:
        return "当前没有笔记"
    lines = ["笔记："]
    for n in notes:
        lines.append(f"  #{n['id']} {n['title']}: {n['content']}")
    return "\n".join(lines)


@agent.tool_plain
def delete_note(note_id: int) -> str:
    """删除一条笔记，参数为笔记编号"""
    return "已删除" if personal.delete_note(note_id) else f"未找到笔记 #{note_id}"


@agent.tool_plain
def add_reminder(text: str = "提醒", when: str = "") -> str:
    """设置一条提醒。when 支持自然语言：'15:00'、'明天 9:00'、'3点'、'下午3点'、'3点一刻'、'30分钟后'、'2026-07-31 15:00'。例：text='开会', when='15:00'
    只在缺失必要信息时才询问，其余情况直接调用本工具：
    - text（内容）：用户没给具体内容（如"提醒我1分钟后"）时，不要停下来询问，直接省略该参数（使用默认内容"提醒"），或按语境用一个简短内容代替。
    - when（时间）：优先从用户的话里解析（"1分钟后""明天9点""3点一刻"等）。只有当用户完全没给时间、也无法从语境推断（如只说"提醒我"）时，才用一句话询问希望什么时候提醒，等用户给出时间后再调用本工具；绝不猜测或编造时间，也不向用户报错。"""
    try:
        r = personal.add_reminder(text, when)
        wake_event.set()  # 立即唤醒调度循环，新提醒无需等待下一个休眠周期
    except ValueError as e:
        # 解析失败 → 返回引导指令，让 LLM 转而询问用户补充时间，而不是直接报错
        return (
            f"时间解析失败: {e}。"
            "请不要直接向用户报告这个错误，而是主动用自然语言询问用户希望设置提醒的具体时间"
            "（可提示支持 '15:00'、'明天 9:00'、'30分钟后'、'3点一刻'、'2026-07-31 15:00' 等写法），"
            "等用户给出时间后再重新调用 add_reminder。"
        )
    return f"已设置提醒 #{r['id']}: {r['text']}（{format_time(r['when'])}）"


@agent.tool_plain
def list_reminders() -> str:
    """查看所有未触发的提醒"""
    items = personal.list_reminders(only_pending=True)
    if not items:
        return "当前没有待触发的提醒"
    lines = ["提醒："]
    for r in items:
        lines.append(f"  #{r['id']} {r['text']}（{format_time(r['when'])}）")
    return "\n".join(lines)


@agent.tool_plain
def delete_reminder(reminder_id: int) -> str:
    """删除一条提醒，参数为提醒编号"""
    return "已删除" if personal.delete_reminder(reminder_id) else f"未找到提醒 #{reminder_id}"


# ---------- 对话逻辑 ----------
async def chat(agent_ctx, message: str, history=None, memory=None) -> list:  # pyright: ignore[reportMissingTypeArgument]
    """在 agent 上下文内发送消息并输出回复

    Args:
        memory: 外部记忆系统实例，启用时自动检索相似记忆并注入上下文
    """
    # 保存原始用户输入用于后续记忆判断（避免增强后消息干扰）
    raw_question = message

    # 外部记忆检索：在用户消息前注入相关历史
    if memory and memory.enabled:
        memories = memory.search(message)
        context = memory.format_context(memories)
        if context:
            message = context + message

    result = await agent_ctx.run(message, message_history=history)
    print(result.output, flush=True)

    # 存储本轮问答到记忆（用原始问题判断，不是增强后的）
    if memory and memory.enabled:
        memory.add(raw_question, result.output)

    return result.new_messages()


# ---------- CLI ----------
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

                if user_input.lower() in ("/help", "/tools"):
                    print("\n── 可用指令 ──", flush=True)
                    print("  /help      查看全部指令与能力", flush=True)
                    print("  /memory    查看记忆状态与隐私规则", flush=True)
                    print("  /todos     查看待办列表", flush=True)
                    print("  /notes     查看笔记列表", flush=True)
                    print("  /reminders 查看提醒列表", flush=True)
                    print("  /forget    清空所有长期记忆", flush=True)
                    print("  /history   查看历史会话（可带关键词）", flush=True)
                    print("  /load <ID> 加载历史会话继续对话", flush=True)
                    print("  /new       开始新会话", flush=True)
                    print("  /clear     清空当前对话", flush=True)
                    print("  /exit      退出程序（exit / quit 亦可）", flush=True)
                    print("  Ctrl+C     复制文本（请先选中）；不会退出程序", flush=True)
                    print("", flush=True)
                    print("── 已注册能力 ──", flush=True)
                    print("  • WebSearch              — 联网搜索（DuckDuckGo）", flush=True)
                    print("  • FileSystem             — 文件读写、编辑、搜索", flush=True)
                    print("  • Shell                  — 执行系统命令", flush=True)
                    print("  • Todo/Note/Reminder     — 待办、笔记、提醒（10 个工具）", flush=True)
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
                    print("      命令: /todos /notes /reminders 查看", flush=True)
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
                    if EMAIL_ENABLED:
                        print("      国内邮箱：已启用（mail_* 工具，收信/发信/回复/管理）", flush=True)
                    else:
                        print("      国内邮箱：未启用（在 .env 配置 EMAIL_ADDRESS / EMAIL_PASSWORD 授权码）", flush=True)
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


def personal_summary(personal: MySQLPersonalManager, kind: str) -> str:
    """格式化显示个人效率数据（供 /todos /notes /reminders 命令使用）"""
    if kind == "todos":
        items = personal.list_todos()
        if not items:
            return "\n待办: 无"
        lines = ["\n待办:"]
        for t in items:
            mark = "[x]" if t["done"] else "[ ]"
            lines.append(f"  {mark} #{t['id']} {t['text']}")
        return "\n".join(lines)
    if kind == "notes":
        notes = personal.list_notes()
        if not notes:
            return "\n笔记: 无"
        lines = ["\n笔记:"]
        for n in notes:
            lines.append(f"  #{n['id']} {n['title']}: {n['content']}")
        return "\n".join(lines)
    if kind == "reminders":
        items = personal.list_reminders(only_pending=True)
        if not items:
            return "\n提醒: 无"
        lines = ["\n提醒:"]
        for r in items:
            lines.append(f"  #{r['id']} {r['text']}（{format_time(r['when'])}）")
        return "\n".join(lines)
    return ""


if __name__ == "__main__":
    asyncio.run(main())
