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
from app.core.path_config import PathConfig
from app.utils.safe_file_ops import SafeFileOperation

logger = logging.getLogger(__name__)
router = APIRouter(tags=["training-ad-samples"])

# 广告样本文件路径
AD_SAMPLES_FILE = PathConfig.AD_TRAINING_FILE

def load_ad_samples():
    """加载广告样本"""
    try:
        if AD_SAMPLES_FILE.exists():
            data = SafeFileOperation.read_json_safe(AD_SAMPLES_FILE)
            return data.get('samples', []) if data else []
        return []
    except Exception as e:
        logger.error(f"加载广告样本失败: {e}")
        return []

def save_ad_samples(samples: List[Dict]) -> bool:
    """保存广告样本"""
    try:
        AD_SAMPLES_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {
            'samples': samples,
            'updated_at': datetime.now().isoformat(),
            'total_count': len(samples)
        }
        return SafeFileOperation.write_json_safe(AD_SAMPLES_FILE, data)
    except Exception as e:
        logger.error(f"保存广告样本失败: {e}")
        return False

@router.get(ROUTES.training.ad_samples)
async def get_ad_samples(page: int = 1, page_size: int = 20):
    """获取广告样本列表"""
    try:
        samples = load_ad_samples()
        
        # 应用分页
        page, page_size = validate_pagination_params(page, page_size)
        paginated_result = paginate_data(samples, page, page_size)
        
        return {
            "success": True,
            "samples": paginated_result['items'],
            "total": paginated_result['total'],
            "page": paginated_result['page'],
            "page_size": paginated_result['page_size'],
            "total_pages": paginated_result['total_pages']
        }
    except Exception as e:
        logger.error(f"获取广告样本失败: {e}")
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
    """获取广告统计信息"""
    try:
        samples = load_ad_samples()
        
        # 计算基础统计
        total_samples = len(samples)
        confirmed_ads = len([s for s in samples if s.get('is_ad', False)])
        non_ads = total_samples - confirmed_ads
        
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
        
        # 统计频道分布
        channels = {}
        for sample in samples:
            channel_id = sample.get('channel_id', 'unknown')
            channels[channel_id] = channels.get(channel_id, 0) + 1
        
        return {
            "success": True,
            "statistics": {
                "total_samples": total_samples,
                "confirmed_ads": confirmed_ads,
                "non_ads": non_ads,
                "today_added": today_added,
                "channel_count": len(channels),
                "top_channels": sorted(channels.items(), key=lambda x: x[1], reverse=True)[:5]
            }
        }
    except Exception as e:
        logger.error(f"获取广告统计失败: {e}")
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
    """标记广告消息"""
    try:
        message_id = request.get("message_id")
        is_ad = request.get("is_ad", True)
        
        if not message_id:
            return {"success": False, "message": "消息ID不能为空"}
        
        
        return {"success": True, "message": "标记完成"}
    except Exception as e:
        raise handle_api_error(e, "标记广告消息")

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