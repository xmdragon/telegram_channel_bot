"""
消息统计和计数Mixin
处理各种消息统计、计数和数据分析功能
"""
import logging
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class MessageStatsMixin:
    """消息统计和计数功能"""
    
    def get_message_count(self, channel_id: str = None, status: str = None) -> int:
        """获取消息计数"""
        try:
            if channel_id and status:
                key = f"msg:count:{channel_id}:{status}"
            elif channel_id:
                key = f"msg:count:{channel_id}:total"
            elif status:
                # 全局状态计数需要遍历所有频道
                pattern = f"msg:count:*:{status}"
                keys = self.redis.keys(pattern)
                total = 0
                for key in keys:
                    count = self.redis.get(key)
                    if count:
                        total += int(count)
                return total
            else:
                key = "msg:count:global:today"
            
            count = self.redis.get(key)
            return int(count) if count else 0
            
        except Exception as e:
            logger.error(f"获取消息计数失败: {e}")
            return 0