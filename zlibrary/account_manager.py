# -*- coding: utf-8 -*-
"""
Z-Library 账号管理器

功能：
- 从 accounts.json 加载/保存账号列表（含 cookie）
- 优先用 cookie 登录（最快，无需请求）
- cookie 失效时用 email/password POST /login 登录
- 下载超限时自动切换到下一个账号
- 跟踪每个账号的当日下载次数

线程安全：
- 内部使用 threading.RLock 保护所有读写操作
- 原子写入：先写临时文件再 os.replace，避免半写状态
- 高可用：登录失败自动重试，cookie 失效自动降级到密码登录

accounts.json 格式：
[
    {
        "email": "xxx@duckmail.sbs",
        "password": "123456",
        "cookies": [
            {"name": "remix_userkey", "value": "xxx", "domain": ".zlib.bz", "path": "/"},
            ...
        ],
        "downloads_today": 0,
        "last_used": ""
    },
    ...
]
"""

import json
import logging
import os
import tempfile
import threading
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin

import requests

from .config import (
    ACCOUNTS_FILE,
    DEFAULT_HEADERS,
    LOGIN_COOKIE_NAME,
    LOGIN_INDICATORS,
    POW_COOKIE_NAMES,
    REGISTERED_USER_DAILY_LIMIT,
    REQUEST_TIMEOUT,
    ZLibError,
)

logger = logging.getLogger(__name__)


# ============ 错误类型 ============

class LoginFailedError(ZLibError):
    """登录失败"""
    pass


# ============ 工具函数 ============

def _clear_login_cookies(session: requests.Session) -> None:
    """
    清除登录相关 cookie，保留 PoW cookie（c_token, c_date）

    账号切换时调用：清除旧账号的登录 cookie，保留 PoW cookie 避免重新求解。
    线程安全：仅操作 session.cookies，无需额外锁。
    """
    to_remove = []
    for cookie in session.cookies:
        if cookie.name not in POW_COOKIE_NAMES:
            to_remove.append((cookie.name, cookie.domain, cookie.path))

    for name, domain, path in to_remove:
        try:
            session.cookies.clear(domain, path, name)
        except Exception:
            # 单个 cookie 清除失败不影响整体
            pass


