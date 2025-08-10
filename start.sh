#!/bin/bash

# Telegram 消息审核系统启动脚本

set -e

echo "🚀 启动 Telegram 消息审核系统..."

# 检查虚拟环境
if [ ! -d "venv" ]; then
    echo "📦 创建虚拟环境..."
    python3 -m venv venv
fi

# 激活虚拟环境
echo "🔧 激活虚拟环境..."
source venv/bin/activate

# 检查依赖
if [ ! -f "venv/installed.flag" ]; then
    echo "📚 安装依赖..."
    pip install -r requirements.txt
    touch venv/installed.flag
fi

# 创建必要的目录
mkdir -p logs data temp_media

# 设置权限
chmod 755 logs data temp_media

# 检查并启动Docker数据库服务
echo "🐳 检查Docker数据库服务..."
if ! docker compose ps postgres 2>/dev/null | grep -q "running"; then
    echo "📦 启动PostgreSQL数据库..."
    docker compose up -d postgres
    # 等待数据库就绪
    echo "⏳ 等待数据库就绪..."
    sleep 3
fi

if ! docker compose ps redis 2>/dev/null | grep -q "running"; then
    echo "📦 启动Redis缓存..."
    docker compose up -d redis
    
    # 等待Redis就绪
    echo "⏳ 等待Redis就绪..."
    for i in {1..10}; do
        if docker exec telegram_bot_redis redis-cli ping > /dev/null 2>&1; then
            echo "✅ Redis已就绪"
            break
        fi
        if [ $i -eq 10 ]; then
            echo "❌ Redis启动超时"
            exit 1
        fi
        sleep 1
    done
fi

# 检查数据库是否需要初始化
if [ ! -f "data/db_initialized.flag" ]; then
    echo "📊 初始化数据库..."
    python3 init_db.py
    touch data/db_initialized.flag
fi

# 启动应用
echo "🌟 启动应用..."
exec python3 main.py