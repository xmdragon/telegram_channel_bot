"""
广告样本管理模块 - 广告样本的CRUD、统计和处理功能
"""
from fastapi import APIRouter, HTTPException
from datetime import datetime
from typing import List, Dict, Any
import logging
import hashlib

from .base import (
    handle_api_error, validate_pagination_params,
    paginate_data, generate_sample_id
)
from app.core.route_config import ROUTES

logger = logging.getLogger(__name__)
router = APIRouter(tags=["training-ad-samples"])

# 向量学习系统 - 不再使用传统文件训练样本

@router.get(ROUTES.training.ad_samples)
async def get_ad_samples(page: int = 1, page_size: int = 20):
    """获取广告向量统计（替代传统样本列表）"""
    try:
        from app.services.vector_manager import vector_manager
        
        # 获取向量统计
        stats = vector_manager.get_stats()
        
        return {
            "success": True,
            "samples": [],  # 保持API兼容性，但返回空列表
            "total": stats.get('total_vectors', 0),
            "page": 1,
            "page_size": page_size,
            "total_pages": 1,
            "vector_stats": stats  # 新增向量统计信息
        }
    except Exception as e:
        logger.error(f"获取向量统计失败: {e}")
        return {
            "success": False,
            "samples": [],
            "total": 0,
            "page": page,
            "page_size": page_size,
            "total_pages": 0
        }

@router.get(ROUTES.training.ad_statistics)
async def get_ad_statistics():
    """获取广告向量统计信息（替代传统样本统计）"""
    try:
        from app.services.vector_manager import vector_manager
        from app.services.vector_ad_detector import get_vector_ad_detector
        
        # 获取向量管理器统计
        vector_stats = vector_manager.get_stats()
        
        # 获取向量检测器统计
        vector_detector = get_vector_ad_detector()
        detector_stats = vector_detector.get_detection_stats()
        
        return {
            "success": True,
            "statistics": {
                "total_samples": vector_stats.get('total_vectors', 0),  # 兼容性字段
                "confirmed_ads": vector_stats.get('total_vectors', 0),  # 向量都是确认的广告
                "non_ads": 0,  # 向量系统中没有非广告样本
                "today_added": 0,  # 暂不统计今日新增
                "channel_count": vector_stats.get('unique_sources', 0),
                "top_channels": [],  # 暂不提供频道排行
                "vector_stats": vector_stats,  # 新增向量统计
                "detector_stats": detector_stats  # 新增检测器统计
            }
        }
    except Exception as e:
        logger.error(f"获取向量统计失败: {e}")
        return {
            "success": False,
            "statistics": {
                "total_samples": 0,
                "confirmed_ads": 0,
                "non_ads": 0,
                "today_added": 0,
                "channel_count": 0,
                "top_channels": []
            }
        }

@router.delete(ROUTES.training.ad_samples_by_id)
async def delete_ad_sample(sample_id: str):
    """删除广告样本"""
    try:
        samples = load_ad_samples()
        
        # 查找并删除样本
        original_count = len(samples)
        sample_to_delete = None
        for sample in samples:
            if str(sample.get('id')) == str(sample_id):
                sample_to_delete = sample
                break
        
        if not sample_to_delete:
            return {"success": False, "message": "广告样本不存在"}
        
        samples = [s for s in samples if str(s.get('id')) != str(sample_id)]
        
        # 保存更新后的数据
        if not save_ad_samples(samples):
            raise HTTPException(status_code=500, detail="保存数据失败")
        
        
        return {"success": True, "message": "删除成功"}
    except Exception as e:
        raise handle_api_error(e, "删除广告样本")

@router.delete(ROUTES.training.ad_samples_batch)
async def batch_delete_ad_samples(request: dict):
    """批量删除广告样本"""
    try:
        sample_ids = request.get("sample_ids", [])
        
        if not sample_ids:
            return {"success": False, "message": "没有指定要删除的样本"}
        
        samples = load_ad_samples()
        
        # 删除指定的样本
        original_count = len(samples)
        samples = [s for s in samples if str(s.get('id')) not in [str(sid) for sid in sample_ids]]
        deleted_count = original_count - len(samples)
        
        if deleted_count > 0:
            # 保存更新后的数据
            if not save_ad_samples(samples):
                raise HTTPException(status_code=500, detail="保存数据失败")
            
        
        return {
            "success": True,
            "message": f"批量删除完成，删除了 {deleted_count} 个样本",
            "deleted_count": deleted_count
        }
    except Exception as e:
        raise handle_api_error(e, "批量删除广告样本")

