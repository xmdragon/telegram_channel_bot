"""
Supervisor服务统一配置管理
零硬编码，所有配置从环境变量或配置文件读取
"""
import os
from pathlib import Path
from typing import Dict, Any
from app.core.path_config import PathConfig

class SupervisorConfig:
    """Supervisor统一配置管理"""

    # Supervisor连接配置（从环境变量读取）
    SUPERVISOR_HOST = os.getenv('SUPERVISOR_HOST', '127.0.0.1')
    SUPERVISOR_PORT = int(os.getenv('SUPERVISOR_PORT', 9001))
    SUPERVISOR_USER = os.getenv('SUPERVISOR_USER', 'supervisor')
    SUPERVISOR_PASS = os.getenv('SUPERVISOR_PASS', 'tg_supervisor_2025')

    # XML-RPC连接URL
    @classmethod
    def get_xmlrpc_url(cls) -> str:
        """获取XML-RPC连接URL"""
        return f'http://{cls.SUPERVISOR_USER}:{cls.SUPERVISOR_PASS}@{cls.SUPERVISOR_HOST}:{cls.SUPERVISOR_PORT}/RPC2'

    # 服务名称映射（短名称 -> 完整名称）
    SERVICE_MAPPING = {
        'web': 'telegram_web',
        'collector': 'telegram_collector',
        'scheduler': 'telegram_scheduler'
    }

    # 服务显示信息
    SERVICE_INFO = {
        'web': {
            'display_name': 'Web服务',
            'description': 'FastAPI Web服务器'
        },
        'collector': {
            'display_name': 'Telegram采集器',
            'description': '消息采集服务'
        },
        'scheduler': {
            'display_name': '调度器',
            'description': '自动转发和清理'
        }
    }

    # 服务配置模板
    @classmethod
    def get_service_configs(cls) -> Dict[str, Dict[str, Any]]:
        """动态生成服务配置"""
        # 使用相对路径以便跨机器使用
        root_dir = Path(PathConfig.ROOT_DIR)

        # 检测虚拟环境
        venv_dir = root_dir / 'venv'
        venv_alt_dir = root_dir / '.venv'

        if venv_dir.exists():
            python_exe = './venv/bin/python3'
        elif venv_alt_dir.exists():
            python_exe = './.venv/bin/python3'
        else:
            # 如果没有虚拟环境，使用系统Python
            python_exe = 'python3'

        return {
            'telegram_web': {
                'command': f'{python_exe} ./web_server.py',
                'directory': '.',
                'autostart': 'true',
                'autorestart': 'true',
                'startretries': '3',
                'stderr_logfile': './logs/web_error.log',
                'stdout_logfile': './logs/web_output.log',
                'stdout_logfile_maxbytes': '10MB',
                'stdout_logfile_backups': '3',
                'stderr_logfile_maxbytes': '10MB',
                'stderr_logfile_backups': '3',
                'environment': 'HF_HUB_OFFLINE="1",PRODUCTION="false"',
                'priority': '10',
                'stopwaitsecs': '10'
            },
            'telegram_collector': {
                'command': f'{python_exe} ./message_collector.py',
                'directory': '.',
                'autostart': 'true',
                'autorestart': 'true',
                'startretries': '3',
                'stderr_logfile': './logs/collector_error.log',
                'stdout_logfile': './logs/collector_output.log',
                'stdout_logfile_maxbytes': '10MB',
                'stdout_logfile_backups': '3',
                'stderr_logfile_maxbytes': '10MB',
                'stderr_logfile_backups': '3',
                'environment': 'HF_HUB_OFFLINE="1"',
                'priority': '20',
                'stopwaitsecs': '10'
            },
            'telegram_scheduler': {
                'command': f'{python_exe} ./message_scheduler.py',
                'directory': '.',
                'autostart': 'true',
                'autorestart': 'true',
                'startretries': '3',
                'stderr_logfile': './logs/scheduler_error.log',
                'stdout_logfile': './logs/scheduler_output.log',
                'stdout_logfile_maxbytes': '10MB',
                'stdout_logfile_backups': '3',
                'stderr_logfile_maxbytes': '10MB',
                'stderr_logfile_backups': '3',
                'environment': 'HF_HUB_OFFLINE="1"',
                'priority': '30',
                'startsecs': '10',
                'stopwaitsecs': '10'
            }
        }

    @classmethod
    def get_service_name(cls, short_name: str) -> str:
        """获取完整服务名"""
        return cls.SERVICE_MAPPING.get(short_name, short_name)

    @classmethod
    def get_short_name(cls, full_name: str) -> str:
        """从完整名称获取短名称"""
        for short, full in cls.SERVICE_MAPPING.items():
            if full == full_name:
                return short
        return full_name

    @classmethod
    def generate_supervisor_conf(cls) -> str:
        """生成完整的Supervisor配置文件内容（包含supervisord主配置）"""
        conf_lines = []

        # 生成supervisord主配置 - 使用相对路径以便跨机器使用
        conf_lines.append('[unix_http_server]')
        conf_lines.append('file=./supervisor.sock')
        conf_lines.append('')

        conf_lines.append('[supervisord]')
        conf_lines.append('logfile=./logs/supervisord.log')
        conf_lines.append('logfile_maxbytes=50MB')
        conf_lines.append('logfile_backups=10')
        conf_lines.append('loglevel=info')
        conf_lines.append('pidfile=./supervisord.pid')
        conf_lines.append('nodaemon=false')
        conf_lines.append('minfds=1024')
        conf_lines.append('minprocs=200')
        conf_lines.append('')

        conf_lines.append('[rpcinterface:supervisor]')
        conf_lines.append('supervisor.rpcinterface_factory = supervisor.rpcinterface:make_main_rpcinterface')
        conf_lines.append('')

        conf_lines.append('[supervisorctl]')
        conf_lines.append('serverurl=unix://./supervisor.sock')
        conf_lines.append('')

        # 生成inet_http_server配置
        conf_lines.append('[inet_http_server]')
        conf_lines.append(f'port={cls.SUPERVISOR_HOST}:{cls.SUPERVISOR_PORT}')
        conf_lines.append(f'username={cls.SUPERVISOR_USER}')
        conf_lines.append(f'password={cls.SUPERVISOR_PASS}')
        conf_lines.append('')

        # 生成各服务配置
        service_configs = cls.get_service_configs()
        for service_name, config in service_configs.items():
            conf_lines.append(f'[program:{service_name}]')
            for key, value in config.items():
                conf_lines.append(f'{key}={value}')
            conf_lines.append('')

        # 生成服务组配置
        conf_lines.append('[group:telegram]')
        conf_lines.append('programs=telegram_web,telegram_collector,telegram_scheduler')
        conf_lines.append('')

        return '\n'.join(conf_lines)

    @classmethod
    def get_supervisor_conf_path(cls) -> Path:
        """获取Supervisor配置文件路径"""
        # 优先使用环境变量指定的路径
        custom_path = os.getenv('SUPERVISOR_CONF_PATH')
        if custom_path:
            return Path(custom_path)

        # 默认路径
        return Path('/etc/supervisor/conf.d/telegram_bot.conf')

    @classmethod
    def get_local_conf_path(cls) -> Path:
        """获取本地配置备份路径"""
        return PathConfig.ROOT_DIR / 'config' / 'supervisor.conf'