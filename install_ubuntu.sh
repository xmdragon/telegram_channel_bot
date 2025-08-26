#!/bin/bash

# Telegram消息审核系统 - Ubuntu 24.04 自动安装脚本
# 一键安装所有依赖和配置服务

set -e  # 遇到错误立即退出

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

# 检查用户权限
check_root() {
    if [[ $EUID -eq 0 ]]; then
        log_warning "检测到root用户，将自动适配root环境"
        log_info "如果是生产环境，建议使用普通用户：sudo adduser telegram"
        
        # root用户环境变量
        export IS_ROOT=true
        export PROJECT_USER="root"
    else
        log_info "使用普通用户部署"
        export IS_ROOT=false
        export PROJECT_USER="$USER"
    fi
}

# 检查Ubuntu版本
check_ubuntu_version() {
    log_info "检查Ubuntu版本..."
    
    if [[ ! -f /etc/lsb-release ]]; then
        log_error "无法检测Ubuntu版本"
        exit 1
    fi
    
    source /etc/lsb-release
    
    if [[ "$DISTRIB_ID" != "Ubuntu" ]]; then
        log_error "此脚本仅支持Ubuntu系统"
        exit 1
    fi
    
    if [[ "$DISTRIB_RELEASE" != "24.04" ]] && [[ "$DISTRIB_RELEASE" != "22.04" ]] && [[ "$DISTRIB_RELEASE" != "20.04" ]]; then
        log_warning "检测到Ubuntu $DISTRIB_RELEASE，推荐使用24.04"
        read -p "是否继续安装? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    else
        log_success "Ubuntu版本检查通过: $DISTRIB_RELEASE"
    fi
}

# 更新系统包
update_system() {
    log_info "更新系统包索引..."
    sudo apt update
    
    log_info "升级系统包..."
    sudo apt upgrade -y
    
    log_success "系统更新完成"
}

# 安装基础工具
install_basic_tools() {
    log_info "安装基础工具..."
    
    sudo apt install -y \
        curl \
        wget \
        git \
        unzip \
        software-properties-common \
        apt-transport-https \
        ca-certificates \
        gnupg \
        lsb-release \
        build-essential \
        pkg-config \
        libffi-dev \
        libssl-dev \
        zlib1g-dev \
        libbz2-dev \
        libreadline-dev \
        libsqlite3-dev \
        libncurses5-dev \
        libncursesw5-dev \
        xz-utils \
        tk-dev \
        libxml2-dev \
        libxmlsec1-dev \
        liblzma-dev
    
    log_success "基础工具安装完成"
}

# Python环境已完全容器化，无需系统安装
check_python_containerized() {
    log_info "🐳 Python运行环境已容器化"
    log_info "   - Web服务: Python容器 + Gunicorn"
    log_info "   - 采集服务: Python容器 + Telethon"
    log_info "   - 调度服务: Python容器 + AsyncIO"
    log_info "✅ 无需安装系统Python，减少依赖冲突"
}

# Redis已容器化，无需系统安装
check_redis() {
    log_info "Redis将运行在Docker容器中，无需系统安装"
}

# 安装Docker和Docker Compose
install_docker() {
    log_info "安装Docker..."
    
    if command -v docker &> /dev/null; then
        log_success "Docker已安装"
    else
        # 添加Docker官方GPG密钥
        curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
        
        # 添加Docker APT仓库
        echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
        
        sudo apt update
        sudo apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
        
        # 将用户添加到docker组
        if [[ "$IS_ROOT" != "true" ]]; then
            sudo usermod -aG docker $USER
            log_info "已将用户 $USER 添加到docker组"
        else
            log_info "root用户无需添加到docker组"
        fi
        
        log_success "Docker安装完成"
    fi
    
    # 安装Docker Compose V2
    if command -v docker compose &> /dev/null; then
        log_success "Docker Compose已安装"
    else
        log_error "Docker Compose安装失败"
        exit 1
    fi
    
    # 启用并启动Docker服务
    sudo systemctl enable docker
    sudo systemctl start docker
}

