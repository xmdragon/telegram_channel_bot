"""
消息发布API
支持创建和发布消息到目标频道
"""
import logging
import json
import uuid
import os
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from pydantic import BaseModel

from app.core.route_config import ROUTES
from app.core.path_config import PathConfig
from app.services.config_manager import config_manager

logger = logging.getLogger(__name__)

router = APIRouter()


# ============= 数据模型 =============

class PublishMessageRequest(BaseModel):
    """发布消息请求"""
    content: str
    media_files: List[str] = []  # 媒体文件ID列表
    parse_mode: str = "Markdown"


class PreviewRequest(BaseModel):
    """预览请求"""
    content: str


class MediaFileInfo(BaseModel):
    """媒体文件信息"""
    file_id: str
    file_name: str
    file_size: int
    file_type: str
    preview_url: str


class EmojiCategory(BaseModel):
    """Emoji分类"""
    name: str
    emojis: List[str]


class EmojiListResponse(BaseModel):
    """Emoji列表响应"""
    categories: List[EmojiCategory]
    recent: List[str]
    favorites: List[str]


# ============= API端点 =============

@router.post(ROUTES.publish.send_message)
async def send_message(request: PublishMessageRequest):
    """
    发布消息到目标频道

    Args:
        request: 发布请求，包含内容和媒体文件

    Returns:
        发布结果
    """
    try:
        # 1. 获取频道落款
        signature = await config_manager.get_config('target.signature', '')

        # 2. 组装完整内容（添加落款）
        full_content = request.content
        if signature:
            full_content = f"{request.content}\n\n{signature}"

        # 3. 验证媒体文件数量
        if len(request.media_files) > 10:
            raise HTTPException(status_code=400, detail="媒体文件数量不能超过10个")

        # 4. 构造消息对象（复用转发逻辑）
        from app.telegram.message_forwarder import message_forwarder
        from datetime import datetime
        import uuid

        # 构造符合转发器期望的消息结构
        message_data = {
            'filtered_content': request.content,  # 不包含签名，转发器会自动添加
            'content': request.content,
            'source_channel': 'manual_publish',  # 标记为手动发布
            'message_id': str(uuid.uuid4()),  # 临时ID
            'is_combined': False,
            'media_group_display': None,
            'media_type': None,
            'media_url': None,
            'grouped_id': None,
            'created_at': datetime.now().isoformat()
        }

        # 处理媒体文件
        if request.media_files:
            if len(request.media_files) == 1:
                # 单个媒体
                media_path = Path(PathConfig.TEMP_MEDIA_DIR) / "publish" / request.media_files[0]
                if not media_path.exists():
                    raise HTTPException(status_code=404, detail=f"媒体文件不存在: {request.media_files[0]}")

                # 判断媒体类型
                file_ext = media_path.suffix.lower()
                if file_ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
                    message_data['media_type'] = 'photo'
                elif file_ext in ['.mp4', '.mpeg', '.mov']:
                    message_data['media_type'] = 'video'
                else:
                    message_data['media_type'] = 'document'

                message_data['media_url'] = f"/temp_media/publish/{request.media_files[0]}"
            else:
                # 多媒体组消息
                message_data['is_combined'] = True
                media_group = []
                for file_id in request.media_files:
                    media_path = Path(PathConfig.TEMP_MEDIA_DIR) / "publish" / file_id
                    if not media_path.exists():
                        raise HTTPException(status_code=404, detail=f"媒体文件不存在: {file_id}")

                    file_ext = media_path.suffix.lower()
                    if file_ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
                        media_type = 'photo'
                    elif file_ext in ['.mp4', '.mpeg', '.mov']:
                        media_type = 'video'
                    else:
                        media_type = 'document'

                    media_group.append({
                        'media_url': f"/temp_media/publish/{file_id}",
                        'media_type': media_type
                    })
                message_data['media_group_display'] = media_group

        # 5. 使用转发器发送消息
        try:
            target_info = await message_forwarder.forward_to_target_with_sender_session(message_data)

            if not target_info:
                raise HTTPException(status_code=500, detail="消息发送失败")

            # 提取消息ID
            if isinstance(target_info, dict):
                message_id = target_info.get('target_message_id')
            else:
                message_id = None

            # 6. 返回结果
            return {
                "success": True,
                "message_id": message_id,
                "message": "消息发布成功"
            }
        except Exception as e:
            logger.error(f"发布消息失败: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"发布失败: {str(e)}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"发布消息失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"发布失败: {str(e)}")


@router.post(ROUTES.publish.upload_media)
async def upload_media(file: UploadFile = File(...)):
    """
    上传媒体文件

    Args:
        file: 上传的文件

    Returns:
        文件信息
    """
    try:
        # 1. 验证文件类型
        allowed_types = [
            'image/jpeg', 'image/png', 'image/gif', 'image/webp',
            'video/mp4', 'video/mpeg', 'video/quicktime',
            'application/pdf', 'application/msword'
        ]

        if file.content_type not in allowed_types:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的文件类型: {file.content_type}"
            )

        # 2. 验证文件大小（200MB限制）
        max_size = await config_manager.get_config('collection.max_media_size_mb', '200')
        max_size_bytes = int(max_size) * 1024 * 1024

        # 读取文件内容
        content = await file.read()
        file_size = len(content)

        if file_size > max_size_bytes:
            raise HTTPException(
                status_code=400,
                detail=f"文件大小超过限制: {file_size / 1024 / 1024:.1f}MB > {max_size}MB"
            )

        # 3. 生成唯一文件ID
        file_extension = Path(file.filename).suffix
        file_id = f"{uuid.uuid4()}{file_extension}"

        # 4. 保存到临时目录
        publish_dir = Path(PathConfig.TEMP_MEDIA_DIR) / "publish"
        publish_dir.mkdir(parents=True, exist_ok=True)

        file_path = publish_dir / file_id
        with open(file_path, 'wb') as f:
            f.write(content)

        # 5. 生成预览URL
        preview_url = f"/temp_media/publish/{file_id}"

        # 6. 返回文件信息
        return MediaFileInfo(
            file_id=file_id,
            file_name=file.filename,
            file_size=file_size,
            file_type=file.content_type,
            preview_url=preview_url
        ).dict()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"上传媒体失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"上传失败: {str(e)}")


