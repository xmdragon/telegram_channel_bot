#!/bin/bash

# Colima健康监控启动脚本
# 用法：
#   ./colima_monitor.sh start    # 启动监控
#   ./colima_monitor.sh stop     # 停止监控
#   ./colima_monitor.sh status   # 查看状态
#   ./colima_monitor.sh logs     # 查看日志

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_CMD="python3"
HEALTH_CHECKER="$SCRIPT_DIR/tools/maintenance/colima_health_checker.py"
PID_FILE="$SCRIPT_DIR/logs/colima_monitor.pid"
LOG_FILE="$SCRIPT_DIR/logs/colima_health.log"

# 确保logs目录存在
mkdir -p "$SCRIPT_DIR/logs"

case "$1" in
    start)
        if [ -f "$PID_FILE" ]; then
            PID=$(cat "$PID_FILE")
            if ps -p "$PID" > /dev/null 2>&1; then
                echo "❌ Colima监控已在运行 (PID: $PID)"
                exit 1
            else
                rm "$PID_FILE"
            fi
        fi
        
        echo "🚀 启动Colima健康监控..."
        
        # 后台运行健康检查器
        nohup $PYTHON_CMD "$HEALTH_CHECKER" --interval 30 --max-restarts 3 > /dev/null 2>&1 &
        PID=$!
        echo $PID > "$PID_FILE"
        
        sleep 2
        
        if ps -p "$PID" > /dev/null 2>&1; then
            echo "✅ Colima监控已启动 (PID: $PID)"
            echo "📝 日志文件: $LOG_FILE"
            echo "💡 提示: 使用 './colima_monitor.sh logs' 查看实时日志"
        else
            echo "❌ 启动失败，请检查日志"
            rm -f "$PID_FILE"
            exit 1
        fi
        ;;
        
    stop)
        if [ ! -f "$PID_FILE" ]; then
            echo "❌ Colima监控未运行"
            exit 1
        fi
        
        PID=$(cat "$PID_FILE")
        
        if ps -p "$PID" > /dev/null 2>&1; then
            echo "🛑 停止Colima监控 (PID: $PID)..."
            kill "$PID"
            sleep 2
            
            # 如果进程仍在运行，强制终止
            if ps -p "$PID" > /dev/null 2>&1; then
                kill -9 "$PID"
            fi
            
            rm -f "$PID_FILE"
            echo "✅ Colima监控已停止"
        else
            echo "⚠️  进程已停止，清理PID文件"
            rm -f "$PID_FILE"
        fi
        ;;
        
    status)
        if [ -f "$PID_FILE" ]; then
            PID=$(cat "$PID_FILE")
            
            if ps -p "$PID" > /dev/null 2>&1; then
                echo "✅ Colima监控正在运行 (PID: $PID)"
                
                # 显示Colima和Docker状态
                echo ""
                echo "📊 系统状态:"
                
                # Colima状态（注意colima status输出在stderr中）
                if colima status 2>&1 | grep -iq "running"; then
                    echo "  • Colima: ✅ 运行中"
                else
                    echo "  • Colima: ❌ 未运行"
                fi
                
                # Docker状态
                if docker ps > /dev/null 2>&1; then
                    echo "  • Docker: ✅ 运行中"
                else
                    echo "  • Docker: ❌ 未运行"
                fi
                
                # 显示最近的日志
                echo ""
                echo "📝 最近日志:"
                tail -n 5 "$LOG_FILE" 2>/dev/null | sed 's/^/  /'
            else
                echo "❌ Colima监控未运行 (进程已停止)"
                rm -f "$PID_FILE"
            fi
        else
            echo "❌ Colima监控未运行"
        fi
        ;;
        
    logs)
        if [ -f "$LOG_FILE" ]; then
            echo "📝 实时日志 (Ctrl+C 退出):"
            echo "=" | awk '{printf "%-80s\n", $0}' | tr ' ' '='
            tail -f "$LOG_FILE"
        else
            echo "❌ 日志文件不存在"
        fi
        ;;
        
    restart)
        $0 stop
        sleep 2
        $0 start
        ;;
        
    *)
        echo "Colima健康监控管理工具"
        echo ""
        echo "用法: $0 {start|stop|status|logs|restart}"
        echo ""
        echo "命令:"
        echo "  start    - 启动健康监控"
        echo "  stop     - 停止健康监控"
        echo "  status   - 查看监控状态"
        echo "  logs     - 查看实时日志"
        echo "  restart  - 重启健康监控"
        echo ""
        echo "配置:"
        echo "  检查间隔: 30秒"
        echo "  最大重启次数: 3次/小时"
        echo "  日志位置: $LOG_FILE"
        exit 1
        ;;
esac