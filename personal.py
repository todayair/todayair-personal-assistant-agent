"""
个人效率工具：纯函数与共享数据（供 personal_mysql 复用）

本模块为纯函数与共享数据（待办 / 笔记 / 提醒统一存 MySQL，
见 personal_mysql.py）。这里只保留：

- parse_time / format_time：自然语言时间解析与格式化纯函数
- format_fired_reminder：提醒通知文本格式化
- Item / DATA_DIR / load_items：MySQL 后端做旧版 .agent_personal/ 存量
  数据一次性迁移时复用的类型与读取函数
"""

import json
import os
import re
from datetime import datetime, timedelta
from typing import Any

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".agent_personal")

# 单条记录（待办/笔记/提醒）的统一类型：str -> Any 的字典
Item = dict[str, Any]
def load_items(path: str) -> list[Item]:
    """读取旧版数据文件（仅供 MySQL 后端一次性迁移使用）"""
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError):
            return []
    return []



def parse_time(s: str) -> float:
    """解析自然语言时间为时间戳（秒）。

    支持的格式：
    - 15:00                    → 今天 15:00（已过则明天）
    - 明天 9:00 / 后天 8:30    → 相对日期 + 时间
    - 3点 / 3点半 / 下午3点 / 明天9点  → 几点风格（已过则明天）
    - 3点一刻 / 3点三刻 / 3点1刻       → 刻钟（1刻=15分，四刻自动进位整点）
    - 30秒后 / 30分钟后 / 2小时后 / 3天后
    - 2026-07-31 15:00
    - 明天 / 2026-08-02（仅日期）→ 默认当天 09:00
    """
    s = s.strip()
    now = datetime.now()

    # N秒后 / N分钟后 / N小时后 / N天后
    m = re.match(r"(\d+)\s*(秒|分钟|小时|天)(后)?$", s)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        delta = {
            "秒": timedelta(seconds=n),
            "分钟": timedelta(minutes=n),
            "小时": timedelta(hours=n),
            "天": timedelta(days=n),
        }[unit]
        return (now + delta).timestamp()

    # 今天/明天/后天/大后天 HH:MM
    m = re.match(r"(今天|明天|后天|大后天)\s*(\d{1,2}):(\d{2})", s)
    if m:
        offset = {"今天": 0, "明天": 1, "后天": 2, "大后天": 3}[m.group(1)]
        dt = (now + timedelta(days=offset)).replace(
            hour=int(m.group(2)), minute=int(m.group(3)), second=0, microsecond=0
        )
        return dt.timestamp()

    # 今天/明天/后天/大后天（仅日期）→ 默认当天 09:00
    m = re.match(r"^(今天|明天|后天|大后天)$", s)
    if m:
        offset = {"今天": 0, "明天": 1, "后天": 2, "大后天": 3}[m.group(1)]
        dt = (now + timedelta(days=offset)).replace(
            hour=9, minute=0, second=0, microsecond=0
        )
        return dt.timestamp()

    # YYYY-MM-DD HH:MM
    m = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})\s+(\d{1,2}):(\d{2})", s)
    if m:
        y, mo, d, h, mi = map(int, m.groups())
        return datetime(y, mo, d, h, mi).timestamp()

    # YYYY-MM-DD（仅日期）→ 默认当天 09:00
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", s)
    if m:
        y, mo, d = map(int, m.groups())
        return datetime(y, mo, d, 9, 0).timestamp()

    # 裸 HH:MM → 今天
    m = re.match(r"^(\d{1,2}):(\d{2})$", s)
    if m:
        dt = now.replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0)
        if dt.timestamp() < now.timestamp():
            dt += timedelta(days=1)
        return dt.timestamp()

    # X点 / X点半 / X点N刻（可带 上午/下午/晚上/凌晨/中午 修饰词，可带 今天/明天/后天/大后天 日期词）
    m = re.match(
        r"^(今天|明天|后天|大后天)?\s*(凌晨|上午|中午|下午|晚上)?\s*(\d{1,2})点(半|一刻|两刻|二刻|三刻|四刻|[1-4]刻)?$",
        s,
    )
    if m:
        day_word, mod, h, tail = m.groups()
        offset = {"今天": 0, "明天": 1, "后天": 2, "大后天": 3}.get(day_word, 0)
        hour = int(h)
        if mod in ("下午", "晚上"):
            hour = hour % 12 + 12  # 下午3点=15点，晚上8点=20点，晚上12点=12点
        if hour > 23:
            raise ValueError(f"无法解析时间: {s!r}，小时超出范围")
        # 刻钟换算：1刻=15分钟，四刻=60分钟（自动进位到下一整点）
        minute = {
            "半": 30,
            "一刻": 15, "两刻": 30, "二刻": 30, "三刻": 45, "四刻": 60,
            "1刻": 15, "2刻": 30, "3刻": 45, "4刻": 60,
        }.get(tail, 0)
        # 从整点基准加分钟，minute=60 时自动进位且跨天也正确
        base = (now + timedelta(days=offset)).replace(
            hour=hour, minute=0, second=0, microsecond=0
        )
        dt = base + timedelta(minutes=minute)
        if offset == 0 and dt.timestamp() < now.timestamp():
            dt += timedelta(days=1)  # 今天已过该点 → 自动推到明天
        return dt.timestamp()

    raise ValueError(
        f"无法解析时间: {s!r}，请用 '15:00'、'明天 9:00'、'30分钟后'、'3点'、'下午3点'、'3点一刻'、'2026-07-31 15:00' 等格式"
    )