@router.post(ROUTES.training.ad_samples_detect_duplicates)
async def detect_ad_duplicates():
    """检测广告样本中的重复项"""
    try:
        samples = load_ad_samples()
        
        if len(samples) == 0:
            return {
                "success": True,
                "groups": [],
                "total_duplicates": 0,
                "total_groups": 0
            }
        
        # 检测重复 - 基于内容哈希
        duplicate_groups = []
        processed = set()
        
        for i, sample1 in enumerate(samples):
            sample1_id = sample1.get('id', i)
            
            if sample1_id in processed:
                continue
            
            group = [sample1]
            content1 = str(sample1.get('content', '')).lower().strip()
            
            if not content1:
                continue
            
            for j, sample2 in enumerate(samples[i+1:], i+1):
                sample2_id = sample2.get('id', j)
                
                if sample2_id in processed:
                    continue
                
                content2 = str(sample2.get('content', '')).lower().strip()
                
                if not content2:
                    continue
                
                # 检查相似度
                if content1 == content2:
                    group.append(sample2)
                    processed.add(sample2_id)
                elif len(content1) > 50 and len(content2) > 50:
                    # 对于长文本，检查包含关系
                    if content1 in content2 or content2 in content1:
                        group.append(sample2)
                        processed.add(sample2_id)
            
            if len(group) > 1:
                duplicate_groups.append({
                    "similarity": 100,  # 完全匹配或包含
                    "samples": group,
                    "count": len(group)
                })
                for sample in group:
                    processed.add(sample.get('id', samples.index(sample)))
        
        total_duplicates = sum(len(group['samples']) - 1 for group in duplicate_groups)
        
        return {
            "success": True,
            "groups": duplicate_groups,
            "total_duplicates": total_duplicates,
            "total_groups": len(duplicate_groups)
        }
    except Exception as e:
        logger.error(f"检测重复广告样本失败: {e}")
        return {
            "success": False,
            "groups": [],
            "total_duplicates": 0,
            "total_groups": 0,
            "error": str(e)
        }

@router.post(ROUTES.training.ad_samples_deduplicate)
async def deduplicate_ad_samples(request: dict):
    """去重广告样本"""
    try:
        remove_ids = request.get("remove_ids", [])
        
        if not remove_ids:
            return {"success": False, "message": "没有指定要删除的重复样本"}
        
        samples = load_ad_samples()
        
        # 删除指定的样本
        original_count = len(samples)
        samples = [s for s in samples if str(s.get('id')) not in [str(rid) for rid in remove_ids]]
        deleted_count = original_count - len(samples)
        
        if deleted_count > 0:
            if not save_ad_samples(samples):
                raise HTTPException(status_code=500, detail="保存数据失败")
        
        return {
            "success": True,
            "message": f"去重完成，删除了 {deleted_count} 个重复样本",
            "removed_count": deleted_count
        }
    except Exception as e:
        return handle_api_error(e, "去重广告样本")

@router.post(ROUTES.training.mark_ad_test)
async def mark_ad_test(request: dict):
    """标记广告测试"""
    try:
        message_content = request.get("message", "")
        
        if not message_content:
            return {"success": False, "message": "消息内容不能为空"}
        
        # 简单实现：返回标记结果
        return {
            "success": True,
            "message": "标记完成",
            "is_ad": True,
            "confidence": 0.95
        }
    except Exception as e:
        raise handle_api_error(e, "标记广告测试")

@router.post(ROUTES.training.mark_ad_message)
async def mark_ad_message(request: dict):
    """标记/取消标记广告消息并自动调整阈值"""
    try:
        message_id = request.get("message_id")
        is_marking_as_ad = request.get("is_marking_as_ad", True)  # 是否标记为广告
        
        if not message_id:
            return {"success": False, "message": "消息ID不能为空"}
        
        # 获取消息
        from app.storage.redis_store import get_redis_message_store
        redis_store = get_redis_message_store()
        message_data = redis_store.get_message_by_id(message_id)
        
        if not message_data:
            return {"success": False, "message": "未找到消息"}
        
        # 记录阈值反馈
        threshold_adjustment = _record_threshold_feedback(message_data, is_marking_as_ad)
        
        # 更新消息状态
        update_data = {
            'is_ad': is_marking_as_ad,
            'updated_at': datetime.now()
        }
        
        if is_marking_as_ad:
            # 标记为广告时，通常也拒绝消息
            update_data['status'] = 'rejected'
            update_data['reject_reason'] = '用户标记为广告'
        else:
            # 取消广告标记时，恢复为未审核状态
            update_data['status'] = 'pending'
            update_data['reject_reason'] = None
        
        # 拆分完整message_id为channel_id和message_id
        # message_id格式: "-1002062871756:43481"
        parts = message_id.split(":")
        if len(parts) != 2:
            return {"success": False, "message": "消息ID格式错误"}
        
        channel_id = parts[0]
        msg_id = int(parts[1])
        
        # 保存更新
        success = await redis_store.update_message(channel_id, msg_id, update_data)
        if not success:
            return {"success": False, "message": "更新消息失败"}
        
        # 向量学习系统
        if is_marking_as_ad:
            # 学习广告向量
            from app.services.vector_ad_detector import get_vector_ad_detector
            from app.services.filters.base import FilterContext
            
            vector_detector = get_vector_ad_detector()
            content = message_data.get('filtered_content', '')
            
            if content:
                context = FilterContext(
                    message_id=str(message_data.get('message_id', '')),
                    channel_id=message_data.get('source_channel', '')
                )
                success = vector_detector.manual_learn_ad(content, context)
                logger.info(f"✅ 向量学习{'成功' if success else '失败'}: {content[:50]}...")
            else:
                logger.warning("filtered_content为空，跳过向量学习")
        else:
            # 取消广告标记，移除错误向量
            from app.services.vector_manager import vector_manager
            content = message_data.get('filtered_content', '')
            if content:
                removed_count = vector_manager.remove_vector_by_content(content)
                logger.info(f"🗑️ 取消广告标记：从向量库移除 {removed_count} 个向量")
            else:
                logger.warning("filtered_content为空，跳过向量移除")
        
        # 构建响应
        response_data = {
            "success": True,
            "message": "操作完成",
            "auto_rejected": is_marking_as_ad,  # 为了兼容现有前端代码
        }
        
        # 包含阈值调整信息
        if threshold_adjustment:
            response_data["threshold_adjustment"] = threshold_adjustment
        
        return response_data
        
    except Exception as e:
        logger.error(f"标记广告消息失败: {e}")
        raise handle_api_error(e, "标记广告消息")


