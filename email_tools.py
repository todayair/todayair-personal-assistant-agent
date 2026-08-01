# -*- coding: utf-8 -*-
"""国内邮箱工具集（IMAP/SMTP + 授权码），支持 QQ / 163 / 126 / Outlook 及自定义服务器。

以进程内 FastMCP 服务形式提供 mail_* 工具，由 agent.py 挂载：
    toolsets = [*toolsets, MCPToolset(email_server).prefixed('mail_')]

配置（.env）：
    EMAIL_ADDRESS           邮箱地址（必填）
    EMAIL_PASSWORD          授权码，不是登录密码（必填，需在邮箱网页端开启 IMAP/SMTP 后生成）
    EMAIL_PROVIDER          qq | 163 | 126 | outlook | custom（默认 qq）
    EMAIL_USERNAME          登录用户名，默认同 EMAIL_ADDRESS
    EMAIL_IMAP_HOST / EMAIL_IMAP_PORT     自定义 IMAP 服务器（provider=custom 时必填）
    EMAIL_SMTP_HOST / EMAIL_SMTP_PORT     自定义 SMTP 服务器（provider=custom 时必填）
    EMAIL_SMTP_STARTTLS     true/false，默认按预设（465 端口走 SSL，587 端口走 STARTTLS）
    EMAIL_IMAP_MODE          ssl | starttls | plain（默认按端口：993=ssl，其他=starttls）
    EMAIL_ATTACHMENT_DIR    附件保存目录，默认 .agent_email_attachments

说明：
- 163 邮箱需要额外发送 IMAP ID 命令，本模块已自动处理（避免“不安全登录”报错）
- 预设服务器（imap.qq.com / imap.163.com / imap.126.com / imap-mail.outlook.com）均国内可直连
- 邮件正文过长会自动截断，避免撑爆模型上下文
"""

import mimetypes
import os
import smtplib
import ssl
from datetime import date
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from pathlib import Path

from dotenv import load_dotenv
from fastmcp import FastMCP
try:  # 兼容旧版本命名（MailBoxTls）
    from imap_tools import MailBoxStartTls as _MailBoxStartTls
except ImportError:
    from imap_tools import MailBoxTls as _MailBoxStartTls
from imap_tools import A, MailBox, MailBoxUnencrypted

load_dotenv()

# ---------- 配置 ----------

PROVIDER_PRESETS = {
    "qq": {
        "imap_host": "imap.qq.com", "imap_port": 993,
        "smtp_host": "smtp.qq.com", "smtp_port": 465, "smtp_starttls": False,
    },
    "163": {
        "imap_host": "imap.163.com", "imap_port": 993,
        "smtp_host": "smtp.163.com", "smtp_port": 465, "smtp_starttls": False,
    },
    "126": {
        "imap_host": "imap.126.com", "imap_port": 993,
        "smtp_host": "smtp.126.com", "smtp_port": 465, "smtp_starttls": False,
    },
    "outlook": {
        "imap_host": "imap-mail.outlook.com", "imap_port": 993,
        "smtp_host": "smtp-mail.outlook.com", "smtp_port": 587, "smtp_starttls": True,
    },
}

TRASH_FOLDER_CANDIDATES = ["已删除", "Deleted Items", "Trash", "Deleted Messages", "Deleted"]
BODY_CLIP = 30000
SNIPPET_LEN = 300


def _provider_config() -> dict:
    """读取并合并邮箱服务器配置（预设 + .env 覆盖）"""
    provider = os.getenv("EMAIL_PROVIDER", "qq").strip().lower()
    preset = PROVIDER_PRESETS.get(provider)
    if preset is None:
        raise ValueError(
            f"不支持的 EMAIL_PROVIDER: {provider}，可选 qq / 163 / 126 / outlook / custom"
        )

    def _int(name: str, default: int) -> int:
        raw = os.getenv(name)
        return int(raw) if raw else default

    def _bool(name: str, default: bool) -> bool:
        raw = os.getenv(name)
        return raw.strip().lower() in ("1", "true", "yes", "on") if raw else default

    if provider == "custom" and (not os.getenv("EMAIL_IMAP_HOST") or not os.getenv("EMAIL_SMTP_HOST")):
        raise ValueError("EMAIL_PROVIDER=custom 时必须配置 EMAIL_IMAP_HOST 和 EMAIL_SMTP_HOST")

    return {
        "provider": provider,
        "imap_host": os.getenv("EMAIL_IMAP_HOST") or preset["imap_host"],
        "imap_port": _int("EMAIL_IMAP_PORT", preset["imap_port"]),
        "smtp_host": os.getenv("EMAIL_SMTP_HOST") or preset["smtp_host"],
        "smtp_port": _int("EMAIL_SMTP_PORT", preset["smtp_port"]),
        "smtp_starttls": _bool("EMAIL_SMTP_STARTTLS", preset["smtp_starttls"]),
    }


