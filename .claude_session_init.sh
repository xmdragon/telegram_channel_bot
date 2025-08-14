#!/bin/bash
# Claude Code Session 初始化脚本
# 每次新session开始时自动检查和提醒

echo "🤖 Claude Code Session 初始化检查..."
echo "======================================================"

# 检查是否有未提交的修改
if [ -n "$(git status --porcelain)" ]; then
    echo "⚠️  发现未提交的修改："
    git status --short
    echo ""
    echo "📝 提醒：请使用以下命令提交修改："
    echo "   python3 auto_commit.py     # 智能自动提交"
    echo "   ./commit.sh fix \"描述\"      # 快速修复提交"
    echo "   ./commit.sh feat \"描述\"     # 快速功能提交"
    echo ""
else
    echo "✅ 工作区干净，无未提交修改"
fi

# 显示最近的提交
echo "📊 最近的提交记录："
git log --oneline -3
echo ""

# 检查分支状态
branch_status=$(git status -b --porcelain | head -1)
if echo "$branch_status" | grep -q "ahead"; then
    ahead_count=$(echo "$branch_status" | grep -o 'ahead [0-9]*' | grep -o '[0-9]*')
    echo "⬆️  本地分支领先远程 $ahead_count 个提交"
    echo "💡 建议：适时使用 git push 推送到远程仓库"
elif echo "$branch_status" | grep -q "behind"; then
    behind_count=$(echo "$branch_status" | grep -o 'behind [0-9]*' | grep -o '[0-9]*')
    echo "⬇️  本地分支落后远程 $behind_count 个提交"
    echo "💡 建议：使用 git pull 拉取最新代码"
else
    echo "🔄 分支与远程同步"
fi

echo ""
echo "🎯 记住：完成任何代码修改后都要自动提交！"
echo "======================================================"