"""
消息维护和清理Mixin
处理索引清理、过期数据清理、数据一致性维护等功能
"""
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class MessageMaintenanceMixin:
    """消息维护和清理功能"""
    
    def cleanup_expired_indexes(self):
        """清理过期的索引"""
        try:
            # 清理今日计数器
            yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y%m%d')
            self.redis.delete(f"msg:count:global:today:{yesterday}")
            
            # 清理过期的状态索引（保留最近30天）
            cutoff_time = (datetime.now() - timedelta(days=30)).timestamp()
            
            for status in ['pending', 'approved', 'rejected']:
                self.redis.zremrangebyscore(f"msg:idx:{status}", 0, cutoff_time)
            
            logger.debug("索引清理完成")
            
        except Exception as e:
            logger.error(f"索引清理失败: {e}")
            
    def cleanup_invalid_indexes(self):
        """清理无效的索引条目（指向不存在消息的索引）"""
        try:
            logger.info("开始清理无效的索引条目...")
            cleaned_count = 0
            
            # 获取所有频道索引
            channel_indexes = self.redis.keys("msg:idx:-*")
            
            for index_key in channel_indexes:
                try:
                    # 获取频道ID
                    channel_id = index_key.decode('utf-8').replace("msg:idx:", "")
                    
                    # 获取该频道索引中的所有消息ID
                    msg_ids = self.redis.zrange(index_key, 0, -1)
                    invalid_ids = []
                    
                    # 检查每个消息是否存在
                    for msg_id in msg_ids:
                        msg_key = f"msg:{channel_id}:{msg_id.decode('utf-8')}"
                        if not self.redis.exists(msg_key):
                            invalid_ids.append(msg_id)
                    
                    # 批量删除无效索引
                    if invalid_ids:
                        pipe = self.redis.pipeline()
                        for invalid_id in invalid_ids:
                            pipe.zrem(index_key, invalid_id)
                        pipe.execute()
                        cleaned_count += len(invalid_ids)
                        logger.debug(f"从 {channel_id} 清理了 {len(invalid_ids)} 个无效索引")
                        
                except Exception as e:
                    logger.warning(f"清理索引 {index_key} 时出错: {e}")
                    continue
            
            # 清理状态索引
            for status in ['pending', 'approved', 'rejected']:
                try:
                    status_keys = self.redis.zrange(f"msg:idx:{status}", 0, -1)
                    invalid_keys = []
                    
                    for key in status_keys:
                        try:
                            channel_id, message_id = key.decode('utf-8').split(':', 1)
                            msg_key = f"msg:{channel_id}:{message_id}"
                            if not self.redis.exists(msg_key):
                                invalid_keys.append(key)
                        except ValueError:
                            invalid_keys.append(key)  # 格式错误的键也删除
                    
                    if invalid_keys:
                        pipe = self.redis.pipeline()
                        for invalid_key in invalid_keys:
                            pipe.zrem(f"msg:idx:{status}", invalid_key)
                        pipe.execute()
                        cleaned_count += len(invalid_keys)
                        logger.debug(f"从状态索引 {status} 清理了 {len(invalid_keys)} 个无效条目")
                        
                except Exception as e:
                    logger.warning(f"清理状态索引 {status} 时出错: {e}")
            
            if cleaned_count > 0:
                logger.info(f"索引清理完成，共清理了 {cleaned_count} 个无效条目")
            else:
                logger.debug("没有发现需要清理的无效索引条目")
                
        except Exception as e:
            logger.error(f"清理无效索引失败: {e}")