def _credentials() -> tuple[str, str, str]:
    """返回 (邮箱地址, IMAP/SMTP 用户名, 授权码)"""
    address = os.getenv("EMAIL_ADDRESS", "").strip()
    password = os.getenv("EMAIL_PASSWORD", "").strip()
    if not address or not password:
        raise ValueError("未配置邮箱：请在 .env 中填写 EMAIL_ADDRESS 与 EMAIL_PASSWORD（授权码）")
    username = os.getenv("EMAIL_USERNAME", "").strip() or address
    return address, username, password


def _attachment_dir() -> Path:
    path = Path(os.getenv("EMAIL_ATTACHMENT_DIR", ".agent_email_attachments"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def _clip(text: str | None, limit: int = BODY_CLIP) -> str:
    if not text:
        return ""
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n……（正文过长，已截断至前 {limit} 字符）"


def _open_mailbox():
    """建立 IMAP 连接并返回登录上下文（配合 with 使用）"""
    cfg = _provider_config()
    address, username, password = _credentials()
    mode = (os.getenv("EMAIL_IMAP_MODE") or "").strip().lower() or ("ssl" if cfg["imap_port"] == 993 else "starttls")
    try:
        if mode == "plain":
            box = MailBoxUnencrypted(cfg["imap_host"], cfg["imap_port"], timeout=30)
        elif mode == "starttls":
            box = _MailBoxStartTls(cfg["imap_host"], cfg["imap_port"], timeout=30)
        else:
            box = MailBox(cfg["imap_host"], cfg["imap_port"], timeout=30)
        context = box.login(username, password)
    except Exception as exc:
        raise RuntimeError(
            f"IMAP 连接/登录失败（{cfg['imap_host']}:{cfg['imap_port']}）：{exc}"
        ) from exc
    # 163 邮箱需发送 IMAP ID 命令，否则会报“不安全登录”
    try:
        context.client._simple_command("ID", '("name" "PersonalAssistant" "version" "1.0.0")')
    except Exception:
        pass
    return context


def _set_folder(mailbox, folder: str) -> None:
    try:
        mailbox.folder.set(folder)
    except Exception as exc:
        raise ValueError(
            f"文件夹不存在或无法访问：{folder}（可用 mail_list_folders 查看可用文件夹）"
        ) from exc


def _find_trash_folder(mailbox) -> str | None:
    names = {f.name for f in mailbox.folder.list()}
    for candidate in TRASH_FOLDER_CANDIDATES:
        if candidate in names:
            return candidate
    return None


def _addr_list(value: str | list[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return [item.strip() for item in value if item and item.strip()]


def _attach_file(msg: EmailMessage, path: str) -> None:
    file_path = Path(path)
    if not file_path.is_file():
        raise ValueError(f"附件文件不存在：{path}")
    mime = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    maintype, subtype = mime.split("/", 1)
    with file_path.open("rb") as fh:
        msg.add_attachment(fh.read(), maintype=maintype, subtype=subtype, filename=file_path.name)


def _summary(msg) -> dict:
    text = msg.text or msg.html or ""
    return {
        "id": msg.uid,
        "date": msg.date.isoformat() if msg.date else None,
        "from": msg.from_,
        "to": msg.to,
        "subject": msg.subject or "",
        "unread": "\\Seen" not in msg.flags,
        "has_attachments": bool(msg.attachments),
        "snippet": _clip(text, SNIPPET_LEN),
    }


def _smtp_send(msg: EmailMessage, recipients: list[str]) -> str:
    cfg = _provider_config()
    address, username, password = _credentials()
    try:
        if cfg["smtp_starttls"]:
            with smtplib.SMTP(cfg["smtp_host"], cfg["smtp_port"], timeout=30) as smtp:
                smtp.ehlo()
                smtp.starttls(context=ssl.create_default_context())
                smtp.ehlo()
                smtp.login(username, password)
                smtp.send_message(msg, to_addrs=recipients)
        else:
            with smtplib.SMTP_SSL(
                cfg["smtp_host"], cfg["smtp_port"], timeout=30, context=ssl.create_default_context()
            ) as smtp:
                smtp.login(username, password)
                smtp.send_message(msg, to_addrs=recipients)
    except Exception as exc:
        raise RuntimeError(
            f"SMTP 发送失败（{cfg['smtp_host']}:{cfg['smtp_port']}）：{exc}"
        ) from exc
    return str(msg["Message-ID"])


# ---------- FastMCP 服务（挂载后工具名为 mail_*） ----------

server = FastMCP("Personal Assistant 国内邮箱")


@server.tool()
def list_folders() -> dict:
    """列出邮箱的全部文件夹（收件箱、已发送、草稿、垃圾邮件、自定义文件夹等）"""
    with _open_mailbox() as mailbox:
        folders = [f.name for f in mailbox.folder.list()]
    return {"folders": folders}


@server.tool()
def search_emails(
    folder: str = "INBOX",
    keyword: str | None = None,
    sender: str | None = None,
    since: str | None = None,
    unread_only: bool = False,
    limit: int = 10,
) -> dict:
    """搜索邮件并返回摘要列表。

    folder: 文件夹名（默认 INBOX，可用 mail_list_folders 查看）
    keyword: 关键词，匹配主题和正文
    sender: 发件人地址/名称关键字
    since: 起始日期，格式 YYYY-MM-DD
    unread_only: 只看未读邮件
    limit: 最多返回条数（默认 10，最大 50）
    """
    if limit > 50:
        limit = 50
    since_date = None
    if since:
        try:
            since_date = date.fromisoformat(since)
        except ValueError as exc:
            raise ValueError(f"since 必须是 YYYY-MM-DD 格式，收到：{since}") from exc
    criteria_kwargs = {}
    if keyword:
        criteria_kwargs["text"] = keyword
    if sender:
        criteria_kwargs["from_"] = sender
    if since_date:
        criteria_kwargs["date_gte"] = since_date
    if unread_only:
        criteria_kwargs["seen"] = False
    criteria = A(**criteria_kwargs) if criteria_kwargs else A(all=True)

    with _open_mailbox() as mailbox:
        _set_folder(mailbox, folder)
        messages = [
            _summary(m)
            for m in mailbox.fetch(criteria, reverse=True, limit=limit, mark_seen=False)
        ]
    return {"folder": folder, "count": len(messages), "messages": messages}


@server.tool()
def read_email(folder: str, id: str, mark_read: bool = True) -> dict:
    """读取一封邮件的完整内容（正文、附件）。

    folder: 所在文件夹；id: 邮件 ID（来自 mail_search_emails 的 id 字段）
    mark_read: 是否将邮件标记为已读（默认 true）
    附件会保存到 EMAIL_ATTACHMENT_DIR（默认 .agent_email_attachments），返回本地路径。
    """
    with _open_mailbox() as mailbox:
        _set_folder(mailbox, folder)
        messages = list(mailbox.fetch(A(uid=str(id)), mark_seen=mark_read))
    if not messages:
        raise ValueError(f"未找到邮件：folder={folder}, id={id}")
    msg = messages[0]
    attachments = []
    for att in msg.attachments:
        if att.filename and att.payload is not None:
            path = _attachment_dir() / att.filename
            path.write_bytes(att.payload)
            attachments.append({"filename": att.filename, "path": str(path), "size": len(att.payload)})
    headers = msg.headers or {}
    return {
        "id": msg.uid,
        "date": msg.date.isoformat() if msg.date else None,
        "from": msg.from_,
        "to": msg.to,
        "cc": msg.cc,
        "subject": msg.subject or "",
        "message_id": str(headers.get("Message-ID", "") or ""),
        "text": _clip(msg.text or ""),
        "html": _clip(msg.html or ""),
        "attachments": attachments,
    }


@server.tool()
def send_email(
    to: str | list[str],
    subject: str,
    body: str,
    cc: str | list[str] | None = None,
    bcc: str | list[str] | None = None,
    html: str | None = None,
    attachments: list[str] | None = None,
) -> dict:
    """发送一封邮件。

    to: 收件人，可以是 "a@x.com"、"a@x.com,b@x.com" 或地址列表
    subject: 主题；body: 纯文本正文
    cc/bcc: 抄送/密送（密送不会出现在收件人可见的头部）
    html: 可选 HTML 正文（与 body 同时提供时使用 multipart/alternative）
    attachments: 附件文件绝对路径列表（本地文件，可用文件系统工具先创建）
    """
    if not _addr_list(to):
        raise ValueError("收件人 to 不能为空")
    address = _credentials()[0]
    msg = EmailMessage()
    msg["From"] = formataddr((os.getenv("EMAIL_FROM_NAME", "Personal Assistant"), address))
    msg["To"] = ", ".join(_addr_list(to))
    if cc:
        msg["Cc"] = ", ".join(_addr_list(cc))
    msg["Subject"] = subject
    msg.set_content(body)
    if html:
        msg.add_alternative(html, subtype="html")
    for path in attachments or []:
        _attach_file(msg, path)
    msg["Message-ID"] = make_msgid(domain=address.split("@")[-1])
    recipients = _addr_list(to) + _addr_list(cc) + _addr_list(bcc)
    message_id = _smtp_send(msg, recipients)
    return {
        "success": True,
        "to": msg["To"],
        "cc": msg.get("Cc", ""),
        "subject": subject,
        "message_id": message_id,
    }


@server.tool()
def reply_email(
    folder: str,
    id: str,
    body: str | None = None,
    html: str | None = None,
    attachments: list[str] | None = None,
) -> dict:
    """回复一封邮件（自动带上 Re: 主题与原始邮件引用）。

    folder: 原邮件所在文件夹；id: 原邮件 ID
    body: 回复正文；不填则自动引用原邮件正文
    """
    with _open_mailbox() as mailbox:
        _set_folder(mailbox, folder)
        messages = list(mailbox.fetch(A(uid=str(id)), mark_seen=False))
    if not messages:
        raise ValueError(f"未找到邮件：folder={folder}, id={id}")
    original = messages[0]
    headers = original.headers or {}
    original_id = str(headers.get("Message-ID", "") or "")
    subject = original.subject or ""
    if not subject.lower().startswith("re:"):
        subject = "Re: " + subject
    if body is None:
        quote = _clip(original.text or original.html or "", 5000)
        body = "\n\n" + "\n".join("> " + line for line in quote.splitlines()) if quote else ""

    address = _credentials()[0]
    msg = EmailMessage()
    msg["From"] = formataddr((os.getenv("EMAIL_FROM_NAME", "Personal Assistant"), address))
    msg["To"] = original.from_
    msg["Subject"] = subject
    if original_id:
        msg["In-Reply-To"] = original_id
        msg["References"] = original_id
    msg.set_content(body)
    if html:
        msg.add_alternative(html, subtype="html")
    for path in attachments or []:
        _attach_file(msg, path)
    msg["Message-ID"] = make_msgid(domain=address.split("@")[-1])
    message_id = _smtp_send(msg, [msg["To"]])
    return {"success": True, "to": msg["To"], "subject": subject, "message_id": message_id}


@server.tool()
def mark_read(folder: str, id: str, read: bool = True) -> dict:
    """将邮件标记为已读或未读。"""
    with _open_mailbox() as mailbox:
        _set_folder(mailbox, folder)
        messages = list(mailbox.fetch(A(uid=str(id)), mark_seen=False))
        if not messages:
            raise ValueError(f"未找到邮件：folder={folder}, id={id}")
        mailbox.flag(messages, "\\Seen", read)
    return {"success": True, "folder": folder, "id": id, "read": read}


@server.tool()
def move_email(folder: str, id: str, target_folder: str) -> dict:
    """把邮件移动到另一个文件夹（如归档、自定义文件夹）。"""
    with _open_mailbox() as mailbox:
        _set_folder(mailbox, folder)
        messages = list(mailbox.fetch(A(uid=str(id)), mark_seen=False))
        if not messages:
            raise ValueError(f"未找到邮件：folder={folder}, id={id}")
        try:
            mailbox.move(messages, target_folder)
        except Exception as exc:
            raise ValueError(f"移动失败，请确认目标文件夹存在：{target_folder}（{exc}）") from exc
    return {"success": True, "folder": folder, "id": id, "target_folder": target_folder}


@server.tool()
def delete_email(folder: str, id: str, permanent: bool = False) -> dict:
    """删除一封邮件。

    permanent=false（默认）：优先移入回收站文件夹，找不到回收站才直接删除
    permanent=true：直接永久删除（不可恢复，请谨慎）
    """
    with _open_mailbox() as mailbox:
        _set_folder(mailbox, folder)
        messages = list(mailbox.fetch(A(uid=str(id)), mark_seen=False))
        if not messages:
            raise ValueError(f"未找到邮件：folder={folder}, id={id}")
        if permanent:
            mailbox.delete(messages)
            return {"success": True, "folder": folder, "id": id, "permanent": True}
        trash = _find_trash_folder(mailbox)
        if trash:
            mailbox.move(messages, trash)
            return {"success": True, "folder": folder, "id": id, "permanent": False, "moved_to": trash}
        mailbox.delete(messages)
        return {
            "success": True,
            "folder": folder,
            "id": id,
            "permanent": True,
            "note": "未找到回收站文件夹，已直接删除",
        }