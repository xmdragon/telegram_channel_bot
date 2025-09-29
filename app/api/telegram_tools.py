"""
Telegram工具API端点
"""
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional, Dict, Any
from pydantic import BaseModel
import logging

from app.core.route_config import ROUTES
from app.services.auth_service import get_auth_service
from app.telegram.dual_session_manager import TelegramDualSessionManager

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/telegram",
    tags=["telegram-tools"]
)
security = HTTPBearer(auto_error=False)

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

# 请求模型
class MessageAnalyzeRequest(BaseModel):
    """消息分析请求"""
    message_url: str


async def fetch_message_from_url(message_url: str) -> Dict[str, Any]:
    """
    从Telegram URL获取消息

    Args:
        message_url: 消息URL，格式如 https://t.me/channel_name/message_id

    Returns:
        消息结构数据
    """
    import re

    # 解析URL
    pattern = r"(?:https?://)?t\.me/([^/]+)/(\d+)"
    match = re.match(pattern, message_url.strip())

    if not match:
        raise ValueError(f"无效的Telegram消息URL: {message_url}")

    channel_username = match.group(1)
    message_id = int(match.group(2))

    logger.info(f"解析消息URL: 频道={channel_username}, 消息ID={message_id}")

    # 获取Telegram客户端
    session_manager = TelegramDualSessionManager()
    client = await session_manager.get_sender_client()

    if not client:
        raise RuntimeError("无法连接到Telegram")

    try:
        # 获取消息
        message = await client.get_messages(channel_username, ids=message_id)

        if not message:
            raise ValueError(f"无法找到消息: {channel_username}/{message_id}")

        # 转换为结构化数据
        message_data = {
            'info': {
                'message_id': message.id,
                'channel_name': channel_username,
                'channel_id': message.chat_id if hasattr(message, 'chat_id') else None,
                'date': message.date.timestamp() if message.date else None,
                'views': message.views if hasattr(message, 'views') else None,
                'forwards': message.forwards if hasattr(message, 'forwards') else None,
                'is_group_message': bool(message.grouped_id) if hasattr(message, 'grouped_id') else False
            },
            'structures': []
        }

        # 检查是否为组合消息
        if hasattr(message, 'grouped_id') and message.grouped_id:
            # 获取组合消息的所有部分
            # 使用列表而不是range
            message_ids = list(range(message_id - 10, message_id + 11))
            messages = await client.get_messages(
                channel_username,
                ids=message_ids
            )
            grouped_messages = [
                msg for msg in messages
                if msg and hasattr(msg, 'grouped_id') and msg.grouped_id == message.grouped_id
            ]

            for msg in grouped_messages:
                # 使用与采集器完全相同的文本提取方法
                # 采集器使用: message.message or ""
                msg_text = ""
                if hasattr(msg, 'message') and msg.message:
                    msg_text = msg.message
                elif hasattr(msg, 'text') and msg.text:
                    msg_text = msg.text
                elif hasattr(msg, 'raw_text') and msg.raw_text:
                    msg_text = msg.raw_text
                elif hasattr(msg, 'caption') and msg.caption:
                    msg_text = msg.caption

                message_data['structures'].append({
                    'message_id': msg.id,
                    'message': msg_text or "",
                    'media': {'type': msg.media.__class__.__name__} if msg.media else None
                })
        else:
            # 单个消息
            # 使用与采集器完全相同的文本提取方法
            # 采集器使用: message.message or ""
            msg_text = ""
            if hasattr(message, 'message') and message.message:
                msg_text = message.message
            elif hasattr(message, 'text') and message.text:
                msg_text = message.text
            elif hasattr(message, 'raw_text') and message.raw_text:
                msg_text = message.raw_text
            elif hasattr(message, 'caption') and message.caption:
                msg_text = message.caption

            message_data['structures'].append({
                'message_id': message.id,
                'message': msg_text or "",
                'media': {'type': message.media.__class__.__name__} if message.media else None
            })

        # 兼容旧格式
        if len(message_data['structures']) == 1:
            # 单消息模式，直接添加message字段
            message_data['message'] = message_data['structures'][0]['message']

        return message_data

    except Exception as e:
        logger.error(f"获取消息失败: {e}")
        raise


