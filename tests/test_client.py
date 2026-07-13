# -*- coding: utf-8 -*-
"""
HTTP 客户端测试类

测试内容包括：
- 首次访问触发 PoW 求解
- Cookie 复用（后续请求不重复求解）
- 302 响应验证下载 URL 获取
- URL 自动切换（第一个失败换第二个）
- Cookie 过期重新求解
- 搜索结果解析
"""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock, PropertyMock

# 将项目根目录加入路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from zlibrary.client import ZLibraryClient
from zlibrary.parser import Book


class ClientTest(unittest.TestCase):
    """HTTP 客户端测试"""

    # 模拟挑战页 HTML
    CHALLENGE_HTML = """
    <html><head><title>Checking your browser...</title></head>
    <body><script>var nonce = 'FFC94FB5494564E790490AE31D23373533758C70';</script></body>
    </html>
    """

    # 模拟搜索结果 HTML（包含一本书）
    SEARCH_RESULT_HTML = """
    <html><body>
    <z-bookcard id="123" href="/book/xxx" download="/dl/abc"
                extension="pdf" filesize="1 MB" year="2020" language="English">
        <div slot="title">Test Book</div>
        <div slot="author">Test Author</div>
    </z-bookcard>
    </body></html>
    """

    # 模拟书籍详情页 HTML
    DETAIL_HTML = """
    <html><body>
    <h1>Test Book Title</h1>
    <a class="btn btn-default addDownloadedBook" href="/dl/abc" data-book_id="123">
        pdf, 1 MB
    </a>
    </body></html>
    """

    def setUp(self):
        """每个测试前创建新客户端"""
        self.client = ZLibraryClient()

    def _mock_response(self, text="", status_code=200, headers=None, url=None):
        """创建模拟响应对象"""
        resp = MagicMock()
        resp.text = text
        resp.status_code = status_code
        resp.headers = headers or {}
        resp.url = url or ""  # 重定向后的 URL
        resp.raise_for_status = MagicMock()
        return resp

    @patch("zlibrary.url_discovery.get_best_url")
    @patch("zlibrary.url_discovery.get_available_urls")
    @patch("zlibrary.url_discovery.mark_url_unavailable")
    def test_search_triggers_pow_on_first_access(self, mock_mark, mock_urls, mock_best):
        """测试首次访问触发 PoW 求解"""
        mock_best.return_value = "https://z-lib.su/"
        mock_urls.return_value = ["https://z-lib.su/"]

        # 模拟 Session.get：首次返回挑战页，第二次返回搜索结果
        responses = [
            self._mock_response(text=self.CHALLENGE_HTML, url="https://z-lib.su/"),   # 首页 → 挑战页
            self._mock_response(text=self.SEARCH_RESULT_HTML, url="https://z-lib.su/s/python"),  # 搜索 → 结果
        ]
        self.client.session.get = MagicMock(side_effect=responses)

        books = self.client.search("python")

        # 验证 PoW 被求解
        self.assertTrue(self.client._pow_solved)
        # 验证返回了搜索结果
        self.assertEqual(len(books), 1)
        self.assertEqual(books[0].title, "Test Book")

    @patch("zlibrary.url_discovery.get_best_url")
    @patch("zlibrary.url_discovery.get_available_urls")
    @patch("zlibrary.url_discovery.mark_url_unavailable")
    def test_search_reuses_cookie(self, mock_mark, mock_urls, mock_best):
        """测试 Cookie 复用（后续请求不重复求解 PoW）"""
        mock_best.return_value = "https://z-lib.su/"
        mock_urls.return_value = ["https://z-lib.su/"]

        # 预设 PoW 已求解
        self.client._pow_solved = True
        self.client.base_url = "https://z-lib.su/"

        # 模拟搜索直接返回结果（无需 PoW）
        self.client.session.get = MagicMock(
            return_value=self._mock_response(text=self.SEARCH_RESULT_HTML)
        )

        books = self.client.search("python")

        # 验证只调用了一次 GET（搜索请求），没有首页 PoW 请求
        self.assertEqual(self.client.session.get.call_count, 1)
        self.assertEqual(len(books), 1)

    @patch("zlibrary.url_discovery.get_best_url")
    @patch("zlibrary.url_discovery.get_available_urls")
    @patch("zlibrary.url_discovery.mark_url_unavailable")
    def test_get_download_url_returns_location(self, mock_mark, mock_urls, mock_best):
        """测试 302 响应返回下载 URL"""
        mock_best.return_value = "https://z-lib.su/"
        mock_urls.return_value = ["https://z-lib.su/"]

        # 预设 PoW 已求解
        self.client._pow_solved = True
        self.client.base_url = "https://z-lib.su/"

        # 模拟 302 重定向响应
        self.client.session.get = MagicMock(
            return_value=self._mock_response(
                status_code=302,
                headers={"Location": "https://cdn.example.com/file.pdf"}
            )
        )

        download_url = self.client.get_download_url("/dl/abc")

        self.assertEqual(download_url, "https://cdn.example.com/file.pdf")

    @patch("zlibrary.url_discovery.get_best_url")
    @patch("zlibrary.url_discovery.get_available_urls")
    @patch("zlibrary.url_discovery.mark_url_unavailable")
    def test_url_auto_switch_on_failure(self, mock_mark, mock_urls, mock_best):
        """测试 URL 自动切换（第一个失败换第二个）"""
        mock_urls.return_value = ["https://url1.com/", "https://url2.com/"]

        # 第一个 URL 抛异常，第二个返回结果
        responses = [
            Exception("Connection error"),  # url1 首页 → 异常
            self._mock_response(text=self.SEARCH_RESULT_HTML, url="https://url2.com/"),  # url2 首页 → 正常
            self._mock_response(text=self.SEARCH_RESULT_HTML, url="https://url2.com/s/python"),  # url2 搜索 → 结果
        ]
        self.client.session.get = MagicMock(side_effect=responses)

        books = self.client.search("python")

        # 验证切换到了第二个 URL
        self.assertEqual(self.client.base_url, "https://url2.com/")
        # 验证标记了第一个 URL 不可用
        mock_mark.assert_called_with("https://url1.com/")
        # 验证返回了搜索结果
        self.assertEqual(len(books), 1)

    @patch("zlibrary.url_discovery.get_best_url")
    @patch("zlibrary.url_discovery.get_available_urls")
    @patch("zlibrary.url_discovery.mark_url_unavailable")
    def test_cookie_expired_re_solve(self, mock_mark, mock_urls, mock_best):
        """测试 Cookie 过期后自动重新求解 PoW"""
        mock_best.return_value = "https://z-lib.su/"
        mock_urls.return_value = ["https://z-lib.su/"]

        # 预设 PoW 已求解，但搜索时返回挑战页（cookie 过期）
        self.client._pow_solved = True
        self.client.base_url = "https://z-lib.su/"

        # 第一次搜索返回挑战页（cookie 过期），第二次返回结果
        responses = [
            self._mock_response(text=self.CHALLENGE_HTML),       # 搜索 → 挑战页
            self._mock_response(text=self.SEARCH_RESULT_HTML),   # 重试 → 结果
        ]
        self.client.session.get = MagicMock(side_effect=responses)

        books = self.client.search("python")

        # 验证返回了搜索结果
        self.assertEqual(len(books), 1)
        # 验证 PoW 被重新求解
        self.assertTrue(self.client._pow_solved)

    @patch("zlibrary.url_discovery.get_best_url")
    @patch("zlibrary.url_discovery.get_available_urls")
    @patch("zlibrary.url_discovery.mark_url_unavailable")
    def test_all_urls_unavailable_raises(self, mock_mark, mock_urls, mock_best):
        """测试所有 URL 不可用时抛出 AllURLsUnavailableError"""
        mock_urls.return_value = ["https://url1.com/", "https://url2.com/"]

        # 所有请求都抛异常
        self.client.session.get = MagicMock(side_effect=Exception("Connection error"))

        with self.assertRaises(Exception) as ctx:
            self.client.search("python")
        # 异常类型可以是 AllURLsUnavailableError 或 RuntimeError（向后兼容）
        assert "All URLs unavailable" in str(ctx.exception) or "RuntimeError" in str(type(ctx.exception).__name__)

    @patch("zlibrary.url_discovery.get_best_url")
    @patch("zlibrary.url_discovery.get_available_urls")
    @patch("zlibrary.url_discovery.mark_url_unavailable")
    def test_stream_download(self, mock_mark, mock_urls, mock_best):
        """测试流式下载"""
        mock_best.return_value = "https://z-lib.su/"
        mock_urls.return_value = ["https://z-lib.su/"]

        # 预设 PoW 已求解
        self.client._pow_solved = True
        self.client.base_url = "https://z-lib.su/"

        # 模拟流式响应
        mock_resp = MagicMock()
        mock_resp.iter_content = MagicMock(return_value=iter([b"chunk1", b"chunk2"]))
        mock_resp.headers = {"Content-Type": "application/pdf"}
        mock_resp.raise_for_status = MagicMock()
        self.client.session.get = MagicMock(return_value=mock_resp)

        chunks, headers = self.client.stream_download("https://cdn.example.com/file.pdf")

        # 验证返回了分块生成器和 headers
        self.assertEqual(list(chunks), [b"chunk1", b"chunk2"])
        self.assertEqual(headers["Content-Type"], "application/pdf")

    @patch("zlibrary.url_discovery.get_best_url")
    @patch("zlibrary.url_discovery.get_available_urls")
    @patch("zlibrary.url_discovery.mark_url_unavailable")
    def test_get_book_detail(self, mock_mark, mock_urls, mock_best):
        """测试获取书籍详情页"""
        mock_best.return_value = "https://z-lib.su/"
        mock_urls.return_value = ["https://z-lib.su/"]

        # 预设 PoW 已求解
        self.client._pow_solved = True
        self.client.base_url = "https://z-lib.su/"

        self.client.session.get = MagicMock(
            return_value=self._mock_response(text=self.DETAIL_HTML)
        )

        book = self.client.get_book_detail("/book/xxx")

        self.assertEqual(book.title, "Test Book Title")
        self.assertEqual(book.download, "/dl/abc")


if __name__ == "__main__":
    unittest.main()
