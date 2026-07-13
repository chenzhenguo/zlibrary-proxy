#!/bin/bash
# =============================================================================
# Z-Library Proxy 启动入口脚本
#
# 功能：
# 1. 检查 accounts.json 是否存在（多个候选路径）
# 2. 不存在则从内置默认文件复制
# 3. 启动 gunicorn
# =============================================================================

set -e

APP_DIR="/app"
DATA_DIR="${APP_DIR}/data"
DEFAULT_FILE="${APP_DIR}/accounts.json.default"

# 确保数据目录存在
mkdir -p "${DATA_DIR}"

# 查找 accounts.json 的位置
ACCOUNTS_FOUND=""
for candidate in "${DATA_DIR}/accounts.json" "${APP_DIR}/accounts.json"; do
    if [ -f "${candidate}" ]; then
        ACCOUNTS_FOUND="${candidate}"
        break
    fi
done

if [ -z "${ACCOUNTS_FOUND}" ]; then
    echo "[entrypoint] accounts.json not found, copying built-in default..."
    if [ -f "${DEFAULT_FILE}" ]; then
        cp "${DEFAULT_FILE}" "${DATA_DIR}/accounts.json"
        # 同时复制到 /app/accounts.json 作为 fallback
        cp "${DEFAULT_FILE}" "${APP_DIR}/accounts.json"
        echo "[entrypoint] Default accounts.json copied to ${DATA_DIR}/accounts.json"
    else
        echo "[entrypoint] WARNING: No default accounts.json found!"
        echo "[]" > "${DATA_DIR}/accounts.json"
    fi
else
    echo "[entrypoint] accounts.json found at ${ACCOUNTS_FOUND}"
fi

# 显示账号数量
ACCOUNT_COUNT=$(python3 -c "import json; print(len(json.load(open('${DATA_DIR}/accounts.json'))))" 2>/dev/null || echo "0")
echo "[entrypoint] Loaded ${ACCOUNT_COUNT} accounts"

# 启动 gunicorn
echo "[entrypoint] Starting gunicorn..."
exec gunicorn -w 4 -b 0.0.0.0:5000 --timeout 120 app:app
