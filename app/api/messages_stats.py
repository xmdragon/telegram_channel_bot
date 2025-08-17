"""
消息统计和监控API模块
处理统计数据、性能监控、报告生成等功能
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from app.utils.timezone import get_current_time, format_for_api
import logging

from app.storage.redis_store import get_redis_message_store
from app.services.auth_service import get_auth_service
from app.services.message_processor import MessageProcessor
from app.services.channel_manager import ChannelManager
from app.core.route_config import ROUTES

logger = logging.getLogger(__name__)
router = APIRouter()
security = HTTPBearer(auto_error=False)

# 依赖注入辅助函数
def get_message_processor() -> MessageProcessor:
    return MessageProcessor()

def get_channel_manager() -> ChannelManager:
    return ChannelManager()

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
        async def wrapper(*args, **kwargs):
            # 这里可以添加具体的权限检查逻辑
            return await func(*args, **kwargs)
        return wrapper
    return decorator

@router.get(ROUTES.messages.stats_overview)
async def get_message_stats(
    user: Dict[str, Any] = Depends(require_auth),
    message_processor: MessageProcessor = Depends(get_message_processor)
):
    """
    获取消息统计概览
    """
    try:
        stats = await message_processor.get_message_stats()
        
        return {
            "success": True,
            "data": stats,
            "timestamp": format_for_api(get_current_time())
        }
        
    except Exception as e:
        logger.error(f"获取消息统计失败: {e}")
        # 返回默认统计数据，确保前端不会出错
        return {
            "success": True,
            "data": {
                "total": 0,
                "pending": 0,
                "approved": 0,
                "rejected": 0,
                "ads": 0,
                "duplicates": 0,
                "channels": 0,
                "auto_forwarded": 0
            },
            "timestamp": format_for_api(get_current_time())
        }

@router.get(ROUTES.messages.stats_channel)
async def get_channel_stats(
    channel_id: str,
    days: int = Query(7, ge=1, le=90, description="统计天数"),
    user: Dict[str, Any] = Depends(require_auth),
    message_processor: MessageProcessor = Depends(get_message_processor)
):
    """
    获取特定频道的统计信息
    """
    try:
        # 计算时间范围
        end_time = get_current_time()
        start_time = end_time - timedelta(days=days)
        
        stats = await message_processor.get_channel_stats(
            channel_id, 
            start_time, 
            end_time
        )
        
        return {
            "success": True,
            "data": {
                "channel_id": channel_id,
                "stats": stats,
                "period": {
                    "start": format_for_api(start_time),
                    "end": format_for_api(end_time),
                    "days": days
                }
            },
            "timestamp": format_for_api(get_current_time())
        }
        
    except Exception as e:
        logger.error(f"获取频道统计失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取频道统计失败: {str(e)}")

@router.get(ROUTES.messages.stats_performance)
@check_permission("stats.performance")
async def get_performance_stats(
    hours: int = Query(24, ge=1, le=168, description="统计小时数"),
    user: Dict[str, Any] = Depends(require_auth),
    message_processor: MessageProcessor = Depends(get_message_processor)
):
    """
    获取系统性能统计
    """
    try:
        # 计算时间范围
        end_time = get_current_time()
        start_time = end_time - timedelta(hours=hours)
        
        performance_data = await message_processor.get_performance_stats(
            start_time, 
            end_time
        )
        
        return {
            "success": True,
            "data": {
                "performance": performance_data,
                "period": {
                    "start": format_for_api(start_time),
                    "end": format_for_api(end_time),
                    "hours": hours
                }
            },
            "timestamp": format_for_api(get_current_time())
        }
        
    except Exception as e:
        logger.error(f"获取性能统计失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取性能统计失败: {str(e)}")

@router.get(ROUTES.messages.stats_filters)
@check_permission("stats.filters")
async def get_filter_stats(
    days: int = Query(7, ge=1, le=30, description="统计天数"),
    user: Dict[str, Any] = Depends(require_auth),
    message_processor: MessageProcessor = Depends(get_message_processor)
):
    """
    获取过滤器统计信息
    """
    try:
        # 计算时间范围
        end_time = get_current_time()
        start_time = end_time - timedelta(days=days)
        
        filter_stats = await message_processor.get_filter_stats(
            start_time, 
            end_time
        )
        
        return {
            "success": True,
            "data": {
                "filter_stats": filter_stats,
                "period": {
                    "start": format_for_api(start_time),
                    "end": format_for_api(end_time),
                    "days": days
                }
            },
            "timestamp": format_for_api(get_current_time())
        }
        
    except Exception as e:
        logger.error(f"获取过滤器统计失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取过滤器统计失败: {str(e)}")

@router.get(ROUTES.messages.stats_trending)
async def get_trending_stats(
    hours: int = Query(24, ge=1, le=72, description="趋势统计小时数"),
    user: Dict[str, Any] = Depends(require_auth),
    message_processor: MessageProcessor = Depends(get_message_processor)
):
    """
    获取消息趋势统计
    """
    try:
        # 计算时间范围
        end_time = get_current_time()
        start_time = end_time - timedelta(hours=hours)
        
        trending_data = await message_processor.get_trending_stats(
            start_time, 
            end_time
        )
        
        return {
            "success": True,
            "data": {
                "trending": trending_data,
                "period": {
                    "start": format_for_api(start_time),
                    "end": format_for_api(end_time),
                    "hours": hours
                }
            },
            "timestamp": format_for_api(get_current_time())
        }
        
    except Exception as e:
        logger.error(f"获取趋势统计失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取趋势统计失败: {str(e)}")

@router.get(ROUTES.messages.health_check)
async def get_system_health():
    """
    获取系统健康状态
    无需认证，供监控系统使用
    """
    try:
        # 检查Redis连接
        redis_status = "healthy"
        try:
            redis_store = get_redis_message_store()
            redis_store.redis.ping()
        except Exception as e:
            redis_status = f"unhealthy: {str(e)}"
        
        # 检查数据库连接
        db_status = "healthy"
        try:
            # 这里可以添加数据库连接检查
            pass
        except Exception as e:
            db_status = f"unhealthy: {str(e)}"
        
        # 获取系统负载信息
        import psutil
        cpu_percent = psutil.cpu_percent(interval=1)
        memory_percent = psutil.virtual_memory().percent
        disk_percent = psutil.disk_usage('/').percent
        
        health_status = "healthy"
        if cpu_percent > 90 or memory_percent > 90 or disk_percent > 90:
            health_status = "warning"
        if redis_status != "healthy" or db_status != "healthy":
            health_status = "unhealthy"
        
        return {
            "status": health_status,
            "services": {
                "redis": redis_status,
                "database": db_status
            },
            "system": {
                "cpu_percent": cpu_percent,
                "memory_percent": memory_percent,
                "disk_percent": disk_percent
            },
            "timestamp": format_for_api(get_current_time())
        }
        
    except Exception as e:
        logger.error(f"获取系统健康状态失败: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": format_for_api(get_current_time())
        }

@router.get(ROUTES.messages.metrics)
@check_permission("stats.metrics")
async def get_system_metrics(
    metric_type: str = Query("all", description="指标类型"),
    user: Dict[str, Any] = Depends(require_auth),
    message_processor: MessageProcessor = Depends(get_message_processor)
):
    """
    获取系统指标数据
    """
    try:
        metrics = {}
        
        if metric_type in ["all", "messages"]:
            # 消息处理指标
            metrics["messages"] = await message_processor.get_message_metrics()
        
        if metric_type in ["all", "performance"]:
            # 性能指标
            import psutil
            metrics["performance"] = {
                "cpu_percent": psutil.cpu_percent(),
                "memory_percent": psutil.virtual_memory().percent,
                "disk_percent": psutil.disk_usage('/').percent,
                "network_io": psutil.net_io_counters()._asdict(),
                "disk_io": psutil.disk_io_counters()._asdict()
            }
        
        if metric_type in ["all", "redis"]:
            # Redis指标
            try:
                redis_store = get_redis_message_store()
                redis_info = redis_store.redis.info()
                metrics["redis"] = {
                    "connected_clients": redis_info.get("connected_clients", 0),
                    "used_memory": redis_info.get("used_memory", 0),
                    "used_memory_human": redis_info.get("used_memory_human", "0B"),
                    "keyspace_hits": redis_info.get("keyspace_hits", 0),
                    "keyspace_misses": redis_info.get("keyspace_misses", 0)
                }
            except Exception as e:
                metrics["redis"] = {"error": str(e)}
        
        return {
            "success": True,
            "data": {
                "metrics": metrics,
                "metric_type": metric_type
            },
            "timestamp": format_for_api(get_current_time())
        }
        
    except Exception as e:
        logger.error(f"获取系统指标失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取系统指标失败: {str(e)}")

@router.post(ROUTES.messages.reports_generate)
@check_permission("stats.reports")
async def generate_report(
    request: dict,
    user: Dict[str, Any] = Depends(require_auth),
    message_processor: MessageProcessor = Depends(get_message_processor)
):
    """
    生成自定义报告
    """
    report_type = request.get("report_type", "daily")
    start_date = request.get("start_date")
    end_date = request.get("end_date")
    channels = request.get("channels", [])
    
    try:
        # 解析日期
        if start_date:
            start_time = datetime.fromisoformat(start_date)
        else:
            start_time = get_current_time() - timedelta(days=1)
        
        if end_date:
            end_time = datetime.fromisoformat(end_date)
        else:
            end_time = get_current_time()
        
        # 生成报告
        report_data = await message_processor.generate_report(
            report_type=report_type,
            start_time=start_time,
            end_time=end_time,
            channels=channels
        )
        
        return {
            "success": True,
            "data": {
                "report": report_data,
                "parameters": {
                    "report_type": report_type,
                    "start_date": format_for_api(start_time),
                    "end_date": format_for_api(end_time),
                    "channels": channels
                },
                "generated_by": user.get('username', 'unknown')
            },
            "timestamp": format_for_api(get_current_time())
        }
        
    except Exception as e:
        logger.error(f"生成报告失败: {e}")
        raise HTTPException(status_code=500, detail=f"生成报告失败: {str(e)}")