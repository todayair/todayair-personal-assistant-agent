"""
Agent 核心：配置、工具集、Agent 实例与 LLM 可调用工具
======================================================

从 agent.py 拆分而来。本模块只负责创建全局共享实例：

- 配置（MODEL / SYSTEM_PROMPT / 压缩参数等）
- MCP 工具集（mcp_config.json）+ 进程内 FastMCP 邮箱工具
- 全局 agent 实例与 @agent.tool_plain 工具注册
- personal（MySQL 个人数据）与提醒调度共享状态
- personal_summary / calendar_summary 展示辅助

对话逻辑见 chat_logic.py，CLI 见 cli.py，agent.py 保留为兼容入口。
"""

import asyncio
import os
import sys

# 确保 stdout/stderr 均输出 UTF-8（Windows GBK 编码兼容；
# 否则 tqdm 进度条、中文日志写入重定向文件时会乱码）
for _stream in (sys.stdout, sys.stderr):
    try:
        if _stream.encoding and _stream.encoding.lower() != 'utf-8':
            _stream.reconfigure(encoding='utf-8')  # pyright: ignore[reportAttributeAccessIssue]
    except Exception:
        pass

from dotenv import load_dotenv
from pydantic_ai import Agent

from pydantic_ai.capabilities import WebSearch

# MCP 配置文件加载 + 进程内 FastMCP 服务（国内邮箱）
from pydantic_ai.mcp import MCPToolset, load_mcp_toolsets

# Pydantic AI Harness 能力
from pydantic_ai_harness.filesystem import FileSystem
from pydantic_ai_harness.shell import Shell
from pydantic_ai_harness.compaction import (
    ClearToolResults,
    SummarizingCompaction,
    TieredCompaction,
)

from personal import format_time
from personal_mysql import MySQLPersonalManager
from storage import create_personal_manager

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
    model_settings={'max_retries': 2, 'timeout': 180},  # pyright: ignore[reportArgumentType]
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
# 定时任务执行串行锁（避免多个到点任务并发跑 Agent）
reminder_task_lock = asyncio.Lock()


# ---------- 个人效率工具（LLM 可调用） ----------
@agent.tool_plain
def add_todo(text: str, due: str = "") -> str:
    """添加一条待办事项，可指定截止时间（会显示在日历中）。
    例：text='买牛奶'、text='周三提交报告'、due='明天18点'、due='明天'（仅日期→默认当天9:00）、due='2026-08-02 15:00'
    """
    t = personal.add_todo(text, due or None)
    due_text = format_time(t["due"]) if t.get("due") else "未设置"
    return f"已添加待办 #{t['id']}: {t['text']}（截止：{due_text}）"


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
def update_todo(todo_id: int, text: str = "", due: str = "") -> str:
    """修改一条待办的内容或截止时间（改动会同步显示在日历上）。
    例：todo_id=3, text='明天出门'；todo_id=3, due='明天9点'；todo_id=3, text='后天开会', due='后天14:00'
    只改其中一项时，另一项留空即可。"""
    if text or due:
        if not personal.update_todo(todo_id, text=text or None, due=due or None):
            return f"未找到待办 #{todo_id}"
    row = next((t for t in personal.list_todos() if t["id"] == todo_id), None)
    if row is None:
        return f"未找到待办 #{todo_id}"
    due_text = format_time(row["due"]) if row.get("due") else "未设置"
    return f"已更新待办 #{row['id']}: {row['text']}（截止：{due_text}）"


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
    """设置一条提醒。when 支持自然语言：'15:00'、'明天 9:00'、'3点'、'下午3点'、'3点一刻'、'30分钟后'、'2026-07-31 15:00'、'明天'（仅日期→当天9:00）。
    支持重复提醒：'每天9点'、'每周一14:00'、'工作日9:30'、'每月15号9点'、'每小时'。例：text='开会', when='15:00'
    只在缺失必要信息时才询问，其余情况直接调用本工具：
    - text（内容）：用户没给具体内容（如"提醒我1分钟后"）时，不要停下来询问，直接省略该参数（使用默认内容"提醒"），或按语境用一个简短内容代替。
    - when（时间）：优先从用户的话里解析（"1分钟后""明天9点""3点一刻"等）。只有当用户完全没给时间、也无法从语境推断（如只说"提醒我"）时，才用一句话询问希望什么时候提醒，等用户给出时间后再调用本工具；绝不猜测或编造时间，也不向用户报错。并且如果用户给出了时间请判断这个时间是否早于当前时间。"""
    try:
        r = personal.add_reminder(text, when)
        wake_event.set()  # 立即唤醒调度循环，新提醒无需等待下一个休眠周期
    except ValueError as e:
        if "早于当前时间" in str(e):
            # 时间在过去 → 引导 LLM 请用户改一个未来的时间
            return (
                "用户给出的提醒时间早于当前时间，不能设置。"
                "请不要向用户报告技术细节，而是用自然语言告知：提醒时间不能早于现在，"
                "并请用户重新给出一个未来的具体时间（可提示 15:00、明天 9:00、30分钟后 等写法），"
                "等用户给出时间后再重新调用 add_reminder。"
            )
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


