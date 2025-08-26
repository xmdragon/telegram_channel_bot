#!/bin/bash

# 生产环境部署脚本
# Ubuntu 24.04 Docker部署

set -e

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

# 配置变量
PROJECT_NAME="telegram-bot"
COMPOSE_FILE="docker-compose.prod.yml"
BACKUP_DIR="/var/backups/telegram-bot"
MAX_BACKUPS=7

# 检查环境
check_environment() {
    log_info "检查部署环境..."
    
    # 检查Docker
    if ! command -v docker &> /dev/null; then
        log_error "Docker未安装，请先运行 install_ubuntu.sh"
        exit 1
    fi
    
    # 检查Docker Compose
    if ! docker compose version &> /dev/null; then
        log_error "Docker Compose未安装"
        exit 1
    fi
    
    # 检查配置文件
    if [[ ! -f ".env" ]]; then
        log_error ".env文件不存在，请先配置环境变量"
        log_info "可以从.env.example复制: cp .env.example .env"
        exit 1
    fi
    
    # 检查Docker Compose文件
    if [[ ! -f "$COMPOSE_FILE" ]]; then
        log_error "Docker Compose文件不存在: $COMPOSE_FILE"
        exit 1
    fi
    
    log_success "环境检查通过"
}

# 创建备份
create_backup() {
    if [[ "${1:-}" == "--no-backup" ]]; then
        log_info "跳过备份"
        return
    fi
    
    log_info "创建数据备份..."
    
    # 创建备份目录
    sudo mkdir -p "$BACKUP_DIR"
    
    # 备份时间戳
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    BACKUP_PATH="$BACKUP_DIR/backup_$TIMESTAMP"
    
    # 创建备份
    sudo mkdir -p "$BACKUP_PATH"
    
    # 备份数据目录
    if [[ -d "data" ]]; then
        sudo cp -r data "$BACKUP_PATH/"
        log_info "数据目录已备份"
    fi
    
    # 备份配置文件
    sudo cp .env "$BACKUP_PATH/" 2>/dev/null || true
    sudo cp docker-compose.prod.yml "$BACKUP_PATH/" 2>/dev/null || true
    
    # 备份数据库
    if docker ps | grep -q "telegram_bot_redis"; then
        log_info "备份Redis数据..."
        docker exec telegram_bot_redis redis-cli BGSAVE
        sleep 2
        docker cp telegram_bot_redis:/data/dump.rdb "$BACKUP_PATH/redis_dump.rdb" 2>/dev/null || true
    fi
    
    # 压缩备份
    sudo tar -czf "$BACKUP_DIR/backup_$TIMESTAMP.tar.gz" -C "$BACKUP_DIR" "backup_$TIMESTAMP"
    sudo rm -rf "$BACKUP_PATH"
    
    # 清理旧备份
    sudo find "$BACKUP_DIR" -name "backup_*.tar.gz" -type f -mtime +$MAX_BACKUPS -delete 2>/dev/null || true
    
    log_success "备份完成: $BACKUP_DIR/backup_$TIMESTAMP.tar.gz"
}

# 预下载AI模型
preload_ai_models() {
    log_info "预下载AI模型..."
    
    # 检查Python环境
    if [[ ! -f "venv/bin/python3" ]]; then
        log_warning "Python虚拟环境不存在，跳过AI模型预下载"
        return
    fi
    
    # 检查预下载工具
    if [[ ! -f "tools/maintenance/preload_ai_models.py" ]]; then
        log_warning "AI模型预下载工具不存在，跳过预下载"
        return
    fi
    
    # 临时启用网络下载模式
    export HF_HUB_OFFLINE=0
    
    # 执行预下载
    if ./venv/bin/python3 tools/maintenance/preload_ai_models.py --download; then
        log_success "AI模型预下载完成"
    else
        log_warning "AI模型预下载失败，系统将在运行时自动下载"
    fi
    
    # 恢复离线模式
    export HF_HUB_OFFLINE=1
}

