"""
分隔符模式管理模块
"""
from fastapi import APIRouter, HTTPException
import logging

from .base import (
    SeparatorPattern,
    load_separator_patterns, save_separator_patterns,
    handle_api_error
)
from app.core.route_config import ROUTES

logger = logging.getLogger(__name__)
router = APIRouter(tags=["training-separator-patterns"])
@router.get(ROUTES.training.separator_patterns)
async def get_separator_patterns():
    """获取分隔符模式列表"""
    try:
        patterns = load_separator_patterns()
        return {
            "success": True,
            "patterns": patterns,
            "total": len(patterns)
        }
    except Exception as e:
        raise handle_api_error(e, "获取分隔符模式")

@router.post(ROUTES.training.separator_patterns)
async def add_separator_pattern(pattern_data: SeparatorPattern):
    """添加分隔符模式"""
    try:
        patterns = load_separator_patterns()
        
        # 检查是否已存在（检查regex字段）
        for pattern in patterns:
            if pattern.get('regex') == pattern_data.pattern:
                return {"success": False, "message": "模式已存在"}
        
        # 添加新模式（使用正确的字段名）
        new_pattern = {
            "regex": pattern_data.pattern,  # 使用regex字段存储正则表达式
            "description": pattern_data.description
        }
        
        patterns.append(new_pattern)
        
        if not save_separator_patterns(patterns):
            raise HTTPException(status_code=500, detail="保存模式失败")
        
        return {"success": True, "message": "模式添加成功"}
    except Exception as e:
        raise handle_api_error(e, "添加分隔符模式")

@router.put(ROUTES.training.separator_patterns)
async def update_all_separator_patterns(patterns_data: dict):
    """批量更新所有分隔符模式（完全替换）"""
    try:
        patterns_list = patterns_data.get('patterns', [])

        # 转换格式并验证
        updated_patterns = []
        for pattern_item in patterns_list:
            # 支持两种格式：{regex: "", description: ""} 和 {pattern: "", description: ""}
            regex = pattern_item.get('regex') or pattern_item.get('pattern', '')
            description = pattern_item.get('description', '')

            if regex and description:  # 只保存有效的模式
                updated_patterns.append({
                    "regex": regex,
                    "description": description
                })

        # 完全替换现有数据
        if not save_separator_patterns(updated_patterns):
            raise HTTPException(status_code=500, detail="保存分隔符模式失败")
        
        return {
            "success": True, 
            "message": f"成功更新 {len(updated_patterns)} 个分隔符模式",
            "total": len(updated_patterns)
        }
    except Exception as e:
        raise handle_api_error(e, "批量更新分隔符模式")

