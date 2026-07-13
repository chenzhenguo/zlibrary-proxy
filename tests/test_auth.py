# -*- coding: utf-8 -*-
"""
密码保护功能测试类

测试 Flask 应用的密码保护机制：
- 未认证访问重定向到登录页
- 正确密码登录成功
- 错误密码登录失败
- 登录后可以正常访问
- 注销后需要重新登录
"""

import pytest

from app import app, ACCESS_PASSWORD


@pytest.fixture
def client():
    """创建 Flask 测试客户端"""
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test-secret-key"
    with app.test_client() as client:
        with app.app_context():
            yield client


class TestPasswordProtection:
    """测试密码保护功能"""

    def test_unauthenticated_access_redirects(self, client):
        """测试未认证访问重定向到登录页"""
        resp = client.get("/")
        assert resp.status_code == 302
        assert "/login" in resp.headers.get("Location", "")

    def test_unauthenticated_search_redirects(self, client):
        """测试未认证搜索重定向"""
        resp = client.get("/search?q=python")
        assert resp.status_code == 302
        assert "/login" in resp.headers.get("Location", "")

    def test_unauthenticated_status_redirects(self, client):
        """测试未认证状态页重定向"""
        resp = client.get("/status")
        assert resp.status_code == 302
        assert "/login" in resp.headers.get("Location", "")

    def test_login_page_accessible(self, client):
        """测试登录页面可以正常访问"""
        resp = client.get("/login")
        assert resp.status_code == 200
        assert b"password" in resp.data.lower() or b"Password" in resp.data


class TestLoginLogout:
    """测试登录和注销流程"""

    def test_login_with_correct_password(self, client):
        """测试正确密码登录"""
        resp = client.post("/login", data={"password": ACCESS_PASSWORD})
        assert resp.status_code == 302
        assert "/" in resp.headers.get("Location", "")

    def test_login_with_wrong_password(self, client):
        """测试错误密码登录"""
        resp = client.post("/login", data={"password": "wrong"})
        assert resp.status_code == 200  # 停留在登录页
        assert b"Wrong password" in resp.data

    def test_access_after_login(self, client):
        """测试登录后可以正常访问"""
        # 先登录
        client.post("/login", data={"password": ACCESS_PASSWORD})
        # 访问首页
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"Z-Library" in resp.data

    def test_logout_clears_session(self, client):
        """测试注销后需要重新登录"""
        # 先登录
        client.post("/login", data={"password": ACCESS_PASSWORD})
        # 注销
        resp = client.get("/logout")
        assert resp.status_code == 302
        # 访问首页应该被重定向到登录页
        resp = client.get("/")
        assert resp.status_code == 302
        assert "/login" in resp.headers.get("Location", "")

    def test_status_page_after_login(self, client):
        """测试登录后可以访问状态页"""
        client.post("/login", data={"password": ACCESS_PASSWORD})
        resp = client.get("/status")
        assert resp.status_code == 200
        # 状态页应该包含账号信息部分
        assert b"Account Status" in resp.data or b"No accounts" in resp.data
