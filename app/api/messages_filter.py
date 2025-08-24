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

@router.post(ROUTES.messages.filter_tail)
@check_permission("filter.execute")
async def filter_message_tail(
    message_id: str,
    user: Dict[str, Any] = Depends(require_auth),
    message_processor: MessageProcessor = Depends(get_message_processor)
):
    """
    对单条消息执行尾部过滤
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
        
        # 获取原始内容（如果没有原始内容，使用当前内容）
        original_content = msg_data.get('content') or msg_data.get('filtered_content')
        
        if not original_content:
            return {
                "success": False,
                "message": "消息没有内容可以过滤"
            }
        
        # 执行尾部过滤 - 使用新的FilterPipeline架构
        from app.services.filters.tail_filter import TailFilter
        from app.services.filters.base import FilterContext
        
        # 创建过滤器上下文
        context = FilterContext(
            message_id=int(msg_id),
            channel_id=int(channel_id),
            timestamp=datetime.now().timestamp(),
            message_type=msg_data.get('media_type', 'text')
        )
        
        # 添加元数据
        context.add_metadata('is_history', False)
        context.add_metadata('message_obj', msg_data)
        
        # 初始化尾部过滤器
        tail_filter = TailFilter({
            'intelligent_threshold': 0.6,
            'semantic_threshold': 0.45,  # 稍微降低阈值以提高检测敏感度
            'enable_intelligent': True,
            'enable_semantic': True
        })
        
        # 执行过滤
        filter_result = await tail_filter.filter(original_content, context)
        
        # 提取结果
        filtered_content = filter_result.filtered_content
        has_tail = not filter_result.passed or len(filtered_content) < len(original_content)
        removed_tail = filter_result.details.get('removed_tail', '')
        
        # 如果没有移除内容，计算移除的部分
        if not removed_tail and has_tail:
            removed_tail = original_content[len(filtered_content):].strip()
        
        # 添加调试日志
        logger.info(f"📊 过滤结果统计:")
        logger.info(f"   原始长度: {len(original_content)} 字符")
        logger.info(f"   过滤后长度: {len(filtered_content)} 字符") 
        logger.info(f"   移除长度: {len(original_content) - len(filtered_content)} 字符")
        logger.info(f"   有尾部: {has_tail}")
        logger.info(f"   过滤器结果: passed={filter_result.passed}")
        
        if removed_tail:
            logger.info(f"   移除内容: {removed_tail[:100]}{'...' if len(removed_tail) > 100 else ''}")
        
        # 更新过滤后的内容
        if has_tail:
            redis_store = get_redis_message_store()
            msg_key = f"msg:{channel_id}:{msg_id}"
            update_data = {
                'filtered_content': filtered_content,
                'updated_at': get_current_time().isoformat()
            }
            redis_store.redis.hset(msg_key, mapping=update_data)
            
            # Linus风格：移除不必要的I/O操作 - 手动过滤只需要过滤，不需要保存训练数据
            # 训练数据应该从实时和历史采集中收集，而不是每次手动过滤都写文件
            if removed_tail:
                logger.info(f"✂️ 尾部过滤完成: 移除 {len(removed_tail)} 字符")
        
        return {
            "success": True,
            "filtered_content": filtered_content,
            "removed_length": len(original_content) - len(filtered_content) if has_tail else 0,
            "removed_tail": removed_tail,
            "has_tail": has_tail,
            "data": {
                "original_content": original_content,
                "filtered_content": filtered_content,
                "has_tail": has_tail,
                "removed_tail": removed_tail,
                "filter_details": filter_result.details
            },
            "message": "尾部过滤已执行" if has_tail else "未检测到尾部内容",
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