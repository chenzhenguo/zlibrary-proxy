# Z-Library Proxy

[![Docker](https://img.shields.io/badge/docker-jakeleos%2Fzlibrary--proxy-blue)](https://hub.docker.com/r/jakeleos/zlibrary-proxy)
[![GitHub](https://img.shields.io/badge/source-chenzhenguo%2Fzlibrary--proxy-green)](https://github.com/chenzhenguo/zlibrary-proxy)
[![Python](https://img.shields.io/badge/python-3.10+-green)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-yellow)](LICENSE)

Z-Library 镜像站代理程序，提供书籍搜索、详情查看和下载功能。
后端自动处理 PoW 挑战、URL 发现切换、多账号轮换，前端用户完全无感知。

## 功能特性

- **搜索书籍**：支持书名、作者、ISBN 等关键词搜索
- **下载功能**：获取 CDN 直链 302 重定向，浏览器直接下载，支持断点续传
- **自动 URL 发现**：从 GitHub README 自动获取最新入口地址，24 小时缓存
- **多镜像切换**：第一个不可用自动切换下一个，内置健康检测
- **PoW 自动求解**：后端 Python 完成 SHA1 工作量证明，无需浏览器 JS
- **多账号轮换**：下载超限时自动循环切换到下一个可用账号，全量耗尽自动重置
- **线程安全**：全局客户端用锁保护，支持多用户并发请求
- **密码保护**：访问页面需输入密码
- **响应式 UI**：移动端优先设计，大字体大按钮，支持各种屏幕尺寸
- **健康检查**：内置 `/health` 端点，支持 Docker HEALTHCHECK
- **操作日志**：搜索、下载、账号切换等关键操作全程记录

## 快速开始

### 方式一：Docker Hub 拉取（最简单）

```bash
# 1. 拉取镜像
docker pull jakeleos/zlibrary-proxy:latest

# 2. 准备数据目录
mkdir -p data
# 将 accounts.json 放入 data/ 目录

# 3. 启动容器
docker run -d \
  --name zlibrary-proxy \
  --restart unless-stopped \
  -p 5000:5000 \
  -v ./data:/app/data \
  -e ZLIB_FLASK_SECRET=$(python -c "import secrets; print(secrets.token_hex(32))") \
  -e ZLIB_ACCESS_PASSWORD=123456 \
  jakeleos/zlibrary-proxy:latest

# 4. 查看日志
docker logs -f zlibrary-proxy
```

访问 `http://localhost:5000/`，输入密码 `123456` 登录。

### 方式二：Docker Compose

```bash
# 1. 下载 docker-compose.yml 和 .env.example
# 2. 准备配置
cp .env.example .env
# 编辑 .env，修改 ZLIB_FLASK_SECRET 为随机字符串

# 3. 准备账号数据
mkdir -p data
cp accounts.json data/

# 4. 启动（自动拉取 Docker Hub 镜像）
docker compose up -d

# 5. 查看日志
docker compose logs -f

# 6. 停止
docker compose down
```

### 方式三：本地构建运行

```bash
# 构建镜像
docker compose up -d --build

# 或本地直接运行
pip install -r requirements.txt
python app.py
```

### 方式四：从源码运行

```bash
pip install -r requirements.txt

# 开发模式
python app.py

# 生产模式（gunicorn）
gunicorn -w 4 -b 0.0.0.0:5000 --timeout 120 app:app
```

## 环境变量

| 变量名 | 必填 | 默认值 | 说明 |
|--------|------|--------|------|
| `ZLIB_FLASK_SECRET` | 生产必填 | `dev-only-...` | Flask session 加密密钥 |
| `ZLIB_ACCESS_PASSWORD` | 否 | `123456` | 页面访问密码 |
| `ZLIB_ACCOUNTS_FILE` | 否 | `accounts.json` | 账号 JSON 文件路径 |
| `PORT` | 否 | `5000` | 监听端口 |
| `HOST` | 否 | `0.0.0.0` | 监听地址 |
| `FLASK_DEBUG` | 否 | `false` | Flask 调试模式 |

生成密钥：
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

## 路由说明

| 路径 | 方法 | 认证 | 功能 |
|------|------|------|------|
| `/login` | GET/POST | 否 | 密码登录页 |
| `/logout` | GET | 是 | 注销 |
| `/` | GET | 是 | 搜索框页面 |
| `/search?q=关键词&page=n` | GET | 是 | 搜索并展示书籍列表 |
| `/book?path=...&title=...` | GET | 是 | 书籍详情 + 下载按钮 |
| `/download?path=/dl/xxx` | GET | 是 | 获取 CDN 直链并 302 重定向 |
| `/status` | GET | 是 | 状态页（URL 信息 + 账号状态） |
| `/health` | GET | 否 | 健康检查（JSON） |

## 项目结构

```
zlibrary-proxy/
├── app.py                        # Flask 应用入口
├── requirements.txt              # Python 依赖
├── Dockerfile                    # Docker 多阶段构建
├── docker-compose.yml            # Docker Compose 编排
├── docker-push.sh                # Docker Hub 发布脚本
├── .env.example                  # 环境变量示例
├── .dockerignore                 # Docker 构建排除
├── .github/
│   └── workflows/
│       └── docker-publish.yml    # CI 自动构建推送
├── accounts.json                 # 账号数据（含 cookie）
├── zlibrary/
│   ├── config.py                 # 共享配置 + 自定义异常
│   ├── client.py                 # HTTP 客户端（PoW + 搜索 + 下载）
│   ├── account_manager.py        # 多账号管理 + 循环切换
│   ├── pow_solver.py             # PoW 挑战求解器（SHA1）
│   ├── url_discovery.py          # URL 发现 + 缓存 + 健康检测
│   └── parser.py                 # HTML 解析器
├── templates/
│   ├── base.html                 # 响应式 CSS 框架
│   ├── login.html                # 登录页
│   ├── index.html                # 搜索 + 结果列表
│   ├── book.html                 # 书籍详情 + 下载按钮
│   └── status.html               # 状态页
└── tests/
    ├── test_account_manager.py   # 账号管理器测试
    ├── test_auth.py              # 认证测试
    ├── test_client.py            # 客户端测试
    ├── test_parser.py            # 解析器测试
    ├── test_pow_solver.py        # PoW 求解器测试
    └── test_url_discovery.py     # URL 发现测试
```

## 运行测试

```bash
python -m pytest tests/ -v
```

## 核心参数

| 参数 | 值 | 说明 |
|------|-----|------|
| 注册用户每日下载限制 | 10 次 | 超限自动循环切换账号 |
| URL 缓存 TTL | 24 小时 | 过期后从 GitHub 重新获取 |
| 健康检测超时 | 10 秒 | URL 可用性检测 |
| HTTP 请求超时 | 15 秒 | 搜索/详情请求 |
| 下载超时 | 30 秒 | CDN 文件下载 |
| PoW 目标字节 | 0xB0 / 0x0B | SHA1 工作量证明参数 |
| 网络重试次数 | 3 | 指数退避 1.5x |

## accounts.json 格式

```json
[
  {
    "email": "user@duckmail.sbs",
    "password": "123456",
    "cookies": [
      {
        "name": "remix_userid",
        "value": "49600663",
        "domain": ".zlib.bz",
        "path": "/"
      }
    ],
    "downloads_today": 0,
    "last_used": ""
  }
]
```

## Docker Hub 发布

### 手动发布

```bash
# 1. 登录 Docker Hub
docker login

# 2. 一键发布（构建 + 打标签 + 推送）
bash docker-push.sh
```

### CI 自动发布

推送到 GitHub main 分支后，GitHub Actions 自动构建多架构镜像（amd64 + arm64）并推送：
- `jakeleos/zlibrary-proxy:latest` - 最新版本
- `jakeleos/zlibrary-proxy:YYYYMMDD-gitsha` - 版本快照

需要在 GitHub repo Settings > Secrets 中配置：
- `DOCKERHUB_USERNAME` - Docker Hub 用户名
- `DOCKERHUB_TOKEN` - Docker Hub Access Token

### 多架构支持

镜像支持以下架构：
- `linux/amd64` - x86_64（PC / 服务器）
- `linux/arm64` - ARM64（树莓派 / Apple Silicon）

## 架构设计

```
用户浏览器
    │
    ▼
Flask (gunicorn 4 workers)
    │
    ▼
ZLibraryClient (线程安全)
    ├── url_discovery → GitHub README → URL 列表 + 健康检测
    ├── pow_solver → SHA1 挑战求解 → cookie 存入 Session
    ├── account_manager → cookie 登录 / 密码登录 → 循环切换
    └── parser → BeautifulSoup 解析搜索结果
    │
    ▼
Z-Library 镜像站 (多 URL 自动切换)
```

### 高可用设计

- **URL 冗余**：≥3 个镜像地址，单个不可用自动切换
- **账号冗余**：多账号循环轮换，全量耗尽自动重置计数
- **Cookie 复用**：PoW cookie 持久化，避免重复求解
- **原子写入**：accounts.json 用 tempfile + os.replace，断电不丢数据
- **线程安全**：RLock 保护所有共享状态
- **优雅降级**：GitHub 不可达时用旧缓存，全挂时用 FALLBACK_URLS
- **操作日志**：搜索/下载/切换全程记录，便于排查

## 技术栈

- **Python 3.10+** / Flask 3.0 / requests / BeautifulSoup4 + lxml
- **gunicorn** - 生产级 WSGI 服务器
- **Docker** - 多阶段构建，多架构支持

## License

MIT
