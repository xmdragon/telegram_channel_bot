#!/usr/bin/env python3
"""
深度健康检查工具
提供详细的系统健康状态检查
"""

import asyncio
import sys
import json
import time
import redis
import requests
import psutil
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any

# 添加项目根目录到Python路径
PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import settings
from app.core.url_config import url_config

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class HealthChecker:
    """健康检查器"""

    def __init__(self):
        self.checks = []
        self.results = {}

    def add_check(self, name: str, func, critical: bool = True):
        """添加检查项"""
        self.checks.append({
            'name': name,
            'func': func,
            'critical': critical
        })

    async def run_all_checks(self) -> Dict[str, Any]:
        """运行所有检查"""
        results = {
            'timestamp': datetime.now().isoformat(),
            'overall_status': 'healthy',
            'checks': {},
            'summary': {
                'total': len(self.checks),
                'passed': 0,
                'failed': 0,
                'critical_failed': 0
            }
        }

        for check in self.checks:
            try:
                start_time = time.time()
                result = await check['func']()
                duration = time.time() - start_time

                check_result = {
                    'status': 'pass' if result['healthy'] else 'fail',
                    'message': result.get('message', ''),
                    'details': result.get('details', {}),
                    'duration': round(duration * 1000, 2),  # 转换为毫秒
                    'critical': check['critical']
                }

                results['checks'][check['name']] = check_result

                if check_result['status'] == 'pass':
                    results['summary']['passed'] += 1
                else:
                    results['summary']['failed'] += 1
                    if check['critical']:
                        results['summary']['critical_failed'] += 1

            except Exception as e:
                logger.error(f"检查 {check['name']} 失败: {e}")
                results['checks'][check['name']] = {
                    'status': 'error',
                    'message': f'检查异常: {str(e)}',
                    'critical': check['critical']
                }
                results['summary']['failed'] += 1
                if check['critical']:
                    results['summary']['critical_failed'] += 1

        # 确定整体状态
        if results['summary']['critical_failed'] > 0:
            results['overall_status'] = 'critical'
        elif results['summary']['failed'] > 0:
            results['overall_status'] = 'warning'

        return results

    async def check_web_service(self) -> Dict[str, Any]:
        """检查Web服务"""
        try:
            response = requests.get(
                f"http://localhost:{url_config.WEB_PORT}/api/health",
                timeout=5
            )

            if response.status_code == 200:
                return {
                    'healthy': True,
                    'message': 'Web服务正常',
                    'details': {
                        'status_code': response.status_code,
                        'response_time': response.elapsed.total_seconds() * 1000
                    }
                }
            else:
                return {
                    'healthy': False,
                    'message': f'Web服务返回错误状态: {response.status_code}',
                    'details': {'status_code': response.status_code}
                }

        except requests.exceptions.ConnectRefused:
            return {
                'healthy': False,
                'message': 'Web服务连接拒绝',
                'details': {'error': 'connection_refused'}
            }
        except requests.exceptions.Timeout:
            return {
                'healthy': False,
                'message': 'Web服务请求超时',
                'details': {'error': 'timeout'}
            }
        except Exception as e:
            return {
                'healthy': False,
                'message': f'Web服务检查异常: {str(e)}',
                'details': {'error': str(e)}
            }

    async def check_redis_service(self) -> Dict[str, Any]:
        """检查Redis服务"""
        try:
            r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

            # 测试连接
            start_time = time.time()
            pong = r.ping()
            ping_time = (time.time() - start_time) * 1000

            if pong:
                # 获取Redis信息
                info = r.info()
                return {
                    'healthy': True,
                    'message': 'Redis服务正常',
                    'details': {
                        'ping_time': round(ping_time, 2),
                        'version': info.get('redis_version'),
                        'memory_used': info.get('used_memory_human'),
                        'connected_clients': info.get('connected_clients')
                    }
                }
            else:
                return {
                    'healthy': False,
                    'message': 'Redis ping失败',
                    'details': {}
                }

        except redis.exceptions.ConnectionError:
            return {
                'healthy': False,
                'message': 'Redis连接失败',
                'details': {'error': 'connection_failed'}
            }
        except Exception as e:
            return {
                'healthy': False,
                'message': f'Redis检查异常: {str(e)}',
                'details': {'error': str(e)}
            }

    async def check_supervisor_process(self) -> Dict[str, Any]:
        """检查主管进程"""
        try:
            pid_file = PROJECT_ROOT / "logs/pids/dev_supervisor.pid"

            if not pid_file.exists():
                return {
                    'healthy': False,
                    'message': 'PID文件不存在',
                    'details': {'pid_file': str(pid_file)}
                }

            with open(pid_file) as f:
                pid = int(f.read().strip())

            # 检查进程是否存在
            if not psutil.pid_exists(pid):
                return {
                    'healthy': False,
                    'message': f'进程 {pid} 不存在',
                    'details': {'pid': pid}
                }

            # 获取进程信息
            proc = psutil.Process(pid)
            return {
                'healthy': True,
                'message': '主管进程运行正常',
                'details': {
                    'pid': pid,
                    'status': proc.status(),
                    'cpu_percent': proc.cpu_percent(),
                    'memory_mb': round(proc.memory_info().rss / 1024 / 1024, 1),
                    'create_time': datetime.fromtimestamp(proc.create_time()).isoformat()
                }
            }

        except FileNotFoundError:
            return {
                'healthy': False,
                'message': 'PID文件不存在或无法读取',
                'details': {}
            }
        except ValueError:
            return {
                'healthy': False,
                'message': 'PID文件格式错误',
                'details': {}
            }
        except psutil.NoSuchProcess:
            return {
                'healthy': False,
                'message': '主管进程已停止',
                'details': {}
            }
        except Exception as e:
            return {
                'healthy': False,
                'message': f'主管进程检查异常: {str(e)}',
                'details': {'error': str(e)}
            }

    async def check_service_activity(self) -> Dict[str, Any]:
        """检查服务活跃度"""
        try:
            r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

            services = ['collector', 'scheduler']
            activity_status = {}
            all_active = True

            for service in services:
                last_activity = r.get(f"service:{service}:last_activity")

                if not last_activity:
                    activity_status[service] = {
                        'status': 'unknown',
                        'message': '无活动记录'
                    }
                    continue

                try:
                    last_time = datetime.fromisoformat(last_activity)
                    now = datetime.now()
                    elapsed = now - last_time

                    if elapsed > timedelta(minutes=10):  # 超过10分钟认为不活跃
                        activity_status[service] = {
                            'status': 'inactive',
                            'message': f'超过 {elapsed} 无活动',
                            'last_activity': last_activity
                        }
                        all_active = False
                    else:
                        activity_status[service] = {
                            'status': 'active',
                            'message': f'最近活动: {elapsed} 前',
                            'last_activity': last_activity
                        }

                except ValueError:
                    activity_status[service] = {
                        'status': 'error',
                        'message': '时间戳格式错误'
                    }
                    all_active = False

            return {
                'healthy': all_active,
                'message': '所有服务活跃' if all_active else '部分服务不活跃',
                'details': activity_status
            }

        except Exception as e:
            return {
                'healthy': False,
                'message': f'服务活跃度检查异常: {str(e)}',
                'details': {'error': str(e)}
            }

    async def check_disk_space(self) -> Dict[str, Any]:
        """检查磁盘空间"""
        try:
            usage = psutil.disk_usage(str(PROJECT_ROOT))

            total_gb = usage.total / (1024**3)
            used_gb = usage.used / (1024**3)
            free_gb = usage.free / (1024**3)
            used_percent = (usage.used / usage.total) * 100

            # 磁盘使用率超过85%认为警告，超过95%认为严重
            if used_percent > 95:
                healthy = False
                message = f'磁盘空间严重不足: {used_percent:.1f}%'
            elif used_percent > 85:
                healthy = False
                message = f'磁盘空间不足: {used_percent:.1f}%'
            else:
                healthy = True
                message = f'磁盘空间充足: {used_percent:.1f}%'

            return {
                'healthy': healthy,
                'message': message,
                'details': {
                    'total_gb': round(total_gb, 1),
                    'used_gb': round(used_gb, 1),
                    'free_gb': round(free_gb, 1),
                    'used_percent': round(used_percent, 1)
                }
            }

        except Exception as e:
            return {
                'healthy': False,
                'message': f'磁盘空间检查异常: {str(e)}',
                'details': {'error': str(e)}
            }

    async def check_system_resources(self) -> Dict[str, Any]:
        """检查系统资源"""
        try:
            # CPU使用率
            cpu_percent = psutil.cpu_percent(interval=1)

            # 内存使用率
            memory = psutil.virtual_memory()

            # 负载平均值（Linux）
            if hasattr(psutil, 'getloadavg'):
                load_avg = psutil.getloadavg()
            else:
                load_avg = None

            # 判断健康状态
            issues = []
            if cpu_percent > 90:
                issues.append(f'CPU使用率过高: {cpu_percent:.1f}%')

            if memory.percent > 90:
                issues.append(f'内存使用率过高: {memory.percent:.1f}%')

            healthy = len(issues) == 0
            message = '系统资源正常' if healthy else '; '.join(issues)

            details = {
                'cpu_percent': round(cpu_percent, 1),
                'memory_percent': round(memory.percent, 1),
                'memory_available_gb': round(memory.available / (1024**3), 1)
            }

            if load_avg:
                details['load_average'] = [round(x, 2) for x in load_avg]

            return {
                'healthy': healthy,
                'message': message,
                'details': details
            }

        except Exception as e:
            return {
                'healthy': False,
                'message': f'系统资源检查异常: {str(e)}',
                'details': {'error': str(e)}
            }

