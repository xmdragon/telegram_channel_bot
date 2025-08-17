"""
消息兼容性模块
桥接Redis数据格式与原有SQLAlchemy格式
"""
from datetime import datetime


class MessageCompat:
    """消息兼容类 - 桥接Redis数据格式与原有SQLAlchemy格式"""
    
    def __init__(self, redis_data: dict):
        self.data = redis_data
    
    @property
    def id(self):
        return self.data.get('message_id')
    
    @property
    def content(self):
        return self.data.get('content')
    
    @property
    def visual_hash(self):
        return self.data.get('visual_hash')
    
    @property
    def created_at(self):
        created_at_str = self.data.get('created_at')
        if created_at_str:
            try:
                # 解析ISO格式时间字符串
                dt = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
                # 返回无时区的UTC时间
                return dt.replace(tzinfo=None)
            except:
                pass
        return datetime.utcnow()
    
    @property
    def status(self):
        return self.data.get('status', 'pending')
    
    @property
    def media_hash(self):
        return self.data.get('media_hash')
    
    @property
    def combined_media_hash(self):
        return self.data.get('combined_media_hash')