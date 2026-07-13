#!/bin/bash
# =============================================================================
# Z-Library Proxy 启动入口脚本
#
# 功能：
# 1. 检查 /app/data/accounts.json 是否存在
# 2. 不存在则从内置默认文件复制
# 3. 启动 gunicorn
# =============================================================================

set -e

DATA_DIR="/app/data"
ACCOUNTS_FILE="${DATA_DIR}/accounts.json"
DEFAULT_FILE="/app/accounts.json.default"

# 确保数据目录存在
mkdir -p "${DATA_DIR}"

# 如果挂载的 accounts.json 不存在，使用内置默认
if [ ! -f "${ACCOUNTS_FILE}" ]; then
    echo "[entrypoint] accounts.json not found in /app/data/"
    if [ -f "${DEFAULT_FILE}" ]; then
        echo "[entrypoint] Copying built-in default accounts.json"
        cp "${DEFAULT_FILE}" "${ACCOUNTS_FILE}"
    else
        echo "[entrypoint] WARNING: No default accounts.json found!"
        echo "[entrypoint] Download will fail without accounts."
        # 创建空数组避免 JSON 解析错误
        echo "[]" > "${ACCOUNTS_FILE}"
    fi
else
    echo "[entrypoint] accounts.json found in /app/data/"
fi

# 显示账号数量
ACCOUNT_COUNT=$(python3 -c "import json; print(len(json.load(open('${ACCOUNTS_FILE}'))))" 2>/dev/null || echo "0")
echo "[entrypoint] Loaded ${ACCOUNT_COUNT} accounts"

# 启动 gunicorn
echo "[entrypoint] Starting gunicorn..."
exec gunicorn -w 4 -b 0.0.0.0:5000 --timeout 120 app:app
