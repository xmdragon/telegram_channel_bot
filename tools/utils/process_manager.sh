#!/bin/bash

# 进程管理工具函数
# 用于统一处理PID文件、端口检查、进程冲突等

# PID文件目录
PID_DIR="./logs/pids"
mkdir -p "$PID_DIR"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 打印带颜色的消息
print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_info() {
    echo -e "${BLUE}📍 $1${NC}"
}

# 检查端口是否被占用
check_port_usage() {
    local port=$1
    local service_name=${2:-"服务"}
    
    if lsof -ti:$port >/dev/null 2>&1; then
        local pid=$(lsof -ti:$port | head -1)
        local process_info=$(ps -p $pid -o comm= 2>/dev/null)
        
        if [[ -n "$process_info" ]]; then
            print_warning "端口 $port 已被占用"
            print_info "占用进程: $process_info (PID: $pid)"
            
            # 检查是否是我们自己的服务
            if pgrep -f "web_server.py\|uvicorn.*main:app" >/dev/null; then
                print_info "检测到已运行的Web服务，可能是重复启动"
                return 2 # 特殊返回码表示重复启动
            fi
            return 1 # 端口被其他进程占用
        fi
    fi
    return 0 # 端口可用
}

# 检查进程是否已运行
check_process_running() {
    local process_name=$1
    local pid_file="$PID_DIR/${process_name}.pid"
    
    # 检查PID文件是否存在
    if [[ -f "$pid_file" ]]; then
        local pid=$(cat "$pid_file" 2>/dev/null)
        
        # 检查PID是否有效
        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
            print_warning "检测到 $process_name 进程已运行 (PID: $pid)"
            return 1 # 进程已运行
        else
            # PID文件存在但进程不存在，清理PID文件
            rm -f "$pid_file"
            print_info "清理无效的PID文件: $pid_file"
        fi
    fi
    
    # 通过进程名称再次确认
    if pgrep -f "$process_name" >/dev/null; then
        local existing_pid=$(pgrep -f "$process_name" | head -1)
        print_warning "检测到 $process_name 进程已运行 (PID: $existing_pid)"
        
        # 更新PID文件
        echo "$existing_pid" > "$pid_file"
        return 1 # 进程已运行
    fi
    
    return 0 # 进程未运行
}

# 创建PID文件
create_pid_file() {
    local process_name=$1
    local pid=$2
    local pid_file="$PID_DIR/${process_name}.pid"
    
    echo "$pid" > "$pid_file"
    print_success "创建PID文件: $pid_file (PID: $pid)"
}

# 清理PID文件
cleanup_pid_file() {
    local process_name=$1
    local pid_file="$PID_DIR/${process_name}.pid"
    
    if [[ -f "$pid_file" ]]; then
        rm -f "$pid_file"
        print_info "清理PID文件: $pid_file"
    fi
}

# 检查多个关键服务的运行状态
check_system_status() {
    local has_conflicts=false
    
    print_info "检查系统状态..."
    
    # 检查Web服务端口
    if check_port_usage 8000 "Web服务"; then
        print_success "端口 8000 可用"
    else
        local port_result=$?
        if [[ $port_result -eq 2 ]]; then
            print_warning "Web服务可能已在运行"
            has_conflicts=true
        else
            print_error "端口 8000 被其他进程占用"
            has_conflicts=true
        fi
    fi
    
    # 检查进程管理器
    if check_process_running "dev_supervisor.py"; then
        print_success "dev_supervisor 未运行"
    else
        print_warning "dev_supervisor 进程已存在"
        has_conflicts=true
    fi
    
    # 检查各个服务进程
    for service in "web_server.py" "telegram_collector.py" "message_scheduler.py"; do
        if pgrep -f "$service" >/dev/null; then
            local pid=$(pgrep -f "$service" | head -1)
            print_warning "${service%.*} 进程已运行 (PID: $pid)"
            has_conflicts=true
        fi
    done
    
    return $([[ "$has_conflicts" == "true" ]] && echo 1 || echo 0)
}

# 处理冲突提示和用户选择
handle_conflicts() {
    local action=${1:-"启动"}
    
    echo
    print_error "检测到进程冲突或端口占用！"
    echo
    echo "可选操作："
    echo "  1) 停止现有服务并继续启动"
    echo "  2) 查看详细状态"
    echo "  3) 取消操作"
    echo "  4) 强制启动（可能导致问题）"
    echo
    
    while true; do
        read -p "请选择操作 (1-4): " choice
        case $choice in
            1)
                print_info "正在停止现有服务..."
                ./stop.sh --quiet >/dev/null 2>&1 || true
                sleep 3
                
                # 再次检查
                if check_system_status >/dev/null 2>&1; then
                    print_success "现有服务已停止，继续启动"
                    return 0
                else
                    print_warning "部分服务仍在运行，建议手动处理"
                    return 1
                fi
                ;;
            2)
                echo
                print_info "详细系统状态："
                check_system_status
                echo
                echo "运行中的相关进程："
                ps aux | grep -E "(dev_supervisor|web_server|telegram_collector|message_scheduler)" | grep -v grep | head -10
                echo
                echo "端口占用情况："
                lsof -i :8000 2>/dev/null || echo "端口 8000 未被占用"
                echo
                ;;
            3)
                print_info "已取消${action}操作"
                exit 0
                ;;
            4)
                print_warning "强制启动可能导致端口冲突或其他问题"
                return 0
                ;;
            *)
                echo "无效选择，请输入 1-4"
                ;;
        esac
    done
}

# 智能启动检查
smart_startup_check() {
    local service_name=${1:-"系统"}
    
    print_info "进行启动前检查..."
    
    if check_system_status; then
        print_success "系统状态正常，可以安全启动"
        return 0
    else
        print_warning "检测到潜在冲突"
        
        # 给用户选择权
        if [[ -t 0 ]]; then  # 检查是否在交互式终端中
            handle_conflicts "启动$service_name"
        else
            # 非交互式环境，直接返回错误
            print_error "非交互式环境检测到冲突，请手动解决"
            print_info "建议运行: ./stop.sh && sleep 3"
            return 1
        fi
    fi
}

# 获取服务状态摘要
get_status_summary() {
    local web_status="stopped"
    local collector_status="stopped" 
    local scheduler_status="stopped"
    local supervisor_status="stopped"
    
    # 检查各服务状态
    if pgrep -f "web_server.py" >/dev/null; then
        web_status="running"
    fi
    
    if pgrep -f "telegram_collector.py" >/dev/null; then
        collector_status="running"
    fi
    
    if pgrep -f "message_scheduler.py" >/dev/null; then
        scheduler_status="running"
    fi
    
    if pgrep -f "dev_supervisor.py" >/dev/null; then
        supervisor_status="running"
    fi
    
    echo "Web:$web_status Collector:$collector_status Scheduler:$scheduler_status Supervisor:$supervisor_status"
}

# 等待端口释放
wait_for_port_release() {
    local port=$1
    local timeout=${2:-30}
    local wait_time=0
    
    print_info "等待端口 $port 释放..."
    
    while lsof -ti:$port >/dev/null 2>&1; do
        if [[ $wait_time -ge $timeout ]]; then
            print_error "等待端口释放超时（${timeout}秒）"
            return 1
        fi
        
        sleep 1
        ((wait_time++))
        
        if [[ $((wait_time % 5)) -eq 0 ]]; then
            print_info "已等待 ${wait_time}秒..."
        fi
    done
    
    print_success "端口 $port 已释放"
    return 0
}