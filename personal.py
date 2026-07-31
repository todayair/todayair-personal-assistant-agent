"""
个人效率工具：待办事项、笔记、提醒

- 待办 / 笔记 / 提醒均以 JSON 持久化到本地目录（默认 .agent_personal/）
- 提醒支持自然语言时间解析：15:00、明天 9:00、30分钟后、2026-07-31 15:00
- check_reminders() 由主程序后台循环调用，到点返回已触发的提醒
"""

import json
import os
import re
import time
from datetime import datetime, timedelta
from typing import Any

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".agent_personal")

# 单条记录（待办/笔记/提醒）的统一类型：str -> Any 的字典
Item = dict[str, Any]


def _load(path: str) -> list[Item]:
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError):
            return []
    return []


def _save(path: str, data: list[Item]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _next_id(items: list[Item]) -> int:
    return max((i.get("id", 0) for i in items), default=0) + 1


def parse_time(s: str) -> float:
    """解析自然语言时间为时间戳（秒）。

    支持的格式：
    - 15:00                    → 今天 15:00（已过则明天）
    - 明天 9:00 / 后天 8:30    → 相对日期 + 时间
    - 30秒后 / 30分钟后 / 2小时后 / 3天后
    - 2026-07-31 15:00
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

    # YYYY-MM-DD HH:MM
    m = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})\s+(\d{1,2}):(\d{2})", s)
    if m:
        y, mo, d, h, mi = map(int, m.groups())
        return datetime(y, mo, d, h, mi).timestamp()

    # 裸 HH:MM → 今天
    m = re.match(r"^(\d{1,2}):(\d{2})$", s)
    if m:
        dt = now.replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0)
        if dt.timestamp() < now.timestamp():
            dt += timedelta(days=1)
        return dt.timestamp()

    raise ValueError(
        f"无法解析时间: {s!r}，请用 '15:00'、'明天 9:00'、'30分钟后'、'2026-07-31 15:00' 等格式"
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


class PersonalManager:
    """待办 / 笔记 / 提醒 的统一管理器（JSON 本地持久化）"""

    def __init__(self, data_dir: str = DATA_DIR):
        os.makedirs(data_dir, exist_ok=True)
        self.todos_file = os.path.join(data_dir, "todos.json")
        self.notes_file = os.path.join(data_dir, "notes.json")
        self.reminders_file = os.path.join(data_dir, "reminders.json")
        self.todos = _load(self.todos_file)
        self.notes = _load(self.notes_file)
        self.reminders = _load(self.reminders_file)

    # ---------- 待办 ----------
    def add_todo(self, text: str) -> Item:
        todo = {
            "id": _next_id(self.todos),
            "text": text,
            "done": False,
            "created_at": time.time(),
        }
        self.todos.append(todo)
        _save(self.todos_file, self.todos)
        return todo

    def list_todos(self, only_pending: bool = False) -> list[Item]:
        items = [t for t in self.todos if not t["done"]] if only_pending else self.todos
        return sorted(items, key=lambda t: (t["done"], -t["created_at"]))

    def complete_todo(self, todo_id: int) -> bool:
        for t in self.todos:
            if t["id"] == todo_id:
                t["done"] = True
                _save(self.todos_file, self.todos)
                return True
        return False

    def delete_todo(self, todo_id: int) -> bool:
        for i, t in enumerate(self.todos):
            if t["id"] == todo_id:
                self.todos.pop(i)
                _save(self.todos_file, self.todos)
                return True
        return False

    # ---------- 笔记 ----------
    def add_note(self, title: str, content: str) -> Item:
        note = {
            "id": _next_id(self.notes),
            "title": title,
            "content": content,
            "created_at": time.time(),
        }
        self.notes.append(note)
        _save(self.notes_file, self.notes)
        return note

    def list_notes(self) -> list[Item]:
        return sorted(self.notes, key=lambda n: -n["created_at"])

    def delete_note(self, note_id: int) -> bool:
        for i, n in enumerate(self.notes):
            if n["id"] == note_id:
                self.notes.pop(i)
                _save(self.notes_file, self.notes)
                return True
        return False

    # ---------- 提醒 ----------
    def add_reminder(self, text: str, when: str) -> Item:
        ts = parse_time(when)
        reminder = {
            "id": _next_id(self.reminders),
            "text": text,
            "when": ts,
            "done": False,
            "created_at": time.time(),
        }
        self.reminders.append(reminder)
        _save(self.reminders_file, self.reminders)
        return reminder

    def list_reminders(self, only_pending: bool = False) -> list[Item]:
        items = [r for r in self.reminders if not r["done"]] if only_pending else self.reminders
        return sorted(items, key=lambda r: r["when"])

    def delete_reminder(self, reminder_id: int) -> bool:
        for i, r in enumerate(self.reminders):
            if r["id"] == reminder_id:
                self.reminders.pop(i)
                _save(self.reminders_file, self.reminders)
                return True
        return False

    def check_reminders(self) -> list[Item]:
        """返回所有已到时间且未通知的提醒，并标记为已通知"""
        now = time.time()
        fired = [r for r in self.reminders if not r["done"] and r["when"] <= now]
        if fired:
            for r in fired:
                r["done"] = True
            _save(self.reminders_file, self.reminders)
        return fired