async def main():
    """主函数"""
    checker = HealthChecker()

    # 添加检查项
    checker.add_check('web_service', checker.check_web_service, critical=True)
    checker.add_check('redis_service', checker.check_redis_service, critical=True)
    checker.add_check('supervisor_process', checker.check_supervisor_process, critical=True)
    checker.add_check('service_activity', checker.check_service_activity, critical=False)
    checker.add_check('disk_space', checker.check_disk_space, critical=False)
    checker.add_check('system_resources', checker.check_system_resources, critical=False)

    # 运行检查
    results = await checker.run_all_checks()

    # 输出结果
    if len(sys.argv) > 1 and sys.argv[1] == '--json':
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        # 人类可读格式
        print(f"=== 健康检查报告 ({results['timestamp']}) ===")
        print(f"整体状态: {results['overall_status'].upper()}")
        print(f"检查项: {results['summary']['passed']}/{results['summary']['total']} 通过")

        if results['summary']['failed'] > 0:
            print(f"失败项: {results['summary']['failed']} (严重: {results['summary']['critical_failed']})")

        print("\n详细结果:")
        for name, result in results['checks'].items():
            status_icon = "✅" if result['status'] == 'pass' else "❌" if result['critical'] else "⚠️"
            print(f"{status_icon} {name}: {result['message']} ({result.get('duration', 0)}ms)")

            if result.get('details') and len(sys.argv) > 1 and sys.argv[1] == '--verbose':
                for key, value in result['details'].items():
                    print(f"   {key}: {value}")

    # 返回适当的退出码
    if results['overall_status'] == 'critical':
        sys.exit(2)
    elif results['overall_status'] == 'warning':
        sys.exit(1)
    else:
        sys.exit(0)

if __name__ == "__main__":
    asyncio.run(main())