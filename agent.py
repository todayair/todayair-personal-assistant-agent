"""
基于 pydantic-ai + Harness 的交互式 Agent 对话程序

提供命令行交互界面，支持：
- 多轮对话历史管理
- 系统提示词自定义
- Harness 能力：WebSearch、FileSystem、Shell
- 上下文压缩：TieredCompaction（分级策略：清旧工具结果 → LLM 摘要）
- DeepSeek Prompt Caching（默认启用，前缀自动缓存）
- MCP 外部工具：通过 mcp_config.json 配置

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

# MCP 配置文件加载
from pydantic_ai.mcp import load_mcp_toolsets

# Pydantic AI Harness 能力
from pydantic_ai_harness.filesystem import FileSystem
from pydantic_ai_harness.shell import Shell

# 外部记忆系统（ChromaDB 向量数据库）
from memory import get_memory
from personal import PersonalManager, format_time
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

# ---------- 创建 Agent ----------
agent = Agent( # pyright: ignore[reportCallIssue]
    model=MODEL,
    system_prompt=SYSTEM_PROMPT,
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

# 个人效率管理（待办/笔记/提醒，JSON 本地持久化）
personal = PersonalManager()


# ---------- 个人效率工具（LLM 可调用） ----------
@agent.tool  # pyright: ignore[reportArgumentType]
def add_todo(text: str) -> str:
    """添加一条待办事项。例：'买牛奶'、'周三提交报告'"""
    t = personal.add_todo(text)
    return f"已添加待办 #{t['id']}: {t['text']}"


@agent.tool  # pyright: ignore[reportArgumentType]
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


@agent.tool  # pyright: ignore[reportArgumentType]
def complete_todo(todo_id: int) -> str:
    """把待办标记为已完成，参数为待办编号"""
    return "已标记完成" if personal.complete_todo(todo_id) else f"未找到待办 #{todo_id}"


@agent.tool  # pyright: ignore[reportArgumentType]
def delete_todo(todo_id: int) -> str:
    """删除一条待办，参数为待办编号"""
    return "已删除" if personal.delete_todo(todo_id) else f"未找到待办 #{todo_id}"


@agent.tool  # pyright: ignore[reportArgumentType]
def add_note(title: str, content: str) -> str:
    """保存一条笔记。例：title='会议纪要', content='周一 10 点例会，议题：预算'"""
    n = personal.add_note(title, content)
    return f"已保存笔记 #{n['id']}: {n['title']}"


@agent.tool  # pyright: ignore[reportArgumentType]
def list_notes() -> str:
    """查看所有笔记标题和内容"""
    notes = personal.list_notes()
    if not notes:
        return "当前没有笔记"
    lines = ["笔记："]
    for n in notes:
        lines.append(f"  #{n['id']} {n['title']}: {n['content']}")
    return "\n".join(lines)


@agent.tool  # pyright: ignore[reportArgumentType]
def delete_note(note_id: int) -> str:
    """删除一条笔记，参数为笔记编号"""
    return "已删除" if personal.delete_note(note_id) else f"未找到笔记 #{note_id}"


@agent.tool  # pyright: ignore[reportArgumentType]
def add_reminder(text: str, when: str) -> str:
    """设置一条提醒。when 支持自然语言：'15:00'、'明天 9:00'、'30分钟后'、'2026-07-31 15:00'。例：text='开会', when='15:00'"""
    r = personal.add_reminder(text, when)
    return f"已设置提醒 #{r['id']}: {r['text']}（{format_time(r['when'])}）"


@agent.tool  # pyright: ignore[reportArgumentType]
def list_reminders() -> str:
    """查看所有未触发的提醒"""
    items = personal.list_reminders(only_pending=True)
    if not items:
        return "当前没有待触发的提醒"
    lines = ["提醒："]
    for r in items:
        lines.append(f"  #{r['id']} {r['text']}（{format_time(r['when'])}）")
    return "\n".join(lines)


@agent.tool  # pyright: ignore[reportArgumentType]
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
    print(f"  /tools 查看能力 | /memory 记忆 | /todos 待办 | /notes 笔记 | /reminders 提醒 | /forget 清空记忆 | /clear 清空历史 | Ctrl+C 退出")
    print("═" * 52)


async def main():
    # 初始化外部记忆系统（首次运行会下载嵌入模型 ~235MB，请耐心等待）
    print("正在初始化记忆系统（首次使用会下载模型，可能需要 1-2 分钟）...", flush=True)
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

    # 后台提醒检查任务：每秒检查一次，到点打印通知
    stop_event = asyncio.Event()

    async def reminder_loop():
        while not stop_event.is_set():
            fired = personal.check_reminders()
            for r in fired:
                print(f"\n[提醒 #{r['id']}] {r['text']}", flush=True)
            await asyncio.sleep(1)

    # 在 agent 生命周期上下文中运行整个对话，确保 MCP 连接持续可用
    async with agent:
        reminder_task = asyncio.create_task(reminder_loop())
        try:
            while True:
                try:
                    user_input = (await asyncio.to_thread(input, "\n你: ")).strip()
                except (EOFError, KeyboardInterrupt, asyncio.CancelledError):
                    print("退出中.....", flush=True)
                    print("\n[对话已结束]", flush=True)
                    break

                if not user_input:
                    continue

                if user_input.lower() == "/clear":
                    all_messages = None
                    print("\n[对话历史已清空]", flush=True)
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

                if user_input.lower() == "/tools":
                    print("\n已注册能力：", flush=True)
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
                    print("个人效率 (JSON 本地存储 .agent_personal/):", flush=True)
                    print(f"      待办: {len(personal.list_todos())} 条 | 笔记: {len(personal.list_notes())} 条 | 提醒: {len(personal.list_reminders(only_pending=True))} 条", flush=True)
                    print("      命令: /todos /notes /reminders 查看", flush=True)
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
                    print("  • MCP 外部工具集 — 从 mcp_config.json 加载：", flush=True)
                    if toolsets:
                        for ts in toolsets:
                            print(f"      └─ {ts}", flush=True)
                    continue

                print("AI: ", end="", flush=True)
                try:
                    new_msgs = await chat(agent, user_input, all_messages, memory=memory)
                    if all_messages is None:
                        all_messages = new_msgs
                    else:
                        all_messages.extend(new_msgs)
                except Exception as e:
                    print(f"\n[错误] {e}")
                    print("[提示] 请检查 API Key、模型名称和网络连接。")
        finally:
            stop_event.set()
            reminder_task.cancel()


def personal_summary(personal: PersonalManager, kind: str) -> str:
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
