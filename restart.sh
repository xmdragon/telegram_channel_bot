#!/bin/bash

# Telegram 消息审核系统重启脚本

# 显示帮助信息
show_help() {
    echo "🔄 Telegram消息采集审核系统 - 服务重启器"
    echo ""
    echo "用法: $0 [OPTIONS]"
    echo ""
    echo "选项:"
    echo "  --help, -h     显示此帮助信息"
    echo "  --quick, -q    快速重启（跳过状态检查和等待）"
    echo "  --force, -f    强制重启（强制停止进程）"
    echo "  --keep-redis   重启时保持Redis服务不变"
    echo "  --skip-logs    跳过日志统计显示"
    echo "  --verbose, -v  显示详细重启信息"
    echo ""
    echo "功能:"
    echo "  • 安全停止所有服务"
    echo "  • 重启Redis缓存服务"
    echo "  • 检查系统状态"
    echo "  • 启动完整服务架构"
    echo ""
    echo "🔄 重启流程和服务说明:"
    echo "  1️⃣ 停止所有服务进程"
    echo "      🎛️ 进程管理器 → 🌐 Web服务器 → 📡 采集服务 → ⏰ 调度服务"
    echo ""
    echo "  2️⃣ 重启Redis缓存服务"
    echo "      🗄️ 数据存储和缓存服务重新启动"
    echo ""
    echo "  3️⃣ 检查系统状态"
    echo "      📊 历史错误统计、💾 磁盘使用情况"
    echo ""
    echo "  4️⃣ 启动所有服务"
    echo "      🌐 Web界面(8000) → 📡 消息采集 → ⏰ 定时调度"
    echo ""
    echo "🛠️ 涉及的服务组件:"
    echo "  • Web服务器: 消息审核、配置管理界面"
    echo "  • 采集服务: Telegram消息收集和过滤"
    echo "  • 调度服务: 自动转发和数据清理"
    echo "  • Redis缓存: 数据存储和会话管理"
    echo ""
    echo "状态检查:"
    echo "  • 历史日志错误统计"
    echo "  • 存储空间使用情况"
    echo "  • Redis连接状态"
    echo ""
    echo "相关命令:"
    echo "  ./start.sh            启动所有服务"
    echo "  ./stop.sh             停止所有服务"
    echo "  ./dev.sh --status     查看服务状态"
    echo ""
    echo "Web界面: http://localhost:8000"
    echo ""
}

# 解析命令行参数
QUICK_MODE=false
FORCE_RESTART=false
KEEP_REDIS=false
SKIP_LOGS=false
VERBOSE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --help|-h)
            show_help
            exit 0
            ;;
        --quick|-q)
            QUICK_MODE=true
            shift
            ;;
        --force|-f)
            FORCE_RESTART=true
            shift
            ;;
        --keep-redis)
            KEEP_REDIS=true
            shift
            ;;
        --skip-logs)
            SKIP_LOGS=true
            shift
            ;;
        --verbose|-v)
            VERBOSE=true
            shift
            ;;
        *)
            echo "❌ 未知参数: $1"
            echo "使用 --help 查看帮助信息"
            exit 1
            ;;
    esac
done

echo "🔄 重启 Telegram 消息审核系统..."
echo

# 加载进程管理工具
if [[ -f "tools/utils/process_manager.sh" ]]; then
    source tools/utils/process_manager.sh
    [ "$VERBOSE" = true ] && echo "✅ 已加载进程管理工具"
else
    echo "⚠️  进程管理工具未找到，使用基础模式"
fi

# 步骤1：停止现有进程和服务
echo "1️⃣ 停止所有服务..."
STOP_ARGS=""
[ "$FORCE_RESTART" = true ] && STOP_ARGS="$STOP_ARGS --force"
[ "$KEEP_REDIS" = true ] && STOP_ARGS="$STOP_ARGS --keep-redis"
[ "$VERBOSE" = true ] && STOP_ARGS="$STOP_ARGS --verbose" || STOP_ARGS="$STOP_ARGS --quiet"

./stop.sh $STOP_ARGS || true

