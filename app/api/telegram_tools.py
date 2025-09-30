"""
Telegram工具API端点
"""
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional, Dict, Any
from pydantic import BaseModel
import logging
import time
import hashlib

from app.core.route_config import ROUTES
from app.services.auth_service import get_auth_service
from app.telegram.dual_session_manager import TelegramDualSessionManager

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/telegram",
    tags=["telegram-tools"]
)
security = HTTPBearer(auto_error=False)

# 消息缓存，避免重复请求Telegram API
# 缓存结构: {url_hash: (message_data, timestamp)}
message_cache = {}
CACHE_TTL = 30  # 缓存30秒
TELEGRAM_TIMEOUT = 30  # Telegram API超时30秒

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


def _extract_message_text(msg) -> str:
    """
    增强的文本提取函数 - 确保不遗漏任何文本内容

    Args:
        msg: Telegram消息对象

    Returns:
        提取的文本内容
    """
    # 按优先级提取文本内容，与采集器保持一致
    text_sources = [
        ('message', getattr(msg, 'message', None)),
        ('text', getattr(msg, 'text', None)),
        ('raw_text', getattr(msg, 'raw_text', None)),
        ('caption', getattr(msg, 'caption', None))
    ]

    for source_name, text_value in text_sources:
        if text_value and text_value.strip():
            logger.debug(f"从 {source_name} 字段提取文本: {len(text_value)} 字符")
            return text_value.strip()

    return ""


async def _get_complete_group_messages(client, channel_username: str, center_message_id: int, target_grouped_id) -> list:
    """
    智能获取组合消息的所有部分 - 动态范围扩展

    Args:
        client: Telegram客户端
        channel_username: 频道用户名
        center_message_id: 中心消息ID
        target_grouped_id: 目标组ID

    Returns:
        完整的组消息列表
    """
    import asyncio

    logger.info(f"开始智能获取组消息: 中心ID={center_message_id}, 组ID={target_grouped_id}")

    grouped_messages = []
    max_range = 15  # 最大扩展范围 ±15
    initial_range = 5  # 初始范围 ±5

    try:
        # 第一步：获取初始范围的消息
        current_range = initial_range
        message_ids = list(range(center_message_id - current_range, center_message_id + current_range + 1))

        logger.debug(f"第一次获取消息范围: {center_message_id - current_range} 到 {center_message_id + current_range}")

        try:
            messages = await asyncio.wait_for(
                client.get_messages(channel_username, ids=message_ids),
                timeout=TELEGRAM_TIMEOUT
            )
        except asyncio.TimeoutError:
            logger.warning(f"获取组合消息超时({TELEGRAM_TIMEOUT}秒)，使用更小范围重试")
            # 超时时使用更小范围重试
            smaller_range = 3
            message_ids = list(range(center_message_id - smaller_range, center_message_id + smaller_range + 1))
            messages = await client.get_messages(channel_username, ids=message_ids)

        # 过滤出属于目标组的消息
        initial_grouped = [
            msg for msg in messages
            if msg and hasattr(msg, 'grouped_id') and msg.grouped_id == target_grouped_id
        ]

        if not initial_grouped:
            logger.warning(f"初始范围内未找到组消息，直接返回空列表")
            return []

        grouped_messages.extend(initial_grouped)
        logger.info(f"初始范围找到 {len(initial_grouped)} 条组消息")

        # 第二步：检查是否需要向左扩展
        leftmost_id = min(msg.id for msg in initial_grouped)
        if leftmost_id == center_message_id - current_range and current_range < max_range:
            logger.debug(f"检测到需要向左扩展，当前最左ID: {leftmost_id}")

            # 向左扩展查找
            extend_range = min(5, max_range - current_range)
            left_message_ids = list(range(leftmost_id - extend_range, leftmost_id))

            try:
                left_messages = await asyncio.wait_for(
                    client.get_messages(channel_username, ids=left_message_ids),
                    timeout=TELEGRAM_TIMEOUT // 2  # 使用较短超时
                )

                left_grouped = [
                    msg for msg in left_messages
                    if msg and hasattr(msg, 'grouped_id') and msg.grouped_id == target_grouped_id
                ]

                if left_grouped:
                    grouped_messages.extend(left_grouped)
                    logger.info(f"向左扩展找到 {len(left_grouped)} 条组消息")

            except (asyncio.TimeoutError, Exception) as e:
                logger.warning(f"向左扩展失败: {e}")

        # 第三步：检查是否需要向右扩展
        rightmost_id = max(msg.id for msg in grouped_messages)
        if rightmost_id == center_message_id + current_range and current_range < max_range:
            logger.debug(f"检测到需要向右扩展，当前最右ID: {rightmost_id}")

            # 向右扩展查找
            extend_range = min(5, max_range - current_range)
            right_message_ids = list(range(rightmost_id + 1, rightmost_id + extend_range + 1))

            try:
                right_messages = await asyncio.wait_for(
                    client.get_messages(channel_username, ids=right_message_ids),
                    timeout=TELEGRAM_TIMEOUT // 2  # 使用较短超时
                )

                right_grouped = [
                    msg for msg in right_messages
                    if msg and hasattr(msg, 'grouped_id') and msg.grouped_id == target_grouped_id
                ]

                if right_grouped:
                    grouped_messages.extend(right_grouped)
                    logger.info(f"向右扩展找到 {len(right_grouped)} 条组消息")

            except (asyncio.TimeoutError, Exception) as e:
                logger.warning(f"向右扩展失败: {e}")

        # 去重并按ID排序
        unique_messages = {}
        for msg in grouped_messages:
            unique_messages[msg.id] = msg

        final_messages = sorted(unique_messages.values(), key=lambda x: x.id)

        logger.info(f"智能获取组消息完成: 总计 {len(final_messages)} 条，ID范围: {final_messages[0].id if final_messages else 'N/A'} - {final_messages[-1].id if final_messages else 'N/A'}")

        return final_messages

    except Exception as e:
        logger.error(f"智能获取组消息失败: {e}")
        # 失败时返回空列表，让上层处理
        return []


