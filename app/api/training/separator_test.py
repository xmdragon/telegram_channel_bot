"""
分隔符测试API
"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from app.core.route_config import ROUTES
from app.services.filters.separator_filter import SeparatorFilter
import re
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

class SeparatorTestRequest(BaseModel):
    """分隔符测试请求"""
    content: str
    pattern: Optional[str] = None  # 可选，用于测试单个正则

class SeparatorTestResponse(BaseModel):
    """分隔符测试响应"""
    success: bool
    matches: List[Dict[str, Any]] = []
    filtered_content: str = ""
    original_length: int = 0
    filtered_length: int = 0
    stats: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

@router.post(ROUTES.training.test_separator)
async def test_separator_filter(request: SeparatorTestRequest) -> SeparatorTestResponse:
    """测试分隔符过滤效果"""
    try:
        if request.pattern:
            # 测试单个正则模式
            try:
                # 使用与后端相同的标志
                pattern = re.compile(
                    request.pattern,
                    re.IGNORECASE | re.MULTILINE | re.DOTALL
                )
                matches = list(pattern.finditer(request.content))
                filtered = pattern.sub('', request.content).strip()

                return SeparatorTestResponse(
                    success=True,
                    matches=[{
                        "text": m.group(),
                        "index": m.start(),
                        "length": len(m.group())
                    } for m in matches],
                    filtered_content=filtered,
                    original_length=len(request.content),
                    filtered_length=len(filtered)
                )
            except re.error as e:
                return SeparatorTestResponse(
                    success=False,
                    error=f"正则表达式错误: {str(e)}",
                    original_length=len(request.content),
                    filtered_length=len(request.content)
                )
        else:
            # 使用实际的分隔符过滤器
            filter_instance = SeparatorFilter()
            filtered, stats = filter_instance.filter_content(request.content)

            return SeparatorTestResponse(
                success=True,
                filtered_content=filtered,
                original_length=len(request.content),
                filtered_length=len(filtered),
                stats=stats
            )
    except Exception as e:
        logger.error(f"分隔符测试失败: {e}")
        return SeparatorTestResponse(
            success=False,
            error=str(e),
            original_length=len(request.content),
            filtered_length=len(request.content)
        )