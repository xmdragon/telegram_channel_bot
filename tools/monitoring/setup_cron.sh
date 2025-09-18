#!/bin/bash

# 设置看门狗定时任务
# 用于自动监控和恢复服务

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/../.." &> /dev/null && pwd )"

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# 日志函数
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 显示帮助
show_help() {
    cat << EOF
看门狗定时任务设置脚本

用法: $0 [选项]

选项:
    install     安装定时任务
    uninstall   移除定时任务
    status      查看定时任务状态
    test        测试看门狗脚本
    --help, -h  显示帮助信息

定时任务说明:
    - 每5分钟执行一次看门狗检查
    - 每天凌晨2点执行深度健康检查
    - 日志保存在 $PROJECT_ROOT/logs/

EOF
}

# 安装定时任务
install_cron() {
    log_info "安装看门狗定时任务..."

    # 检查脚本是否存在
    local watchdog_script="$SCRIPT_DIR/watchdog.sh"
    local health_check_script="$SCRIPT_DIR/health_check.py"

    if [ ! -f "$watchdog_script" ]; then
        log_error "看门狗脚本不存在: $watchdog_script"
        return 1
    fi

    if [ ! -f "$health_check_script" ]; then
        log_error "健康检查脚本不存在: $health_check_script"
        return 1
    fi

    # 创建临时cron文件
    local temp_cron=$(mktemp)

    # 保留现有的cron任务
    crontab -l 2>/dev/null | grep -v "telegram-channel-bot" > "$temp_cron" || true

    # 添加新的定时任务
    cat >> "$temp_cron" << EOF

# Telegram Channel Bot 监控任务
# 每5分钟执行看门狗检查
*/5 * * * * $watchdog_script --once >> $PROJECT_ROOT/logs/watchdog.log 2>&1

# 每天凌晨2点执行深度健康检查
0 2 * * * cd $PROJECT_ROOT && python3 $health_check_script --json >> $PROJECT_ROOT/logs/health_check.log 2>&1

# 每周日凌晨3点清理日志（保留最近30天）
0 3 * * 0 find $PROJECT_ROOT/logs -name "*.log" -mtime +30 -delete 2>/dev/null

EOF

    # 安装cron任务
    if crontab "$temp_cron"; then
        log_info "定时任务安装成功"
        rm -f "$temp_cron"
    else
        log_error "定时任务安装失败"
        rm -f "$temp_cron"
        return 1
    fi

    # 启动cron服务（如果未启动）
    if command -v systemctl >/dev/null 2>&1; then
        if ! systemctl is-active --quiet cron && ! systemctl is-active --quiet crond; then
            log_info "启动cron服务..."
            sudo systemctl start cron || sudo systemctl start crond || true
        fi
    fi

    log_info "安装完成！监控任务将每5分钟执行一次"
    log_info "查看日志: tail -f $PROJECT_ROOT/logs/watchdog.log"
}

# 移除定时任务
uninstall_cron() {
    log_info "移除看门狗定时任务..."

    # 创建临时cron文件
    local temp_cron=$(mktemp)

    # 保留其他cron任务，移除本项目的任务
    crontab -l 2>/dev/null | grep -v "telegram-channel-bot" > "$temp_cron" || true

    # 安装修改后的cron
    if crontab "$temp_cron"; then
        log_info "定时任务移除成功"
        rm -f "$temp_cron"
    else
        log_error "定时任务移除失败"
        rm -f "$temp_cron"
        return 1
    fi
}

# 查看定时任务状态
show_status() {
    log_info "查看定时任务状态..."

    echo "=== 当前定时任务 ==="
    crontab -l 2>/dev/null | grep -A5 -B1 "telegram-channel-bot" || echo "未找到相关定时任务"

    echo ""
    echo "=== Cron服务状态 ==="
    if command -v systemctl >/dev/null 2>&1; then
        systemctl status cron 2>/dev/null || systemctl status crond 2>/dev/null || echo "Cron服务状态未知"
    else
        echo "无法检查cron服务状态"
    fi

    echo ""
    echo "=== 最近的看门狗日志 ==="
    if [ -f "$PROJECT_ROOT/logs/watchdog.log" ]; then
        tail -10 "$PROJECT_ROOT/logs/watchdog.log"
    else
        echo "暂无看门狗日志"
    fi
}

# 测试看门狗
test_watchdog() {
    log_info "测试看门狗脚本..."

    local watchdog_script="$SCRIPT_DIR/watchdog.sh"

    if [ ! -f "$watchdog_script" ]; then
        log_error "看门狗脚本不存在: $watchdog_script"
        return 1
    fi

    log_info "执行看门狗状态检查..."
    "$watchdog_script" --status

    echo ""
    log_info "执行单次健康检查..."
    if "$watchdog_script" --once; then
        log_info "健康检查通过"
    else
        log_warning "健康检查发现问题"
    fi

    echo ""
    log_info "执行深度健康检查..."
    local health_check_script="$SCRIPT_DIR/health_check.py"
    if [ -f "$health_check_script" ]; then
        cd "$PROJECT_ROOT"
        python3 "$health_check_script" --verbose
    else
        log_warning "深度健康检查脚本不存在"
    fi
}

# 主逻辑
case "${1:-}" in
    install)
        install_cron
        ;;
    uninstall)
        uninstall_cron
        ;;
    status)
        show_status
        ;;
    test)
        test_watchdog
        ;;
    --help|-h)
        show_help
        ;;
    *)
        echo "请指定操作: install, uninstall, status, test"
        echo "使用 --help 查看详细帮助"
        exit 1
        ;;
esac