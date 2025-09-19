"""
Telegram工具API路由
提供消息结构查看、频道分析等工具功能
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any, List, Optional
import logging
from datetime import datetime
import re

from app.api.admin_auth import get_current_admin
from app.telegram.dual_session_manager import dual_session_manager
# 响应格式化函数
def success_response(data):
    return {"success": True, "data": data}

def error_response(message):
    return {"success": False, "error": message}

router = APIRouter(prefix="/telegram", tags=["telegram-tools"])
logger = logging.getLogger(__name__)


class MessageStructureRequest:
    """消息结构查询请求"""
    def __init__(self, message_url: str):
        self.message_url = message_url


@router.post("/message-structure")
async def get_message_structure(
    request: Dict[str, str],
    current_admin: Dict = Depends(get_current_admin)
):
    """
    获取Telegram消息的完整结构体数据
    支持单条消息和组合消息
    """
    try:
        message_url = request.get('message_url', '').strip()
        if not message_url:
            raise HTTPException(status_code=400, detail="消息URL不能为空")
        
        logger.info(f"获取消息结构: {message_url}")
        
        # 解析消息URL
        parsed_info = parse_message_url(message_url)
        if not parsed_info:
            raise HTTPException(status_code=400, detail="无效的消息URL格式")
        
        # 获取Telegram客户端
        client = await dual_session_manager.get_sender_client()
        if not client:
            raise HTTPException(status_code=503, detail="Telegram客户端未连接")
        
        # 获取消息数据
        message_data = await fetch_message_structure(
            client, 
            parsed_info['channel'], 
            parsed_info['message_id']
        )
        
        return success_response(message_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取消息结构失败: {e}", exc_info=True)
        return error_response(f"获取消息结构失败: {str(e)}")


def parse_message_url(url: str) -> Optional[Dict[str, Any]]:
    """
    解析Telegram消息URL
    支持格式：
    - https://t.me/channel_name/123
    - t.me/channel_name/123
    - https://t.me/c/1234567890/123
    """
    # 清理URL
    url = url.strip()
    if not url.startswith('http'):
        url = 'https://' + url
    
    # 私有频道格式: https://t.me/c/1234567890/123
    private_match = re.match(r'https?://t\.me/c/(-?\d+)/(\d+)', url)
    if private_match:
        channel_id = private_match.group(1)
        message_id = int(private_match.group(2))
        
        # 私有频道ID需要加上-100前缀（如果还没有的话）
        if not channel_id.startswith('-100'):
            channel_id = f"-100{channel_id}"
        
        return {
            'channel': channel_id,
            'message_id': message_id,
            'original_url': url
        }
    
    # 公开频道格式: https://t.me/channel_name/123
    public_match = re.match(r'https?://t\.me/([^/]+)/(\d+)', url)
    if public_match:
        channel = public_match.group(1)
        message_id = int(public_match.group(2))
        
        return {
            'channel': channel,
            'message_id': message_id,
            'original_url': url
        }
    
    return None


async def fetch_message_structure(client, channel: str, message_id: int) -> Dict[str, Any]:
    """
    获取消息的完整结构数据
    """
    try:
        # 获取指定消息
        message = await client.get_messages(channel, ids=message_id)
        
        if not message:
            raise HTTPException(status_code=404, detail="消息不存在或无权访问")
        
        # 检查是否为组合消息
        grouped_messages = []
        
        if hasattr(message, 'grouped_id') and message.grouped_id:
            # 获取组合消息的所有部分
            grouped_messages = await client.get_messages(
                channel, 
                min_id=message_id-10,  # 向前查找
                max_id=message_id+10   # 向后查找  
            )
            
            # 过滤出同组的消息
            grouped_messages = [
                msg for msg in grouped_messages 
                if hasattr(msg, 'grouped_id') and msg.grouped_id == message.grouped_id
            ]
            
            # 按消息ID排序
            grouped_messages.sort(key=lambda x: x.id)
        else:
            grouped_messages = [message]
        
        # 构建基本信息
        channel_entity = await client.get_entity(channel)
        message_info = {
            'message_id': message.id,
            'channel_id': str(channel_entity.id) if hasattr(channel_entity, 'id') else channel,
            'channel_name': getattr(channel_entity, 'username', channel) or channel,
            'channel_title': getattr(channel_entity, 'title', ''),
            'date': message.date.isoformat() if hasattr(message, 'date') and message.date else None,
            'views': getattr(message, 'views', None),
            'forwards': getattr(message, 'forwards', None),
            'is_group_message': len(grouped_messages) > 1,
            'group_size': len(grouped_messages)
        }
        
        # 构建消息结构数据
        structures = []
        for msg in grouped_messages:
            structure = await message_to_structure(msg)
            structures.append(structure)
        
        return {
            'info': message_info,
            'structures': structures,
            'total_messages': len(structures)
        }
        
    except Exception as e:
        logger.error(f"获取消息结构失败: {e}", exc_info=True)
        raise


async def message_to_structure(message) -> Dict[str, Any]:
    """
    将Telegram消息对象转换为结构化数据
    """
    structure = {
        'id': message.id,
        'date': message.date.isoformat() if hasattr(message, 'date') and message.date else None,
        'message': message.message or '',
        'from_id': str(message.from_id) if message.from_id else None,
        'peer_id': str(message.peer_id) if message.peer_id else None,
    }
    
    # 添加基本属性
    basic_attrs = [
        'out', 'mentioned', 'media_unread', 'silent', 'post', 
        'from_scheduled', 'legacy', 'edit_hide', 'pinned', 'noforwards',
        'views', 'forwards', 'replies', 'edit_date', 'post_author',
        'grouped_id', 'restriction_reason', 'ttl_period'
    ]
    
    for attr in basic_attrs:
        if hasattr(message, attr):
            value = getattr(message, attr)
            if value is not None:
                if hasattr(value, 'to_dict'):
                    structure[attr] = value.to_dict()
                elif isinstance(value, datetime):
                    structure[attr] = value.isoformat()
                else:
                    structure[attr] = value
    
    # 处理媒体信息
    if hasattr(message, 'media') and message.media:
        structure['media'] = serialize_media(message.media)
    
    # 处理实体信息（链接、提及等）
    if hasattr(message, 'entities') and message.entities:
        structure['entities'] = [serialize_entity(entity) for entity in message.entities]
    
    # 处理回复信息
    if hasattr(message, 'reply_to') and message.reply_to:
        structure['reply_to'] = serialize_reply_to(message.reply_to)
    
    # 处理转发信息
    if hasattr(message, 'fwd_from') and message.fwd_from:
        structure['fwd_from'] = serialize_forward_info(message.fwd_from)
    
    # 处理按钮/键盘
    if hasattr(message, 'reply_markup') and message.reply_markup:
        structure['reply_markup'] = serialize_reply_markup(message.reply_markup)
    
    return structure


def serialize_media(media) -> Dict[str, Any]:
    """序列化媒体对象"""
    if not media:
        return None
    
    media_data = {
        '_': type(media).__name__
    }
    
    # 基本属性
    if hasattr(media, 'ttl_seconds'):
        media_data['ttl_seconds'] = media.ttl_seconds
    
    # 根据媒体类型处理
    if hasattr(media, 'photo'):
        media_data['photo'] = serialize_photo(media.photo)
    elif hasattr(media, 'document'):
        media_data['document'] = serialize_document(media.document)
    elif hasattr(media, 'webpage'):
        media_data['webpage'] = serialize_webpage(media.webpage)
    
    return media_data


def serialize_photo(photo) -> Dict[str, Any]:
    """序列化照片对象"""
    if not photo:
        return None
    
    return {
        'id': photo.id,
        'access_hash': photo.access_hash,
        'file_reference': photo.file_reference.hex() if hasattr(photo, 'file_reference') else None,
        'date': photo.date.isoformat() if hasattr(photo, 'date') else None,
        'sizes': len(photo.sizes) if hasattr(photo, 'sizes') else 0,
        'has_stickers': getattr(photo, 'has_stickers', False)
    }


def serialize_document(document) -> Dict[str, Any]:
    """序列化文档对象"""
    if not document:
        return None
    
    doc_data = {
        'id': document.id,
        'access_hash': document.access_hash,
        'file_reference': document.file_reference.hex() if hasattr(document, 'file_reference') else None,
        'date': document.date.isoformat() if hasattr(document, 'date') else None,
        'mime_type': getattr(document, 'mime_type', ''),
        'size': getattr(document, 'size', 0),
        'dc_id': getattr(document, 'dc_id', None)
    }
    
    # 处理属性（动画、音频、视频等）
    if hasattr(document, 'attributes') and document.attributes:
        doc_data['attributes'] = []
        for attr in document.attributes:
            attr_data = {'_': type(attr).__name__}
            # 添加常见属性
            common_attrs = ['w', 'h', 'duration', 'file_name', 'performer', 'title']
            for common_attr in common_attrs:
                if hasattr(attr, common_attr):
                    attr_data[common_attr] = getattr(attr, common_attr)
            doc_data['attributes'].append(attr_data)
    
    return doc_data


def serialize_webpage(webpage) -> Dict[str, Any]:
    """序列化网页预览对象"""
    if not webpage:
        return None
    
    return {
        'id': webpage.id,
        'url': getattr(webpage, 'url', ''),
        'display_url': getattr(webpage, 'display_url', ''),
        'hash': getattr(webpage, 'hash', 0),
        'type': getattr(webpage, 'type', ''),
        'site_name': getattr(webpage, 'site_name', ''),
        'title': getattr(webpage, 'title', ''),
        'description': getattr(webpage, 'description', ''),
        'has_photo': hasattr(webpage, 'photo') and webpage.photo is not None,
        'has_document': hasattr(webpage, 'document') and webpage.document is not None
    }


def serialize_entity(entity) -> Dict[str, Any]:
    """序列化消息实体（链接、提及等）"""
    entity_data = {
        '_': type(entity).__name__,
        'offset': entity.offset,
        'length': entity.length
    }
    
    # 添加特定类型的属性
    if hasattr(entity, 'url'):
        entity_data['url'] = entity.url
    if hasattr(entity, 'user_id'):
        entity_data['user_id'] = entity.user_id
    if hasattr(entity, 'language'):
        entity_data['language'] = entity.language
    
    return entity_data


def serialize_reply_to(reply_to) -> Dict[str, Any]:
    """序列化回复信息"""
    if not reply_to:
        return None
    
    return {
        '_': type(reply_to).__name__,
        'reply_to_msg_id': getattr(reply_to, 'reply_to_msg_id', None),
        'reply_to_peer_id': str(reply_to.reply_to_peer_id) if hasattr(reply_to, 'reply_to_peer_id') else None,
        'reply_to_top_id': getattr(reply_to, 'reply_to_top_id', None)
    }


def serialize_forward_info(fwd_from) -> Dict[str, Any]:
    """序列化转发信息"""
    if not fwd_from:
        return None
    
    return {
        'date': fwd_from.date.isoformat() if hasattr(fwd_from, 'date') else None,
        'from_id': str(fwd_from.from_id) if hasattr(fwd_from, 'from_id') else None,
        'from_name': getattr(fwd_from, 'from_name', ''),
        'channel_post': getattr(fwd_from, 'channel_post', None),
        'post_author': getattr(fwd_from, 'post_author', ''),
        'saved_from_peer': str(fwd_from.saved_from_peer) if hasattr(fwd_from, 'saved_from_peer') else None,
        'saved_from_msg_id': getattr(fwd_from, 'saved_from_msg_id', None)
    }


def serialize_reply_markup(reply_markup) -> Dict[str, Any]:
    """序列化回复标记（按钮等）"""
    if not reply_markup:
        return None
    
    markup_data = {
        '_': type(reply_markup).__name__
    }
    
    if hasattr(reply_markup, 'rows'):
        markup_data['rows'] = []
        for row in reply_markup.rows:
            row_data = []
            for button in row.buttons:
                button_data = {
                    '_': type(button).__name__,
                    'text': getattr(button, 'text', '')
                }
                # 添加按钮特定属性
                if hasattr(button, 'url'):
                    button_data['url'] = button.url
                if hasattr(button, 'data'):
                    button_data['data'] = button.data.hex() if button.data else None
                row_data.append(button_data)
            markup_data['rows'].append(row_data)
    
    return markup_data