#!/bin/bash

# Telegram 消息审核系统重启脚本

echo "🔄 重启 Telegram 消息审核系统..."
echo

# 停止现有进程和数据库
./stop.sh

# 等待进程完全停止
sleep 2

echo
echo "🐳 重启Docker数据库服务..."
docker compose restart postgres redis 2>/dev/null || true

# 等待数据库就绪
echo "⏳ 等待数据库就绪..."
sleep 3

echo

# 显示错误日志信息
if [ -f "./logs/error.log" ]; then
    ERROR_COUNT=$(grep -c "ERROR" "./logs/error.log" 2>/dev/null || echo "0")
    WARNING_COUNT=$(grep -c "WARNING" "./logs/error.log" 2>/dev/null || echo "0")
    if [ "$ERROR_COUNT" -gt 0 ] || [ "$WARNING_COUNT" -gt 0 ]; then
        echo "⚠️  发现历史错误日志: $WARNING_COUNT 个警告, $ERROR_COUNT 个错误"
        echo "   使用 ./view_errors.sh 查看详情"
        echo
    fi
fi

echo "🚀 启动系统..."
echo

# 启动新进程
./start.sh