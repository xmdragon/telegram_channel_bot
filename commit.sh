#!/bin/bash

# 自动提交脚本 - 简化版本，用于快速提交

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 检查是否在git仓库中
if ! git rev-parse --git-dir > /dev/null 2>&1; then
    echo -e "${RED}❌ 错误：当前目录不是Git仓库${NC}"
    exit 1
fi

# 获取变更状态
STATUS=$(git status --porcelain)

if [ -z "$STATUS" ]; then
    echo -e "${YELLOW}📭 没有检测到任何变更${NC}"
    exit 0
fi

# 显示变更摘要
echo -e "${BLUE}📊 变更摘要：${NC}"
git status --short

# 获取变更文件数量
CHANGED_FILES=$(git status --porcelain | wc -l | tr -d ' ')
echo -e "${GREEN}✨ 共 ${CHANGED_FILES} 个文件变更${NC}"

# 自动分析变更类型
if [[ "$1" == "auto" ]]; then
    # 调用Python脚本进行智能分析
    python3 auto_commit.py auto "${@:2}"
    exit $?
fi

# 快速提交模式
if [[ "$1" == "fix" ]]; then
    if [ -z "$2" ]; then
        echo -e "${RED}❌ 请提供bug描述${NC}"
        echo "用法: ./commit.sh fix <bug描述>"
        exit 1
    fi
    
    MESSAGE="🐛 fix: ${@:2}

🤖 自动提交 $(date '+%Y-%m-%d %H:%M:%S')"
    
elif [[ "$1" == "feat" ]]; then
    if [ -z "$2" ]; then
        echo -e "${RED}❌ 请提供功能描述${NC}"
        echo "用法: ./commit.sh feat <功能描述>"
        exit 1
    fi
    
    MESSAGE="✨ feat: ${@:2}

🤖 自动提交 $(date '+%Y-%m-%d %H:%M:%S')"
    
elif [[ "$1" == "update" ]]; then
    if [ -z "$2" ]; then
        echo -e "${RED}❌ 请提供更新描述${NC}"
        echo "用法: ./commit.sh update <更新描述>"
        exit 1
    fi
    
    MESSAGE="🔄 update: ${@:2}

🤖 自动提交 $(date '+%Y-%m-%d %H:%M:%S')"
    
else
    # 默认模式 - 提示输入
    echo -e "${BLUE}请选择提交类型：${NC}"
    echo "1) 🐛 fix - Bug修复"
    echo "2) ✨ feat - 新功能"
    echo "3) 🔄 update - 更新/优化"
    echo "4) 📝 docs - 文档"
    echo "5) 🎨 style - 样式"
    echo "6) ♻️ refactor - 重构"
    echo "7) 🔧 chore - 其他"
    
    read -p "选择 (1-7): " TYPE_CHOICE
    
    case $TYPE_CHOICE in
        1) TYPE="fix"; EMOJI="🐛";;
        2) TYPE="feat"; EMOJI="✨";;
        3) TYPE="update"; EMOJI="🔄";;
        4) TYPE="docs"; EMOJI="📝";;
        5) TYPE="style"; EMOJI="🎨";;
        6) TYPE="refactor"; EMOJI="♻️";;
        7) TYPE="chore"; EMOJI="🔧";;
        *) TYPE="update"; EMOJI="🔄";;
    esac
    
    read -p "请输入提交描述: " DESCRIPTION
    
    if [ -z "$DESCRIPTION" ]; then
        DESCRIPTION="代码更新"
    fi
    
    MESSAGE="$EMOJI $TYPE: $DESCRIPTION

🤖 自动提交 $(date '+%Y-%m-%d %H:%M:%S')"
fi

# 显示即将提交的信息
echo -e "\n${BLUE}📝 提交信息：${NC}"
echo "------------------------"
echo "$MESSAGE"
echo "------------------------"

# 确认提交
read -p "确认提交？ (y/n): " CONFIRM

if [[ "$CONFIRM" != "y" && "$CONFIRM" != "Y" ]]; then
    echo -e "${YELLOW}❌ 取消提交${NC}"
    exit 0
fi

# 执行提交
git add .
git commit -m "$MESSAGE"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ 提交成功！${NC}"
    
    # 询问是否推送
    read -p "是否推送到远程仓库？ (y/n): " PUSH
    
    if [[ "$PUSH" == "y" || "$PUSH" == "Y" ]]; then
        git push
        if [ $? -eq 0 ]; then
            echo -e "${GREEN}✅ 推送成功！${NC}"
        else
            echo -e "${RED}❌ 推送失败${NC}"
        fi
    fi
else
    echo -e "${RED}❌ 提交失败${NC}"
    exit 1
fi