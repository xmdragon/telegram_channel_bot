#!/bin/bash
"""
Docker服务启动时序检查脚本
等待所有Docker容器健康后再启动Python服务
遵循Linus原则：可靠性优于速度
"""

set -euo pipefail

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 日志函数
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查Docker是否运行
check_docker() {
    if ! command -v docker &> /dev/null; then
        log_error "Docker未安装或未在PATH中找到"
        exit 1
    fi
    
    if ! docker info &> /dev/null; then
        log_error "Docker未运行或无权限访问"
        exit 1
    fi
    
    log_info "Docker运行正常"
}

# 检查docker compose是否可用
check_compose() {
    if ! command -v "docker" &> /dev/null; then
        log_error "docker命令未找到"
        exit 1
    fi
    
    # 尝试docker compose（新版本）
    if docker compose version &> /dev/null; then
        COMPOSE_CMD="docker compose"
    # 尝试docker-compose（旧版本）
    elif command -v docker-compose &> /dev/null; then
        COMPOSE_CMD="docker-compose"
    else
        log_error "docker compose 或 docker-compose 未找到"
        exit 1
    fi
    
    log_info "使用: $COMPOSE_CMD"
}

# 启动Docker服务
start_services() {
    log_info "启动Docker服务..."
    
    # 启动服务（如果未运行）
    $COMPOSE_CMD up -d
    
    if [ $? -ne 0 ]; then
        log_error "Docker服务启动失败"
        exit 1
    fi
    
    log_success "Docker服务启动命令执行成功"
}

# 等待特定服务健康
wait_for_service() {
    local service_name="$1"
    local max_attempts=30
    local attempt=0
    
    log_info "等待服务 $service_name 健康检查通过..."
    
    while [ $attempt -lt $max_attempts ]; do
        # 检查容器健康状态
        local health_status=$($COMPOSE_CMD ps --format json | jq -r ".[] | select(.Service == \"$service_name\") | .Health")
        
        if [ "$health_status" = "healthy" ]; then
            log_success "服务 $service_name 健康检查通过"
            return 0
        elif [ "$health_status" = "unhealthy" ]; then
            log_warning "服务 $service_name 健康检查失败，继续等待..."
        else
            log_info "服务 $service_name 健康状态: $health_status (等待中...)"
        fi
        
        ((attempt++))
        sleep 2
    done
    
    log_error "服务 $service_name 健康检查超时"
    return 1
}

# 等待端口可用
wait_for_port() {
    local host="$1"
    local port="$2"
    local service_name="$3"
    local max_attempts=30
    local attempt=0
    
    log_info "等待 $service_name ($host:$port) 端口可用..."
    
    while [ $attempt -lt $max_attempts ]; do
        if nc -z "$host" "$port" 2>/dev/null; then
            log_success "$service_name 端口 $port 已可用"
            return 0
        fi
        
        ((attempt++))
        echo -n "."
        sleep 1
    done
    
    echo
    log_error "$service_name 端口 $port 连接超时"
    return 1
}

# 验证Redis连接
verify_redis() {
    log_info "验证Redis连接..."
    
    # 使用docker exec测试Redis连接
    if docker exec telegram_bot_redis redis-cli ping 2>/dev/null | grep -q "PONG"; then
        log_success "Redis连接验证成功"
        return 0
    else
        log_error "Redis连接验证失败"
        return 1
    fi
}

# 验证Nginx
verify_nginx() {
    log_info "验证Nginx服务..."
    
    # 检查nginx配置
    if docker exec telegram_bot_nginx nginx -t 2>/dev/null; then
        log_success "Nginx配置验证成功"
    else
        log_warning "Nginx配置验证失败，但继续运行"
    fi
    
    # 检查HTTP响应
    if curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/static/favicon.svg | grep -q "200"; then
        log_success "Nginx HTTP响应验证成功"
        return 0
    else
        log_error "Nginx HTTP响应验证失败"
        return 1
    fi
}

# 显示服务状态
show_status() {
    log_info "Docker服务状态:"
    $COMPOSE_CMD ps
    echo
}

# 主函数
main() {
    echo "🐳 Docker服务启动时序检查"
    echo "================================"
    
    # 基础检查
    check_docker
    check_compose
    
    # 启动服务
    start_services
    
    # 等待服务健康（并行检查）
    local services_ready=true
    
    # Redis服务检查
    if ! wait_for_service "redis"; then
        services_ready=false
    fi
    
    # Nginx服务检查  
    if ! wait_for_service "nginx"; then
        services_ready=false
    fi
    
    if [ "$services_ready" = false ]; then
        log_error "部分服务健康检查失败，使用端口检查作为后备方案"
        
        # 后备方案：端口检查
        wait_for_port "localhost" "6379" "Redis"
        wait_for_port "localhost" "8080" "Nginx"
    fi
    
    # 额外验证
    if ! verify_redis; then
        log_error "Redis连接验证失败"
        exit 1
    fi
    
    if ! verify_nginx; then
        log_error "Nginx验证失败"
        exit 1
    fi
    
    # 显示最终状态
    show_status
    
    log_success "✅ 所有Docker服务已就绪，可以启动Python应用"
    echo
}

# 执行主函数
main "$@"