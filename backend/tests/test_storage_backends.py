"""存储层测试：key 安全校验 + 本地后端往返。

A7（阿里云 OSS 适配）按本轮要求暂不实施，当前仍只支持本地目录与腾讯云 COS。
"""
import io
import os
import tempfile
import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.gettempdir() + "/test_rhub.db")

from app.core.storage import LocalStorage, StorageKeyError, safe_key  # noqa: E402


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

