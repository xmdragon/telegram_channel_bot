#!/bin/bash

# 使用项目内的Supervisor配置重启所有服务

echo "🔄 重启 Telegram 消息审核系统..."

# 先停止
./stop.sh

# 等待一下确保服务完全停止
echo "⏳ 等待服务完全停止..."
sleep 2

# 再启动
./start.sh