"""
统一日志配置模块 - 设计原则：消除特殊情况，统一管理

设计原则：
1. 单一真相源 - 所有日志配置集中管理
2. 零冗余 - 消除重复的日志输出
3. 信号优于噪音 - 只记录有价值的信息
"""

import os
import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Optional


# 直接定义路径，避免依赖PathConfig
LOGS_DIR = Path("./logs")
APP_LOG_FILE = LOGS_DIR / "app.log"
ERROR_LOG_FILE = LOGS_DIR / "error.log"


def setup_logging(
    service_name: str = "app",
    log_level: str = "INFO",
    console_output: bool = True
) -> None:
    """
    统一的日志配置函数 - 方案C：只使用标准输出

    Args:
        service_name: 服务名称，用于日志标识
        log_level: 日志级别 (DEBUG, INFO, WARNING, ERROR)
        console_output: 保留兼容性，现在总是输出到控制台
    """
    
    # 确保日志目录存在
    LOGS_DIR.mkdir(exist_ok=True)
    
    # 获取根日志器
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))
    
    # 清除现有处理器（避免重复）
    root_logger.handlers.clear()
    
    # 创建统一格式
    formatter = logging.Formatter(
        '[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # 控制台输出（标准输出，由supervisor捕获）
    import sys
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # 4. 调整第三方库日志级别 - 关键优化点
    _configure_third_party_loggers()
    
    logging.info(f"📝 日志系统初始化完成 - 服务: {service_name}, 级别: {log_level}")


def _configure_third_party_loggers():
    """
    配置第三方库的日志级别
    原则：只保留错误和关键警告，消除噪音
    """
    
    # Telethon - 最大的噪音源
    logging.getLogger('telethon').setLevel(logging.WARNING)
    logging.getLogger('telethon.client.updates').setLevel(logging.ERROR)  # 消除"Got difference"噪音
    logging.getLogger('telethon.network').setLevel(logging.WARNING)
    logging.getLogger('telethon.network.mtprotosender').setLevel(logging.WARNING)
    
    # SQLAlchemy - 数据库日志
    logging.getLogger('sqlalchemy').setLevel(logging.ERROR)
    logging.getLogger('sqlalchemy.engine').setLevel(logging.ERROR)
    logging.getLogger('sqlalchemy.pool').setLevel(logging.ERROR)
    logging.getLogger('sqlalchemy.orm').setLevel(logging.ERROR)
    
    # Web框架
    logging.getLogger('uvicorn.access').setLevel(logging.WARNING)
    logging.getLogger('uvicorn.error').setLevel(logging.WARNING)
    logging.getLogger('fastapi').setLevel(logging.WARNING)
    
    # HTTP客户端
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('httpcore').setLevel(logging.WARNING)
    logging.getLogger('aiohttp').setLevel(logging.WARNING)
    
    # 其他
    logging.getLogger('asyncio').setLevel(logging.WARNING)
    logging.getLogger('PIL').setLevel(logging.WARNING)
    logging.getLogger('multipart').setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """
    获取指定名称的日志器
    
    Args:
        name: 日志器名称（通常使用 __name__）
        
    Returns:
        配置好的日志器实例
    """
    return logging.getLogger(name)