# API端点
@router.post(ROUTES.TelegramTools.analyze_message)
async def analyze_message(
    request: MessageAnalyzeRequest,
    user: Dict[str, Any] = Depends(require_auth)
):
    """
    分析Telegram消息 - 获取结构并测试过滤检测

    合并了原来的两个端点：
    - 获取消息结构
    - 测试过滤检测
    """
    try:
        # 获取消息数据
        message_data = await fetch_message_from_url(request.message_url)

        if not message_data:
            raise HTTPException(status_code=404, detail="无法获取消息数据")

        # 获取消息内容
        message_content = ""
        if message_data.get('structures'):
            # 如果是组合消息，合并所有消息的内容
            for msg_struct in message_data['structures']:
                if msg_struct.get('message'):
                    message_content += msg_struct['message'] + "\n"
        elif message_data.get('message'):
            # 单个消息
            message_content = message_data['message']

        # 准备响应数据
        result = {
            'structure': message_data,
            'filters': None,
            'has_content': bool(message_content.strip())
        }

        # 如果有内容，执行过滤测试
        if message_content.strip():
            filter_results = await test_message_filters(message_content.strip())
            result['filters'] = filter_results

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"分析消息失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"分析消息失败: {str(e)}")


async def test_message_filters(content: str) -> Dict[str, Any]:
    """
    测试所有过滤器对消息内容的处理

    使用与生产环境完全相同的 ContentProcessor.process() 方法进行过滤测试
    """
    logger.info(f"测试过滤器: 内容长度={len(content)}")

    from app.services.content_processor import ContentProcessor, LocalMessage

    # 创建与生产环境相同的 ContentProcessor 实例
    content_processor = ContentProcessor()

    # 创建测试用的 LocalMessage 对象
    test_message = LocalMessage(
        message_id='test_message',
        channel_id='test_channel',
        content=content,
        filtered_content=content,
        entities=[]  # 暂时不包含实体信息
    )

    # 使用与生产环境完全相同的过滤逻辑
    # 启用所有过滤器，这与采集器的默认配置一致
    filter_config = {
        'enabled': True,
        'tail_filter': True,
        'separator_filter': True,
        'text_filter': True,
        'markdown_filter': True,
        'ad_detector': True  # 启用广告检测以获得完整测试结果
    }

    original_content = content

    # 执行过滤处理 - 使用与生产环境完全相同的方法
    processed_message = await content_processor.process(
        test_message,
        config_manager=None,  # 测试时不需要配置管理器
        detect_ad=True,
        filter_config=filter_config
    )

    # 构建详细的过滤结果 - 模拟 analyze_with_details 的输出格式
    filter_results = await _build_detailed_filter_results(
        content_processor,
        original_content,
        processed_message,
        filter_config
    )

    logger.info(f"过滤完成: {len(original_content)} -> {len(processed_message.filtered_content)} 字符")

    return filter_results


