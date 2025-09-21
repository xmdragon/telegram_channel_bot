#!/bin/bash

# Telegram Channel Bot 看门狗脚本
# 外部监控脚本，定期检查主服务状态并进行恢复

# 设置脚本路径
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/../.." &> /dev/null && pwd )"

# 配置参数
SERVICE_NAME="telegram-channel-bot"
CHECK_INTERVAL=${CHECK_INTERVAL:-30}  # 检查间隔（秒）
MAX_RESTART_ATTEMPTS=${MAX_RESTART_ATTEMPTS:-3}  # 最大重启尝试次数
RESTART_COOLDOWN=${RESTART_COOLDOWN:-300}  # 重启冷却时间（秒）

# 日志配置
LOG_DIR="$PROJECT_ROOT/logs"
WATCHDOG_LOG="$LOG_DIR/watchdog.log"
ALERT_LOG="$LOG_DIR/watchdog_alerts.log"

# 状态文件
STATE_DIR="$LOG_DIR/watchdog_state"
RESTART_COUNT_FILE="$STATE_DIR/restart_count"
LAST_RESTART_FILE="$STATE_DIR/last_restart"
ALERT_SENT_FILE="$STATE_DIR/alert_sent"

# 确保目录存在
mkdir -p "$LOG_DIR" "$STATE_DIR"

# 日志函数
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$WATCHDOG_LOG"
}

log_alert() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ALERT: $1" | tee -a "$ALERT_LOG"
    log "ALERT: $1"
}

# 检查服务是否为系统服务
is_system_service() {
    systemctl list-unit-files | grep -q "^${SERVICE_NAME}.service"
}

# 检查进程PID文件
check_pid_file() {
    local pid_file="$PROJECT_ROOT/logs/pids/dev_supervisor.pid"

    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file" 2>/dev/null)
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            return 0  # 进程存在
        fi
    fi
    return 1  # 进程不存在
}

# 检查Web服务健康
check_web_health() {
    local web_port=${WEB_PORT:-8008}
    local timeout=5

    # 检查端口是否开放
    if ! nc -z localhost "$web_port" 2>/dev/null; then
        return 1
    fi

    # 检查HTTP健康端点
    if command -v curl >/dev/null 2>&1; then
        if curl -s --max-time "$timeout" "http://localhost:${web_port}/api/health" >/dev/null 2>&1; then
            return 0
        fi
    fi

    return 1
}

# 检查Redis连接
check_redis_health() {
    if command -v redis-cli >/dev/null 2>&1; then
        if redis-cli ping >/dev/null 2>&1; then
            return 0
        fi
    fi
    return 1
}

# 综合健康检查
health_check() {
    local issues=0

    if is_system_service; then
        # 系统服务模式检查
        if ! systemctl is-active --quiet "$SERVICE_NAME"; then
            log "系统服务 $SERVICE_NAME 未运行"
            ((issues++))
        fi
    else
        # 进程模式检查
        if ! check_pid_file; then
            log "主进程未运行"
            ((issues++))
        fi
    fi

    # Web服务检查
    if ! check_web_health; then
        log "Web服务健康检查失败"
        ((issues++))
    fi

    # Redis检查
    if ! check_redis_health; then
        log "Redis健康检查失败"
        ((issues++))
    fi

    return $issues
}

# 获取重启计数
get_restart_count() {
    if [ -f "$RESTART_COUNT_FILE" ]; then
        cat "$RESTART_COUNT_FILE"
    else
        echo "0"
    fi
}

# 设置重启计数
set_restart_count() {
    echo "$1" > "$RESTART_COUNT_FILE"
}

# 获取最后重启时间
get_last_restart() {
    if [ -f "$LAST_RESTART_FILE" ]; then
        cat "$LAST_RESTART_FILE"
    else
        echo "0"
    fi
}

# 设置最后重启时间
set_last_restart() {
    echo "$1" > "$LAST_RESTART_FILE"
}

