# -*- coding: utf-8 -*-
# =============================================================================
# Z-Library Proxy Dockerfile
# 多阶段构建：builder 安装依赖 → runtime 精简运行镜像
# 镜像名: jakeleos/zlibrary-proxy
# =============================================================================

# ---------- 阶段1: builder ----------
FROM python:3.10-slim AS builder

WORKDIR /build

# 仅复制依赖文件，利用 Docker 层缓存
COPY requirements.txt .

# 安装依赖到指定目录
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---------- 阶段2: runtime ----------
FROM python:3.10-slim AS runtime

LABEL maintainer="jakeleos"
LABEL org.opencontainers.image.title="zlibrary-proxy"
LABEL org.opencontainers.image.description="Z-Library proxy with PoW solver, multi-account rotation, and auto URL discovery"
LABEL org.opencontainers.image.source="https://hub.docker.com/r/jakeleos/zlibrary-proxy"
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

# 复制项目代码
COPY . .

# 创建数据目录
RUN mkdir -p /app/data

EXPOSE 5000

VOLUME ["/app/data"]

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

# gunicorn 启动
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "--timeout", "120", "app:app"]
