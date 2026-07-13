# -*- coding: utf-8 -*-
"""
Z-Library HTTP 客户端

封装所有对 Z-Library 镜像站的请求，整合以下功能：
- URL 自动发现与切换（url_discovery 模块）
- PoW 挑战求解与 Cookie 复用（pow_solver 模块）
- 搜索结果解析（parser 模块）
- 下载 URL 获取与流式下载

线程安全：
- Client 实例可多线程共享
- requests.Session 是线程安全的（每个请求独立连接）
- PoW 状态由客户端锁保护，避免重复求解

Cookie 复用机制：
- requests.Session 自动管理 cookie jar
- PoW 求解后 cookie 持久存在于 Session 中
- 所有后续请求自动携带 cookie，无需重复求解
"""

import logging
import threading
from typing import List, Optional, Tuple
from urllib.parse import urljoin

import requests

from . import url_discovery
from .config import (
    DEFAULT_HEADERS,
    DOWNLOAD_CHUNK_SIZE,
    DOWNLOAD_TIMEOUT,
    REQUEST_TIMEOUT,
    AllAccountsExhaustedError,
    AllURLsUnavailableError,
    DailyLimitReachedError,
    LoginRequiredError,
    ZLibError,
)
from .pow_solver import is_challenge_page, solve_challenge
from .parser import Book, parse_book_detail, parse_books
from .account_manager import AccountManager

logger = logging.getLogger(__name__)


# ============ 错误类型 ============

class DownloadBlockedError(ZLibError):
    """下载被限制（限流或需登录）"""
    pass


# ============ 工具函数 ============

def _is_limit_response(resp: requests.Response) -> bool:
    """检查响应是否为下载限制页"""
    if resp.status_code != 200:
        return False
    text = resp.text.lower()
    if "daily limit" in text:
        return True
    if "limit" in text and "download" in text:
        return True
    if "download limit reached" in text:
        return True
    return False


def _is_login_required(resp: requests.Response) -> bool:
    """检查响应是否需要登录"""
    if resp.status_code != 200:
        return False
    text = resp.text.lower()
    if "sign in" in text or "log in" in text:
        # 进一步验证：是否有 login 链接或登录表单
        if "action=login" in text or 'id="loginForm"' in text:
            return True
    return False


# ============ ZLibraryClient ============

