# Nginx 配置文件

## 📁 文件说明

- `nginx.conf` - Nginx配置模板，包含完整的静态文件服务和反向代理配置
- `deploy_nginx.sh` - 自动部署脚本，自动替换路径并部署到系统目录

## 🚀 快速部署

### 自动部署（推荐）
```bash
# 在项目根目录执行
./conf/deploy_nginx.sh
```

### 手动部署
```bash
# 1. 复制配置文件
cp conf/nginx.conf /opt/homebrew/etc/nginx/servers/telegram_bot.conf

# 2. 修改配置文件中的项目路径
# 将所有 /Users/eric/workspace/telegram_channel_bot 替换为实际项目路径

# 3. 验证配置
nginx -t

# 4. 重新加载配置
nginx -s reload
```

## 📋 配置功能

### 静态文件服务 (端口 8080)
- `/static/` - 前端页面和资源文件
- `/temp_media/` - 临时媒体文件
- `/media/` - 训练数据媒体文件

### 反向代理
- `/` - API请求代理到本地FastAPI服务 (端口 8000)
- `/ws` - WebSocket连接代理

### 便捷重定向
- `/` → `/static/index.html`
- `/admin` → `/static/login.html`
- `/config` → `/static/config.html`
- `/auth` → `/static/telegram-auth.html`

## 🔧 路径配置

配置文件中需要根据实际部署环境修改的路径（已用🔧标记）：
- 静态文件目录: `{project_path}/static/`
- 临时媒体目录: `{project_path}/temp_media/`
- 训练数据目录: `{project_path}/data/training/ad/`

## 📊 性能优化

- **Gzip压缩** - 减少传输大小
- **缓存策略** - 静态文件1天，临时文件1小时
- **连接优化** - Keep-alive和缓冲区优化
- **安全头部** - X-Frame-Options, X-Content-Type-Options

## 🌐 访问地址

部署完成后可通过以下地址访问：
- 主页: http://localhost:8080
- 管理员登录: http://localhost:8080/admin
- 配置页面: http://localhost:8080/config
- Telegram认证: http://localhost:8080/auth