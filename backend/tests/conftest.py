import os, tempfile, pytest
os.environ["DATABASE_URL"] = "sqlite:///" + tempfile.gettempdir() + "/test_rhub.db"
os.environ["LOCAL_STORAGE_DIR"] = tempfile.gettempdir() + "/test_rhub_data"
os.environ["STORAGE_BACKEND"] = "local"

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
    client.post("/api/auth/register", json={"username": "outsider1", "password": "pass123"})
    return {"Authorization": f"Bearer {_token(client, 'outsider1', 'pass123')}"}
