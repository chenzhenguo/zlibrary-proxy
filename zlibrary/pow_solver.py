# -*- coding: utf-8 -*-
"""
PoW（工作量证明）挑战求解器

Z-Library 镜像站在首次访问时会返回一个 "Checking your browser..." 挑战页，
要求客户端完成 SHA1 工作量证明后才能访问真实内容。

本模块全程在 Python 后端完成求解，前端用户完全无感知。
求解后的 cookie 存入 requests.Session，后续请求自动复用。

PoW 算法（已逆向验证）：
1. 挑战页包含 40 字符 hex nonce
2. n1 = int(nonce[0], 16) 确定检查位置
3. 找到 i 使 SHA1(nonce + str(i)) 的第 n1 字节 == 0xb0 且第 n1+1 字节 == 0x0b
4. 设置 cookie：c_token = nonce + str(i)，c_time = 计算耗时
"""

import hashlib
import re
import time
from typing import Dict

from .config import (
    CHALLENGE_KEYWORDS,
    CHALLENGE_MAX_SIZE,
    CHALLENGE_TITLE,
)


# 目标字节条件（从 JS 逆向得到，固定值）
_TARGET_BYTE_1 = 0xB0
_TARGET_BYTE_2 = 0x0B

# 从挑战页 HTML 中提取 40 字符 hex nonce 的正则
# 挑战页 JS 中 nonce 通常以 'XXXXXXXX...' 格式出现
_NONCE_PATTERN = re.compile(r"'([0-9A-Fa-f]{40})'")


def extract_nonce(challenge_html: str) -> str:
    """
    从挑战页 HTML 中提取 nonce（40 字符十六进制字符串）

    Args:
        challenge_html: 挑战页 HTML 内容

    Returns:
        40 字符 hex nonce 字符串

    Raises:
        ValueError: 无法从 HTML 中提取 nonce 时抛出
    """
    match = _NONCE_PATTERN.search(challenge_html)
    if not match:
        raise ValueError("Cannot extract nonce from challenge page")
    return match.group(1)


def solve_pow(nonce: str) -> Dict[str, str]:
    """
    求解工作量证明

    算法：
    1. n1 = int(nonce[0], 16) 确定检查位置
    2. 递增 i，计算 SHA1(nonce + str(i))
    3. 检查第 n1 字节 == 0xb0 且第 n1+1 字节 == 0x0b
    4. 找到后返回 cookie 字典

    Args:
        nonce: 40 字符 hex nonce 字符串

    Returns:
        包含 c_token 和 c_time 的 cookie 字典
    """
    n1 = int(nonce[0], 16)  # 索引位置由 nonce 首字符决定
    start = time.time()
    i = 0

    while True:
        # 计算 SHA1(nonce + str(i))
        digest = hashlib.sha1((nonce + str(i)).encode()).digest()
        # 检查目标字节条件
        if digest[n1] == _TARGET_BYTE_1 and digest[n1 + 1] == _TARGET_BYTE_2:
            break
        i += 1

    elapsed = round(time.time() - start, 3)
    return {"c_token": nonce + str(i), "c_time": str(elapsed)}


def solve_challenge(challenge_html: str) -> Dict[str, str]:
    """
    完整流程：从挑战页 HTML 提取 nonce + 求解 PoW

    Args:
        challenge_html: 挑战页 HTML 内容

    Returns:
        包含 c_token 和 c_time 的 cookie 字典

    Raises:
        ValueError: 无法提取 nonce 时抛出
    """
    nonce = extract_nonce(challenge_html)
    return solve_pow(nonce)


def is_challenge_page(html: str) -> bool:
    """
    检测给定 HTML 是否为 PoW 挑战页

    判断依据（避免正常页面误判）：
    1. 页面标题包含 "Checking your browser"（最可靠）
    2. 或页面内容很小（< 15KB）且包含挑战页关键词

    Args:
        html: 待检测的 HTML 内容

    Returns:
        True 表示是挑战页
    """
    if not html:
        return False

    # 方法1：检查页面标题（最可靠）
    if CHALLENGE_TITLE.lower() in html.lower():
        return True

    # 方法2：小页面 + 挑战页关键词（避免大页面中的关键词误判）
    if len(html) < CHALLENGE_MAX_SIZE:
        html_lower = html.lower()
        return any(kw in html_lower for kw in CHALLENGE_KEYWORDS)

    return False
