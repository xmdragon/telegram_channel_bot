"""
分隔符模式管理模块
"""
from fastapi import APIRouter, HTTPException
from datetime import datetime
from typing import List, Dict
from pydantic import BaseModel
import logging
import json
from pathlib import Path

from app.core.path_config import PathConfig
from app.utils.safe_file_ops import SafeFileOperation
from app.core.route_config import ROUTES

logger = logging.getLogger(__name__)

# 文件路径配置
SEPARATOR_PATTERNS_FILE = PathConfig.SEPARATOR_PATTERNS_FILE

# 确保目录存在
PathConfig.ensure_directories()

# Pydantic模型定义
class SeparatorPattern(BaseModel):
    """分隔符模式模型"""
    pattern: str  # 前端传入的字段名，内部映射到regex
    description: str = ""

# 核心数据操作函数
def load_separator_patterns() -> List[Dict]:
    """加载分隔符模式"""
    try:
        if SEPARATOR_PATTERNS_FILE.exists():
            data = SafeFileOperation.read_json_safe(SEPARATOR_PATTERNS_FILE)
            return data.get('patterns', []) if data else []
        return []
    except Exception as e:
        logger.error(f"加载分隔符模式失败: {e}")
        return []

def save_separator_patterns(patterns: List[Dict]) -> bool:
    """保存分隔符模式"""
    try:
        data = {
            'patterns': patterns,
            'updated_at': datetime.now().isoformat(),
            'total_count': len(patterns)
        }
        SafeFileOperation.write_json_safe(SEPARATOR_PATTERNS_FILE, data)
        return True
    except Exception as e:
        logger.error(f"保存分隔符模式失败: {e}")
        return False

# 错误处理工具
def handle_api_error(error: Exception, operation: str) -> HTTPException:
    """统一的API错误处理"""
    logger.error(f"{operation}失败: {error}")
    return HTTPException(
        status_code=500,
        detail=f"{operation}失败: {str(error)}"
    )

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

