#!/bin/bash
# ============================================
# ChronicleAgent 云服务器启动脚本
# 用法: ./start.sh [dev|prod]
# ============================================

set -e

MODE=${1:-prod}
COMPOSE_FILE="docker-compose.yml"

echo "============================================"
echo " ChronicleAgent - 启动 ($MODE)"
echo "============================================"

# 检查 .env
if [ ! -f .env ]; then
    echo "[错误] 未找到 .env 文件"
    echo "请执行: cp .env.example .env && vim .env"
    exit 1
fi

if [ "$MODE" = "dev" ]; then
    echo "开发模式: 附加 --reload 标志"
    export DEBUG=true
    docker compose -f "$COMPOSE_FILE" up -d
    echo ""
    echo "后端 API: http://localhost:8000"
    echo "API 文档: http://localhost:8000/docs"
    echo ""
    echo "查看日志: docker compose logs -f backend"
else
    echo "生产模式"
    docker compose -f "$COMPOSE_FILE" up -d
    echo ""
    echo "服务已启动"
    echo "健康检查: curl http://localhost:8000/health"
    echo "查看日志: docker compose logs -f"
fi
