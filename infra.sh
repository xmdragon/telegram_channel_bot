#!/bin/bash

# 基础设施服务管理脚本
# 管理Redis和Nginx服务，这些服务通常不需要频繁重启

set -e

# 加载环境配置
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# 端口配置
NGINX_PORT=${NGINX_PORT:-8080}
REDIS_PORT=${REDIS_PORT:-6379}

# 域名配置（从环境变量读取）
DOMAIN_NAME=${DOMAIN_NAME:-""}
ENABLE_SSL=${ENABLE_SSL:-false}
BASE_URL=${BASE_URL:-""}

# 显示帮助信息
show_help() {
    echo "🏗️  基础设施服务管理器"
    echo ""
    echo "用法: $0 [COMMAND] [OPTIONS]"
    echo ""
    echo "命令:"
    echo "  start      启动Redis和Nginx服务"
    echo "  stop       停止Redis和Nginx服务"
    echo "  restart    重启Redis和Nginx服务"
    echo "  status     显示服务状态"
    echo "  check      快速检查服务是否正常运行"
    echo "  help       显示此帮助信息"
    echo ""
    echo "选项:"
    echo "  --verbose, -v    显示详细信息"
    echo "  --quiet, -q      静默模式（减少输出）"
    echo "  --redis-only     仅操作Redis服务"
    echo "  --nginx-only     仅操作Nginx服务"
    echo ""
    echo "服务说明:"
    echo "  🗄️  Redis (端口 $REDIS_PORT)"
    echo "      • 消息数据缓存"
    echo "      • 会话管理"
    echo "      • 分布式锁"
    echo ""
    echo "  🌐 Nginx (端口 $NGINX_PORT)"
    echo "      • 静态文件服务"
    echo "      • API反向代理"
    echo "      • WebSocket代理"
    echo ""
    echo "示例:"
    echo "  $0 start           # 启动所有基础服务"
    echo "  $0 stop            # 停止所有基础服务"
    echo "  $0 status          # 查看服务状态"
    echo "  $0 check           # 快速检查服务"
    echo "  $0 restart --redis-only  # 仅重启Redis"
    echo ""
    echo "提示:"
    echo "  • 基础服务通常只需启动一次"
    echo "  • 开发时使用 ./dev.sh 管理应用服务"
    echo "  • 基础服务可以持续运行，供多个项目使用"
    echo ""
}

# 解析参数
VERBOSE=false
QUIET=false
REDIS_ONLY=false
NGINX_ONLY=false

# 命令
COMMAND=""

# 解析命令和选项
while [[ $# -gt 0 ]]; do
    case $1 in
        start|stop|restart|status|check)
            COMMAND=$1
            shift
            ;;
        help|--help|-h)
            show_help
            exit 0
            ;;
        --verbose|-v)
            VERBOSE=true
            shift
            ;;
        --quiet|-q)
            QUIET=true
            shift
            ;;
        --redis-only)
            REDIS_ONLY=true
            shift
            ;;
        --nginx-only)
            NGINX_ONLY=true
            shift
            ;;
        *)
            echo "❌ 未知参数: $1"
            echo "使用 '$0 help' 查看帮助信息"
            exit 1
            ;;
    esac
done

# 如果没有命令，显示帮助
if [ -z "$COMMAND" ]; then
    show_help
    exit 0
fi

# 加载服务管理工具
if [[ -f "tools/utils/service_manager.sh" ]]; then
    source tools/utils/service_manager.sh
    SERVICE_MANAGER_LOADED=true
    [ "$VERBOSE" = true ] && echo "✅ 已加载服务管理工具"
else
    echo "❌ 服务管理工具未找到: tools/utils/service_manager.sh"
    exit 1
fi

# 输出函数
log_info() {
    [ "$QUIET" = false ] && echo "$1"
}

log_verbose() {
    [ "$VERBOSE" = true ] && echo "$1"
}

# 服务操作函数
operate_services() {
    local operation=$1

    if [ "$REDIS_ONLY" = true ] && [ "$NGINX_ONLY" = true ]; then
        echo "❌ 不能同时指定 --redis-only 和 --nginx-only"
        exit 1
    fi

    case $operation in
        start)
            log_info "🚀 启动基础设施服务..."

            if [ "$NGINX_ONLY" = false ]; then
                log_info "📦 启动Redis服务..."
                start_redis "$VERBOSE"
                sleep 1
                if check_redis_status; then
                    log_info "✅ Redis服务已启动 (端口: $REDIS_PORT)"
                else
                    echo "❌ Redis启动失败"
                    exit 1
                fi
            fi

            if [ "$REDIS_ONLY" = false ]; then
                log_info "🌐 启动Nginx服务..."
                start_nginx "$VERBOSE"
                sleep 2
                if check_nginx_status; then
                    log_info "✅ Nginx服务已启动 (端口: $NGINX_PORT)"
                else
                    echo "❌ Nginx启动失败"
                    exit 1
                fi
            fi

            log_info "✅ 基础设施服务启动完成"
            ;;

        stop)
            log_info "🛑 停止基础设施服务..."

            if [ "$NGINX_ONLY" = false ]; then
                log_info "🛑 停止Redis服务..."
                stop_redis "$VERBOSE"
                log_info "✅ Redis服务已停止"
            fi

            if [ "$REDIS_ONLY" = false ]; then
                log_info "🛑 停止Nginx服务..."
                stop_nginx "$VERBOSE"
                log_info "✅ Nginx服务已停止"
            fi

            log_info "✅ 基础设施服务停止完成"
            ;;

        restart)
            log_info "🔄 重启基础设施服务..."

            if [ "$NGINX_ONLY" = false ]; then
                log_info "🔄 重启Redis服务..."
                restart_redis "$VERBOSE"
                sleep 1
                if check_redis_status; then
                    log_info "✅ Redis服务已重启"
                else
                    echo "❌ Redis重启失败"
                    exit 1
                fi
            fi

            if [ "$REDIS_ONLY" = false ]; then
                log_info "🔄 重启Nginx服务..."
                restart_nginx "$VERBOSE"
                sleep 2
                if check_nginx_status; then
                    log_info "✅ Nginx服务已重启"
                else
                    echo "❌ Nginx重启失败"
                    exit 1
                fi
            fi

            log_info "✅ 基础设施服务重启完成"
            ;;
    esac
}

