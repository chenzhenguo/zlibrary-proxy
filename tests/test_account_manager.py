# -*- coding: utf-8 -*-
"""
AccountManager 测试类

测试账号管理器的核心功能：
- 账号加载与保存
- 账号切换
- 下载计数
- 限制检测
- 状态查询
"""

import json
import os
import tempfile
import pytest

from zlibrary.account_manager import AccountManager, REGISTERED_USER_DAILY_LIMIT


@pytest.fixture
def temp_accounts_file():
    """创建临时账号文件用于测试"""
    fd, path = tempfile.mkstemp(suffix=".json")
    # 写入测试账号数据
    test_accounts = [
        {"email": "test1@mailto.plus", "password": "pass1", "downloads_today": 0, "last_used": ""},
        {"email": "test2@mailto.plus", "password": "pass2", "downloads_today": 3, "last_used": ""},
        {"email": "test3@mailto.plus", "password": "pass3", "downloads_today": 0, "last_used": ""},
    ]
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(test_accounts, f)
    yield path
    # 测试后清理
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture
def empty_accounts_file():
    """创建空账号文件（不存在的文件）用于测试"""
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    os.remove(path)  # 删除文件，测试不存在的场景
    yield path
    if os.path.exists(path):
        os.remove(path)


class TestAccountManagerInit:
    """测试 AccountManager 初始化"""

    def test_load_accounts_from_file(self, temp_accounts_file):
        """测试从 JSON 文件加载账号"""
        manager = AccountManager(temp_accounts_file)
        assert len(manager.accounts) == 3
        assert manager.accounts[0]["email"] == "test1@mailto.plus"
        assert manager.accounts[1]["email"] == "test2@mailto.plus"
        assert manager.accounts[2]["email"] == "test3@mailto.plus"

    def test_init_with_nonexistent_file(self, empty_accounts_file):
        """测试文件不存在时初始化"""
        manager = AccountManager(empty_accounts_file)
        assert len(manager.accounts) == 0
        assert manager.has_accounts() is False

    def test_init_with_corrupt_file(self, temp_accounts_file):
        """测试文件损坏时初始化"""
        # 写入损坏的 JSON
        with open(temp_accounts_file, "w", encoding="utf-8") as f:
            f.write("{invalid json}")
        manager = AccountManager(temp_accounts_file)
        assert len(manager.accounts) == 0


class TestAccountManagerSwitch:
    """测试账号切换功能"""

    def test_switch_to_next_account(self, temp_accounts_file):
        """测试切换到下一个账号"""
        manager = AccountManager(temp_accounts_file)
        assert manager.current_index == 0
        assert manager.switch_account() is True
        assert manager.current_index == 1
        assert manager.switch_account() is True
        assert manager.current_index == 2

    def test_switch_past_last_account_loops(self, temp_accounts_file):
        """测试切换超过最后一个账号时循环回到第一个"""
        manager = AccountManager(temp_accounts_file)
        manager.switch_account()  # 0 -> 1
        manager.switch_account()  # 1 -> 2
        # 2 -> 循环回到 0（downloads_today=0 < limit）
        assert manager.switch_account() is True
        assert manager.current_index == 0

    def test_switch_with_no_accounts(self, empty_accounts_file):
        """测试无账号时切换"""
        manager = AccountManager(empty_accounts_file)
        assert manager.switch_account() is False

    def test_get_current_account(self, temp_accounts_file):
        """测试获取当前账号"""
        manager = AccountManager(temp_accounts_file)
        current = manager.get_current_account()
        assert current is not None
        assert current["email"] == "test1@mailto.plus"

        manager.switch_account()
        current = manager.get_current_account()
        assert current["email"] == "test2@mailto.plus"

    def test_get_current_account_with_no_accounts(self, empty_accounts_file):
        """测试无账号时获取当前账号"""
        manager = AccountManager(empty_accounts_file)
        assert manager.get_current_account() is None


class TestAccountManagerDownload:
    """测试下载计数功能"""

    def test_record_download(self, temp_accounts_file):
        """测试记录下载"""
        manager = AccountManager(temp_accounts_file)
        assert manager.accounts[0]["downloads_today"] == 0
        manager.record_download()
        assert manager.accounts[0]["downloads_today"] == 1
        manager.record_download()
        assert manager.accounts[0]["downloads_today"] == 2

    def test_record_download_persists(self, temp_accounts_file):
        """测试下载计数持久化"""
        manager = AccountManager(temp_accounts_file)
        manager.record_download()
        manager.record_download()

        # 重新加载，检查持久化
        manager2 = AccountManager(temp_accounts_file)
        assert manager2.accounts[0]["downloads_today"] == 2

    def test_is_limit_reached_false(self, temp_accounts_file):
        """测试未达限制"""
        manager = AccountManager(temp_accounts_file)
        assert manager.is_limit_reached() is False

    def test_is_limit_reached_true(self, temp_accounts_file):
        """测试已达限制"""
        manager = AccountManager(temp_accounts_file)
        # 将下载次数设为限制值
        manager.accounts[0]["downloads_today"] = REGISTERED_USER_DAILY_LIMIT
        assert manager.is_limit_reached() is True

    def test_reset_daily_counts(self, temp_accounts_file):
        """测试重置每日下载计数"""
        manager = AccountManager(temp_accounts_file)
        manager.record_download()
        manager.record_download()
        assert manager.accounts[0]["downloads_today"] == 2
        manager.reset_daily_counts()
        assert manager.accounts[0]["downloads_today"] == 0
        assert manager.accounts[1]["downloads_today"] == 0


