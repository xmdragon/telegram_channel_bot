"""
Supervisor服务管理器
提供与Supervisor交互的统一接口
"""
import xmlrpc.client
import logging
from typing import Dict, List, Any, Optional
from app.core.supervisor_config import SupervisorConfig

logger = logging.getLogger(__name__)

class SupervisorManager:
    """Supervisor服务管理器 - 单例模式"""

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self.server = None
        try:
            self.server = xmlrpc.client.ServerProxy(
                SupervisorConfig.get_xmlrpc_url()
            )
            # 测试连接
            self.server.supervisor.getState()
            self._initialized = True
            logger.info("Supervisor管理器初始化成功")
        except Exception as e:
            logger.error(f"连接Supervisor失败: {e}")
            logger.info("服务将以降级模式运行（无Supervisor管理功能）")

    def is_connected(self) -> bool:
        """检查连接状态"""
        if not self.server:
            return False
        try:
            state = self.server.supervisor.getState()
            return state['statename'] == 'RUNNING'
        except:
            return False

    def get_all_services_status(self) -> List[Dict[str, Any]]:
        """获取所有服务状态"""
        if not self.server:
            return self._get_fallback_status()

        try:
            processes = self.server.supervisor.getAllProcessInfo()
            result = []

            for p in processes:
                # 只返回telegram组的服务
                if p.get('group') == 'telegram':
                    short_name = SupervisorConfig.get_short_name(p['name'])
                    service_info = SupervisorConfig.SERVICE_INFO.get(short_name, {})

                    result.append({
                        'id': short_name,
                        'name': p['name'],
                        'display_name': service_info.get('display_name', p['name']),
                        'description': service_info.get('description', p.get('description', '')),
                        'status': self._map_status(p['statename']),
                        'pid': p.get('pid', 0),
                        'uptime': p['now'] - p['start'] if p.get('start') else 0,
                        'exitstatus': p.get('exitstatus', 0),
                        'spawnerr': p.get('spawnerr', '')
                    })

            return result
        except Exception as e:
            logger.error(f"获取服务状态失败: {e}")
            return self._get_fallback_status()

    def get_service_status(self, service_name: str) -> Optional[Dict[str, Any]]:
        """获取单个服务状态"""
        full_name = SupervisorConfig.get_service_name(service_name)

        if not self.server:
            return None

        try:
            info = self.server.supervisor.getProcessInfo(full_name)
            service_info = SupervisorConfig.SERVICE_INFO.get(service_name, {})

            return {
                'id': service_name,
                'name': full_name,
                'display_name': service_info.get('display_name', full_name),
                'description': service_info.get('description', ''),
                'status': self._map_status(info['statename']),
                'pid': info.get('pid', 0),
                'uptime': info['now'] - info['start'] if info.get('start') else 0,
                'exitstatus': info.get('exitstatus', 0),
                'spawnerr': info.get('spawnerr', '')
            }
        except Exception as e:
            logger.error(f"获取服务{full_name}状态失败: {e}")
            return None

    def start_service(self, service_name: str) -> bool:
        """启动服务"""
        full_name = SupervisorConfig.get_service_name(service_name)

        if not self.server:
            logger.warning(f"Supervisor未连接，无法启动服务{full_name}")
            return False

        try:
            result = self.server.supervisor.startProcess(full_name)
            logger.info(f"服务{full_name}启动成功: {result}")
            return True
        except xmlrpc.client.Fault as e:
            if e.faultCode == 60:  # ALREADY_STARTED
                logger.info(f"服务{full_name}已在运行")
                return True
            logger.error(f"启动服务{full_name}失败: {e.faultString}")
            return False
        except Exception as e:
            logger.error(f"启动服务{full_name}异常: {e}")
            return False

    def stop_service(self, service_name: str) -> bool:
        """停止服务"""
        full_name = SupervisorConfig.get_service_name(service_name)

        if not self.server:
            logger.warning(f"Supervisor未连接，无法停止服务{full_name}")
            return False

        try:
            result = self.server.supervisor.stopProcess(full_name)
            logger.info(f"服务{full_name}停止成功: {result}")
            return True
        except xmlrpc.client.Fault as e:
            if e.faultCode == 70:  # NOT_RUNNING
                logger.info(f"服务{full_name}未在运行")
                return True
            logger.error(f"停止服务{full_name}失败: {e.faultString}")
            return False
        except Exception as e:
            logger.error(f"停止服务{full_name}异常: {e}")
            return False

    def restart_service(self, service_name: str) -> bool:
        """重启服务"""
        full_name = SupervisorConfig.get_service_name(service_name)

        if not self.server:
            logger.warning(f"Supervisor未连接，无法重启服务{full_name}")
            return False

        try:
            # 先停止
            try:
                self.server.supervisor.stopProcess(full_name)
            except xmlrpc.client.Fault as e:
                if e.faultCode != 70:  # 忽略NOT_RUNNING错误
                    raise

            # 再启动
            result = self.server.supervisor.startProcess(full_name)
            logger.info(f"服务{full_name}重启成功: {result}")
            return True
        except Exception as e:
            logger.error(f"重启服务{full_name}失败: {e}")
            return False

    def get_service_logs(self, service_name: str, log_type: str = 'stdout',
                        offset: int = 0, length: int = 1000) -> str:
        """获取服务日志"""
        full_name = SupervisorConfig.get_service_name(service_name)

        # 如果服务在组中，需要使用 group:name 格式
        # telegram组中的服务需要加上组前缀
        if full_name.startswith('telegram_'):
            full_name = f'telegram:{full_name}'

        if not self.server:
            return "Supervisor未连接"

        try:
            if log_type == 'stdout':
                # 获取标准输出日志
                result = self.server.supervisor.tailProcessStdoutLog(
                    full_name, offset, length
                )
            else:
                # 获取错误日志
                result = self.server.supervisor.tailProcessStderrLog(
                    full_name, offset, length
                )

            # result是一个元组: (log_text, offset, overflow)
            if isinstance(result, tuple):
                return result[0] if result[0] else ""
            elif isinstance(result, list) and len(result) >= 1:
                return result[0] if result[0] else ""
            else:
                return str(result) if result else ""
        except Exception as e:
            logger.error(f"获取服务{full_name}日志失败: {e}")
            return f"获取日志失败: {str(e)}"

    def start_all_services(self) -> bool:
        """启动所有服务"""
        if not self.server:
            logger.warning("Supervisor未连接，无法启动所有服务")
            return False

        try:
            result = self.server.supervisor.startProcessGroup('telegram')
            logger.info(f"所有服务启动成功: {result}")
            return True
        except xmlrpc.client.Fault as e:
            if e.faultCode == 60:  # ALREADY_STARTED
                logger.info("所有服务已在运行")
                return True
            logger.error(f"启动所有服务失败: {e.faultString}")
            return False
        except Exception as e:
            logger.error(f"启动所有服务异常: {e}")
            return False

    def stop_all_services(self) -> bool:
        """停止所有服务"""
        if not self.server:
            logger.warning("Supervisor未连接，无法停止所有服务")
            return False

        try:
            result = self.server.supervisor.stopProcessGroup('telegram')
            logger.info(f"所有服务停止成功: {result}")
            return True
        except xmlrpc.client.Fault as e:
            if e.faultCode == 70:  # NOT_RUNNING
                logger.info("所有服务未在运行")
                return True
            logger.error(f"停止所有服务失败: {e.faultString}")
            return False
        except Exception as e:
            logger.error(f"停止所有服务异常: {e}")
            return False

    def reload_config(self) -> bool:
        """重新加载配置"""
        if not self.server:
            logger.warning("Supervisor未连接，无法重载配置")
            return False

        try:
            # 重新读取配置
            added, changed, removed = self.server.supervisor.reloadConfig()
            logger.info(f"配置重载完成 - 新增: {added}, 修改: {changed}, 删除: {removed}")

            # 更新受影响的服务
            for group in added:
                self.server.supervisor.addProcessGroup(group)
            for group in removed:
                self.server.supervisor.removeProcessGroup(group)

            return True
        except Exception as e:
            logger.error(f"重载配置失败: {e}")
            return False

    def _map_status(self, state: str) -> str:
        """映射Supervisor状态到简化状态"""
        status_map = {
            'RUNNING': 'running',
            'STOPPED': 'stopped',
            'STARTING': 'starting',
            'STOPPING': 'stopping',
            'FATAL': 'failed',
            'EXITED': 'stopped',
            'BACKOFF': 'restarting',
            'UNKNOWN': 'unknown'
        }
        return status_map.get(state, 'unknown')

    def _get_fallback_status(self) -> List[Dict[str, Any]]:
        """获取降级状态（Supervisor不可用时）"""
        result = []
        for short_name, full_name in SupervisorConfig.SERVICE_MAPPING.items():
            service_info = SupervisorConfig.SERVICE_INFO.get(short_name, {})
            result.append({
                'id': short_name,
                'name': full_name,
                'display_name': service_info.get('display_name', full_name),
                'description': service_info.get('description', ''),
                'status': 'unknown',
                'pid': 0,
                'uptime': 0,
                'exitstatus': 0,
                'spawnerr': 'Supervisor未连接'
            })
        return result

# 全局实例
supervisor_manager = SupervisorManager()