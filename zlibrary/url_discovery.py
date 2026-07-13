# -*- coding: utf-8 -*-
"""
URL 发现与健康检测模块

从 GitHub README 自动获取最新 Z-Library 入口地址，
支持 24 小时缓存、多链接自动切换和健康检测。

线程安全：所有缓存读写用 threading.Lock 保护。
"""

import json
import os
import re
import threading
import time
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urlparse

import requests

from .config import DEFAULT_HEADERS, REQUEST_TIMEOUT

# GitHub README 原始内容地址
GITHUB_README_URL = (
    "https://raw.githubusercontent.com/z-libraryopp/"
    "z-libraryopp.github.io/main/README.md"
)

# 缓存文件路径（与本文件同目录）
CACHE_FILE = os.path.join(os.path.dirname(__file__), "url_cache.json")

# 缓存过期时间（小时）
CACHE_TTL_HOURS = 24

# 健康检测超时时间（秒）
HEALTH_CHECK_TIMEOUT = 10

# Z-Library 镜像域名关键词（用于过滤 README 中的链接）
ZLIB_DOMAIN_KEYWORDS = ["z-lib", "zlibrary", "zlib", "z-library"]

# 需要排除的域名关键词
EXCLUDE_DOMAINS = ["pages.dev", "wangpanziyuan", "appxiazai", "telegram", "mastodon"]

# 硬编码备用 URL（无缓存且 GitHub 不可达时使用）
FALLBACK_URLS = ["https://z-lib.su/", "https://zh.z-library.sk", "https://zh.z-lib.gd/"]

# 模块级锁，保护缓存读写
_cache_lock = threading.RLock()


def fetch_urls_from_github() -> list:
    """
    从 GitHub README 提取所有 Z-Library 入口链接

    Returns:
        URL 字符串列表，按 README 中出现的顺序排列
    Raises:
        requests.RequestException: GitHub 请求失败时抛出
    """
    resp = requests.get(
        GITHUB_README_URL, headers=DEFAULT_HEADERS, timeout=REQUEST_TIMEOUT
    )
    resp.raise_for_status()
    text = resp.text

    # 用正则提取所有 href 中的 URL 和裸 URL
    # 匹配 <a href="https://...">格式
    href_pattern = re.compile(r'href=["\']?(https?://[^"\'\s>]+)', re.IGNORECASE)
    urls = href_pattern.findall(text)

    # 也匹配裸 URL（README 中可能有不在 href 中的）
    bare_pattern = re.compile(r'(https?://[^\s<>"\']+)', re.IGNORECASE)
    for match in bare_pattern.findall(text):
        if match not in urls:
            urls.append(match)

    # 过滤：保留 Z-Library 镜像域名，排除非镜像链接
    filtered = []
    seen = set()
    for url in urls:
        # 去除尾部斜杠后比较，避免重复
        normalized = url.rstrip("/")
        if normalized in seen:
            continue

        domain = urlparse(url).netloc.lower()

        # 排除非镜像域名
        if any(exc in domain for exc in EXCLUDE_DOMAINS):
            continue

        # 保留包含 Z-Library 关键词的域名
        if any(kw in domain for kw in ZLIB_DOMAIN_KEYWORDS):
            seen.add(normalized)
            filtered.append(url)

    return filtered


def load_cache() -> Optional[dict]:
    """
    加载本地缓存（线程安全）

    Returns:
        缓存字典，包含 urls、last_update、current_index；
        若缓存文件不存在或读取失败返回 None
    """
    with _cache_lock:
        if not os.path.exists(CACHE_FILE):
            return None
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None