# Nginx已容器化，无需系统安装
check_nginx() {
    log_info "Nginx将运行在Docker容器中，无需系统安装"
}

# 安装系统监控工具
install_monitoring_tools() {
    log_info "安装系统监控工具..."
    
    sudo apt install -y \
        htop \
        iotop \
        net-tools \
        iproute2 \
        lsof \
        tree \
        jq \
        ncdu
    
    log_success "监控工具安装完成"
}

# 创建项目目录和用户
setup_project_environment() {
    log_info "设置项目环境..."
    
    # 创建项目目录
    PROJECT_DIR="/opt/telegram-bot"
    if [[ ! -d "$PROJECT_DIR" ]]; then
        if [[ "$IS_ROOT" == "true" ]]; then
            mkdir -p "$PROJECT_DIR"
        else
            sudo mkdir -p "$PROJECT_DIR"
            sudo chown $USER:$USER "$PROJECT_DIR"
        fi
        log_info "创建项目目录: $PROJECT_DIR"
    fi
    
    # 创建日志目录
    LOG_DIR="/var/log/telegram-bot"
    if [[ ! -d "$LOG_DIR" ]]; then
        if [[ "$IS_ROOT" == "true" ]]; then
            mkdir -p "$LOG_DIR"
        else
            sudo mkdir -p "$LOG_DIR"
            sudo chown $USER:$USER "$LOG_DIR"
        fi
        log_info "创建日志目录: $LOG_DIR"
    fi
    
    # 创建数据目录
    DATA_DIR="/var/lib/telegram-bot"
    if [[ ! -d "$DATA_DIR" ]]; then
        if [[ "$IS_ROOT" == "true" ]]; then
            mkdir -p "$DATA_DIR"
        else
            sudo mkdir -p "$DATA_DIR"
            sudo chown $USER:$USER "$DATA_DIR"
        fi
        log_info "创建数据目录: $DATA_DIR"
    fi
    
    log_success "项目环境设置完成"
}

# 配置系统服务
setup_systemd_services() {
    log_info "配置systemd服务..."
    
    # 创建Telegram Bot服务文件
    sudo tee /etc/systemd/system/telegram-bot.service > /dev/null <<EOF
[Unit]
Description=Telegram Bot Message Processing System
After=network.target docker.service
Requires=docker.service

[Service]
Type=forking
User=$PROJECT_USER
Group=$PROJECT_USER
WorkingDirectory=/opt/telegram-bot
Environment=PATH=/usr/bin:/usr/local/bin
ExecStart=/opt/telegram-bot/start.sh
ExecStop=/opt/telegram-bot/stop.sh
ExecReload=/opt/telegram-bot/restart.sh
Restart=always
RestartSec=10
KillMode=mixed
KillSignal=SIGTERM
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
EOF
    
    sudo systemctl daemon-reload
    log_success "systemd服务配置完成"
}

# 配置防火墙
configure_firewall() {
    log_info "配置防火墙..."
    
    # 启用UFW防火墙
    sudo ufw --force enable
    
    # 允许SSH
    sudo ufw allow ssh
    
    # 允许HTTP和HTTPS
    sudo ufw allow 80
    sudo ufw allow 443
    
    # 允许Docker容器端口
    sudo ufw allow from 127.0.0.1 to any port 8000  # 内部API端口
    
    log_success "防火墙配置完成"
}

