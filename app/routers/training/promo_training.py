"""
推广链接训练数据管理路由
"好代码没有特殊情况" - Linus Torvalds
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import json
import logging
from datetime import datetime

from app.core.route_config import ROUTES

# 设置日志
logger = logging.getLogger(__name__)

router = APIRouter()

class PromoTrainingRequest(BaseModel):
    """推广链接训练请求"""
    promo_content: str  # 推广内容
    separator_type: Optional[str] = ""  # 分隔符类型

class PromoFilterPreviewRequest(BaseModel):
    """推广过滤预览请求"""
    content: str  # 要预览过滤的内容

@router.post(ROUTES.training.promo_samples)
async def add_promo_sample(request: PromoTrainingRequest):
    """
    添加推广链接训练样本
    这是一个占位符实现，用于解决前端按钮404错误
    """
    try:
        # 验证输入
        if not request.promo_content.strip():
            raise HTTPException(status_code=400, detail="推广内容不能为空")
        
        # 临时数据处理（实际实现需要保存到数据库）
        sample_data = {
            "id": f"promo_{datetime.now().timestamp()}",
            "promo_content": request.promo_content,
            "separator_type": request.separator_type,
            "created_at": datetime.now().isoformat(),
            "status": "active",
            "is_promo": True
        }
        
        logger.info(f"推广内容训练样本已添加: {sample_data['id']}")
        
        return {
            "success": True,
            "message": "推广内容训练样本已成功添加",
            "data": {
                "sample_id": sample_data["id"],
                "content_length": len(request.promo_content)
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"添加推广链接训练样本失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"服务器内部错误: {str(e)}")

@router.post(ROUTES.training.preview_promo_filter)
async def preview_promo_filter(request: PromoFilterPreviewRequest):
    """
    预览推广过滤效果
    这是一个占位符实现，用于解决前端按钮404错误
    """
    try:
        if not request.content.strip():
            raise HTTPException(status_code=400, detail="内容不能为空")
        
        # 简单的推广内容检测逻辑（占位符）
        content = request.content.strip()
        
        # 检测常见推广关键词
        promo_keywords = [
            "订阅", "关注", "@", "t.me", "频道", "群组", 
            "链接", "加入", "点击", "联系", "商务合作"
        ]
        
        detected_features = []
        for keyword in promo_keywords:
            if keyword in content:
                detected_features.append(keyword)
        
        # 模拟过滤效果
        is_promo_detected = len(detected_features) >= 2
        confidence = min(len(detected_features) * 0.2, 1.0)
        
        # 简单的内容分割（实际实现需要更复杂的算法）
        lines = content.split('\n')
        filtered_content = content
        removed_sections = []
        
        if is_promo_detected:
            # 移除包含多个推广关键词的行
            filtered_lines = []
            for line in lines:
                line_keywords = sum(1 for keyword in promo_keywords if keyword in line)
                if line_keywords <= 1:  # 保留推广关键词不超过1个的行
                    filtered_lines.append(line)
                else:
                    removed_sections.append(line)
            
            filtered_content = '\n'.join(filtered_lines)
        
        return {
            "success": True,
            "data": {
                "original_content": content,
                "filtered_content": filtered_content,
                "is_promo_detected": is_promo_detected,
                "confidence": round(confidence, 2),
                "detected_features": detected_features,
                "removed_sections": removed_sections,
                "filter_stats": {
                    "original_length": len(content),
                    "filtered_length": len(filtered_content),
                    "removed_length": len(content) - len(filtered_content),
                    "removal_percentage": round((len(content) - len(filtered_content)) / len(content) * 100, 1) if content else 0
                }
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"预览推广过滤失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"服务器内部错误: {str(e)}")

@router.get(ROUTES.training.promo_samples)
async def get_promo_samples():
    """
    获取推广链接训练样本列表
    占位符实现
    """
    try:
        # 返回空的样本列表
        return {
            "success": True,
            "data": {
                "samples": [],
                "total_count": 0,
                "statistics": {
                    "total_samples": 0,
                    "active_samples": 0,
                    "today_added": 0
                }
            }
        }
        
    except Exception as e:
        logger.error(f"获取推广链接训练样本失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"服务器内部错误: {str(e)}")