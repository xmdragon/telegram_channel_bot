#!/bin/bash

# 开发环境运行脚本（支持服务分离和选择）

set -e

# 🚀 Linus式修复: 强制使用HuggingFace离线模式，避免API限流
export HF_HUB_OFFLINE=1

# 显示帮助信息
show_help() {
    echo "🚀 Telegram消息采集审核系统 - 开发环境管理器"
    echo ""
    echo "用法: $0 [OPTIONS] [SERVICES...]"
    echo ""
    echo "🛠️ 可用服务选项:"
    echo "  all         启动所有服务 (默认)"
    echo "              ├── Web服务器 (端口8000)"
    echo "              ├── Telegram消息采集服务"
    echo "              ├── 消息队列处理器"
    echo "              └── 消息调度和清理服务"
    echo ""
    echo "  web         仅启动Web服务器"
    echo "              • Web界面: http://localhost:8000"
    echo "              • 消息审核、配置管理、系统监控"
    echo ""
    echo "  collector   仅启动Telegram消息采集服务"
    echo "              • 从源频道采集消息"
    echo "              • 内容过滤和去重处理"
    echo "              • 发送到审核群组"
    echo ""
    echo "  processor   仅启动消息队列处理器"
    echo "              • 处理队列中的消息"
    echo "              • 消息保存到存储系统"
    echo "              • 3个工作线程并发处理"
    echo ""
    echo "  scheduler   仅启动消息调度服务"
    echo "              • 自动转发已审核消息"
    echo "              • 定时清理过期数据"
    echo "              • 临时文件管理"
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
    echo "  $0 collector processor  # 启动采集和处理服务"
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
        web|collector|scheduler|processor|all)
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

# 加载进程管理工具
if [[ -f "tools/utils/process_manager.sh" ]]; then
    source tools/utils/process_manager.sh
else
    echo "⚠️  进程管理工具未找到，使用基础模式"
fi

# 启动前检查（智能冲突处理）
if [[ $(type -t smart_startup_check) == function ]]; then
    if ! smart_startup_check "开发环境"; then
        echo "❌ 启动前检查失败，已取消启动"
        exit 1
    fi
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
if [ ! -f "venv/installed.flag" ]; then
    echo "📚 安装依赖..."
    pip install -r requirements.txt
    # 安装开发依赖（如果需要）
    pip install watchdog 2>/dev/null || true
    touch venv/installed.flag
fi

# 创建必要的目录
mkdir -p logs data temp_media

# 启动并等待Docker服务就绪（修复启动时序问题）
echo "🐳 启动Docker基础设施服务..."
if [ -f "tools/docker/wait_for_services_simple.sh" ]; then
    echo "📋 使用智能等待机制确保服务就绪"
    if ! bash tools/docker/wait_for_services_simple.sh; then
        echo "❌ Docker服务启动失败"
        exit 1
    fi
else
    # 后备方案：传统启动方式
    echo "⚠️  等待脚本未找到，使用传统启动方式"
    if ! docker compose ps redis 2>/dev/null | grep -q "running"; then
        echo "📦 启动Redis和Nginx..."
        docker compose up -d
    else
        echo "✅ Docker服务已在运行中"
    fi
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
echo "🎯 启动进程管理器..."

# 创建PID文件记录
if [[ $(type -t create_pid_file) == function ]]; then
    # 在后台启动进程管理器，获取PID
    python3 dev_supervisor.py "${SERVICES[@]}" &
    SUPERVISOR_PID=$!
    
    # 创建PID文件
    create_pid_file "dev_supervisor" "$SUPERVISOR_PID"
    
    # 设置退出陷阱，确保清理PID文件
    trap 'cleanup_pid_file "dev_supervisor"; kill -TERM $SUPERVISOR_PID 2>/dev/null || true' EXIT INT TERM
    
    # 等待进程管理器
    wait $SUPERVISOR_PID
else
    # 降级为直接启动
    exec python3 dev_supervisor.py "${SERVICES[@]}"
fi