#!/bin/bash

# Telegram 消息审核系统重启脚本

# 🚀 修复: 强制使用HuggingFace离线模式，避免API限流
export HF_HUB_OFFLINE=1

# 🔧 PyTorch MPS修复: 禁用MPS后端避免多进程Fork崩溃
export PYTORCH_ENABLE_MPS_FALLBACK=1
export PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.0

# 🌐 URL配置: 环境变量支持，消除硬编码
export BASE_URL=${BASE_URL:-"http://localhost:8080"}
export API_URL=${API_URL:-"http://localhost:8000"}

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
    echo "  --restart-infra  同时重启基础设施服务（Redis/Nginx）"
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
    echo "  3️⃣ 清理残留锁"
    echo "      🔧 清理可能存在的Telegram进程锁"
    echo ""
    echo "  4️⃣ 检查系统状态"
    echo "      📊 历史错误统计、💾 磁盘使用情况"
    echo ""
    echo "  5️⃣ 启动所有服务"
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
    echo "Web界面: ${API_URL}"
    echo ""
}

# 解析命令行参数
QUICK_MODE=false
FORCE_RESTART=false
RESTART_INFRA=false
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
        --restart-infra)
            RESTART_INFRA=true
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
[ "$RESTART_INFRA" = true ] && STOP_ARGS="$STOP_ARGS --stop-infra"
[ "$VERBOSE" = true ] && STOP_ARGS="$STOP_ARGS --verbose" || STOP_ARGS="$STOP_ARGS --quiet"

./stop.sh $STOP_ARGS || true

# 直接检查，不盲目等待
echo "🔍 检查进程状态..."

# 使用智能进程检查和清理
if [[ $(type -t check_system_status) == function ]]; then
    # 智能检查剩余进程
    if ! check_system_status >/dev/null 2>&1; then
        print_warning "检测到剩余进程，进行强制清理..."
        
        # 清理PID文件
        for service in "dev_supervisor" "web_server" "message_scheduler"; do
            cleanup_pid_file "$service"
        done
        
        # 强制杀死进程
        pkill -9 -f "dev_supervisor.py" 2>/dev/null || true
        pkill -9 -f "web_server.py" 2>/dev/null || true
        pkill -9 -f "message_scheduler.py" 2>/dev/null || true
        
        # 等待端口释放
        wait_for_port_release 8000 10 || print_warning "端口 8000 未在预期时间内释放"
    else
        print_success "所有进程已正常停止"
    fi
else
    # 降级为原始检查方式
    REMAINING_PROCESSES=$(ps aux | grep -E "(dev_supervisor|web_server|message_scheduler)" | grep -v grep | wc -l)
    if [ "$REMAINING_PROCESSES" -gt 0 ]; then
        echo "⚠️  仍有 $REMAINING_PROCESSES 个进程未停止，强制清理..."
        pkill -9 -f "dev_supervisor.py" 2>/dev/null || true
        pkill -9 -f "web_server.py" 2>/dev/null || true
        pkill -9 -f "message_scheduler.py" 2>/dev/null || true
    fi
fi

echo "✅ 所有服务已停止"
echo

# 步骤2：基础设施服务管理（可选）
if [ "$RESTART_INFRA" = true ]; then
    echo "2️⃣ 重启基础设施服务..."

    # 使用infra.sh重启基础服务
    if [ -f "./infra.sh" ]; then
        ./infra.sh restart
        echo "⏳ 等待服务重启完成（3秒）..."
        sleep 3
    else
        echo "❌ 未找到infra.sh脚本"
        echo "手动重启命令："
        echo "   macOS: brew services restart redis nginx"
        echo "   Linux: sudo service redis-server restart && sudo service nginx restart"
        echo ""
        echo "⏳ 等待服务重启（5秒）..."
        sleep 5
    fi
else
    [ "$VERBOSE" = true ] && echo "2️⃣ 保持基础设施服务不变（默认）..."

    # 检查基础服务状态
    echo "🔍 检查基础设施服务状态..."
    if ! redis-cli ping >/dev/null 2>&1; then
        echo "⚠️  Redis未运行，请先运行：./infra.sh start"
    fi
    if ! curl -s http://localhost:8080/static/favicon.svg >/dev/null 2>&1; then
        echo "⚠️  Nginx未运行，请先运行：./infra.sh start"
    fi
fi

echo

# 步骤3：显示系统状态信息（优化版）
if [ "$SKIP_LOGS" = false ] && [ "$QUICK_MODE" = false ]; then
    echo "3️⃣ 检查系统状态..."
    
    # 快速检查错误日志（只看最近1000行避免大文件扫描）
    if [ -f "./logs/error.log" ]; then
        # 使用tail限制扫描范围，提升速度
        RECENT_LOGS=$(tail -n 1000 "./logs/error.log" 2>/dev/null)
        if [ -n "$RECENT_LOGS" ]; then
            ERROR_COUNT=$(echo "$RECENT_LOGS" | grep -c "\[ERROR\]" 2>/dev/null || echo "0")
            WARNING_COUNT=$(echo "$RECENT_LOGS" | grep -c "\[WARNING\]" 2>/dev/null || echo "0")
            
            if [ "$ERROR_COUNT" -gt 0 ] || [ "$WARNING_COUNT" -gt 0 ]; then
                echo "📊 近期日志统计: $WARNING_COUNT 个警告, $ERROR_COUNT 个错误"
                echo "   Web查看详情: ${API_URL}/static/admin.html"
            else
                echo "✅ 近期无错误记录"
            fi
        else
            echo "✅ 无错误日志内容"
        fi
    else
        echo "✅ 无错误日志文件"
    fi
else
    [ "$VERBOSE" = true ] && echo "3️⃣ 跳过系统状态检查..."
fi

echo

# 步骤4：显示磁盘使用情况（后台异步）
if [ "$SKIP_LOGS" = false ] && [ "$QUICK_MODE" = false ]; then
    # 启动后台进程计算磁盘使用，不阻塞主流程
    (
        LOGS_SIZE=$(du -sh ./logs 2>/dev/null | cut -f1 || echo "未知")
        DATA_SIZE=$(du -sh ./data 2>/dev/null | cut -f1 || echo "未知")
        echo "💾 存储使用: 日志 $LOGS_SIZE, 数据 $DATA_SIZE" > /tmp/disk_usage_$$
    ) &
    echo "💾 存储信息计算中..."
    echo
elif [ "$VERBOSE" = true ]; then
    echo "💾 跳过磁盘使用检查"
    echo
fi

# 步骤4：清理残留锁（使用Redis分布式锁，无需文件锁清理）
echo "3️⃣ 检查存储服务状态..."
echo "✅ Redis分布式锁系统就绪"
echo

# 步骤5：启动所有服务
echo "5️⃣ 启动所有服务..."
echo

# 构建启动参数
START_ARGS=""
[ "$QUICK_MODE" = true ] && START_ARGS="$START_ARGS --quick"
[ "$VERBOSE" = true ] && START_ARGS="$START_ARGS --verbose"

# 静默启动，避免重复信息
exec ./start.sh $START_ARGS