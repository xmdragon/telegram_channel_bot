"""
广告向量管理模块 - 向量数据的CRUD、统计和处理功能
"""
from fastapi import APIRouter, HTTPException
from datetime import datetime
from typing import List, Dict, Any, Optional
import logging
from pydantic import BaseModel

from .base import handle_api_error, validate_pagination_params
from app.core.route_config import ROUTES

logger = logging.getLogger(__name__)
router = APIRouter(tags=["training-ad-vector"])

class VectorTestRequest(BaseModel):
    content: str

class AddVectorRequest(BaseModel):
    content: str
    source: str = "manual"

@router.get(ROUTES.training.ad_vectors)
async def get_ad_vectors(page: int = 1, page_size: int = 20, search: str = ""):
    """获取广告训练样本列表（分页）"""
    try:
        import json
        import os
        from app.core.path_config import PathConfig
        
        # 读取广告训练数据文件
        ad_training_file = PathConfig.AD_TRAINING_FILE
        
        if not os.path.exists(ad_training_file):
            # 文件不存在，返回空数据
            return {
                "success": True,
                "vectors": [],
                "total": 0,
                "page": page,
                "page_size": page_size,
                "total_pages": 0
            }
        
        # 读取训练数据
        with open(ad_training_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            samples = data.get('samples', [])
        
        # 搜索过滤
        if search:
            search_lower = search.lower()
            samples = [s for s in samples if search_lower in s.get('content', '').lower()]
        
        # 分页处理
        total = len(samples)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        page_samples = samples[start_idx:end_idx]
        
        # 格式化数据供前端使用（适配原有的向量格式）
        formatted_vectors = []
        for sample in page_samples:
            formatted_vectors.append({
                'id': sample.get('message_id', ''),  # 使用message_id作为ID
                'content': sample.get('content', ''),
                'source': sample.get('labeled_by', 'manual'),  # 标记者
                'created_at': sample.get('created_at'),
                'vector_length': len(sample.get('content', '')),  # 使用内容长度代替向量长度
                'metadata': {
                    'sample_id': sample.get('id'),
                    'message_id': sample.get('message_id'),
                    'labeled_by': sample.get('labeled_by')
                }
            })
        
        return {
            "success": True,
            "vectors": formatted_vectors,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size
        }
    except Exception as e:
        logger.error(f"获取广告向量列表失败: {e}")
        return handle_api_error(e, "获取广告向量列表")

@router.get(ROUTES.training.ad_vector_statistics)
async def get_ad_vector_statistics():
    """获取广告训练样本统计信息"""
    try:
        import json
        import os
        from datetime import datetime
        from app.core.path_config import PathConfig
        
        # 读取广告训练数据文件
        ad_training_file = PathConfig.AD_TRAINING_FILE
        
        if not os.path.exists(ad_training_file):
            return {
                "success": True,
                "statistics": {
                    "total_vectors": 0,
                    "source_distribution": {},
                    "similarity_threshold": 0.7,
                    "duplicate_threshold": 0.95,
                    "storage_path": str(ad_training_file),
                    "last_updated": '',
                    "created_at": ''
                }
            }
        
        # 读取训练数据
        with open(ad_training_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            samples = data.get('samples', [])
        
        # 统计标记者分布
        source_distribution = {}
        for sample in samples:
            labeled_by = sample.get('labeled_by', 'unknown')
            source_distribution[labeled_by] = source_distribution.get(labeled_by, 0) + 1
        
        # 获取文件修改时间
        last_modified = datetime.fromtimestamp(os.path.getmtime(ad_training_file)).isoformat()
        
        # 获取最早的样本创建时间
        created_at = ''
        if samples:
            created_at = min(s.get('created_at', '') for s in samples if s.get('created_at'))
        
        return {
            "success": True,
            "statistics": {
                "total_vectors": len(samples),
                "source_distribution": source_distribution,
                "similarity_threshold": 0.7,  # 保留兼容性
                "duplicate_threshold": 0.95,  # 保留兼容性
                "storage_path": str(ad_training_file),
                "last_updated": last_modified,
                "created_at": created_at
            }
        }
    except Exception as e:
        logger.error(f"获取广告向量统计失败: {e}")
        return handle_api_error(e, "获取广告向量统计")

@router.delete(ROUTES.training.ad_vector_by_id)
async def delete_ad_vector(vector_id: str):
    """删除单个广告训练样本"""
    try:
        import json
        import os
        from app.core.path_config import PathConfig
        
        # 读取广告训练数据文件
        ad_training_file = PathConfig.AD_TRAINING_FILE
        
        if not os.path.exists(ad_training_file):
            return {"success": False, "message": "训练数据文件不存在"}
        
        # 读取训练数据
        with open(ad_training_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            samples = data.get('samples', [])
        
        # 查找要删除的样本（vector_id对应message_id）
        sample_to_delete = None
        for sample in samples:
            if sample.get('message_id') == vector_id:
                sample_to_delete = sample
                break
        
        if not sample_to_delete:
            return {"success": False, "message": "训练样本不存在"}
        
        # 删除样本
        samples = [s for s in samples if s.get('message_id') != vector_id]
        
        # 保存数据
        with open(ad_training_file, 'w', encoding='utf-8') as f:
            json.dump({"samples": samples}, f, ensure_ascii=False, indent=2)
        
        logger.info(f"成功删除广告训练样本: {vector_id}")
        return {"success": True, "message": "训练样本删除成功"}
            
    except Exception as e:
        logger.error(f"删除向量失败: {e}")
        return handle_api_error(e, "删除广告向量")

@router.delete(ROUTES.training.ad_vectors_batch)
async def batch_delete_ad_vectors(request: dict):
    """批量删除广告训练样本"""
    try:
        vector_ids = request.get("vector_ids", [])
        
        if not vector_ids:
            return {"success": False, "message": "没有指定要删除的训练样本"}
        
        import json
        import os
        from app.core.path_config import PathConfig
        
        # 读取广告训练数据文件
        ad_training_file = PathConfig.AD_TRAINING_FILE
        
        if not os.path.exists(ad_training_file):
            return {"success": False, "message": "训练数据文件不存在"}
        
        # 读取训练数据
        with open(ad_training_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            samples = data.get('samples', [])
        
        # 删除指定样本（vector_ids对应message_ids）
        original_count = len(samples)
        samples = [s for s in samples if s.get('message_id') not in vector_ids]
        deleted_count = original_count - len(samples)
        
        if deleted_count > 0:
            # 保存数据
            with open(ad_training_file, 'w', encoding='utf-8') as f:
                json.dump({"samples": samples}, f, ensure_ascii=False, indent=2)
        
        logger.info(f"成功删除 {deleted_count} 个训练样本")
        return {
            "success": True,
            "message": f"批量删除完成，删除了 {deleted_count} 个训练样本",
            "deleted_count": deleted_count
        }
    except Exception as e:
        logger.error(f"批量删除向量失败: {e}")
        return handle_api_error(e, "批量删除广告向量")

@router.post(ROUTES.training.ad_vector_test_detection)
async def test_ad_detection(request: VectorTestRequest):
    """测试广告检测（现在基于关键词检测）"""
    try:
        content = request.content.strip()
        
        if not content:
            return {"success": False, "message": "测试内容不能为空"}
        
        from app.services.unified_ad_detector import unified_ad_detector
        
        # 使用统一广告检测器进行检测
        detection_result = unified_ad_detector.detect(content)
        
        return {
            "success": True,
            "is_ad": detection_result.is_ad,
            "confidence": detection_result.confidence,
            "threshold": 0.7,  # 保留兼容性
            "details": {"reason": detection_result.reason} if detection_result.reason else {},
            "test_content": content[:200]  # 返回前200字符
        }
    except Exception as e:
        logger.error(f"测试广告检测失败: {e}")
        return handle_api_error(e, "测试广告检测")

@router.post(ROUTES.training.ad_vector_add_from_text)
async def add_vector_from_text(request: AddVectorRequest):
    """添加广告训练样本"""
    try:
        import json
        import os
        from datetime import datetime
        from app.core.path_config import PathConfig
        
        content = request.content.strip()
        source = request.source
        
        if not content:
            return {"success": False, "message": "内容不能为空"}
        
        # 读取广告训练数据文件
        ad_training_file = PathConfig.AD_TRAINING_FILE
        
        # 读取现有数据
        if os.path.exists(ad_training_file):
            with open(ad_training_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                samples = data.get('samples', [])
        else:
            samples = []
        
        # 创建新样本
        new_sample = {
            "id": len(samples) + 1,
            "message_id": f"manual_{datetime.now().timestamp():.0f}",
            "content": content,
            "labeled_by": source,
            "created_at": datetime.now().isoformat()
        }
        
        samples.append(new_sample)
        
        # 保存数据
        os.makedirs(os.path.dirname(ad_training_file), exist_ok=True)
        with open(ad_training_file, 'w', encoding='utf-8') as f:
            json.dump({"samples": samples}, f, ensure_ascii=False, indent=2)
        
        logger.info(f"添加广告训练样本: {new_sample['message_id']}")
        return {"success": True, "message": "广告训练样本添加成功"}
            
    except Exception as e:
        logger.error(f"从文本添加向量失败: {e}")
        return handle_api_error(e, "添加广告向量")

@router.get(ROUTES.training.ad_vector_stats)
async def get_ad_vector_stats():
    """获取广告训练样本简化统计"""
    try:
        import json
        import os
        from datetime import datetime
        from app.core.path_config import PathConfig
        
        # 读取广告训练数据文件
        ad_training_file = PathConfig.AD_TRAINING_FILE
        
        if not os.path.exists(ad_training_file):
            return {
                "success": True,
                "stats": {
                    "totalVectors": 0,
                    "lastUpdate": datetime.now().isoformat()
                }
            }
        
        # 读取训练数据
        with open(ad_training_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            samples = data.get('samples', [])
        
        # 获取最后更新时间
        last_update = datetime.fromtimestamp(os.path.getmtime(ad_training_file)).isoformat()
        
        return {
            "success": True,
            "stats": {
                "totalVectors": len(samples),
                "lastUpdate": last_update
            }
        }
    except Exception as e:
        logger.error(f"获取向量统计失败: {e}")
        return handle_api_error(e, "获取广告向量统计")