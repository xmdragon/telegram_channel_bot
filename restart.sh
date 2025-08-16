#!/bin/bash

# Telegram 消息审核系统重启脚本

echo "🔄 重启 Telegram 消息审核系统..."
echo

# 步骤1：停止现有进程和服务
echo "1️⃣ 停止所有服务..."
./stop.sh > /dev/null 2>&1 || true

# 等待进程完全停止，确保清理完成
echo "⏳ 等待进程完全停止..."
sleep 5

# 二次确认所有进程已停止
REMAINING_PROCESSES=$(ps aux | grep -E "(dev_supervisor|web_server|telegram_collector|message_scheduler)" | grep -v grep | wc -l)
if [ "$REMAINING_PROCESSES" -gt 0 ]; then
    echo "⚠️  仍有 $REMAINING_PROCESSES 个进程未停止，强制清理..."
    pkill -9 -f "dev_supervisor.py" 2>/dev/null || true
    pkill -9 -f "web_server.py" 2>/dev/null || true
    pkill -9 -f "telegram_collector.py" 2>/dev/null || true
    pkill -9 -f "message_scheduler.py" 2>/dev/null || true
    sleep 2
fi

echo "✅ 所有服务已停止"
echo

# 步骤2：重启Redis服务
echo "2️⃣ 重启Redis服务..."
docker compose restart redis > /dev/null 2>&1 || true

# 等待Redis就绪
echo "⏳ 等待Redis就绪..."
for i in {1..15}; do
    if docker exec telegram_bot_redis redis-cli ping > /dev/null 2>&1; then
        echo "✅ Redis已就绪"
        break
    fi
    if [ $i -eq 15 ]; then
        echo "❌ Redis启动超时，尝试继续启动服务..."
        break
    fi
    sleep 1
done

echo

# 步骤3：显示系统状态信息
echo "3️⃣ 检查系统状态..."

# 显示错误日志统计
if [ -f "./logs/error.log" ]; then
    ERROR_COUNT=$(grep -c "\[ERROR\]" "./logs/error.log" 2>/dev/null || echo "0")
    WARNING_COUNT=$(grep -c "\[WARNING\]" "./logs/error.log" 2>/dev/null || echo "0")
    
    # 确保数值有效
    ERROR_COUNT=${ERROR_COUNT:-0}
    WARNING_COUNT=${WARNING_COUNT:-0}
    
    if [ "$ERROR_COUNT" -gt 0 ] || [ "$WARNING_COUNT" -gt 0 ]; then
        echo "📊 历史日志统计: $WARNING_COUNT 个警告, $ERROR_COUNT 个错误"
        echo "   Web查看详情: http://localhost:8000/static/admin.html"
    else
        echo "✅ 无历史错误记录"
    fi
else
    echo "✅ 无错误日志文件"
fi

echo

# 步骤4：显示磁盘使用情况
LOGS_SIZE=$(du -sh ./logs 2>/dev/null | cut -f1 || echo "未知")
DATA_SIZE=$(du -sh ./data 2>/dev/null | cut -f1 || echo "未知")
echo "💾 存储使用: 日志 $LOGS_SIZE, 数据 $DATA_SIZE"
echo

# 步骤5：启动所有服务
echo "4️⃣ 启动所有服务..."
echo

# 静默启动，避免重复信息
exec ./start.sh