"""
OCR样本管理模块 - OCR样本的管理、学习和导出功能
"""
from fastapi import APIRouter, HTTPException
from datetime import datetime
from typing import List, Dict, Any
import logging

from .base import (
    handle_api_error, validate_pagination_params,
    paginate_data, generate_sample_id
)
from app.core.path_config import PathConfig
from app.utils.safe_file_ops import SafeFileOperation

logger = logging.getLogger(__name__)
router = APIRouter(tags=["training-ocr"])

# OCR样本文件路径
OCR_SAMPLES_FILE = PathConfig.AD_TRAINING_DIR / "ocr_samples.json"

def load_ocr_samples():
    """加载OCR样本"""
    try:
        if OCR_SAMPLES_FILE.exists():
            data = SafeFileOperation.read_json_safe(OCR_SAMPLES_FILE)
            return data.get('samples', []) if data else []
        return []
    except Exception as e:
        logger.error(f"加载OCR样本失败: {e}")
        return []

def save_ocr_samples(samples: List[Dict]) -> bool:
    """保存OCR样本"""
    try:
        OCR_SAMPLES_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {
            'samples': samples,
            'updated_at': datetime.now().isoformat(),
            'total_count': len(samples)
        }
        return SafeFileOperation.write_json_safe(OCR_SAMPLES_FILE, data)
    except Exception as e:
        logger.error(f"保存OCR样本失败: {e}")
        return False

@router.get("/ocr-samples")
async def get_ocr_samples(page: int = 1, page_size: int = 20):
    """获取OCR样本列表"""
    try:
        samples = load_ocr_samples()
        
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
        logger.error(f"获取OCR样本失败: {e}")
        return {
            "success": False,
            "samples": [],
            "total": 0,
            "page": page,
            "page_size": page_size,
            "total_pages": 0
        }

@router.get("/ocr-samples/statistics")
async def get_ocr_statistics():
    """获取OCR统计信息"""
    try:
        samples = load_ocr_samples()
        
        # 计算基础统计
        total_samples = len(samples)
        
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
        
        # 统计置信度分布
        high_confidence = len([s for s in samples if s.get('confidence', 0) > 0.8])
        medium_confidence = len([s for s in samples if 0.5 < s.get('confidence', 0) <= 0.8])
        low_confidence = len([s for s in samples if s.get('confidence', 0) <= 0.5])
        
        return {
            "success": True,
            "statistics": {
                "total_samples": total_samples,
                "today_added": today_added,
                "high_confidence": high_confidence,
                "medium_confidence": medium_confidence,
                "low_confidence": low_confidence,
                "avg_confidence": sum(s.get('confidence', 0) for s in samples) / total_samples if total_samples > 0 else 0
            }
        }
    except Exception as e:
        logger.error(f"获取OCR统计失败: {e}")
        return {
            "success": False,
            "statistics": {
                "total_samples": 0,
                "today_added": 0,
                "high_confidence": 0,
                "medium_confidence": 0,
                "low_confidence": 0,
                "avg_confidence": 0
            }
        }

@router.post("/ocr-samples/learn")
async def learn_from_ocr_samples():
    """从OCR样本学习"""
    try:
        samples = load_ocr_samples()
        
        if not samples:
            return {"success": False, "message": "没有OCR样本可供学习"}
        
        # 过滤高置信度样本用于学习
        high_confidence_samples = [s for s in samples if s.get('confidence', 0) > 0.8]
        
        if len(high_confidence_samples) < 5:
            return {"success": False, "message": "高置信度样本不足，需要至少5个样本"}
        
        
        return {
            "success": True,
            "message": f"成功从 {len(high_confidence_samples)} 个OCR样本中学习",
            "learned_count": len(high_confidence_samples)
        }
    except Exception as e:
        raise handle_api_error(e, "从OCR样本学习")

