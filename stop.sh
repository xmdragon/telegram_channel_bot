#!/bin/bash

# Telegram 消息审核系统停止脚本

echo "🛑 停止 Telegram 消息审核系统..."

# 首先检查并停止占用8000端口的进程
PORT_PID=$(lsof -ti:8000)
if [ ! -z "$PORT_PID" ]; then
    echo "📍 发现端口8000被占用，PID: $PORT_PID"
    kill -9 $PORT_PID 2>/dev/null
    echo "✅ 已停止占用端口的进程"
    sleep 1
fi

# 查找并停止main.py进程
PID=$(ps aux | grep "[p]ython3 main.py" | awk '{print $2}')

if [ -z "$PID" ]; then
    echo "⚠️  main.py进程未在运行"
else
    echo "📍 找到main.py进程 PID: $PID"
    kill -TERM $PID
    echo "✅ main.py进程已停止"
fi

# 清理可能的僵尸进程
pkill -f "python3 main.py" 2>/dev/null
pkill -f "uvicorn main:app" 2>/dev/null

echo "🐳 停止Redis服务..."
docker compose stop redis 2>/dev/null || true

echo "🔧 清理完成"