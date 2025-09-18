#!/bin/bash

# Ubuntu 24.04 Telegram Channel Bot 部署检查脚本
# 检查依赖、配置服务、设置环境

set -e

# 获取脚本所在目录和项目根目录
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/../.." &> /dev/null && pwd )"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
PURPLE='\033[0;35m'
NC='\033[0m' # No Color

# 项目配置
PROJECT_NAME="telegram_channel_bot"
PYTHON_MIN_VERSION="3.11"
REDIS_MIN_VERSION="6.0"
NGINX_MIN_VERSION="1.18"

# 端口配置
WEB_PORT=8008
NGINX_PORT=8080
REDIS_PORT=6379

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

# 显示帮助信息
show_help() {
    echo "🚀 Ubuntu 24.04 Telegram Channel Bot 部署检查器"
    echo ""
    echo "用法: $0 [选项]"
    echo ""
    echo "选项:"
    echo "  --check-only        仅检查依赖，不安装或配置"
    echo "  --install-deps      自动安装缺失的依赖"
    echo "  --config-nginx      配置Nginx站点"
    echo "  --domain <域名>     配置域名 (如: bot.example.com)"
    echo "  --ssl              启用SSL证书 (使用Let's Encrypt)"
    echo "  --email <邮箱>      SSL证书通知邮箱"
    echo "  --skip-firewall     跳过防火墙配置"
    echo "  --verbose, -v       显示详细信息"
    echo "  --help, -h          显示此帮助信息"
    echo ""
    echo "检查项目:"
    echo "  ✅ Python $PYTHON_MIN_VERSION+ 和 pip"
    echo "  ✅ Redis $REDIS_MIN_VERSION+ 服务"
    echo "  ✅ Nginx $NGINX_MIN_VERSION+ 服务"
    echo "  ✅ 系统权限和防火墙"
    echo "  ✅ 项目依赖安装"
    echo ""
    echo "示例:"
    echo "  $0                          # 完整检查和配置"
    echo "  $0 --check-only             # 仅检查当前状态"
    echo "  $0 --install-deps           # 检查并自动安装缺失依赖"
    echo "  $0 --domain bot.example.com --ssl --email admin@example.com  # 配置域名和SSL"
    echo ""
}

# 交互式输入函数
prompt_for_input() {
    local prompt=$1
    local default=$2
    local var_name=$3

    if [ -n "$default" ]; then
        echo -ne "${CYAN}$prompt ${NC}[${GREEN}$default${NC}]: "
    else
        echo -ne "${CYAN}$prompt${NC}: "
    fi

    read user_input

    if [ -z "$user_input" ] && [ -n "$default" ]; then
        eval "$var_name='$default'"
    else
        eval "$var_name='$user_input'"
    fi
}

# 交互式确认函数
confirm() {
    local prompt=$1
    local default=${2:-n}

    if [ "$default" = "y" ]; then
        echo -ne "${CYAN}$prompt ${NC}[${GREEN}Y${NC}/n]: "
    else
        echo -ne "${CYAN}$prompt ${NC}[y/${GREEN}N${NC}]: "
    fi

    read -r response
    response=${response,,}  # 转小写

    if [ -z "$response" ]; then
        response=$default
    fi

    [ "$response" = "y" ] || [ "$response" = "yes" ]
}

# 解析参数
CHECK_ONLY=false
INSTALL_DEPS=false
CONFIG_NGINX=true
SKIP_FIREWALL=false
VERBOSE=false
DOMAIN_NAME=""
ENABLE_SSL=false
ADMIN_EMAIL=""
INTERACTIVE_MODE=true

while [[ $# -gt 0 ]]; do
    case $1 in
        --check-only)
            CHECK_ONLY=true
            INSTALL_DEPS=false
            CONFIG_NGINX=false
            INTERACTIVE_MODE=false
            shift
            ;;
        --install-deps)
            INSTALL_DEPS=true
            INTERACTIVE_MODE=false
            shift
            ;;
        --config-nginx)
            CONFIG_NGINX=true
            INTERACTIVE_MODE=false
            shift
            ;;
        --domain)
            DOMAIN_NAME="$2"
            CONFIG_NGINX=true
            INTERACTIVE_MODE=false
            shift 2
            ;;
        --ssl)
            ENABLE_SSL=true
            INTERACTIVE_MODE=false
            shift
            ;;
        --email)
            ADMIN_EMAIL="$2"
            INTERACTIVE_MODE=false
            shift 2
            ;;
        --skip-firewall)
            SKIP_FIREWALL=true
            shift
            ;;
        --non-interactive)
            INTERACTIVE_MODE=false
            shift
            ;;
        --verbose|-v)
            VERBOSE=true
            shift
            ;;
        --help|-h)
            show_help
            exit 0
            ;;
        *)
            log_error "未知参数: $1"
            show_help
            exit 1
            ;;
    esac
done

