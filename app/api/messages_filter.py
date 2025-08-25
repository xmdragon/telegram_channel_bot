"""
消息过滤API模块
处理尾部过滤、阈值管理、训练数据等功能
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from app.utils.timezone import get_current_time
import logging
import json
import os

from app.storage.redis_store import get_redis_message_store
from app.services.auth_service import get_auth_service
from app.services.message_processor import MessageProcessor
from app.core.route_config import ROUTES

logger = logging.getLogger(__name__)
router = APIRouter()
security = HTTPBearer(auto_error=False)

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

def check_permission(permission_name: str):
    """检查权限装饰器"""
    def decorator(func):
        import functools
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # 这里可以添加具体的权限检查逻辑
            return await func(*args, **kwargs)
        return wrapper
    return decorator

@router.post(ROUTES.messages.filter_content)
@check_permission("filter.execute")
async def filter_message_content(
    message_id: str,
    user: Dict[str, Any] = Depends(require_auth),
    message_processor: MessageProcessor = Depends(get_message_processor)
):
    """
    对单条消息执行内容过滤（包括尾部、推广链接等）
    """
    try:
        # 解析消息ID
        if ':' in message_id:
            channel_id, msg_id = message_id.split(':', 1)
        else:
            raise HTTPException(status_code=400, detail="不支持的消息ID格式")
        
        # 获取消息
        msg_data = await message_processor.get_message(channel_id, int(msg_id))
        if not msg_data:
            raise HTTPException(status_code=404, detail="消息不存在")
        
        # 前端手动过滤时，必须基于当前显示的内容（filtered_content）
        original_content = msg_data.get('filtered_content') or msg_data.get('content')
        
        # 🚀 Linus式修复：移除媒体组标记干扰，让过滤器专注于实际内容
        if '[📎 媒体组' in original_content:
            media_tag_start = original_content.find('[📎 媒体组')
            original_content = original_content[:media_tag_start].rstrip()
        
        if not original_content:
            return {
                "success": False,
                "message": "消息没有内容可以过滤"
            }
        
        # 🚀 Linus式解决方案：使用内容过滤管道（5个内容清理过滤器）
        from app.services.filters.filter_pipeline import FilterPipeline, PipelineConfig
        from app.services.filters.base import FilterContext
        from app.services.filters.tail_filter import TailFilter
        from app.services.filters.footer_promo_filter import FooterPromoFilter
        from app.services.filters.markdown_filter import MarkdownFilter
        from app.services.filters.promo_content_filter import PromoContentFilter
        from app.services.filters.promo_vector_filter import PromoVectorFilter
        
        # 创建内容过滤专用的轻量级管道（不包含检测类过滤器6-8）
        pipeline = FilterPipeline(PipelineConfig(enable_early_stopping=False))
        pipeline.add_filter(TailFilter())           # 1. 尾部过滤
        pipeline.add_filter(FooterPromoFilter())    # 2. 尾部推广链接过滤
        pipeline.add_filter(MarkdownFilter())       # 3. Markdown格式清理
        pipeline.add_filter(PromoContentFilter())   # 4. 推广内容过滤
        pipeline.add_filter(PromoVectorFilter())    # 5. 推广内容向量过滤
        
        # 创建过滤上下文
        filter_context = FilterContext(
            message_id=f"{channel_id}:{msg_id}",
            channel_id=channel_id
        )
        
        # 添加元数据
        has_media = msg_data.get('media_type') in ['photo', 'video', 'document']
        filter_context.add_metadata('is_history', False)
        filter_context.add_metadata('has_media', has_media)
        filter_context.add_metadata('message_obj', msg_data)
        
        # 执行过滤管道
        pipeline_result = await pipeline.process(original_content, filter_context)
        filtered_content = pipeline_result.final_content
        
        # 简单的调试日志
        removed_length = len(original_content) - len(filtered_content)
        logger.info(f"📊 内容过滤结果: 原始{len(original_content)} -> 过滤后{len(filtered_content)} 字符")
        
        if removed_length > 0:
            removed_content = original_content[len(filtered_content):]  # 简单估算移除的内容
            logger.info(f"   移除内容: {removed_content[:100]}{'...' if len(removed_content) > 100 else ''}")
        
        # 更新过滤后的内容
        content_changed = removed_length > 0
        if content_changed:
            redis_store = get_redis_message_store()
            msg_key = f"msg:{channel_id}:{msg_id}"
            update_data = {
                'filtered_content': filtered_content,
                'updated_at': get_current_time().isoformat()
            }
            redis_store.redis.hset(msg_key, mapping=update_data)
            logger.info(f"✂️ 内容过滤完成: 移除 {removed_length} 字符")
        
        return {
            "success": True,
            "filtered_content": filtered_content,
            "removed_length": removed_length,
            "removed_tail": original_content[len(filtered_content):] if removed_length > 0 else "",
            "has_tail": content_changed,  # 兼容原API
            "data": {
                "original_content": original_content,
                "filtered_content": filtered_content,
                "has_tail": content_changed,
                "removed_tail": original_content[len(filtered_content):] if removed_length > 0 else "",
                "filter_details": pipeline_result.filter_results
            },
            "message": f"内容过滤已执行，应用了 {len(pipeline_result.applied_filters)} 个过滤器" if content_changed else "内容无需过滤",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"执行尾部过滤失败: {e}")
        raise HTTPException(status_code=500, detail=f"执行过滤失败: {str(e)}")

@router.post(ROUTES.messages.refilter)
@check_permission("filter.execute")
async def refilter_message(
    message_id: str,
    user: Dict[str, Any] = Depends(require_auth),
    message_processor: MessageProcessor = Depends(get_message_processor)
):
    """
    重新过滤消息（使用所有过滤器）
    """
    try:
        # 解析消息ID
        if ':' in message_id:
            channel_id, msg_id = message_id.split(':', 1)
        else:
            raise HTTPException(status_code=400, detail="不支持的消息ID格式")
        
        # 重新执行完整的过滤流程
        success = await message_processor.refilter_message(channel_id, int(msg_id))
        
        if not success:
            raise HTTPException(status_code=404, detail="消息不存在或重新过滤失败")
        
        return {
            "success": True,
            "message": "消息已重新过滤",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"重新过滤消息失败: {e}")
        raise HTTPException(status_code=500, detail=f"重新过滤失败: {str(e)}")


@router.post(ROUTES.messages.train_tail)
@check_permission("filter.train")
async def train_message_tail(
    message_id: str,
    tail_content: str = Query(..., description="要训练的尾部内容"),
    user: Dict[str, Any] = Depends(require_auth),
    message_processor: MessageProcessor = Depends(get_message_processor)
):
    """
    手动标注消息尾部用于训练
    """
    try:
        # 解析消息ID
        if ':' in message_id:
            channel_id, msg_id = message_id.split(':', 1)
        else:
            raise HTTPException(status_code=400, detail="不支持的消息ID格式")
        
        # 获取消息
        msg_data = await message_processor.get_message(channel_id, int(msg_id))
        if not msg_data:
            raise HTTPException(status_code=404, detail="消息不存在")
        
        # 保存尾部训练数据
        from app.core.path_config import PathConfig
        
        tail_file = str(PathConfig.TAIL_FILTER_SAMPLES_FILE)
        try:
            with open(tail_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                samples = data.get('samples', [])
        except:
            samples = []
        
        # 添加新的训练样本
        new_sample = {
            "id": len(samples) + 1,
            "tail_part": tail_content.strip(),
            "message_id": message_id,
            "labeled_by": user.get('username', 'unknown'),
            "created_at": datetime.now().isoformat()
        }
        samples.append(new_sample)
        
        # 保存数据
        import os
        os.makedirs(os.path.dirname(tail_file), exist_ok=True)
        with open(tail_file, 'w', encoding='utf-8') as f:
            json.dump({"samples": samples}, f, ensure_ascii=False, indent=2)
        
        logger.info(f"尾部训练数据已保存 - 用户: {user.get('username')}, 样本: {len(tail_content)} 字符")
        
        return {
            "success": True,
            "message": "尾部训练数据已保存",
            "data": {
                "sample_id": new_sample["id"],
                "tail_length": len(tail_content),
                "total_samples": len(samples)
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"保存训练数据失败: {e}")
        raise HTTPException(status_code=500, detail=f"保存训练数据失败: {str(e)}")

@router.post(ROUTES.messages.not_ad)
@check_permission("filter.train")
async def mark_not_ad(
    message_id: str,
    user: Dict[str, Any] = Depends(require_auth),
    message_processor: MessageProcessor = Depends(get_message_processor)
):
    """
    标记消息为非广告（用于训练）
    """
    try:
        # 解析消息ID
        if ':' in message_id:
            channel_id, msg_id = message_id.split(':', 1)
        else:
            raise HTTPException(status_code=400, detail="不支持的消息ID格式")
        
        # 执行非广告标记
        success = await message_processor.mark_as_not_ad(channel_id, int(msg_id), user.get('user_id'))
        
        if not success:
            raise HTTPException(status_code=404, detail="消息不存在或标记失败")
        
        return {
            "success": True,
            "message": "消息已标记为非广告",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"标记非广告失败: {e}")
        raise HTTPException(status_code=500, detail=f"标记失败: {str(e)}")

@router.post(ROUTES.messages.feedback)
@check_permission("filter.feedback")
async def submit_filter_feedback(
    message_id: str,
    feedback_type: str = Query(..., description="反馈类型"),
    feedback_content: str = Query(..., description="反馈内容"),
    user: Dict[str, Any] = Depends(require_auth),
    message_processor: MessageProcessor = Depends(get_message_processor)
):
    """
    提交过滤反馈（用于改进过滤算法）
    """
    try:
        # 解析消息ID
        if ':' in message_id:
            channel_id, msg_id = message_id.split(':', 1)
        else:
            raise HTTPException(status_code=400, detail="不支持的消息ID格式")
        
        # 保存反馈数据
        feedback_data = {
            "message_id": message_id,
            "feedback_type": feedback_type,
            "feedback_content": feedback_content,
            "user_id": user.get('user_id'),
            "username": user.get('username'),
            "timestamp": datetime.now().isoformat()
        }
        
        # 这里可以保存到专门的反馈存储系统
        logger.info(f"收到过滤反馈 - 用户: {user.get('username')}, 类型: {feedback_type}")
        
        return {
            "success": True,
            "message": "反馈已提交",
            "data": {
                "feedback_id": f"{message_id}_{datetime.now().timestamp()}",
                "feedback_type": feedback_type
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"提交反馈失败: {e}")
        raise HTTPException(status_code=500, detail=f"提交反馈失败: {str(e)}")