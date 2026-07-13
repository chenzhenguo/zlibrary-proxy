# -*- coding: utf-8 -*-
"""
Z-Library 共享配置

集中管理所有模块共用的配置：
- HTTP 请求头
- 超时时间
- 账号存储路径
- 登录/PoW 检测关键词
- 限流/重试参数

从环境变量读取敏感配置（密码、密钥），避免硬编码。
"""
import os
from pathlib import Path


# ============ HTTP 配置 ============

# 模拟浏览器的请求头
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# 请求超时（秒）
REQUEST_TIMEOUT = 15
DOWNLOAD_TIMEOUT = 30

# 下载分块大小
DOWNLOAD_CHUNK_SIZE = 8192


# ============ 账号配置 ============

# 注册用户的每日下载限制（Z-Library 注册用户通常 10 次/天）
REGISTERED_USER_DAILY_LIMIT = 10

# 账号文件路径：环境变量 > /app/data/accounts.json > 项目根目录/accounts.json
_PROJECT_ROOT = Path(__file__).parent.parent
_DEFAULT_ACCOUNTS = _PROJECT_ROOT / "data" / "accounts.json"
_FALLBACK_ACCOUNTS = _PROJECT_ROOT / "accounts.json"

def _resolve_accounts_file() -> Path:
    """按优先级查找 accounts.json"""
    env_val = os.environ.get("ZLIB_ACCOUNTS_FILE")
    if env_val:
        return Path(env_val)
    if _DEFAULT_ACCOUNTS.exists():
        return _DEFAULT_ACCOUNTS
    if _FALLBACK_ACCOUNTS.exists():
        return _FALLBACK_ACCOUNTS
    return _DEFAULT_ACCOUNTS  # 返回默认路径（即使不存在，_load_accounts 会处理）

ACCOUNTS_FILE = _resolve_accounts_file()


# ============ PoW / 登录检测 ============

# PoW 挑战页特征
CHALLENGE_TITLE = "Checking your browser"
CHALLENGE_KEYWORDS = ("challenge-form", "pow_challenge")
CHALLENGE_MAX_SIZE = 15000

# PoW 相关 cookie 名称（账号切换时不能清除）
POW_COOKIE_NAMES = frozenset({"c_token", "c_date"})

# 登录成功标志：检测 remix_userid cookie（比检查 HTML 文本更可靠）
LOGIN_COOKIE_NAME = "remix_userid"

# 登录后页面特征（备用检测）
LOGIN_INDICATORS = ("log out", "my books", "profileMenu")


# ============ 重试/熔断配置 ============

# 网络重试：最大次数、退避策略
NETWORK_RETRY_MAX = 3
NETWORK_RETRY_BACKOFF = 1.5      # 指数退避基数
NETWORK_RETRY_MIN_WAIT = 1       # 最小等待秒数
NETWORK_RETRY_MAX_WAIT = 10      # 最大等待秒数

# URL 熔断：连续失败 N 次后标记为不可用
URL_CIRCUIT_BREAK_THRESHOLD = 3

# 账号登录：每个账号最多重试次数
LOGIN_RETRY_PER_ACCOUNT = 2


# ============ 错误类型 ============

class ZLibError(Exception):
    """Z-Library 基础异常"""
    pass


class AllAccountsExhaustedError(ZLibError):
    """所有账号都用尽（下载限制或登录失败）"""
    pass


class AllURLsUnavailableError(ZLibError):
    """所有镜像都不可用"""
    pass


class DailyLimitReachedError(ZLibError):
    """今日下载次数已达上限"""
    pass


class LoginRequiredError(ZLibError):
    """需要登录才能执行此操作"""
    pass


# ============ 工具函数 ============

def load_secret(env_key: str, default: str = None, required: bool = False) -> str:
    """
    从环境变量加载敏感配置

    Args:
        env_key: 环境变量名
        default: 默认值（如果环境变量未设置）
        required: 是否必填（必填但未设置时抛异常）

    Returns:
        配置值

    Raises:
        RuntimeError: 必填配置缺失时
    """
    value = os.environ.get(env_key, default)
    if required and not value:
        raise RuntimeError(
            f"Required environment variable {env_key} is not set. "
            f"Please set it in .env or system environment."
        )
    return value