def save_cache(urls: list, current_index: int = 0) -> None:
    """
    保存 URL 列表到本地缓存，记录当前时间（线程安全）

    Args:
        urls: URL 字符串列表
        current_index: 当前使用的 URL 索引
    """
    cache = {
        "urls": urls,
        "last_update": datetime.now().isoformat(),
        "current_index": current_index,
    }
    with _cache_lock:
        try:
            # 原子写入：tempfile + os.replace
            import tempfile
            fd, tmp_path = tempfile.mkstemp(
                dir=os.path.dirname(CACHE_FILE) or ".",
                prefix=".url_cache_", suffix=".tmp",
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(cache, f, ensure_ascii=False, indent=2)
                os.replace(tmp_path, CACHE_FILE)
            except Exception:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
        except IOError:
            pass  # 缓存写入失败不影响程序运行


def is_cache_expired(cache: dict) -> bool:
    """
    检查缓存是否超过 24 小时

    Args:
        cache: 缓存字典

    Returns:
        True 表示已过期或时间格式无效
    """
    try:
        last_update = datetime.fromisoformat(cache["last_update"])
        return datetime.now() - last_update > timedelta(hours=CACHE_TTL_HOURS)
    except (KeyError, ValueError, TypeError):
        return True


def get_available_urls() -> list:
    """
    获取可用 URL 列表（主入口函数）

    逻辑：
    1. 加载缓存
    2. 若缓存不存在或过期，从 GitHub 重新获取
    3. 若 GitHub 获取失败，使用旧缓存（即使过期）
    4. 返回 URL 列表

    Returns:
        URL 字符串列表
    """
    cache = load_cache()

    # 缓存有效且未过期，直接返回
    if cache and not is_cache_expired(cache) and cache.get("urls"):
        return cache["urls"]

    # 尝试从 GitHub 获取最新 URL
    try:
        urls = fetch_urls_from_github()
        if urls:
            # 获取成功，更新缓存
            current_index = cache.get("current_index", 0) if cache else 0
            save_cache(urls, current_index)
            return urls
    except requests.RequestException:
        pass  # GitHub 不可达，降级使用旧缓存

    # 降级：使用旧缓存（即使过期）
    if cache and cache.get("urls"):
        return cache["urls"]

    # 无缓存且 GitHub 不可达，返回硬编码的备用 URL
    return FALLBACK_URLS


def health_check(url: str, timeout: int = HEALTH_CHECK_TIMEOUT) -> bool:
    """
    检测某个 URL 是否可用

    Z-Library 首次访问会返回 503 状态码（PoW 挑战页），这是正常行为。
    因此健康检测接受 200 和 503 状态码，并检查内容是否包含
    Z-Library 特征词或 PoW 挑战页特征词。

    Args:
        url: 待检测的 URL
        timeout: 超时时间（秒）

    Returns:
        True 表示可用（200/503 + 包含 Z-Library 或挑战页特征词）
    """
    try:
        resp = requests.get(
            url, headers=DEFAULT_HEADERS, timeout=timeout, allow_redirects=True
        )
        # 200 = 正常页面，503 = PoW 挑战页（首次访问的正常行为）
        if resp.status_code not in (200, 503):
            return False
        # 检查页面是否包含 Z-Library 特征词或 PoW 挑战页特征词
        text = resp.text
        keywords = [
            "Z-Library", "z-bookcard", "z-library", "e-book",
            "Checking your browser", "c_token",  # PoW 挑战页特征词
        ]
        return any(kw in text for kw in keywords)
    except requests.RequestException:
        return False


def get_best_url() -> str:
    """
    获取最佳可用 URL（带健康检测和自动切换）

    逻辑：
    1. 获取 URL 列表
    2. 从当前索引开始，依次健康检测
    3. 返回第一个可用的 URL
    4. 若全部健康检测失败，降级返回第一个 URL（服务器可能暂时超时）
    5. 更新缓存中的 current_index

    Returns:
        可用的 URL 字符串
    """
    urls = get_available_urls()
    if not urls:
        raise RuntimeError("No URLs available")

    cache = load_cache()
    start_index = cache.get("current_index", 0) if cache else 0

    # 从当前索引开始遍历所有 URL（循环一圈）
    for offset in range(len(urls)):
        idx = (start_index + offset) % len(urls)
        url = urls[idx]
        if health_check(url):
            # 找到可用 URL，更新缓存索引
            save_cache(urls, idx)
            return url

    # 降级：所有健康检测都失败，返回第一个 URL（可能只是暂时超时）
    save_cache(urls, 0)
    return urls[0]


def mark_url_unavailable(url: str):
    """
    标记某个 URL 不可用，切换到下一个

    Args:
        url: 不可用的 URL
    """
    cache = load_cache()
    if not cache or not cache.get("urls"):
        return

    urls = cache["urls"]
    current_index = cache.get("current_index", 0)

    # 找到当前 URL 的索引，切换到下一个
    try:
        idx = urls.index(url)
        next_index = (idx + 1) % len(urls)
        save_cache(urls, next_index)
    except ValueError:
        pass  # URL 不在列表中，忽略


def get_status_info() -> dict:
    """
    获取当前 URL 发现状态信息（供 /status 路由使用）

    Returns:
        包含状态信息的字典
    """
    cache = load_cache()
    urls = get_available_urls()

    return {
        "urls": urls,
        "current_url": urls[cache["current_index"]] if cache and cache.get("current_index") is not None and cache["current_index"] < len(urls) else (urls[0] if urls else None),
        "last_update": cache.get("last_update") if cache else None,
        "cache_expired": is_cache_expired(cache) if cache else True,
        "github_readme_url": GITHUB_README_URL,
    }
