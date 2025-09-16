#!/bin/bash

# 开发环境运行脚本（支持服务分离和选择）

set -e

# 🔧 修复: 全局禁用作业控制，避免"Killed"消息
set +m  # 禁用作业控制消息

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
    echo "  $0                    # 启动所有服务（后台运行）"
    echo "  $0 web               # 仅启动Web服务（后台运行）"
    echo "  $0 web collector     # 启动Web和采集服务（后台运行）"
    echo "  $0 collector scheduler  # 启动采集和调度服务（后台运行）"
    echo "  $0 --status          # 查看服务状态"
    echo ""
    echo "服务管理:"
    echo "  启动后服务在后台运行，终端可继续使用"
    echo "  使用 ./stop.sh 停止所有服务"
    echo "  使用 ./dev.sh --status 实时查看服务状态"
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

# 检查基础设施服务状态
echo "🔍 检查基础设施服务..."

# 快速检查Redis和Nginx状态
INFRA_OK=true
if ! redis-cli ping >/dev/null 2>&1; then
    echo "❌ Redis未运行"
    INFRA_OK=false
else
    echo "✅ Redis运行正常"
fi

if ! curl -s http://localhost:${NGINX_PORT}/static/favicon.svg >/dev/null 2>&1; then
    echo "❌ Nginx未运行"
    INFRA_OK=false
else
    echo "✅ Nginx运行正常"
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

# 优雅的进程管理和信号处理
graceful_shutdown() {
    echo "🛑 收到停止信号，正在优雅关闭服务..."
    if [[ -n "$SUPERVISOR_PID" ]] && kill -0 "$SUPERVISOR_PID" 2>/dev/null; then
        # 发送优雅停止信号
        kill -TERM "$SUPERVISOR_PID" 2>/dev/null || true
        
        # 等待优雅关闭
        local timeout=10
        for i in $(seq 1 $timeout); do
            if ! kill -0 "$SUPERVISOR_PID" 2>/dev/null; then
                echo "✅ 服务已优雅停止"
                break
            fi
            sleep 1
        done
        
        # 如果仍在运行，强制停止
        if kill -0 "$SUPERVISOR_PID" 2>/dev/null; then
            kill -9 "$SUPERVISOR_PID" 2>/dev/null || true
        fi
    fi
    
    # 清理PID文件
    [[ $(type -t cleanup_pid_file) == function ]] && cleanup_pid_file "dev_supervisor"
    exit 0
}

# 创建PID文件记录
if [[ $(type -t create_pid_file) == function ]]; then
    # 🔧 修复: 抑制不友好的进程终止输出
    # 启动进程管理器，禁用作业控制避免"Killed: 9"消息
    (
        set +m  # 禁用作业控制消息
        source venv/bin/activate && python3 dev_supervisor.py ${SERVICES[*]} >/dev/null 2>&1
    ) &
    SUPERVISOR_PID=$!
    
    # 创建PID文件
    create_pid_file "dev_supervisor" "$SUPERVISOR_PID"
    
    # 设置优雅的信号处理器
    trap 'graceful_shutdown' EXIT INT TERM
    
    # 等待服务启动完成（减少等待时间）
    echo "⏳ 等待服务启动..."
    sleep 1
    
    # 检查服务状态
    if kill -0 $SUPERVISOR_PID 2>/dev/null; then
        echo "✅ 开发环境已启动！"
        echo ""
        echo "🎯 服务管理："
        echo "   停止服务: ./stop.sh"
        echo "   查看状态: ./dev.sh --status"
        echo "   查看日志: tail -f logs/app.log"
        echo "   Web界面: ${API_URL}"
        echo ""
        echo "💡 服务已在后台运行，终端可继续使用"
        
        # 使用disown分离进程，避免Bash跟踪
        disown $SUPERVISOR_PID 2>/dev/null || true
        
        # 清理陷阱（服务已在后台运行，不需要前台等待）
        trap - EXIT INT TERM
        
        # 正常退出，让服务在后台继续运行
        exit 0
    else
        echo "❌ 服务启动失败"
        exit 1
    fi
else
    # 解决方案：简单直接
    # "Complex is bad. Simple is good."
    exec venv/bin/python3 dev_supervisor.py ${SERVICES[*]} 2>/dev/null
fi