"""
统一的频道管理API
合并admin_channels.py, config_channels.py, channel_resolver.py的源频道管理功能
去除状态管理、config字段等冗余功能
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any, Optional, List
from pydantic import BaseModel
import logging
import re

from app.services.config_manager import config_manager
from app.services.telegram_resolver import telegram_resolver
from app.core.route_config import ROUTES
from app.api.deps import require_auth

router = APIRouter()
logger = logging.getLogger(__name__)

# 数据模型
class ChannelAddRequest(BaseModel):
    channel_id: str = ""
    channel_name: str = ""
    channel_title: str = ""
    description: str = ""

class ChannelBatchAddRequest(BaseModel):
    channels: str  # 多行文本，每行一个频道信息

class ChannelResolveRequest(BaseModel):
    channel_input: str  # 频道用户名、链接或ID
    save_to_list: bool = False  # 是否保存到源频道列表

# 频道基础管理
@router.get(ROUTES.channels.list)
async def get_channels(user: Dict[str, Any] = Depends(require_auth)):
    """获取所有源频道"""
    try:
        from app.services.channel_manager import channel_manager

        channels = await channel_manager.get_source_channels()

        return {
            "success": True,
            "channels": channels
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取频道列表失败: {str(e)}")

@router.post(ROUTES.channels.add)
async def add_channel(request: ChannelAddRequest, user: Dict[str, Any] = Depends(require_auth)):
    """添加源频道"""
    try:
        from app.services.channel_manager import channel_manager

        result = await channel_manager.add_channel(
            channel_id=request.channel_id,
            channel_name=request.channel_name,
            description=request.description
        )

        if result:
            # 获取刚添加的频道信息
            channels = await channel_manager.get_all_channels()
            added_channel = next((ch for ch in channels if ch.get('channel_id') == request.channel_id), None)

            return {
                "success": True,
                "message": f"频道 {request.channel_id} 添加成功",
                "channel": added_channel or {
                    "channel_id": request.channel_id,
                    "channel_name": request.channel_name,
                    "channel_title": request.channel_name,
                    "description": request.description
                }
            }
        else:
            raise HTTPException(status_code=400, detail="频道已存在或添加失败")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"添加频道失败: {str(e)}")

@router.delete(ROUTES.channels.delete)
async def remove_channel(channel_id: str, user: Dict[str, Any] = Depends(require_auth)):
    """移除源频道"""
    try:
        from app.services.channel_manager import channel_manager

        success = await channel_manager.delete_channel(channel_id)

        if success:
            return {"success": True, "message": f"频道 {channel_id} 移除成功"}
        else:
            raise HTTPException(status_code=404, detail="频道不存在")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"移除频道失败: {str(e)}")

@router.get(ROUTES.channels.get)
async def get_channel(channel_id: str, user: Dict[str, Any] = Depends(require_auth)):
    """获取单个频道信息"""
    try:
        from app.services.channel_manager import channel_manager

        channel = await channel_manager.get_channel_by_id(channel_id)

        if channel:
            return {
                "success": True,
                "channel": channel
            }
        else:
            raise HTTPException(status_code=404, detail="频道不存在")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取频道信息失败: {str(e)}")

# 批量操作
@router.post(ROUTES.channels.batch_add)
async def batch_add_channels(request: ChannelBatchAddRequest, user: Dict[str, Any] = Depends(require_auth)):
    """批量添加频道"""
    try:
        if not request.channels.strip():
            raise HTTPException(status_code=400, detail="频道列表不能为空")

        from app.services.channel_manager import channel_manager

        lines = request.channels.strip().split('\n')
        results = {
            "added": [],
            "failed": [],
            "skipped": []
        }

        for line in lines:
            line = line.strip()
            if not line:
                continue

            try:
                # 解析频道信息，支持多种格式：
                # 1. @channel_name
                # 2. https://t.me/channel_name
                # 3. -1001234567890 (频道ID)
                # 4. channel_name (不带@)

                channel_name = None
                channel_id = None

                # 格式1: @channel_name
                if line.startswith('@'):
                    channel_name = line
                # 格式2: Telegram链接
                elif line.startswith('https://t.me/'):
                    match = re.search(r'https://t\.me/([a-zA-Z0-9_]+)', line)
                    if match:
                        channel_name = f"@{match.group(1)}"
                # 格式3: 数字ID
                elif line.startswith('-100') or line.isdigit():
                    channel_id = line if line.startswith('-100') else f"-100{line}"
                # 格式4: 纯频道名
                else:
                    # 只包含字母、数字、下划线的被视为频道名
                    if re.match(r'^[a-zA-Z0-9_]+$', line):
                        channel_name = f"@{line}"
                    else:
                        results["failed"].append({
                            "input": line,
                            "error": "无法识别的频道格式"
                        })
                        continue

                # 尝试添加频道
                if channel_name or channel_id:
                    success = await channel_manager.add_channel(
                        channel_id=channel_id or "",
                        channel_name=channel_name or "",
                        description="批量添加的频道"
                    )

                    if success:
                        results["added"].append({
                            "input": line,
                            "channel_name": channel_name,
                            "channel_id": channel_id,
                            "message": "添加成功"
                        })
                    else:
                        results["skipped"].append({
                            "input": line,
                            "channel_name": channel_name,
                            "channel_id": channel_id,
                            "message": "频道已存在或添加失败"
                        })

            except Exception as e:
                results["failed"].append({
                    "input": line,
                    "error": str(e)
                })

        # 统计结果
        added_count = len(results["added"])
        failed_count = len(results["failed"])
        skipped_count = len(results["skipped"])
        total_count = added_count + failed_count + skipped_count

        success = added_count > 0
        if success:
            message = f"批量添加完成：成功 {added_count}，跳过 {skipped_count}，失败 {failed_count}"
        else:
            message = f"批量添加失败：没有成功添加任何频道，跳过 {skipped_count}，失败 {failed_count}"

        return {
            "success": success,
            "message": message,
            "results": results,
            "stats": {
                "total": total_count,
                "added": added_count,
                "skipped": skipped_count,
                "failed": failed_count
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"批量添加频道失败: {e}")
        raise HTTPException(status_code=500, detail=f"批量添加频道失败: {str(e)}")

# 搜索功能
@router.get(ROUTES.channels.search)
async def search_channels(
    q: str = "",
    limit: int = 20,
    user: Dict[str, Any] = Depends(require_auth)
):
    """搜索频道"""
    try:
        from app.services.channel_manager import channel_manager

        all_channels = await channel_manager.get_source_channels()

        if not q:
            # 没有查询条件，返回所有频道（限制数量）
            results = all_channels[:limit]
        else:
            # 按名称、标题、描述搜索
            query_lower = q.lower()
            results = []

            for channel in all_channels:
                if (query_lower in channel.get('channel_name', '').lower() or
                    query_lower in channel.get('channel_title', '').lower() or
                    query_lower in channel.get('description', '').lower()):
                    results.append(channel)

                if len(results) >= limit:
                    break

        return {
            "success": True,
            "query": q,
            "total_found": len(results),
            "channels": results
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"搜索频道失败: {str(e)}")

# 频道解析功能
@router.post(ROUTES.channels.resolve)
async def resolve_channel(request: ChannelResolveRequest, user: Dict[str, Any] = Depends(require_auth)):
    """
    解析频道ID
    支持解析源频道的频道名/链接到ID
    """
    try:
        channel_input = request.channel_input.strip()
        if not channel_input:
            return {"success": False, "message": "请输入频道名称或链接"}

        # 使用双Session系统获取客户端
        from app.telegram.dual_session_manager import dual_session_manager
        client = await dual_session_manager.get_listener_client()

        if not client:
            return {"success": False, "message": "Telegram客户端未连接，请先完成认证"}

        # 解析频道ID
        resolved_id = await telegram_resolver.resolve(channel_input)

        if not resolved_id:
            return {
                "success": False,
                "message": f"无法解析 {channel_input}，请检查频道名称或链接是否正确"
            }

        # 获取频道详细信息
        channel_info = None
        try:
            entity = await client.get_entity(int(resolved_id))
            channel_info = {
                "id": resolved_id,
                "title": getattr(entity, 'title', '未知'),
                "username": getattr(entity, 'username', None),
                "type": "channel" if getattr(entity, 'broadcast', False) else "group"
            }
        except Exception as e:
            logger.warning(f"获取频道详细信息失败: {e}")
            channel_info = {"id": resolved_id}

        # 如果指定保存到列表，添加到源频道列表
        saved_to_list = False
        if request.save_to_list and channel_info:
            try:
                from app.services.channel_manager import channel_manager
                success = await channel_manager.add_channel(
                    channel_id=resolved_id,
                    channel_name=f"@{channel_info.get('username', '')}" if channel_info.get('username') else "",
                    description=f"通过解析添加: {channel_input}"
                )
                saved_to_list = success
                if success:
                    logger.info(f"已将解析的频道 {resolved_id} 添加到源频道列表")
            except Exception as e:
                logger.warning(f"保存解析的频道到列表失败: {e}")

        return {
            "success": True,
            "input": channel_input,
            "resolved_id": resolved_id,
            "channel_info": channel_info,
            "saved_to_list": saved_to_list,
            "message": f"成功解析为 {resolved_id}"
        }

    except Exception as e:
        logger.error(f"解析频道失败: {e}")
        return {
            "success": False,
            "message": f"解析失败: {str(e)}"
        }