async def fetch_message_from_url(message_url: str) -> Dict[str, Any]:
    """
    从Telegram URL获取消息（带5分钟缓存）

    Args:
        message_url: 消息URL，格式如 https://t.me/channel_name/message_id

    Returns:
        消息结构数据
    """
    import re
    import asyncio

    # 生成缓存键
    url_hash = hashlib.md5(message_url.encode()).hexdigest()
    current_time = time.time()

    # 检查缓存
    if url_hash in message_cache:
        cached_data, cached_time = message_cache[url_hash]
        if current_time - cached_time < CACHE_TTL:
            logger.info(f"从缓存返回消息: {message_url} (剩余TTL: {CACHE_TTL - (current_time - cached_time):.1f}秒)")
            return cached_data
        else:
            # 缓存过期，删除
            del message_cache[url_hash]

    # 清理过期缓存
    expired_keys = [k for k, (_, t) in message_cache.items() if current_time - t >= CACHE_TTL]
    for key in expired_keys:
        del message_cache[key]

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
        # 获取消息（添加超时控制和异常处理）
        try:
            message = await asyncio.wait_for(
                client.get_messages(channel_username, ids=message_id),
                timeout=TELEGRAM_TIMEOUT
            )
        except asyncio.TimeoutError:
            logger.warning(f"获取消息超时({TELEGRAM_TIMEOUT}秒): {message_url}")
            raise RuntimeError(f"获取消息超时，请稍后重试")
        except Exception as e:
            if "429" in str(e) or "Too Many Requests" in str(e):
                logger.warning(f"遇到速率限制(429)，请稍后重试")
                raise RuntimeError("Telegram API速率限制，请稍后重试")
            raise

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
            # 智能获取组合消息的所有部分 - 动态范围扩展
            grouped_messages = await _get_complete_group_messages(
                client, channel_username, message_id, message.grouped_id
            )

            for msg in grouped_messages:
                # 增强文本提取逻辑 - 确保不遗漏任何文本内容
                msg_text = _extract_message_text(msg)

                # 构建媒体信息
                media_info = None
                if msg.media:
                    media_info = {
                        'type': msg.media.__class__.__name__,
                        'has_content': bool(msg_text.strip())  # 标记是否包含文本
                    }

                message_data['structures'].append({
                    'message_id': msg.id,
                    'message': msg_text,
                    'media': media_info
                })

                # 调试日志：记录文本提取情况
                if msg_text.strip():
                    logger.debug(f"组消息 {msg.id} 提取到文本: {len(msg_text)} 字符")
                elif msg.media:
                    logger.debug(f"组消息 {msg.id} 纯媒体消息: {media_info['type']}")
                else:
                    logger.debug(f"组消息 {msg.id} 空消息")
        else:
            # 单个消息 - 使用增强的文本提取
            msg_text = _extract_message_text(message)

            # 构建媒体信息
            media_info = None
            if message.media:
                media_info = {
                    'type': message.media.__class__.__name__,
                    'has_content': bool(msg_text.strip())
                }

            message_data['structures'].append({
                'message_id': message.id,
                'message': msg_text,
                'media': media_info
            })

            # 调试日志
            if msg_text.strip():
                logger.debug(f"单个消息 {message.id} 提取到文本: {len(msg_text)} 字符")
            elif message.media:
                logger.debug(f"单个消息 {message.id} 纯媒体消息: {media_info['type']}")
            else:
                logger.debug(f"单个消息 {message.id} 空消息")

        # 兼容旧格式
        if len(message_data['structures']) == 1:
            # 单消息模式，直接添加message字段
            message_data['message'] = message_data['structures'][0]['message']

        # 添加到缓存
        message_cache[url_hash] = (message_data, current_time)
        logger.info(f"消息已缓存: {message_url} (TTL: {CACHE_TTL}秒)")

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

        # 智能获取消息内容 - 改进合并逻辑
        message_content = ""
        text_parts = []

        if message_data.get('structures'):
            # 组合消息：收集所有非空文本内容
            for msg_struct in message_data['structures']:
                text = msg_struct.get('message', '').strip()
                if text:
                    text_parts.append(text)
                    logger.debug(f"收集组消息文本: 消息ID={msg_struct.get('message_id')}, 长度={len(text)}")

            # 用换行符连接所有文本
            if text_parts:
                message_content = '\n'.join(text_parts)
                logger.info(f"组消息文本合并完成: {len(text_parts)} 个文本片段，总长度 {len(message_content)} 字符")
            else:
                logger.info("组消息中未找到任何文本内容")

        elif message_data.get('message'):
            # 单个消息（兼容旧格式）
            message_content = message_data['message'].strip()
            if message_content:
                logger.info(f"单个消息文本: 长度 {len(message_content)} 字符")

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

    # 执行过滤处理 - 使用与生产环境完全相同的方法（只执行一次）
    processed_message = await content_processor.process(
        test_message,
        config_manager=None,  # 测试时不需要配置管理器
        detect_ad=True,
        filter_config=filter_config
    )

    # 直接使用 process() 返回的详细信息，不再重新执行过滤器
    original_length = len(original_content)
    final_length = len(processed_message.filtered_content)
    total_removed = original_length - final_length
    removal_percentage = (total_removed / original_length * 100) if original_length > 0 else 0

    filter_results = {
        'is_ad': processed_message.is_ad,
        'final_content': processed_message.filtered_content,
        'original_content': original_content,
        'total_removed_length': total_removed,
        'removal_percentage': removal_percentage,
        'filters': processed_message.filter_details,  # 直接使用收集的详细信息
        'filter_reason': processed_message.filter_reason or "",
        'early_stopped': False,  # ContentProcessor 不使用早期停止
        'processing_time_ms': 0  # 暂不计算处理时间
    }

    logger.info(f"过滤完成: {len(original_content)} -> {len(processed_message.filtered_content)} 字符")

    return filter_results