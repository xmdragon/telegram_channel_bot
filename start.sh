#!/bin/bash

# Telegram 消息审核系统 Docker 启动脚本

set -e

echo "🚀 启动 Telegram 消息审核系统..."

# 创建必要的目录
mkdir -p sessions logs data

# 设置权限
chmod 755 sessions logs data

# 初始化数据库
echo "📊 初始化数据库..."
python init_db.py

# 启动应用
echo "🌟 启动应用..."
exec python main.py