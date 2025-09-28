"""
文本过滤器API
用于管理文本过滤关键词

Author: Claude
Created: 2025-09-29
"""

from fastapi import APIRouter, Depends, HTTPException, Body
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Dict, List, Optional, Any
from datetime import datetime

from app.services.auth_service import get_auth_service
from app.services.filters.text_filter import get_text_filter
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


@router.delete(ROUTES.training.text_filters_clear)
async def clear_text_filters(
    user: Dict[str, Any] = Depends(require_auth)
):
    """清除所有文本过滤器"""
    try:
        text_filter = get_text_filter()

        # 清空过滤器列表
        text_filter.filters = []
        text_filter.compiled_regexes = {}

        # 保存到文件
        if not text_filter.save_filters():
            raise HTTPException(status_code=500, detail="保存失败")

        return {
            "success": True,
            "message": "成功清除所有文本过滤器"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"清除文本过滤器失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"清除失败: {str(e)}")


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