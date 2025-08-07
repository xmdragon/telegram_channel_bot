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
echo "🚀 启动系统..."
echo

# 启动新进程
./start.sh