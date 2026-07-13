# -*- coding: utf-8 -*-
# =============================================================================
# Z-Library Proxy Dockerfile
# 多阶段构建：builder 安装依赖 → runtime 精简运行镜像
# 镜像名: chenchen620/zlibrary-proxy
# =============================================================================

# ---------- 阶段1: builder ----------
FROM python:3.10-slim AS builder

WORKDIR /build

COPY requirements.txt .

RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---------- 阶段2: runtime ----------
FROM python:3.10-slim AS runtime

LABEL maintainer="chenchen620"
LABEL org.opencontainers.image.title="zlibrary-proxy"
LABEL org.opencontainers.image.description="Z-Library proxy with PoW solver, multi-account rotation, and auto URL discovery"
LABEL org.opencontainers.image.source="https://github.com/chenzhenguo/zlibrary-proxy"
LABEL org.opencontainers.image.licenses="MIT"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=5000 \
    HOST=0.0.0.0

# 安装 curl 用于健康检查
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 从 builder 阶段复制已安装的 Python 依赖
COPY --from=builder /install /usr/local

# 复制项目代码（accounts.json.default 会被包含，accounts.json 被 .dockerignore 排除）
COPY . .

# 创建数据目录
RUN mkdir -p /app/data

# 设置 entrypoint.sh 可执行权限
RUN chmod +x /app/entrypoint.sh

EXPOSE 5000

VOLUME ["/app/data"]

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

# 使用 entrypoint.sh 启动（自动检测 accounts.json）
ENTRYPOINT ["/app/entrypoint.sh"]
