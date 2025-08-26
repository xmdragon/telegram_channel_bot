#!/bin/bash

# 修复Docker卷挂载问题的脚本

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

log_info "修复Docker卷挂载问题..."

# 1. 检查当前目录
log_info "当前工作目录: $(pwd)"

# 2. 创建必要的目录
log_info "创建必要的目录..."
mkdir -p temp_media
mkdir -p logs
mkdir -p data

# 3. 设置正确的权限
log_info "设置目录权限..."
chmod -R 777 temp_media/
chmod -R 777 logs/
chmod -R 755 data/

# 4. 检查目录是否存在和权限
log_info "检查目录状态:"
ls -ld temp_media/ logs/ data/

# 5. 停止问题容器
log_info "停止可能有问题的容器..."
docker compose -f docker-compose.prod.yml stop message-scheduler 2>/dev/null || true

# 6. 删除可能损坏的容器
log_info "删除可能损坏的容器..."
docker compose -f docker-compose.prod.yml rm -f message-scheduler 2>/dev/null || true

# 7. 清理Docker卷缓存
log_info "清理Docker卷缓存..."
docker volume prune -f 2>/dev/null || true

# 8. 重新构建和启动
log_info "重新构建和启动message-scheduler服务..."
docker compose -f docker-compose.prod.yml build --no-cache message-scheduler
docker compose -f docker-compose.prod.yml up -d message-scheduler

# 9. 检查服务状态
log_info "检查服务状态..."
sleep 5
docker compose -f docker-compose.prod.yml ps message-scheduler

# 10. 检查日志
log_info "检查最新日志..."
docker compose -f docker-compose.prod.yml logs --tail=20 message-scheduler

log_success "修复完成！"