#!/bin/bash

# 跨平台服务管理工具
# 支持macOS (brew), Ubuntu/Debian (systemctl/service), WSL等环境

# 检测系统类型
detect_system() {
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo "macos"
    elif [[ -f /proc/version ]] && grep -qi microsoft /proc/version; then
        echo "wsl"
    elif [[ -f /etc/os-release ]]; then
        . /etc/os-release
        echo "${ID,,}"  # 转换为小写: ubuntu, debian, fedora等
    else
        echo "unknown"
    fi
}

# 检测服务管理器
detect_service_manager() {
    if command -v systemctl &> /dev/null; then
        echo "systemctl"
    elif command -v service &> /dev/null; then
        echo "service"
    elif command -v brew &> /dev/null; then
        echo "brew"
    else
        echo "none"
    fi
}

# 保存系统类型到变量
SYSTEM_TYPE=$(detect_system)
SERVICE_MANAGER=$(detect_service_manager)

# 输出系统信息（调试用）
debug_system_info() {
    echo "🖥️  系统类型: $SYSTEM_TYPE"
    echo "🔧 服务管理器: $SERVICE_MANAGER"
}

# ==================== Redis 服务管理 ====================

# 启动Redis
start_redis() {
    local verbose=${1:-false}
    
    case $SYSTEM_TYPE in
        macos)
            if command -v brew &> /dev/null; then
                if ! brew services list | grep -q "redis.*started"; then
                    [ "$verbose" = true ] && echo "📦 启动Redis (brew)..."
                    brew services start redis
                else
                    [ "$verbose" = true ] && echo "✅ Redis已在运行"
                fi
            else
                echo "❌ 未安装Homebrew，请先安装: /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
                return 1
            fi
            ;;
        ubuntu|debian|wsl)
            if ! pgrep -x redis-server > /dev/null; then
                [ "$verbose" = true ] && echo "📦 启动Redis (service)..."
                if [[ "$SERVICE_MANAGER" == "systemctl" ]] && [[ "$SYSTEM_TYPE" != "wsl" ]]; then
                    sudo systemctl start redis || sudo systemctl start redis-server
                else
                    sudo service redis-server start
                fi
            else
                [ "$verbose" = true ] && echo "✅ Redis已在运行"
            fi
            ;;
        *)
            echo "⚠️  不支持的系统: $SYSTEM_TYPE"
            echo "   请手动启动Redis服务"
            return 1
            ;;
    esac
}

# 停止Redis
stop_redis() {
    local verbose=${1:-false}
    
    case $SYSTEM_TYPE in
        macos)
            if brew services list | grep -q "redis.*started"; then
                [ "$verbose" = true ] && echo "🛑 停止Redis (brew)..."
                brew services stop redis
            else
                [ "$verbose" = true ] && echo "✅ Redis未在运行"
            fi
            ;;
        ubuntu|debian|wsl)
            if pgrep -x redis-server > /dev/null; then
                [ "$verbose" = true ] && echo "🛑 停止Redis (service)..."
                if [[ "$SERVICE_MANAGER" == "systemctl" ]] && [[ "$SYSTEM_TYPE" != "wsl" ]]; then
                    sudo systemctl stop redis || sudo systemctl stop redis-server
                else
                    sudo service redis-server stop
                fi
            else
                [ "$verbose" = true ] && echo "✅ Redis未在运行"
            fi
            ;;
        *)
            [ "$verbose" = true ] && echo "⚠️  不支持的系统: $SYSTEM_TYPE"
            ;;
    esac
}

# 重启Redis
restart_redis() {
    local verbose=${1:-false}
    
    case $SYSTEM_TYPE in
        macos)
            [ "$verbose" = true ] && echo "🔄 重启Redis (brew)..."
            brew services restart redis
            ;;
        ubuntu|debian|wsl)
            [ "$verbose" = true ] && echo "🔄 重启Redis (service)..."
            if [[ "$SERVICE_MANAGER" == "systemctl" ]] && [[ "$SYSTEM_TYPE" != "wsl" ]]; then
                sudo systemctl restart redis || sudo systemctl restart redis-server
            else
                sudo service redis-server restart
            fi
            ;;
        *)
            echo "⚠️  不支持的系统: $SYSTEM_TYPE"
            return 1
            ;;
    esac
}

# 检查Redis状态
check_redis_status() {
    if redis-cli ping &>/dev/null; then
        return 0
    else
        return 1
    fi
}