# 交互式配置收集
if [ "$INTERACTIVE_MODE" = true ]; then
    echo ""
    echo -e "${PURPLE}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${PURPLE}     Telegram Channel Bot 部署配置向导      ${NC}"
    echo -e "${PURPLE}═══════════════════════════════════════════════════════════${NC}"
    echo ""

    # 询问Web端口
    prompt_for_input "请输入Web API服务端口" "$WEB_PORT" "WEB_PORT"

    # 询问Nginx端口
    prompt_for_input "请输入Nginx前端访问端口" "$NGINX_PORT" "NGINX_PORT"

    # 询问域名
    echo ""
    echo -e "${CYAN}域名配置（支持多个域名）：${NC}"
    echo -e "${YELLOW}  - 留空则只使用 localhost${NC}"
    echo -e "${YELLOW}  - 输入域名将同时支持域名和 localhost 访问${NC}"
    prompt_for_input "请输入您的域名（如: bot.example.com）" "" "DOMAIN_NAME"

    # 如果有域名，询问是否配置SSL
    if [ -n "$DOMAIN_NAME" ]; then
        echo ""
        if confirm "是否为域名 $DOMAIN_NAME 配置SSL证书？" "y"; then
            ENABLE_SSL=true
            echo ""
            echo -e "${CYAN}SSL证书配置：${NC}"
            echo -e "${YELLOW}  - 留空将使用 --register-unsafely-without-email${NC}"
            echo -e "${YELLOW}  - 建议提供邮箱以接收证书过期提醒${NC}"
            prompt_for_input "请输入管理员邮箱（用于SSL证书通知）" "" "ADMIN_EMAIL"
        fi
    fi

    # 询问是否自动安装依赖
    echo ""
    if confirm "是否自动安装缺失的依赖？" "y"; then
        INSTALL_DEPS=true
    fi

    # 询问是否配置Nginx
    echo ""
    if confirm "是否配置Nginx站点？" "y"; then
        CONFIG_NGINX=true
    fi

    # 询问是否配置防火墙
    echo ""
    if confirm "是否配置防火墙规则？" "n"; then
        SKIP_FIREWALL=false
    else
        SKIP_FIREWALL=true
    fi

    # 询问是否安装系统服务
    echo ""
    INSTALL_SERVICE=false
    if confirm "是否安装为系统服务（开机自启动）？" "y"; then
        INSTALL_SERVICE=true
    fi

    # 显示配置摘要
    echo ""
    echo -e "${PURPLE}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}配置摘要：${NC}"
    echo -e "  ${CYAN}Web API端口：${NC}$WEB_PORT"
    echo -e "  ${CYAN}Nginx端口：${NC}$NGINX_PORT"
    if [ -n "$DOMAIN_NAME" ]; then
        echo -e "  ${CYAN}域名：${NC}$DOMAIN_NAME (同时支持 localhost)"
    else
        echo -e "  ${CYAN}域名：${NC}仅使用 localhost"
    fi
    if [ "$ENABLE_SSL" = true ]; then
        echo -e "  ${CYAN}SSL证书：${NC}${GREEN}启用${NC}"
        if [ -n "$ADMIN_EMAIL" ]; then
            echo -e "  ${CYAN}管理员邮箱：${NC}$ADMIN_EMAIL"
        fi
    else
        echo -e "  ${CYAN}SSL证书：${NC}不配置"
    fi
    echo -e "  ${CYAN}自动安装依赖：${NC}$([ "$INSTALL_DEPS" = true ] && echo "${GREEN}是${NC}" || echo "${YELLOW}否${NC}")"
    echo -e "  ${CYAN}配置Nginx：${NC}$([ "$CONFIG_NGINX" = true ] && echo "${GREEN}是${NC}" || echo "${YELLOW}否${NC}")"
    echo -e "  ${CYAN}配置防火墙：${NC}$([ "$SKIP_FIREWALL" = true ] && echo "${YELLOW}跳过${NC}" || echo "${GREEN}配置${NC}")"
    echo -e "  ${CYAN}系统服务：${NC}$([ "$INSTALL_SERVICE" = true ] && echo "${GREEN}安装${NC}" || echo "${YELLOW}不安装${NC}")"
    echo -e "${PURPLE}═══════════════════════════════════════════════════════════${NC}"
    echo ""

    if ! confirm "确认以上配置并开始部署？" "y"; then
        echo -e "${YELLOW}部署已取消${NC}"
        exit 0
    fi
    echo ""
fi

