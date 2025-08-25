"""
训练数据管理基础模块 - 共享功能和数据操作
"""
from fastapi import HTTPException
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
import logging
import json
import hashlib
from pathlib import Path

from app.core.path_config import PathConfig
from app.utils.safe_file_ops import SafeFileOperation

logger = logging.getLogger(__name__)

# 文件路径配置
TRAINING_DATA_FILE = PathConfig.MANUAL_TRAINING_FILE
TAIL_FILTER_SAMPLES_FILE = PathConfig.TAIL_FILTER_SAMPLES_FILE
SEPARATOR_PATTERNS_FILE = PathConfig.SEPARATOR_PATTERNS_FILE
PROMO_SAMPLES_FILE = PathConfig.PROMO_SAMPLES_FILE

# 确保目录存在
PathConfig.ensure_directories()

# 简化权限检查以避免循环依赖
def check_permission(permission_name: str):
    """简化的权限检查装饰器"""
    def dependency():
        # 临时简化权限检查，生产环境需要更严格的权限验证
        return {"permission": permission_name, "granted": True}
    return dependency

# Pydantic模型定义
class TrainingSubmission(BaseModel):
    """训练数据提交模型"""
    channel_id: str
    channel_name: str = ""
    original_message: str
    tail_content: str

class TailFilterSample(BaseModel):
    """尾部过滤样本模型"""
    id: Optional[str] = None
    channel_id: str
    channel_name: str = ""
    original_message: str
    tail_content: str
    is_ad: bool = False
    confidence_score: Optional[float] = None
    created_at: Optional[str] = None

class SeparatorPattern(BaseModel):
    """分隔符模式模型"""
    pattern: str
    description: str = ""
    enabled: bool = True

class PromoSample(BaseModel):
    """推广链接样本模型"""
    id: Optional[str] = None
    promo_content: str
    separator_type: Optional[str] = ""
    created_at: Optional[str] = None

class FeedbackData(BaseModel):
    """反馈数据模型"""
    sample_id: str
    is_correct: bool
    user_feedback: str = ""

# 核心数据操作函数
def load_training_data() -> List[Dict]:
    """加载训练数据"""
    try:
        if TRAINING_DATA_FILE.exists():
            data = SafeFileOperation.read_json_safe(TRAINING_DATA_FILE)
            return data.get('samples', []) if data else []
        return []
    except Exception as e:
        logger.error(f"加载训练数据失败: {e}")
        return []

def save_training_data(samples: List[Dict]) -> bool:
    """保存训练数据"""
    try:
        data = {
            'samples': samples,
            'updated_at': datetime.now().isoformat(),
            'total_count': len(samples)
        }
        SafeFileOperation.write_json_safe(TRAINING_DATA_FILE, data)
        return True
    except Exception as e:
        logger.error(f"保存训练数据失败: {e}")
        return False


def load_tail_filter_samples() -> List[Dict]:
    """加载尾部过滤样本"""
    try:
        if TAIL_FILTER_SAMPLES_FILE.exists():
            data = SafeFileOperation.read_json_safe(TAIL_FILTER_SAMPLES_FILE)
            return data.get('samples', []) if data else []
        return []
    except Exception as e:
        logger.error(f"加载尾部过滤样本失败: {e}")
        return []

def save_tail_filter_samples(samples: List[Dict]) -> bool:
    """保存尾部过滤样本"""
    try:
        data = {
            'samples': samples,
            'updated_at': datetime.now().isoformat(),
            'total_count': len(samples)
        }
        SafeFileOperation.write_json_safe(TAIL_FILTER_SAMPLES_FILE, data)
        return True
    except Exception as e:
        logger.error(f"保存尾部过滤样本失败: {e}")
        return False

def load_separator_patterns() -> List[Dict]:
    """加载分隔符模式"""
    try:
        if SEPARATOR_PATTERNS_FILE.exists():
            data = SafeFileOperation.read_json_safe(SEPARATOR_PATTERNS_FILE)
            return data.get('patterns', []) if data else []
        return []
    except Exception as e:
        logger.error(f"加载分隔符模式失败: {e}")
        return []

def save_separator_patterns(patterns: List[Dict]) -> bool:
    """保存分隔符模式"""
    try:
        data = {
            'patterns': patterns,
            'updated_at': datetime.now().isoformat(),
            'total_count': len(patterns)
        }
        SafeFileOperation.write_json_safe(SEPARATOR_PATTERNS_FILE, data)
        return True
    except Exception as e:
        logger.error(f"保存分隔符模式失败: {e}")
        return False

def load_promo_samples() -> List[Dict]:
    """加载推广链接样本"""
    try:
        if PROMO_SAMPLES_FILE.exists():
            data = SafeFileOperation.read_json_safe(PROMO_SAMPLES_FILE)
            return data.get('samples', []) if data else []
        return []
    except Exception as e:
        logger.error(f"加载推广链接样本失败: {e}")
        return []

def save_promo_samples(samples: List[Dict]) -> bool:
    """保存推广链接样本"""
    try:
        data = {
            'samples': samples,
            'updated_at': datetime.now().isoformat(),
            'total_count': len(samples)
        }
        SafeFileOperation.write_json_safe(PROMO_SAMPLES_FILE, data)
        return True
    except Exception as e:
        logger.error(f"保存推广链接样本失败: {e}")
        return False

# 工具函数
def generate_sample_id(content: str) -> str:
    """生成样本ID"""
    return hashlib.md5(f"{content}_{datetime.now().timestamp()}".encode()).hexdigest()[:12]

def validate_sample_data(sample: Dict) -> bool:
    """验证样本数据格式"""
    required_fields = ['channel_id', 'original_message', 'tail_content']
    return all(field in sample and sample[field] for field in required_fields)

def calculate_statistics(samples: List[Dict]) -> Dict[str, Any]:
    """计算基础统计信息"""
    if not samples:
        return {
            'total_count': 0,
            'channel_count': 0,
            'avg_length': 0,
            'recent_count': 0
        }
    
    # 基础统计
    total_count = len(samples)
    channels = set(sample.get('channel_id', '') for sample in samples)
    channel_count = len(channels)
    
    # 平均长度计算
    total_length = sum(len(sample.get('tail_content', '')) for sample in samples)
    avg_length = total_length // total_count if total_count > 0 else 0
    
    # 最近7天的样本数
    recent_date = datetime.now() - timedelta(days=7)
    recent_count = sum(
        1 for sample in samples
        if sample.get('created_at') and 
        datetime.fromisoformat(sample['created_at'].replace('Z', '+00:00')) > recent_date
    )
    
    return {
        'total_count': total_count,
        'channel_count': channel_count,
        'avg_length': avg_length,
        'recent_count': recent_count,
        'channels': list(channels)
    }


# 错误处理工具
def handle_api_error(error: Exception, operation: str) -> HTTPException:
    """统一的API错误处理"""
    logger.error(f"{operation}失败: {error}")
    return HTTPException(
        status_code=500,
        detail=f"{operation}失败: {str(error)}"
    )

def validate_pagination_params(page: int = 1, page_size: int = 20) -> tuple[int, int]:
    """验证分页参数"""
    page = max(1, page)
    page_size = min(max(1, page_size), 100)  # 限制每页最多100条
    return page, page_size

def paginate_data(data: List[Any], page: int, page_size: int) -> Dict[str, Any]:
    """分页数据"""
    total = len(data)
    start = (page - 1) * page_size
    end = start + page_size
    
    return {
        'items': data[start:end],
        'total': total,
        'page': page,
        'page_size': page_size,
        'total_pages': (total + page_size - 1) // page_size
    }