# 获取Redis服务状态
get_redis_status() {
    case $SYSTEM_TYPE in
        macos)
            brew services list | grep redis || echo "Redis: 未安装"
            ;;
        ubuntu|debian|wsl)
            if [[ "$SERVICE_MANAGER" == "systemctl" ]] && [[ "$SYSTEM_TYPE" != "wsl" ]]; then
                systemctl status redis --no-pager 2>/dev/null || systemctl status redis-server --no-pager 2>/dev/null || echo "Redis: 未安装"
            else
                service redis-server status 2>/dev/null || echo "Redis: 未安装"
            fi
            ;;
        *)
            echo "Redis: 不支持的系统"
            ;;
    esac
}

# ==================== Nginx 服务管理 ====================

# 启动Nginx
start_nginx() {
    local verbose=${1:-false}
    
    case $SYSTEM_TYPE in
        macos)
            if command -v brew &> /dev/null; then
                if ! brew services list | grep -q "nginx.*started"; then
                    [ "$verbose" = true ] && echo "🌐 启动Nginx (brew)..."
                    brew services start nginx
                else
                    [ "$verbose" = true ] && echo "✅ Nginx已在运行"
                fi
            else
                echo "❌ 未安装Homebrew"
                return 1
            fi
            ;;
        ubuntu|debian|wsl)
            if ! pgrep -x nginx > /dev/null; then
                [ "$verbose" = true ] && echo "🌐 启动Nginx (service)..."
                if [[ "$SERVICE_MANAGER" == "systemctl" ]] && [[ "$SYSTEM_TYPE" != "wsl" ]]; then
                    sudo systemctl start nginx
                else
                    sudo service nginx start
                fi
            else
                [ "$verbose" = true ] && echo "✅ Nginx已在运行"
            fi
            ;;
        *)
            echo "⚠️  不支持的系统: $SYSTEM_TYPE"
            echo "   请手动启动Nginx服务"
            return 1
            ;;
    esac
}

# 停止Nginx
stop_nginx() {
    local verbose=${1:-false}
    
    case $SYSTEM_TYPE in
        macos)
            if brew services list | grep -q "nginx.*started"; then
                [ "$verbose" = true ] && echo "🛑 停止Nginx (brew)..."
                brew services stop nginx
            else
                [ "$verbose" = true ] && echo "✅ Nginx未在运行"
            fi
            ;;
        ubuntu|debian|wsl)
            if pgrep -x nginx > /dev/null; then
                [ "$verbose" = true ] && echo "🛑 停止Nginx (service)..."
                if [[ "$SERVICE_MANAGER" == "systemctl" ]] && [[ "$SYSTEM_TYPE" != "wsl" ]]; then
                    sudo systemctl stop nginx
                else
                    sudo service nginx stop
                fi
            else
                [ "$verbose" = true ] && echo "✅ Nginx未在运行"
            fi
            ;;
        *)
            [ "$verbose" = true ] && echo "⚠️  不支持的系统: $SYSTEM_TYPE"
            ;;
    esac
}

# 重启Nginx
restart_nginx() {
    local verbose=${1:-false}
    
    case $SYSTEM_TYPE in
        macos)
            [ "$verbose" = true ] && echo "🔄 重启Nginx (brew)..."
            brew services restart nginx
            ;;
        ubuntu|debian|wsl)
            [ "$verbose" = true ] && echo "🔄 重启Nginx (service)..."
            if [[ "$SERVICE_MANAGER" == "systemctl" ]] && [[ "$SYSTEM_TYPE" != "wsl" ]]; then
                sudo systemctl restart nginx
            else
                sudo service nginx restart
            fi
            ;;
        *)
            echo "⚠️  不支持的系统: $SYSTEM_TYPE"
            return 1
            ;;
    esac
}

# 检查Nginx状态 - 带重试机制，使用动态端口
check_nginx_status() {
    local max_retries=3
    local retry_delay=1
    local nginx_port=${NGINX_PORT:-8080}
    local test_url="http://localhost:${nginx_port}/static/favicon.svg"
    
    for ((i=1; i<=max_retries; i++)); do
        if curl -s --connect-timeout 2 --max-time 5 "$test_url" &>/dev/null; then
            return 0
        fi
        
        if [ $i -lt $max_retries ]; then
            sleep $retry_delay
        fi
    done
    
    # 最后一次检查失败，输出调试信息
    echo "🔍 Nginx检查调试信息："
    echo "   - 尝试次数: $max_retries"
    echo "   - 检查URL: $test_url"
    echo "   - Nginx端口: $nginx_port"
    
    # 检查Nginx服务状态
    case $SYSTEM_TYPE in
        macos)
            echo "   - Nginx服务状态: $(brew services list | grep nginx || echo 'Unknown')"
            ;;
    esac
    
    return 1
}

