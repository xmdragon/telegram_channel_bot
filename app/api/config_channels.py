"""
频道配置管理API
包括：频道添加、删除、状态更新、获取频道信息
"""
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Dict, Any, Optional
from pydantic import BaseModel
import logging

from app.services.config_manager import config_manager
from app.services.auth_service import get_auth_service
from app.core.route_config import ROUTES

router = APIRouter()
logger = logging.getLogger(__name__)
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

async def check_config_permission(user: Dict[str, Any] = Depends(require_auth)) -> Dict[str, Any]:
    """检查配置管理权限"""
    try:
        # 简化权限检查：超级管理员可以管理配置
        # 在实际项目中，可以根据需要添加更细粒度的权限控制
        if user.get('is_super_admin'):
            return user
        else:
            # 暂时只允许超级管理员访问配置管理
            raise HTTPException(status_code=403, detail="权限不足")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"检查配置权限失败: {e}")
        raise HTTPException(status_code=500, detail="权限检查失败")

# 频道管理相关API
class ChannelAddRequest(BaseModel):
    channel_id: str
    channel_name: str = ""
    channel_title: str = ""
    description: str = ""

class ChannelBatchAddRequest(BaseModel):
    channels: str  # 多行文本，每行一个频道信息

@router.post(ROUTES.config.channels_add)
async def add_channel(request: ChannelAddRequest, user: Dict[str, Any] = Depends(check_config_permission)):
    """添加监听频道"""
    try:
        from app.services.channel_manager import channel_manager
        
        success = await channel_manager.add_channel(
            channel_id=request.channel_id,
            channel_name=request.channel_name,
            description=request.description
        )
        
        if success:
            return {"success": True, "message": f"频道 {request.channel_id} 添加成功"}
        else:
            raise HTTPException(status_code=400, detail="频道已存在或添加失败")
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"添加频道失败: {str(e)}")

@router.delete(ROUTES.config.channels_by_id)
async def remove_channel(channel_id: str, user: Dict[str, Any] = Depends(check_config_permission)):
    """移除监听频道"""
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

class ChannelStatusRequest(BaseModel):
    enabled: bool

@router.put(ROUTES.config.channels_status)
async def update_channel_status(channel_id: str, request: ChannelStatusRequest, user: Dict[str, Any] = Depends(check_config_permission)):
    """更新频道监听状态"""
    try:
        from app.services.channel_manager import channel_manager
        
        success = await channel_manager.update_channel_status(
            channel_id, 
            is_active=request.enabled
        )
        
        if success:
            return {"success": True, "message": f"频道 {channel_id} 状态更新成功"}
        else:
            raise HTTPException(status_code=404, detail="频道不存在")
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新频道状态失败: {str(e)}")

@router.get(ROUTES.config.channels_list)
async def get_channels(user: Dict[str, Any] = Depends(check_config_permission)):
    """获取所有频道"""
    try:
        from app.services.channel_manager import channel_manager
        
        channels = await channel_manager.get_source_channels()
        
        return {
            "success": True,
            "channels": channels
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取频道列表失败: {str(e)}")

@router.get(ROUTES.config.channels_by_id)
async def get_channel(channel_id: str, user: Dict[str, Any] = Depends(check_config_permission)):
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

@router.post(ROUTES.config.channels_batch_add)
async def batch_add_channels(request: ChannelBatchAddRequest, user: Dict[str, Any] = Depends(check_config_permission)):
    """批量添加频道"""
    try:
        if not request.channels.strip():
            raise HTTPException(status_code=400, detail="频道列表不能为空")
        
        from app.services.channel_manager import channel_manager
        import re
        
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
                        description=f"批量添加的频道"
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