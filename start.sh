#!/bin/bash

# Telegram消息采集审核系统启动脚本

echo "🚀 启动Telegram消息采集审核系统..."

# 检查Python版本
python_version=$(python3 --version 2>&1 | grep -o '[0-9]\+\.[0-9]\+')
required_version="3.8"

if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" != "$required_version" ]; then
    echo "❌ Python版本过低，需要Python 3.8+，当前版本: $python_version"
    exit 1
fi

# 检查.env文件
if [ ! -f ".env" ]; then
    echo "⚠️  未找到.env文件，正在创建..."
    cp .env.example .env
    echo "✅ 已创建.env文件，请编辑配置后重新运行"
    echo "📝 需要配置的重要参数："
    echo "   - TELEGRAM_BOT_TOKEN: Telegram机器人Token"
    echo "   - TELEGRAM_API_ID: Telegram API ID"
    echo "   - TELEGRAM_API_HASH: Telegram API Hash"
    echo "   - SOURCE_CHANNELS: 源频道列表"
    echo "   - REVIEW_GROUP_ID: 审核群ID"
    echo "   - TARGET_CHANNEL_ID: 目标频道ID"
    exit 1
fi

# 检查依赖
echo "📦 检查依赖..."
if ! pip3 show fastapi > /dev/null 2>&1; then
    echo "📥 安装依赖包..."
    pip3 install -r requirements.txt
fi

# 检查数据库
if [ ! -f "telegram_system.db" ]; then
    echo "🗄️  初始化数据库..."
    python3 init_db.py
fi

# 启动系统
echo "🎯 启动系统..."
python3 main.py