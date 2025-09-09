#!/bin/bash

# Telegram 消息审核系统启动脚本 - 本地服务版本
# 使用本地Redis和Nginx，不依赖Docker

set -e

# 🚀 Linus式修复: 强制使用HuggingFace离线模式，避免API限流
export HF_HUB_OFFLINE=1

# 🔧 PyTorch MPS修复: 禁用MPS后端避免多进程Fork崩溃
export PYTORCH_ENABLE_MPS_FALLBACK=1
export PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.0

# 🌐 URL配置: 环境变量支持，消除硬编码
export BASE_URL=${BASE_URL:-"http://localhost:8080"}
export API_URL=${API_URL:-"http://localhost:8000"}

# 显示帮助信息
show_help() {
    echo "🚀 Telegram消息采集审核系统 - 本地服务启动器"
    echo ""
    echo "用法: $0 [OPTIONS]"
    echo ""
    echo "选项:"
    echo "  --help, -h         显示此帮助信息"
    echo "  --skip-deps        跳过依赖检查和安装"
    echo "  --force-reinstall  强制重新安装依赖"
    echo "  --verbose, -v      显示详细启动信息"
    echo "  --quick, -q        快速启动模式（跳过等待）"
    echo ""
    echo "🏗️ 本地服务架构:"
    echo "  ├── 🍺 Redis (Homebrew)      (端口6379)"
    echo "  │   • 高性能内存数据库"
    echo "  │   • 消息缓存和会话管理"
    echo "  │"
    echo "  ├── 🌐 Nginx (Homebrew)      (端口8080)"
    echo "  │   • 静态文件服务: ${BASE_URL}"
    echo "  │   • API反向代理到FastAPI"
    echo "  │"
    echo "  ├── 🐍 FastAPI应用           (端口8000)"
    echo "  │   • REST API和WebSocket"
    echo "  │   • 业务逻辑处理"
    echo "  │"
    echo "  ├── 📡 Telegram采集服务      (消息收集)"
    echo "  │   • 从源频道采集消息"
    echo "  │   • 内容过滤和去重处理"
    echo "  │"
    echo "  ├── ⏰ 消息调度服务          (定时任务)"
    echo "  │   • 自动转发已审核消息"
    echo "  │   • 定时清理过期数据"
    echo "  │"
    echo "  └── 🎛️ 进程管理器            (服务监控)"
    echo "      • 管理所有服务进程"
    echo "      • 自动重启和健康检查"
    echo ""
    echo "💡 注意: 使用本地服务，无需Docker，更稳定更快速"
    echo ""
    echo "日志文件:"
    echo "  • Web服务: ./logs/app.log"
    echo "  • 采集服务: ./logs/telegram_collector.log"
    echo "  • 调度服务: ./logs/message_scheduler.log"
    echo "  • 错误日志: ./logs/error.log"
    echo "  • 管理器状态: ./logs/supervisor_status.json"
    echo ""
    echo "相关命令:"
    echo "  ./stop_native.sh          停止所有服务"
    echo "  ./restart_native.sh       重启所有服务"
    echo "  ./dev.sh                  开发模式启动"
    echo "  ./dev.sh --status         查看服务状态"
    echo ""
    echo "Web界面: ${BASE_URL}"
    echo ""
}

# 解析命令行参数
SKIP_DEPS=false
FORCE_REINSTALL=false
VERBOSE=false
QUICK_MODE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --help|-h)
            show_help
            exit 0
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
        *)
            echo "❌ 未知参数: $1"
            echo "使用 --help 查看帮助信息"
            exit 1
            ;;
    esac
done

echo "🚀 启动 Telegram 消息审核系统 (本地服务版)..."

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

# 启动本地服务
echo "🍺 启动本地Redis和Nginx服务..."

# 检查服务状态
if ! brew services list | grep -q "redis.*started"; then
    echo "📦 启动Redis..."
    brew services start redis
else
    [ "$VERBOSE" = true ] && echo "✅ Redis已在运行"
fi

if ! brew services list | grep -q "nginx.*started"; then
    echo "🌐 启动Nginx..."
    brew services start nginx
else
    [ "$VERBOSE" = true ] && echo "✅ Nginx已在运行"
fi

# 验证服务状态
echo "🔧 验证服务状态..."
if ! redis-cli ping >/dev/null 2>&1; then
    echo "❌ Redis连接失败"
    exit 1
fi
echo "✅ Redis连接正常"

if ! curl -s http://localhost:8080/static/favicon.svg >/dev/null 2>&1; then
    echo "❌ Nginx静态文件服务异常"
    exit 1
fi
echo "✅ Nginx服务正常"

echo "🌟 启动应用..."
echo "📊 日志文件："
echo "   - Web服务: ./logs/app.log"
echo "   - 采集服务: ./logs/telegram_collector.log"
echo "   - 调度服务: ./logs/message_scheduler.log"
echo "   - 管理器状态: ./logs/supervisor_status.json"
echo "   - 错误日志: ./logs/error.log (仅WARNING和ERROR)"
echo "   - Web查看错误: ${BASE_URL}/static/admin.html"
echo
echo "💡 提示："
echo "   - 使用 './stop_native.sh' 停止所有服务"
echo "   - 使用 './dev.sh --status' 查看服务状态"
echo "   - Web界面: ${BASE_URL}"
echo

echo "🔧 启动应用进程管理器..."
exec python3 dev_supervisor.py all