# 检查是否在冷却期
is_in_cooldown() {
    local current_time=$(date +%s)
    local last_restart=$(get_last_restart)
    local elapsed=$((current_time - last_restart))

    if [ "$elapsed" -lt "$RESTART_COOLDOWN" ]; then
        return 0  # 在冷却期
    fi
    return 1  # 不在冷却期
}

# 重置重启计数（如果超出冷却期）
reset_restart_count_if_needed() {
    if ! is_in_cooldown; then
        set_restart_count 0
        rm -f "$ALERT_SENT_FILE"
    fi
}

# 重启服务
restart_service() {
    local current_time=$(date +%s)
    local restart_count=$(get_restart_count)

    # 检查重启次数限制
    if [ "$restart_count" -ge "$MAX_RESTART_ATTEMPTS" ]; then
        if [ ! -f "$ALERT_SENT_FILE" ]; then
            log_alert "服务 $SERVICE_NAME 达到最大重启次数($MAX_RESTART_ATTEMPTS)，需要人工介入"
            send_alert "服务重启次数过多"
            touch "$ALERT_SENT_FILE"
        fi
        return 1
    fi

    # 执行重启
    log "尝试重启服务 $SERVICE_NAME (第 $((restart_count + 1)) 次)"

    if is_system_service; then
        # 系统服务重启
        if sudo systemctl restart "$SERVICE_NAME"; then
            log "系统服务重启成功"
            sleep 10  # 等待服务启动

            # 验证重启是否成功
            if systemctl is-active --quiet "$SERVICE_NAME"; then
                log "服务重启成功并正在运行"
                set_restart_count $((restart_count + 1))
                set_last_restart "$current_time"
                return 0
            else
                log "服务重启失败，状态检查未通过"
            fi
        else
            log "系统服务重启命令失败"
        fi
    else
        # 进程模式重启
        log "停止现有进程..."
        if [ -f "$PROJECT_ROOT/stop.sh" ]; then
            cd "$PROJECT_ROOT"
            ./stop.sh --quiet || true
        fi

        sleep 3

        log "启动新进程..."
        if [ -f "$PROJECT_ROOT/start.sh" ]; then
            cd "$PROJECT_ROOT"
            ./start.sh --daemon --quick > /dev/null 2>&1 &
            sleep 10  # 等待启动

            # 验证启动是否成功
            if check_pid_file && check_web_health; then
                log "进程重启成功"
                set_restart_count $((restart_count + 1))
                set_last_restart "$current_time"
                return 0
            else
                log "进程重启失败，健康检查未通过"
            fi
        fi
    fi

    # 重启失败
    set_restart_count $((restart_count + 1))
    set_last_restart "$current_time"
    return 1
}

# 发送告警（可以扩展为邮件、微信等）
send_alert() {
    local message="$1"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')

    # 记录到告警日志
    log_alert "$message"

    # TODO: 这里可以添加邮件、钉钉、企业微信等通知方式
    # 示例：发送邮件
    # if command -v mail >/dev/null 2>&1; then
    #     echo "[$timestamp] Telegram Channel Bot Alert: $message" | mail -s "Bot Service Alert" admin@example.com
    # fi

    # 示例：调用webhook
    # if command -v curl >/dev/null 2>&1; then
    #     curl -X POST "https://hooks.slack.com/your/webhook/url" \
    #         -H "Content-Type: application/json" \
    #         -d "{\"text\":\"[$timestamp] Telegram Channel Bot Alert: $message\"}"
    # fi
}

# 主监控循环
main_loop() {
    log "看门狗启动，监控间隔: ${CHECK_INTERVAL}秒"

    while true; do
        # 重置重启计数（如果需要）
        reset_restart_count_if_needed

        # 健康检查
        if ! health_check; then
            log "健康检查失败，发送告警（不自动重启）"

            # 只发送告警，不自动重启（重启由systemd负责）
            if [ ! -f "$ALERT_SENT_FILE" ]; then
                log_alert "服务 $SERVICE_NAME 健康检查失败，需要人工检查"
                send_alert "服务健康检查失败"
                touch "$ALERT_SENT_FILE"
            fi
        else
            # 健康检查通过，清理过期的告警状态
            if [ -f "$ALERT_SENT_FILE" ] && ! is_in_cooldown; then
                rm -f "$ALERT_SENT_FILE"
                log "服务恢复正常，清除告警状态"
            fi
        fi

        sleep "$CHECK_INTERVAL"
    done
}

