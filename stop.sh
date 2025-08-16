#!/bin/bash

# Telegram 消息审核系统停止脚本

echo "🛑 停止 Telegram 消息审核系统..."

# 停止服务分离架构的所有服务
echo "📍 查找并停止所有服务进程..."

# 函数：停止进程并等待
stop_process() {
    local process_name="$1"
    local pattern="$2"
    local timeout="${3:-10}"
    
    echo "🔍 查找 $process_name 进程..."
    local pids=$(ps aux | grep "$pattern" | grep -v grep | awk '{print $2}')
    
    if [ -z "$pids" ]; then
        echo "   ✅ 未找到 $process_name 进程"
        return 0
    fi
    
    echo "   📍 找到 $process_name 进程: $pids"
    
    # 发送TERM信号进行优雅关闭
    for pid in $pids; do
        if kill -0 $pid 2>/dev/null; then
            echo "   🛑 向进程 $pid 发送停止信号..."
            kill -TERM $pid 2>/dev/null || true
        fi
    done
    
    # 等待进程优雅关闭
    echo "   ⏳ 等待进程优雅关闭 (最多 ${timeout}秒)..."
    for i in $(seq 1 $timeout); do
        local remaining_pids=""
        for pid in $pids; do
            if kill -0 $pid 2>/dev/null; then
                remaining_pids="$remaining_pids $pid"
            fi
        done
        
        if [ -z "$remaining_pids" ]; then
            echo "   ✅ $process_name 进程已正常停止"
            return 0
        fi
        
        sleep 1
    done
    
    # 如果还有进程，强制终止
    for pid in $pids; do
        if kill -0 $pid 2>/dev/null; then
            echo "   ⚠️  强制终止进程 $pid..."
            kill -9 $pid 2>/dev/null || true
        fi
    done
    
    sleep 1
    echo "   ✅ $process_name 进程已强制停止"
}

# 按依赖顺序停止服务
stop_process "进程管理器" "dev_supervisor.py" 5
stop_process "Web服务器" "web_server.py" 5  
stop_process "Telegram采集服务" "telegram_collector.py" 8
stop_process "消息调度服务" "message_scheduler.py" 5

# 额外清理：使用pkill确保所有相关进程都被停止
echo "🧹 执行最终清理..."
pkill -f "dev_supervisor.py" 2>/dev/null || true
pkill -f "web_server.py" 2>/dev/null || true  
pkill -f "telegram_collector.py" 2>/dev/null || true
pkill -f "message_scheduler.py" 2>/dev/null || true
pkill -f "uvicorn.*web_server:app" 2>/dev/null || true

# 兼容旧版本 - 停止main.py进程
MAIN_PID=$(ps aux | grep "[p]ython3 main.py" | awk '{print $2}')
if [ ! -z "$MAIN_PID" ]; then
    echo "📍 停止传统模式进程 PID: $MAIN_PID"
    kill -TERM $MAIN_PID 2>/dev/null || true
fi
pkill -f "python3 main.py" 2>/dev/null || true
pkill -f "uvicorn main:app" 2>/dev/null || true

# 强制清理8000端口占用
PORT_PID=$(lsof -ti:8000 2>/dev/null)
if [ ! -z "$PORT_PID" ]; then
    echo "📍 清理端口8000占用 PID: $PORT_PID"
    kill -9 $PORT_PID 2>/dev/null || true
fi

echo "✅ 所有服务进程已停止"

echo "🐳 停止Redis服务..."
docker compose stop redis 2>/dev/null || true

echo "🔧 清理完成"