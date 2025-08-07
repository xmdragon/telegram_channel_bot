#!/bin/bash

# Telegram 消息审核系统停止脚本

echo "🛑 停止 Telegram 消息审核系统..."

# 查找并停止main.py进程
PID=$(ps aux | grep "[p]ython3 main.py" | awk '{print $2}')

if [ -z "$PID" ]; then
    echo "⚠️  系统未在运行"
else
    echo "📍 找到进程 PID: $PID"
    kill -TERM $PID
    echo "✅ 系统已停止"
fi

# 清理可能的僵尸进程
pkill -f "python3 main.py" 2>/dev/null
pkill -f "uvicorn main:app" 2>/dev/null

echo "🐳 停止Docker数据库服务..."
docker compose stop postgres redis 2>/dev/null || true

echo "🔧 清理完成"