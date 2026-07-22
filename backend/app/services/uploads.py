"""文件上传公共助手：大小/类型白名单校验 + 存 storage。"""
import re
import uuid
from urllib.parse import quote
from fastapi import UploadFile, HTTPException
from ..core.config import settings
from ..core.storage import storage

# 数据文件支持的格式：Stata / CSV / Excel / Parquet / MATLAB(.mat v7.2 及以下)
DATA_EXT = {".dta", ".csv", ".xlsx", ".xls", ".parquet", ".mat"}
DOC_EXT = {".pdf", ".docx", ".doc", ".md", ".txt", ".csv"}
CODE_EXT = {".do", ".py", ".r", ".ipynb", ".sql", ".txt", ".m"}
IMG_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
DEFAULT_WHITELIST = DATA_EXT | DOC_EXT | CODE_EXT | IMG_EXT | {".zip", ".xlsx", ".xls"}


def data_ext_of(name: str | None) -> str:
    """取数据文件扩展名（小写、带点）；无扩展名返回 ''。"""
    return _ext(name or "")


def attachment_headers(filename: str) -> dict:
    """构造 Content-Disposition 头，安全支持中文等非 ASCII 文件名（RFC 5987）。

    直接拼 `filename="中文.xlsx"` 会让 Starlette 按 latin-1 编码响应头而 500，
    这是此前上传/下载中文文件名报错的根因之一。这里给 ASCII 回退名 + UTF-8 编码名。
    """
    name = (filename or "file").replace('"', "").replace("\r", "").replace("\n", "")
    fallback = re.sub(r"[^\x20-\x7e]", "_", name) or "file"
    return {"Content-Disposition":
            f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(name)}"}


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
