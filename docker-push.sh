#!/bin/bash
# =============================================================================
# Z-Library Proxy Docker Hub 发布脚本
#
# 用法：
#   1. 确保 Docker 已安装并运行
#   2. 登录 Docker Hub: docker login
#   3. 运行此脚本: bash docker-push.sh
# =============================================================================

set -e

# ============ 配置 ============
DOCKER_USER="chenchen620"
IMAGE_NAME="zlibrary-proxy"
VERSION="$(date +%Y%m%d)-$(git rev-parse --short HEAD 2>/dev/null || echo 'local')"

FULL_NAME="${DOCKER_USER}/${IMAGE_NAME}"

echo "=========================================="
echo " Docker Hub Publish"
echo " Image: ${FULL_NAME}"
echo " Version: ${VERSION}"
echo "=========================================="

# ============ 登录检查 ============
if ! docker info | grep -q "Username:"; then
    echo ">>> Please login to Docker Hub..."
    docker login
fi

# ============ 构建 ============
echo ""
echo ">>> Building image: ${FULL_NAME}:latest"
docker build -t "${FULL_NAME}:latest" .

# ============ 打版本标签 ============
echo ""
echo ">>> Tagging version: ${FULL_NAME}:${VERSION}"
docker tag "${FULL_NAME}:latest" "${FULL_NAME}:${VERSION}"

# ============ 推送 ============
echo ""
echo ">>> Pushing ${FULL_NAME}:latest"
docker push "${FULL_NAME}:latest"

echo ""
echo ">>> Pushing ${FULL_NAME}:${VERSION}"
docker push "${FULL_NAME}:${VERSION}"

# ============ 完成 ============
echo ""
echo "=========================================="
echo " Published successfully!"
echo ""
echo " Pull command:"
echo "   docker pull ${FULL_NAME}:latest"
echo ""
echo " Run command:"
echo "   docker run -d -p 5000:5000 -v ./data:/app/data \\"
echo "     -e ZLIB_FLASK_SECRET=your-secret \\"
echo "     -e ZLIB_ACCESS_PASSWORD=123456 \\"
echo "     ${FULL_NAME}:latest"
echo "=========================================="
