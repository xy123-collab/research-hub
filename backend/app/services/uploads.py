"""文件上传公共助手：大小/类型白名单校验 + 存 storage。"""
import uuid
from fastapi import UploadFile, HTTPException
from ..core.config import settings
from ..core.storage import storage

DATA_EXT = {".dta"}
DOC_EXT = {".pdf", ".docx", ".doc", ".md", ".txt", ".csv"}
CODE_EXT = {".do", ".py", ".r", ".ipynb", ".sql", ".txt", ".m"}
IMG_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
DEFAULT_WHITELIST = DATA_EXT | DOC_EXT | CODE_EXT | IMG_EXT | {".zip", ".xlsx", ".xls"}


def _ext(name: str) -> str:
    return ("." + name.rsplit(".", 1)[-1].lower()) if "." in name else ""


def save_upload(file: UploadFile, prefix: str, whitelist: set | None = None) -> dict:
    wl = whitelist or DEFAULT_WHITELIST
    ext = _ext(file.filename or "")
    if ext not in wl:
        raise HTTPException(400, f"不支持的文件类型 {ext}；允许：{', '.join(sorted(wl))}")
    # 读入判断大小
    data = file.file.read()
    size = len(data)
    if size > settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(400, f"文件超过 {settings.MAX_UPLOAD_MB}MB 上限")
    import io
    key = f"{prefix}/{uuid.uuid4().hex}{ext}"
    storage.save(key, io.BytesIO(data))
    return {"file_path": key, "file_name": file.filename,
            "mime": file.content_type or "application/octet-stream", "size": size}
