#!/bin/bash
# Web服务器启动脚本 - 支持开发和生产模式
# Linus原则：一个脚本处理多种情况，但保持简单

set -e

# 配置
MODE="${1:-dev}"  # dev 或 prod
PORT="${PORT:-8000}"
WORKERS="${WORKERS:-4}"

# 确保日志目录存在
mkdir -p logs

echo "🚀 启动Web服务器 (模式: $MODE)"

case "$MODE" in
    "dev"|"development")
        echo "📋 开发模式: uvicorn直接启动"
        echo "   - 端口: $PORT"
        echo "   - Workers: 1 (开发模式)"
        echo "   - 热重载: 启用"
        
        ./venv/bin/uvicorn web_server:app \
            --host 0.0.0.0 \
            --port $PORT \
            --reload \
            --log-level info
        ;;
        
    "prod"|"production")
        echo "🏭 生产模式: Gunicorn + uvicorn workers"
        echo "   - 端口: $PORT"
        echo "   - Workers: $WORKERS"
        echo "   - 进程管理: Gunicorn"
        echo "   - Worker类型: UvicornWorker"
        
        ./venv/bin/gunicorn web_server:app \
            --config gunicorn.conf.py \
            --bind 0.0.0.0:$PORT \
            --workers $WORKERS
        ;;
        
    "test"|"testing")
        echo "🧪 测试模式: 单worker，适合调试"
        echo "   - 端口: $PORT" 
        echo "   - Workers: 1"
        echo "   - 日志: 详细"
        
        WORKERS=1 ./venv/bin/gunicorn web_server:app \
            --config gunicorn.conf.py \
            --bind 0.0.0.0:$PORT \
            --workers 1 \
            --log-level debug
        ;;
        
    *)
        echo "❌ 未知模式: $MODE"
        echo "用法: $0 [dev|prod|test]"
        echo ""
        echo "示例:"
        echo "  $0 dev     # 开发模式，热重载"
        echo "  $0 prod    # 生产模式，多进程"
        echo "  $0 test    # 测试模式，单进程调试"
        exit 1
        ;;
esac