"""国内邮箱路由：/api/mail（IMAP/SMTP 直连，QQ/163/126/Outlook；未配置 .env 时返回 400）"""

import os
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from web_state import logger

router = APIRouter(prefix="/api/mail", tags=["mail"])

# ---------- 邮箱模块导入（依赖缺失时仅关闭邮箱端点，不影响其余功能） ----------
try:
    from email_tools import (
        delete_email as _mail_delete,
        list_folders as _mail_list_folders,
        mark_read as _mail_mark_read,
        move_email as _mail_move,
        read_email as _mail_read,
        reply_email as _mail_reply,
        search_emails as _mail_search,
        send_email as _mail_send,
    )
except Exception as _mail_import_exc:  # noqa: BLE001
    _mail_import_failed = True
    _mail_import_error = str(_mail_import_exc)
else:
    _mail_import_failed = False
    _mail_import_error = ""


def _email_enabled() -> bool:
    """动态判断邮箱是否已配置（页面保存配置后立即生效，无需重启）"""
    if _mail_import_failed:
        return False
    return bool(os.getenv("EMAIL_ADDRESS") and os.getenv("EMAIL_PASSWORD"))


def _save_mail_env(provider: str, address: str, password: str, username: str = "") -> None:
    """把邮箱配置写入项目根目录 .env（替换已有行或追加），供下次启动继续生效"""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(env_path):
        with open(env_path, "w", encoding="utf-8") as fh:
            fh.write("")
    with open(env_path, "r", encoding="utf-8-sig") as fh:
        lines = fh.read().splitlines()
    updates = {
        "EMAIL_PROVIDER": provider,
        "EMAIL_ADDRESS": address,
        "EMAIL_PASSWORD": password,
    }
    if username:
        updates["EMAIL_USERNAME"] = username
    written: set[str] = set()
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        key = None
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
        if key in updates:
            out.append(f"{key}={updates[key]}")
            written.add(key)
        else:
            out.append(line)
    for key, value in updates.items():
        if key not in written:
            out.append(f"{key}={value}")
    with open(env_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")


def _remove_mail_env(keys: list[str]) -> None:
    """从 .env 移除指定键（退出邮箱时清除配置）"""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, "r", encoding="utf-8-sig") as fh:
        lines = fh.read().splitlines()
    removed: set[str] = set()
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        key = None
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
        if key in keys:
            removed.add(key)
            continue
        out.append(line)
    if not removed:
        return
    with open(env_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")


def _require_email() -> None:
    if _mail_import_failed:
        raise HTTPException(503, f"邮箱模块不可用：{_mail_import_error}（请先 pip install -r requirements.txt）")
    if not _email_enabled():
        raise HTTPException(400, "国内邮箱未启用：请先在邮箱页面填写账户与授权码，或在 .env 中配置")


def _mail_call(fn, *args, **kwargs) -> dict[str, Any]:
    """同步调用邮箱工具（IMAP/SMTP 网络 IO），统一把异常转成 HTTP 错误。"""
    try:
        result = fn(*args, **kwargs)
        if isinstance(result, dict):
            return result
        return {"success": True, "result": result}
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except RuntimeError as e:
        raise HTTPException(502, str(e)) from e
    except Exception as e:  # noqa: BLE001
        logger.error("邮箱操作失败: %s", e)
        raise HTTPException(500, f"邮箱操作失败：{e}") from e


@router.get("/status")
def mail_status() -> dict[str, Any]:
    """邮箱启用状态与当前账户（前端用来决定是否展示配置引导）"""
    return {
        "enabled": _email_enabled(),
        "address": os.getenv("EMAIL_ADDRESS", ""),
        "provider": os.getenv("EMAIL_PROVIDER", "qq"),
        "importError": _mail_import_error,
    }


class MailConfigBody(BaseModel):
    provider: str = "qq"
    address: str
    password: str
    username: str = ""


@router.post("/config")
def mail_config(body: MailConfigBody) -> dict[str, Any]:
    """在页面内保存邮箱账户（写入 .env 并即时生效，无需重启后端）"""
    if _mail_import_failed:
        raise HTTPException(503, f"邮箱模块不可用：{_mail_import_error}（请先 pip install -r requirements.txt）")
    provider = body.provider.strip().lower()
    if provider not in ("qq", "163", "126", "outlook", "custom"):
        raise HTTPException(400, "不支持的服务商，可选 qq / 163 / 126 / outlook / custom")
    address = body.address.strip()
    password = body.password.strip()
    if not address or not password:
        raise HTTPException(400, "邮箱地址与授权码不能为空")
    _save_mail_env(
        provider=provider,
        address=address,
        password=password,
        username=body.username.strip(),
    )
    os.environ["EMAIL_PROVIDER"] = provider
    os.environ["EMAIL_ADDRESS"] = address
    os.environ["EMAIL_PASSWORD"] = password
    if body.username.strip():
        os.environ["EMAIL_USERNAME"] = body.username.strip()
    else:
        os.environ.pop("EMAIL_USERNAME", None)
    return {"enabled": True, "address": address, "provider": provider}


@router.post("/logout")
def mail_logout() -> dict[str, Any]:
    """退出邮箱：清除 .env 中的邮箱配置并立即停用（无需重启）"""
    _remove_mail_env(["EMAIL_PROVIDER", "EMAIL_ADDRESS", "EMAIL_PASSWORD", "EMAIL_USERNAME"])
    for key in ("EMAIL_PROVIDER", "EMAIL_ADDRESS", "EMAIL_PASSWORD", "EMAIL_USERNAME"):
        os.environ.pop(key, None)
    return {"enabled": False, "address": "", "provider": "qq", "importError": _mail_import_error}


@router.get("/folders")
def mail_folders() -> dict[str, Any]:
    _require_email()
    return _mail_call(_mail_list_folders)


@router.get("/messages")
def mail_messages(
    folder: str = "INBOX", keyword: str = "", unreadOnly: bool = False, limit: int = 20
) -> dict[str, Any]:
    _require_email()
    return _mail_call(
        _mail_search,
        folder=folder,
        keyword=keyword.strip() or None,
        unread_only=unreadOnly,
        limit=max(1, min(limit, 50)),
    )


@router.get("/messages/{mid}")
def mail_message(mid: str, folder: str = "INBOX", markRead: bool = True) -> dict[str, Any]:
    _require_email()
    return _mail_call(_mail_read, folder=folder, id=mid, mark_read=markRead)


class MailSendBody(BaseModel):
    to: str
    subject: str
    body: str = ""
    cc: str | None = None


@router.post("/send")
def mail_send(body: MailSendBody) -> dict[str, Any]:
    _require_email()
    if not body.to.strip():
        raise HTTPException(400, "收件人不能为空")
    return _mail_call(
        _mail_send,
        to=body.to,
        subject=body.subject.strip(),
        body=body.body,
        cc=(body.cc or "").strip() or None,
    )


class MailReplyBody(BaseModel):
    folder: str = "INBOX"
    body: str | None = None


@router.post("/messages/{mid}/reply")
def mail_reply(mid: str, body: MailReplyBody) -> dict[str, Any]:
    _require_email()
    return _mail_call(_mail_reply, folder=body.folder, id=mid, body=body.body)


class MailReadBody(BaseModel):
    folder: str = "INBOX"
    read: bool = True


@router.post("/messages/{mid}/read")
def mail_mark_read(mid: str, body: MailReadBody) -> dict[str, Any]:
    _require_email()
    return _mail_call(_mail_mark_read, folder=body.folder, id=mid, read=body.read)


class MailMoveBody(BaseModel):
    folder: str
    targetFolder: str


@router.post("/messages/{mid}/move")
def mail_move(mid: str, body: MailMoveBody) -> dict[str, Any]:
    _require_email()
    return _mail_call(_mail_move, folder=body.folder, id=mid, target_folder=body.targetFolder)


@router.delete("/messages/{mid}")
def mail_delete(mid: str, folder: str = "INBOX", permanent: bool = False) -> dict[str, Any]:
    _require_email()
    return _mail_call(_mail_delete, folder=folder, id=mid, permanent=permanent)
