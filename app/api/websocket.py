"""
WebSocket 实时消息推送
"""
import asyncio
import json
import logging
from typing import Dict, Set
from fastapi import WebSocket, WebSocketDisconnect
from datetime import datetime

logger = logging.getLogger(__name__)

class WebSocketManager:
    """WebSocket连接管理器"""
    
    def __init__(self):
        # 存储活跃连接
        self.active_connections: Set[WebSocket] = set()
        
    async def connect(self, websocket: WebSocket):
        """接受新的WebSocket连接"""
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(f"新的WebSocket连接，当前连接数: {len(self.active_connections)}")
        
    def disconnect(self, websocket: WebSocket):
        """断开WebSocket连接"""
        self.active_connections.discard(websocket)
        logger.info(f"WebSocket连接断开，当前连接数: {len(self.active_connections)}")
        
    async def send_personal_message(self, message: str, websocket: WebSocket):
        """发送个人消息"""
        try:
            await websocket.send_text(message)
        except Exception as e:
            logger.error(f"发送个人消息失败: {e}")
            self.disconnect(websocket)
            
    async def broadcast(self, message: str):
        """广播消息给所有连接"""
        if not self.active_connections:
            return
            
        disconnected = set()
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.error(f"广播消息失败: {e}")
                disconnected.add(connection)
                
        # 清理断开的连接
        for connection in disconnected:
            self.disconnect(connection)
            
    async def broadcast_new_message(self, message_data: Dict):
        """广播新消息"""
        payload = {
            "type": "new_message",
            "data": message_data,
            "timestamp": datetime.utcnow().isoformat()
        }
        message_json = json.dumps(payload, ensure_ascii=False)
        logger.info(f"📡 广播新消息，ID:{message_data.get('id')}, 状态:{message_data.get('status')}, 连接数:{len(self.active_connections)}")
        await self.broadcast(message_json)
        
    async def broadcast_stats_update(self, stats: Dict):
        """广播统计更新"""
        payload = {
            "type": "stats_update", 
            "data": stats,
            "timestamp": datetime.utcnow().isoformat()
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
            "timestamp": datetime.utcnow().isoformat()
        }
        await self.broadcast(json.dumps(payload, ensure_ascii=False))
        
    async def broadcast_log_message(self, log_data: Dict):
        """广播日志消息"""
        payload = {
            "type": "log_message",
            "data": log_data,
            "timestamp": datetime.utcnow().isoformat()
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
                "timestamp": datetime.utcnow().isoformat()
            }
        }
        logger.info(f"📡 广播进度: {operation} - {progress}% - {message}")
        await self.broadcast(json.dumps(payload, ensure_ascii=False))

# 全局WebSocket管理器实例
websocket_manager = WebSocketManager()

async def handle_websocket_message(websocket: WebSocket, message: str):
    """处理WebSocket消息 - Linus式双向通信"""
    try:
        data = json.loads(message)
        msg_type = data.get("type")
        request_id = data.get("request_id")
        
        if msg_type == "ping":
            # 心跳响应
            response = {
                "type": "pong",
                "request_id": request_id,
                "timestamp": datetime.utcnow().isoformat()
            }
            await websocket_manager.send_personal_message(json.dumps(response), websocket)
            
        elif msg_type == "request_stats":
            # 请求统计数据
            from app.api.messages_stats import get_linus_stats_overview
            try:
                stats = await get_linus_stats_overview()
                response = {
                    "type": "stats_response",
                    "request_id": request_id,
                    "data": stats.get("data") if stats.get("success") else None,
                    "success": stats.get("success", False),
                    "error": stats.get("error") if not stats.get("success") else None,
                    "timestamp": datetime.utcnow().isoformat()
                }
            except Exception as e:
                response = {
                    "type": "stats_response", 
                    "request_id": request_id,
                    "success": False,
                    "error": str(e),
                    "timestamp": datetime.utcnow().isoformat()
                }
            await websocket_manager.send_personal_message(json.dumps(response), websocket)
            
        elif msg_type == "request_system_status":
            # 请求系统状态
            from app.api.system_health import get_system_health
            try:
                status = await get_system_health()
                response = {
                    "type": "system_status_response",
                    "request_id": request_id,
                    "data": status,
                    "success": True,
                    "timestamp": datetime.utcnow().isoformat()
                }
            except Exception as e:
                response = {
                    "type": "system_status_response",
                    "request_id": request_id,
                    "success": False,
                    "error": str(e),
                    "timestamp": datetime.utcnow().isoformat()
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
                "timestamp": datetime.utcnow().isoformat()
            }
            await websocket_manager.send_personal_message(json.dumps(response), websocket)
            logger.info(f"客户端订阅频道: {channel}")
            
        else:
            # 未知消息类型
            response = {
                "type": "error",
                "request_id": request_id,
                "error": f"未知消息类型: {msg_type}",
                "timestamp": datetime.utcnow().isoformat()
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
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                await handle_websocket_message(websocket, data)
            except asyncio.TimeoutError:
                # 超时继续循环，保持连接
                continue
    except WebSocketDisconnect:
        websocket_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket错误: {e}")
        websocket_manager.disconnect(websocket)