# 生成环境配置文件
generate_env_file() {
    local env_file="$PROJECT_ROOT/.env"

    log_info "生成环境配置文件..."

    # 生成BASE_URL
    local base_url=""
    if [ -n "$DOMAIN_NAME" ]; then
        if [ "$ENABLE_SSL" = true ]; then
            base_url="https://$DOMAIN_NAME"
        else
            if [ "$NGINX_PORT" = "80" ]; then
                base_url="http://$DOMAIN_NAME"
            else
                base_url="http://$DOMAIN_NAME:$NGINX_PORT"
            fi
        fi
    else
        if [ "$NGINX_PORT" = "80" ]; then
            base_url="http://localhost"
        else
            base_url="http://localhost:$NGINX_PORT"
        fi
    fi

    # 备份现有的.env文件
    if [ -f "$env_file" ]; then
        cp "$env_file" "${env_file}.backup.$(date +%Y%m%d_%H%M%S)"
        log_info "已备份现有 .env 文件"
    fi

    # 写入新的环境配置
    cat > "$env_file" << EOF
# Telegram Channel Bot Environment Configuration
# Generated by deployment script at $(date)

# 端口配置
WEB_PORT=$WEB_PORT
NGINX_PORT=$NGINX_PORT
REDIS_PORT=$REDIS_PORT

# 域名配置
DOMAIN_NAME=$DOMAIN_NAME
ENABLE_SSL=$ENABLE_SSL

# URL配置
BASE_URL=$base_url
API_URL=$base_url

# 环境标识
ENVIRONMENT=production
DEPLOYMENT_TIME=$(date -Iseconds)
EOF

    log_success "环境配置文件已生成: $env_file"

    # 显示生成的配置
    if [ "$VERBOSE" = true ]; then
        echo "生成的环境配置:"
        cat "$env_file" | grep -E "^[A-Z]" | sed 's/^/  /'
    fi
}

# 生成环境配置文件（在交互式配置后立即生成）
if [ "$INTERACTIVE_MODE" = true ] || [ -n "$DOMAIN_NAME" ]; then
    generate_env_file
fi

# 版本比较函数
version_compare() {
    local version1=$1
    local version2=$2

    if [ "$(printf '%s\n' "$version1" "$version2" | sort -V | head -n1)" = "$version2" ]; then
        return 0  # version1 >= version2
    else
        return 1  # version1 < version2
    fi
}

# 检查系统信息
check_system_info() {
    log_info "检查系统信息..."

    # 检查Ubuntu版本
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        if [ "$ID" != "ubuntu" ]; then
            log_warning "检测到非Ubuntu系统: $ID $VERSION_ID"
            log_warning "此脚本专为Ubuntu 24.04设计，可能需要调整"
        elif [ "$VERSION_ID" != "24.04" ]; then
            log_warning "检测到Ubuntu版本: $VERSION_ID (推荐: 24.04)"
        else
            log_success "Ubuntu 24.04 系统检查通过"
        fi
    else
        log_error "无法检测系统版本"
        return 1
    fi

    # 检查用户权限
    if [ "$EUID" -eq 0 ]; then
        log_warning "检测到root用户，推荐使用普通用户配合sudo"
    else
        if sudo -n true 2>/dev/null; then
            log_success "sudo权限检查通过"
        else
            log_error "当前用户需要sudo权限才能完成部署"
            log_info "请运行: sudo usermod -aG sudo $USER"
            return 1
        fi
    fi

    # 检查网络连接
    if ping -c 1 8.8.8.8 >/dev/null 2>&1; then
        log_success "网络连接正常"
    else
        log_error "网络连接异常，无法访问外网"
        return 1
    fi

    return 0
}

# 检查Python环境
check_python() {
    log_info "检查Python环境..."

    # 检查Python版本
    if command -v python3 >/dev/null 2>&1; then
        local python_version=$(python3 --version | cut -d' ' -f2)
        [ "$VERBOSE" = true ] && log_info "检测到Python版本: $python_version"

        if version_compare "$python_version" "$PYTHON_MIN_VERSION"; then
            log_success "Python版本符合要求: $python_version >= $PYTHON_MIN_VERSION"
        else
            log_error "Python版本过低: $python_version < $PYTHON_MIN_VERSION"
            if [ "$INSTALL_DEPS" = true ]; then
                log_info "尝试升级Python..."
                sudo apt update
                sudo apt install -y python3.11 python3.11-venv python3.11-dev
            fi
            return 1
        fi
    else
        log_error "Python3未安装"
        if [ "$INSTALL_DEPS" = true ]; then
            log_info "安装Python3..."
            sudo apt update
            sudo apt install -y python3.11 python3.11-venv python3.11-dev
        fi
        return 1
    fi

    # 检查pip
    if command -v pip3 >/dev/null 2>&1; then
        log_success "pip3已安装"
    else
        log_error "pip3未安装"
        if [ "$INSTALL_DEPS" = true ]; then
            log_info "安装pip3..."
            sudo apt install -y python3-pip
        fi
        return 1
    fi

    # 检查虚拟环境支持
    if python3 -m venv --help >/dev/null 2>&1; then
        log_success "Python虚拟环境支持正常"
    else
        log_error "Python虚拟环境模块缺失"
        if [ "$INSTALL_DEPS" = true ]; then
            log_info "安装python3-venv..."
            sudo apt install -y python3-venv
        fi
        return 1
    fi

    return 0
}

