# Ubuntu 24.04 生产环境部署指南

## 🚀 快速部署

### 1. 系统环境准备

```bash
# 下载并运行自动安装脚本
wget https://raw.githubusercontent.com/your-repo/telegram_channel_bot/main/install_ubuntu.sh
chmod +x install_ubuntu.sh

# 默认安装Python 3.12（Ubuntu 24.04自带）
./install_ubuntu.sh

# 或指定其他Python版本
PYTHON_VERSION=3.11 ./install_ubuntu.sh   # Python 3.11（推荐性能）
PYTHON_VERSION=3.10 ./install_ubuntu.sh   # Python 3.10（稳定）
```

安装完成后**重新登录**以使Docker组权限生效。

### 2. 项目部署

```bash
# 切换到项目目录
cd /opt/telegram-bot

# 克隆项目代码
git clone https://github.com/your-repo/telegram_channel_bot.git .

# 配置环境变量
cp .env.production .env
nano .env  # 编辑配置文件

# 一键部署
./deploy.sh
```

## 📋 详细部署步骤

### 1. 环境要求

- **操作系统**: Ubuntu 24.04 LTS (推荐) / 22.04 / 20.04
- **内存**: 最低2GB，推荐4GB+
- **存储**: 最低10GB可用空间
- **网络**: 能够访问Telegram API

### 2. 系统依赖安装

自动安装脚本会安装以下组件：

- **Python 3.11**: 应用运行环境
- **Docker & Docker Compose**: 容器化部署
- **Redis**: 数据缓存和消息队列
- **Nginx**: 反向代理和静态文件服务
- **系统工具**: Git, curl, 监控工具等

```bash
# 检查安装状态
./install_ubuntu.sh check
```

### 3. 项目配置

#### 3.1 环境变量配置

```bash
# 复制模板文件
cp .env.production .env

# 编辑配置文件
nano .env
```

**必须配置的关键参数**:

```bash
# Telegram配置
TELEGRAM_BOT_TOKEN=your_bot_token_here        # 从@BotFather获取
TELEGRAM_API_ID=your_api_id                   # 从my.telegram.org获取
TELEGRAM_API_HASH=your_api_hash               # 从my.telegram.org获取

# 安全配置
JWT_SECRET_KEY=your_very_secure_secret        # 生成强密码
ADMIN_PASSWORD=your_secure_admin_password     # 管理员密码

# 生产环境域名
CORS_ORIGINS=https://yourdomain.com
```

#### 3.2 获取Telegram凭证

