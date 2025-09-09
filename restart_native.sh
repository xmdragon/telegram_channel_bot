#!/bin/bash

# Telegram 消息审核系统重启脚本 - 本地服务版本

set -e

echo "🔄 重启 Telegram 消息审核系统 (本地服务版)..."

# 停止应用
echo "1️⃣ 停止当前应用..."
./stop_native.sh

# 等待进程完全停止
echo "2️⃣ 等待进程停止..."
sleep 3

# 重启服务
echo "3️⃣ 重启本地服务..."
if ! brew services list | grep -q "redis.*started"; then
    brew services start redis
fi

if ! brew services list | grep -q "nginx.*started"; then
    brew services start nginx
fi

# 启动应用
echo "4️⃣ 启动应用..."
exec ./start_native.sh --quick