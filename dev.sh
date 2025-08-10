#!/bin/bash

# 开发环境运行脚本（支持自动重载）

set -e

echo "🚀 启动开发模式..."

# 检查虚拟环境
if [ ! -d "venv" ]; then
    echo "📦 创建虚拟环境..."
    python3 -m venv venv
fi

# 激活虚拟环境
echo "🔧 激活虚拟环境..."
source venv/bin/activate

# 检查依赖
if [ ! -f "venv/installed.flag" ]; then
    echo "📚 安装依赖..."
    pip install -r requirements.txt
    # 安装开发依赖（如果需要）
    pip install watchdog 2>/dev/null || true
    touch venv/installed.flag
fi

# 创建必要的目录
mkdir -p logs data temp_media

# 检查并启动Docker数据库服务
echo "🐳 检查Docker数据库服务..."
if ! docker compose ps postgres 2>/dev/null | grep -q "running"; then
    echo "📦 启动PostgreSQL数据库..."
    docker compose up -d postgres
    # 等待数据库就绪
    echo "⏳ 等待数据库就绪..."
    sleep 3
fi

if ! docker compose ps redis 2>/dev/null | grep -q "running"; then
    echo "📦 启动Redis缓存..."
    docker compose up -d redis
    
    # 等待Redis就绪
    echo "⏳ 等待Redis就绪..."
    for i in {1..10}; do
        if docker exec telegram_bot_redis redis-cli ping > /dev/null 2>&1; then
            echo "✅ Redis已就绪"
            break
        fi
        if [ $i -eq 10 ]; then
            echo "❌ Redis启动超时"
            exit 1
        fi
        sleep 1
    done
fi

# 检查数据库是否需要初始化
if [ ! -f "data/db_initialized.flag" ]; then
    echo "📊 初始化数据库..."
    python3 init_db.py
    touch data/db_initialized.flag
fi

# 使用uvicorn的reload功能启动（如果可用）
echo "🌟 启动应用（开发模式，支持热重载）..."
echo "📝 提示：修改代码后会自动重新加载"
echo "📊 日志文件："
echo "   - 完整日志: ./logs/app.log"
echo "   - 错误日志: ./logs/error.log (仅WARNING和ERROR)"
echo "   - 查看错误: ./view_errors.sh"
echo

# 检查是否安装了uvicorn
if python3 -c "import uvicorn" 2>/dev/null; then
    # 使用uvicorn的热重载功能
    exec uvicorn main:app --host 0.0.0.0 --port 8000 --reload
else
    # 降级为普通启动
    echo "⚠️  未检测到uvicorn，使用普通模式启动（不支持热重载）"
    exec python3 main.py
fi