# 获取Nginx服务状态
get_nginx_status() {
    case $SYSTEM_TYPE in
        macos)
            brew services list | grep nginx || echo "Nginx: 未安装"
            ;;
        ubuntu|debian|wsl)
            if [[ "$SERVICE_MANAGER" == "systemctl" ]] && [[ "$SYSTEM_TYPE" != "wsl" ]]; then
                systemctl status nginx --no-pager 2>/dev/null || echo "Nginx: 未安装"
            else
                service nginx status 2>/dev/null || echo "Nginx: 未安装"
            fi
            ;;
        *)
            echo "Nginx: 不支持的系统"
            ;;
    esac
}

# ==================== 通用服务管理 ====================

# 启动所有服务
start_all_services() {
    local verbose=${1:-false}
    
    [ "$verbose" = true ] && echo "🚀 启动所有服务..."
    start_redis "$verbose"
    start_nginx "$verbose"
    
    # 等待服务完全启动
    [ "$verbose" = true ] && echo "⏳ 等待服务启动完成..."
    sleep 2
    
    # 验证服务状态
    [ "$verbose" = true ] && echo "🔧 验证服务状态..."
    
    if ! check_redis_status; then
        echo "❌ Redis连接失败"
        return 1
    fi
    [ "$verbose" = true ] && echo "✅ Redis连接正常"
    
    if ! check_nginx_status; then
        echo "❌ Nginx静态文件服务异常"
        return 1
    fi
    [ "$verbose" = true ] && echo "✅ Nginx服务正常"
    
    return 0
}

# 停止所有服务（可选）
stop_all_services() {
    local verbose=${1:-false}
    local keep_services=${2:-true}  # 默认保持服务运行
    
    if [ "$keep_services" = false ]; then
        [ "$verbose" = true ] && echo "🛑 停止所有服务..."
        stop_redis "$verbose"
        stop_nginx "$verbose"
    else
        [ "$verbose" = true ] && echo "💡 保持Redis和Nginx服务运行（推荐）"
        case $SYSTEM_TYPE in
            macos)
                [ "$verbose" = true ] && echo "   如需停止: brew services stop redis nginx"
                ;;
            ubuntu|debian|wsl)
                [ "$verbose" = true ] && echo "   如需停止: sudo service redis-server stop && sudo service nginx stop"
                ;;
        esac
    fi
}

# 显示服务状态
show_services_status() {
    echo "📊 服务状态："
    echo "   系统类型: $SYSTEM_TYPE"
    echo "   服务管理器: $SERVICE_MANAGER"
    echo ""
    echo "Redis状态:"
    get_redis_status
    echo ""
    echo "Nginx状态:"
    get_nginx_status
}

# 安装依赖提示
show_install_instructions() {
    echo "📦 安装说明："
    case $SYSTEM_TYPE in
        macos)
            echo "   安装Homebrew: /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
            echo "   安装Redis: brew install redis"
            echo "   安装Nginx: brew install nginx"
            ;;
        ubuntu|debian|wsl)
            echo "   更新包列表: sudo apt update"
            echo "   安装Redis: sudo apt install redis-server"
            echo "   安装Nginx: sudo apt install nginx"
            ;;
        *)
            echo "   请查阅系统文档安装Redis和Nginx"
            ;;
    esac
}

# 导出所有函数供其他脚本使用
export -f detect_system
export -f detect_service_manager
export -f start_redis
export -f stop_redis
export -f restart_redis
export -f check_redis_status
export -f start_nginx
export -f stop_nginx
export -f restart_nginx
export -f check_nginx_status
export -f start_all_services
export -f stop_all_services
export -f show_services_status
export -f show_install_instructions

# 如果直接运行此脚本，显示帮助信息
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    echo "🔧 跨平台服务管理工具"
    echo ""
    debug_system_info
    echo ""
    show_services_status
    echo ""
    show_install_instructions
fi