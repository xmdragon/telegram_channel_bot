#!/bin/bash

# 使用项目内的Supervisor配置启动所有服务

echo "🚀 启动 Telegram 消息审核系统..."

# 加载环境配置
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Redis配置
REDIS_HOST=${REDIS_HOST:-localhost}
REDIS_PORT=${REDIS_PORT:-6379}
REDIS_PASSWORD=${REDIS_PASSWORD:-}

# 检查Redis服务
echo "📡 检查Redis连接..."
if [ -n "$REDIS_PASSWORD" ]; then
    # 有密码的Redis
    if ! redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" -a "$REDIS_PASSWORD" ping > /dev/null 2>&1; then
        echo "⚠️  无法连接到Redis: $REDIS_HOST:$REDIS_PORT"
        echo "   请检查Redis配置和服务状态"
        exit 1
    fi
else
    # 无密码的Redis
    if ! redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" ping > /dev/null 2>&1; then
        echo "⚠️  无法连接到Redis: $REDIS_HOST:$REDIS_PORT"
        echo "   请检查Redis配置和服务状态"
        exit 1
    fi
fi
echo "✅ Redis连接正常: $REDIS_HOST:$REDIS_PORT"

# 检查Supervisor是否安装
if ! command -v supervisord &> /dev/null; then
    echo "❌ Supervisor未安装，请先运行: sudo apt install supervisor"
    exit 1
fi

# 确保日志目录存在
mkdir -p logs
mkdir -p temp_media
mkdir -p data/config
mkdir -p data/training
mkdir -p data/backups

# 检查是否已有supervisord运行
if [ -f "supervisord.pid" ]; then
    PID=$(cat supervisord.pid)
    if ps -p $PID > /dev/null 2>&1; then
        echo "⚠️  Supervisor已在运行 (PID: $PID)"
        echo "📦 重新加载配置并启动服务..."
        supervisorctl -c config/supervisord.conf reread
        supervisorctl -c config/supervisord.conf update
        supervisorctl -c config/supervisord.conf start telegram:*
    else
        echo "🔧 清理旧的PID文件..."
        rm -f supervisord.pid
        rm -f supervisor.sock

        echo "📦 启动Supervisor..."
        supervisord -c config/supervisord.conf
        sleep 2

        echo "📦 启动所有服务..."
        supervisorctl -c config/supervisord.conf start telegram:*
    fi
else
    echo "📦 启动Supervisor..."
    supervisord -c config/supervisord.conf
    sleep 2

    echo "📦 启动所有服务..."
    supervisorctl -c config/supervisord.conf start telegram:*
fi

# 等待一下让服务启动
sleep 2

# 显示服务状态
echo ""
echo "📊 服务状态:"
supervisorctl -c config/supervisord.conf status telegram:*

echo ""
echo "✅ 所有服务已通过Supervisor启动"
echo "🌐 访问 http://localhost:8080/static/status.html 查看服务状态"
echo ""
echo "常用命令:"
echo "  查看状态: supervisorctl -c config/supervisord.conf status"
echo "  停止服务: supervisorctl -c config/supervisord.conf stop telegram:*"
echo "  重启服务: supervisorctl -c config/supervisord.conf restart telegram_web"
echo "  查看日志: supervisorctl -c config/supervisord.conf tail -f telegram_web"