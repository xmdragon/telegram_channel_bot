#!/bin/bash

# Telegram Channel Bot 系统服务管理脚本
# 用于创建、安装、管理systemd服务

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# 获取脚本目录
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/../.." &> /dev/null && pwd )"

# 配置变量
SERVICE_NAME="telegram-channel-bot"
SERVICE_FILE="$SCRIPT_DIR/$SERVICE_NAME.service"
SYSTEM_SERVICE_PATH="/etc/systemd/system/$SERVICE_NAME.service"
SERVICE_USER="telegram-bot"
SERVICE_GROUP="telegram-bot"
INSTALL_PATH="/opt/telegram-channel-bot"

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

# 显示帮助
show_help() {
    echo "Telegram Channel Bot 系统服务管理器"
    echo ""
    echo "用法: $0 <命令> [选项]"
    echo ""
    echo "命令:"
    echo "  install        安装系统服务"
    echo "  uninstall      卸载系统服务"
    echo "  start          启动服务"
    echo "  stop           停止服务"
    echo "  restart        重启服务"
    echo "  status         查看服务状态"
    echo "  logs           查看服务日志"
    echo "  enable         启用开机自启动"
    echo "  disable        禁用开机自启动"
    echo ""
    echo "选项:"
    echo "  --user USER    指定运行用户 (默认: $SERVICE_USER)"
    echo "  --path PATH    指定安装路径 (默认: $INSTALL_PATH)"
    echo "  --help, -h     显示帮助信息"
}

# 检查是否为root用户
check_root() {
    if [ "$EUID" -ne 0 ]; then
        log_error "此操作需要root权限，请使用sudo运行"
        return 1
    fi
}

# 创建系统用户
create_service_user() {
    if ! id "$SERVICE_USER" &>/dev/null; then
        log_info "创建系统用户: $SERVICE_USER"
        useradd --system --home-dir "$INSTALL_PATH" --shell /bin/false --create-home "$SERVICE_USER"
        log_success "用户 $SERVICE_USER 创建成功"
    else
        log_info "用户 $SERVICE_USER 已存在"
    fi
}