1. **Bot Token**: 
   - 联系 [@BotFather](https://t.me/botfather)
   - 发送 `/newbot` 创建新bot
   - 获取token并填入 `TELEGRAM_BOT_TOKEN`

2. **API凭证**:
   - 访问 [my.telegram.org](https://my.telegram.org)
   - 登录并创建应用
   - 获取 `api_id` 和 `api_hash`

### 4. 部署服务

#### 4.1 完整部署

```bash
# 完整部署（包含备份）
./deploy.sh

# 快速部署（跳过备份）
./deploy.sh deploy-fast
```

#### 4.2 分步部署

```bash
# 1. 构建镜像
./deploy.sh build

# 2. 启动服务
./deploy.sh start

# 3. 检查状态
./deploy.sh status
```

### 5. SSL证书配置 (可选)

```bash
# 为域名设置SSL证书
./deploy.sh ssl yourdomain.com

# 手动设置Let's Encrypt
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d yourdomain.com
```

## 🔧 服务管理

### 日常运维命令

```bash
# 查看服务状态
./deploy.sh status

# 查看所有日志
./deploy.sh logs

# 查看特定服务日志
./deploy.sh logs app
./deploy.sh logs nginx

# 重启服务
./deploy.sh restart

# 停止服务
./deploy.sh stop

# 创建备份
./deploy.sh backup
```

### 系统服务管理

```bash
# 设置开机自启
sudo systemctl enable telegram-bot

# 启动系统服务
sudo systemctl start telegram-bot

# 查看服务状态
sudo systemctl status telegram-bot

# 查看系统日志
journalctl -u telegram-bot -f
```

## 📊 监控和维护

### 1. 健康检查

```bash
# Web界面健康检查
curl http://localhost/health

# API健康检查
curl http://localhost/api/health

# Redis健康检查
docker exec telegram_bot_redis redis-cli ping
```

### 2. 性能监控

```bash
# 查看容器资源使用
docker stats

# 查看系统资源
htop

# 查看磁盘使用
ncdu /opt/telegram-bot
```

### 3. 日志管理

```bash
# 实时日志
tail -f /var/log/telegram-bot/app.log

# 错误日志
tail -f /var/log/telegram-bot/error.log

# Nginx日志
tail -f /var/log/nginx/access.log
```

### 4. 备份和恢复

```bash
# 手动备份
./deploy.sh backup

# 查看备份文件
ls -la /var/backups/telegram-bot/

# 恢复备份 (需要手动操作)
sudo tar -xzf /var/backups/telegram-bot/backup_YYYYMMDD_HHMMSS.tar.gz
```

## 🔐 安全配置

### 1. 防火墙设置

```bash
# 查看防火墙状态
sudo ufw status

# 允许必要端口
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow ssh
```

### 2. SSL/TLS强化

编辑 `nginx/prod.conf`:

```nginx
# SSL配置
ssl_protocols TLSv1.2 TLSv1.3;
ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512;
ssl_prefer_server_ciphers off;
ssl_session_cache shared:SSL:10m;
```

### 3. 访问控制

```nginx
# 限制管理面板访问
location /static/admin.html {
    allow 192.168.1.0/24;  # 仅允许内网访问
    deny all;
}
```

## 🚨 故障排查

### 常见问题

1. **容器启动失败**
```bash
# 查看具体错误
docker compose -f docker-compose.prod.yml logs app

# 检查配置文件
docker compose -f docker-compose.prod.yml config
```

2. **Redis连接失败**
```bash
# 检查Redis状态
docker exec telegram_bot_redis redis-cli ping

# 检查网络连接
docker network ls
docker network inspect telegram-bot_telegram-bot-network
```

3. **Nginx配置错误**
```bash
# 测试Nginx配置
docker exec telegram_bot_nginx nginx -t

# 重新加载配置
docker exec telegram_bot_nginx nginx -s reload
```

### 性能问题

1. **内存不足**
```bash
# 检查内存使用
free -h

# 调整Worker数量 (.env文件)
WORKERS=2  # 减少worker数量
```

2. **磁盘空间不足**
```bash
# 清理Docker资源
./deploy.sh cleanup

# 清理日志文件
sudo find /var/log -name "*.log" -mtime +7 -delete
```

## 📈 扩展和优化

### 1. 负载均衡

使用多台服务器时，修改 `nginx/prod.conf`:

```nginx
upstream telegram_bot_app {
    server app1:8000;
    server app2:8000;
    server app3:8000;
}
```

### 2. 数据库集群

使用Redis Cluster:

```yaml
# docker-compose.prod.yml
redis-cluster:
  image: redis:7-alpine
  command: redis-cli --cluster create --cluster-replicas 1
```

### 3. 监控集成

添加Prometheus + Grafana:

```yaml
prometheus:
  image: prom/prometheus
  ports:
    - "9090:9090"

grafana:
  image: grafana/grafana
  ports:
    - "3000:3000"
```

## 📞 技术支持

- **文档**: 查看项目README和代码注释
- **日志**: 检查应用日志和系统日志
- **监控**: 使用健康检查端点
- **备份**: 定期创建数据备份

---

**部署完成后访问地址**:
- Web管理界面: `https://yourdomain.com/static/login.html`
- API文档: `https://yourdomain.com/api/`
- 健康检查: `https://yourdomain.com/health`