def extract_time(s: str) -> tuple[str, float | None]:
    """从自然语言句子中提取时间表达式，返回 (去掉时间后的文本, 时间戳或None)。

    例如：
    - "明天出门"           → ("出门", 明天 09:00)
    - "明天9点开会"        → ("开会", 明天 09:00)
    - "2026-08-02 交报告"  → ("交报告", 2026-08-02 09:00)
    - "下午3点开会"        → ("开会", 今天 15:00)
    - "30分钟后出门"       → ("出门", 30分钟后)
    - "出门"               → ("出门", None)
    无法提取时返回 (原文本, None)，不抛异常。
    """
    text = s.strip()
    if not text:
        return text, None
    now = datetime.now()
    day_map = {"今天": 0, "明天": 1, "后天": 2, "大后天": 3}

    def cut(m: re.Match) -> str:
        rest = (text[: m.start()] + " " + text[m.end() :]).strip()
        if rest.startswith("的"):
            rest = rest[1:].strip()
        return rest or text

    # 今天/明天/后天/大后天 + HH:MM
    m = re.search(r"(今天|明天|后天|大后天)\s*(\d{1,2}):(\d{2})", text)
    if m:
        dt = (now + timedelta(days=day_map[m.group(1)])).replace(
            hour=int(m.group(2)), minute=int(m.group(3)), second=0, microsecond=0
        )
        return cut(m), dt.timestamp()

    # [今天/明天/后天/大后天] [凌晨/早上/上午/中午/下午/晚上] X点[半/刻]
    m = re.search(
        r"(今天|明天|后天|大后天)?\s*(凌晨|早上|上午|中午|下午|晚上)?\s*(\d{1,2})点(半|一刻|两刻|二刻|三刻|四刻|[1-4]刻)?",
        text,
    )
    if m:
        day_word, mod, h, tail = m.groups()
        hour = int(h)
        if mod in ("下午", "晚上"):
            hour = hour % 12 + 12
        if hour <= 23:
            offset = day_map.get(day_word, 0)
            minute = {
                "半": 30,
                "一刻": 15, "两刻": 30, "二刻": 30, "三刻": 45, "四刻": 60,
                "1刻": 15, "2刻": 30, "3刻": 45, "4刻": 60,
            }.get(tail, 0)
            base = (now + timedelta(days=offset)).replace(
                hour=hour, minute=0, second=0, microsecond=0
            )
            dt = base + timedelta(minutes=minute)
            if offset == 0 and dt.timestamp() < now.timestamp():
                dt += timedelta(days=1)
            return cut(m), dt.timestamp()

    # 今天/明天/后天/大后天（仅日期）→ 默认当天 09:00
    m = re.search(r"(今天|明天|后天|大后天)", text)
    if m:
        dt = (now + timedelta(days=day_map[m.group(1)])).replace(
            hour=9, minute=0, second=0, microsecond=0
        )
        return cut(m), dt.timestamp()

    # YYYY-MM-DD HH:MM
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})\s+(\d{1,2}):(\d{2})", text)
    if m:
        y, mo, d, h, mi = map(int, m.groups())
        return cut(m), datetime(y, mo, d, h, mi).timestamp()

    # YYYY-MM-DD（仅日期）→ 默认当天 09:00
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", text)
    if m:
        y, mo, d = map(int, m.groups())
        return cut(m), datetime(y, mo, d, 9, 0).timestamp()

    # N秒后 / N分钟后 / N小时后 / N天后
    m = re.search(r"(\d+)\s*(秒|分钟|小时|天)后", text)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        delta = {
            "秒": timedelta(seconds=n),
            "分钟": timedelta(minutes=n),
            "小时": timedelta(hours=n),
            "天": timedelta(days=n),
        }[unit]
        return cut(m), (now + delta).timestamp()

    # 裸 HH:MM → 今天（已过则明天）
    m = re.search(r"(?<!\d)(\d{1,2}):(\d{2})(?!\d)", text)
    if m:
        dt = now.replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0)
        if dt.timestamp() < now.timestamp():
            dt += timedelta(days=1)
        return cut(m), dt.timestamp()

    return text, None


def format_fired_reminder(r: Item) -> str:
    """将一条已触发的提醒格式化为多行可读文本（CLI 打印 / UI 展示通用）"""
    return "\n".join(
        [
            f"提醒时间到！[#{r['id']}] {r['text']}",
            f"  内容：{r['text']}",
            f"  预定时间：{format_time(r['when'])}",
            f"  按回车键(Enter)继续",
        ]
    )


def format_time(ts: float) -> str:
    """把时间戳格式化为人类可读的本地时间"""
    dt = datetime.fromtimestamp(ts)
    now = datetime.now()
    if dt.date() == now.date():
        return f"今天 {dt:%H:%M}"
    if dt.date() == (now + timedelta(days=1)).date():
        return f"明天 {dt:%H:%M}"
    return dt.strftime("%m-%d %H:%M")



