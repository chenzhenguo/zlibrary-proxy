# -*- coding: utf-8 -*-
"""
搜索结果 HTML 解析器

将 Z-Library 搜索结果页 HTML 解析为结构化书籍列表。
每本书是 <z-bookcard> 自定义元素，属性包含元数据，slot 包含书名和作者。

HTML 结构示例：
<z-bookcard id="122949529" href="/book/nJjNAqkpJg/..." download="/dl/J97YlW8rgx"
            extension="pdf" filesize="799 KB" year="2015" language="English">
    <div slot="title">PYTHON: Learn Python Programming...</div>
    <div slot="author">AZ Elite Publishing</div>
</z-bookcard>
"""

from dataclasses import dataclass, field
from bs4 import BeautifulSoup


@dataclass
class Book:
    """书籍数据模型"""
    book_id: str = ""          # 书籍 ID
    title: str = ""            # 书名
    author: str = ""           # 作者
    href: str = ""             # 详情页路径（如 /book/xxx）
    download: str = ""         # 下载路径（如 /dl/xxx）
    extension: str = ""        # 文件格式（pdf/epub/mobi 等）
    filesize: str = ""         # 文件大小（如 "799 KB"）
    year: str = ""             # 出版年份
    language: str = ""         # 语言


def parse_books(html: str) -> list:
    """
    解析搜索结果页，提取所有 z-bookcard 元素为 Book 列表

    Args:
        html: 搜索结果页 HTML 内容

    Returns:
        Book 对象列表；若无结果返回空列表
    """
    soup = BeautifulSoup(html, "lxml")
    books = []

    for card in soup.find_all("z-bookcard"):
        # 从 slot 属性的 div 中提取书名和作者
        title_el = card.find(attrs={"slot": "title"})
        author_el = card.find(attrs={"slot": "author"})

        book = Book(
            book_id=card.get("id", ""),
            title=title_el.get_text(strip=True) if title_el else "",
            author=author_el.get_text(strip=True) if author_el else "",
            href=card.get("href", ""),
            download=card.get("download", ""),
            extension=card.get("extension", ""),
            filesize=card.get("filesize", ""),
            year=card.get("year", ""),
            language=card.get("language", ""),
        )
        books.append(book)

    return books


def parse_book_detail(html: str) -> Book:
    """
    从书籍详情页 HTML 解析单本书的信息

    详情页结构与搜索结果不同，书名在 <h1> 标签中，
    下载链接在 <a class="addDownloadedBook" href="/dl/xxx"> 中。

    Args:
        html: 书籍详情页 HTML 内容

    Returns:
        Book 对象
    """
    soup = BeautifulSoup(html, "lxml")

    # 书名在 <h1> 标签中
    title_el = soup.find("h1")
    title = title_el.get_text(strip=True) if title_el else ""

    # 下载链接在 <a class="addDownloadedBook"> 中
    download_el = soup.find("a", class_="addDownloadedBook")
    download = download_el.get("href", "") if download_el else ""
    book_id = download_el.get("data-book_id", "") if download_el else ""

    # 从下载按钮文本中提取格式和大小（如 "pdf, 799 KB"）
    extension = ""
    filesize = ""
    if download_el:
        text = download_el.get_text(strip=True)
        # 格式通常在文本开头
        parts = text.split(",")
        if parts:
            extension = parts[0].strip().lower()

    # 作者通常在详情页的特定位置
    author_el = soup.find("a", href=lambda x: x and "/s/" in str(x))
    author = ""
    # 尝试从页面中提取作者信息
    for el in soup.find_all("a"):
        href = el.get("href", "")
        if href and "/a/" in href:
            author = el.get_text(strip=True)
            break

    return Book(
        book_id=book_id,
        title=title,
        author=author,
        href="",
        download=download,
        extension=extension,
        filesize=filesize,
        year="",
        language="",
    )
