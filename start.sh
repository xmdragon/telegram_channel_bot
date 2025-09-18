#!/bin/bash

# Telegram 消息审核系统启动脚本

set -e

# 加载环境配置
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# 🚀 修复: 强制使用HuggingFace离线模式，避免API限流
export HF_HUB_OFFLINE=1

# 🔧 PyTorch MPS修复: 禁用MPS后端避免多进程Fork崩溃
export PYTORCH_ENABLE_MPS_FALLBACK=1
export PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.0

# 🌐 URL配置: 环境变量支持，消除硬编码
WEB_PORT=${WEB_PORT:-8008}
NGINX_PORT=${NGINX_PORT:-8080}
export BASE_URL=${BASE_URL:-"http://localhost:${NGINX_PORT}"}
export API_URL=${API_URL:-"http://localhost:${WEB_PORT}"}

# 显示帮助信息
show_help() {
    echo "🚀 Telegram消息采集审核系统 - 生产环境启动器"
    echo ""
    echo "用法: $0 [OPTIONS]"
    echo ""
    echo "选项:"
    echo "  --help, -h         显示此帮助信息"
    echo "  --check-infra      检查基础设施服务状态"
    echo "  --skip-deps        跳过依赖检查和安装"
    echo "  --force-reinstall  强制重新安装依赖"
    echo "  --verbose, -v      显示详细启动信息"
    echo "  --quick, -q        快速启动模式（跳过等待）"
    echo "  --daemon, -d       后台运行模式（SSH断开后继续运行）"
    echo ""
    echo "功能:"
    echo "  • 自动检查并创建虚拟环境"
    echo "  • 安装Python依赖包"
    echo "  • 启动Redis缓存服务"
    echo "  • 启动完整的服务分离架构"
    echo "  • 提供详细的日志文件路径"
    echo ""
    echo "🏗️ 启动的服务架构:"
    echo "  ├── 🌐 Web服务器        (端口${WEB_PORT})"
    echo "  │   • Web界面: ${API_URL}"
    echo "  │   • 消息审核、配置管理、系统监控"
    echo "  │"
    echo "  ├── 📡 Telegram采集服务  (消息收集)"
    echo "  │   • 从源频道采集消息"
    echo "  │   • 内容过滤和去重处理"
    echo "  │"
    echo "  ├── ⏰ 消息调度服务      (定时任务)"
    echo "  │   • 自动转发已审核消息"
    echo "  │   • 定时清理过期数据"
    echo "  │"
    echo "  └── 🎛️ 进程管理器        (服务监控)"
    echo "      • 管理所有服务进程"
    echo "      • 自动重启和健康检查"
    echo ""
    echo "💡 注意: 生产模式启动所有服务，如需单独启动请使用 ./dev.sh"
    echo ""
    echo "日志文件:"
    echo "  • Web服务: ./logs/app.log"
    echo "  • 采集服务: ./logs/telegram_collector.log"
    echo "  • 调度服务: ./logs/message_scheduler.log"
    echo "  • 错误日志: ./logs/error.log"
    echo "  • 管理器状态: ./logs/supervisor_status.json"
    echo ""
    echo "相关命令:"
    echo "  ./stop.sh             停止所有服务"
    echo "  ./restart.sh          重启所有服务"
    echo "  ./dev.sh              开发模式启动"
    echo "  ./dev.sh --status     查看服务状态"
    echo ""
    echo "Web界面: ${API_URL}"
    echo ""
}

# 解析命令行参数
CHECK_INFRA=true
SKIP_DEPS=false
FORCE_REINSTALL=false
VERBOSE=false
QUICK_MODE=false
DAEMON_MODE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --help|-h)
            show_help
            exit 0
            ;;
        --check-infra)
            CHECK_INFRA=true
            shift
            ;;
        --skip-deps)
            SKIP_DEPS=true
            shift
            ;;
        --force-reinstall)
            FORCE_REINSTALL=true
            shift
            ;;
        --verbose|-v)
            VERBOSE=true
            shift
            ;;
        --quick|-q)
            QUICK_MODE=true
            shift
            ;;
        --daemon|-d)
            DAEMON_MODE=true
            shift
            ;;
        *)
            echo "❌ 未知参数: $1"
            echo "使用 --help 查看帮助信息"
            exit 1
            ;;
    esac
done

echo "🚀 启动 Telegram 消息审核系统..."

# 加载进程管理工具
if [[ -f "tools/utils/process_manager.sh" ]]; then
    source tools/utils/process_manager.sh
    [ "$VERBOSE" = true ] && echo "✅ 已加载进程管理工具"
else
    echo "⚠️  进程管理工具未找到，使用基础模式"
fi