def _record_threshold_feedback(message_data: dict, is_marking_as_ad: bool):
    """记录阈值反馈并触发自动调整"""
    try:
        from app.core.threshold_manager import ThresholdManager
        
        threshold_manager = ThresholdManager()
        
        # 获取原始AI检测分数（如果有的话）
        # 这里我们需要从消息数据中获取原始的广告检测分数
        # 如果没有保存原始分数，使用当前is_ad状态推算
        original_ad_score = message_data.get('ad_confidence_score', 0.5)
        original_is_ad = message_data.get('is_ad', False)
        
        # 判断这是否是误判情况
        if is_marking_as_ad and not original_is_ad:
            # 用户手动标记为广告，但AI原本判断不是广告 -> False Negative
            actual_result = 'positive'
            feedback_type = "FN: AI误判为正常，用户标记为广告"
        elif not is_marking_as_ad and original_is_ad:
            # 用户取消广告标记，AI原本判断是广告 -> False Positive  
            actual_result = 'negative'
            feedback_type = "FP: AI误判为广告，用户取消标记"
        else:
            # 没有误判，不需要调整
            return None
        
        # 记录反馈到阈值管理器
        threshold_manager.record_feedback(
            filter_name='ad_detector',
            metric_name='classifier',
            predicted_score=original_ad_score,
            actual_result=actual_result
        )
        
        logger.info(f"📊 阈值反馈已记录: {feedback_type}, 分数: {original_ad_score}")
        return feedback_type
        
    except Exception as e:
        logger.error(f"记录阈值反馈失败: {e}")
        return None


# _add_to_training_samples 函数已删除 - 使用向量学习系统替代

@router.post(ROUTES.training.add_ad_sample)
async def add_ad_sample(request: dict):
    """添加广告样本"""
    try:
        content = request.get("content", "")
        channel_id = request.get("channel_id", "manual")
        channel_name = request.get("channel_name", "手动添加")
        is_ad = request.get("is_ad", True)
        
        if not content:
            return {"success": False, "message": "内容不能为空"}
        
        samples = load_ad_samples()
        
        # 生成新的ID
        new_id = generate_sample_id(content)
        
        # 创建新样本
        new_sample = {
            "id": new_id,
            "content": content,
            "channel_id": channel_id,
            "channel_name": channel_name,
            "is_ad": is_ad,
            "confidence_score": 1.0,
            "content_hash": hashlib.md5(content.encode()).hexdigest(),
            "created_by": "manual",
            "created_at": datetime.now().isoformat()
        }
        
        # 检查重复
        for sample in samples:
            if sample.get('content_hash') == new_sample['content_hash']:
                return {"success": False, "message": "广告样本已存在"}
        
        # 添加样本
        samples.append(new_sample)
        if not save_ad_samples(samples):
            raise HTTPException(status_code=500, detail="保存样本失败")
        
        return {"success": True, "message": "广告样本已添加", "id": new_id}
    except Exception as e:
        raise handle_api_error(e, "添加广告样本")

@router.get(ROUTES.training.ad_stats)
async def get_ad_stats():
    """获取广告统计（简化版）"""
    try:
        samples = load_ad_samples()
        
        return {
            "success": True,
            "stats": {
                "totalSamples": len(samples),
                "confirmedAds": len([s for s in samples if s.get('is_ad', False)]),
                "lastUpdate": datetime.now().isoformat()
            }
        }
    except Exception as e:
        raise handle_api_error(e, "获取广告统计")

@router.post(ROUTES.training.ad_samples_reload)
async def reload_ad_samples():
    """重新加载广告样本"""
    try:
        samples = load_ad_samples()
        
        return {
            "success": True,
            "message": "广告样本重新加载完成",
            "sampleCount": len(samples)
        }
    except Exception as e:
        raise handle_api_error(e, "重新加载广告样本")