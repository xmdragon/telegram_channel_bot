"""
尾部过滤管理模块 - 代理到 app.services.filters.tail_filter
"""
from fastapi import APIRouter, HTTPException
import logging

from app.services.filters.tail_filter import get_tail_filter_manager
from app.core.route_config import ROUTES

logger = logging.getLogger(__name__)
router = APIRouter(tags=["training-tail-filter"])


@router.get(ROUTES.training.tail_filter_statistics)
async def get_tail_filter_statistics():
    """获取尾部过滤统计信息"""
    manager = get_tail_filter_manager()
    return manager.get_statistics()


@router.get(ROUTES.training.tail_filter_history)
async def get_tail_filter_history(limit: int = 20):
    """获取尾部过滤历史记录 - 返回空列表"""
    # 不需要历史功能，返回空
    return {
        "success": True,
        "history": [],
        "total": 0
    }


@router.get(ROUTES.training.tail_filter_samples)
async def get_tail_filter_samples(page: int = 1, page_size: int = 20):
    """获取尾部过滤样本列表（分页）"""
    manager = get_tail_filter_manager()
    return manager.get_samples(page, page_size)


@router.post(ROUTES.training.tail_filter_samples)
async def add_tail_filter_sample(request: dict):
    """添加尾部过滤样本"""
    tail_part = request.get('tail_part', '').strip()
    if not tail_part:
        raise HTTPException(status_code=400, detail="尾部内容不能为空")

    rules = request.get('rules', [])
    manager = get_tail_filter_manager()
    return manager.add_sample(tail_part, rules)


@router.get(ROUTES.training.tail_filter_samples_by_id)
async def get_tail_filter_sample_by_id(sample_id: int):
    """根据ID获取尾部过滤样本"""
    manager = get_tail_filter_manager()
    result = manager.get_sample_by_id(sample_id)
    if not result.get('success'):
        raise HTTPException(status_code=404, detail=result.get('message', '样本不存在'))
    return result


@router.put(ROUTES.training.tail_filter_samples_by_id)
async def update_tail_filter_sample(sample_id: int, request: dict):
    """更新尾部过滤样本"""
    tail_part = request.get('tail_part', '').strip()
    if not tail_part:
        raise HTTPException(status_code=400, detail="尾部内容不能为空")

    rules = request.get('rules', [])
    manager = get_tail_filter_manager()
    result = manager.update_sample(sample_id, tail_part, rules)

    if not result.get('success'):
        raise HTTPException(status_code=404, detail=result.get('message', '更新失败'))
    return result


@router.delete(ROUTES.training.tail_filter_samples_by_id)
async def delete_tail_filter_sample(sample_id: int):
    """删除尾部过滤样本"""
    manager = get_tail_filter_manager()
    result = manager.delete_sample(sample_id)
    if not result.get('success'):
        raise HTTPException(status_code=404, detail=result.get('message', '删除失败'))
    return result