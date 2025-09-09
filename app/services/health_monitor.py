"""
服务健康监控模块
各个服务通过此模块上报健康状态，Web界面可以查询服务状态
"""
import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum

logger = logging.getLogger(__name__)

class ServiceStatus(Enum):
    """服务状态枚举"""
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    STARTING = "starting"
    STOPPING = "stopping"
    UNKNOWN = "unknown"

@dataclass
class ServiceHealth:
    """服务健康状态"""
    service_name: str
    status: ServiceStatus
    last_heartbeat: datetime
    uptime_seconds: float
    metadata: Dict[str, Any]
    error_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        data = asdict(self)
        data['status'] = self.status.value
        data['last_heartbeat'] = self.last_heartbeat.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ServiceHealth':
        """从字典创建实例"""
        data['status'] = ServiceStatus(data['status'])
        data['last_heartbeat'] = datetime.fromisoformat(data['last_heartbeat'])
        return cls(**data)

class HealthMonitor:
    """健康监控器"""
    
    def __init__(self, service_name: str):
        self.service_name = service_name
        self.start_time = datetime.now()
        self.last_heartbeat = datetime.now()
        self.status = ServiceStatus.STARTING
        self.metadata = {}
        self.error_message = None
        self.heartbeat_task = None
        self.heartbeat_interval = 30  # 30秒心跳间隔
        
    async def start(self):
        """启动健康监控"""
        logger.info(f"[{self.service_name}] 启动服务健康监控")
        self.status = ServiceStatus.HEALTHY
        self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        logger.info(f"[{self.service_name}] 心跳任务已启动，间隔: {self.heartbeat_interval}秒")
        await self.update_status()
    
    async def stop(self):
        """停止健康监控"""
        logger.info(f"停止服务健康监控: {self.service_name}")
        self.status = ServiceStatus.STOPPING
        await self.update_status()
        
        if self.heartbeat_task:
            self.heartbeat_task.cancel()
            try:
                await self.heartbeat_task
            except asyncio.CancelledError:
                pass
    
    async def set_healthy(self, metadata: Dict[str, Any] = None):
        """设置为健康状态"""
        self.status = ServiceStatus.HEALTHY
        self.error_message = None
        if metadata:
            self.metadata.update(metadata)
        logger.info(f"[{self.service_name}] 设置为健康状态: {metadata}")
        await self.update_status()
    
    async def set_unhealthy(self, error_message: str, metadata: Dict[str, Any] = None):
        """设置为不健康状态"""
        self.status = ServiceStatus.UNHEALTHY
        self.error_message = error_message
        if metadata:
            self.metadata.update(metadata)
        await self.update_status()
        logger.warning(f"服务 {self.service_name} 状态异常: {error_message}")
    
    async def update_metadata(self, metadata: Dict[str, Any]):
        """更新元数据"""
        self.metadata.update(metadata)
        await self.update_status()
    
    async def update_status(self):
        """更新服务状态到Redis"""
        try:
            from app.storage.redis_manager import redis_manager
            
            redis = redis_manager.client
            if not redis:
                logger.warning(f"[{self.service_name}] Redis客户端不可用，无法更新健康状态")
                return
            
            uptime = (datetime.now() - self.start_time).total_seconds()
            self.last_heartbeat = datetime.now()
            
            health = ServiceHealth(
                service_name=self.service_name,
                status=self.status,
                last_heartbeat=self.last_heartbeat,
                uptime_seconds=uptime,
                metadata=self.metadata,
                error_message=self.error_message
            )
            
            key = f"service_health:{self.service_name}"
            value = json.dumps(health.to_dict(), ensure_ascii=False)
            
            # 设置30分钟过期时间，防止僵尸记录
            result = redis.setex(key, 1800, value)
            
            if result:
                logger.debug(f"[{self.service_name}] 健康状态已更新到Redis: {key}")
            else:
                logger.warning(f"[{self.service_name}] Redis写入返回False: {key}")
                
        except Exception as e:
            logger.error(f"[{self.service_name}] 更新服务状态失败: {e}")
            import traceback
            logger.error(f"[{self.service_name}] 错误详情: {traceback.format_exc()}")
    
    async def _heartbeat_loop(self):
        """心跳循环"""
        heartbeat_count = 0
        while True:
            try:
                await asyncio.sleep(self.heartbeat_interval)
                heartbeat_count += 1
                await self.update_status()
                # 每10次心跳记录一次（5分钟一次）
                if heartbeat_count % 10 == 0:
                    logger.debug(f"[{self.service_name}] 心跳正常 #{heartbeat_count}")
            except asyncio.CancelledError:
                logger.info(f"[{self.service_name}] 心跳循环已取消")
                break
            except Exception as e:
                logger.error(f"[{self.service_name}] 心跳更新失败: {e}")
                import traceback
                logger.error(f"[{self.service_name}] 心跳错误详情: {traceback.format_exc()}")

class HealthCheckService:
    """健康检查服务 - 用于查询所有服务状态"""
    
    @staticmethod
    async def get_all_service_health() -> Dict[str, ServiceHealth]:
        """获取所有服务的健康状态"""
        try:
            from app.storage.redis_manager import redis_manager
            
            redis = redis_manager.client
            if not redis:
                return {}
            
            # 查找所有服务健康状态键
            pattern = "service_health:*"
            keys = redis.keys(pattern)
            
            if not keys:
                return {}
            
            # 批量获取所有服务状态
            values = redis.mget(keys)
            
            services = {}
            for key, value in zip(keys, values):
                if value:
                    try:
                        # 从键中提取服务名
                        service_name = key.replace("service_health:", "")
                        
                        # 解析JSON数据
                        data = json.loads(value)
                        health = ServiceHealth.from_dict(data)
                        
                        # Linus式修复：更合理的心跳超时时间（3倍心跳间隔 = 90秒）
                        heartbeat_timeout = 90  # 30秒心跳间隔的3倍
                        if (datetime.now() - health.last_heartbeat).total_seconds() > heartbeat_timeout:
                            health.status = ServiceStatus.UNKNOWN
                            health.error_message = "服务心跳超时"
                        
                        services[service_name] = health
                        
                    except Exception as e:
                        logger.error(f"解析服务状态失败 {key}: {e}")
            
            return services
            
        except Exception as e:
            logger.error(f"获取服务健康状态失败: {e}")
            return {}
    
    @staticmethod
    async def get_service_health(service_name: str) -> Optional[ServiceHealth]:
        """获取指定服务的健康状态"""
        services = await HealthCheckService.get_all_service_health()
        return services.get(service_name)
    
    @staticmethod
    async def get_system_summary() -> Dict[str, Any]:
        """获取系统状态摘要"""
        services = await HealthCheckService.get_all_service_health()
        
        total_services = len(services)
        healthy_services = sum(1 for s in services.values() if s.status == ServiceStatus.HEALTHY)
        unhealthy_services = sum(1 for s in services.values() if s.status == ServiceStatus.UNHEALTHY)
        unknown_services = sum(1 for s in services.values() if s.status == ServiceStatus.UNKNOWN)
        
        return {
            "total_services": total_services,
            "healthy_services": healthy_services,
            "unhealthy_services": unhealthy_services,
            "unknown_services": unknown_services,
            "health_ratio": healthy_services / total_services if total_services > 0 else 0,
            "services": {name: health.to_dict() for name, health in services.items()}
        }

# 创建全局健康监控实例的工厂函数
def create_health_monitor(service_name: str) -> HealthMonitor:
    """创建健康监控实例"""
    return HealthMonitor(service_name)