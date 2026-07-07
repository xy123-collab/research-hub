"""storage 接口 + 双实现：本地目录 / 腾讯云 COS。切换只改 STORAGE_BACKEND。"""
import os
import shutil
from abc import ABC, abstractmethod
from .config import settings


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

    def _path(self, key: str) -> str:
        p = os.path.join(self.base, key)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        return p

    def save(self, key, fileobj) -> str:
        p = self._path(key)
        with open(p, "wb") as f:
            shutil.copyfileobj(fileobj, f)
        return key

    def open(self, key):
        return open(os.path.join(self.base, key), "rb")

    def url(self, key) -> str:
        return f"/files/{key}"

    def delete(self, key) -> None:
        p = os.path.join(self.base, key)
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
        self.client.put_object(Bucket=self.bucket, Body=fileobj, Key=key)
        return key

    def open(self, key):
        resp = self.client.get_object(Bucket=self.bucket, Key=key)
        return resp["Body"].get_raw_stream()

    def url(self, key) -> str:
        return self.client.get_presigned_download_url(
            Bucket=self.bucket, Key=key, Expired=settings.COS_SIGNED_URL_TTL)

    def delete(self, key) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)


def get_storage() -> Storage:
    if settings.STORAGE_BACKEND == "cos":
        return COSStorage()
    return LocalStorage(settings.LOCAL_STORAGE_DIR)


storage = get_storage()
