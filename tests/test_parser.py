# -*- coding: utf-8 -*-
"""
HTML 解析器测试类

测试内容包括：
- 单本书解析（用真实 z-bookcard HTML）
- 多本书解析
- 空页面容错
- 缺失 slot 容错
- 书籍详情页解析
"""

import os
import sys
import unittest

# 将项目根目录加入路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from zlibrary.parser import parse_books, parse_book_detail, Book


class ParserTest(unittest.TestCase):
    """HTML 解析器测试"""

    # 真实 z-bookcard HTML 片段（来自搜索结果页）
    SINGLE_BOOK_HTML = """
    <html><body>
    <div class="book-item resItemBoxBooks">
        <z-bookcard id="122949529" isbn="B0134EWTSO"
                    href="/book/nJjNAqkpJg/python-learn-python-programming.html"
                    download="/dl/J97YlW8rgx"
                    extension="pdf" filesize="799 KB"
                    year="2015" language="English"
                    publisher="AZ Elite Publishing">
            <img data-src="https://example.com/cover.jpg">
            <div slot="title">PYTHON: Learn Python Programming in 90 minutes or Less!</div>
            <div slot="author">AZ Elite Publishing</div>
            <div slot="note"></div>
            <div slot="extend"></div>
        </z-bookcard>
    </div>
    </body></html>
    """

    # 多本书 HTML
    MULTI_BOOK_HTML = """
    <html><body>
    <z-bookcard id="1" href="/book/aaa" download="/dl/aaa"
                extension="pdf" filesize="1 MB" year="2020" language="English">
        <div slot="title">Book One</div>
        <div slot="author">Author A</div>
    </z-bookcard>
    <z-bookcard id="2" href="/book/bbb" download="/dl/bbb"
                extension="epub" filesize="2 MB" year="2021" language="Chinese">
        <div slot="title">Book Two</div>
        <div slot="author">Author B</div>
    </z-bookcard>
    <z-bookcard id="3" href="/book/ccc" download="/dl/ccc"
                extension="mobi" filesize="3 MB" year="2022" language="Spanish">
        <div slot="title">Book Three</div>
        <div slot="author">Author C</div>
    </z-bookcard>
    </body></html>
    """

    # 空页面
    EMPTY_HTML = "<html><body></body></html>"

    # 缺失 slot 的 z-bookcard
    MISSING_SLOT_HTML = """
    <html><body>
    <z-bookcard id="99" href="/book/xxx" download="/dl/xxx"
                extension="pdf" filesize="5 MB" year="2023" language="English">
    </z-bookcard>
    </body></html>
    """

    # 书籍详情页 HTML
    DETAIL_HTML = """
    <html><body>
    <h1>PYTHON: Learn Python Programming in 90 minutes or Less!</h1>
    <div class="book-details">
        <a href="/a/AZElite">AZ Elite Publishing</a>
    </div>
    <a class="btn btn-default addDownloadedBook" href="/dl/J97YlW8rgx"
       data-book_id="122949529">
        <i class="zlibicon-bookcard-download"></i>
        <span class="book-property__extension">pdf</span>, 799 KB
    </a>
    </body></html>
    """

    def test_parse_single_bookcard(self):
        """测试单本书解析"""
        books = parse_books(self.SINGLE_BOOK_HTML)

        self.assertEqual(len(books), 1)
        book = books[0]
        self.assertEqual(book.book_id, "122949529")
        self.assertEqual(book.title, "PYTHON: Learn Python Programming in 90 minutes or Less!")
        self.assertEqual(book.author, "AZ Elite Publishing")
        self.assertEqual(book.href, "/book/nJjNAqkpJg/python-learn-python-programming.html")
        self.assertEqual(book.download, "/dl/J97YlW8rgx")
        self.assertEqual(book.extension, "pdf")
        self.assertEqual(book.filesize, "799 KB")
        self.assertEqual(book.year, "2015")
        self.assertEqual(book.language, "English")

    def test_parse_multiple_books(self):
        """测试多本书解析"""
        books = parse_books(self.MULTI_BOOK_HTML)

        self.assertEqual(len(books), 3)
        self.assertEqual(books[0].title, "Book One")
        self.assertEqual(books[1].title, "Book Two")
        self.assertEqual(books[2].title, "Book Three")

        # 验证不同格式
        self.assertEqual(books[0].extension, "pdf")
        self.assertEqual(books[1].extension, "epub")
        self.assertEqual(books[2].extension, "mobi")

    def test_parse_empty_html(self):
        """测试空页面返回空列表"""
        books = parse_books(self.EMPTY_HTML)
        self.assertEqual(len(books), 0)

    def test_parse_completely_empty(self):
        """测试空字符串"""
        books = parse_books("")
        self.assertEqual(len(books), 0)

    def test_missing_slot_fallback(self):
        """测试缺失 slot 时的容错"""
        books = parse_books(self.MISSING_SLOT_HTML)

        self.assertEqual(len(books), 1)
        book = books[0]
        # slot 缺失时 title 和 author 应为空字符串
        self.assertEqual(book.title, "")
        self.assertEqual(book.author, "")
        # 其他属性应正常提取
        self.assertEqual(book.book_id, "99")
        self.assertEqual(book.download, "/dl/xxx")
        self.assertEqual(book.extension, "pdf")

    def test_book_dataclass_defaults(self):
        """测试 Book 数据类默认值"""
        book = Book()
        self.assertEqual(book.book_id, "")
        self.assertEqual(book.title, "")
        self.assertEqual(book.author, "")
        self.assertEqual(book.download, "")

    def test_parse_book_detail(self):
        """测试书籍详情页解析"""
        book = parse_book_detail(self.DETAIL_HTML)

        self.assertEqual(book.book_id, "122949529")
        self.assertEqual(book.title, "PYTHON: Learn Python Programming in 90 minutes or Less!")
        self.assertEqual(book.download, "/dl/J97YlW8rgx")
        self.assertEqual(book.extension, "pdf")


if __name__ == "__main__":
    unittest.main()