# ---------- 展示辅助（供 CLI /help 与 /todos 等命令使用） ----------
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


def calendar_summary(personal: MySQLPersonalManager, days: int = 14) -> str:
    """按日期分组展示日程（带截止时间的待办 + 待触发提醒），供 /calendar 命令使用"""
    from datetime import datetime, timedelta

    now = datetime.now()
    cutoff = now + timedelta(days=days)
    weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

    buckets: dict[str, list[tuple[float | None, str]]] = {}

    def push(bucket: str, ts: float | None, line: str) -> None:
        buckets.setdefault(bucket, []).append((ts, line))

    def date_key(ts: float) -> str:
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")

    for t in personal.list_todos(only_pending=True):
        due = t.get("due")
        if due is None:
            push("未设置日期", None, f"[待办] #{t['id']} {t['text']}")
            continue
        ts = float(due)
        bucket = "已过期" if ts < now.timestamp() else ("更晚" if ts > cutoff.timestamp() else date_key(ts))
        push(bucket, ts, f"[待办] #{t['id']} {t['text']}（截止 {format_time(ts)}）")

    for r in personal.list_reminders(only_pending=True):
        ts = float(r["when"])
        bucket = "已过期" if ts < now.timestamp() else ("更晚" if ts > cutoff.timestamp() else date_key(ts))
        push(bucket, ts, f"[提醒] #{r['id']} {r['text']}（{format_time(ts)}）")

    if not buckets:
        return "\n日历: 未来日程为空（可让 AI 添加带截止时间的待办或提醒，如\"周三交报告\"）"

    lines = [f"\n日历（未来 {days} 天，含过期与未设置日期）:"]
    ordered_keys = [(now + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days)]
    ordered_keys += ["已过期", "更晚", "未设置日期"]
    for k in ordered_keys:
        if k not in buckets:
            continue
        if k == "已过期":
            lines.append("  已过期:")
        elif k == "更晚":
            lines.append(f"  {days} 天以后:")
        elif k == "未设置日期":
            lines.append("  未设置日期:")
        else:
            dt = datetime.strptime(k, "%Y-%m-%d")
            if dt.date() == now.date():
                label = "今天"
            elif dt.date() == (now + timedelta(days=1)).date():
                label = "明天"
            else:
                label = f"{dt.month}月{dt.day}日（{weekday_names[dt.weekday()]}）"
            lines.append(f"  {label} {k}:")
        for ts, item in sorted(buckets[k], key=lambda x: (x[0] is None, x[0] or 0)):
            lines.append(f"    {item}")
    return "\n".join(lines)
