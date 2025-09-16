#!/usr/bin/env python3
"""
开发环境进程管理器
管理Web服务、Telegram采集、消息调度等多个服务进程
"""
import asyncio
import signal
import sys
import subprocess
import time
import logging
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum
from app.core.url_config import url_config
from app.core.config import settings
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

class ServiceStatus(Enum):
    """服务状态"""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    FAILED = "failed"

@dataclass
class ServiceConfig:
    """服务配置"""
    name: str
    command: List[str]
    description: str
    enabled: bool = True
    auto_restart: bool = True
    restart_delay: int = 5  # 重启延迟秒数

class ServiceProcess:
    """服务进程管理"""
    
    def __init__(self, config: ServiceConfig):
        self.config = config
        self.process: Optional[subprocess.Popen] = None
        self.status = ServiceStatus.STOPPED
        self.start_time: Optional[datetime] = None
        self.restart_count = 0
        self.last_restart_time: Optional[datetime] = None
        
    @property
    def uptime(self) -> Optional[str]:
        """运行时间"""
        if not self.start_time or self.status != ServiceStatus.RUNNING:
            return None
        
        uptime_seconds = (datetime.now() - self.start_time).total_seconds()
        hours = int(uptime_seconds // 3600)
        minutes = int((uptime_seconds % 3600) // 60)
        seconds = int(uptime_seconds % 60)
        
        if hours > 0:
            return f"{hours}h {minutes}m {seconds}s"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"
    
    def _check_port_available(self, port: int) -> bool:
        """检查端口是否可用"""
        import socket
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(1)
                result = sock.connect_ex(('localhost', port))
                return result != 0  # 0表示连接成功，即端口被占用
        except Exception:
            return True  # 假设可用
    
    async def _wait_for_service_ready(self) -> bool:
        """等待服务真正就绪"""
        if self.config.name == "web":
            # Web服务需要等待HTTP端点可用
            import urllib.request
            import asyncio
            
            for attempt in range(12):  # 最多等待12次，每次间隔1秒 = 12秒
                try:
                    # 使用asyncio.to_thread来包装同步的urllib.request
                    def check_health():
                        req = urllib.request.Request(url_config.get_health_url())
                        response = urllib.request.urlopen(req, timeout=2.0)  # 增加单次请求超时
                        return response.getcode() == 200
                    
                    if await asyncio.to_thread(check_health):
                        logger.info(f"✅ Web服务健康检查通过 (尝试第{attempt + 1}次)")
                        return True
                except:
                    pass
                await asyncio.sleep(1.0)  # 增加检查间隔，给Web服务更多启动时间
            
            logger.error("❌ Web服务健康检查超时")
            return False
        else:
            # 其他服务只需要检查进程存在
            import asyncio
            await asyncio.sleep(0.3)  # 进一步减少非Web服务等待时间
            return self.process.poll() is None
    
    async def start(self) -> bool:
        """启动服务"""
        if self.status in [ServiceStatus.STARTING, ServiceStatus.RUNNING]:
            logger.warning(f"服务 {self.config.name} 已在运行中")
            return True
        
        # Web服务启动前检查端口
        if self.config.name == "web" and not self._check_port_available(settings.WEB_PORT):
            logger.error(f"端口 {settings.WEB_PORT} 已被占用，无法启动Web服务")
            logger.error("请检查是否有其他实例正在运行，或使用 ./stop.sh 停止现有服务")
            self.status = ServiceStatus.FAILED
            return False
            
        logger.info(f"启动服务: {self.config.name}")
        self.status = ServiceStatus.STARTING
        
        try:
            # 🚀 修复: 设置环境变量，确保使用离线模式
            import os
            env = os.environ.copy()
            env['HF_HUB_OFFLINE'] = '1'  # 强制使用HuggingFace离线模式
            
            # 启动进程
            self.process = subprocess.Popen(
                self.config.command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=".",
                env=env  # 传递包含离线模式的环境变量
            )
            
            # 等待服务真正就绪（包含健康检查）
            if await self._wait_for_service_ready():
                self.status = ServiceStatus.RUNNING
                self.start_time = datetime.now()
                logger.info(f"✅ 服务 {self.config.name} 启动成功 (PID: {self.process.pid})")
                return True
            else:
                # 服务未就绪
                if self.process.poll() is not None:
                    returncode = self.process.returncode
                    
                    # 特殊处理：collector服务退出码0可能是配置禁用导致的正常退出
                    if self.config.name == "collector" and returncode == 0:
                        logger.info(f"📋 Collector服务正常退出 (可能因配置禁用)")
                        self.status = ServiceStatus.STOPPED
                        return True
                    else:
                        self.status = ServiceStatus.FAILED
                        logger.error(f"❌ 服务 {self.config.name} 进程已退出 (退出码: {returncode})")
                        return False
                else:
                    self.status = ServiceStatus.FAILED
                    logger.error(f"❌ 服务 {self.config.name} 健康检查失败")
                    return False
                
        except Exception as e:
            self.status = ServiceStatus.FAILED
            logger.error(f"❌ 启动服务 {self.config.name} 时出错: {e}")
            return False
    
    async def stop(self, timeout: int = 10) -> bool:
        """停止服务"""
        if self.status == ServiceStatus.STOPPED:
            return True
            
        if not self.process:
            self.status = ServiceStatus.STOPPED
            return True
            
        logger.info(f"停止服务: {self.config.name}")
        self.status = ServiceStatus.STOPPING
        
        try:
            # 发送 SIGTERM
            self.process.terminate()
            
            # 等待进程结束
            try:
                await asyncio.wait_for(
                    asyncio.to_thread(self.process.wait),
                    timeout=timeout
                )
                logger.info(f"✅ 服务 {self.config.name} 已停止")
            except asyncio.TimeoutError:
                # 超时，强制杀死
                logger.warning(f"服务 {self.config.name} 超时未响应，强制终止")
                self.process.kill()
                await asyncio.to_thread(self.process.wait)
                
            self.status = ServiceStatus.STOPPED
            self.start_time = None
            return True
            
        except Exception as e:
            logger.error(f"❌ 停止服务 {self.config.name} 时出错: {e}")
            self.status = ServiceStatus.FAILED
            return False
    
    def check_health(self) -> bool:
        """检查服务健康状态"""
        if not self.process:
            return False
            
        # 检查进程是否还在运行
        poll_result = self.process.poll()
        if poll_result is None:
            # 进程仍在运行
            return True
        else:
            # 进程已退出
            logger.warning(f"服务 {self.config.name} 意外退出 (退出码: {poll_result})")
            self.status = ServiceStatus.FAILED
            return False

class DevSupervisor:
    """开发环境进程管理器"""
    
    def __init__(self):
        self.services: Dict[str, ServiceProcess] = {}
        self.running = False
        self.status_file = Path("logs/supervisor_status.json")
        
        # 定义服务配置
        self.service_configs = {
            "web": ServiceConfig(
                name="web",
                command=[
                    "venv/bin/gunicorn", "web_server:app",
                    "--bind", "0.0.0.0:8008",
                    "--workers", "1",
                    "--worker-class", "uvicorn.workers.UvicornWorker",
                    "--max-requests", "500",
                    "--max-requests-jitter", "50",
                    "--timeout", "60",
                    "--graceful-timeout", "10",
                    "--worker-connections", "100",
                    "--preload",
                    "--access-logfile", "logs/gunicorn_access.log",
                    "--error-logfile", "logs/gunicorn_error.log",
                    "--log-level", "info"
                ],
                description="Web服务器 (Gunicorn + UvicornWorker - 稳定模式)"
            ),
            "collector": ServiceConfig(
                name="collector", 
                command=["venv/bin/python3", "message_collector.py"],
                description="Telegram消息采集服务"
            ),
            "scheduler": ServiceConfig(
                name="scheduler",
                command=["venv/bin/python3", "message_scheduler.py"], 
                description="消息调度服务 (自动转发、数据清理)"
            ),
        }
        
        # 初始化服务进程
        for config in self.service_configs.values():
            self.services[config.name] = ServiceProcess(config)
    
    async def start_service(self, service_name: str) -> bool:
        """启动单个服务"""
        if service_name not in self.services:
            logger.error(f"未知服务: {service_name}")
            return False
            
        service = self.services[service_name]
        return await service.start()
    
    async def stop_service(self, service_name: str) -> bool:
        """停止单个服务"""
        if service_name not in self.services:
            logger.error(f"未知服务: {service_name}")
            return False
            
        service = self.services[service_name]
        return await service.stop()
    
    async def restart_service(self, service_name: str) -> bool:
        """重启单个服务"""
        logger.info(f"重启服务: {service_name}")
        service = self.services[service_name]
        
        if await service.stop():
            await asyncio.sleep(2)  # 等待清理
            return await service.start()
        return False
    
    async def start_all_services(self, service_names: List[str] = None) -> None:
        """启动所有服务或指定服务 - Web服务最后启动"""
        if service_names is None:
            service_names = list(self.services.keys())
        
        # 重新排序：先启动非Web服务，Web服务放最后
        ordered_services = []
        web_services = []
        
        for service_name in service_names:
            if service_name == "web":
                web_services.append(service_name)
            else:
                ordered_services.append(service_name)
        
        # Web服务放最后
        ordered_services.extend(web_services)
        
        logger.info(f"启动服务: {', '.join(ordered_services)}")
        
        for service_name in ordered_services:
            if service_name in self.services:
                config = self.services[service_name].config
                if config.enabled:
                    await self.start_service(service_name)
                    # Web服务启动前多等待一些时间
                    if service_name == "web":
                        await asyncio.sleep(1.0)  # Web服务启动前额外等待
                    else:
                        await asyncio.sleep(0.1)
    
    async def stop_all_services(self) -> None:
        """停止所有服务"""
        logger.info("停止所有服务...")
        
        # 并行停止所有服务
        stop_tasks = []
        for service in self.services.values():
            if service.status == ServiceStatus.RUNNING:
                stop_tasks.append(service.stop())
        
        if stop_tasks:
            await asyncio.gather(*stop_tasks, return_exceptions=True)
    
    async def health_check_loop(self) -> None:
        """健康检查循环"""
        while self.running:
            try:
                for service in self.services.values():
                    if service.status == ServiceStatus.RUNNING:
                        if not service.check_health():
                            # 服务异常，检查是否需要重启
                            if service.config.auto_restart:
                                service.restart_count += 1
                                service.last_restart_time = datetime.now()
                                logger.warning(f"服务 {service.config.name} 异常退出，尝试重启 (第{service.restart_count}次)")
                                
                                await asyncio.sleep(service.config.restart_delay)
                                await service.start()
                
                # 更新状态文件
                await self.update_status_file()
                
            except Exception as e:
                logger.error(f"健康检查出错: {e}")
            
            await asyncio.sleep(5)  # 每5秒检查一次
    
    async def update_status_file(self) -> None:
        """更新状态文件"""
        try:
            status_data = {
                "timestamp": datetime.now().isoformat(),
                "services": {}
            }
            
            for name, service in self.services.items():
                status_data["services"][name] = {
                    "status": service.status.value,
                    "uptime": service.uptime,
                    "restart_count": service.restart_count,
                    "last_restart": service.last_restart_time.isoformat() if service.last_restart_time else None,
                    "pid": service.process.pid if service.process else None
                }
            
            # 确保日志目录存在
            self.status_file.parent.mkdir(exist_ok=True)
            
            with open(self.status_file, 'w', encoding='utf-8') as f:
                json.dump(status_data, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            logger.error(f"更新状态文件失败: {e}")
    
    def print_status(self) -> None:
        """打印服务状态"""
        print("\\n" + "="*80)
        print(f"{'服务名称':<15} {'状态':<10} {'运行时间':<15} {'重启次数':<8} {'描述'}")
        print("-"*80)
        
        for name, service in self.services.items():
            status_emoji = {
                ServiceStatus.RUNNING: "🟢",
                ServiceStatus.STARTING: "🟡", 
                ServiceStatus.STOPPING: "🟡",
                ServiceStatus.STOPPED: "⚪",
                ServiceStatus.FAILED: "🔴"
            }
            
            uptime_str = service.uptime or "-"
            restart_count_str = str(service.restart_count) if service.restart_count > 0 else "-"
            
            print(f"{name:<15} {status_emoji[service.status]} {service.status.value:<8} {uptime_str:<15} {restart_count_str:<8} {service.config.description}")
        
        print("="*80)
    
    def print_status_from_data(self, services_data: Dict[str, Any]) -> None:
        """从状态数据打印服务状态"""
        print("\\n" + "="*80)
        print(f"{'服务名称':<15} {'状态':<10} {'运行时间':<15} {'重启次数':<8} {'描述'}")
        print("-"*80)
        
        status_emoji = {
            "running": "🟢",
            "starting": "🟡", 
            "stopping": "🟡",
            "stopped": "⚪",
            "failed": "🔴"
        }
        
        # 确保显示所有服务，包括没有状态数据的
        all_services = set(self.service_configs.keys()) | set(services_data.keys())
        
        for service_name in sorted(all_services):
            service_data = services_data.get(service_name, {})
            config = self.service_configs.get(service_name)
            
            if not config:
                continue
                
            status = service_data.get('status', 'stopped')
            uptime = service_data.get('uptime', '-')
            restart_count = service_data.get('restart_count', 0)
            
            uptime_str = uptime if uptime else "-"
            restart_count_str = str(restart_count) if restart_count > 0 else "-"
            
            print(f"{service_name:<15} {status_emoji.get(status, '⚪')} {status:<8} {uptime_str:<15} {restart_count_str:<8} {config.description}")
        
        print("="*80)
    
    async def run(self, service_names: List[str] = None) -> None:
        """运行管理器"""
        self.running = True
        
        # 注册信号处理
        def signal_handler(signum, frame):
            logger.info(f"收到信号 {signum}，正在关闭...")
            self.running = False
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        try:
            # 启动服务
            await self.start_all_services(service_names)
            
            # 启动健康检查
            health_task = asyncio.create_task(self.health_check_loop())
            
            # 主循环
            while self.running:
                await asyncio.sleep(1)
            
            # 停止健康检查
            health_task.cancel()
            
            # 停止所有服务
            await self.stop_all_services()
            
        except Exception as e:
            logger.error(f"管理器运行出错: {e}")
        finally:
            logger.info("开发环境管理器已退出")

async def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="开发环境进程管理器")
    parser.add_argument("services", nargs="*", choices=["web", "collector", "scheduler", "processor", "all"], 
                       help="要启动的服务")
    parser.add_argument("--status", action="store_true", help="显示服务状态")
    
    args = parser.parse_args()
    
    supervisor = DevSupervisor()
    
    if args.status:
        # 读取状态文件并显示
        try:
            if supervisor.status_file.exists():
                with open(supervisor.status_file, 'r', encoding='utf-8') as f:
                    status_data = json.load(f)
                print(f"\\n状态更新时间: {status_data['timestamp']}")
                supervisor.print_status_from_data(status_data['services'])
            else:
                print("未找到状态文件，请先启动服务")
        except Exception as e:
            logger.error(f"读取状态失败: {e}")
        return
    
    # 确定要启动的服务
    service_names = None
    if args.services:
        if "all" not in args.services:
            service_names = args.services
    else:
        # 如果没有指定服务，默认启动所有服务
        service_names = None
    
    logger.info("🚀 启动开发环境管理器...")
    await supervisor.run(service_names)

if __name__ == "__main__":
    asyncio.run(main())