# 检查Redis
check_redis() {
    log_info "检查Redis服务..."

    # 检查Redis安装
    if command -v redis-server >/dev/null 2>&1; then
        local redis_version=$(redis-server --version | grep -oP 'v=\K[0-9.]+' | head -1)
        [ "$VERBOSE" = true ] && log_info "检测到Redis版本: $redis_version"

        if version_compare "$redis_version" "$REDIS_MIN_VERSION"; then
            log_success "Redis版本符合要求: $redis_version >= $REDIS_MIN_VERSION"
        else
            log_warning "Redis版本较低: $redis_version < $REDIS_MIN_VERSION"
        fi
    else
        log_error "Redis未安装"
        if [ "$INSTALL_DEPS" = true ]; then
            log_info "安装Redis..."
            sudo apt update
            sudo apt install -y redis-server
        fi
        return 1
    fi

    # 检查Redis客户端
    if command -v redis-cli >/dev/null 2>&1; then
        log_success "Redis客户端已安装"
    else
        log_error "Redis客户端未安装"
        if [ "$INSTALL_DEPS" = true ]; then
            sudo apt install -y redis-tools
        fi
        return 1
    fi

    # 检查Redis服务状态
    if systemctl is-active --quiet redis; then
        log_success "Redis服务正在运行"

        # 测试连接
        if redis-cli -p $REDIS_PORT ping >/dev/null 2>&1; then
            log_success "Redis连接测试通过"
        else
            log_warning "Redis服务运行中但连接失败"
        fi
    else
        log_warning "Redis服务未启动"
        if [ "$INSTALL_DEPS" = true ]; then
            log_info "启动Redis服务..."
            sudo systemctl enable redis
            sudo systemctl start redis
        fi
    fi

    return 0
}

# 检查Nginx
check_nginx() {
    log_info "检查Nginx服务..."

    # 检查Nginx安装
    if command -v nginx >/dev/null 2>&1; then
        local nginx_version=$(nginx -v 2>&1 | grep -oP 'nginx/\K[0-9.]+')
        [ "$VERBOSE" = true ] && log_info "检测到Nginx版本: $nginx_version"

        if version_compare "$nginx_version" "$NGINX_MIN_VERSION"; then
            log_success "Nginx版本符合要求: $nginx_version >= $NGINX_MIN_VERSION"
        else
            log_warning "Nginx版本较低: $nginx_version < $NGINX_MIN_VERSION"
        fi
    else
        log_error "Nginx未安装"
        if [ "$INSTALL_DEPS" = true ]; then
            log_info "安装Nginx..."
            sudo apt update
            sudo apt install -y nginx
        fi
        return 1
    fi

    # 检查Nginx服务状态
    if systemctl is-active --quiet nginx; then
        log_success "Nginx服务正在运行"
    else
        log_warning "Nginx服务未启动"
        if [ "$INSTALL_DEPS" = true ]; then
            log_info "启动Nginx服务..."
            sudo systemctl enable nginx
            sudo systemctl start nginx
        fi
    fi

    # 检查Nginx配置语法
    if sudo nginx -t >/dev/null 2>&1; then
        log_success "Nginx配置语法正确"
    else
        log_error "Nginx配置存在语法错误"
        [ "$VERBOSE" = true ] && sudo nginx -t
    fi

    return 0
}

