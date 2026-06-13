#!/bin/bash
# ============================================
# ChronicleAgent 停止脚本
# 用法: ./stop.sh
# ============================================

set -e

echo "============================================"
echo " ChronicleAgent - 停止"
echo "============================================"

docker compose down

echo ""
echo "已停止所有服务"
echo "数据卷（数据库/向量）保留，重启后数据还在"
echo ""
echo "如需完全清理（删除数据）:"
echo "  docker compose down -v"
