#!/bin/bash
# 服务器环境初始化脚本 - 在服务器上以 root 执行
# 用法: bash deploy_server_init.sh
set -euo pipefail

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PROJECT_DIR="/opt/tcb"

log_ok()   { echo -e "${GREEN}✅ $1${NC}"; }
log_fail() { echo -e "${RED}❌ $1${NC}"; }
log_info() { echo -e "${YELLOW}➜ $1${NC}"; }

step() {
    log_info "$1"
    if eval "$2"; then
        log_ok "$1"
    else
        log_fail "$1"
        return 1
    fi
}

# ============================================================
# 1. 系统更新 + 基础工具
# ============================================================
step "系统更新" "apt update -qq && apt upgrade -y -qq"
step "安装基础工具" "apt install -y -qq curl wget git unzip htop > /dev/null"

# ============================================================
# 2. Python 环境
# ============================================================
step "安装 Python 开发工具" "apt install -y -qq python3-pip python3-venv python3-dev > /dev/null"

# ============================================================
# 3. Redis（仅 WebSocket pub/sub）
# ============================================================
step "安装 Redis" "apt install -y -qq redis-server > /dev/null"

log_info "配置 Redis（仅本地、64MB、禁用持久化）"
REDIS_CONF="/etc/redis/redis.conf"
# 仅监听本地
sed -i 's/^bind .*/bind 127.0.0.1 ::1/' "$REDIS_CONF"
# 最大内存 64MB
if grep -q '^maxmemory ' "$REDIS_CONF"; then
    sed -i 's/^maxmemory .*/maxmemory 64mb/' "$REDIS_CONF"
else
    echo 'maxmemory 64mb' >> "$REDIS_CONF"
fi
# 内存淘汰策略
if grep -q '^maxmemory-policy ' "$REDIS_CONF"; then
    sed -i 's/^maxmemory-policy .*/maxmemory-policy allkeys-lru/' "$REDIS_CONF"
else
    echo 'maxmemory-policy allkeys-lru' >> "$REDIS_CONF"
fi
# 禁用持久化
sed -i 's/^save /#save /' "$REDIS_CONF"
sed -i 's/^appendonly yes/appendonly no/' "$REDIS_CONF"

systemctl enable redis-server && systemctl restart redis-server
log_ok "Redis 配置完成"

# ============================================================
# 4. Nginx
# ============================================================
step "安装 Nginx" "apt install -y -qq nginx > /dev/null"

