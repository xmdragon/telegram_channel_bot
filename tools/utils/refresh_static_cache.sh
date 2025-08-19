#!/bin/bash
# 快速刷新静态资源缓存
echo "🔄 刷新静态资源缓存..."
python3 "/Users/eric/workspace/telegram_channel_bot/tools/utils/static_version_manager.py" --mode dev --quiet
echo "✅ 缓存刷新完成"