def _atomic_write_json(path: str, data) -> None:
    """
    原子写入 JSON 文件：先写临时文件再 os.replace

    防止并发写入导致文件半写状态。
    """
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)

    # NamedTemporaryFile + delete=False 确保 Windows 兼容
    fd, tmp_path = tempfile.mkstemp(
        dir=directory, prefix=".accounts_", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        # 原子替换（POSIX/Windows 都支持）
        os.replace(tmp_path, path)
    except Exception:
        # 清理临时文件
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ============ 账号管理器 ============

class AccountManager:
    """
    Z-Library 账号管理器

    线程安全：所有公开方法均可从多线程并发调用。
    与 ZLibraryClient 配合使用：当下载超限时，自动切换到下一个账号。
    """

    def __init__(self, accounts_file: Optional[str] = None):
        """
        初始化账号管理器

        Args:
            accounts_file: 账号 JSON 文件路径，默认从 config.ACCOUNTS_FILE 读取
        """
        self.accounts_file = str(accounts_file or ACCOUNTS_FILE)
        self.accounts: list = []
        self.current_index: int = 0
        self._logged_in: bool = False
        # RLock 允许同一线程重复获取（避免内部方法互相调用时死锁）
        self._lock = threading.RLock()
        self._load_accounts()

    # ============ 内部方法（线程安全） ============

    def _load_accounts(self) -> None:
        """从 JSON 文件加载账号列表（线程安全）"""
        with self._lock:
            if os.path.exists(self.accounts_file):
                try:
                    with open(self.accounts_file, "r", encoding="utf-8") as f:
                        self.accounts = json.load(f)
                    # 确保每个账号都有必要字段
                    for acc in self.accounts:
                        acc.setdefault("downloads_today", 0)
                        acc.setdefault("last_used", "")
                        acc.setdefault("cookies", [])
                except (json.JSONDecodeError, IOError):
                    self.accounts = []
            else:
                self.accounts = []

    def _save_accounts(self) -> None:
        """原子保存账号列表到 JSON 文件（线程安全）"""
        with self._lock:
            _atomic_write_json(self.accounts_file, self.accounts)

    def _load_cookies_to_session(self, session: requests.Session, base_url: str = "") -> None:
        """
        将当前账号的 cookies 加载到 session（线程安全）

        关键修复：cookie 域名适配当前镜像域名
        保存的 cookie 域名可能是 .zlib.bz，但当前镜像可能是 z-lib.su，
        需要将 cookie 域名替换为当前 base_url 的域名，否则 cookie 不会被发送。

        Args:
            session: requests.Session 对象
            base_url: 当前 Z-Library 镜像 URL（用于提取域名）
        """
        with self._lock:
            account = self._get_current_account_unsafe()
            if not account:
                return
            cookies = account.get("cookies", [])

        # 提取当前镜像域名
        from urllib.parse import urlparse
        current_domain = ""
        if base_url:
            parsed = urlparse(base_url)
            current_domain = parsed.netloc
            # 加上通配前缀（如 .z-lib.su）
            if current_domain and not current_domain.startswith("."):
                current_domain = "." + current_domain

        # 设置 cookie，用当前镜像域名替换保存的域名
        for cookie in cookies:
            try:
                name = cookie.get("name", "")
                value = cookie.get("value", "")
                # 跳过 PoW cookie（由 client 自行管理）
                if name in POW_COOKIE_NAMES:
                    continue
                domain = current_domain or cookie.get("domain", "")
                session.cookies.set(
                    name,
                    value,
                    domain=domain,
                    path=cookie.get("path", "/"),
                )
            except Exception:
                continue

    def _save_session_cookies(self, session: requests.Session) -> None:
        """将 session 中的 cookies 保存到当前账号（线程安全）"""
        # 读取 cookies 不需要锁（session 独立）
        cookie_list = []
        for c in session.cookies:
            cookie_list.append({
                "name": c.name,
                "value": c.value,
                "domain": c.domain,
                "path": c.path,
                "expiry": getattr(c, "expiry", 0) or 0,
            })

        with self._lock:
            account = self._get_current_account_unsafe()
            if account:
                account["cookies"] = cookie_list

    def _get_current_account_unsafe(self) -> Optional[dict]:
        """获取当前账号（不加锁，调用方需持锁）"""
        if not self.accounts:
            return None
        return self.accounts[self.current_index]

    def _check_login_status(self, session: requests.Session, base_url: str) -> bool:
        """
        精确检查登录状态

        优先检查 session 中是否有 remix_userid cookie（最可靠）；
        否则检查 HTML 文本中的登录标志。

        Args:
            session: requests.Session 对象
            base_url: Z-Library 基础 URL

        Returns:
            True 表示已登录
        """
        # 方法1：检查 session 中的登录 cookie（最可靠，无需 HTTP 请求）
        if session.cookies.get(LOGIN_COOKIE_NAME):
            return True

        # 方法2：访问首页，检查 HTML 文本
        try:
            resp = session.get(base_url, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 503:
                return False  # PoW 挑战页
            if resp.status_code == 200:
                text = resp.text.lower()
                return any(indicator in text for indicator in LOGIN_INDICATORS)
            return False
        except requests.RequestException:
            return False

    # ============ 公开方法（线程安全） ============

    def has_accounts(self) -> bool:
        """是否有可用账号"""
        with self._lock:
            return len(self.accounts) > 0

    def get_current_account(self) -> Optional[dict]:
        """获取当前账号信息（线程安全，copy 返回避免外部修改）"""
        with self._lock:
            acc = self._get_current_account_unsafe()
            return dict(acc) if acc else None

    def is_logged_in(self) -> bool:
        """当前账号是否已登录"""
        with self._lock:
            return self._logged_in

    def login(self, session: requests.Session, base_url: str) -> bool:
        """
        登录 Z-Library（线程安全）

        优先使用保存的 cookie 登录（最快）；
        cookie 失效时用 email/password POST /login 登录。

        Args:
            session: requests.Session 对象（与 ZLibraryClient 共享）
            base_url: Z-Library 基础 URL

        Returns:
            True 表示登录成功
        """
        with self._lock:
            account = self._get_current_account_unsafe()
            if not account:
                return False

        # 方式1: 用保存的 cookie 登录
        cookies = account.get("cookies", [])
        if cookies:
            self._load_cookies_to_session(session, base_url)
            if self._check_login_status(session, base_url):
                with self._lock:
                    self._logged_in = True
                    account["last_used"] = datetime.now().isoformat()
                    self._save_accounts()
                return True
            # cookie 失效，清除登录 cookie（保留 PoW）
            _clear_login_cookies(session)

        # 方式2: POST /login 密码登录
        return self._login_with_password(session, base_url)

    def _login_with_password(self, session: requests.Session, base_url: str) -> bool:
        """用 email/password 登录（内部方法）"""
        with self._lock:
            account = self._get_current_account_unsafe()
            if not account:
                return False

        login_url = urljoin(base_url, "/login")
        login_data = {
            "email": account["email"],
            "password": account["password"],
            "site_mode": "books",
            "action": "login",
            "submit": "true",
            "redirectUrl": "",
        }

        try:
            resp = session.post(
                login_url,
                data=login_data,
                headers=DEFAULT_HEADERS,
                timeout=REQUEST_TIMEOUT,
                allow_redirects=True,
            )
            if resp.status_code != 200:
                return False

            text = resp.text
            if not any(ind in text.lower() for ind in LOGIN_INDICATORS):
                return False

            with self._lock:
                self._logged_in = True
                account["last_used"] = datetime.now().isoformat()
                # 保存新获取的 cookie
                self._save_session_cookies(session)
                self._save_accounts()
            return True
        except requests.RequestException:
            return False

    def switch_account(self) -> bool:
        """
        切换到下一个可用账号（循环切换）

        策略：
        1. 从当前账号的下一个开始，循环查找 downloads_today < limit 的账号
        2. 找到则切换到该账号
        3. 如果所有账号都达到限制，自动重置所有计数并回到第一个账号
        4. 如果只有一个账号，重置其计数后返回 True

        Returns:
            True 表示切换成功，False 表示无账号
        """
        with self._lock:
            if not self.accounts:
                return False

            total = len(self.accounts)

            # 查找下一个未达限制的账号（循环查找）
            for offset in range(1, total + 1):
                idx = (self.current_index + offset) % total
                acc = self.accounts[idx]
                if acc.get("downloads_today", 0) < REGISTERED_USER_DAILY_LIMIT:
                    old_email = self.accounts[self.current_index].get("email", "?")
                    self.current_index = idx
                    self._logged_in = False
                    new_email = acc.get("email", "?")
                    logger.info(
                        f"Account switched: {old_email} -> {new_email} "
                        f"(downloads: {acc.get('downloads_today', 0)}/{REGISTERED_USER_DAILY_LIMIT})"
                    )
                    return True

            # 所有账号都达到限制，自动重置计数并回到第一个
            logger.warning(
                f"All {total} accounts reached daily limit, auto-resetting counts"
            )
            for acc in self.accounts:
                acc["downloads_today"] = 0
            self.current_index = 0
            self._logged_in = False
            self._save_accounts()
            logger.info(f"Reset complete, switched to account: {self.accounts[0].get('email', '?')}")
            return True

    def record_download(self) -> None:
        """记录一次下载（线程安全）"""
        with self._lock:
            account = self._get_current_account_unsafe()
            if account:
                account["downloads_today"] = account.get("downloads_today", 0) + 1
                count = account["downloads_today"]
                email = account.get("email", "?")
                self._save_accounts()
                logger.info(
                    f"Download recorded: {email} "
                    f"({count}/{REGISTERED_USER_DAILY_LIMIT})"
                )

    def is_limit_reached(self) -> bool:
        """检查当前账号是否已达到下载限制"""
        with self._lock:
            account = self._get_current_account_unsafe()
            if not account:
                return False
            return account.get("downloads_today", 0) >= REGISTERED_USER_DAILY_LIMIT

    def reset_daily_counts(self) -> None:
        """重置所有账号的当日下载计数"""
        with self._lock:
            for acc in self.accounts:
                acc["downloads_today"] = 0
            self._save_accounts()

    def add_account(self, email: str, password: str, cookies: list = None) -> None:
        """添加新账号（线程安全）"""
        with self._lock:
            self.accounts.append({
                "email": email,
                "password": password,
                "cookies": cookies or [],
                "downloads_today": 0,
                "last_used": "",
            })
            self._save_accounts()

    def get_status(self) -> dict:
        """获取账号管理器状态信息（线程安全）"""
        with self._lock:
            current = self._get_current_account_unsafe()
            return {
                "total_accounts": len(self.accounts),
                "current_index": self.current_index,
                "current_email": current["email"] if current else None,
                "current_downloads": current.get("downloads_today", 0) if current else 0,
                "daily_limit": REGISTERED_USER_DAILY_LIMIT,
                "logged_in": self._logged_in,
                "accounts": [
                    {
                        "email": acc["email"],
                        "downloads_today": acc.get("downloads_today", 0),
                        "last_used": acc.get("last_used", ""),
                        "has_cookies": len(acc.get("cookies", [])) > 0,
                    }
                    for acc in self.accounts
                ],
            }
