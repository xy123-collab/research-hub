"""storage 接口 + 双实现：本地目录 / 腾讯云 COS。切换只改 STORAGE_BACKEND。

三个后端的 key 语义完全一致（如 `versions/ab12cd.dta`），所以切换后端**不需要动数据库里
任何 file_path 字段**，只需把历史对象搬到新后端。
"""
import os
import shutil
from abc import ABC, abstractmethod
from .config import settings


class StorageKeyError(ValueError):
    """非法的对象 key（路径穿越等）。"""


def safe_key(key: str) -> str:
    """校验并规范化对象 key。

    历史问题：`api/users.py` 的头像接口只校验 `key.startswith("avatar/")`，而
    LocalStorage 直接 os.path.join(base, key)，于是 `avatar/../versions/xxx.dta`
    既通过了前缀校验、又读到了别的数据集的原始数据；`avatar/../../../etc/passwd`
    更是直接跳出存储目录。这里统一在存储层拦住，任何后端都不再接受 `..`。
    """
    if not key or not isinstance(key, str):
        raise StorageKeyError("对象 key 不能为空")
    if "\x00" in key:
        raise StorageKeyError("对象 key 含非法字符")
    k = key.replace("\\", "/")
    if k.startswith("/"):
        raise StorageKeyError("对象 key 不允许使用绝对路径")
    # 逐段检查，杜绝 ".." 与空段；不用 normpath，避免它把 a/../b 悄悄化简为 b 而放行
    parts = [p for p in k.split("/") if p != ""]
    if not parts:
        raise StorageKeyError("对象 key 不能为空")
    if any(p == ".." for p in parts):
        raise StorageKeyError("对象 key 不允许包含上级目录（..）")
    return "/".join(parts)


class Storage(ABC):
    @abstractmethod
    def save(self, key: str, fileobj) -> str: ...
    @abstractmethod
    def open(self, key: str): ...
    @abstractmethod
    def url(self, key: str) -> str: ...
    @abstractmethod
    def delete(self, key: str) -> None: ...


class LocalStorage(Storage):
    def __init__(self, base_dir: str):
        self.base = os.path.abspath(base_dir)
        os.makedirs(self.base, exist_ok=True)

    def _path(self, key: str, *, mkdir: bool = False) -> str:
        p = os.path.abspath(os.path.join(self.base, safe_key(key)))
        # 双保险：即便 safe_key 被绕过，最终路径也不允许逃出 base
        if not p.startswith(self.base + os.sep):
            raise StorageKeyError("对象 key 超出存储目录范围")
        if mkdir:
            os.makedirs(os.path.dirname(p), exist_ok=True)
        return p

    def save(self, key, fileobj) -> str:
        with open(self._path(key, mkdir=True), "wb") as f:
            shutil.copyfileobj(fileobj, f)
        return safe_key(key)

    def open(self, key):
        return open(self._path(key), "rb")

    def url(self, key) -> str:
        return f"/files/{safe_key(key)}"

    def delete(self, key) -> None:
        p = self._path(key)
        if os.path.exists(p):
            os.remove(p)


class COSStorage(Storage):
    """腾讯云 COS 实现（私有读 + 签名 URL）。仅在此层引用 COS SDK。"""
    def __init__(self):
        from qcloud_cos import CosConfig, CosS3Client
        conf = CosConfig(Region=settings.COS_REGION, SecretId=settings.COS_SECRET_ID,
                         SecretKey=settings.COS_SECRET_KEY, Scheme="https")
        self.client = CosS3Client(conf)
        self.bucket = settings.COS_BUCKET

    def save(self, key, fileobj) -> str:
        key = safe_key(key)
        self.client.put_object(Bucket=self.bucket, Body=fileobj, Key=key)
        return key

    def open(self, key):
        resp = self.client.get_object(Bucket=self.bucket, Key=safe_key(key))
        return resp["Body"].get_raw_stream()

    def url(self, key) -> str:
        return self.client.get_presigned_download_url(
            Bucket=self.bucket, Key=safe_key(key), Expired=settings.COS_SIGNED_URL_TTL)

    def delete(self, key) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=safe_key(key))


def get_storage() -> Storage:
    backend = (settings.STORAGE_BACKEND or "local").strip().lower()
    if backend == "cos":
        return COSStorage()
    return LocalStorage(settings.LOCAL_STORAGE_DIR)


storage = get_storage()
