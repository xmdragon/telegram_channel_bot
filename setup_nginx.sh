#!/bin/bash

echo "配置Nginx站点..."

# 复制配置文件
sudo cp nginx_telegram_bot.conf /etc/nginx/sites-available/telegram_bot

# 创建符号链接
sudo ln -sf /etc/nginx/sites-available/telegram_bot /etc/nginx/sites-enabled/

# 删除默认站点（如果存在）
sudo rm -f /etc/nginx/sites-enabled/default

# 测试配置
echo "测试Nginx配置..."
sudo nginx -t

# 重启Nginx
echo "重启Nginx服务..."
sudo systemctl restart nginx

echo "Nginx配置完成！"
echo "访问地址：http://localhost:8080"