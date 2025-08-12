"""
统一的时区处理工具
所有获取当前时间的操作都应该使用这个模块
"""
from datetime import datetime, timezone
from typing import Optional

def get_current_time() -> datetime:
    """
    获取当前时间（UTC，无时区信息）
    数据库存储使用这个函数，确保一致性
    
    Returns:
        datetime: 当前UTC时间（无时区信息，适合数据库存储）
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)

def get_current_time_with_tz() -> datetime:
    """
    获取当前时间（UTC，带时区信息）
    用于需要时区感知的操作
    
    Returns:
        datetime: 当前UTC时间（带时区信息）
    """
    return datetime.now(timezone.utc)

def to_utc(dt: datetime) -> datetime:
    """
    将任意时间转换为UTC时间（无时区信息）
    
    Args:
        dt: 输入的datetime对象
        
    Returns:
        datetime: UTC时间（无时区信息）
    """
    if dt.tzinfo is not None:
        # 如果有时区信息，转换为UTC并移除时区
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    else:
        # 如果没有时区信息，假设已经是UTC
        return dt

def format_for_api(dt: Optional[datetime]) -> Optional[str]:
    """
    格式化时间用于API返回
    确保前端能正确解析为UTC时间
    
    Args:
        dt: datetime对象
        
    Returns:
        str: ISO格式的时间字符串，明确标记为UTC
    """
    if dt is None:
        return None
    
    # 如果没有时区信息，假设是UTC
    if dt.tzinfo is None:
        # 添加UTC时区信息后转换为ISO格式
        dt_with_tz = dt.replace(tzinfo=timezone.utc)
        return dt_with_tz.isoformat()
    else:
        # 有时区信息，直接转换
        return dt.isoformat()

def parse_telegram_time(telegram_dt: datetime) -> datetime:
    """
    处理Telegram消息的时间
    Telegram的date字段通常是带时区的UTC时间
    
    Args:
        telegram_dt: Telegram消息的date字段
        
    Returns:
        datetime: UTC时间（无时区信息，适合数据库存储）
    """
    if telegram_dt is None:
        return get_current_time()
    
    if hasattr(telegram_dt, 'tzinfo') and telegram_dt.tzinfo is not None:
        # 如果有时区信息，转换为UTC并移除时区
        return telegram_dt.astimezone(timezone.utc).replace(tzinfo=None)
    else:
        # 如果没有时区信息，假设已经是UTC
        return telegram_dt

# 为了向后兼容，提供一个简单的别名
now = get_current_time