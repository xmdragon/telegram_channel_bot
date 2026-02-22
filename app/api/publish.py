"""
消息发布API
支持创建和发布消息到目标频道
"""
import logging
import json
import uuid
import os
import re
from pathlib import Path
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from pydantic import BaseModel

from app.core.route_config import ROUTES
from app.core.path_config import PathConfig
from app.services.config_manager import config_manager
from app.api.deps import require_auth

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
async def send_message(request: PublishMessageRequest, user: Dict[str, Any] = Depends(require_auth)):
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
                        'file_path': f"/temp_media/publish/{file_id}",
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

            # 6. 清理临时媒体文件
            if request.media_files:
                publish_dir = Path(PathConfig.TEMP_MEDIA_DIR) / "publish"
                for file_id in request.media_files:
                    try:
                        file_path = publish_dir / file_id
                        if file_path.exists():
                            file_path.unlink()
                            logger.debug(f"发布成功，已清理临时媒体: {file_id}")
                    except Exception as e:
                        logger.warning(f"清理临时媒体文件失败 {file_id}: {e}")

            # 7. 返回结果
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
async def upload_media(file: UploadFile = File(...), user: Dict[str, Any] = Depends(require_auth)):
    """
    上传媒体文件

    Args:
        file: 上传的文件

    Returns:
        文件信息
    """
    try:
        # 1. Validate file extension whitelist
        ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.mp4', '.mov', '.avi', '.pdf', '.doc', '.docx'}
        file_extension = Path(file.filename).suffix.lower()
        if file_extension not in ALLOWED_EXTENSIONS:
            raise HTTPException(status_code=400, detail=f"不支持的文件类型: {file_extension}")

        # 2. 验证MIME类型
        allowed_types = [
            'image/jpeg', 'image/png', 'image/gif', 'image/webp',
            'video/mp4', 'video/mpeg', 'video/quicktime',
            'application/pdf', 'application/msword',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        ]

        if file.content_type not in allowed_types:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的文件类型: {file.content_type}"
            )

        # 3. Stream-check file size
        max_size_mb = int(await config_manager.get_config('collection.max_media_size_mb', '200'))
        max_size_bytes = max_size_mb * 1024 * 1024

        chunks = []
        total_size = 0
        while chunk := await file.read(1024 * 1024):  # 1MB chunks
            total_size += len(chunk)
            if total_size > max_size_bytes:
                raise HTTPException(status_code=413, detail=f"文件大小超过限制: {max_size_mb}MB")
            chunks.append(chunk)
        content = b''.join(chunks)
        file_size = total_size

        # 4. 生成唯一文件ID
        file_id = f"{uuid.uuid4()}{file_extension}"

        # 5. 保存到临时目录
        publish_dir = Path(PathConfig.TEMP_MEDIA_DIR) / "publish"
        publish_dir.mkdir(parents=True, exist_ok=True)

        file_path = publish_dir / file_id
        with open(file_path, 'wb') as f:
            f.write(content)

        # 6. 生成预览URL
        preview_url = f"/temp_media/publish/{file_id}"

        # 7. 返回文件信息
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
async def delete_media(file_id: str, user: Dict[str, Any] = Depends(require_auth)):
    """
    删除临时媒体文件

    Args:
        file_id: 文件ID

    Returns:
        删除结果
    """
    try:
        # Validate file_id to prevent path traversal
        if not re.match(r'^[a-zA-Z0-9_\-]+\.[a-zA-Z0-9]+$', file_id):
            raise HTTPException(status_code=400, detail="无效的文件ID")

        file_path = Path(PathConfig.TEMP_MEDIA_DIR) / "publish" / file_id
        publish_dir = (Path(PathConfig.TEMP_MEDIA_DIR) / "publish").resolve()
        if not file_path.resolve().is_relative_to(publish_dir):
            raise HTTPException(status_code=400, detail="无效的文件路径")

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
async def preview_message(request: PreviewRequest, user: Dict[str, Any] = Depends(require_auth)):
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
