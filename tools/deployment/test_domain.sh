#!/bin/bash

# 测试域名绑定功能的脚本
# Usage: ./test_domain.sh

echo "==================================="
echo "测试域名绑定功能"
echo "==================================="
echo ""

# 显示帮助信息
echo "使用示例："
echo ""
echo "1. 仅绑定域名（不配置SSL）："
echo "   ./ubuntu_deploy_check.sh --domain example.com"
echo ""
echo "2. 绑定域名并配置SSL证书："
echo "   ./ubuntu_deploy_check.sh --domain example.com --ssl"
echo ""
echo "3. 绑定域名、配置SSL并提供邮箱："
echo "   ./ubuntu_deploy_check.sh --domain example.com --ssl --email admin@example.com"
echo ""
echo "4. 只检查不执行（dry run）："
echo "   ./ubuntu_deploy_check.sh --domain example.com --check-only"
echo ""

echo "==================================="
echo "注意事项："
echo "==================================="
echo "1. 域名必须已经解析到服务器IP"
echo "2. 需要开放80和443端口（用于SSL验证）"
echo "3. SSL证书会自动续期（每12小时检查）"
echo "4. 配置后访问: https://your-domain.com"
echo ""

# 检查当前Nginx配置
echo "==================================="
echo "当前Nginx配置："
echo "==================================="
if [ -f "/etc/nginx/sites-enabled/telegram-channel-bot" ]; then
    echo "站点配置已存在"
    grep "server_name" /etc/nginx/sites-enabled/telegram-channel-bot 2>/dev/null || echo "未找到server_name配置"
else
    echo "站点配置不存在"
fi
echo ""

# 检查SSL证书
echo "==================================="
echo "SSL证书状态："
echo "==================================="
if command -v certbot &> /dev/null; then
    sudo certbot certificates 2>/dev/null || echo "暂无证书"
else
    echo "Certbot未安装"
fi