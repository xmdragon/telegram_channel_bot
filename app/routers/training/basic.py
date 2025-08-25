"""
基础训练数据管理模块 - 频道、统计、历史记录等核心功能
"""
from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timedelta
from typing import List, Dict, Any
import logging
import hashlib

from .base import (
    check_permission, SeparatorPattern,
    load_separator_patterns, save_separator_patterns,
    generate_sample_id, validate_sample_data, calculate_statistics,
    handle_api_error, validate_pagination_params,
    paginate_data
)
# 注意：load_training_data, save_training_data, TrainingSubmission 已废弃
from app.core.path_config import PathConfig
from app.core.route_config import ROUTES

logger = logging.getLogger(__name__)
router = APIRouter(tags=["training-basic"])

@router.get(ROUTES.training.channels)
async def get_channels():
    """获取频道列表（手动训练数据功能已移除）"""
    # 手动训练数据功能已移除，返回空列表保持API兼容性
    logger.info("手动训练数据功能已移除，返回空频道列表")
    return {"channels": []}

@router.get(ROUTES.training.stats)
async def get_stats():
    """获取训练统计（手动训练数据功能已移除）"""
    # 手动训练数据功能已移除，返回空统计保持API兼容性
    logger.info("手动训练数据功能已移除，返回空统计")
    return {
        "totalChannels": 0,
        "trainedChannels": 0,
        "totalSamples": 0,
        "todayTraining": 0
    }

@router.get(ROUTES.training.history)
async def get_history(limit: int = 20):
    """获取训练历史（手动训练数据功能已移除）"""
    # 手动训练数据功能已移除，返回空历史保持API兼容性
    logger.info("手动训练数据功能已移除，返回空历史")
    return {"history": []}

@router.post(ROUTES.training.submit)
async def submit_training(submission: dict):  # TrainingSubmission 已废弃
    """提交训练数据（手动训练数据功能已移除）"""
    # 手动训练数据功能已移除，但保持API兼容性
    logger.warning("手动训练数据功能已移除，提交请求被忽略")
    return {"success": False, "message": "手动训练数据功能已移除，请使用专门的AI训练模块"}

@router.delete(ROUTES.training.sample_by_id)
async def delete_training_sample(sample_id: int):
    """删除训练样本（手动训练数据功能已移除）"""
    logger.warning("手动训练数据功能已移除，删除请求被忽略")
    return {"success": False, "message": "手动训练数据功能已移除"}

@router.post(ROUTES.training.apply)
async def apply_training():
    """应用所有训练数据到AI过滤器（手动训练数据功能已移除）"""
    logger.warning("手动训练数据功能已移除，应用请求被忽略")
    return {"success": False, "message": "手动训练数据功能已移除"}

@router.delete(ROUTES.training.clear_by_channel)
async def clear_channel_training(channel_id: str):
    """清除某个频道的训练数据（手动训练数据功能已移除）"""
    logger.warning("手动训练数据功能已移除，清理请求被忽略")
    return {"success": False, "message": "手动训练数据功能已移除"}

@router.get(ROUTES.training.export)
async def export_training_data():
    """导出训练数据（手动训练数据功能已移除）"""
    logger.warning("手动训练数据功能已移除，返回空导出")
    return {
        "channels": {},
        "exported_at": datetime.now().isoformat(),
        "total_samples": 0
    }

@router.post(ROUTES.training.auto_learn)
async def auto_learn_from_history(channel_id: str):
    """从现有训练样本自动学习频道模式（手动训练数据功能已移除）"""
    logger.warning("手动训练数据功能已移除，自动学习请求被忽略")
    return {"success": False, "message": "手动训练数据功能已移除"}

@router.get(ROUTES.training.sample_detail)
async def get_training_sample(sample_id: int):
    """获取单个训练样本详情（手动训练数据功能已移除）"""
    logger.warning("手动训练数据功能已移除，样本不存在")
    return {"success": False, "message": "手动训练数据功能已移除"}

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
        
        # 检查是否已存在
        for pattern in patterns:
            if pattern.get('pattern') == pattern_data.pattern:
                return {"success": False, "message": "模式已存在"}
        
        # 添加新模式
        new_pattern = {
            "id": generate_sample_id(pattern_data.pattern),
            "pattern": pattern_data.pattern,
            "description": pattern_data.description,
            "enabled": pattern_data.enabled,
            "created_at": datetime.now().isoformat()
        }
        
        patterns.append(new_pattern)
        
        if not save_separator_patterns(patterns):
            raise HTTPException(status_code=500, detail="保存模式失败")
        
        return {"success": True, "message": "模式添加成功", "id": new_pattern["id"]}
    except Exception as e:
        raise handle_api_error(e, "添加分隔符模式")

@router.post(ROUTES.training.reload_model)
async def reload_model():
    """重新加载AI模型"""
    try:
        from app.services.ai_filter import ai_filter
        
        # 重新加载模型
        success = await ai_filter.reload_model()
        
        if success:
            return {"success": True, "message": "模型重新加载成功"}
        else:
            return {"success": False, "message": "模型重新加载失败"}
            
    except ImportError:
        raise HTTPException(status_code=500, detail="AI过滤器模块未找到")
    except Exception as e:
        raise handle_api_error(e, "重新加载模型")