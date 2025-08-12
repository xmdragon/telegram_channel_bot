"""
WebSocket 实时消息推送
"""
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

# 全局WebSocket管理器实例
websocket_manager = WebSocketManager()

async def websocket_endpoint(websocket: WebSocket):
    """WebSocket端点"""
    await websocket_manager.connect(websocket)
    try:
        while True:
            # 保持连接活跃，接收客户端ping
            data = await websocket.receive_text()
            if data == "ping":
                pong_response = json.dumps({"type": "pong", "timestamp": datetime.utcnow().isoformat()})
                await websocket_manager.send_personal_message(pong_response, websocket)
    except WebSocketDisconnect:
        websocket_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket错误: {e}")
        websocket_manager.disconnect(websocket)