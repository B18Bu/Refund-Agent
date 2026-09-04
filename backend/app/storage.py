"""本地文件存储：上传图片落盘、重命名、sha256 校验、受控存储键。

- 服务端自行重命名文件，暴露 `storage_key`（相对路径），不暴露绝对路径。
- 计算 sha256 用于内容校验。
- 仅支持 image/jpeg、image/png（MIME + 文件头双重校验）。
"""
import hashlib
import io
import os
import re
import uuid

from fastapi import HTTPException, UploadFile

from app.config import settings

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png"}
ALLOWED_MIME = {"image/jpeg", "image/png"}
# 文件头魔数 → MIME
_MAGIC = {
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG\r\n\x1a\n": "image/png",
}

_SANE_FILENAME = re.compile(r"[^A-Za-z0-9._\-一-鿿]")


def sanitize_filename(name: str) -> str:
    base = os.path.basename(name or "file")
    base = _SANE_FILENAME.sub("_", base)
    return base[:120] or "file"


def sniff_mime(head: bytes) -> str | None:
    for magic, mime in _MAGIC.items():
        if head.startswith(magic):
            return mime
    return None


async def save_upload(ufile: UploadFile) -> dict:
    """校验并保存单个上传文件，返回 {storage_key, filename, content_type, size_bytes, sha256}。"""
    data = await ufile.read()
    if len(data) == 0:
        raise HTTPException(400, "空文件")

    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if len(data) > max_bytes:
        raise HTTPException(413, f"文件超过 {settings.MAX_UPLOAD_SIZE_MB}MB 上限")

    mime_by_header = sniff_mime(data[:8])
    if mime_by_header is None:
        raise HTTPException(415, "仅支持 JPG/JPEG/PNG 图片")

    content_type = (ufile.content_type or "").split(";")[0].strip().lower()
    if content_type and content_type not in ALLOWED_MIME:
        raise HTTPException(415, f"不支持的媒体类型: {content_type}")

    ext = ".png" if mime_by_header == "image/png" else ".jpg"
    storage_key = f"uploads/{uuid.uuid4().hex}{ext}"

    upload_dir = settings.UPLOAD_DIR
    os.makedirs(upload_dir, exist_ok=True)
    dest = os.path.join(upload_dir, os.path.basename(storage_key))
    with open(dest, "wb") as f:
        f.write(data)

    return {
        "storage_key": storage_key,
        "filename": sanitize_filename(ufile.filename or "file"),
        "content_type": mime_by_header,
        "size_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def resolve_abs_path(storage_key: str) -> str:
    """storage_key → 本地绝对路径（供 Worker OCR 读取）。"""
    return os.path.join(settings.UPLOAD_DIR, os.path.basename(storage_key))
