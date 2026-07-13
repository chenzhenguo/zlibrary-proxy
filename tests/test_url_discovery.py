# -*- coding: utf-8 -*-
"""
URL 发现与健康检测模块的测试类

测试内容包括：
- 从 README HTML 提取 URL 列表
- URL 过滤规则
- 缓存加载/保存
- 缓存过期判断
- 健康检测（mock requests）
- 自动切换逻辑
- GitHub 获取失败时使用旧缓存
"""

import json
import os
import sys
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

# 将项目根目录加入路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from zlibrary import url_discovery


class UrlDiscoveryTest(unittest.TestCase):
    """URL 发现模块测试"""

    # 模拟 GitHub README 内容（包含多种链接类型）
    MOCK_README = """
    <h2>Z-library，官方Z-lib镜像网址及入口</h2>
    <p>zlibrary最新国内入口：<a href="https://z-lib.su/">https://z-lib.su/</a>（可用）</p>
    <p>zlibrary最新镜像地址：<a href="https://z-lib.su/">https://z-lib.su/</a>（可用）</p>
    <p>客户端：<a href="https://ztsg.pages.dev/">夸克网盘分享</a></p>
    <p>一键访问：<a href="https://wangpanziyuan.pages.dev/">网盘资源</a></p>
    <p>zlibrary官网入口：<a href="https://zh.z-library.sk">https://zh.z-library.sk</a></p>
    <p>zlibrary官网入口：<a href="https://zh.z-lib.gd/">https://zh.z-lib.gd/</a></p>
    <p>2026电子书网站：<a href="https://appxiazai.pages.dev/">https://appxiazai.pages.dev/</a></p>
    """

    def setUp(self):
        """每个测试前清理缓存文件"""
        if os.path.exists(url_discovery.CACHE_FILE):
            os.remove(url_discovery.CACHE_FILE)

    def tearDown(self):
        """每个测试后清理缓存文件"""
        if os.path.exists(url_discovery.CACHE_FILE):
            os.remove(url_discovery.CACHE_FILE)

    def test_extract_urls_from_readme(self):
        """测试从 README HTML 提取 URL 列表"""
        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.text = self.MOCK_README
            mock_resp.status_code = 200
            mock_resp.raise_for_status = MagicMock()
            mock_get.return_value = mock_resp

            urls = url_discovery.fetch_urls_from_github()

            # 应该提取到 3 个 Z-Library 镜像链接（去重后）
            self.assertEqual(len(urls), 3)
            self.assertIn("https://z-lib.su/", urls)
            self.assertIn("https://zh.z-library.sk", urls)
            self.assertIn("https://zh.z-lib.gd/", urls)

    def test_filter_exclude_non_mirror_links(self):
        """测试 URL 过滤规则：排除 pages.dev 等非镜像链接"""
        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.text = self.MOCK_README
            mock_resp.status_code = 200
            mock_resp.raise_for_status = MagicMock()
            mock_get.return_value = mock_resp

            urls = url_discovery.fetch_urls_from_github()

            # pages.dev 链接应被排除
            for url in urls:
                self.assertNotIn("pages.dev", url)
                self.assertNotIn("wangpanziyuan", url)
                self.assertNotIn("appxiazai", url)

    def test_cache_save_and_load(self):
        """测试缓存保存与加载"""
        test_urls = ["https://z-lib.su/", "https://zh.z-library.sk"]
        url_discovery.save_cache(test_urls, current_index=1)

        cache = url_discovery.load_cache()
        self.assertIsNotNone(cache)
        self.assertEqual(cache["urls"], test_urls)
        self.assertEqual(cache["current_index"], 1)
        self.assertIn("last_update", cache)

    def test_cache_expired(self):
        """测试缓存过期判断（超过 24 小时）"""
        # 创建 25 小时前的缓存
        old_time = (datetime.now() - timedelta(hours=25)).isoformat()
        cache = {"urls": ["https://z-lib.su/"], "last_update": old_time, "current_index": 0}
        self.assertTrue(url_discovery.is_cache_expired(cache))

    def test_cache_not_expired(self):
        """测试缓存未过期（1 小时内）"""
        recent_time = (datetime.now() - timedelta(hours=1)).isoformat()
        cache = {"urls": ["https://z-lib.su/"], "last_update": recent_time, "current_index": 0}
        self.assertFalse(url_discovery.is_cache_expired(cache))

    def test_health_check_success(self):
        """测试健康检测成功（200 + 包含 Z-Library 特征词）"""
        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.text = "<html><body>Z-Library - the world's largest e-book library</body></html>"
            mock_get.return_value = mock_resp

            result = url_discovery.health_check("https://z-lib.su/")
            self.assertTrue(result)

    def test_health_check_wrong_status(self):
        """测试健康检测失败（非 200/503 状态码）"""
        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 404
            mock_resp.text = "Not Found"
            mock_get.return_value = mock_resp

            result = url_discovery.health_check("https://z-lib.su/")
            self.assertFalse(result)

    def test_health_check_503_challenge_page(self):
        """测试健康检测成功（503 + PoW 挑战页特征词）"""
        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 503
            mock_resp.text = "<html><title>Checking your browser...</title>c_token=xxx</html>"
            mock_get.return_value = mock_resp

            result = url_discovery.health_check("https://z-lib.su/")
            self.assertTrue(result)

    def test_health_check_no_keywords(self):
        """测试健康检测失败（200 但无 Z-Library 特征词）"""
        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.text = "<html><body>Some random website</body></html>"
            mock_get.return_value = mock_resp

            result = url_discovery.health_check("https://example.com/")
            self.assertFalse(result)

    def test_health_check_timeout(self):
        """测试健康检测超时"""
        import requests as req
        with patch("requests.get", side_effect=req.RequestException("Timeout")):
            result = url_discovery.health_check("https://z-lib.su/")
            self.assertFalse(result)

    def test_get_available_urls_from_cache(self):
        """测试从有效缓存获取 URL 列表"""
        recent_time = datetime.now().isoformat()
        test_urls = ["https://z-lib.su/", "https://zh.z-library.sk"]
        url_discovery.save_cache(test_urls, 0)

        # 不应调用 GitHub
        with patch("zlibrary.url_discovery.fetch_urls_from_github") as mock_fetch:
            urls = url_discovery.get_available_urls()
            self.assertEqual(urls, test_urls)
            mock_fetch.assert_not_called()

    def test_get_available_urls_github_fallback(self):
        """测试 GitHub 不可达时使用旧缓存"""
        old_time = (datetime.now() - timedelta(hours=48)).isoformat()
        cache = {"urls": ["https://old-url.example/"], "last_update": old_time, "current_index": 0}
        with open(url_discovery.CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f)

        # GitHub 请求失败时应降级使用旧缓存
        import requests as req
        with patch("zlibrary.url_discovery.fetch_urls_from_github", side_effect=req.RequestException("Network error")):
            urls = url_discovery.get_available_urls()
            self.assertEqual(urls, ["https://old-url.example/"])

    def test_get_best_url_health_check(self):
        """测试 get_best_url 健康检测和自动切换"""
        test_urls = ["https://z-lib.su/", "https://zh.z-library.sk"]
        url_discovery.save_cache(test_urls, 0)

        # 第一个 URL 不可用，第二个可用
        def mock_health(url, timeout=10):
            return url == "https://zh.z-library.sk"

        with patch("zlibrary.url_discovery.health_check", side_effect=mock_health):
            best = url_discovery.get_best_url()
            self.assertEqual(best, "https://zh.z-library.sk")

    def test_get_best_url_all_unavailable_fallback(self):
        """测试所有 URL 健康检测失败时降级返回第一个 URL"""
        test_urls = ["https://z-lib.su/", "https://zh.z-library.sk"]
        url_discovery.save_cache(test_urls, 0)

        with patch("zlibrary.url_discovery.health_check", return_value=False):
            best = url_discovery.get_best_url()
            # 降级返回第一个 URL
            self.assertEqual(best, "https://z-lib.su/")

    def test_mark_url_unavailable(self):
        """测试标记 URL 不可用后切换索引"""
        test_urls = ["https://z-lib.su/", "https://zh.z-library.sk", "https://zh.z-lib.gd/"]
        url_discovery.save_cache(test_urls, 0)

        url_discovery.mark_url_unavailable("https://z-lib.su/")

        cache = url_discovery.load_cache()
        self.assertEqual(cache["current_index"], 1)

    def test_get_status_info(self):
        """测试获取状态信息"""
        test_urls = ["https://z-lib.su/", "https://zh.z-library.sk"]
        url_discovery.save_cache(test_urls, 0)

        status = url_discovery.get_status_info()
        self.assertEqual(status["urls"], test_urls)
        self.assertEqual(status["current_url"], "https://z-lib.su/")
        self.assertIn("last_update", status)
        self.assertFalse(status["cache_expired"])


if __name__ == "__main__":
    unittest.main()
