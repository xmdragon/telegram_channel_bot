#!/bin/bash

# Nginx配置部署脚本
# 自动替换路径并部署nginx配置

set -e

# 配置参数
PROJECT_ROOT=$(cd "$(dirname "$0")/.." && pwd)
NGINX_CONF_SOURCE="$PROJECT_ROOT/conf/nginx.conf"
NGINX_CONF_TARGET="/opt/homebrew/etc/nginx/servers/telegram_bot.conf"

echo "🔧 Nginx配置部署脚本"
echo "项目根目录: $PROJECT_ROOT"

# 检查源配置文件是否存在
if [ ! -f "$NGINX_CONF_SOURCE" ]; then
    echo "❌ 源配置文件不存在: $NGINX_CONF_SOURCE"
    exit 1
fi

# 检查nginx是否安装
if ! command -v nginx &> /dev/null; then
    echo "❌ Nginx未安装，请先安装: brew install nginx"
    exit 1
fi

# 创建临时文件，替换路径占位符
TEMP_CONF="/tmp/telegram_bot_nginx.conf"
sed "s|/Users/eric/workspace/telegram_channel_bot|$PROJECT_ROOT|g" "$NGINX_CONF_SOURCE" > "$TEMP_CONF"

echo "✅ 已生成临时配置文件: $TEMP_CONF"

# 备份现有配置（如果存在）
if [ -f "$NGINX_CONF_TARGET" ]; then
    BACKUP_FILE="${NGINX_CONF_TARGET}.backup.$(date +%Y%m%d_%H%M%S)"
    cp "$NGINX_CONF_TARGET" "$BACKUP_FILE"
    echo "📦 已备份现有配置: $BACKUP_FILE"
fi

# 部署新配置
cp "$TEMP_CONF" "$NGINX_CONF_TARGET"
echo "✅ 已部署配置文件: $NGINX_CONF_TARGET"

# 验证nginx配置
echo "🔍 验证nginx配置..."
if nginx -t; then
    echo "✅ Nginx配置验证通过"
    
    # 重新加载nginx配置
    echo "🔄 重新加载nginx配置..."
    if nginx -s reload; then
        echo "✅ Nginx配置已重新加载"
        echo "🌐 项目可通过 http://localhost:8080 访问"
    else
        echo "❌ Nginx重新加载失败"
        exit 1
    fi
else
    echo "❌ Nginx配置验证失败"
    exit 1
fi

# 清理临时文件
rm -f "$TEMP_CONF"

echo "🎉 Nginx配置部署完成！"