# Docker 部署指南

## 🐳 概述

本项目支持 Docker 容器化部署，提供了完整的容器化解决方案，包括应用服务、Redis 缓存等。

## 📋 系统要求

- Docker 20.10+
- Docker Compose 2.0+
- 至少 2GB 可用内存
- 至少 5GB 可用磁盘空间

## 🚀 快速开始

### 1. 克隆项目

```bash
git clone <repository-url>
cd telegram_channel_bot
```

### 2. 构建并启动

```bash
# 生产环境
docker-compose up -d

# 开发环境（代码热重载）
docker-compose -f docker-compose.dev.yml up -d
```

### 3. 查看日志

```bash
# 查看应用日志
docker-compose logs -f app

# 查看所有服务日志
docker-compose logs -f
```

### 4. 访问系统

- **状态检查**: http://localhost:8000/status
- **登录页面**: http://localhost:8000/auth
- **主界面**: http://localhost:8000
- **配置界面**: http://localhost:8000/config

## 🔧 配置说明

### 环境变量

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `DATABASE_URL` | `sqlite:///./telegram_system.db` | 数据库连接URL |
| `REDIS_URL` | `redis://redis:6379` | Redis连接URL |
| `LOG_LEVEL` | `INFO` | 日志级别 |
| `TZ` | `Asia/Shanghai` | 时区设置 |

### 数据持久化

项目会自动创建以下目录：

- `./sessions/` - Telegram 会话文件
- `./logs/` - 应用日志
- `./data/` - 数据文件

### 网络配置

- **应用端口**: 8000
- **Redis端口**: 6379
- **网络**: `telegram_network`

## 📦 服务架构

```
┌─────────────────┐    ┌─────────────────┐
│   Telegram      │    │   Web Browser   │
│   App           │    │                 │
└─────────────────┘    └─────────────────┘
         │                       │
         ▼                       ▼
┌─────────────────┐    ┌─────────────────┐
│   FastAPI App   │◄──►│   Redis Cache   │
│   (Port 8000)   │    │   (Port 6379)   │
└─────────────────┘    └─────────────────┘
```

## 🛠️ 常用命令

### 基础操作

```bash
# 构建镜像
docker-compose build

# 启动服务
docker-compose up -d

# 停止服务
docker-compose down

# 重启服务
docker-compose restart

# 查看服务状态
docker-compose ps
```

### 开发操作

```bash
# 开发环境启动
docker-compose -f docker-compose.dev.yml up -d

# 查看实时日志
docker-compose logs -f app

# 进入容器
docker-compose exec app bash

# 运行测试
docker-compose exec app python test_telethon.py
```

### 维护操作

```bash
# 清理未使用的镜像
docker system prune

# 清理所有数据（谨慎使用）
docker-compose down -v

# 备份数据
docker-compose exec app tar -czf backup.tar.gz sessions/ data/

# 恢复数据
docker-compose exec app tar -xzf backup.tar.gz
```

## 🔍 故障排除

### 常见问题

#### 1. 容器启动失败

```bash
# 查看详细错误信息
docker-compose logs app

# 检查端口占用
netstat -tulpn | grep 8000

# 重新构建镜像
docker-compose build --no-cache
```

#### 2. 数据库连接失败

```bash
# 检查数据库文件权限
docker-compose exec app ls -la data/

# 重新初始化数据库
docker-compose exec app python init_db.py
```

#### 3. Redis 连接失败

```bash
# 检查 Redis 状态
docker-compose exec redis redis-cli ping

# 重启 Redis
docker-compose restart redis
```

#### 4. 会话文件问题

```bash
# 检查会话文件
docker-compose exec app ls -la sessions/

# 清理会话文件
docker-compose exec app rm -f sessions/*
```

### 日志分析

```bash
# 查看应用日志
docker-compose logs app

# 查看错误日志
docker-compose logs app | grep ERROR

# 实时监控日志
docker-compose logs -f app | grep -E "(ERROR|WARNING)"
```

## 🔒 安全配置

### 生产环境建议

1. **修改默认端口**
   ```yaml
   ports:
     - "9000:8000"  # 使用非标准端口
   ```

2. **设置环境变量**
   ```bash
   export DATABASE_URL="postgresql://user:pass@host:5432/db"
   export REDIS_URL="redis://user:pass@host:6379"
   ```

3. **启用 HTTPS**
   - 使用 Nginx 反向代理
   - 配置 SSL 证书

4. **限制资源使用**
   ```yaml
   deploy:
     resources:
       limits:
         memory: 1G
         cpus: '0.5'
   ```

## 📊 监控和健康检查

### 健康检查

容器内置健康检查：

```dockerfile
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/status')" || exit 1
```

### 监控指标

- 应用响应时间
- 内存使用情况
- CPU 使用率
- 磁盘使用情况

## 🚀 部署到生产环境

### 1. 准备环境

```bash
# 创建生产环境目录
mkdir -p /opt/telegram-bot
cd /opt/telegram-bot

# 复制项目文件
cp -r /path/to/telegram_channel_bot/* .

# 设置权限
chown -R 1000:1000 .
```

### 2. 配置环境变量

```bash
# 创建环境变量文件
cat > .env << EOF
DATABASE_URL=postgresql://user:pass@host:5432/telegram_system
REDIS_URL=redis://user:pass@host:6379
LOG_LEVEL=INFO
TZ=Asia/Shanghai
EOF
```

### 3. 启动服务

```bash
# 启动服务
docker-compose up -d

# 检查状态
docker-compose ps

# 查看日志
docker-compose logs -f
```

### 4. 配置反向代理（可选）

```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## 📝 注意事项

1. **数据备份**: 定期备份 `sessions/` 和 `data/` 目录
2. **日志管理**: 配置日志轮转，避免磁盘空间不足
3. **安全更新**: 定期更新 Docker 镜像和依赖包
4. **资源监控**: 监控容器资源使用情况
5. **网络配置**: 确保容器间网络通信正常

## 🆘 获取帮助

如果遇到问题，请：

1. 查看日志：`docker-compose logs -f`
2. 检查状态：`docker-compose ps`
3. 查看文档：`README.md`
4. 提交 Issue：项目仓库

---

**Docker 配置完成时间**: 2025-08-02  
**状态**: ✅ 完成  
**测试状态**: ✅ 通过 