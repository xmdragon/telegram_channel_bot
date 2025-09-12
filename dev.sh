#!/bin/bash

# 开发环境运行脚本（支持服务分离和选择）

set -e

# 加载环境配置
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# 🚀 Linus式修复: 强制使用HuggingFace离线模式，避免API限流
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
    echo "🚀 Telegram消息采集审核系统 - 开发环境管理器"
    echo ""
    echo "用法: $0 [OPTIONS] [SERVICES...]"
    echo ""
    echo "🛠️ 可用服务选项:"
    echo "  all         启动所有服务 (默认)"
    echo "              ├── Web服务器 (端口${WEB_PORT})"
    echo "              ├── Telegram消息采集服务"
    echo "              ├── 消息队列处理器"
    echo "              └── 消息调度和清理服务"
    echo ""
    echo "  web         仅启动Web服务器"
    echo "              • Web界面: ${API_URL}"
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
    echo ""
    echo "示例:"
    echo "  $0                    # 启动所有服务"
    echo "  $0 web               # 仅启动Web服务"
    echo "  $0 web collector     # 启动Web和采集服务"
    echo "  $0 collector processor  # 启动采集和处理服务"
    echo "  $0 --status          # 查看服务状态"
    echo ""
}

# 解析命令行参数
SERVICES=()
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
    source venv/bin/activate && python3 dev_supervisor.py --status
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

# 加载跨平台服务管理工具
if [[ -f "tools/utils/service_manager.sh" ]]; then
    source tools/utils/service_manager.sh
else
    echo "⚠️  服务管理工具未找到，使用传统方式"
    # 降级到传统方式
    echo "🍺 启动本地Redis和Nginx服务..."
    
    # 尝试通用的服务启动命令
    if command -v redis-cli &>/dev/null; then
        echo "📦 检查Redis..."
        if ! redis-cli ping >/dev/null 2>&1; then
            echo "⚠️  Redis未运行，请手动启动"
            echo "   macOS: brew services start redis"
            echo "   Linux: sudo service redis-server start"
        else
            echo "✅ Redis已在运行"
        fi
    else
        echo "❌ Redis未安装"
        exit 1
    fi
    
    if ! curl -s http://localhost:8080/static/favicon.svg >/dev/null 2>&1; then
        echo "⚠️  Nginx未运行或配置错误，请检查"
        echo "   macOS: brew services start nginx"
        echo "   Linux: sudo service nginx start"
    else
        echo "✅ Nginx服务正常"
    fi
fi

# 使用服务管理工具启动服务
if [[ $(type -t start_all_services) == function ]]; then
    echo "🚀 启动本地服务..."
    if ! start_all_services true; then
        echo "❌ 服务启动失败"
        show_install_instructions
        exit 1
    fi
else
    # 如果函数不存在，手动检查
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
fi



# 使用新的服务分离模式
echo "🎯 启动服务分离模式..."
echo "📋 启动服务: ${SERVICES[*]}"
echo ""
echo "📊 日志文件："
echo "   - Web服务: ./logs/app.log"
echo "   - 采集服务: ./logs/message_collector.log" 
echo "   - 调度服务: ./logs/message_scheduler.log"
echo "   - 管理器状态: ./logs/supervisor_status.json"
echo ""
echo "💡 提示："
echo "   - 使用 Ctrl+C 停止所有服务"
echo "   - 使用 './dev.sh --status' 查看服务状态"
echo "   - Web界面: ${API_URL}"
echo ""

# 启动进程管理器
echo "🎯 启动进程管理器..."

# 创建PID文件记录
if [[ $(type -t create_pid_file) == function ]]; then
    # 在后台启动进程管理器，获取PID
    source venv/bin/activate && python3 dev_supervisor.py "${SERVICES[@]}" &
    SUPERVISOR_PID=$!
    
    # 创建PID文件
    create_pid_file "dev_supervisor" "$SUPERVISOR_PID"
    
    # 设置退出陷阱，确保清理PID文件
    trap 'cleanup_pid_file "dev_supervisor"; kill -TERM $SUPERVISOR_PID 2>/dev/null || true' EXIT INT TERM
    
    # 等待进程管理器
    wait $SUPERVISOR_PID
else
    # 降级为直接启动
    exec venv/bin/python3 dev_supervisor.py "${SERVICES[@]}"
fi