# 构建镜像
build_images() {
    log_info "构建Docker镜像..."
    
    # 清理构建缓存释放空间
    log_info "清理Docker构建缓存..."
    docker buildx prune -f 2>/dev/null || true
    docker system prune -f 2>/dev/null || true
    
    # 检查可用空间
    AVAILABLE_SPACE=$(df / | tail -1 | awk '{print $4}')
    log_info "可用磁盘空间: ${AVAILABLE_SPACE}KB"
    
    # 分步构建，避免同时构建多个镜像
    log_info "分步构建镜像以节省空间..."
    
    # 先构建应用镜像
    log_info "构建应用镜像..."
    docker compose -f "$COMPOSE_FILE" build --no-cache app
    
    # 清理中间缓存
    docker image prune -f
    
    # 再构建调度器镜像
    log_info "构建调度器镜像..."
    docker compose -f "$COMPOSE_FILE" build --no-cache message-scheduler
    
    # 最终清理
    docker image prune -f
    
    log_success "镜像构建完成"
}

# 部署服务
deploy_services() {
    log_info "部署服务..."
    
    # 停止现有服务
    docker compose -f "$COMPOSE_FILE" down 2>/dev/null || true
    
    # 清理悬挂镜像
    docker image prune -f
    
    # 启动服务
    docker compose -f "$COMPOSE_FILE" up -d
    
    log_success "服务部署完成"
}

# 等待服务就绪
wait_for_services() {
    log_info "等待服务启动..."
    
    # 等待Redis
    log_info "等待Redis服务..."
    timeout=30
    while [ $timeout -gt 0 ]; do
        if docker exec telegram_bot_redis redis-cli ping 2>/dev/null | grep -q "PONG"; then
            log_success "Redis服务就绪"
            break
        fi
        sleep 2
        ((timeout-=2))
    done
    
    if [ $timeout -le 0 ]; then
        log_error "Redis服务启动超时"
        return 1
    fi
    
    # 等待应用服务
    log_info "等待应用服务..."
    timeout=60
    while [ $timeout -gt 0 ]; do
        if curl -f http://localhost/health 2>/dev/null; then
            log_success "应用服务就绪"
            break
        fi
        sleep 5
        ((timeout-=5))
    done
    
    if [ $timeout -le 0 ]; then
        log_error "应用服务启动超时"
        return 1
    fi
    
    log_success "所有服务已就绪"
}

# 检查服务状态
check_services() {
    log_info "检查服务状态..."
    
    echo "================服务状态================"
    docker compose -f "$COMPOSE_FILE" ps
    echo "======================================"
    
    # 检查健康状态
    echo
    log_info "健康检查..."
    
    # Redis健康检查
    if docker exec telegram_bot_redis redis-cli ping 2>/dev/null | grep -q "PONG"; then
        echo "✅ Redis: 健康"
    else
        echo "❌ Redis: 不健康"
    fi
    
    # 应用健康检查
    if curl -f http://localhost/health 2>/dev/null; then
        echo "✅ 应用: 健康"
    else
        echo "❌ 应用: 不健康"
    fi
    
    # Nginx健康检查
    if curl -f http://localhost 2>/dev/null >/dev/null; then
        echo "✅ Nginx: 健康"
    else
        echo "❌ Nginx: 不健康"
    fi
}

# 查看日志
show_logs() {
    local service=${1:-}
    
    if [[ -n "$service" ]]; then
        log_info "查看 $service 服务日志..."
        docker compose -f "$COMPOSE_FILE" logs -f "$service"
    else
        log_info "查看所有服务日志..."
        docker compose -f "$COMPOSE_FILE" logs -f
    fi
}

# 停止服务
stop_services() {
    log_info "停止服务..."
    
    docker compose -f "$COMPOSE_FILE" down
    
    log_success "服务已停止"
}

# 重启服务
restart_services() {
    log_info "重启服务..."
    
    create_backup --no-backup
    docker compose -f "$COMPOSE_FILE" restart
    wait_for_services
    
    log_success "服务重启完成"
}