# 配置Nginx站点
configure_nginx() {
    if [ "$CONFIG_NGINX" != true ]; then
        return 0
    fi

    log_info "配置Nginx站点..."

    # 检查Nginx是否安装
    if ! command -v nginx &> /dev/null; then
        log_error "Nginx未安装，无法配置站点"
        return 1
    fi

    # 检查并创建Nginx配置目录
    if [ ! -d "/etc/nginx" ]; then
        log_error "Nginx配置目录不存在，请确保Nginx正确安装"
        return 1
    fi

    # 创建sites-available和sites-enabled目录（如果不存在）
    sudo mkdir -p /etc/nginx/sites-available
    sudo mkdir -p /etc/nginx/sites-enabled

    # 检查Nginx主配置文件是否包含sites-enabled
    local nginx_conf="/etc/nginx/nginx.conf"
    if [ -f "$nginx_conf" ]; then
        if ! sudo grep -q "sites-enabled" "$nginx_conf"; then
            log_warning "Nginx主配置可能不包含sites-enabled目录"
            log_info "请确保 $nginx_conf 中有: include /etc/nginx/sites-enabled/*;"
        fi
    fi

    local site_config="/etc/nginx/sites-available/$PROJECT_NAME"
    local site_enabled="/etc/nginx/sites-enabled/$PROJECT_NAME"

    # 检查sudo权限
    if ! sudo -n true 2>/dev/null; then
        log_error "需要sudo权限配置Nginx"
        return 1
    fi

    # 确定server_name配置
    local server_name="localhost"
    if [ -n "$DOMAIN_NAME" ]; then
        server_name="$DOMAIN_NAME"
        log_info "配置域名: $DOMAIN_NAME"
    else
        log_info "使用默认: localhost"
    fi

    # 创建站点配置
    log_info "创建Nginx站点配置: $site_config"
    sudo tee "$site_config" > /dev/null << EOF
# Telegram Channel Bot Nginx配置
# 生成时间: $(date)

server {
    listen $NGINX_PORT;
    server_name $server_name;

    # 安全头设置
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # 日志配置
    access_log /var/log/nginx/${PROJECT_NAME}_access.log;
    error_log /var/log/nginx/${PROJECT_NAME}_error.log;

    # 静态文件服务
    location /static/ {
        alias $PROJECT_ROOT/static/;
        expires 1h;
        add_header Cache-Control "public, immutable";

        # 静态文件类型
        location ~* \.(css|js|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
            expires 1y;
            add_header Cache-Control "public, immutable";
        }
    }

    # 临时媒体文件
    location /temp_media/ {
        alias $PROJECT_ROOT/temp_media/;
        expires 1h;
        add_header Cache-Control "public";
        add_header X-Served-By "nginx-temp";

        # 媒体文件类型
        location ~* \.(jpg|jpeg|png|gif|webp|mp4|webm|pdf)$ {
            expires 7d;
            add_header Cache-Control "public";
        }
    }

    # API代理
    location /api/ {
        proxy_pass http://127.0.0.1:$WEB_PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;

        # 超时设置
        proxy_connect_timeout 30s;
        proxy_send_timeout 30s;
        proxy_read_timeout 30s;
    }

    # WebSocket代理
    location /ws {
        proxy_pass http://127.0.0.1:$WEB_PORT;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;

        # WebSocket特定设置
        proxy_read_timeout 86400;
    }

    # 健康检查
    location /health {
        proxy_pass http://127.0.0.1:$WEB_PORT/api/health;
        access_log off;
    }

    # 默认首页
    location = / {
        return 302 /static/login.html;
    }

    # 安全：隐藏敏感文件
    location ~ /\. {
        deny all;
        access_log off;
        log_not_found off;
    }

    location ~ \.(py|sh|log|conf)$ {
        deny all;
        access_log off;
        log_not_found off;
    }
}
EOF

    # 验证配置文件创建成功
    if [ ! -f "$site_config" ]; then
        log_error "站点配置文件创建失败: $site_config"
        return 1
    fi

    log_success "Nginx站点配置文件已创建"

    # 启用站点
    if [ ! -e "$site_enabled" ]; then
        log_info "启用站点配置..."
        if sudo ln -s "$site_config" "$site_enabled" 2>/dev/null; then
            log_success "Nginx站点配置已启用"
        else
            log_error "启用站点配置失败"
            return 1
        fi
    else
        # 如果链接已存在，先删除再重新创建
        log_info "更新现有站点配置..."
        sudo rm "$site_enabled" 2>/dev/null || true
        if sudo ln -s "$site_config" "$site_enabled" 2>/dev/null; then
            log_success "Nginx站点配置已更新"
        else
            log_error "更新站点配置失败"
            return 1
        fi
    fi

    # 禁用默认站点（避免冲突）
    if [ -e "/etc/nginx/sites-enabled/default" ]; then
        log_info "禁用默认站点以避免端口冲突..."
        if sudo rm "/etc/nginx/sites-enabled/default" 2>/dev/null; then
            log_success "已禁用Nginx默认站点"
        else
            log_warning "无法禁用默认站点，可能会有端口冲突"
        fi
    fi

    # 检查并修复nginx主配置的include设置
    if ! sudo grep -q "sites-enabled" /etc/nginx/nginx.conf; then
        log_info "修复Nginx主配置的sites-enabled包含设置..."

        # 在http块中添加include语句
        sudo sed -i '/http {/a\\t# Include site configurations' /etc/nginx/nginx.conf
        sudo sed -i '/# Include site configurations/a\\tinclude /etc/nginx/sites-enabled/*;' /etc/nginx/nginx.conf

        log_success "已添加sites-enabled包含设置到nginx.conf"
    fi

    # 验证配置被正确加载
    log_info "验证站点配置是否被正确加载..."
    if sudo nginx -T 2>/dev/null | grep -q "$server_name"; then
        log_success "站点配置已被Nginx正确加载"
    else
        log_error "站点配置未被Nginx加载，请检查配置"
        log_info "手动检查命令: sudo nginx -T | grep '$server_name'"
        return 1
    fi

    # 测试配置并重新加载
    if sudo nginx -t >/dev/null 2>&1; then
        sudo systemctl reload nginx
        log_success "Nginx配置已重新加载"
    else
        log_error "Nginx配置测试失败"
        sudo nginx -t
        return 1
    fi

    return 0
}

