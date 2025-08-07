#!/bin/bash

# Telegram 消息审核系统重启脚本

echo "🔄 重启 Telegram 消息审核系统..."
echo

# 停止现有进程
./stop.sh

# 等待进程完全停止
sleep 2

echo
echo "🚀 启动系统..."
echo

# 启动新进程
./start.sh