log_info "写入 Nginx 配置"
cat > /etc/nginx/sites-available/tcb << 'NGINX_CONF'
server {
    listen 80;
    server_name tcb.gxfc.life;

    client_max_body_size 50m;

    location /static/ {
        alias /opt/tcb/current/static/;
        expires 1d;
        add_header Cache-Control "public, immutable";
    }

    location /ws {
        proxy_pass http://127.0.0.1:8008/ws;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 86400;
    }

    location / {
        proxy_pass http://127.0.0.1:8008;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
NGINX_CONF

ln -sf /etc/nginx/sites-available/tcb /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

if nginx -t 2>/dev/null; then
    systemctl enable nginx && systemctl restart nginx
    log_ok "Nginx 配置完成"
else
    log_fail "Nginx 配置有误"
    nginx -t
    exit 1
fi

# ============================================================
# 5. Supervisor
# ============================================================
step "安装 Supervisor" "apt install -y -qq supervisor > /dev/null"

log_info "写入 Supervisor 配置"
cat > /etc/supervisor/conf.d/tcb.conf << 'SUPERVISOR_CONF'
[program:telegram_web]
command=/opt/tcb/shared/venv/bin/python web_server.py
directory=/opt/tcb/current
environment=HOME="/root",VIRTUAL_ENV="/opt/tcb/shared/venv",PATH="/opt/tcb/shared/venv/bin:%(ENV_PATH)s",HF_HUB_OFFLINE="1",PYTHONUNBUFFERED="1",PRODUCTION="true"
autostart=true
autorestart=true
startretries=3
stdout_logfile=/opt/tcb/shared/logs/web_output.log
stderr_logfile=/opt/tcb/shared/logs/web_error.log
stdout_logfile_maxbytes=10MB
stdout_logfile_backups=3
stderr_logfile_maxbytes=10MB
stderr_logfile_backups=3
priority=10
stopwaitsecs=10

[program:telegram_collector]
command=/opt/tcb/shared/venv/bin/python message_collector.py
directory=/opt/tcb/current
environment=HOME="/root",VIRTUAL_ENV="/opt/tcb/shared/venv",PATH="/opt/tcb/shared/venv/bin:%(ENV_PATH)s",HF_HUB_OFFLINE="1",PYTHONUNBUFFERED="1"
autostart=true
autorestart=true
startretries=3
stdout_logfile=/opt/tcb/shared/logs/collector_output.log
stderr_logfile=/opt/tcb/shared/logs/collector_error.log
stdout_logfile_maxbytes=10MB
stdout_logfile_backups=3
stderr_logfile_maxbytes=10MB
stderr_logfile_backups=3
priority=20
stopwaitsecs=10

[program:telegram_scheduler]
command=/opt/tcb/shared/venv/bin/python message_scheduler.py
directory=/opt/tcb/current
environment=HOME="/root",VIRTUAL_ENV="/opt/tcb/shared/venv",PATH="/opt/tcb/shared/venv/bin:%(ENV_PATH)s",HF_HUB_OFFLINE="1",PYTHONUNBUFFERED="1"
autostart=true
autorestart=true
startretries=3
stdout_logfile=/opt/tcb/shared/logs/scheduler_output.log
stderr_logfile=/opt/tcb/shared/logs/scheduler_error.log
stdout_logfile_maxbytes=10MB
stdout_logfile_backups=3
stderr_logfile_maxbytes=10MB
stderr_logfile_backups=3
priority=30
startsecs=10
stopwaitsecs=10

[group:tcb]
programs=telegram_web,telegram_collector,telegram_scheduler
SUPERVISOR_CONF

systemctl enable supervisor && systemctl restart supervisor
log_ok "Supervisor 配置完成"

# ============================================================
# 6. 创建项目目录结构
# ============================================================
log_info "创建项目目录结构"
mkdir -p "$PROJECT_DIR"/{releases,shared/{data/{config,db,training,backups},logs,temp_media,telegram_sessions}}
log_ok "目录结构创建完成"

# ============================================================
# 7. 创建 Python venv
# ============================================================
if [ ! -d "$PROJECT_DIR/shared/venv" ]; then
    step "创建 Python 虚拟环境" "python3 -m venv $PROJECT_DIR/shared/venv"
else
    log_ok "Python 虚拟环境已存在，跳过"
fi

# 升级 pip
"$PROJECT_DIR/shared/venv/bin/pip" install --upgrade pip -q

# ============================================================
# 8. 防火墙
# ============================================================
log_info "配置防火墙"
ufw allow 22/tcp > /dev/null 2>&1
ufw allow 80/tcp > /dev/null 2>&1
ufw allow 443/tcp > /dev/null 2>&1
ufw --force enable > /dev/null 2>&1
log_ok "防火墙配置完成"

# ============================================================
# 最终汇总
# ============================================================
echo ""
echo "=========================================="
echo -e "${GREEN}  服务器初始化完成${NC}"
echo "=========================================="
echo ""
echo "服务状态:"
echo "  Redis:      $(systemctl is-active redis-server)"
echo "  Nginx:      $(systemctl is-active nginx)"
echo "  Supervisor: $(systemctl is-active supervisor)"
echo ""
echo "Python: $(python3 --version)"
echo "Venv:   $PROJECT_DIR/shared/venv"
echo "项目:   $PROJECT_DIR"
echo ""
echo "下一步: 从本地运行 deploy.sh init 完成代码部署"