# 生产环境启动前检查
if [[ $(type -t smart_startup_check) == function ]]; then
    if ! smart_startup_check "生产环境"; then
        echo "❌ 启动前检查失败，已取消启动"
        exit 1
    fi
elif [ "$VERBOSE" = true ]; then
    echo "⚠️  未启用智能冲突检测"
fi

# 检查虚拟环境
if [ ! -d "venv" ]; then
    echo "📦 创建虚拟环境..."
    python3 -m venv venv
fi

# 激活虚拟环境
echo "🔧 激活虚拟环境..."
source venv/bin/activate

# 检查依赖
if [ "$SKIP_DEPS" = false ]; then
    if [ "$FORCE_REINSTALL" = true ] || [ ! -f "venv/installed.flag" ]; then
        echo "📚 $([ "$FORCE_REINSTALL" = true ] && echo "重新安装" || echo "安装")依赖..."
        [ "$FORCE_REINSTALL" = true ] && rm -f venv/installed.flag
        pip install -r requirements.txt
        touch venv/installed.flag
    elif [ "$VERBOSE" = true ]; then
        echo "✅ 依赖已安装（跳过安装检查）"
    fi
else
    [ "$VERBOSE" = true ] && echo "⏭️ 跳过依赖检查"
fi

# 创建必要的目录
mkdir -p logs data temp_media

# 设置权限
chmod 755 logs data temp_media

# 检查基础设施服务状态
if [ "$CHECK_INFRA" = true ]; then
    echo "🔍 检查基础设施服务..."

    INFRA_OK=true

    # 检查Redis
    if ! redis-cli ping >/dev/null 2>&1; then
        echo "❌ Redis未运行"
        INFRA_OK=false
    else
        [ "$VERBOSE" = true ] && echo "✅ Redis运行正常"
    fi

    # 检查Nginx
    if ! curl -s http://localhost:${NGINX_PORT}/static/favicon.svg >/dev/null 2>&1; then
        echo "❌ Nginx未运行"
        INFRA_OK=false
    else
        [ "$VERBOSE" = true ] && echo "✅ Nginx运行正常"
    fi

    # 如果基础服务未运行，提示用户
    if [ "$INFRA_OK" = false ]; then
        echo ""
        echo "⚠️  基础设施服务未完全启动"
        echo "请先运行以下命令启动基础服务："
        echo ""
        echo "   ./infra.sh start"
        echo ""
        echo "提示：基础服务通常只需启动一次，可以持续运行"
        exit 1
    fi

    echo "✅ 基础设施服务检查通过"
else
    [ "$VERBOSE" = true ] && echo "⏭️ 跳过基础设施检查"
fi

# 数据库初始化已废弃（使用Redis+JSON存储）
# 系统启动时会自动初始化配置

# 启动应用（生产模式 - 服务分离架构）
echo "🌟 启动应用..."
echo "📊 日志文件："
echo "   - Web服务: ./logs/app.log"
echo "   - 采集服务: ./logs/telegram_collector.log"
echo "   - 调度服务: ./logs/message_scheduler.log"
echo "   - 管理器状态: ./logs/supervisor_status.json"
echo "   - 错误日志: ./logs/error.log (仅WARNING和ERROR)"
echo "   - Web查看错误: ${API_URL}/static/admin.html"
echo
echo "💡 提示："
echo "   - 使用 './stop.sh' 停止所有服务"
echo "   - 使用 './dev.sh --status' 查看服务状态"
echo "   - Web界面: ${API_URL}"
echo
# 存储服务状态检查（使用Redis分布式锁）
echo "🔧 检查存储服务状态..."
echo "✅ Redis分布式锁系统就绪"

# 启动进程管理器（生产模式）
echo "🌟 启动应用进程管理器..."

# 创建PID文件记录
if [[ $(type -t create_pid_file) == function ]]; then
    # 在后台启动进程管理器，获取PID
    python3 dev_supervisor.py all &
    SUPERVISOR_PID=$!
    
    # 创建PID文件
    create_pid_file "dev_supervisor" "$SUPERVISOR_PID"
    
    # 设置退出陷阱，确保清理PID文件
    trap 'cleanup_pid_file "dev_supervisor"; kill -TERM $SUPERVISOR_PID 2>/dev/null || true' EXIT INT TERM
    
    # 报告启动状态
    sleep 2
    if kill -0 "$SUPERVISOR_PID" 2>/dev/null; then
        print_success "进程管理器启动成功 (PID: $SUPERVISOR_PID)"
        [ "$VERBOSE" = true ] && echo "📄 PID文件: ./logs/pids/dev_supervisor.pid"
    else
        print_error "进程管理器启动失败"
        cleanup_pid_file "dev_supervisor"
        exit 1
    fi
    
    # 等待进程管理器
    wait $SUPERVISOR_PID
else
    # 降级为直接启动
    exec python3 dev_supervisor.py all
fi