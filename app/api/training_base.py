"""
训练数据管理API模块
处理广告标记、训练样本管理等功能
"""
from fastapi import APIRouter, Depends, HTTPException, Body
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from pydantic import BaseModel
import logging
import json
import os

from app.storage.redis_manager import redis_manager
from app.services.auth_service import get_auth_service
from app.services.message_processor import MessageProcessor
from app.core.path_config import PathConfig
from app.core.route_config import ROUTES

logger = logging.getLogger(__name__)
router = APIRouter()
security = HTTPBearer(auto_error=False)

class MarkAdRequest(BaseModel):
    """广告标记请求模型"""
    message_id: str
    is_marking_as_ad: bool = True

# 依赖注入辅助函数
def get_message_processor() -> MessageProcessor:
    return MessageProcessor()

# 认证中间件
async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[Dict[str, Any]]:
    """获取当前用户"""
    if not credentials:
        return None
    
    try:
        auth_service = get_auth_service()
        return await auth_service.get_current_user(credentials.credentials)
    except Exception as e:
        logger.error(f"获取当前用户失败: {e}")
        return None

async def require_auth(user: Optional[Dict[str, Any]] = Depends(get_current_user)) -> Dict[str, Any]:
    """要求用户认证"""
    if not user:
        raise HTTPException(status_code=401, detail="未授权访问")
    return user

@router.post(ROUTES.training.mark_ad_message)
async def mark_ad_message(
    request: MarkAdRequest,
    user: Dict[str, Any] = Depends(require_auth),
    message_processor: MessageProcessor = Depends(get_message_processor)
):
    """
    标记或取消标记消息为广告
    支持双向操作：标记为广告或取消广告标记
    """
    try:
        message_id = request.message_id
        is_marking_as_ad = request.is_marking_as_ad
        
        # 解析消息ID
        if ':' in message_id:
            channel_id, msg_id = message_id.split(':', 1)
        else:
            raise HTTPException(status_code=400, detail="不支持的消息ID格式")
        
        # 获取消息
        msg_data = await message_processor.get_message(channel_id, int(msg_id))
        if not msg_data:
            raise HTTPException(status_code=404, detail="消息不存在")
        
        # 获取当前广告状态
        current_is_ad = msg_data.get('is_ad', False)
        
        # 根据操作更新状态
        if is_marking_as_ad and not current_is_ad:
            # 标记为广告
            msg_data['is_ad'] = True
            msg_data['status'] = 'rejected'
            msg_data['rejection_reason'] = '手动标记为广告'
            auto_rejected = True
            action = "标记为广告"
            
            # 添加到广告训练样本
            await add_ad_training_sample(msg_data, user)
            
        elif not is_marking_as_ad and current_is_ad:
            # 取消广告标记
            msg_data['is_ad'] = False
            msg_data['status'] = 'pending'
            msg_data['rejection_reason'] = None
            auto_rejected = False
            action = "取消广告标记"
            
            # 从广告训练样本中移除
            await remove_ad_training_sample(message_id)
            
        else:
            # 状态未改变
            return {
                "success": False,
                "message": f"消息已经是{'广告' if current_is_ad else '非广告'}状态"
            }
        
        # 初始化 redis_store
        if message_processor.redis_store is None:
            from app.storage.redis_manager import redis_manager
            message_processor.redis_store = redis_manager
        
        # 准备更新数据
        update_data = {
            'is_ad': str(msg_data.get('is_ad', False)),  # 转换为字符串以保持一致性
            'rejection_reason': msg_data.get('rejection_reason')
        }
        
        # 先更新is_ad和rejection_reason字段
        success = message_processor.redis_store.update_message(channel_id, int(msg_id), update_data)
        
        # 然后更新状态（这会同时更新状态索引）
        if success:
            full_message_id = f"{channel_id}:{msg_id}"
            success = message_processor.redis_store.update_message_status(
                full_message_id, 
                msg_data['status'], 
                user.get('username')
            )
        if not success:
            raise HTTPException(status_code=500, detail="更新消息失败")
        
        # 动态阈值调整（如果启用）
        threshold_adjustment = None
        try:
            from app.core.ai_config import get_ai_config
            ai_config = get_ai_config()
            if ai_config.is_ai_enabled():
                # 这里可以添加阈值调整逻辑
                threshold_adjustment = "阈值已自动优化"
        except:
            pass
        
        logger.info(f"消息 {message_id} {action} - 用户: {user.get('username')}")
        
        return {
            "success": True,
            "message": f"消息已{action}",
            "auto_rejected": auto_rejected,
            "threshold_adjustment": threshold_adjustment,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"广告标记失败: {e}")
        raise HTTPException(status_code=500, detail=f"广告标记失败: {str(e)}")

