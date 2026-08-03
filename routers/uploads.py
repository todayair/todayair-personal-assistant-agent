"""附件上传路由：/api/upload"""

import os
import uuid
from typing import Any

from fastapi import APIRouter, File, HTTPException, Request, UploadFile

from web_state import UPLOAD_DIR, UPLOAD_MAX_BYTES

router = APIRouter(tags=["uploads"])


@router.post("/api/upload")
async def upload_file(request: Request, file: UploadFile = File(...)) -> dict[str, Any]:
    """上传附件到本地 uploads/，返回绝对路径与访问 URL，供 Agent 读取分析。"""
    raw_name = os.path.basename(file.filename or "file")
    safe_name = "".join(c for c in raw_name if c.isalnum() or c in "._- ").strip() or "file"
    data = await file.read()
    if len(data) > UPLOAD_MAX_BYTES:
        raise HTTPException(400, "文件过大（上限 20MB）")
    if not data:
        raise HTTPException(400, "空文件")
    dest = os.path.join(UPLOAD_DIR, f"{uuid.uuid4().hex[:8]}_{safe_name}")
    with open(dest, "wb") as f:
        f.write(data)
    base = str(request.base_url).rstrip("/")
    return {
        "name": safe_name,
        "path": os.path.abspath(dest),
        "size": len(data),
        "type": file.content_type or "",
        "url": f"{base}/uploads/{os.path.basename(dest)}",
    }