# 配置SSL证书
configure_ssl() {
    if [ "$ENABLE_SSL" != true ] || [ -z "$DOMAIN_NAME" ]; then
        return 0
    fi

    log_info "配置SSL证书..."

    # 检查Certbot是否安装
    if ! command -v certbot &> /dev/null; then
        log_info "安装Certbot..."
        sudo apt update
        sudo apt install -y certbot python3-certbot-nginx
        log_success "Certbot安装完成"
    fi

    # 申请SSL证书
    local email_param=""
    if [ -n "$ADMIN_EMAIL" ]; then
        email_param="--email $ADMIN_EMAIL"
    else
        email_param="--register-unsafely-without-email"
    fi

    log_info "申请SSL证书 for $DOMAIN_NAME..."

    # 检查证书是否已存在
    if sudo certbot certificates 2>/dev/null | grep -q "$DOMAIN_NAME"; then
        log_info "检测到现有证书，尝试安装..."

        # 尝试安装现有证书
        if sudo certbot install --cert-name "$DOMAIN_NAME" --nginx --non-interactive; then
            log_success "现有证书安装成功"
        else
            log_warning "现有证书安装失败，删除并重新申请..."

            # 删除现有证书和配置
            sudo certbot delete --cert-name "$DOMAIN_NAME" --non-interactive 2>/dev/null || true

            # 重新申请证书
            if sudo certbot --nginx -d "$DOMAIN_NAME" \
                --non-interactive \
                --agree-tos \
                $email_param \
                --redirect; then
                log_success "SSL证书重新申请成功"
            else
                log_error "SSL证书重新申请失败"
                return 1
            fi
        fi
    else
        # 首次申请证书
        if sudo certbot --nginx -d "$DOMAIN_NAME" \
            --non-interactive \
            --agree-tos \
            $email_param \
            --redirect; then
            log_success "SSL证书申请成功"
        else
            log_error "SSL证书申请失败"

            # 如果失败，进行详细诊断
            log_info "进行SSL配置失败诊断..."

            # 检查Nginx配置
            if sudo nginx -t >/dev/null 2>&1; then
                log_info "✓ Nginx配置语法正确"

                # 检查域名配置是否被加载
                if sudo nginx -T 2>/dev/null | grep -q "$DOMAIN_NAME"; then
                    log_info "✓ 域名配置已被Nginx加载"
                    log_info "可能原因：域名DNS解析问题"
                    log_info "检查命令：dig +short $DOMAIN_NAME"
                else
                    log_error "✗ 域名配置未被Nginx加载"
                    log_info "手动检查：sudo nginx -T | grep '$DOMAIN_NAME'"
                fi

                # 测试Certbot配置识别
                log_info "测试Certbot是否能识别配置..."
                if sudo certbot certificates 2>/dev/null | grep -q "$DOMAIN_NAME"; then
                    log_info "Certbot可识别现有证书，尝试手动安装："
                    log_info "sudo certbot install --cert-name $DOMAIN_NAME --nginx"
                else
                    log_info "Certbot未识别到配置，尝试详细诊断："
                    log_info "sudo certbot certonly --nginx --dry-run -d $DOMAIN_NAME -v"
                fi
            else
                log_error "✗ Nginx配置语法错误"
                sudo nginx -t
            fi
            return 1
        fi
    fi

    # 设置自动续期
    if ! sudo crontab -l 2>/dev/null | grep -q "certbot renew"; then
        (sudo crontab -l 2>/dev/null; echo "0 0,12 * * * /usr/bin/certbot renew --quiet") | sudo crontab -
        log_success "已设置SSL证书自动续期"
    fi

    return 0
}

# 安装系统服务
install_system_service() {
    log_info "安装系统服务..."

    # 检查服务管理器是否存在
    local service_manager="$SCRIPT_DIR/service_manager.sh"
    if [ ! -f "$service_manager" ]; then
        log_error "服务管理器不存在: $service_manager"
        return 1
    fi

    # 检查是否有sudo权限
    if ! sudo -n true 2>/dev/null; then
        log_error "安装系统服务需要sudo权限"
        return 1
    fi

    # 使用服务管理器安装服务
    log_info "运行服务安装器..."
    if sudo "$service_manager" install; then
        log_success "系统服务安装成功"

        # 启用开机自启动
        if sudo "$service_manager" enable; then
            log_success "开机自启动已启用"
        fi

        log_info "服务管理命令："
        log_info "  启动服务: sudo systemctl start telegram-channel-bot"
        log_info "  停止服务: sudo systemctl stop telegram-channel-bot"
        log_info "  重启服务: sudo systemctl restart telegram-channel-bot"
        log_info "  查看状态: sudo systemctl status telegram-channel-bot"
        log_info "  查看日志: sudo journalctl -u telegram-channel-bot -f"

    else
        log_error "系统服务安装失败"
        return 1
    fi

    return 0
}

# 检查端口占用
check_ports() {
    log_info "检查端口占用情况..."

    local ports=($WEB_PORT $NGINX_PORT $REDIS_PORT)
    local port_names=("API服务" "Web前端" "Redis")

    for i in "${!ports[@]}"; do
        local port=${ports[$i]}
        local name=${port_names[$i]}

        if netstat -tuln 2>/dev/null | grep -q ":$port "; then
            log_success "$name端口 $port 正在使用中"
        else
            log_warning "$name端口 $port 空闲"
        fi
    done

    return 0
}

# 配置防火墙
configure_firewall() {
    if [ "$SKIP_FIREWALL" = true ]; then
        return 0
    fi

    log_info "配置防火墙..."

    # 检查ufw状态
    if command -v ufw >/dev/null 2>&1; then
        local ufw_status=$(sudo ufw status | head -1)
        [ "$VERBOSE" = true ] && log_info "UFW状态: $ufw_status"

        if [[ "$ufw_status" == *"inactive"* ]]; then
            log_info "启用UFW防火墙..."
            echo "y" | sudo ufw enable
        fi

        # 允许SSH（防止锁定）
        sudo ufw allow ssh >/dev/null 2>&1

        # 允许项目端口
        sudo ufw allow $NGINX_PORT/tcp comment "Telegram Bot Web" >/dev/null 2>&1
        sudo ufw allow $WEB_PORT/tcp comment "Telegram Bot API" >/dev/null 2>&1

        log_success "防火墙规则已配置"
    else
        log_warning "UFW未安装，跳过防火墙配置"
    fi

    return 0
}

