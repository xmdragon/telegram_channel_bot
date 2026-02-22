"""
文本过滤器API
用于管理文本过滤关键词

Author: Claude
Created: 2025-09-29
"""

from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel
from typing import Dict, List, Optional, Any
from datetime import datetime

from app.services.filters.text_filter import get_text_filter
from app.core.route_config import ROUTES
from app.api.deps import require_auth

import logging

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(ROUTES.training.text_filters)
async def get_text_filters(
    user: Dict[str, Any] = Depends(require_auth)
):
    """获取所有文本过滤器"""
    try:
        text_filter = get_text_filter()
        filters = text_filter.get_filters()

        return {
            "success": True,
            "data": {
                "filters": filters,
                "total": len(filters)
            }
        }
    except Exception as e:
        logger.error(f"获取文本过滤器失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取文本过滤器失败: {str(e)}")


class AddFilterRequest(BaseModel):
    keyword: str
    is_regex: bool = False

@router.post(ROUTES.training.text_filters)
async def add_text_filter(
    request: AddFilterRequest,
    user: Dict[str, Any] = Depends(require_auth)
):
    """添加文本过滤器"""
    try:
        keyword = request.keyword.strip()
        if not keyword:
            raise HTTPException(status_code=400, detail="关键词不能为空")

        text_filter = get_text_filter()
        success = text_filter.add_filter(keyword, request.is_regex)

        if not success:
            raise HTTPException(status_code=400, detail="添加失败，关键词可能已存在或正则表达式无效")

        return {
            "success": True,
            "message": f"成功添加文本过滤器: {keyword}"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"添加文本过滤器失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"添加失败: {str(e)}")


@router.delete(ROUTES.training.text_filters_by_keyword)
async def delete_text_filter(
    keyword: str,
    user: Dict[str, Any] = Depends(require_auth)
):
    """删除文本过滤器"""
    try:
        text_filter = get_text_filter()
        success = text_filter.remove_filter(keyword)

        if not success:
            raise HTTPException(status_code=404, detail=f"过滤器不存在: {keyword}")

        return {
            "success": True,
            "message": f"成功删除文本过滤器: {keyword}"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除文本过滤器失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"删除失败: {str(e)}")



class TestFilterRequest(BaseModel):
    text: str

@router.post(ROUTES.training.test_text_filter)
async def test_text_filter(
    request: TestFilterRequest,
    user: Dict[str, Any] = Depends(require_auth)
):
    """测试文本过滤效果"""
    try:
        if not request.text:
            raise HTTPException(status_code=400, detail="测试文本不能为空")

        text_filter = get_text_filter()
        result = text_filter.test_filter(request.text)

        return {
            "success": True,
            "data": result
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"测试文本过滤失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"测试失败: {str(e)}")