# 显示帮助
show_help() {
    cat << EOF
Telegram Channel Bot 看门狗脚本

用法: $0 [选项]

选项:
    --interval N        检查间隔秒数 (默认: $CHECK_INTERVAL)
    --max-restarts N    最大重启次数 (默认: $MAX_RESTART_ATTEMPTS)
    --cooldown N        重启冷却时间秒数 (默认: $RESTART_COOLDOWN)
    --once              只执行一次检查（不循环）
    --status            显示当前状态
    --reset             重置重启计数和告警状态
    --help, -h          显示帮助信息

环境变量:
    CHECK_INTERVAL      检查间隔
    MAX_RESTART_ATTEMPTS 最大重启次数
    RESTART_COOLDOWN    重启冷却时间
    WEB_PORT           Web服务端口

示例:
    $0                  # 启动看门狗（默认设置）
    $0 --interval 60    # 60秒检查间隔
    $0 --once           # 执行一次检查
    $0 --status         # 显示状态
EOF
}

# 显示状态
show_status() {
    echo "=== 看门狗状态 ==="
    echo "检查间隔: ${CHECK_INTERVAL}秒"
    echo "最大重启次数: $MAX_RESTART_ATTEMPTS"
    echo "重启冷却时间: $RESTART_COOLDOWN 秒"
    echo "当前重启次数: $(get_restart_count)"
    echo "最后重启时间: $(date -d @$(get_last_restart) 2>/dev/null || echo '从未重启')"
    echo "是否在冷却期: $(is_in_cooldown && echo '是' || echo '否')"
    echo "告警状态: $([ -f "$ALERT_SENT_FILE" ] && echo '已发送' || echo '未发送')"
    echo ""

    echo "=== 服务健康状态 ==="
    if is_system_service; then
        echo "模式: 系统服务"
        echo "服务状态: $(systemctl is-active "$SERVICE_NAME" 2>/dev/null || echo 'unknown')"
    else
        echo "模式: 进程"
        echo "进程状态: $(check_pid_file && echo 'running' || echo 'stopped')"
    fi

    echo "Web健康: $(check_web_health && echo 'OK' || echo 'Failed')"
    echo "Redis健康: $(check_redis_health && echo 'OK' || echo 'Failed')"
}

# 重置状态
reset_status() {
    rm -f "$RESTART_COUNT_FILE" "$LAST_RESTART_FILE" "$ALERT_SENT_FILE"
    echo "状态已重置"
}

# 解析参数
RUN_ONCE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --interval)
            CHECK_INTERVAL="$2"
            shift 2
            ;;
        --max-restarts)
            MAX_RESTART_ATTEMPTS="$2"
            shift 2
            ;;
        --cooldown)
            RESTART_COOLDOWN="$2"
            shift 2
            ;;
        --once)
            RUN_ONCE=true
            shift
            ;;
        --status)
            show_status
            exit 0
            ;;
        --reset)
            reset_status
            exit 0
            ;;
        --help|-h)
            show_help
            exit 0
            ;;
        *)
            echo "未知参数: $1"
            show_help
            exit 1
            ;;
    esac
done

# 主逻辑
if [ "$RUN_ONCE" = true ]; then
    log "执行单次健康检查"
    if health_check; then
        log "健康检查通过"
        exit 0
    else
        log "健康检查失败"
        exit 1
    fi
else
    # 检查是否已在运行
    if pgrep -f "$(basename $0)" | grep -v "$$" > /dev/null; then
        echo "看门狗已在运行"
        exit 1
    fi

    # 启动主循环
    main_loop
fi