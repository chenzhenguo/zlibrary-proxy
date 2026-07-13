# -*- coding: utf-8 -*-
"""
Z-Library 代理程序 - Flask 应用入口

提供搜索、列表展示、书籍详情和下载功能。
前端响应式 CSS，移动端友好。

高可用设计：
- 共享 ZLibraryClient（Session 内部用 threading.Lock 保护）
- 账号管理器线程安全
- 错误信息友好展示
- 健康检查端点
- 操作日志记录

路由：
- GET/POST /login   → 密码登录页
- GET /logout       → 注销
- GET /             → 搜索框页面（需登录）
- GET /search       → 搜索 + 列表展示（需登录）
- GET /book         → 书籍详情 + 下载按钮（需登录）
- GET /download     → 获取 CDN 直链并 302 重定向（需登录）
- GET /status       → 状态页（URL 发现信息 + 账号状态，需登录）
- GET /health       → 健康检查（无需登录）

配置（环境变量）：
- ZLIB_ACCESS_PASSWORD  页面访问密码（默认: 123456）
- ZLIB_FLASK_SECRET     Flask session 密钥（生产环境必须设置）
- ZLIB_ACCOUNTS_FILE    账号 JSON 文件路径
"""

import logging
import os
from urllib.parse import parse_qs, unquote, urlparse

from flask import (
    Flask,
    Response,
    abort,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from zlibrary import url_discovery
from zlibrary.client import ZLibraryClient
from zlibrary.config import (
    AllAccountsExhaustedError,
    AllURLsUnavailableError,
    DailyLimitReachedError,
    LoginRequiredError,
    ZLibError,
    load_secret,
)

# ============ 日志配置 ============
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ============ 应用配置 ============
app = Flask(__name__)

# Flask session 密钥：环境变量 > 默认值（生产环境必须设置 ZLIB_FLASK_SECRET）
app.secret_key = load_secret(
    "ZLIB_FLASK_SECRET",
    default="dev-only-secret-key-please-set-ZLIB_FLASK_SECRET-in-production",
)

# 页面访问密码
ACCESS_PASSWORD = load_secret("ZLIB_ACCESS_PASSWORD", default="123456")

# ============ 全局客户端（线程安全） ============
client = ZLibraryClient()


# ============ 错误处理 ============

@app.errorhandler(ZLibError)
def handle_zlib_error(e: ZLibError):
    """统一处理 Z-Library 相关错误"""
    logger.error(f"ZLib error: {e}", exc_info=True)
    return render_template(
        "index.html",
        books=None,
        query="",
        page=1,
        error=str(e),
    ), 500


@app.errorhandler(404)
def handle_404(e):
    return render_template(
        "index.html", books=None, query="", page=1, error="Page not found"
    ), 404


# ============ 认证 ============

@app.before_request
def require_auth():
    """请求前拦截：检查用户是否已登录"""
    if request.path in ("/login", "/health"):
        return
    if not session.get("authenticated"):
        return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    """密码登录页"""
    if request.method == "POST":
        password = request.form.get("password", "")
        if password == ACCESS_PASSWORD:
            session["authenticated"] = True
            logger.info("User logged in")
            return redirect(url_for("index"))
        logger.warning("Login failed: wrong password")
        return render_template("login.html", error="Wrong password")
    return render_template("login.html", error=None)


@app.route("/logout")
def logout():
    """注销：清除 session"""
    session.clear()
    return redirect(url_for("login"))


# ============ 业务路由 ============

@app.route("/health")
def health():
    """健康检查端点（无需登录）"""
    return {
        "status": "ok",
        "accounts": client.account_manager.has_accounts(),
        "pow_solved": client._pow_solved,
    }


@app.route("/")
def index():
    """首页：展示搜索框"""
    return render_template("index.html", books=None, query="", page=1, error=None)


@app.route("/search")
def search():
    """搜索：输入关键词，展示书籍名称列表"""
    query = request.args.get("q", "").strip()
    page = request.args.get("page", 1, type=int)

    if not query:
        return render_template("index.html", books=None, query="", page=1, error=None)

    try:
        logger.info(f"Search: q='{query}', page={page}")
        books = client.search(query, page)
        logger.info(f"Search results: {len(books)} books")
        return render_template(
            "index.html", books=books, query=query, page=page, error=None
        )
    except AllURLsUnavailableError as e:
        logger.error(f"Search failed: {e}")
        return render_template(
            "index.html",
            books=None,
            query=query,
            page=1,
            error=f"Search failed: {e}",
        )


@app.route("/book")
def book_detail():
    """书籍详情：点击书名后展示书籍信息和下载按钮"""
    path = request.args.get("path", "")
    title = request.args.get("title", "")
    author = request.args.get("author", "")
    extension = request.args.get("extension", "")
    filesize = request.args.get("filesize", "")
    year = request.args.get("year", "")
    language = request.args.get("language", "")
    download = request.args.get("download", "")

    if not path and not download:
        abort(400, "Missing book path or download link")

    return render_template(
        "book.html",
        title=title,
        author=author,
        extension=extension,
        filesize=filesize,
        year=year,
        language=language,
        download=download,
        path=path,
    )


@app.route("/download")
def download():
    """
    下载：获取 CDN 直链并 302 重定向

    不再通过服务器代理流式转发，直接让浏览器访问 CDN URL 下载。
    优势：
    - 服务器不消耗带宽和内存
    - 下载速度更快（直连 CDN）
    - 支持断点续传（浏览器原生支持）
    - 服务器不会因为大文件下载阻塞 worker

    账号切换逻辑由 client.get_download_url 内部处理：
    - 遇到下载限制自动切换到下一个可用账号
    - 所有账号用尽时抛出 DailyLimitReachedError
    """
    path = request.args.get("path", "")

    if not path or not path.startswith("/dl/"):
        abort(400, "Invalid download path")

    try:
        # 获取 CDN 直链（内部自动处理 PoW + 登录 + 账号切换）
        cdn_url = client.get_download_url(path)
        logger.info(f"Download redirect: path={path} -> {cdn_url[:80]}...")

        # 提取文件名用于日志
        parsed = urlparse(cdn_url)
        params = parse_qs(parsed.query)
        filename = unquote(params.get("filename", ["book"])[0])
        logger.info(f"Download file: {filename}")

        # 302 重定向到 CDN 直链，浏览器直接下载
        return redirect(cdn_url, code=302)

    except DailyLimitReachedError as e:
        logger.warning(f"Download limit reached: {e}")
        return Response(f"Daily limit reached: {e}", status=429, mimetype="text/plain")
    except AllAccountsExhaustedError as e:
        logger.error(f"All accounts exhausted: {e}")
        return Response(f"All accounts exhausted: {e}", status=503, mimetype="text/plain")
    except LoginRequiredError as e:
        logger.warning(f"Login required: {e}")
        return Response(f"Login required: {e}", status=401, mimetype="text/plain")
    except ZLibError as e:
        logger.error(f"Download error: {e}", exc_info=True)
        return Response(f"Download failed: {e}", status=500, mimetype="text/plain")


@app.route("/status")
def status():
    """状态页：显示当前 URL、可用列表、缓存时间、账号状态"""
    info = url_discovery.get_status_info()
    info["accounts"] = client.account_manager.get_status()
    return render_template("status.html", info=info)


# ============ 入口 ============

if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    port = int(os.environ.get("PORT", "5000"))
    host = os.environ.get("HOST", "0.0.0.0")
    app.run(host=host, port=port, debug=debug, threaded=True)
