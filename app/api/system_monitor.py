"""
系统监控API
负责实时日志和系统状态监控
"""
from fastapi import APIRouter, HTTPException
from typing import Dict, Any
import logging
from datetime import datetime, timedelta
from app.storage.redis_store import get_redis_message_store
from app.core.routes import ROUTES

logger = logging.getLogger(__name__)
router = APIRouter(tags=["system-monitor"])

@router.get(ROUTES.system.logs_realtime)  
async def get_realtime_logs(since: str = None) -> Dict[str, Any]:
    """获取实时日志更新"""
    try:
        # 解析since参数
        since_time = None
        if since:
            try:
                since_time = datetime.fromisoformat(since.replace('Z', '+00:00'))
            except:
                since_time = datetime.now() - timedelta(seconds=30)
        else:
            since_time = datetime.now() - timedelta(seconds=30)
        
        logs = []
        current_time = datetime.now()
        
        # 从内存中的日志处理器获取实时日志
        try:
            import logging
            # 获取根日志记录器
            root_logger = logging.getLogger()
            
            # 检查是否有新的日志记录
            # 这里我们模拟一些系统活动日志
            redis_store = get_redis_message_store()
            
            # 检查Redis连接状态
            try:
                redis_store.redis.ping()
                logs.append({
                    "timestamp": current_time.strftime('%Y-%m-%d %H:%M:%S'),
                    "level": "INFO",
                    "source": "system", 
                    "message": "Redis连接正常"
                })
            except Exception as e:
                logs.append({
                    "timestamp": current_time.strftime('%Y-%m-%d %H:%M:%S'),
                    "level": "ERROR",
                    "source": "system",
                    "message": f"Redis连接异常: {str(e)}"
                })
            
            # 检查最近的消息处理活动
            recent_keys = redis_store.redis.keys("msg:*")
            if recent_keys:
                recent_count = len(recent_keys)
                logs.append({
                    "timestamp": current_time.strftime('%Y-%m-%d %H:%M:%S'),
                    "level": "INFO",
                    "source": "message",
                    "message": f"当前消息总数: {recent_count}"
                })
                
                # 检查最近处理的消息
                try:
                    latest_processed = 0
                    for key in recent_keys[:10]:  # 检查最近10条
                        try:
                            msg_data = redis_store.redis.hgetall(key)
                            created_at_str = msg_data.get(b'created_at', b'').decode('utf-8')
                            if created_at_str:
                                created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
                                if created_at >= since_time:
                                    latest_processed += 1
                        except:
                            continue
                    
                    if latest_processed > 0:
                        logs.append({
                            "timestamp": current_time.strftime('%Y-%m-%d %H:%M:%S'),
                            "level": "INFO",
                            "source": "processing",
                            "message": f"最近{int((current_time - since_time).total_seconds())}秒内处理 {latest_processed} 条新消息"
                        })
                except Exception as e:
                    logger.debug(f"检查最近消息处理失败: {e}")
            
            # 检查频道配置状态
            try:
                from app.storage.json_storage import JsonStorage
                json_store = JsonStorage()
                channels = json_store.load_channels()
                if channels:
                    logs.append({
                        "timestamp": current_time.strftime('%Y-%m-%d %H:%M:%S'),
                        "level": "INFO",
                        "source": "config",
                        "message": f"已配置 {len(channels)} 个频道"
                    })
            except Exception as e:
                logger.debug(f"检查频道配置失败: {e}")
                
        except Exception as e:
            logger.debug(f"获取系统状态失败: {e}")
            logs.append({
                "timestamp": current_time.strftime('%Y-%m-%d %H:%M:%S'),
                "level": "WARNING",
                "source": "system",
                "message": f"系统监控部分异常: {str(e)}"
            })
            
        return {
            "success": True,
            "data": {
                "logs": logs,
                "timestamp": current_time.isoformat(),
                "since": since_time.isoformat() if since_time else None
            }
        }
    except Exception as e:
        logger.error(f"获取实时日志失败: {e}")
        return {
            "success": False,
            "message": f"获取实时日志失败: {str(e)}"
        }