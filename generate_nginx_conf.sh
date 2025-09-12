#!/bin/bash

# 生成Nginx配置文件脚本
# 根据环境变量生成实际的Nginx配置

# 加载环境配置
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# 使用配置的端口，提供默认值
WEB_PORT=${WEB_PORT:-8008}
NGINX_PORT=${NGINX_PORT:-8080}
PROJECT_PATH=$(pwd)

# 输出文件
OUTPUT_FILE="nginx_telegram_bot.conf"

echo "📝 生成Nginx配置文件..."
echo "   - Web服务端口: $WEB_PORT"
echo "   - Nginx端口: $NGINX_PORT"
echo "   - 项目路径: $PROJECT_PATH"

cat > $OUTPUT_FILE << EOF
# Telegram消息审核系统 - Nginx配置
# 自动生成的配置文件，请勿手动修改
# 生成时间: $(date)

server {
    listen $NGINX_PORT;
    server_name localhost;
    
    # 性能优化配置
    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;
    types_hash_max_size 2048;
    
    # Gzip压缩
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_types
        text/plain
        text/css
        text/xml
        text/javascript
        application/javascript
        application/xml+rss
        application/json;
    
    # 静态文件服务
    location /static/ {
        alias $PROJECT_PATH/static/;
        
        # 强缓存策略
        expires 1d;
        add_header Cache-Control "public, immutable";
        add_header X-Served-By "nginx-static";
        
        # 安全头部
        add_header X-Frame-Options "SAMEORIGIN" always;
        add_header X-Content-Type-Options "nosniff" always;
        
        # 404处理
        try_files \$uri \$uri/ =404;
    }
    
    # 临时媒体文件
    location /temp_media/ {
        alias $PROJECT_PATH/temp_media/;
        expires 1h;
        add_header Cache-Control "public";
        add_header X-Served-By "nginx-temp";
    }
    
    # 训练数据媒体文件
    location /media/ {
        alias $PROJECT_PATH/data/training/ad/;
        expires 1d;
        add_header Cache-Control "public";
        add_header X-Served-By "nginx-media";
    }
    
    # WebSocket代理
    location /ws {
        proxy_pass http://localhost:$WEB_PORT;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        
        # WebSocket超时配置
        proxy_read_timeout 86400;
        proxy_send_timeout 86400;
        
        add_header X-Served-By "nginx-websocket";
    }
    
    # 根路径重定向到主页
    location = / {
        return 301 http://\$host:$NGINX_PORT/static/index.html;
    }
    
    # 便捷路径重定向
    location = /admin {
        return 301 http://\$host:$NGINX_PORT/static/login.html;
    }
    
    location = /config {
        return 301 http://\$host:$NGINX_PORT/static/config.html;
    }
    
    location = /auth {
        return 301 http://\$host:$NGINX_PORT/static/telegram-auth.html;
    }
    
    # API反向代理到FastAPI
    location / {
        proxy_pass http://localhost:$WEB_PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        
        # 连接优化
        proxy_connect_timeout 30s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
        proxy_buffering on;
        proxy_buffer_size 4k;
        proxy_buffers 8 4k;
        
        add_header X-Served-By "nginx-api";
    }
    
    # 隐藏nginx版本
    server_tokens off;
    
    # 错误页面
    error_page 404 /404.html;
    error_page 500 502 503 504 /50x.html;
    
    location = /50x.html {
        root /usr/share/nginx/html;
    }
}
EOF

echo "✅ Nginx配置文件已生成: $OUTPUT_FILE"
echo ""
echo "部署步骤："
echo "1. 复制配置文件到Nginx目录："
echo "   sudo cp $OUTPUT_FILE /etc/nginx/sites-available/telegram_bot"
echo ""
echo "2. 创建符号链接："
echo "   sudo ln -sf /etc/nginx/sites-available/telegram_bot /etc/nginx/sites-enabled/"
echo ""
echo "3. 测试配置："
echo "   sudo nginx -t"
echo ""
echo "4. 重启Nginx："
echo "   sudo systemctl restart nginx"