async def _build_detailed_filter_results(
    content_processor: 'ContentProcessor',
    original_content: str,
    processed_message: 'LocalMessage',
    filter_config: Dict[str, bool]
) -> Dict[str, Any]:
    """
    构建详细的过滤结果，模拟 UnifiedFilterEngine.analyze_with_details 的输出格式
    通过逐步执行每个过滤器来获取详细信息
    """
    from app.services.content_processor import LocalMessage

    filter_details = []
    current_content = original_content
    original_length = len(original_content)

    # 1. 尾部过滤
    if filter_config.get('tail_filter', True):
        try:
            filtered_content, is_filtered, removed_tail, _ = content_processor.tail_filter.filter(current_content)

            filter_info = {
                'name': '尾部过滤',
                'enabled': True,
                'filtered_content': filtered_content,
                'removed_length': len(removed_tail) if is_filtered else 0,
                'description': f"移除尾部内容: {removed_tail[:50]}..." if is_filtered and removed_tail else "未检测到尾部内容"
            }

            if is_filtered:
                current_content = filtered_content

            filter_details.append(filter_info)
        except Exception as e:
            filter_details.append({
                'name': '尾部过滤',
                'enabled': True,
                'error': str(e),
                'description': f"过滤器执行失败: {e}"
            })

    # 2. 分隔符过滤
    if filter_config.get('separator_filter', True):
        try:
            filtered_content, separator_stats = content_processor.separator_filter.filter_content(current_content)
            removed_blocks = separator_stats.get('removed_blocks_count', 0)

            filter_info = {
                'name': '分隔符过滤',
                'enabled': True,
                'filtered_content': filtered_content,
                'removed_length': len(current_content) - len(filtered_content),
                'description': f"移除{removed_blocks}个内容块" if removed_blocks > 0 else "未检测到需要过滤的分隔符内容"
            }

            if removed_blocks > 0:
                current_content = filtered_content

            filter_details.append(filter_info)
        except Exception as e:
            filter_details.append({
                'name': '分隔符过滤',
                'enabled': True,
                'error': str(e),
                'description': f"过滤器执行失败: {e}"
            })

    # 3. 文本过滤
    if filter_config.get('text_filter', True):
        try:
            filtered_content, is_filtered, matched_keywords = content_processor.text_filter.filter(current_content)

            filter_info = {
                'name': '文本过滤',
                'enabled': True,
                'filtered_content': filtered_content,
                'removed_length': len(current_content) - len(filtered_content) if is_filtered else 0,
                'matched_keywords': [{'keyword': kw} for kw in matched_keywords] if matched_keywords else [],
                'description': f"匹配{len(matched_keywords)}个关键词" if is_filtered and matched_keywords else "未检测到需要过滤的文本内容"
            }

            if is_filtered:
                current_content = filtered_content

            filter_details.append(filter_info)
        except Exception as e:
            filter_details.append({
                'name': '文本过滤',
                'enabled': True,
                'error': str(e),
                'description': f"过滤器执行失败: {e}"
            })

    # 4. Markdown过滤
    if filter_config.get('markdown_filter', True):
        try:
            # 由于测试时entities为空，这里模拟处理
            filtered_content, links_removed = content_processor.markdown_filter.filter(current_content, [])

            filter_info = {
                'name': 'Markdown过滤',
                'enabled': True,
                'filtered_content': filtered_content,
                'removed_length': len(current_content) - len(filtered_content),
                'description': f"移除{links_removed}个链接" if links_removed > 0 else "无需处理Markdown"
            }

            if links_removed > 0:
                current_content = filtered_content

            filter_details.append(filter_info)
        except Exception as e:
            filter_details.append({
                'name': 'Markdown过滤',
                'enabled': True,
                'error': str(e),
                'description': f"过滤器执行失败: {e}"
            })

    # 5. 广告检测
    if filter_config.get('ad_detector', True):
        try:
            is_ad, total_weight, matched_keywords = content_processor.ad_detector.detect(current_content)

            filter_info = {
                'name': '广告检测',
                'enabled': True,
                'is_ad': is_ad,
                'total_score': total_weight,
                'threshold': content_processor.ad_detector.threshold,
                'confidence': total_weight / content_processor.ad_detector.threshold if content_processor.ad_detector.threshold > 0 else 0,
                'matched_keywords': matched_keywords if is_ad else [],
                'description': f"检测为广告，得分: {total_weight}/{content_processor.ad_detector.threshold}" if is_ad else "未检测为广告"
            }

            filter_details.append(filter_info)
        except Exception as e:
            filter_details.append({
                'name': '广告检测',
                'enabled': True,
                'error': str(e),
                'description': f"广告检测失败: {e}"
            })

    # 计算总体统计
    final_content = processed_message.filtered_content
    total_removed = original_length - len(final_content)
    removal_percentage = (total_removed / original_length * 100) if original_length > 0 else 0

    return {
        'is_ad': processed_message.is_ad,
        'final_content': final_content,
        'original_content': original_content,
        'total_removed_length': total_removed,
        'removal_percentage': removal_percentage,
        'filters': filter_details,
        'filter_reason': processed_message.filter_reason or "",
        'early_stopped': False,  # ContentProcessor 不使用早期停止
        'processing_time_ms': 0  # 暂不计算处理时间
    }