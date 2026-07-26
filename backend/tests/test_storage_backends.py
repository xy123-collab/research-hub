"""存储层测试：key 安全校验 + 本地后端往返。

A7（阿里云 OSS 适配）按本轮要求暂不实施，当前仍只支持本地目录与腾讯云 COS。
"""
import io
import os
import sys
import tempfile
import types
import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.gettempdir() + "/test_rhub.db")

from app.core.config import settings  # noqa: E402
from app.core.storage import (COSStorage, LocalStorage, StorageKeyError,  # noqa: E402
                              get_storage, safe_key)


# ---------- key 安全校验（这是 A3 路径穿越漏洞的回归测试）----------

@pytest.mark.parametrize("bad", [
    "avatar/../versions/secret.dta",      # 不跳出 base，但越权读别的数据集 —— 真实攻击载荷
    "avatar/../../../etc/passwd",         # 跳出存储目录读服务器文件
    "../etc/passwd",
    "avatar/..",
    "avatar\\..\\..\\etc\\passwd",        # 反斜杠变体
    "/versions/ab12cd.dta",               # 绝对路径
    "/etc/passwd",
    "",
    None,
])
def test_safe_key_rejects_traversal(bad):
    with pytest.raises(StorageKeyError):
        safe_key(bad)


@pytest.mark.parametrize("good,expected", [
    ("avatar/12ab.png", "avatar/12ab.png"),
    ("versions/ab12cd.dta", "versions/ab12cd.dta"),
    ("versions//ab12cd.dta", "versions/ab12cd.dta"),      # 空段被规范掉
])
def test_safe_key_accepts_normal(good, expected):
    assert safe_key(good) == expected


# ---------- 本地后端往返 ----------

@pytest.fixture
def local_store(tmp_path):
    return LocalStorage(str(tmp_path / "data"))


def test_local_roundtrip(local_store):
    key = "versions/roundtrip.dta"
    payload = b"hello \xe4\xb8\xad\xe6\x96\x87 data"
    assert local_store.save(key, io.BytesIO(payload)) == key
    with local_store.open(key) as f:
        assert f.read() == payload
    local_store.delete(key)
    with pytest.raises(FileNotFoundError):
        local_store.open(key)


def test_local_open_rejects_traversal(local_store, tmp_path):
    """构造一个真实存在于 base 之外的文件，确认拿不到。"""
    outside = tmp_path / "outside.txt"
    outside.write_text("SECRET")
    with pytest.raises(StorageKeyError):
        local_store.open("versions/../../outside.txt")


def test_local_save_rejects_traversal(local_store):
    with pytest.raises(StorageKeyError):
        local_store.save("avatar/../../evil.txt", io.BytesIO(b"x"))


def test_local_delete_rejects_traversal(local_store):
    with pytest.raises(StorageKeyError):
        local_store.delete("avatar/../../../etc/passwd")


# ---------- 腾讯云 COS 后端（SDK mock，不访问真实桶）----------

class _FakeBody:
    def __init__(self, value):
        self.value = value

    def get_raw_stream(self):
        return io.BytesIO(self.value)


class _FakeCOSClient:
    objects = {}

    def __init__(self, _conf):
        self.conf = _conf

    def put_object(self, *, Bucket, Body, Key):
        self.objects[(Bucket, Key)] = Body.read()

    def get_object(self, *, Bucket, Key):
        return {"Body": _FakeBody(self.objects[(Bucket, Key)])}

    def get_presigned_download_url(self, *, Bucket, Key, Expired):
        return f"https://cos.example/{Bucket}/{Key}?ttl={Expired}"

    def delete_object(self, *, Bucket, Key):
        self.objects.pop((Bucket, Key), None)


def _cos_settings(monkeypatch):
    monkeypatch.setattr(settings, "COS_BUCKET", "research-hub-123")
    monkeypatch.setattr(settings, "COS_REGION", "ap-beijing")
    monkeypatch.setattr(settings, "COS_SECRET_ID", "test-id")
    monkeypatch.setattr(settings, "COS_SECRET_KEY", "test-key")


def test_cos_roundtrip_and_signed_url(monkeypatch):
    _cos_settings(monkeypatch)
    _FakeCOSClient.objects = {}
    fake_sdk = types.SimpleNamespace(
        CosConfig=lambda **kw: kw,
        CosS3Client=_FakeCOSClient,
    )
    monkeypatch.setitem(sys.modules, "qcloud_cos", fake_sdk)
    store = COSStorage()
    key = "avatar/user-1.png"
    assert store.save(key, io.BytesIO(b"avatar")) == key
    assert store.open(key).read() == b"avatar"
    assert store.url(key).startswith(
        "https://cos.example/research-hub-123/avatar/user-1.png?ttl=")
    store.delete(key)
    assert ("research-hub-123", key) not in _FakeCOSClient.objects


def test_cos_requires_complete_configuration(monkeypatch):
    monkeypatch.setattr(settings, "COS_BUCKET", "")
    monkeypatch.setattr(settings, "COS_REGION", "")
    monkeypatch.setattr(settings, "COS_SECRET_ID", "")
    monkeypatch.setattr(settings, "COS_SECRET_KEY", "")
    with pytest.raises(RuntimeError, match="COS 配置不完整"):
        COSStorage()


def test_unknown_storage_backend_never_falls_back_to_local(monkeypatch):
    monkeypatch.setattr(settings, "STORAGE_BACKEND", "typo-coss")
    with pytest.raises(RuntimeError, match="不支持"):
        get_storage()
