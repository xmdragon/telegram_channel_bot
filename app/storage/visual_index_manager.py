"""
视觉哈希索引管理器
专门优化视觉相似度检测的性能问题
"""
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import redis

logger = logging.getLogger(__name__)


class VisualIndexManager:
    """视觉哈希专门索引管理器 - Linus式解决方案"""
    
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        
        # TTL设置：96小时 = 345600秒
        self.ttl_seconds = 96 * 60 * 60
        
        # 索引键名
        self.timeline_key = "visual:index:timeline"
        self.msg_prefix = "visual:msg:"
        self.hash_prefix = "visual:hash:"
        
    def add_visual_hash(self, channel_id: str, message_id: int, 
                       visual_hashes: dict, timestamp: Optional[datetime] = None) -> bool:
        """
        添加视觉哈希到索引
        
        Args:
            channel_id: 频道ID
            message_id: 消息ID
            visual_hashes: 视觉哈希字典
            timestamp: 时间戳（可选，默认当前时间）
            
        Returns:
            是否成功添加
        """
        try:
            if not visual_hashes:
                return False
            
            if timestamp is None:
                timestamp = datetime.utcnow()
            
            # 确保时间没有时区信息
            if hasattr(timestamp, 'tzinfo') and timestamp.tzinfo is not None:
                timestamp = timestamp.replace(tzinfo=None)
            
            # 序列化视觉哈希
            visual_hash_json = json.dumps(visual_hashes, ensure_ascii=False)
            message_key = f"{channel_id}:{message_id}"
            
            # 使用pipeline提高性能
            pipe = self.redis.pipeline()
            
            # 1. 添加到时间线索引
            score = timestamp.timestamp()
            member = f"{message_key}:{visual_hash_json}"
            pipe.zadd(self.timeline_key, {member: score})
            
            # 2. 缓存消息的视觉哈希（带TTL）
            msg_cache_key = f"{self.msg_prefix}{message_key}"
            pipe.setex(msg_cache_key, self.ttl_seconds, visual_hash_json)
            
            # 3. 为每个哈希值创建快速查找索引
            for hash_type, hash_value in visual_hashes.items():
                if hash_value and hash_type != 'sha256':  # 排除文件哈希
                    hash_index_key = f"{self.hash_prefix}{hash_type}:{hash_value}"
                    pipe.sadd(hash_index_key, message_key)
                    pipe.expire(hash_index_key, self.ttl_seconds)
            
            # 执行所有操作
            pipe.execute()
            
            logger.debug(f"✅ 视觉哈希索引已添加: {message_key}")
            return True
            
        except Exception as e:
            logger.error(f"添加视觉哈希索引失败: {e}")
            return False
    
    def get_recent_visual_hashes(self, time_threshold: datetime, 
                                exclude_message_id: Optional[int] = None,
                                limit: int = 100) -> List[Dict]:
        """
        获取指定时间后的所有视觉哈希（高性能版本）
        
        Args:
            time_threshold: 时间阈值
            exclude_message_id: 排除的消息ID
            limit: 限制返回数量
            
        Returns:
            包含视觉哈希的消息列表
        """
        try:
            # 确保时间没有时区信息
            if hasattr(time_threshold, 'tzinfo') and time_threshold.tzinfo is not None:
                time_threshold = time_threshold.replace(tzinfo=None)
            
            score_min = time_threshold.timestamp()
            score_max = datetime.utcnow().timestamp()
            
            # 🚀 Linus式优化：使用ZRANGEBYSCORE而不是扫描所有key
            timeline_members = self.redis.zrangebyscore(
                self.timeline_key, 
                score_min, 
                score_max,
                start=0,
                num=limit * 2  # 多获取一些，因为要过滤排除的消息
            )
            
            if not timeline_members:
                return []
            
            # 解析时间线成员
            message_keys = []
            for member in timeline_members[:limit]:
                try:
                    # 格式：{channel_id}:{message_id}:{visual_hash_json}
                    member_str = member.decode() if isinstance(member, bytes) else str(member)
                    parts = member_str.split(':', 2)  # 最多分割成3部分
                    if len(parts) >= 2:
                        channel_id = parts[0]
                        msg_id = int(parts[1])
                        
                        # 排除指定的消息ID
                        if exclude_message_id and msg_id == exclude_message_id:
                            continue
                        
                        message_keys.append(f"{channel_id}:{msg_id}")
                        
                except (ValueError, IndexError) as e:
                    logger.debug(f"解析时间线成员失败: {member}, 错误: {e}")
                    continue
            
            if not message_keys:
                return []
            
            # 🚀 批量获取视觉哈希缓存
            cache_keys = [f"{self.msg_prefix}{key}" for key in message_keys[:limit]]
            cached_hashes = self.redis.mget(cache_keys)
            
            # 构建结果
            results = []
            for i, (message_key, cached_hash) in enumerate(zip(message_keys[:limit], cached_hashes)):
                if not cached_hash:
                    continue
                
                try:
                    # 解析消息键
                    channel_id, message_id = message_key.split(':', 1)
                    
                    # 解析视觉哈希
                    if isinstance(cached_hash, bytes):
                        cached_hash = cached_hash.decode('utf-8')
                    
                    visual_hash = json.loads(cached_hash)
                    
                    results.append({
                        'channel_id': channel_id,
                        'message_id': int(message_id),
                        'visual_hash': visual_hash,
                        '_cache_key': cache_keys[i]
                    })
                    
                except (ValueError, json.JSONDecodeError) as e:
                    logger.debug(f"解析缓存哈希失败: {message_key}, 错误: {e}")
                    continue
            
            logger.debug(f"🔍 获取到 {len(results)} 个近期视觉哈希")
            return results
            
        except Exception as e:
            logger.error(f"获取近期视觉哈希失败: {e}")
            return []
    
    def find_similar_by_hash(self, hash_type: str, hash_value: str) -> List[str]:
        """
        根据特定哈希值快速查找相似消息
        
        Args:
            hash_type: 哈希类型（phash, dhash等）
            hash_value: 哈希值
            
        Returns:
            消息键列表
        """
        try:
            hash_index_key = f"{self.hash_prefix}{hash_type}:{hash_value}"
            members = self.redis.smembers(hash_index_key)
            
            return [member.decode() if isinstance(member, bytes) else str(member) 
                   for member in members]
            
        except Exception as e:
            logger.error(f"查找相似哈希失败: {e}")
            return []
    
    def cleanup_expired_data(self, cutoff_time: Optional[datetime] = None) -> int:
        """
        清理过期的视觉哈希数据
        
        Args:
            cutoff_time: 截止时间（默认96小时前）
            
        Returns:
            清理的条目数
        """
        try:
            if cutoff_time is None:
                cutoff_time = datetime.utcnow() - timedelta(seconds=self.ttl_seconds)
            
            # 确保时间没有时区信息
            if hasattr(cutoff_time, 'tzinfo') and cutoff_time.tzinfo is not None:
                cutoff_time = cutoff_time.replace(tzinfo=None)
            
            score_max = cutoff_time.timestamp()
            
            # 清理时间线索引中的过期数据
            removed_count = self.redis.zremrangebyscore(self.timeline_key, 0, score_max)
            
            if removed_count > 0:
                logger.info(f"🧹 清理了 {removed_count} 个过期的视觉哈希索引")
            
            return removed_count
            
        except Exception as e:
            logger.error(f"清理过期数据失败: {e}")
            return 0
    
    def get_index_stats(self) -> Dict:
        """获取索引统计信息"""
        try:
            # 时间线索引大小
            timeline_size = self.redis.zcard(self.timeline_key)
            
            # 计算时间范围
            oldest_score = None
            newest_score = None
            
            if timeline_size > 0:
                # 获取最旧和最新的分数
                oldest = self.redis.zrange(self.timeline_key, 0, 0, withscores=True)
                newest = self.redis.zrange(self.timeline_key, -1, -1, withscores=True)
                
                if oldest:
                    oldest_score = oldest[0][1]
                if newest:
                    newest_score = newest[0][1]
            
            # 统计哈希索引数量
            hash_index_count = 0
            try:
                hash_keys = self.redis.keys(f"{self.hash_prefix}*")
                hash_index_count = len(hash_keys)
            except:
                hash_index_count = "N/A"
            
            return {
                'timeline_size': timeline_size,
                'hash_index_count': hash_index_count,
                'oldest_timestamp': oldest_score,
                'newest_timestamp': newest_score,
                'time_span_hours': (newest_score - oldest_score) / 3600 if oldest_score and newest_score else 0,
                'ttl_hours': self.ttl_seconds / 3600
            }
            
        except Exception as e:
            logger.error(f"获取索引统计失败: {e}")
            return {'error': str(e)}
    
    def migrate_existing_visual_hashes(self, batch_size: int = 100) -> Dict:
        """
        迁移现有的视觉哈希到新索引（一次性迁移工具）
        
        Args:
            batch_size: 批次大小
            
        Returns:
            迁移统计信息
        """
        try:
            logger.info("🔄 开始迁移现有视觉哈希到新索引...")
            
            migrated = 0
            errors = 0
            
            # 扫描现有消息（使用SCAN避免阻塞）
            cursor = 0
            while True:
                cursor, keys = self.redis.scan(cursor, match="msg:*", count=batch_size)
                
                for key in keys:
                    try:
                        # 获取消息数据
                        message_data = self.redis.hgetall(key)
                        if not message_data or not message_data.get('visual_hash'):
                            continue
                        
                        # 解析消息键
                        key_str = key.decode() if isinstance(key, bytes) else str(key)
                        if not key_str.startswith('msg:'):
                            continue
                        
                        parts = key_str[4:].split(':', 1)  # 移除'msg:'前缀
                        if len(parts) != 2:
                            continue
                        
                        channel_id, message_id = parts
                        
                        # 解析视觉哈希
                        visual_hash_str = message_data.get('visual_hash')
                        if isinstance(visual_hash_str, bytes):
                            visual_hash_str = visual_hash_str.decode('utf-8')
                        
                        try:
                            visual_hashes = json.loads(visual_hash_str)
                        except:
                            # 尝试eval解析（兼容旧格式）
                            visual_hashes = eval(visual_hash_str)
                        
                        # 获取时间戳
                        created_at_str = message_data.get('created_at', '')
                        if created_at_str:
                            try:
                                timestamp = datetime.fromisoformat(created_at_str.replace('Z', '+00:00')).replace(tzinfo=None)
                            except:
                                timestamp = datetime.utcnow()
                        else:
                            timestamp = datetime.utcnow()
                        
                        # 添加到新索引
                        if self.add_visual_hash(channel_id, int(message_id), visual_hashes, timestamp):
                            migrated += 1
                        else:
                            errors += 1
                            
                    except Exception as e:
                        logger.debug(f"迁移消息失败: {key}, 错误: {e}")
                        errors += 1
                        continue
                
                # 检查是否完成
                if cursor == 0:
                    break
            
            result = {
                'migrated': migrated,
                'errors': errors,
                'total_processed': migrated + errors
            }
            
            logger.info(f"✅ 迁移完成: {result}")
            return result
            
        except Exception as e:
            logger.error(f"迁移失败: {e}")
            return {'error': str(e)}


# 懒加载全局实例
_visual_index_manager = None

def get_visual_index_manager(redis_client: Optional[redis.Redis] = None):
    """获取视觉索引管理器实例"""
    global _visual_index_manager
    if _visual_index_manager is None:
        if redis_client is None:
            from app.storage.redis_store import get_redis_message_store
            store = get_redis_message_store()
            redis_client = store.redis
        _visual_index_manager = VisualIndexManager(redis_client)
    return _visual_index_manager