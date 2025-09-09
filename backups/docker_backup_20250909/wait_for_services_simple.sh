#!/bin/bash
# Docker服务启动时序检查脚本（简化版）
# 等待Docker容器启动并可用后再启动Python服务
# 无外部依赖，纯bash实现

set -euo pipefail

# URL配置: 环境变量支持，消除硬编码
BASE_URL=${BASE_URL:-"http://localhost:8080"}
API_URL=${API_URL:-"http://localhost:8000"}

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 日志函数
log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# 检查Docker是否运行
check_docker() {
    if ! command -v docker &> /dev/null; then
        log_error "Docker未安装"
        exit 1
    fi
    
    if ! docker info &> /dev/null; then
        log_error "Docker未运行"
        exit 1
    fi
    
    log_info "Docker运行正常"
}

# 确定compose命令
get_compose_cmd() {
    if docker compose version &> /dev/null; then
        echo "docker compose"
    elif command -v docker-compose &> /dev/null; then
        echo "docker-compose"
    else
        log_error "docker compose未找到"
        exit 1
    fi
}

# 启动服务
start_services() {
    local compose_cmd="$1"
    
    log_info "启动Docker服务..."
    $compose_cmd up -d
    
    if [ $? -ne 0 ]; then
        log_error "Docker服务启动失败"
        exit 1
    fi
    
    log_success "Docker服务启动成功"
}

# 等待容器运行
wait_for_container() {
    local container_name="$1"
    local max_wait=60
    local count=0
    
    log_info "等待容器 $container_name 启动..."
    
    while [ $count -lt $max_wait ]; do
        if docker ps --filter "name=$container_name" --filter "status=running" --format "{{.Names}}" | grep -q "^${container_name}$"; then
            log_success "容器 $container_name 已启动"
            return 0
        fi
        
        ((count++))
        printf "."
        sleep 1
    done
    
    echo
    log_error "容器 $container_name 启动超时"
    return 1
}

# 测试Redis连接
test_redis() {
    local max_attempts=30
    local attempt=0
    
    log_info "测试Redis连接..."
    
    while [ $attempt -lt $max_attempts ]; do
        # 直接使用docker exec测试Redis
        if docker exec telegram_bot_redis redis-cli ping 2>/dev/null | grep -q "PONG"; then
            log_success "Redis连接成功"
            return 0
        fi
        
        ((attempt++))
        printf "."
        sleep 1
    done
    
    echo
    log_error "Redis连接测试失败"
    return 1
}

# 测试Nginx
test_nginx() {
    local max_attempts=30
    local attempt=0
    
    log_info "测试Nginx服务..."
    
    while [ $attempt -lt $max_attempts ]; do
        # 使用curl测试nginx（如果可用）
        if command -v curl &> /dev/null; then
            if curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/static/favicon.svg" 2>/dev/null | grep -q "200"; then
                log_success "Nginx HTTP测试成功"
                return 0
            fi
        # 否则使用wget测试
        elif command -v wget &> /dev/null; then
            if wget --quiet --tries=1 --spider "${BASE_URL}/static/favicon.svg" 2>/dev/null; then
                log_success "Nginx HTTP测试成功"
                return 0
            fi
        # 最后使用docker exec测试nginx配置
        else
            if docker exec telegram_bot_nginx nginx -t 2>/dev/null; then
                log_success "Nginx配置测试成功"
                return 0
            fi
        fi
        
        ((attempt++))
        printf "."
        sleep 1
    done
    
    echo
    log_warning "Nginx测试未通过，但继续运行"
    return 0  # 不阻塞启动
}

# 显示服务状态
show_status() {
    local compose_cmd="$1"
    
    log_info "服务状态:"
    echo "Redis容器: $(docker ps --filter "name=telegram_bot_redis" --format "{{.Status}}")"
    echo "Nginx容器: $(docker ps --filter "name=telegram_bot_nginx" --format "{{.Status}}")"
    echo
}

# 主函数
main() {
    echo "🐳 Docker服务等待脚本（简化版）"
    echo "================================="
    
    # 基础检查
    check_docker
    
    # 获取compose命令
    local compose_cmd
    compose_cmd=$(get_compose_cmd)
    log_info "使用: $compose_cmd"
    
    # 启动服务
    start_services "$compose_cmd"
    
    # 等待容器启动
    wait_for_container "telegram_bot_redis"
    wait_for_container "telegram_bot_nginx"
    
    # 功能测试
    test_redis
    test_nginx
    
    # 显示最终状态
    show_status "$compose_cmd"
    
    log_success "✅ Docker服务已就绪"
    echo
}

# 执行
main "$@"