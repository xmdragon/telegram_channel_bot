#!/bin/bash

# Telegram 消息审核系统停止脚本

# 显示帮助信息
show_help() {
    echo "🛑 Telegram消息采集审核系统 - 服务停止器"
    echo ""
    echo "用法: $0 [OPTIONS]"
    echo ""
    echo "选项:"
    echo "  --help, -h       显示此帮助信息"
    echo "  --force, -f      强制停止（跳过优雅关闭）"
    echo "  --keep-redis     保持Redis服务运行"
    echo "  --timeout=SEC    设置停止超时时间（默认10秒）"
    echo "  --verbose, -v    显示详细停止信息"
    echo "  --quiet, -q      静默模式（减少输出）"
    echo ""
    echo "功能:"
    echo "  • 优雅停止所有服务进程"
    echo "  • 强制清理端口占用"
    echo "  • 停止Redis缓存服务"
    echo "  • 兼容传统模式和服务分离架构"
    echo ""
    echo "🔄 停止顺序和服务说明:"
    echo "  1️⃣ 🎛️ 进程管理器 (dev_supervisor.py)"
    echo "      • 服务监控和管理进程"
    echo ""
    echo "  2️⃣ 🌐 Web服务器 (web_server.py)"
    echo "      • 端口8000的Web界面服务"
    echo "      • 消息审核、配置管理界面"
    echo ""
    echo "  3️⃣ 📡 Telegram采集服务 (telegram_collector.py)"
    echo "      • 消息采集和内容过滤"
    echo "      • 从源频道到审核群组"
    echo ""
    echo "  4️⃣ ⏰ 消息调度服务 (message_scheduler.py)"
    echo "      • 自动转发和定时清理"
    echo "      • 数据维护和文件管理"
    echo ""
    echo "  5️⃣ 📊 传统模式进程 (main.py)"
    echo "      • 兼容旧版本单进程模式"
    echo ""
    echo "  6️⃣ 🗄️ Redis缓存服务"
    echo "      • 数据存储和缓存服务"
    echo ""
    echo "超时处理:"
    echo "  • 每个服务最多等待10秒优雅关闭"
    echo "  • 超时后自动强制终止进程"
    echo "  • 清理8000端口占用"
    echo ""
    echo "相关命令:"
    echo "  ./start.sh            启动所有服务"
    echo "  ./restart.sh          重启所有服务"
    echo "  ./dev.sh --status     查看服务状态"
    echo ""
}

# 解析命令行参数
FORCE_STOP=false
KEEP_REDIS=false
TIMEOUT=10
VERBOSE=false
QUIET=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --help|-h)
            show_help
            exit 0
            ;;
        --force|-f)
            FORCE_STOP=true
            shift
            ;;
        --keep-redis)
            KEEP_REDIS=true
            shift
            ;;
        --timeout=*)
            TIMEOUT="${1#*=}"
            if ! [[ "$TIMEOUT" =~ ^[0-9]+$ ]]; then
                echo "❌ 错误：超时时间必须是数字"
                exit 1
            fi
            shift
            ;;
        --verbose|-v)
            VERBOSE=true
            shift
            ;;
        --quiet|-q)
            QUIET=true
            shift
            ;;
        *)
            echo "❌ 未知参数: $1"
            echo "使用 --help 查看帮助信息"
            exit 1
            ;;
    esac
done

echo "🛑 停止 Telegram 消息审核系统..."

# 停止服务分离架构的所有服务
echo "📍 查找并停止所有服务进程..."

# 函数：停止进程并等待
stop_process() {
    local process_name="$1"
    local pattern="$2"
    local timeout="${3:-$TIMEOUT}"
    
    [ "$QUIET" = false ] && echo "🔍 查找 $process_name 进程..."
    local pids=$(ps aux | grep "$pattern" | grep -v grep | awk '{print $2}')
    
    if [ -z "$pids" ]; then
        [ "$VERBOSE" = true ] && echo "   ✅ 未找到 $process_name 进程"
        return 0
    fi
    
    [ "$QUIET" = false ] && echo "   📍 找到 $process_name 进程: $pids"
    
    # 发送TERM信号进行优雅关闭或强制停止
    if [ "$FORCE_STOP" = true ]; then
        [ "$VERBOSE" = true ] && echo "   ⚡ 强制停止模式"
        for pid in $pids; do
            if kill -0 $pid 2>/dev/null; then
                [ "$VERBOSE" = true ] && echo "   🛑 强制终止进程 $pid..."
                kill -9 $pid 2>/dev/null || true
            fi
        done
        [ "$QUIET" = false ] && echo "   ✅ $process_name 进程已强制停止"
        return 0
    else
        for pid in $pids; do
            if kill -0 $pid 2>/dev/null; then
                [ "$VERBOSE" = true ] && echo "   🛑 向进程 $pid 发送停止信号..."
                kill -TERM $pid 2>/dev/null || true
            fi
        done
    fi
    
    # 等待进程优雅关闭
    [ "$QUIET" = false ] && echo "   ⏳ 等待进程优雅关闭 (最多 ${timeout}秒)..."
    for i in $(seq 1 $timeout); do
        local remaining_pids=""
        for pid in $pids; do
            if kill -0 $pid 2>/dev/null; then
                remaining_pids="$remaining_pids $pid"
            fi
        done
        
        if [ -z "$remaining_pids" ]; then
            [ "$QUIET" = false ] && echo "   ✅ $process_name 进程已正常停止"
            return 0
        fi
        
        sleep 1
    done
    
    # 如果还有进程，强制终止
    for pid in $pids; do
        if kill -0 $pid 2>/dev/null; then
            [ "$VERBOSE" = true ] && echo "   ⚠️  强制终止进程 $pid..."
            kill -9 $pid 2>/dev/null || true
        fi
    done
    
    sleep 1
    [ "$QUIET" = false ] && echo "   ✅ $process_name 进程已强制停止"
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

# 停止Redis服务
if [ "$KEEP_REDIS" = false ]; then
    [ "$QUIET" = false ] && echo "🐳 停止Redis服务..."
    docker compose stop redis 2>/dev/null || true
else
    [ "$VERBOSE" = true ] && echo "⏭️ 保持Redis服务运行"
fi

# 清理PID文件
if [[ -d "./logs/pids" ]]; then
    [ "$VERBOSE" = true ] && echo "🗂️ 清理PID文件..."
    rm -f ./logs/pids/*.pid 2>/dev/null || true
    [ "$VERBOSE" = true ] && echo "✅ PID文件已清理"
fi

[ "$QUIET" = false ] && echo "🔧 清理完成"