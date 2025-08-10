#!/bin/bash

# 查看错误日志的便捷脚本

echo "📋 错误日志查看工具"
echo "===================="

# 检查错误日志文件是否存在
ERROR_LOG="./logs/error.log"

if [ ! -f "$ERROR_LOG" ]; then
    echo "⚠️  错误日志文件不存在: $ERROR_LOG"
    echo "系统启动后会自动创建此文件"
    exit 0
fi

# 显示选项
echo ""
echo "请选择查看方式："
echo "1. 查看最新的20条错误"
echo "2. 实时跟踪错误日志"
echo "3. 查看今天的所有错误"
echo "4. 统计错误类型"
echo "5. 查看完整错误日志"
echo ""
read -p "请输入选项 (1-5): " choice

case $choice in
    1)
        echo ""
        echo "📌 最新的20条错误："
        echo "--------------------"
        tail -n 40 "$ERROR_LOG"  # 每条错误占2行（消息+文件路径）
        ;;
    2)
        echo ""
        echo "📡 实时跟踪错误日志 (Ctrl+C 退出)："
        echo "--------------------"
        tail -f "$ERROR_LOG"
        ;;
    3)
        echo ""
        echo "📅 今天的错误："
        echo "--------------------"
        TODAY=$(date +"%Y-%m-%d")
        grep "$TODAY" "$ERROR_LOG"
        ;;
    4)
        echo ""
        echo "📊 错误统计："
        echo "--------------------"
        echo "WARNING 数量: $(grep -c "WARNING" "$ERROR_LOG")"
        echo "ERROR 数量: $(grep -c "ERROR" "$ERROR_LOG")"
        echo "CRITICAL 数量: $(grep -c "CRITICAL" "$ERROR_LOG")"
        echo ""
        echo "最常见的错误："
        grep -E "WARNING|ERROR|CRITICAL" "$ERROR_LOG" | cut -d'-' -f4- | sort | uniq -c | sort -rn | head -10
        ;;
    5)
        echo ""
        echo "📜 完整错误日志："
        echo "--------------------"
        less "$ERROR_LOG"
        ;;
    *)
        echo "❌ 无效的选项"
        exit 1
        ;;
esac

echo ""
echo "✅ 完成"