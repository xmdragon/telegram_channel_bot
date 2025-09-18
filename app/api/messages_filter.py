"""
消息过滤API模块
处理尾部过滤、阈值管理、训练数据等功能
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from app.utils.timezone import get_current_time
import logging
import json
import os

from app.storage.redis_manager import redis_manager
from app.services.auth_service import get_auth_service
from app.services.message_processor import MessageProcessor
from app.services.filters.ad_detector import AdDetector
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


@router.post(ROUTES.messages.filter_content)
async def filter_message_content(
    message_id: str,
    user: Dict[str, Any] = Depends(require_auth),
    message_processor: MessageProcessor = Depends(get_message_processor)
):
    """
    对单条消息执行内容过滤（包括尾部、推广链接等）
    """
    try:
        # 标准化消息ID格式 - 与其他API保持一致
        from app.api.messages_crud import _normalize_message_id
        message_id = _normalize_message_id(message_id)

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
        original_content = msg_data.get('filtered_content')
        
        if not original_content:
            return {
                "success": False,
                "message": "消息没有内容可以过滤"
            }
        
        # 使用新的ContentProcessor，不进行广告检测
        from app.services.content_processor import ContentProcessor, LocalMessage

        # 创建处理管道
        pipeline = ContentProcessor()
        
        # 创建LocalMessage对象
        local_message = LocalMessage(
            message_id=int(msg_id),
            channel_id=channel_id,
            content=original_content,
            filtered_content=original_content,
            entities=msg_data.get('entities')
        )
        
        # 执行过滤，不进行广告检测（detect_ad=False）
        processed_message = await pipeline.process(local_message, detect_ad=False)
        
        filtered_content = processed_message.filtered_content
        
        # 简单的调试日志
        removed_length = len(original_content) - len(filtered_content)
        logger.info(f"📊 内容过滤结果: 原始{len(original_content)} -> 过滤后{len(filtered_content)} 字符")
        
        if removed_length > 0:
            removed_content = original_content[len(filtered_content):]  # 简单估算移除的内容
            logger.info(f"   移除内容: {removed_content[:100]}{'...' if len(removed_content) > 100 else ''}")
        
        # 更新过滤后的内容
        content_changed = removed_length > 0
        if content_changed:
            update_data = {
                'filtered_content': filtered_content,
                'updated_at': get_current_time().isoformat()
            }
            success = redis_manager.update_message(channel_id, int(msg_id), update_data)
            if success:
                logger.info(f"✂️ 内容过滤完成: 移除 {removed_length} 字符")
            else:
                logger.error(f"❌ Redis更新失败: {channel_id}:{msg_id}")
        
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
                "filter_reason": processed_message.filter_reason
            },
            "message": f"内容过滤已执行: {processed_message.filter_reason}" if content_changed else "内容无需过滤",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"执行尾部过滤失败: {e}")
        raise HTTPException(status_code=500, detail=f"执行过滤失败: {str(e)}")



@router.post(ROUTES.messages.train_tail)
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
        # 标准化消息ID格式 - 与其他API保持一致
        from app.api.messages_crud import _normalize_message_id
        message_id = _normalize_message_id(message_id)
        
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
        
        # 添加新的训练样本 - 只保留核心字段
        new_sample = {
            "id": len(samples) + 1,
            "tail_part": tail_content.strip(),
            "rules": [],  # 规则可以后续生成
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
async def mark_not_ad(
    message_id: str,  # 参数名必须与路由定义中的{message_id}匹配
    user: Dict[str, Any] = Depends(require_auth),
    message_processor: MessageProcessor = Depends(get_message_processor)
):
    """
    标记消息为非广告（用于训练）
    同时对命中的关键词进行降权操作
    """
    try:
        # 解析消息ID
        if ':' in message_id:
            channel_id, msg_id = message_id.split(':', 1)
        else:
            raise HTTPException(status_code=400, detail="不支持的消息ID格式")
        
        # 获取消息数据
        message = redis_manager.get_message(channel_id, int(msg_id))
        if not message:
            raise HTTPException(status_code=404, detail="消息不存在")
        
        # 🎯 使用统一的AdDetector处理负面反馈
        decreased_keywords = []
        deleted_keywords = []
        
        # 获取消息的关键词详情，优先从新字段获取
        matched_keywords = []
        if message.get('ad_keywords_detail'):
            # 新格式：从ad_keywords_detail获取
            matched_keywords = [k['keyword'] for k in message.get('ad_keywords_detail', {}).get('matched_keywords', [])]
        elif message.get('hit_keywords'):
            # 旧格式：从hit_keywords获取
            matched_keywords = [kw.get('keyword') for kw in message.get('hit_keywords', []) if kw.get('keyword')]
        
        if matched_keywords:
            ad_detector = AdDetector()

            # 使用AdDetector的负面反馈处理
            success = ad_detector.handle_negative_feedback(matched_keywords)
            if success:
                logger.info(f"AdDetector负面反馈处理完成: 关键词={matched_keywords}")
            else:
                logger.error("AdDetector负面反馈处理失败")
        else:
            logger.info("消息无匹配关键词，跳过负面反馈处理")
        
        # 更新消息状态
        update_data = {
            'is_ad': 'False',  # 清除广告标记
            'ad_weight': 0,
            'hit_keywords': None,  # 清除命中的关键词
            'status': 'pending',  # 改为待审核
            'updated_at': get_current_time().isoformat()
        }
        
        success = redis_manager.update_message(channel_id, int(msg_id), update_data)
        
        if not success:
            raise HTTPException(status_code=500, detail="更新消息状态失败")
        
        # 更新统计数据
        from app.storage.message_stats_store import get_message_stats_store
        stats_store = get_message_stats_store()
        stats_store.increment_pending()
        if message.get('status') == 'rejected':
            stats_store.decrement_rejected()
        
        return {
            "success": True,
            "message": "消息已标记为非广告，关键词已降权",
            "data": {
                "matched_keywords": matched_keywords,
                "feedback_processed": len(matched_keywords) > 0
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"标记非广告失败: {e}")
        raise HTTPException(status_code=500, detail=f"标记失败: {str(e)}")

@router.post(ROUTES.messages.feedback)
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

@router.post(ROUTES.messages.extract_ad_keywords)
async def extract_ad_keywords(
    id: str,
    user: Dict[str, Any] = Depends(require_auth)
):
    """
    从消息中提取广告关键词
    """
    try:
        # 解析消息ID
        if ':' in id:
            channel_id, msg_id = id.split(':', 1)
        else:
            raise HTTPException(status_code=400, detail="不支持的消息ID格式")
        
        # 获取消息内容
        message = redis_manager.get_message(channel_id, int(msg_id))
        if not message:
            raise HTTPException(status_code=404, detail="消息不存在")
        
        content = message.get('content', '')
        if not content:
            return {
                "success": True,
                "data": {
                    "keywords": [],
                    "message": "消息内容为空"
                }
            }
        
        # 使用关键词提取器
        from app.services.keyword_extractor import get_keyword_extractor
        extractor = get_keyword_extractor()
        
        # 提取建议的关键词（简化版本）
        suggested_keywords = extractor.suggest_keywords(content)
        
        # 格式化返回数据
        keywords = [
            {
                "keyword": keyword,
                "weight": 1.0,  # 简化版本：统一权重
                "is_new": True  # 标记为新关键词
            }
            for keyword in suggested_keywords
        ]
        
        return {
            "success": True,
            "data": {
                "keywords": keywords,
                "total": len(keywords)
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"提取关键词失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"提取关键词失败: {str(e)}")

@router.post(ROUTES.messages.mark_as_ad)
async def mark_as_ad(
    id: str,
    keywords: Dict[str, float] = Body(..., embed=True),
    user: Dict[str, Any] = Depends(require_auth),
    message_processor: MessageProcessor = Depends(get_message_processor)
):
    """
    标记消息为广告并保存关键词
    """
    try:
        # 解析消息ID
        if ':' in id:
            channel_id, msg_id = id.split(':', 1)
        else:
            raise HTTPException(status_code=400, detail="不支持的消息ID格式")

        # 🎯 使用统一的AdDetector处理正面反馈
        if keywords:
            from app.services.filters.ad_detector import AdDetector
            ad_detector = AdDetector()

            # 过滤掉权重小于等于0的关键词
            float_keywords = {k: v for k, v in keywords.items() if k and v > 0}

            # 使用AdDetector的正面反馈处理
            success = ad_detector.handle_positive_feedback(float_keywords)
            if success:
                logger.info(f"AdDetector正面反馈处理完成: 添加了 {len(float_keywords)} 个新关键词")
            else:
                logger.error("AdDetector正面反馈处理失败")
        else:
            logger.info("无新关键词需要添加")
        
        # 更新消息状态为拒绝
        success = await message_processor.update_message_status(
            channel_id, int(msg_id), 'rejected', user.get('username')
        )
        
        if not success:
            raise HTTPException(status_code=500, detail="更新消息状态失败")
        
        # 记录广告样本
        logger.info(f"消息 {id} 被标记为广告，添加了 {len(keywords)} 个关键词")
        
        return {
            "success": True,
            "message": "已标记为广告并保存关键词",
            "data": {
                "message_id": id,
                "keywords_added": len(keywords),
                "status": "rejected"
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"标记广告失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"标记广告失败: {str(e)}")