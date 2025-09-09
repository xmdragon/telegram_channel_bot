#!/bin/bash

# Telegram 消息审核系统停止脚本 - 本地服务版本
# 停止本地Redis和Nginx服务以及Python应用

set -e

echo "🛑 停止 Telegram 消息审核系统 (本地服务版)..."

# 停止Python应用进程
echo "📱 停止应用进程..."
if pgrep -f "dev_supervisor.py" >/dev/null; then
    echo "   停止进程管理器..."
    pkill -f "dev_supervisor.py" || true
    sleep 2
fi

if pgrep -f "web_server.py\|telegram_collector.py\|message_scheduler.py" >/dev/null; then
    echo "   停止应用服务进程..."
    pkill -f "web_server.py" || true
    pkill -f "telegram_collector.py" || true  
    pkill -f "message_scheduler.py" || true
    sleep 2
fi

# 停止本地服务（可选）
echo "🍺 本地服务管理："
echo "   - Redis: brew services stop redis (可选)"
echo "   - Nginx: brew services stop nginx (可选)"
echo ""
echo "💡 提示:"
echo "   本地服务可以继续运行，供其他应用使用"
echo "   如需完全停止，请手动运行："
echo "   brew services stop redis nginx"
echo ""

echo "✅ 应用进程已停止"
echo "🌐 Web界面已关闭"
echo ""