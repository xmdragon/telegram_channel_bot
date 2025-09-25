#!/bin/bash

# 使用项目内的Supervisor配置停止所有服务

echo "🛑 停止 Telegram 消息审核系统..."

# 获取当前目录的绝对路径
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 1. 首先尝试通过supervisorctl正常关闭
if [ -f "logs/supervisord.pid" ] || [ -f "supervisord.pid" ]; then
    # 优先使用logs目录下的pid文件
    PID_FILE="logs/supervisord.pid"
    [ ! -f "$PID_FILE" ] && PID_FILE="supervisord.pid"

    PID=$(cat "$PID_FILE" 2>/dev/null)
    if [ ! -z "$PID" ] && ps -p $PID > /dev/null 2>&1; then
        echo "📦 停止所有服务..."
        supervisorctl -c config/supervisord.conf stop telegram:* 2>/dev/null || true

        echo "📦 关闭Supervisor..."
        supervisorctl -c config/supervisord.conf shutdown 2>/dev/null || true

        # 等待进程正常退出
        sleep 2
    fi
fi

# 2. 强制终止所有supervisord进程（处理多次启动的情况）
echo "🔍 检查所有supervisord进程..."
SUPERVISOR_PIDS=$(pgrep -f "supervisord.*config/supervisord.conf" 2>/dev/null)
if [ ! -z "$SUPERVISOR_PIDS" ]; then
    echo "  发现supervisord进程: $SUPERVISOR_PIDS"
    for PID in $SUPERVISOR_PIDS; do
        echo "  终止supervisord进程: $PID"
        kill -TERM $PID 2>/dev/null || true
    done
    sleep 1

    # 如果还存在，使用KILL信号
    SUPERVISOR_PIDS=$(pgrep -f "supervisord.*config/supervisord.conf" 2>/dev/null)
    if [ ! -z "$SUPERVISOR_PIDS" ]; then
        echo "  强制终止supervisord进程: $SUPERVISOR_PIDS"
        kill -KILL $SUPERVISOR_PIDS 2>/dev/null || true
    fi
fi

# 3. 终止所有相关的Python进程（包括venv下的）
echo "🔍 检查Python服务进程..."
for script in web_server.py message_collector.py message_scheduler.py; do
    # 查找所有匹配的进程（包括通过venv运行的）
    PIDS=$(pgrep -f "$script" 2>/dev/null)
    if [ ! -z "$PIDS" ]; then
        echo "  终止 $script 进程: $PIDS"
        kill -TERM $PIDS 2>/dev/null || true
        sleep 0.5

        # 再次检查，如果还存在则强制终止
        PIDS=$(pgrep -f "$script" 2>/dev/null)
        if [ ! -z "$PIDS" ]; then
            echo "  强制终止 $script: $PIDS"
            kill -KILL $PIDS 2>/dev/null || true
        fi
    fi
done

# 4. 清理端口占用（特别是8008和9001端口）
echo "🔍 检查端口占用..."
for PORT in 8008 9001; do
    # 获取占用端口的进程
    PORT_PIDS=$(lsof -ti:$PORT 2>/dev/null)
    if [ ! -z "$PORT_PIDS" ]; then
        echo "  端口 $PORT 被占用，终止进程: $PORT_PIDS"
        kill -TERM $PORT_PIDS 2>/dev/null || true
        sleep 0.5

        # 如果还占用，强制终止
        PORT_PIDS=$(lsof -ti:$PORT 2>/dev/null)
        if [ ! -z "$PORT_PIDS" ]; then
            echo "  强制终止端口 $PORT 的进程: $PORT_PIDS"
            kill -KILL $PORT_PIDS 2>/dev/null || true
        fi
    fi
done

# 5. 清理所有相关文件
echo "🧹 清理临时文件..."
rm -f supervisord.pid
rm -f logs/supervisord.pid
rm -f supervisor.sock
rm -f logs/supervisor.sock

# 6. 最终检查
echo "🔍 最终进程检查..."
REMAINING_PIDS=$(pgrep -f "supervisord.*config/supervisord.conf|web_server.py|message_collector.py|message_scheduler.py" 2>/dev/null)
if [ ! -z "$REMAINING_PIDS" ]; then
    echo "⚠️  警告：仍有残留进程: $REMAINING_PIDS"
    echo "  尝试强制清理..."
    kill -KILL $REMAINING_PIDS 2>/dev/null || true
else
    echo "✅ 所有服务已完全停止"
fi

# 显示端口状态
echo ""
echo "📊 端口状态检查:"
for PORT in 8008 9001; do
    if lsof -i:$PORT > /dev/null 2>&1; then
        echo "  ❌ 端口 $PORT 仍被占用"
    else
        echo "  ✅ 端口 $PORT 已释放"
    fi
done