# 完整部署
full_deploy() {
    local backup_option=${1:-}
    
    log_info "开始完整部署..."
    
    check_environment
    create_backup $backup_option
    preload_ai_models  # 在构建镜像前预下载AI模型
    build_images
    deploy_services
    wait_for_services
    check_services
    
    log_success "部署完成！"
    echo
    log_info "访问地址:"
    echo "  - Web界面: http://localhost/static/login.html"
    echo "  - API接口: http://localhost/api/"
    echo "  - 健康检查: http://localhost/health"
    echo
    log_info "管理命令:"
    echo "  - 查看状态: $0 status"
    echo "  - 查看日志: $0 logs [service]"
    echo "  - 重启服务: $0 restart"
    echo "  - 停止服务: $0 stop"
}

# 清理系统
cleanup() {
    log_warning "清理Docker资源..."
    
    # 停止服务
    docker compose -f "$COMPOSE_FILE" down -v
    
    # 清理镜像
    docker system prune -f
    docker volume prune -f
    
    log_success "清理完成"
}

# 深度清理（用于磁盘空间不足时）
deep_cleanup() {
    log_warning "执行深度清理释放最大空间..."
    
    # 停止所有容器
    docker stop $(docker ps -aq) 2>/dev/null || true
    
    # 删除所有容器、镜像、网络、卷
    docker system prune -af --volumes
    docker buildx prune -af
    
    # 清理构建缓存
    docker builder prune -af
    
    log_success "深度清理完成"
    
    # 显示清理后的空间
    log_info "清理后磁盘空间:"
    df -h / | grep -v Filesystem
}

# SSL证书设置
setup_ssl() {
    local domain=${1:-}
    
    if [[ -z "$domain" ]]; then
        log_error "请提供域名: $0 ssl yourdomain.com"
        exit 1
    fi
    
    log_info "为域名 $domain 设置SSL证书..."
    
    # 安装certbot
    if ! command -v certbot &> /dev/null; then
        log_info "安装certbot..."
        sudo apt update
        sudo apt install -y certbot python3-certbot-nginx
    fi
    
    # 获取证书
    sudo certbot --nginx -d "$domain" --non-interactive --agree-tos --email admin@"$domain"
    
    # 设置自动续期
    (crontab -l 2>/dev/null; echo "0 12 * * * /usr/bin/certbot renew --quiet") | crontab -
    
    log_success "SSL证书设置完成"
}

# 帮助信息
show_help() {
    echo "Telegram Bot 生产环境部署脚本"
    echo
    echo "用法: $0 <命令> [选项]"
    echo
    echo "命令:"
    echo "  deploy          - 完整部署（默认）"
    echo "  deploy-fast     - 快速部署（跳过备份）"
    echo "  build           - 构建镜像"
    echo "  start           - 启动服务"
    echo "  stop            - 停止服务"
    echo "  restart         - 重启服务"
    echo "  status          - 查看服务状态"
    echo "  logs [service]  - 查看日志"
    echo "  backup          - 创建备份"
    echo "  cleanup         - 清理Docker资源"
    echo "  deep-cleanup    - 深度清理（磁盘空间不足时使用）"
    echo "  ssl <domain>    - 设置SSL证书"
    echo "  help            - 显示帮助"
    echo
    echo "示例:"
    echo "  $0 deploy                    # 完整部署"
    echo "  $0 logs app                  # 查看应用日志"
    echo "  $0 ssl yourdomain.com        # 设置SSL"
    echo
}

# 主程序
main() {
    case "${1:-deploy}" in
        "deploy")
            full_deploy
            ;;
        "deploy-fast")
            full_deploy --no-backup
            ;;
        "build")
            check_environment
            build_images
            ;;
        "start")
            check_environment
            deploy_services
            wait_for_services
            ;;
        "stop")
            stop_services
            ;;
        "restart")
            restart_services
            ;;
        "status")
            check_services
            ;;
        "logs")
            show_logs "${2:-}"
            ;;
        "backup")
            create_backup
            ;;
        "cleanup")
            cleanup
            ;;
        "deep-cleanup")
            deep_cleanup
            ;;
        "ssl")
            setup_ssl "${2:-}"
            ;;
        "help")
            show_help
            ;;
        *)
            log_error "未知命令: $1"
            show_help
            exit 1
            ;;
    esac
}

main "$@"