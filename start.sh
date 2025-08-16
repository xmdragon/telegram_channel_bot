#!/bin/bash

# Telegram 消息审核系统启动脚本

set -e

# 显示帮助信息
show_help() {
    echo "🚀 Telegram消息采集审核系统 - 生产环境启动器"
    echo ""
    echo "用法: $0 [OPTIONS]"
    echo ""
    echo "选项:"
    echo "  --help, -h    显示此帮助信息"
    echo ""
    echo "功能:"
    echo "  • 自动检查并创建虚拟环境"
    echo "  • 安装Python依赖包"
    echo "  • 启动Redis缓存服务"
    echo "  • 启动完整的服务分离架构"
    echo "  • 提供详细的日志文件路径"
    echo ""
    echo "服务架构:"
    echo "  ├── Web服务器        (端口8000)"
    echo "  ├── Telegram采集服务  (消息收集)"
    echo "  ├── 消息调度服务      (定时任务)"
    echo "  └── 进程管理器        (服务监控)"
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
    echo "Web界面: http://localhost:8000"
    echo ""
}

# 解析命令行参数
while [[ $# -gt 0 ]]; do
    case $1 in
        --help|-h)
            show_help
            exit 0
            ;;
        *)
            echo "❌ 未知参数: $1"
            echo "使用 --help 查看帮助信息"
            exit 1
            ;;
    esac
done

echo "🚀 启动 Telegram 消息审核系统..."

# 检查虚拟环境
if [ ! -d "venv" ]; then
    echo "📦 创建虚拟环境..."
    python3 -m venv venv
fi

# 激活虚拟环境
echo "🔧 激活虚拟环境..."
source venv/bin/activate

# 检查依赖
if [ ! -f "venv/installed.flag" ]; then
    echo "📚 安装依赖..."
    pip install -r requirements.txt
    touch venv/installed.flag
fi

# 创建必要的目录
mkdir -p logs data temp_media

# 设置权限
chmod 755 logs data temp_media

# 检查并启动Redis服务（PostgreSQL已废弃）
echo "🐳 检查Redis服务..."

if ! docker compose ps redis 2>/dev/null | grep -q "running"; then
    echo "📦 启动Redis缓存..."
    docker compose up -d redis
    
    # 等待Redis就绪
    echo "⏳ 等待Redis就绪..."
    for i in {1..10}; do
        if docker exec telegram_bot_redis redis-cli ping > /dev/null 2>&1; then
            echo "✅ Redis已就绪"
            break
        fi
        if [ $i -eq 10 ]; then
            echo "❌ Redis启动超时"
            exit 1
        fi
        sleep 1
    done
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
echo "   - Web查看错误: http://localhost:8000/static/admin.html"
echo
echo "💡 提示："
echo "   - 使用 './stop.sh' 停止所有服务"
echo "   - 使用 './dev.sh --status' 查看服务状态"
echo "   - Web界面: http://localhost:8000"
echo
exec python3 dev_supervisor.py all