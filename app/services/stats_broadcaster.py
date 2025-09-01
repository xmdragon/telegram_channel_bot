"""
统计数据广播器 - Linus式主动推送架构

核心理念：
- 数据变化时主动推送，而不是等前端轮询
- 智能节流，避免过度推送
- 差异检测，只推送真正变化的数据

"永远不要让客户端询问数据是否更新，服务器应该主动告知"
"""

import asyncio
import json
import logging
import time
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime

logger = logging.getLogger(__name__)

@dataclass
class BroadcastState:
    """广播状态"""
    last_stats: Optional[Dict] = None
    last_system_status: Optional[Dict] = None
    last_broadcast_time: float = 0
    broadcast_count: int = 0
    change_count: int = 0

class StatsBroadcaster:
    """统计数据广播器"""
    
    def __init__(self):
        self.state = BroadcastState()
        self.is_running = False
        self.task = None
        
        # 配置参数 - Linus式优化：降低无必要的轮询频率
        self.check_interval = 30.0  # 检查间隔（秒）- 从10秒优化到30秒
        self.min_broadcast_interval = 15.0  # 最小广播间隔 - 从5秒优化到15秒
        self.max_broadcast_interval = 120.0  # 最大广播间隔 - 从60秒优化到120秒
        
        # 差异阈值
        self.change_threshold = 0.01  # 数值变化阈值（1%）
        
    async def start(self):
        """启动广播器"""
        if self.is_running:
            return
            
        self.is_running = True
        self.task = asyncio.create_task(self._broadcast_loop())
        # 添加异常处理回调，避免"Task exception was never retrieved"警告
        self.task.add_done_callback(self._task_done_callback)
        logger.info("📡 统计数据广播器已启动")
        
    async def stop(self):
        """停止广播器"""
        self.is_running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        logger.info("📡 统计数据广播器已停止")
    
    def _task_done_callback(self, task):
        """任务完成回调，处理未捕获的异常"""
        try:
            # 尝试获取任务结果，如果有异常会被抛出
            task.result()
        except asyncio.CancelledError:
            logger.debug("统计广播任务已取消")
        except Exception as e:
            logger.error(f"统计广播任务异常: {e}")
            import traceback
            logger.error(f"异常堆栈: {traceback.format_exc()}")
        
    async def _broadcast_loop(self):
        """广播主循环"""
        while self.is_running:
            try:
                await self._check_and_broadcast()
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"广播循环错误: {e}")
                await asyncio.sleep(5)  # 错误后等待5秒重试
                
    async def _check_and_broadcast(self):
        """检查数据变化并广播"""
        current_time = time.time()
        
        # 检查是否满足最小广播间隔
        if current_time - self.state.last_broadcast_time < self.min_broadcast_interval:
            return
            
        try:
            # 获取当前统计数据
            current_stats = await self._get_current_stats()
            current_system_status = await self._get_current_system_status()
            
            # 检查统计数据是否变化
            stats_changed = self._has_stats_changed(current_stats)
            system_changed = self._has_system_status_changed(current_system_status)
            
            # 检查是否达到最大广播间隔（强制广播）
            force_broadcast = (current_time - self.state.last_broadcast_time) > self.max_broadcast_interval
            
            if stats_changed or system_changed or force_broadcast:
                await self._broadcast_updates(current_stats, current_system_status, {
                    'stats_changed': stats_changed,
                    'system_changed': system_changed,
                    'force_broadcast': force_broadcast
                })
                
                # 更新状态
                self.state.last_stats = current_stats
                self.state.last_system_status = current_system_status
                self.state.last_broadcast_time = current_time
                self.state.broadcast_count += 1
                
                if stats_changed or system_changed:
                    self.state.change_count += 1
                    
        except Exception as e:
            logger.error(f"检查和广播数据失败: {e}")
            
    async def _get_current_stats(self) -> Optional[Dict]:
        """获取当前统计数据"""
        try:
            from app.storage.redis_manager import redis_manager
            from datetime import datetime
            
            # 真正的统计数据获取
            if redis_manager is None:
                logger.warning("Redis消息存储未初始化")
                return None
            
            # 按Linus原则：直接获取所需的统计数据
            system_stats = redis_manager.get_statistics()
            stats = {
                "total_messages": system_stats.get("total_messages", 0),
                "pending_count": system_stats.get("pending_messages", 0),
                "approved_count": system_stats.get("approved_messages", 0),
                "rejected_count": system_stats.get("rejected_messages", 0),
                "timestamp": datetime.utcnow().isoformat()
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"获取统计数据失败: {e}")
            return None
            
    async def _get_current_system_status(self) -> Optional[Dict]:
        """获取当前系统状态"""
        # 暂时禁用API调用避免导入错误，使用简化版本
        # TODO: 实现直接的系统状态检查逻辑
        try:
            from datetime import datetime
            
            # 简化版本：返回基础系统状态
            return {
                "status": "running",
                "timestamp": datetime.utcnow().isoformat(),
                "web_server": "active",
                "simplified": True  # 标记这是简化版本
            }
        except Exception as e:
            logger.error(f"获取系统状态失败: {e}")
            return None
            
    def _has_stats_changed(self, current_stats: Optional[Dict]) -> bool:
        """检查统计数据是否变化"""
        if current_stats is None:
            return False
            
        if self.state.last_stats is None:
            return True
            
        return self._deep_compare_with_threshold(
            self.state.last_stats, 
            current_stats,
            self.change_threshold
        )
        
    def _has_system_status_changed(self, current_status: Optional[Dict]) -> bool:
        """检查系统状态是否变化"""
        if current_status is None:
            return False
            
        if self.state.last_system_status is None:
            return True
            
        # 系统状态变化更敏感，任何变化都推送
        return not self._deep_equal(self.state.last_system_status, current_status)
        
    def _deep_compare_with_threshold(self, old_data: Dict, new_data: Dict, threshold: float) -> bool:
        """深度比较数据，考虑数值阈值"""
        def compare_values(old_val, new_val):
            if old_val == new_val:
                return False
                
            # 数值类型使用阈值比较
            if isinstance(old_val, (int, float)) and isinstance(new_val, (int, float)):
                if old_val == 0:
                    return new_val != 0
                return abs((new_val - old_val) / old_val) > threshold
                
            # 其他类型直接比较
            return old_val != new_val
            
        return self._deep_compare_recursive(old_data, new_data, compare_values)
        
    def _deep_compare_recursive(self, old_data: Any, new_data: Any, compare_func) -> bool:
        """递归深度比较"""
        if type(old_data) != type(new_data):
            return True
            
        if isinstance(old_data, dict):
            # 检查键是否相同
            if set(old_data.keys()) != set(new_data.keys()):
                return True
                
            # 递归比较每个值
            for key in old_data.keys():
                if self._deep_compare_recursive(old_data[key], new_data[key], compare_func):
                    return True
            return False
            
        elif isinstance(old_data, list):
            if len(old_data) != len(new_data):
                return True
                
            for old_item, new_item in zip(old_data, new_data):
                if self._deep_compare_recursive(old_item, new_item, compare_func):
                    return True
            return False
            
        else:
            return compare_func(old_data, new_data)
            
    def _deep_equal(self, a: Any, b: Any) -> bool:
        """深度相等比较"""
        if a == b:
            return True
        if type(a) != type(b):
            return False
            
        if isinstance(a, dict):
            if set(a.keys()) != set(b.keys()):
                return False
            return all(self._deep_equal(a[k], b[k]) for k in a.keys())
            
        elif isinstance(a, list):
            if len(a) != len(b):
                return False
            return all(self._deep_equal(x, y) for x, y in zip(a, b))
            
        return False
        
    async def _broadcast_updates(self, stats: Optional[Dict], system_status: Optional[Dict], change_info: Dict):
        """广播更新数据"""
        try:
            from app.api.websocket import websocket_manager
            
            broadcast_data = {
                "type": "data_update",
                "timestamp": datetime.utcnow().isoformat(),
                "change_info": change_info,
                "data": {}
            }
            
            # 添加有效数据
            if stats is not None:
                broadcast_data["data"]["stats"] = stats
                
            if system_status is not None:
                broadcast_data["data"]["system_status"] = system_status
                
            # 添加广播统计信息
            broadcast_data["broadcast_info"] = {
                "broadcast_count": self.state.broadcast_count,
                "change_count": self.state.change_count,
                "uptime": time.time() - (self.state.last_broadcast_time - self.state.broadcast_count * self.check_interval)
            }
            
            await websocket_manager.broadcast(json.dumps(broadcast_data, ensure_ascii=False))
            
            logger.info(f"📡 广播数据更新: 统计={change_info['stats_changed']}, 系统={change_info['system_changed']}, 强制={change_info['force_broadcast']}")
            
        except Exception as e:
            logger.error(f"广播更新失败: {e}")
            
    def get_status(self) -> Dict:
        """获取广播器状态"""
        return {
            "is_running": self.is_running,
            "broadcast_count": self.state.broadcast_count,
            "change_count": self.state.change_count,
            "last_broadcast_time": self.state.last_broadcast_time,
            "uptime": time.time() - (self.state.last_broadcast_time - self.state.broadcast_count * self.check_interval) if self.state.broadcast_count > 0 else 0,
            "config": {
                "check_interval": self.check_interval,
                "min_broadcast_interval": self.min_broadcast_interval,
                "max_broadcast_interval": self.max_broadcast_interval,
                "change_threshold": self.change_threshold
            }
        }

# 全局广播器实例
stats_broadcaster = StatsBroadcaster()

async def init_stats_broadcaster():
    """初始化统计数据广播器"""
    await stats_broadcaster.start()
    
async def shutdown_stats_broadcaster():
    """关闭统计数据广播器"""
    await stats_broadcaster.stop()