# 确保Python venv模块已安装
ensure_venv_installed() {
    if python3 -m venv --help &>/dev/null; then
        return 0  # venv已安装
    fi

    log_warning "Python venv模块未安装"

    if [ "$INSTALL_DEPS" != true ]; then
        log_error "请先安装python3-venv包:"
        log_error "  sudo apt update"
        log_error "  sudo apt install python3-venv python3.12-venv"
        return 1
    fi

    log_info "安装python3-venv包..."

    # 检测Python版本
    PYTHON_VERSION=$(python3 --version | grep -oE '[0-9]+\.[0-9]+')
    log_info "检测到Python版本: $PYTHON_VERSION"

    log_info "更新包列表..."
    if ! sudo apt update; then
        log_error "apt update失败"
        return 1
    fi

    # 尝试分别安装每个包，以便看到具体错误
    local packages_to_try=("python3-venv" "python${PYTHON_VERSION}-venv" "python3.12-venv")
    local installed=false

    for package in "${packages_to_try[@]}"; do
        log_info "尝试安装 $package..."

        # 不隐藏错误输出，这样可以看到具体问题
        if sudo apt install -y $package; then
            log_success "$package 安装成功"

            # 验证是否可用
            if python3 -m venv --help &>/dev/null; then
                log_success "venv模块已可用"
                installed=true
                break
            else
                log_warning "$package 已安装但venv仍不可用，继续尝试..."
            fi
        else
            log_warning "$package 安装失败或已安装，继续尝试下一个包..."
        fi
    done

    if [ "$installed" = true ]; then
        return 0
    else
        log_error "无法安装python3-venv"
        log_error "请手动运行以下命令："
        log_error "  sudo apt update"
        log_error "  sudo apt install -y python3-venv python3.12-venv"
        log_error ""
        log_error "如果仍然失败，可能需要："
        log_error "  sudo apt install -y python3-pip python3-dev"
        log_error "  sudo apt install -y build-essential"
        return 1
    fi
}

# 检查项目依赖
check_project_deps() {
    log_info "检查项目Python依赖..."

    # 检查requirements.txt
    if [ ! -f "$PROJECT_ROOT/requirements.txt" ]; then
        log_error "requirements.txt文件不存在于: $PROJECT_ROOT"
        return 1
    fi

    # 创建必要的项目目录
    log_info "创建必要的项目目录..."
    mkdir -p "$PROJECT_ROOT/logs"
    mkdir -p "$PROJECT_ROOT/data"
    mkdir -p "$PROJECT_ROOT/temp_media"
    mkdir -p "$PROJECT_ROOT/logs/pids"
    log_success "项目目录已创建"

    # 检查虚拟环境
    if [ -d "$PROJECT_ROOT/venv" ]; then
        log_success "虚拟环境目录存在"

        # 检查虚拟环境是否可用
        if [ -f "$PROJECT_ROOT/venv/bin/activate" ]; then
            log_success "虚拟环境配置正常"

            # 检查已安装的包
            if [ "$VERBOSE" = true ]; then
                source "$PROJECT_ROOT/venv/bin/activate"
                local installed_count=$(pip list --format=freeze | wc -l)
                log_info "已安装Python包数量: $installed_count"
                deactivate
            fi
        else
            log_error "虚拟环境损坏"
            if [ "$INSTALL_DEPS" = true ]; then
                log_info "删除损坏的虚拟环境..."
                rm -rf "$PROJECT_ROOT/venv"

                # 确保venv模块已安装
                if ! ensure_venv_installed; then
                    log_error "无法安装python3-venv，虚拟环境创建失败"
                    return 1
                fi

                log_info "重新创建虚拟环境..."
                if python3 -m venv "$PROJECT_ROOT/venv"; then
                    source "$PROJECT_ROOT/venv/bin/activate"
                    pip install --upgrade pip
                    pip install -r "$PROJECT_ROOT/requirements.txt"
                    deactivate
                    log_success "虚拟环境重建完成"
                else
                    log_error "虚拟环境创建失败"
                    log_error "请检查Python安装是否完整"
                    return 1
                fi
            else
                return 1
            fi
        fi
    else
        log_warning "虚拟环境不存在"
        if [ "$INSTALL_DEPS" = true ]; then
            # 确保venv模块已安装
            if ! ensure_venv_installed; then
                log_error "无法安装python3-venv，虚拟环境创建失败"
                return 1
            fi

            log_info "创建虚拟环境..."
            if python3 -m venv "$PROJECT_ROOT/venv"; then
                source "$PROJECT_ROOT/venv/bin/activate"
                pip install --upgrade pip
                pip install -r "$PROJECT_ROOT/requirements.txt"
                deactivate
                log_success "虚拟环境创建完成"
            else
                log_error "虚拟环境创建失败"
                log_error "请检查Python安装是否完整"
                return 1
            fi
        else
            log_error "虚拟环境不存在，请使用 --install-deps 选项创建"
            return 1
        fi
    fi

    return 0
}

