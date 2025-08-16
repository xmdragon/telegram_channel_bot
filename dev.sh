#!/bin/bash

# 开发环境运行脚本（支持服务分离和选择）

set -e

# 显示帮助信息
show_help() {
    echo "🚀 Telegram消息采集审核系统 - 开发环境管理器"
    echo ""
    echo "用法: $0 [OPTIONS] [SERVICES...]"
    echo ""
    echo "服务选项:"
    echo "  all         启动所有服务 (默认)"
    echo "  web         仅启动Web服务器"
    echo "  collector   仅启动Telegram采集服务"
    echo "  scheduler   仅启动消息调度服务"
    echo ""
    echo "其他选项:"
    echo "  --help, -h  显示此帮助信息"
    echo "  --status    显示服务状态"
    echo "  --legacy    使用传统模式启动 (单进程)"
    echo ""
    echo "示例:"
    echo "  $0                    # 启动所有服务"
    echo "  $0 web               # 仅启动Web服务"
    echo "  $0 web collector     # 启动Web和采集服务"
    echo "  $0 --status          # 查看服务状态"
    echo "  $0 --legacy          # 使用传统模式"
    echo ""
}

# 解析命令行参数
SERVICES=()
USE_LEGACY=false
SHOW_STATUS=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --help|-h)
            show_help
            exit 0
            ;;
        --status)
            SHOW_STATUS=true
            shift
            ;;
        --legacy)
            USE_LEGACY=true
            shift
            ;;
        web|collector|scheduler|all)
            SERVICES+=("$1")
            shift
            ;;
        *)
            echo "❌ 未知参数: $1"
            echo "使用 --help 查看帮助信息"
            exit 1
            ;;
    esac
done

# 如果只是查看状态，直接执行
if [ "$SHOW_STATUS" = true ]; then
    echo "📊 查看服务状态..."
    python3 dev_supervisor.py --status
    exit 0
fi

# 如果没有指定服务，默认启动所有服务
if [ ${#SERVICES[@]} -eq 0 ]; then
    SERVICES=("all")
fi

echo "🚀 启动开发模式..."

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
    # 安装开发依赖（如果需要）
    pip install watchdog 2>/dev/null || true
    touch venv/installed.flag
fi

# 创建必要的目录
mkdir -p logs data temp_media

# 检查并启动Redis缓存服务
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


# 如果使用传统模式
if [ "$USE_LEGACY" = true ]; then
    echo "🌟 启动应用（传统模式，单进程）..."
    echo "📝 提示：修改代码后会自动重新加载"
    echo "📊 日志文件："
    echo "   - 完整日志: ./logs/app.log"
    echo "   - 错误日志: ./logs/error.log (仅WARNING和ERROR)"
    echo "   - Web查看错误: http://localhost:8000/static/admin.html"
    echo

    # 检查是否安装了uvicorn
    if python3 -c "import uvicorn" 2>/dev/null; then
        # 使用uvicorn的热重载功能
        exec uvicorn main:app --host 0.0.0.0 --port 8000 --reload
    else
        # 降级为普通启动
        echo "⚠️  未检测到uvicorn，使用普通模式启动（不支持热重载）"
        exec python3 main.py
    fi
fi

# 使用新的服务分离模式
echo "🎯 启动服务分离模式..."
echo "📋 启动服务: ${SERVICES[*]}"
echo ""
echo "📊 日志文件："
echo "   - Web服务: ./logs/app.log"
echo "   - 采集服务: ./logs/telegram_collector.log" 
echo "   - 调度服务: ./logs/message_scheduler.log"
echo "   - 管理器状态: ./logs/supervisor_status.json"
echo ""
echo "💡 提示："
echo "   - 使用 Ctrl+C 停止所有服务"
echo "   - 使用 './dev.sh --status' 查看服务状态"
echo "   - Web界面: http://localhost:8000"
echo ""

# 启动进程管理器
exec python3 dev_supervisor.py "${SERVICES[@]}"