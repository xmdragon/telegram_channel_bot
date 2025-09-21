"""
WebSocket 实时消息推送
"""
import asyncio
import json
import logging
from typing import Dict, Set
from fastapi import WebSocket, WebSocketDisconnect
from datetime import datetime
from app.utils.timezone import get_current_time

logger = logging.getLogger(__name__)

class WebSocketManager:
    """WebSocket连接管理器"""
    
    def __init__(self):
        # 存储活跃连接
        self.active_connections: Set[WebSocket] = set()
        # Redis订阅任务
        self.redis_subscriber_task = None
        self.redis_subscriber_running = False
        
    async def connect(self, websocket: WebSocket):
        """接受新的WebSocket连接"""
        import os
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(f"[PID:{os.getpid()}] 新的WebSocket连接，当前连接数: {len(self.active_connections)}")
        
        # 在第一个连接时启动Redis监听器（确保与WebSocket在同一进程）
        if len(self.active_connections) == 1 and not self.redis_subscriber_running:
            import asyncio
            self.redis_subscriber_task = asyncio.create_task(self.start_redis_listener())
            logger.info(f"[PID:{os.getpid()}] 在WebSocket进程中启动Redis监听器")
        
    def disconnect(self, websocket: WebSocket):
        """断开WebSocket连接"""
        import os
        self.active_connections.discard(websocket)
        logger.info(f"[PID:{os.getpid()}] WebSocket连接断开，当前连接数: {len(self.active_connections)}")
        
        # 如果没有连接了，停止Redis监听器
        if len(self.active_connections) == 0 and self.redis_subscriber_running:
            import asyncio
            asyncio.create_task(self.stop_redis_listener())
            logger.info(f"[PID:{os.getpid()}] 已停止Redis监听器（无活跃连接）")
        
    async def send_personal_message(self, message: str, websocket: WebSocket):
        """发送个人消息"""
        try:
            await websocket.send_text(message)
        except Exception as e:
            logger.error(f"发送个人消息失败: {e}")
            self.disconnect(websocket)
            
    async def broadcast(self, message: str):
        """广播消息给所有连接 - ：发送即忘，不阻塞"""
        if not self.active_connections:
            return
            
        # 创建连接集合的副本，避免"Set changed size during iteration"错误
        connections_copy = list(self.active_connections)
        disconnected = []
        
        for connection in connections_copy:
            try:
                import os
                import asyncio
                # 添加1秒超时，防止无限等待
                await asyncio.wait_for(connection.send_text(message), timeout=1.0)
                logger.debug(f"[PID:{os.getpid()}] 📤 成功发送消息到WebSocket连接，消息长度: {len(message)}")
            except asyncio.TimeoutError:
                import os
                logger.warning(f"[PID:{os.getpid()}] WebSocket发送超时，标记断开连接")
                disconnected.append(connection)
            except Exception as e:
                import os
                logger.debug(f"[PID:{os.getpid()}] 广播消息失败: {e}")
                disconnected.append(connection)
                
        # 清理断开的连接
        for connection in disconnected:
            self.disconnect(connection)
            
    async def broadcast_new_message(self, message_data: Dict):
        """广播新消息"""
        payload = {
            "type": "new_message",
            "data": message_data,
            "timestamp": get_current_time().isoformat()
        }
        message_json = json.dumps(payload, ensure_ascii=False)
        logger.info(f"📡 广播新消息，ID:{message_data.get('id')}, 状态:{message_data.get('status')}, 连接数:{len(self.active_connections)}")
        await self.broadcast(message_json)
        
    async def broadcast_stats_update(self, stats: Dict):
        """广播统计更新"""
        payload = {
            "type": "stats_update", 
            "data": stats,
            "timestamp": get_current_time().isoformat()
        }
        await self.broadcast(json.dumps(payload, ensure_ascii=False))
        
    async def broadcast_message_status_update(self, message_id: int, status: str):
        """广播消息状态更新"""
        payload = {
            "type": "message_status_update",
            "data": {
                "message_id": message_id,
                "status": status
            },
            "timestamp": get_current_time().isoformat()
        }
        await self.broadcast(json.dumps(payload, ensure_ascii=False))
        
    async def broadcast_progress(self, operation: str, progress: int, message: str, details: Dict = None):
        """广播操作进度"""
        payload = {
            "type": "operation_progress",
            "data": {
                "operation": operation,      # "system_status" 或 "system_reset"
                "progress": progress,        # 0-100 进度百分比
                "message": message,          # 当前步骤描述
                "details": details or {},    # 额外详情数据
                "timestamp": get_current_time().isoformat()
            }
        }
        logger.info(f"📡 广播进度: {operation} - {progress}% - {message}")
        await self.broadcast(json.dumps(payload, ensure_ascii=False))

    async def start_redis_listener(self):
        """启动Redis订阅监听器（跨进程通信）"""
        if self.redis_subscriber_running:
            logger.info("Redis订阅监听器已经在运行")
            return
            
        try:
            import redis.asyncio as redis
            from app.core.config import settings
            
            # 创建Redis异步客户端
            redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
            pubsub = redis_client.pubsub()
            await pubsub.subscribe("websocket:broadcast")
            
            self.redis_subscriber_running = True
            logger.info("🔔 Redis WebSocket订阅监听器已启动")
            
            async for message in pubsub.listen():
                if not self.redis_subscriber_running:
                    break
                    
                if message['type'] == 'message':
                    try:
                        import os
                        logger.info(f"[PID:{os.getpid()}] 📥 从Redis接收到WebSocket广播消息: {message['data'][:100]}...")
                        
                        # 验证JSON格式
                        json.loads(message['data'])
                        
                        # 广播到所有WebSocket连接
                        logger.info(f"[PID:{os.getpid()}] 🔄 准备广播到 {len(self.active_connections)} 个WebSocket连接")
                        await self.broadcast(message['data'])
                        logger.info(f"[PID:{os.getpid()}] ✅ WebSocket消息广播完成")
                        
                    except json.JSONDecodeError as e:
                        logger.error(f"Redis消息JSON格式错误: {e}")
                    except Exception as e:
                        logger.error(f"处理Redis WebSocket消息失败: {e}")
                        
        except Exception as e:
            logger.error(f"Redis订阅监听器启动失败: {e}")
            import traceback
            logger.error(f"详细错误信息: {traceback.format_exc()}")
        finally:
            self.redis_subscriber_running = False
            try:
                await pubsub.unsubscribe("websocket:broadcast")
                await redis_client.close()
                logger.info("Redis订阅监听器已关闭")
            except:
                pass

    async def stop_redis_listener(self):
        """停止Redis订阅监听器"""
        if self.redis_subscriber_running:
            self.redis_subscriber_running = False
            logger.info("正在停止Redis订阅监听器...")
            
            if self.redis_subscriber_task:
                try:
                    self.redis_subscriber_task.cancel()
                    await self.redis_subscriber_task
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    logger.error(f"停止Redis订阅任务失败: {e}")