async def add_ad_training_sample(msg_data: Dict[str, Any], user: Dict[str, Any]):
    """添加广告训练样本"""
    try:
        # 获取广告样本文件路径
        ad_samples_file = str(PathConfig.AD_TRAINING_FILE)
        
        # 读取现有样本
        try:
            with open(ad_samples_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                samples = data.get('samples', [])
        except:
            samples = []
        
        # 检查是否已存在
        message_id = f"{msg_data.get('source_channel')}:{msg_data.get('message_id')}"
        if any(s.get('message_id') == message_id for s in samples):
            return  # 已存在，不重复添加
        
        # 添加新样本
        new_sample = {
            "id": len(samples) + 1,
            "message_id": message_id,
            "content": msg_data.get('content', ''),
            "labeled_by": user.get('username', 'unknown'),
            "created_at": datetime.now().isoformat()
        }
        samples.append(new_sample)
        
        # 保存数据
        os.makedirs(os.path.dirname(ad_samples_file), exist_ok=True)
        with open(ad_samples_file, 'w', encoding='utf-8') as f:
            json.dump({"samples": samples}, f, ensure_ascii=False, indent=2)
            
        logger.info(f"广告训练样本已添加: {message_id}")
        
    except Exception as e:
        logger.error(f"添加广告训练样本失败: {e}")

async def remove_ad_training_sample(message_id: str):
    """移除广告训练样本"""
    try:
        # 获取广告样本文件路径
        ad_samples_file = str(PathConfig.AD_TRAINING_FILE)
        
        # 读取现有样本
        try:
            with open(ad_samples_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                samples = data.get('samples', [])
        except:
            return  # 文件不存在，无需移除
        
        # 移除样本
        original_count = len(samples)
        samples = [s for s in samples if s.get('message_id') != message_id]
        
        if len(samples) < original_count:
            # 保存更新后的数据
            with open(ad_samples_file, 'w', encoding='utf-8') as f:
                json.dump({"samples": samples}, f, ensure_ascii=False, indent=2)
            logger.info(f"广告训练样本已移除: {message_id}")
            
    except Exception as e:
        logger.error(f"移除广告训练样本失败: {e}")

# 其他训练相关的API端点可以在这里添加
@router.get(ROUTES.training.ad_samples)
async def get_ad_samples(
    page: int = 1,
    page_size: int = 20,
    user: Dict[str, Any] = Depends(require_auth)
):
    """获取广告训练样本列表"""
    try:
        ad_samples_file = str(PathConfig.AD_TRAINING_FILE)
        
        # 读取样本数据
        try:
            with open(ad_samples_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                samples = data.get('samples', [])
        except:
            samples = []
        
        # 分页处理
        total = len(samples)
        start = (page - 1) * page_size
        end = start + page_size
        page_samples = samples[start:end]
        
        return {
            "success": True,
            "data": {
                "samples": page_samples,
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": (total + page_size - 1) // page_size
            }
        }
        
    except Exception as e:
        logger.error(f"获取广告样本失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取广告样本失败: {str(e)}")

@router.get(ROUTES.training.stats)
async def get_training_stats(
    user: Dict[str, Any] = Depends(require_auth)
):
    """获取训练统计信息"""
    try:
        stats = {
            "ad_samples": 0,
            "tail_samples": 0,
            "promo_samples": 0
        }
        
        # 统计广告样本
        try:
            ad_samples_file = str(PathConfig.AD_TRAINING_FILE)
            with open(ad_samples_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                stats["ad_samples"] = len(data.get('samples', []))
        except:
            pass
        
        # 统计尾部样本
        try:
            tail_samples_file = str(PathConfig.TAIL_FILTER_SAMPLES_FILE)
            with open(tail_samples_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                stats["tail_samples"] = len(data.get('samples', []))
        except:
            pass
        
        # 统计推广样本
        try:
            promo_samples_file = str(PathConfig.PROMO_SAMPLES_FILE)
            with open(promo_samples_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                stats["promo_samples"] = len(data.get('samples', []))
        except:
            pass
        
        return {
            "success": True,
            "data": stats
        }
        
    except Exception as e:
        logger.error(f"获取训练统计失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取训练统计失败: {str(e)}")