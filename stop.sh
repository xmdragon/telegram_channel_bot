#!/bin/bash

# 使用项目内的Supervisor配置停止所有服务

echo "🛑 停止 Telegram 消息审核系统..."

# 检查supervisord是否运行
if [ -f "supervisord.pid" ]; then
    PID=$(cat supervisord.pid)
    if ps -p $PID > /dev/null 2>&1; then
        echo "📦 停止所有服务..."
        supervisorctl -c config/supervisord.conf stop telegram:*

        echo "📦 关闭Supervisor..."
        supervisorctl -c config/supervisord.conf shutdown

        # 等待进程完全退出
        sleep 2
    else
        echo "⚠️  Supervisor进程不存在，清理残留文件..."
    fi

    # 清理PID和SOCK文件
    rm -f supervisord.pid
    rm -f supervisor.sock
else
    echo "⚠️  Supervisor未运行"
fi

# 检查并终止可能残留的Python进程
echo "🔍 检查残留进程..."
for script in web_server.py message_collector.py message_scheduler.py; do
    PIDS=$(pgrep -f $script)
    if [ ! -z "$PIDS" ]; then
        echo "  终止 $script (PID: $PIDS)"
        kill $PIDS 2>/dev/null
    fi
done

echo "✅ 所有服务已停止"