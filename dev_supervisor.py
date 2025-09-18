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
from datetime import datetime, timedelta
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
    max_restarts: int = 3  # 最大重启次数
    restart_window: int = 300  # 重启次数统计窗口（秒）

class ServiceProcess:
    """服务进程管理"""
    
    def __init__(self, config: ServiceConfig):
        self.config = config
        self.process: Optional[subprocess.Popen] = None
        self.status = ServiceStatus.STOPPED
        self.start_time: Optional[datetime] = None
        self.restart_count = 0
        self.last_restart_time: Optional[datetime] = None
        self.restart_history: List[datetime] = []  # 重启历史
        
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
        import asyncio

        # Web服务需要更多时间来启动Gunicorn + FastAPI
        if self.config.name == "web":
            await asyncio.sleep(3.0)  # Web服务给更多启动时间
        else:
            await asyncio.sleep(0.5)  # 其他服务保持原有时间

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
                    logger.error(f"❌ 服务 {self.config.name} 启动失败")
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
            # 进程仍在运行，进行深度健康检查
            return self._deep_health_check()
        else:
            # 进程已退出
            logger.warning(f"服务 {self.config.name} 意外退出 (退出码: {poll_result})")
            self.status = ServiceStatus.FAILED
            return False

    def _deep_health_check(self) -> bool:
        """深度健康检查"""
        try:
            import psutil

            # 获取进程信息
            try:
                proc = psutil.Process(self.process.pid)

                # 检查进程状态
                if proc.status() == psutil.STATUS_ZOMBIE:
                    logger.warning(f"服务 {self.config.name} 进程状态异常: ZOMBIE")
                    return False

                # 检查CPU和内存使用
                cpu_percent = proc.cpu_percent(interval=0.1)
                memory_info = proc.memory_info()
                memory_mb = memory_info.rss / 1024 / 1024  # 转换为MB

                # 检查异常高CPU使用率（持续超过90%视为异常）
                if hasattr(self, '_high_cpu_count'):
                    if cpu_percent > 90:
                        self._high_cpu_count += 1
                        if self._high_cpu_count > 3:  # 连续3次检查都高CPU
                            logger.warning(f"服务 {self.config.name} CPU使用率异常: {cpu_percent:.1f}%")
                            return False
                    else:
                        self._high_cpu_count = 0
                else:
                    self._high_cpu_count = 0

                # 检查内存使用（超过1GB视为异常）
                if memory_mb > 1024:
                    logger.warning(f"服务 {self.config.name} 内存使用异常: {memory_mb:.1f}MB")
                    return False

                # 应用级健康检查
                return self._app_health_check()

            except psutil.NoSuchProcess:
                logger.warning(f"服务 {self.config.name} 进程不存在")
                return False

        except ImportError:
            # psutil未安装，降级为基础检查
            return True
        except Exception as e:
            logger.error(f"深度健康检查失败 {self.config.name}: {e}")
            return True  # 检查失败时假设健康，避免误杀

    def _app_health_check(self) -> bool:
        """应用级健康检查"""
        try:
            if self.config.name == "web":
                # Web服务健康检查 - HTTP请求
                try:
                    import requests
                    import time
                except ImportError:
                    logger.warning("requests 模块未安装，跳过Web健康检查")
                    return True  # 没有 requests 模块时假设健康，避免误重启

                # 限制检查频率（每30秒检查一次）
                if not hasattr(self, '_last_web_check'):
                    self._last_web_check = 0

                current_time = time.time()
                if current_time - self._last_web_check < 30:
                    return True  # 跳过本次检查

                self._last_web_check = current_time

                try:
                    response = requests.get(
                        f"http://localhost:{url_config.WEB_PORT}/api/health",
                        timeout=5
                    )
                    return response.status_code == 200
                except:
                    logger.warning(f"Web服务健康检查失败 - API无响应")
                    return False

            elif self.config.name == "collector":
                # Collector服务检查 - 检查进程活跃度
                return self._check_activity_timestamp("collector")

            elif self.config.name == "scheduler":
                # Scheduler服务检查 - 检查任务执行时间戳
                return self._check_activity_timestamp("scheduler")

            return True

        except Exception as e:
            logger.error(f"应用级健康检查失败 {self.config.name}: {e}")
            return True  # 检查失败时假设健康

    def _check_activity_timestamp(self, service_name: str) -> bool:
        """检查服务活跃时间戳"""
        try:
            import redis
            from datetime import datetime, timedelta

            # 连接Redis检查活跃时间戳
            r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

            # 获取最后活跃时间戳
            last_activity = r.get(f"service:{service_name}:last_activity")

            if not last_activity:
                # 如果没有时间戳，可能服务刚启动
                return True

            # 解析时间戳
            last_time = datetime.fromisoformat(last_activity)
            now = datetime.now()

            # 如果超过5分钟没有活动，认为服务可能卡住
            if now - last_time > timedelta(minutes=5):
                logger.warning(f"服务 {service_name} 超过5分钟无活动")
                return False

            return True

        except Exception as e:
            logger.debug(f"活跃时间戳检查失败 {service_name}: {e}")
            return True  # 检查失败时假设健康

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
                    "--timeout", "1800",
                    "--graceful-timeout", "30",
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
                                if await self._should_restart_service(service):
                                    await self._restart_service_with_strategy(service)
                                else:
                                    logger.error(f"服务 {service.config.name} 达到最大重启次数，标记为失败")
                                    service.status = ServiceStatus.FAILED

                # 更新状态文件
                await self.update_status_file()

            except Exception as e:
                logger.error(f"健康检查出错: {e}")

            await asyncio.sleep(5)  # 每5秒检查一次

    async def _should_restart_service(self, service: ServiceProcess) -> bool:
        """判断是否应该重启服务"""
        now = datetime.now()

        # 清理过期的重启历史（超出时间窗口的记录）
        window_start = now - timedelta(seconds=service.config.restart_window)
        service.restart_history = [
            restart_time for restart_time in service.restart_history
            if restart_time > window_start
        ]

        # 检查在时间窗口内的重启次数
        recent_restarts = len(service.restart_history)

        if recent_restarts >= service.config.max_restarts:
            logger.warning(f"服务 {service.config.name} 在 {service.config.restart_window}秒内已重启 {recent_restarts} 次，超过限制")
            return False

        return True

    async def _restart_service_with_strategy(self, service: ServiceProcess) -> None:
        """使用智能策略重启服务"""
        now = datetime.now()

        # 记录重启历史
        service.restart_history.append(now)
        service.restart_count += 1
        service.last_restart_time = now

        # 计算智能延迟（递增延迟策略）
        recent_restarts = len(service.restart_history)
        if recent_restarts == 1:
            delay = service.config.restart_delay  # 第一次：5秒
        elif recent_restarts == 2:
            delay = service.config.restart_delay * 6  # 第二次：30秒
        else:
            delay = service.config.restart_delay * 12  # 第三次：60秒

        logger.warning(f"服务 {service.config.name} 异常退出，{delay}秒后重启 (第{service.restart_count}次)")

        # 先停止服务
        await service.stop(timeout=5)

        # 等待重启延迟
        await asyncio.sleep(delay)

        # 重新启动
        success = await service.start()
        if success:
            logger.info(f"✅ 服务 {service.config.name} 重启成功")
        else:
            logger.error(f"❌ 服务 {service.config.name} 重启失败")
    
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