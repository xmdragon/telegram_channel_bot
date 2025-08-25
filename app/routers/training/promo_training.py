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
from .base import (
    PromoSample, load_promo_samples, save_promo_samples,
    generate_sample_id, handle_api_error
)

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
    """
    try:
        # 验证输入
        if not request.promo_content.strip():
            raise HTTPException(status_code=400, detail="推广内容不能为空")
        
        # 加载现有样本
        samples = load_promo_samples()
        
        # 创建新样本
        sample_data = {
            "id": generate_sample_id(request.promo_content),
            "promo_content": request.promo_content.strip(),
            "separator_type": request.separator_type or "",
            "created_at": datetime.now().isoformat()
        }
        
        # 添加到样本列表
        samples.append(sample_data)
        
        # 保存到文件
        if not save_promo_samples(samples):
            raise HTTPException(status_code=500, detail="保存样本失败")
        
        logger.info(f"推广内容训练样本已添加: {sample_data['id']}")
        
        return {
            "success": True,
            "message": "推广内容训练样本已成功添加",
            "data": {
                "sample_id": sample_data["id"],
                "content_length": len(request.promo_content),
                "total_samples": len(samples)
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
    """
    try:
        # 加载样本数据
        samples = load_promo_samples()
        
        # 计算统计信息
        total_samples = len(samples)
        active_samples = len([s for s in samples if s.get('promo_content')])
        
        # 计算今日新增
        today = datetime.now().date()
        today_added = 0
        for sample in samples:
            created_at = sample.get('created_at', '')
            if created_at:
                try:
                    sample_date = datetime.fromisoformat(created_at).date()
                    if sample_date == today:
                        today_added += 1
                except:
                    pass
        
        return {
            "success": True,
            "data": {
                "samples": samples,
                "total_count": total_samples,
                "statistics": {
                    "total_samples": total_samples,
                    "active_samples": active_samples,
                    "today_added": today_added
                }
            }
        }
        
    except Exception as e:
        logger.error(f"获取推广链接训练样本失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"服务器内部错误: {str(e)}")

@router.put("/training/promo-samples/{sample_id}")
async def update_promo_sample(sample_id: str, request: PromoTrainingRequest):
    """
    更新推广链接训练样本
    """
    try:
        # 验证输入
        if not request.promo_content.strip():
            raise HTTPException(status_code=400, detail="推广内容不能为空")
        
        # 加载现有样本
        samples = load_promo_samples()
        
        # 查找要更新的样本
        sample_found = False
        for i, sample in enumerate(samples):
            if sample.get('id') == sample_id:
                # 更新样本数据
                samples[i]['promo_content'] = request.promo_content.strip()
                samples[i]['separator_type'] = request.separator_type or ""
                samples[i]['updated_at'] = datetime.now().isoformat()
                sample_found = True
                break
        
        if not sample_found:
            raise HTTPException(status_code=404, detail="样本未找到")
        
        # 保存更新后的数据
        if not save_promo_samples(samples):
            raise HTTPException(status_code=500, detail="更新样本失败")
        
        logger.info(f"推广内容训练样本已更新: {sample_id}")
        
        return {
            "success": True,
            "message": "推广内容训练样本已成功更新",
            "data": {
                "sample_id": sample_id,
                "content_length": len(request.promo_content)
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新推广链接训练样本失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"服务器内部错误: {str(e)}")

@router.delete("/training/promo-samples/{sample_id}")
async def delete_promo_sample(sample_id: str):
    """
    删除推广链接训练样本
    """
    try:
        # 加载现有样本
        samples = load_promo_samples()
        
        # 查找并删除样本
        original_count = len(samples)
        samples = [s for s in samples if s.get('id') != sample_id]
        
        if len(samples) == original_count:
            raise HTTPException(status_code=404, detail="样本未找到")
        
        # 保存更新后的数据
        if not save_promo_samples(samples):
            raise HTTPException(status_code=500, detail="删除样本失败")
        
        logger.info(f"推广内容训练样本已删除: {sample_id}")
        
        return {
            "success": True,
            "message": "推广内容训练样本已成功删除",
            "data": {
                "sample_id": sample_id,
                "remaining_samples": len(samples)
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除推广链接训练样本失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"服务器内部错误: {str(e)}")