class ZLibraryClient:
    """
    Z-Library HTTP 客户端

    内部维护 requests.Session 与 PoW cookie，支持 URL 自动切换。
    全局共享一个实例即可，Session 会自动复用 cookie。

    线程安全：可从多线程并发调用，PoW 状态由内部锁保护。
    """

    def __init__(self, account_manager: Optional[AccountManager] = None):
        """初始化客户端"""
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        self.base_url: Optional[str] = None
        self._pow_solved: bool = False
        # 保护 _pow_solved 和 base_url 的修改
        self._pow_lock = threading.Lock()
        self.account_manager = account_manager or AccountManager()

    # ============ 基础 URL 管理 ============

    def _get_base_url(self) -> str:
        """
        获取当前可用的 Z-Library 基础 URL

        若 base_url 已设置且未标记不可用，直接返回；
        否则调用 url_discovery.get_best_url() 获取最佳 URL。
        """
        if self.base_url:
            return self.base_url

        with self._pow_lock:
            if not self.base_url:
                self.base_url = url_discovery.get_best_url()
                self._pow_solved = False  # URL 变了，PoW 需要重新求解
        return self.base_url

    # ============ PoW 管理 ============

    def _ensure_access(self) -> None:
        """
        确保 PoW 挑战已解决

        若 _pow_solved 为 False，请求首页检测挑战页并求解 PoW，
        将 cookie 存入 Session，标记为 True。
        后续调用直接跳过，实现 cookie 复用。
        """
        with self._pow_lock:
            if self._pow_solved:
                return

        base_url = self._get_base_url()
        resp = self.session.get(base_url, timeout=REQUEST_TIMEOUT)

        # 更新 base_url 为重定向后的真实 URL
        with self._pow_lock:
            if resp.url and resp.url != base_url:
                self.base_url = resp.url.rstrip("/")
                base_url = self.base_url

        if is_challenge_page(resp.text):
            try:
                cookies = solve_challenge(resp.text)
                self.session.cookies.update(cookies)
            except ValueError as e:
                logger.warning(f"Failed to solve PoW: {e}")

        with self._pow_lock:
            self._pow_solved = True

    def _reset_pow(self) -> None:
        """重置 PoW 状态（切换 URL 或遇到挑战页时调用）"""
        with self._pow_lock:
            self._pow_solved = False

    # ============ 搜索 ============

    def search(self, query: str, page: int = 1) -> List[Book]:
        """
        搜索书籍

        流程：
        1. 确保 PoW 已解决
        2. GET /s/{query} 搜索
        3. 若返回挑战页，重新求解并重试
        4. 若当前 URL 异常，切换到下一个 URL 重试
        5. 解析搜索结果返回 Book 列表

        Args:
            query: 搜索关键词
            page: 页码（从 1 开始）

        Returns:
            Book 对象列表

        Raises:
            AllURLsUnavailableError: 所有 URL 不可用时抛出
        """
        urls = url_discovery.get_available_urls()
        if not urls:
            raise AllURLsUnavailableError("No URLs available")

        last_error = None
        for url in urls:
            try:
                # 仅在 PoW 未求解时才设置 base_url（避免覆盖已重定向的 URL）
                with self._pow_lock:
                    if not self._pow_solved:
                        self.base_url = url
                self._ensure_access()

                search_url = f"{self.base_url}/s/{query}"
                params = {"page": page} if page > 1 else None

                resp = self.session.get(search_url, params=params, timeout=REQUEST_TIMEOUT)

                # 若返回挑战页，重新求解并重试
                if is_challenge_page(resp.text):
                    self._handle_challenge_response(resp)
                    resp = self.session.get(search_url, params=params, timeout=REQUEST_TIMEOUT)

                if resp.status_code == 200 and not is_challenge_page(resp.text):
                    return parse_books(resp.text)

            except Exception as e:
                logger.warning(f"Search failed on {url}: {e}")
                last_error = e
                url_discovery.mark_url_unavailable(url)
                self._reset_pow()
                continue

        raise AllURLsUnavailableError(
            f"All URLs unavailable. Last error: {last_error}"
        )

    def _handle_challenge_response(self, resp: requests.Response) -> None:
        """处理 PoW 挑战响应：求解并更新 Session"""
        try:
            cookies = solve_challenge(resp.text)
            self.session.cookies.update(cookies)
            with self._pow_lock:
                self._pow_solved = True
        except ValueError as e:
            logger.warning(f"Failed to solve PoW on retry: {e}")
            self._reset_pow()

    # ============ 登录 ============

    def _ensure_logged_in(self) -> None:
        """
        确保已使用 Z-Library 账号登录

        如果账号管理器中有可用账号且当前账号未登录，
        则使用当前账号登录。登录失败时自动切换到下一个账号重试。
        """
        if not self.account_manager.has_accounts():
            return
        if self.account_manager.is_logged_in():
            return

        base_url = self._get_base_url()
        max_attempts = len(self.account_manager.accounts)
        for _ in range(max_attempts):
            if self.account_manager.login(self.session, base_url):
                return
            if not self.account_manager.switch_account():
                break

    # ============ 下载 ============

    def get_download_url(self, download_path: str) -> str:
        """
        获取下载 URL（302 重定向的 Location）

        集成账号切换逻辑：
        1. 登录（如有可用账号）
        2. 遇到下载限制或需登录时，自动切换到下一个账号并重试
        3. 最多尝试 len(accounts) 次，避免无限循环
        4. 所有账号都失败后抛出异常

        Args:
            download_path: 下载路径（如 /dl/J97YlW8rgx）

        Returns:
            CDN 下载 URL 字符串

        Raises:
            AllAccountsExhaustedError: 所有账号都失败
            DailyLimitReachedError: 达到下载限制且无可用账号
            AllURLsUnavailableError: 所有 URL 不可用
            LoginRequiredError: 无账号且需要登录
        """
        self._ensure_access()
        self._ensure_logged_in()
        base_url = self._get_base_url()
        url = urljoin(base_url, download_path)

        # 无账号场景：直接尝试，失败则要求登录
        if not self.account_manager.has_accounts():
            resp = self._try_get_download_redirect(url)
            if resp is not None:
                return resp
            logger.error("No accounts configured. Download requires login.")
            raise LoginRequiredError(
                "No accounts configured. "
                "Please mount accounts.json to /app/data/accounts.json. "
                "See README for details."
            )

        # 有账号场景：循环尝试每个账号
        max_attempts = len(self.account_manager.accounts)
        for attempt in range(max_attempts):
            # 确保当前账号已登录
            if not self.account_manager.is_logged_in():
                login_ok = self.account_manager.login(self.session, base_url)
                if not login_ok:
                    logger.warning(
                        f"Account login failed (attempt {attempt + 1}/{max_attempts}), "
                        f"switching to next..."
                    )
                    if not self.account_manager.switch_account():
                        break
                    from .account_manager import _clear_login_cookies
                    _clear_login_cookies(self.session)
                    continue

            # 尝试获取下载链接
            resp = self._try_get_download_redirect(url)
            if resp is not None:
                self.account_manager.record_download()
                return resp

            # 当前账号失败（限制/需登录），切换到下一个
            logger.info(f"Download attempt {attempt + 1}/{max_attempts} failed, switching account...")
            if not self.account_manager.switch_account():
                # switch_account 返回 False 仅当无账号
                break

            # 清除旧登录 cookie，保留 PoW cookie
            from .account_manager import _clear_login_cookies
            _clear_login_cookies(self.session)

        raise AllAccountsExhaustedError(
            f"Failed to download after trying {max_attempts} accounts. "
            f"All accounts may have expired cookies or invalid credentials. "
            f"URL: {url}"
        )

    def _try_get_download_redirect(self, url: str) -> Optional[str]:
        """
        尝试获取下载重定向 URL

        Returns:
            CDN URL 字符串，失败返回 None
        """
        try:
            resp = self.session.get(url, allow_redirects=False, timeout=REQUEST_TIMEOUT)

            if resp.status_code == 302:
                location = resp.headers.get("Location", "")
                if location:
                    return location

            if resp.status_code == 200:
                if _is_limit_response(resp):
                    return None  # 触发账号切换
                if _is_login_required(resp):
                    return None  # 触发账号切换

        except requests.RequestException as e:
            logger.warning(f"Download request failed: {e}")

        return None

    # ============ 流式下载 ============

    def stream_download(self, cdn_url: str) -> Tuple:
        """
        流式获取 CDN 文件

        使用 stream=True 分块下载，避免大文件占满内存。

        Args:
            cdn_url: CDN 下载 URL

        Returns:
            (iter_content 生成器, headers 字典) 元组

        Raises:
            ZLibError: 下载失败时抛出
        """
        try:
            resp = self.session.get(cdn_url, stream=True, timeout=DOWNLOAD_TIMEOUT)
            resp.raise_for_status()
            return resp.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE), resp.headers
        except requests.RequestException as e:
            raise ZLibError(f"Download failed: {e}") from e

    # ============ 详情页 ============

    def get_book_detail(self, book_path: str) -> Book:
        """
        获取书籍详情页信息

        Args:
            book_path: 书籍详情页路径（如 /book/xxx.html）

        Returns:
            Book 对象
        """
        self._ensure_access()
        base_url = self._get_base_url()
        url = urljoin(base_url, book_path)

        resp = self.session.get(url, timeout=REQUEST_TIMEOUT)

        # 若返回挑战页，重新求解并重试
        if is_challenge_page(resp.text):
            self._handle_challenge_response(resp)
            resp = self.session.get(url, timeout=REQUEST_TIMEOUT)

        if resp.status_code == 200:
            return parse_book_detail(resp.text)

        raise ZLibError(f"Failed to get book detail: status {resp.status_code}")
