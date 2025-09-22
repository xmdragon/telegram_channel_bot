#!/bin/bash

# 部署脚本 - 初始化配置文件

echo "🚀 开始部署 Telegram Channel Bot..."

# 检查并创建必要的目录
mkdir -p data/config
mkdir -p data/backups
mkdir -p data/training
mkdir -p logs
mkdir -p temp_media

# 检查system.json是否存在，如果不存在则从模板创建
if [ ! -f "data/config/system.json" ]; then
    if [ -f "data/config/system.json.example" ]; then
        echo "📋 从模板创建 system.json..."
        cp data/config/system.json.example data/config/system.json
        echo "✅ system.json 已创建"
        echo "⚠️  请编辑 data/config/system.json 并填入您的 Telegram API 凭据"
    else
        echo "❌ 错误：找不到 system.json.example 模板文件"
        exit 1
    fi
else
    echo "✅ system.json 已存在"
fi

# 检查其他必要的配置文件
if [ ! -f "data/config/channels.json" ]; then
    echo "📋 创建空的 channels.json..."
    echo "{}" > data/config/channels.json
fi

if [ ! -f "data/config/admins.json" ]; then
    echo "📋 创建默认的 admins.json..."
    cat > data/config/admins.json << 'EOF'
{
  "1": {
    "username": "admin",
    "password_hash": "240be518fabd2724ddb6f04eeb1da5967448d7e831c08c8fa822809f74c720a9",
    "is_active": true,
    "is_super_admin": true,
    "created_at": "2025-08-14T19:18:31.538677",
    "updated_at": "2025-08-14T19:18:31.538677",
    "last_login": null
  }
}
EOF
    echo "✅ 默认管理员账号创建完成 (用户名: admin, 密码: admin123)"
fi

# 安装Python依赖
if [ -f "requirements.txt" ]; then
    echo "📦 安装Python依赖..."
    pip install -r requirements.txt
fi

# 检查Redis服务
echo "🔍 检查Redis服务..."
if command -v redis-cli &> /dev/null; then
    if redis-cli ping > /dev/null 2>&1; then
        echo "✅ Redis服务正在运行"
    else
        echo "⚠️  Redis服务未运行，请启动Redis: redis-server"
    fi
else
    echo "⚠️  Redis未安装，请先安装Redis"
fi

echo ""
echo "✨ 部署准备完成！"
echo ""
echo "下一步操作："
echo "1. 编辑 data/config/system.json 配置文件"
echo "2. 在 https://my.telegram.org 获取 API ID 和 API Hash"
echo "3. 填入 telegram.api_id 和 telegram.api_hash"
echo "4. 运行 ./start.sh 启动所有服务"
echo "5. 访问 http://localhost:8080 进行Telegram认证"
echo ""