@router.delete(ROUTES.publish.delete_media)
async def delete_media(file_id: str):
    """
    删除临时媒体文件

    Args:
        file_id: 文件ID

    Returns:
        删除结果
    """
    try:
        file_path = Path(PathConfig.TEMP_MEDIA_DIR) / "publish" / file_id

        if not file_path.exists():
            raise HTTPException(status_code=404, detail="文件不存在")

        file_path.unlink()

        return {
            "success": True,
            "message": "文件删除成功"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除媒体失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"删除失败: {str(e)}")


@router.get(ROUTES.publish.emoji_list)
async def get_emoji_list() -> EmojiListResponse:
    """
    获取常用emoji列表

    Returns:
        Emoji分类列表
    """
    try:
        emoji_file = PathConfig.DATA_DIR / "config" / "emojis.json"

        if not emoji_file.exists():
            raise HTTPException(status_code=404, detail="Emoji配置文件不存在")

        with open(emoji_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        return EmojiListResponse(**data)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取emoji列表失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取失败: {str(e)}")


@router.post(ROUTES.publish.preview)
async def preview_message(request: PreviewRequest):
    """
    预览消息（添加频道落款）

    Args:
        request: 预览请求

    Returns:
        预览内容
    """
    try:
        # 获取频道落款
        signature = await config_manager.get_config('target.signature', '')

        # 组装完整内容
        full_content = request.content
        if signature:
            full_content = f"{request.content}\n\n{signature}"

        return {
            "content": full_content,
            "signature": signature
        }

    except Exception as e:
        logger.error(f"预览消息失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"预览失败: {str(e)}")
