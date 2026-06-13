"""pytest 配置 + 共享 fixtures"""
import pytest
from fastapi.testclient import TestClient
import sys
from pathlib import Path

# 确保项目根目录在路径中
sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app
from database import SessionLocal, engine, Base


@pytest.fixture(scope="function")
def client():
    """创建测试客户端"""
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="function")
def auth_headers(client):
    """注册一个测试用户并返回带 Token 的 headers"""
    # 注册
    import uuid
    username = f"test_{uuid.uuid4().hex[:6]}"
    resp = client.post("/auth/register", json={"username": username, "password": "test123456"})
    token = resp.json().get("token", "")
    return {"Authorization": f"Bearer {token}", "X-Username": username}