# 等待进程完全停止，确保清理完成
if [ "$QUICK_MODE" = false ]; then
    echo "⏳ 等待进程完全停止..."
    sleep 5
else
    [ "$VERBOSE" = true ] && echo "⚡ 快速模式：跳过停止等待"
    sleep 1
fi

# 使用智能进程检查和清理
if [[ $(type -t check_system_status) == function ]]; then
    # 智能检查剩余进程
    if ! check_system_status >/dev/null 2>&1; then
        print_warning "检测到剩余进程，进行强制清理..."
        
        # 清理PID文件
        for service in "dev_supervisor" "web_server" "telegram_collector" "message_scheduler"; do
            cleanup_pid_file "$service"
        done
        
        # 强制杀死进程
        pkill -9 -f "dev_supervisor.py" 2>/dev/null || true
        pkill -9 -f "web_server.py" 2>/dev/null || true
        pkill -9 -f "telegram_collector.py" 2>/dev/null || true
        pkill -9 -f "message_scheduler.py" 2>/dev/null || true
        
        # 等待端口释放
        wait_for_port_release 8000 10 || print_warning "端口 8000 未在预期时间内释放"
    else
        print_success "所有进程已正常停止"
    fi
else
    # 降级为原始检查方式
    REMAINING_PROCESSES=$(ps aux | grep -E "(dev_supervisor|web_server|telegram_collector|message_scheduler)" | grep -v grep | wc -l)
    if [ "$REMAINING_PROCESSES" -gt 0 ]; then
        echo "⚠️  仍有 $REMAINING_PROCESSES 个进程未停止，强制清理..."
        pkill -9 -f "dev_supervisor.py" 2>/dev/null || true
        pkill -9 -f "web_server.py" 2>/dev/null || true
        pkill -9 -f "telegram_collector.py" 2>/dev/null || true
        pkill -9 -f "message_scheduler.py" 2>/dev/null || true
        sleep 2
    fi
fi

echo "✅ 所有服务已停止"
echo

# 步骤2：重启Redis服务
if [ "$KEEP_REDIS" = false ]; then
    echo "2️⃣ 重启Redis服务..."
    docker compose restart redis > /dev/null 2>&1 || true
else
    [ "$VERBOSE" = true ] && echo "2️⃣ 保持Redis服务不变..."
fi

# 等待Redis就绪
if [ "$QUICK_MODE" = false ]; then
    echo "⏳ 等待Redis就绪..."
    max_wait=15
    for i in $(seq 1 $max_wait); do
        if docker exec telegram_bot_redis redis-cli ping > /dev/null 2>&1; then
            echo "✅ Redis已就绪"
            break
        fi
        if [ $i -eq $max_wait ]; then
            echo "❌ Redis启动超时，尝试继续启动服务..."
            break
        fi
        sleep 1
    done
else
    [ "$VERBOSE" = true ] && echo "⚡ 快速模式：跳过Redis等待"
fi

echo

# 步骤3：显示系统状态信息
if [ "$SKIP_LOGS" = false ] && [ "$QUICK_MODE" = false ]; then
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
else
    [ "$VERBOSE" = true ] && echo "3️⃣ 跳过系统状态检查..."
fi

echo

# 步骤4：显示磁盘使用情况  
if [ "$SKIP_LOGS" = false ] && [ "$QUICK_MODE" = false ]; then
    LOGS_SIZE=$(du -sh ./logs 2>/dev/null | cut -f1 || echo "未知")
    DATA_SIZE=$(du -sh ./data 2>/dev/null | cut -f1 || echo "未知")
    echo "💾 存储使用: 日志 $LOGS_SIZE, 数据 $DATA_SIZE"
    echo
elif [ "$VERBOSE" = true ]; then
    echo "💾 跳过磁盘使用检查"
    echo
fi

# 步骤5：启动所有服务
echo "4️⃣ 启动所有服务..."
echo

# 构建启动参数
START_ARGS=""
[ "$QUICK_MODE" = true ] && START_ARGS="$START_ARGS --quick"
[ "$VERBOSE" = true ] && START_ARGS="$START_ARGS --verbose"

# 静默启动，避免重复信息
exec ./start.sh $START_ARGS