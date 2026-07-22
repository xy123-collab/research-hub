"""文件上传公共助手：文件名/大小/类型校验 + 存 storage。"""
import os
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


def save_stored_file(key: str, fileobj) -> str:
    """把存储后端错误转为用户可执行的提示，避免裸 500。"""
    try:
        return storage.save(key, fileobj)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            503, "文件存储服务暂时不可用；请稍后重试。若持续发生，"
                 "请管理员检查 STORAGE_BACKEND 及 COS 配置/密钥")


def open_stored_file(key: str):
    """打开已存文件，区分「文件丢失」与「存储服务不可用」。"""
    try:
        return storage.open(key)
    except FileNotFoundError:
        raise HTTPException(
            404, "存储中已找不到该文件；如果使用 Render 免费本地存储，"
                 "服务重启后文件会丢失。请管理员重新上传，并建议配置 COS")
    except Exception as exc:
        if "NoSuchKey" in str(exc) or "not exist" in str(exc).lower():
            raise HTTPException(
                404, "存储中已找不到该文件；请管理员重新上传并检查 COS 文件键")
        raise HTTPException(
            503, "暂时无法连接文件存储；请稍后重试。若持续发生，"
                 "请管理员检查 COS 网络、地域、存储桶和密钥配置")


def validate_upload(file: UploadFile, whitelist: set | None = None,
                    *, allow_any_type: bool = False) -> dict:
    """校验上传文件并将文件指针复位。

    Codebook/对照表只存储不解析，可传 allow_any_type=True 保留任意扩展名；
    数据、代码、图片等仍使用明确白名单。
    """
    original = os.path.basename((file.filename or "").replace("\\", "/"))
    if not original:
        raise HTTPException(400, "未识别到文件名；请重新选择一个带文件名的本地文件")
    if any(c in original for c in ("\r", "\n", "\x00")):
        raise HTTPException(400, "文件名含有无效控制字符；请重命名后再上传")
    ext = _ext(original)
    if not allow_any_type:
        wl = whitelist or DEFAULT_WHITELIST
        if ext not in wl:
            shown = ext or "（无扩展名）"
            raise HTTPException(
                400, f"不支持的文件类型 {shown}；请改用：{', '.join(sorted(wl))}")
    try:
        file.file.seek(0, 2)
        size = file.file.tell()
        file.file.seek(0)
    except Exception:
        data = file.file.read()
        size = len(data)
        import io
        file.file = io.BytesIO(data)
    if size <= 0:
        raise HTTPException(400, "文件为空；请检查本地文件后重新选择")
    if size > settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(
            400, f"文件超过 {settings.MAX_UPLOAD_MB}MB 上限；请压缩、分拆文件或联系管理员调整上限")
    return {"filename": original, "ext": ext, "size": size}


def save_upload(file: UploadFile, prefix: str, whitelist: set | None = None) -> dict:
    checked = validate_upload(file, whitelist)
    ext, size = checked["ext"], checked["size"]
    data = file.file.read()
    import io
    key = f"{prefix}/{uuid.uuid4().hex}{ext}"
    save_stored_file(key, io.BytesIO(data))
    return {"file_path": key, "file_name": checked["filename"],
            "mime": file.content_type or "application/octet-stream", "size": size}