# 生成部署报告
generate_report() {
    log_info "生成部署报告..."

    local report_file="deployment_report_$(date +%Y%m%d_%H%M%S).txt"

    cat > "$report_file" << EOF
Ubuntu 24.04 Telegram Channel Bot 部署报告
=============================================
生成时间: $(date)
主机名: $(hostname)
系统: $(lsb_release -d | cut -f2)
用户: $(whoami)

检查结果:
---------
EOF

    # 添加各项检查结果
    echo "Python: $(python3 --version 2>/dev/null || echo '未安装')" >> "$report_file"
    echo "Redis: $(redis-server --version 2>/dev/null | grep -oP 'v=\K[0-9.]+' | head -1 || echo '未安装')" >> "$report_file"
    echo "Nginx: $(nginx -v 2>&1 | grep -oP 'nginx/\K[0-9.]+' || echo '未安装')" >> "$report_file"

    echo "" >> "$report_file"
    echo "服务状态:" >> "$report_file"
    echo "Redis: $(systemctl is-active redis 2>/dev/null || echo '未知')" >> "$report_file"
    echo "Nginx: $(systemctl is-active nginx 2>/dev/null || echo '未知')" >> "$report_file"

    echo "" >> "$report_file"
    echo "网络配置:" >> "$report_file"
    echo "Web端口: $NGINX_PORT" >> "$report_file"
    echo "API端口: $WEB_PORT" >> "$report_file"
    echo "Redis端口: $REDIS_PORT" >> "$report_file"

    echo "" >> "$report_file"
    echo "访问地址:" >> "$report_file"
    echo "Web界面: http://$(hostname -I | awk '{print $1}'):$NGINX_PORT" >> "$report_file"
    echo "API文档: http://$(hostname -I | awk '{print $1}'):$NGINX_PORT/api/docs" >> "$report_file"

    log_success "部署报告已生成: $report_file"
}

# 主函数
main() {
    echo "🚀 Ubuntu 24.04 Telegram Channel Bot 部署检查器"
    echo "=================================================="
    echo ""

    # 切换到项目根目录
    log_info "项目根目录: $PROJECT_ROOT"
    cd "$PROJECT_ROOT" || {
        log_error "无法切换到项目目录: $PROJECT_ROOT"
        exit 1
    }

    local exit_code=0

    # 系统检查
    check_system_info || exit_code=1
    echo ""

    # 依赖检查
    check_python || exit_code=1
    echo ""

    check_redis || exit_code=1
    echo ""

    check_nginx || exit_code=1
    echo ""

    # 配置阶段
    if [ "$CHECK_ONLY" != true ]; then
        configure_nginx || exit_code=1
        echo ""

        configure_ssl || exit_code=1
        echo ""

        configure_firewall || exit_code=1
        echo ""

        check_project_deps || exit_code=1
        echo ""

        # 安装系统服务（如果选择）
        if [ "$INSTALL_SERVICE" = true ]; then
            install_system_service || exit_code=1
            echo ""
        fi
    fi

    # 端口检查
    check_ports
    echo ""

    # 生成报告
    generate_report
    echo ""

    # 最终结果
    if [ $exit_code -eq 0 ]; then
        log_success "🎉 部署检查完成！所有依赖和配置正常"
        echo ""

        # 动态生成访问地址
        local web_url
        if [ -n "$DOMAIN_NAME" ]; then
            if [ "$ENABLE_SSL" = true ]; then
                web_url="https://$DOMAIN_NAME"
            else
                if [ "$NGINX_PORT" = "80" ]; then
                    web_url="http://$DOMAIN_NAME"
                else
                    web_url="http://$DOMAIN_NAME:$NGINX_PORT"
                fi
            fi
        else
            if [ "$NGINX_PORT" = "80" ]; then
                web_url="http://localhost"
            else
                web_url="http://localhost:$NGINX_PORT"
            fi
        fi

        echo "后续步骤:"
        echo "1. 启动服务: cd $PROJECT_ROOT && ./start.sh"
        echo "2. 访问Web界面: $web_url"
        echo "3. 查看日志: tail -f $PROJECT_ROOT/logs/app.log"

        if [ -n "$DOMAIN_NAME" ]; then
            echo ""
            echo "📌 访问方式:"
            echo "   - 域名访问: $web_url"
            echo "   - 本地访问: http://localhost:$NGINX_PORT"
        fi
    else
        log_error "❌ 部署检查发现问题，请检查上述错误信息"
        echo ""
        echo "建议操作:"
        echo "1. 使用 --install-deps 自动安装缺失依赖"
        echo "2. 手动解决权限和网络问题"
        echo "3. 重新运行检查脚本"
    fi

    exit $exit_code
}

# 运行主函数
main "$@"