# 全局WebSocket管理器实例
websocket_manager = WebSocketManager()

async def handle_websocket_message(websocket: WebSocket, message: str):
    """处理WebSocket消息 - 双向通信"""
    try:
        # 错误处理：垃圾输入优雅丢弃，不报错
        if not isinstance(message, str):
            return  # 直接忽略非字符串消息
            
        data = json.loads(message)
        if not isinstance(data, dict):
            return  # 忽略非字典格式的消息
            
        msg_type = data.get("type")
        request_id = data.get("request_id")
        
        if msg_type == "ping":
            # 心跳响应
            logger.debug(f"💓 收到心跳 ping，返回 pong")
            response = {
                "type": "pong",
                "request_id": request_id,
                "timestamp": get_current_time().isoformat()
            }
            await websocket_manager.send_personal_message(json.dumps(response), websocket)
            
        elif msg_type == "request_stats":
            # 请求统计数据 - 使用真正的统计功能
            try:
                from app.storage.message_stats_store import message_stats_store

                if message_stats_store is None:
                    raise RuntimeError("统计存储未初始化")
                
                # 按设计原则：直接获取所需的统计数据
                stats_data = {
                    "total_messages": message_stats_store.get_total_messages(),
                    "pending_count": message_stats_store.get_pending_count(),
                    "approved_count": message_stats_store.get_approved_count(),
                    "rejected_count": message_stats_store.get_rejected_count(),
                    "timestamp": get_current_time().isoformat()
                }
                
                response = {
                    "type": "stats_response",
                    "request_id": request_id,
                    "data": stats_data,
                    "success": True,
                    "timestamp": get_current_time().isoformat()
                }
            except Exception as e:
                response = {
                    "type": "stats_response", 
                    "request_id": request_id,
                    "success": False,
                    "error": str(e),
                    "timestamp": get_current_time().isoformat()
                }
            await websocket_manager.send_personal_message(json.dumps(response), websocket)
            
        elif msg_type == "request_system_status":
            # 请求系统状态 - 使用简化版本避免导入错误
            try:
                # 简化版本：返回基础系统状态
                status_data = {
                    "status": "running",
                    "web_server": "active",
                    "timestamp": get_current_time().isoformat(),
                    "simplified": True
                }
                
                response = {
                    "type": "system_status_response",
                    "request_id": request_id,
                    "data": status_data,
                    "success": True,
                    "timestamp": get_current_time().isoformat()
                }
            except Exception as e:
                response = {
                    "type": "system_status_response",
                    "request_id": request_id,
                    "success": False,
                    "error": str(e),
                    "timestamp": get_current_time().isoformat()
                }
            await websocket_manager.send_personal_message(json.dumps(response), websocket)
            
        elif msg_type == "subscribe":
            # 订阅特定数据流
            channel = data.get("channel")
            response = {
                "type": "subscribe_response",
                "request_id": request_id,
                "channel": channel,
                "success": True,
                "timestamp": get_current_time().isoformat()
            }
            await websocket_manager.send_personal_message(json.dumps(response), websocket)
            logger.info(f"客户端订阅频道: {channel}")
            
        else:
            # 未知消息类型
            response = {
                "type": "error",
                "request_id": request_id,
                "error": f"未知消息类型: {msg_type}",
                "timestamp": get_current_time().isoformat()
            }
            await websocket_manager.send_personal_message(json.dumps(response), websocket)
            
    except json.JSONDecodeError:
        logger.error("WebSocket消息JSON解析失败")
    except Exception as e:
        logger.error(f"WebSocket消息处理失败: {e}")

async def websocket_endpoint(websocket: WebSocket):
    """WebSocket端点 - 支持双向通信"""
    await websocket_manager.connect(websocket)
    try:
        while True:
            # 接收客户端消息进行双向通信
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=45.0)  # 增加到45秒，给20秒心跳更多缓冲时间
                await handle_websocket_message(websocket, data)
            except asyncio.TimeoutError:
                # 超时继续循环，保持连接
                continue
    except WebSocketDisconnect:
        websocket_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket错误: {e}")
        websocket_manager.disconnect(websocket)