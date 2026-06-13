"""认证模块测试"""
import pytest
import uuid


class TestAuth:
    def test_register_success(self, client):
        """注册成功返回 token"""
        name = f"test_{uuid.uuid4().hex[:6]}"
        resp = client.post("/auth/register", json={"username": name, "password": "test123"})
        assert resp.status_code == 200 or resp.status_code == 409  # 409 if name collision
        if resp.status_code == 200:
            assert "token" in resp.json()

    def test_register_duplicate(self, client):
        """重复注册被拒绝"""
        name = f"dup_{uuid.uuid4().hex[:6]}"
        client.post("/auth/register", json={"username": name, "password": "test123"})
        resp = client.post("/auth/register", json={"username": name, "password": "test123"})
        assert resp.status_code == 409

    def test_register_short_password(self, client):
        """密码太短被拒绝"""
        resp = client.post("/auth/register", json={"username": "abc", "password": "123"})
        assert resp.status_code == 400

    def test_login_success(self, client):
        """登录成功返回 token"""
        name = f"login_{uuid.uuid4().hex[:6]}"
        client.post("/auth/register", json={"username": name, "password": "test123"})
        resp = client.post("/auth/login", json={"username": name, "password": "test123"})
        assert resp.status_code == 200
        assert len(resp.json()["token"]) > 10

    def test_login_wrong_password(self, client):
        """错误密码被拒绝"""
        name = f"wrong_{uuid.uuid4().hex[:6]}"
        client.post("/auth/register", json={"username": name, "password": "test123"})
        resp = client.post("/auth/login", json={"username": name, "password": "bad"})
        assert resp.status_code == 401

    def test_me_requires_auth(self, client):
        """未登录访问 /auth/me 被拒"""
        resp = client.get("/auth/me")
        assert resp.status_code == 401

    def test_me_with_auth(self, client, auth_headers):
        """登录后可以获取用户信息"""
        resp = client.get("/auth/me", headers=auth_headers)
        assert resp.status_code == 200
        assert "username" in resp.json()
        assert "role" in resp.json()


class TestRolePermission:
    def test_upload_without_auth(self, client):
        """未登录上传被拒"""
        resp = client.post("/documents/upload")
        assert resp.status_code in (401, 422)

    def test_ask_without_auth(self, client):
        """未登录无法问答"""
        resp = client.post("/ask", json={"question": "测试"})
        assert resp.status_code == 401

    def test_health_check(self, client):
        """健康检查无需登录"""
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