# 部署应用文件
deploy_application() {
    log_info "部署应用到 $INSTALL_PATH"

    # 创建安装目录
    mkdir -p "$INSTALL_PATH"

    # 复制应用文件
    log_info "复制应用文件..."
    cp -r "$PROJECT_ROOT"/* "$INSTALL_PATH/"

    # 创建必要目录
    mkdir -p "$INSTALL_PATH/logs" "$INSTALL_PATH/data" "$INSTALL_PATH/temp_media" "$INSTALL_PATH/logs/pids"

    # 设置权限
    chown -R "$SERVICE_USER:$SERVICE_GROUP" "$INSTALL_PATH"
    chmod +x "$INSTALL_PATH/start.sh" "$INSTALL_PATH/stop.sh" "$INSTALL_PATH/restart.sh" "$INSTALL_PATH/dev.sh"

    log_success "应用部署完成"
}

# 安装Python环境
install_python_env() {
    log_info "设置Python虚拟环境..."

    # 切换到应用用户执行
    sudo -u "$SERVICE_USER" bash -c "
        cd '$INSTALL_PATH'
        python3 -m venv venv
        source venv/bin/activate
        pip install -r requirements.txt
        touch venv/installed.flag
    "

    log_success "Python环境设置完成"
}

# 安装服务
install_service() {
    log_info "安装 $SERVICE_NAME 系统服务..."

    # 检查服务文件是否存在
    if [ ! -f "$SERVICE_FILE" ]; then
        log_error "服务文件不存在: $SERVICE_FILE"
        return 1
    fi

    # 创建用户
    create_service_user

    # 部署应用
    deploy_application

    # 安装Python环境
    install_python_env

    # 复制服务文件
    log_info "安装systemd服务文件..."
    sed "s|/opt/telegram-channel-bot|$INSTALL_PATH|g; s|User=telegram-bot|User=$SERVICE_USER|g; s|Group=telegram-bot|Group=$SERVICE_GROUP|g" \
        "$SERVICE_FILE" > "$SYSTEM_SERVICE_PATH"

    # 重新加载systemd
    systemctl daemon-reload

    log_success "服务安装完成"
    log_info "使用以下命令管理服务:"
    log_info "  启动: sudo systemctl start $SERVICE_NAME"
    log_info "  停止: sudo systemctl stop $SERVICE_NAME"
    log_info "  状态: sudo systemctl status $SERVICE_NAME"
    log_info "  开机自启: sudo systemctl enable $SERVICE_NAME"
}

# 卸载服务
uninstall_service() {
    log_info "卸载 $SERVICE_NAME 系统服务..."

    # 停止并禁用服务
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        systemctl stop "$SERVICE_NAME"
        log_info "服务已停止"
    fi

    if systemctl is-enabled --quiet "$SERVICE_NAME"; then
        systemctl disable "$SERVICE_NAME"
        log_info "服务自启动已禁用"
    fi

    # 删除服务文件
    if [ -f "$SYSTEM_SERVICE_PATH" ]; then
        rm "$SYSTEM_SERVICE_PATH"
        log_info "服务文件已删除"
    fi

    # 重新加载systemd
    systemctl daemon-reload

    log_warning "应用文件保留在 $INSTALL_PATH，如需完全删除请手动删除"
    log_success "服务卸载完成"
}

# 服务控制函数
start_service() {
    log_info "启动服务..."
    systemctl start "$SERVICE_NAME"
    sleep 2
    systemctl status "$SERVICE_NAME" --no-pager
}

stop_service() {
    log_info "停止服务..."
    systemctl stop "$SERVICE_NAME"
    systemctl status "$SERVICE_NAME" --no-pager
}

restart_service() {
    log_info "重启服务..."
    systemctl restart "$SERVICE_NAME"
    sleep 2
    systemctl status "$SERVICE_NAME" --no-pager
}

show_status() {
    systemctl status "$SERVICE_NAME" --no-pager -l
}

show_logs() {
    journalctl -u "$SERVICE_NAME" -f --no-pager
}

enable_service() {
    log_info "启用开机自启动..."
    systemctl enable "$SERVICE_NAME"
    log_success "开机自启动已启用"
}

disable_service() {
    log_info "禁用开机自启动..."
    systemctl disable "$SERVICE_NAME"
    log_success "开机自启动已禁用"
}

# 解析命令行参数
while [[ $# -gt 0 ]]; do
    case $1 in
        install)
            COMMAND="install"
            shift
            ;;
        uninstall)
            COMMAND="uninstall"
            shift
            ;;
        start)
            COMMAND="start"
            shift
            ;;
        stop)
            COMMAND="stop"
            shift
            ;;
        restart)
            COMMAND="restart"
            shift
            ;;
        status)
            COMMAND="status"
            shift
            ;;
        logs)
            COMMAND="logs"
            shift
            ;;
        enable)
            COMMAND="enable"
            shift
            ;;
        disable)
            COMMAND="disable"
            shift
            ;;
        --user)
            SERVICE_USER="$2"
            SERVICE_GROUP="$2"
            shift 2
            ;;
        --path)
            INSTALL_PATH="$2"
            shift 2
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

# 执行命令
case $COMMAND in
    install)
        check_root || exit 1
        install_service
        ;;
    uninstall)
        check_root || exit 1
        uninstall_service
        ;;
    start)
        check_root || exit 1
        start_service
        ;;
    stop)
        check_root || exit 1
        stop_service
        ;;
    restart)
        check_root || exit 1
        restart_service
        ;;
    status)
        show_status
        ;;
    logs)
        show_logs
        ;;
    enable)
        check_root || exit 1
        enable_service
        ;;
    disable)
        check_root || exit 1
        disable_service
        ;;
    *)
        log_error "请指定命令"
        show_help
        exit 1
        ;;
esac