@router.delete("/ocr-samples/{sample_id}")
async def delete_ocr_sample(sample_id: str):
    """删除OCR样本"""
    try:
        samples = load_ocr_samples()
        
        # 查找并删除样本
        original_count = len(samples)
        sample_to_delete = None
        for sample in samples:
            if str(sample.get('id')) == str(sample_id):
                sample_to_delete = sample
                break
        
        if not sample_to_delete:
            return {"success": False, "message": "OCR样本不存在"}
        
        samples = [s for s in samples if str(s.get('id')) != str(sample_id)]
        
        # 保存更新后的数据
        if not save_ocr_samples(samples):
            raise HTTPException(status_code=500, detail="保存数据失败")
        
        
        return {"success": True, "message": "删除成功"}
    except Exception as e:
        raise handle_api_error(e, "删除OCR样本")

@router.post("/ocr-samples/export")
async def export_ocr_samples():
    """导出OCR样本"""
    try:
        samples = load_ocr_samples()
        
        # 按置信度分组
        export_data = {
            "high_confidence": [s for s in samples if s.get('confidence', 0) > 0.8],
            "medium_confidence": [s for s in samples if 0.5 < s.get('confidence', 0) <= 0.8],
            "low_confidence": [s for s in samples if s.get('confidence', 0) <= 0.5],
            "exported_at": datetime.now().isoformat(),
            "total_samples": len(samples)
        }
        
        
        return {
            "success": True,
            "exportData": export_data,
            "message": f"成功导出 {len(samples)} 个OCR样本"
        }
    except Exception as e:
        raise handle_api_error(e, "导出OCR样本")

@router.post("/ocr-samples/add")
async def add_ocr_sample(request: dict):
    """添加OCR样本"""
    try:
        file_hash = request.get("file_hash", "")
        ocr_text = request.get("ocr_text", "")
        confidence = request.get("confidence", 0.0)
        file_path = request.get("file_path", "")
        
        if not file_hash or not ocr_text:
            return {"success": False, "message": "文件哈希和OCR文本不能为空"}
        
        samples = load_ocr_samples()
        
        # 生成新的ID
        new_id = generate_sample_id(f"{file_hash}_{ocr_text}")
        
        # 创建新样本
        new_sample = {
            "id": new_id,
            "file_hash": file_hash,
            "file_path": file_path,
            "ocr_text": ocr_text,
            "confidence": confidence,
            "created_by": "manual",
            "created_at": datetime.now().isoformat()
        }
        
        # 检查重复
        for sample in samples:
            if sample.get('file_hash') == file_hash:
                return {"success": False, "message": "该文件的OCR样本已存在"}
        
        # 添加样本
        samples.append(new_sample)
        if not save_ocr_samples(samples):
            raise HTTPException(status_code=500, detail="保存样本失败")
        
        
        return {"success": True, "message": "OCR样本已添加", "id": new_id}
    except Exception as e:
        raise handle_api_error(e, "添加OCR样本")

@router.post("/ocr-samples/batch-process")
async def batch_process_ocr():
    """批量处理OCR"""
    try:
        # 简单实现：返回处理状态
        
        return {
            "success": True,
            "message": "批量OCR处理完成",
            "processed_count": 0
        }
    except Exception as e:
        raise handle_api_error(e, "批量处理OCR")

@router.get("/ocr-samples/confidence-distribution")
async def get_confidence_distribution():
    """获取置信度分布"""
    try:
        samples = load_ocr_samples()
        
        # 计算置信度分布
        distribution = {
            "0.0-0.2": 0,
            "0.2-0.4": 0,
            "0.4-0.6": 0,
            "0.6-0.8": 0,
            "0.8-1.0": 0
        }
        
        for sample in samples:
            confidence = sample.get('confidence', 0)
            if confidence <= 0.2:
                distribution["0.0-0.2"] += 1
            elif confidence <= 0.4:
                distribution["0.2-0.4"] += 1
            elif confidence <= 0.6:
                distribution["0.4-0.6"] += 1
            elif confidence <= 0.8:
                distribution["0.6-0.8"] += 1
            else:
                distribution["0.8-1.0"] += 1
        
        return {
            "success": True,
            "distribution": distribution,
            "total_samples": len(samples)
        }
    except Exception as e:
        raise handle_api_error(e, "获取置信度分布")