# 显示服务状态
show_status() {
    echo "📊 基础设施服务状态"
    echo "===================="
    echo ""

    # 系统信息
    echo "🖥️  系统信息:"
    echo "   • 系统类型: $(detect_system)"
    echo "   • 服务管理器: $(detect_service_manager)"
    echo ""

    # Redis状态
    echo "🗄️  Redis服务 (端口: $REDIS_PORT):"
    if check_redis_status; then
        echo "   ✅ 运行中"
        if [ "$VERBOSE" = true ]; then
            echo "   详细状态:"
            get_redis_status | sed 's/^/      /'
        fi
    else
        echo "   ❌ 未运行"
    fi
    echo ""

    # Nginx状态
    echo "🌐 Nginx服务 (端口: $NGINX_PORT):"
    if check_nginx_status; then
        echo "   ✅ 运行中"

        # 根据配置显示正确的访问地址
        if [ -n "$BASE_URL" ]; then
            echo "   • Web界面: $BASE_URL"
        elif [ -n "$DOMAIN_NAME" ]; then
            if [ "$ENABLE_SSL" = "true" ]; then
                echo "   • Web界面: https://$DOMAIN_NAME"
            else
                if [ "$NGINX_PORT" = "80" ]; then
                    echo "   • Web界面: http://$DOMAIN_NAME"
                else
                    echo "   • Web界面: http://$DOMAIN_NAME:$NGINX_PORT"
                fi
            fi
        else
            echo "   • Web界面: http://localhost:$NGINX_PORT"
        fi

        if [ "$VERBOSE" = true ]; then
            echo "   详细状态:"
            get_nginx_status | sed 's/^/      /'
        fi
    else
        echo "   ❌ 未运行"
    fi
    echo ""

    # 连接测试
    if [ "$VERBOSE" = true ]; then
        echo "🔧 连接测试:"

        # Redis连接测试
        echo -n "   • Redis连接: "
        REDIS_HOST=${REDIS_HOST:-localhost}
        REDIS_PASSWORD=${REDIS_PASSWORD:-}

        if [ -n "$REDIS_PASSWORD" ]; then
            # 有密码的Redis
            if redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" -a "$REDIS_PASSWORD" ping >/dev/null 2>&1; then
                echo "✅ 正常 ($REDIS_HOST:$REDIS_PORT)"
            else
                echo "❌ 失败 ($REDIS_HOST:$REDIS_PORT)"
            fi
        else
            # 无密码的Redis
            if redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" ping >/dev/null 2>&1; then
                echo "✅ 正常 ($REDIS_HOST:$REDIS_PORT)"
            else
                echo "❌ 失败 ($REDIS_HOST:$REDIS_PORT)"
            fi
        fi

        # Nginx连接测试
        echo -n "   • Nginx静态文件: "
        # 使用localhost进行本地连接测试（避免DNS问题）
        if curl -s http://localhost:$NGINX_PORT/static/favicon.svg >/dev/null 2>&1; then
            echo "✅ 正常"
        else
            echo "❌ 失败"
        fi
    fi
}

# 快速检查服务
quick_check() {
    local all_good=true

    # 检查Redis - 功能优先
    if check_redis_status; then
        [ "$QUIET" = false ] && echo "✅ Redis: 运行中"
    else
        [ "$QUIET" = false ] && echo "❌ Redis: 未运行"
        all_good=false
    fi

    # 检查Nginx - 快速检测
    if check_nginx_status; then
        [ "$QUIET" = false ] && echo "✅ Nginx: 运行中"
    else
        [ "$QUIET" = false ] && echo "❌ Nginx: 未运行"
        all_good=false
    fi

    if [ "$all_good" = true ]; then
        [ "$QUIET" = false ] && echo "✅ 所有基础服务正常"
        exit 0
    else
        [ "$QUIET" = false ] && echo "⚠️ 部分服务未运行，使用 './infra.sh start' 启动"
        exit 1
    fi
}

# 执行命令
case $COMMAND in
    start)
        operate_services start
        ;;
    stop)
        operate_services stop
        ;;
    restart)
        operate_services restart
        ;;
    status)
        show_status
        ;;
    check)
        quick_check
        ;;
    *)
        echo "❌ 未知命令: $COMMAND"
        show_help
        exit 1
        ;;
esac