# 优化系统参数
optimize_system() {
    log_info "优化系统参数..."
    
    # 创建系统优化配置
    sudo tee /etc/sysctl.d/99-telegram-bot.conf > /dev/null <<EOF
# 网络优化
net.core.somaxconn = 65535
net.core.netdev_max_backlog = 5000
net.ipv4.tcp_max_syn_backlog = 8192
net.ipv4.tcp_keepalive_time = 600
net.ipv4.tcp_keepalive_intvl = 60
net.ipv4.tcp_keepalive_probes = 3

# 内存优化
vm.swappiness = 10
vm.dirty_ratio = 15
vm.dirty_background_ratio = 5

# 文件描述符限制
fs.file-max = 100000
EOF
    
    # 应用系统参数
    sudo sysctl -p /etc/sysctl.d/99-telegram-bot.conf
    
    # 设置用户限制
    sudo tee /etc/security/limits.d/telegram-bot.conf > /dev/null <<EOF
$PROJECT_USER soft nofile 65535
$PROJECT_USER hard nofile 65535
$PROJECT_USER soft nproc 32768
$PROJECT_USER hard nproc 32768
EOF
    
    log_success "系统优化完成"
}

# 安装完成后的设置说明
show_post_install_instructions() {
    log_success "🎉 安装完成！"
    echo
    log_info "接下来的步骤："
    
    if [[ "$IS_ROOT" != "true" ]]; then
        echo "1. 重新登录以使docker组权限生效："
        echo "   exit"
        echo "   # 重新SSH登录"
        echo
        echo "2. 克隆项目代码："
    else
        echo "1. 克隆项目代码（root用户可直接继续）："
    fi
    echo "   cd /opt/telegram-bot"
    echo "   git clone <your-repo-url> ."
    echo
    echo "2. 配置环境变量："
    echo "   cp .env.production .env"
    echo "   nano .env  # 编辑Telegram凭证等"
    echo
    echo "3. 一键部署（Docker容器化）："
    echo "   ./deploy.sh"
    echo
    echo "4. 设置开机自启（可选）："
    echo "   sudo systemctl enable telegram-bot"
    echo
    log_info "服务端口："
    echo "- Web界面: http://localhost:8080"
    echo "- API接口: http://localhost:8000"
    echo "- Redis: localhost:6379"
    echo
    log_info "日志位置："
    echo "- 应用日志: /var/log/telegram-bot/"
    echo "- 系统日志: journalctl -u telegram-bot"
    echo
    log_info "管理命令："
    echo "- 查看状态: ./dev.sh --status"
    echo "- 重启服务: ./restart.sh"
    echo "- 查看日志: tail -f logs/app.log"
    echo
}

# 主安装流程
main() {
    echo "=================================================="
    echo "  Telegram消息审核系统 - Ubuntu 24.04 自动安装"
    echo "=================================================="
    echo
    
    check_root
    check_ubuntu_version
    
    log_info "开始安装..."
    
    update_system
    install_basic_tools
    check_python_containerized
    check_redis
    install_docker
    check_nginx
    install_monitoring_tools
    setup_project_environment
    setup_systemd_services
    configure_firewall
    optimize_system
    
    show_post_install_instructions
}

# 脚本参数处理
case "${1:-install}" in
    "install")
        main
        ;;
    "check")
        log_info "检查系统环境..."
        check_ubuntu_version
        
        # 检查已安装的组件
        echo
        log_info "已安装组件检查："
        
        echo "✅ Python (Docker容器)"
        echo "✅ Redis (Docker容器)"
        command -v docker >/dev/null && echo "✅ Docker" || echo "❌ Docker"
        echo "✅ Nginx (Docker容器)"
        [[ -d "/opt/telegram-bot" ]] && echo "✅ 项目目录" || echo "❌ 项目目录"
        
        echo
        ;;
    "help")
        echo "用法: $0 [命令]"
        echo
        echo "命令:"
        echo "  install  - 执行完整安装（默认）"
        echo "  check    - 检查系统环境和已安装组件"
        echo "  help     - 显示此帮助信息"
        echo
        ;;
    *)
        log_error "未知命令: $1"
        echo "使用 '$0 help' 查看帮助"
        exit 1
        ;;
esac