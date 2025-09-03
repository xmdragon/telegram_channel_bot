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
    """获取广告向量列表（分页）"""
    try:
        from app.services.vector_manager import vector_manager
        
        # 加载向量数据
        data = vector_manager._load_vectors()
        vectors = data.get('vectors', [])
        
        # 搜索过滤
        if search:
            search_lower = search.lower()
            vectors = [v for v in vectors if search_lower in v.get('content', '').lower()]
        
        # 分页处理
        total = len(vectors)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        page_vectors = vectors[start_idx:end_idx]
        
        # 格式化向量数据供前端使用
        formatted_vectors = []
        for vector in page_vectors:
            formatted_vectors.append({
                'id': vector.get('id'),
                'content': vector.get('content', ''),
                'source': vector.get('source', ''),
                'created_at': vector.get('created_at'),
                'vector_length': len(vector.get('vector', [])),
                'metadata': vector.get('metadata', {})
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
    """获取广告向量统计信息"""
    try:
        from app.services.vector_manager import vector_manager
        
        # 获取向量统计
        stats = vector_manager.get_stats()
        
        return {
            "success": True,
            "statistics": {
                "total_vectors": stats.get('total_vectors', 0),
                "source_distribution": stats.get('source_distribution', {}),
                "similarity_threshold": stats.get('similarity_threshold', 0.7),
                "duplicate_threshold": stats.get('duplicate_threshold', 0.95),
                "storage_path": stats.get('storage_path', ''),
                "last_updated": stats.get('last_updated', ''),
                "created_at": stats.get('created_at', '')
            }
        }
    except Exception as e:
        logger.error(f"获取广告向量统计失败: {e}")
        return handle_api_error(e, "获取广告向量统计")

@router.delete(ROUTES.training.ad_vector_by_id)
async def delete_ad_vector(vector_id: str):
    """删除单个广告向量"""
    try:
        from app.services.vector_manager import vector_manager
        
        # 加载向量数据
        data = vector_manager._load_vectors()
        vectors = data.get('vectors', [])
        
        # 查找要删除的向量
        vector_to_delete = None
        for vector in vectors:
            if vector.get('id') == vector_id:
                vector_to_delete = vector
                break
        
        if not vector_to_delete:
            return {"success": False, "message": "向量不存在"}
        
        # 删除向量
        vectors = [v for v in vectors if v.get('id') != vector_id]
        data['vectors'] = vectors
        
        # 保存数据
        if vector_manager._save_vectors(data):
            logger.info(f"成功删除向量: {vector_id}")
            return {"success": True, "message": "向量删除成功"}
        else:
            raise HTTPException(status_code=500, detail="保存数据失败")
            
    except Exception as e:
        logger.error(f"删除向量失败: {e}")
        return handle_api_error(e, "删除广告向量")

@router.delete(ROUTES.training.ad_vectors_batch)
async def batch_delete_ad_vectors(request: dict):
    """批量删除广告向量"""
    try:
        vector_ids = request.get("vector_ids", [])
        
        if not vector_ids:
            return {"success": False, "message": "没有指定要删除的向量"}
        
        from app.services.vector_manager import vector_manager
        
        # 加载向量数据
        data = vector_manager._load_vectors()
        vectors = data.get('vectors', [])
        
        # 删除指定向量
        original_count = len(vectors)
        vectors = [v for v in vectors if v.get('id') not in vector_ids]
        deleted_count = original_count - len(vectors)
        
        if deleted_count > 0:
            data['vectors'] = vectors
            if not vector_manager._save_vectors(data):
                raise HTTPException(status_code=500, detail="保存数据失败")
        
        return {
            "success": True,
            "message": f"批量删除完成，删除了 {deleted_count} 个向量",
            "deleted_count": deleted_count
        }
    except Exception as e:
        logger.error(f"批量删除向量失败: {e}")
        return handle_api_error(e, "批量删除广告向量")

@router.post(ROUTES.training.ad_vector_test_detection)
async def test_ad_detection(request: VectorTestRequest):
    """测试广告检测"""
    try:
        content = request.content.strip()
        
        if not content:
            return {"success": False, "message": "测试内容不能为空"}
        
        from app.services.vector_manager import vector_manager
        from app.services.semantic_extractor import get_semantic_extractor
        
        # 提取向量
        semantic_extractor = get_semantic_extractor(768)
        test_vector = semantic_extractor.extract_vector(content)
        
        if not test_vector:
            return {
                "success": False, 
                "message": "无法提取文本向量",
                "is_ad": False,
                "confidence": 0.0
            }
        
        # 进行广告检测
        is_ad, confidence, details = vector_manager.is_advertisement(test_vector)
        
        return {
            "success": True,
            "is_ad": is_ad,
            "confidence": float(confidence),
            "threshold": vector_manager.similarity_threshold,
            "details": details,
            "test_content": content[:200]  # 返回前200字符
        }
    except Exception as e:
        logger.error(f"测试广告检测失败: {e}")
        return handle_api_error(e, "测试广告检测")

@router.post(ROUTES.training.ad_vector_add_from_text)
async def add_vector_from_text(request: AddVectorRequest):
    """从文本添加广告向量"""
    try:
        content = request.content.strip()
        source = request.source
        
        if not content:
            return {"success": False, "message": "内容不能为空"}
        
        from app.services.vector_manager import vector_manager
        from app.services.semantic_extractor import get_semantic_extractor
        
        # 提取向量
        semantic_extractor = get_semantic_extractor(768)
        vector = semantic_extractor.extract_vector(content)
        
        if not vector:
            return {"success": False, "message": "无法从文本提取向量"}
        
        # 添加向量
        success = vector_manager.add_vector(
            vector=vector,
            content=content,
            source=source,
            metadata={"added_manually": True}
        )
        
        if success:
            return {"success": True, "message": "向量添加成功"}
        else:
            return {"success": False, "message": "向量已存在或添加失败"}
            
    except Exception as e:
        logger.error(f"从文本添加向量失败: {e}")
        return handle_api_error(e, "添加广告向量")

@router.get(ROUTES.training.ad_vector_stats)
async def get_ad_vector_stats():
    """获取广告向量简化统计"""
    try:
        from app.services.vector_manager import vector_manager
        
        stats = vector_manager.get_stats()
        
        return {
            "success": True,
            "stats": {
                "totalVectors": stats.get('total_vectors', 0),
                "lastUpdate": stats.get('last_updated', datetime.now().isoformat())
            }
        }
    except Exception as e:
        logger.error(f"获取向量统计失败: {e}")
        return handle_api_error(e, "获取广告向量统计")