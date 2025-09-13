"""
广告关键词管理API
用于管理权重关键词系统

Author: Claude
Created: 2025-09-12
"""

from fastapi import APIRouter, Depends, HTTPException, Body
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Dict, List, Optional, Any
from datetime import datetime

from app.services.auth_service import get_auth_service
from app.services.detectors.weighted_keyword_detector import get_weighted_keyword_detector
from app.core.route_config import ROUTES

import logging

logger = logging.getLogger(__name__)
router = APIRouter()

# 认证配置
security = HTTPBearer()

# 认证依赖
async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[Dict[str, Any]]:
    """获取当前用户"""
    if not credentials:
        return None
    
    try:
        auth_service = get_auth_service()
        # 传递token而不是整个credentials对象
        user = await auth_service.get_current_user(credentials.credentials)
        return user
    except Exception as e:
        logger.error(f"获取当前用户失败: {e}")
        return None

async def require_auth(user: Optional[Dict[str, Any]] = Depends(get_current_user)) -> Dict[str, Any]:
    """要求用户认证"""
    if not user:
        raise HTTPException(status_code=401, detail="未授权访问")
    return user


@router.get("/training/ad-keywords")
async def get_ad_keywords(
    user: Dict[str, Any] = Depends(require_auth)
):
    """获取所有广告关键词及权重"""
    try:
        detector = get_weighted_keyword_detector()
        keywords = detector.get_keywords()
        
        # 转换为前端需要的格式
        keyword_list = [
            {
                "keyword": keyword,
                "weight": weight
            }
            for keyword, weight in keywords.items()
        ]
        
        return {
            "success": True,
            "data": {
                "keywords": keyword_list,
                "total": len(keyword_list),
                "threshold": detector.threshold
            }
        }
    except Exception as e:
        logger.error(f"获取关键词失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取关键词失败: {str(e)}")


class AddKeywordRequest(BaseModel):
    keyword: str
    weight: float

@router.post("/training/ad-keywords")
async def add_ad_keyword(
    request: AddKeywordRequest,
    user: Dict[str, Any] = Depends(require_auth)
):
    """添加广告关键词"""
    try:
        keyword = request.keyword
        weight = request.weight
        
        if not keyword or weight < 0.1 or weight > 10.0:
            raise HTTPException(status_code=400, detail="权重必须在0.1-10.0之间")
        
        detector = get_weighted_keyword_detector()
        success = detector.add_keyword(keyword, weight)
        
        if success:
            return {
                "success": True,
                "message": "关键词已添加",
                "data": {
                    "keyword": keyword,
                    "weight": weight
                }
            }
        else:
            raise HTTPException(status_code=500, detail="添加关键词失败")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"添加关键词失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"添加关键词失败: {str(e)}")


@router.put("/training/ad-keywords/{keyword}")
async def update_ad_keyword(
    keyword: str,
    weight: float = Body(..., embed=True),
    user: Dict[str, Any] = Depends(require_auth)
):
    """更新关键词权重"""
    try:
        if weight < 0.1 or weight > 10.0:
            raise HTTPException(status_code=400, detail="权重必须在0.1-10.0之间")
        
        detector = get_weighted_keyword_detector()
        success = detector.update_keyword(keyword, weight)
        
        if success:
            return {
                "success": True,
                "message": "权重已更新",
                "data": {
                    "keyword": keyword,
                    "weight": weight
                }
            }
        else:
            raise HTTPException(status_code=404, detail="关键词不存在")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新关键词失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"更新关键词失败: {str(e)}")


@router.delete("/training/ad-keywords/{keyword}")
async def delete_ad_keyword(
    keyword: str,
    user: Dict[str, Any] = Depends(require_auth)
):
    """删除关键词"""
    try:
        detector = get_weighted_keyword_detector()
        success = detector.delete_keyword(keyword)
        
        if success:
            return {
                "success": True,
                "message": "关键词已删除",
                "data": {
                    "keyword": keyword
                }
            }
        else:
            raise HTTPException(status_code=404, detail="关键词不存在")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除关键词失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"删除关键词失败: {str(e)}")


@router.put("/training/ad-keywords/threshold")
async def update_threshold(
    threshold: float = Body(..., embed=True),
    user: Dict[str, Any] = Depends(require_auth)
):
    """更新检测阈值"""
    try:
        if threshold < 0.1 or threshold > 20.0:
            raise HTTPException(status_code=400, detail="阈值必须在0.1-20.0之间")
        
        detector = get_weighted_keyword_detector()
        success = detector.set_threshold(threshold)
        
        if success:
            return {
                "success": True,
                "message": "阈值已更新",
                "data": {
                    "threshold": threshold
                }
            }
        else:
            raise HTTPException(status_code=500, detail="更新阈值失败")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新阈值失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"更新阈值失败: {str(e)}")


@router.get("/training/ad-keywords/stats")
async def get_keyword_stats(
    user: Dict[str, Any] = Depends(require_auth)
):
    """获取关键词检测统计"""
    try:
        detector = get_weighted_keyword_detector()
        stats = detector.get_stats()
        
        return {
            "success": True,
            "data": stats
        }
    except Exception as e:
        logger.error(f"获取统计失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取统计失败: {str(e)}")