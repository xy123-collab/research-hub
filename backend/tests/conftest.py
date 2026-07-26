import os, tempfile, pytest
os.environ["DATABASE_URL"] = "sqlite:///" + tempfile.gettempdir() + "/test_rhub.db"
os.environ["LOCAL_STORAGE_DIR"] = tempfile.gettempdir() + "/test_rhub_data"
os.environ["STORAGE_BACKEND"] = "local"
os.environ["ENABLE_ONLINE_ANALYSIS"] = "true"  # sqlite 测试环境仅用于功能回归
# 频率限制默认关：整个测试套件从同一个「IP」发几百次登录，会被正常限流挡住。
# 限流本身由 tests/test_security_hardening.py 单独打开验证。
os.environ["RATE_LIMIT_ENABLED"] = "false"

# 测试里统一使用的合规密码（注册/重置要求 ≥10 位 + 两类字符）
STRONG_PW = "Rhub-Test-2026"

# 清库重建
_dbfile = os.path.join(tempfile.gettempdir(), "test_rhub.db")
if os.path.exists(_dbfile):
    os.remove(_dbfile)

from app.seed import run as seed_run
from app.main import app
from fastapi.testclient import TestClient

seed_run()


@pytest.fixture(scope="session")
def client():
    return TestClient(app)


def _token(client, u, p):
    return client.post("/api/auth/login", json={"username": u, "password": p}).json()["access_token"]


@pytest.fixture
def founder(client):
    return {"Authorization": f"Bearer {_token(client, 'lixiaoyu', 'pass123')}"}


@pytest.fixture
def member(client):
    return {"Authorization": f"Bearer {_token(client, 'chenmo', 'pass123')}"}


@pytest.fixture
def outsider(client):
    # 新注册用户：不是任何数据集成员
    client.post("/api/auth/register", json={"username": "outsider1", "password": STRONG_PW,
                                             "email": "outsider1@example.com"})
    return {"Authorization": f"Bearer {_token(client, 'outsider1', STRONG_PW)}"}