class TestAccountManagerAdd:
    """测试添加账号功能"""

    def test_add_account(self, empty_accounts_file):
        """测试添加新账号"""
        manager = AccountManager(empty_accounts_file)
        assert len(manager.accounts) == 0

        manager.add_account("new@mailto.plus", "newpass")
        assert len(manager.accounts) == 1
        assert manager.accounts[0]["email"] == "new@mailto.plus"
        assert manager.accounts[0]["password"] == "newpass"
        assert manager.accounts[0]["downloads_today"] == 0

    def test_add_multiple_accounts(self, empty_accounts_file):
        """测试添加多个账号"""
        manager = AccountManager(empty_accounts_file)
        for i in range(5):
            manager.add_account(f"user{i}@mailto.plus", f"pass{i}")
        assert len(manager.accounts) == 5
        assert manager.has_accounts() is True


class TestAccountManagerStatus:
    """测试状态查询功能"""

    def test_get_status(self, temp_accounts_file):
        """测试获取状态信息"""
        manager = AccountManager(temp_accounts_file)
        status = manager.get_status()

        assert status["total_accounts"] == 3
        assert status["current_index"] == 0
        assert status["current_email"] == "test1@mailto.plus"
        assert status["current_downloads"] == 0
        assert status["daily_limit"] == REGISTERED_USER_DAILY_LIMIT
        assert status["logged_in"] is False
        assert len(status["accounts"]) == 3

    def test_get_status_after_switch(self, temp_accounts_file):
        """测试切换后获取状态"""
        manager = AccountManager(temp_accounts_file)
        manager.switch_account()
        status = manager.get_status()
        assert status["current_index"] == 1
        assert status["current_email"] == "test2@mailto.plus"
        assert status["current_downloads"] == 3  # 预设值为 3

    def test_get_status_no_accounts(self, empty_accounts_file):
        """测试无账号时获取状态"""
        manager = AccountManager(empty_accounts_file)
        status = manager.get_status()
        assert status["total_accounts"] == 0
        assert status["current_email"] is None


class TestAccountManagerCookies:
    """测试 cookie 登录功能"""

    @pytest.fixture
    def cookie_accounts_file(self):
        """创建带 cookie 的测试账号文件"""
        fd, path = tempfile.mkstemp(suffix=".json")
        test_accounts = [
            {
                "email": "user1@duckmail.sbs",
                "password": "123456",
                "cookies": [
                    {"name": "remix_userkey", "value": "abc123", "domain": ".zlib.bz", "path": "/"},
                    {"name": "remix_userid", "value": "456789", "domain": ".zlib.bz", "path": "/"},
                    {"name": "session_id", "value": "xyz789", "domain": ".zlib.bz", "path": "/"},
                ],
                "downloads_today": 0,
                "last_used": "",
            },
            {
                "email": "user2@duckmail.sbs",
                "password": "123456",
                "cookies": [],
                "downloads_today": 0,
                "last_used": "",
            },
        ]
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(test_accounts, f)
        yield path
        if os.path.exists(path):
            os.remove(path)

    def test_load_cookies_to_session(self, cookie_accounts_file):
        """测试将 cookie 加载到 session"""
        import requests
        from zlibrary.account_manager import AccountManager

        manager = AccountManager(cookie_accounts_file)
        session = requests.Session()

        # 调用私有方法加载 cookie
        manager._load_cookies_to_session(session)

        # 验证 cookie 已加载
        assert len(session.cookies) == 3
        assert session.cookies.get("remix_userkey") == "abc123"
        assert session.cookies.get("remix_userid") == "456789"

    def test_save_session_cookies(self, cookie_accounts_file):
        """测试保存 session cookie 到账号"""
        import requests
        from zlibrary.account_manager import AccountManager

        manager = AccountManager(cookie_accounts_file)
        session = requests.Session()

        # 设置一些 cookie
        session.cookies.set("new_cookie", "new_value", domain=".zlib.bz", path="/")

        # 保存
        manager._save_session_cookies(session)

        # 验证保存
        account = manager.get_current_account()
        cookie_names = [c["name"] for c in account["cookies"]]
        assert "new_cookie" in cookie_names

    def test_status_shows_cookies(self, cookie_accounts_file):
        """测试状态信息中显示 cookie 状态"""
        from zlibrary.account_manager import AccountManager

        manager = AccountManager(cookie_accounts_file)
        status = manager.get_status()

        assert status["accounts"][0]["has_cookies"] is True
        assert status["accounts"][1]["has_cookies"] is False

    def test_switch_to_account_with_cookies(self, cookie_accounts_file):
        """测试切换到有 cookie 的账号"""
        import requests
        from zlibrary.account_manager import AccountManager

        manager = AccountManager(cookie_accounts_file)

        # 第一个账号有 cookie
        assert manager.get_current_account()["email"] == "user1@duckmail.sbs"
        assert len(manager.get_current_account()["cookies"]) == 3

        # 切换到第二个账号（无 cookie）
        manager.switch_account()
        assert manager.get_current_account()["email"] == "user2@duckmail.sbs"
        assert len(manager.get_current_account()["cookies"]) == 0

    def test_add_account_with_cookies(self, empty_accounts_file):
        """测试添加带 cookie 的账号"""
        from zlibrary.account_manager import AccountManager

        manager = AccountManager(empty_accounts_file)
        cookies = [
            {"name": "test_cookie", "value": "test_value", "domain": ".zlib.bz", "path": "/"},
        ]
        manager.add_account("new@duckmail.sbs", "123456", cookies=cookies)

        assert len(manager.accounts) == 1
        assert len(manager.accounts[0]["cookies"]) == 1
        assert manager.accounts[0]["cookies"][0]["name"] == "test_cookie"
