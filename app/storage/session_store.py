"""
会话存储操作模块
处理用户会话的存储、验证和管理
"""
import logging
from typing import Dict, List, Optional, Any
from app.utils.timezone import get_current_time
from .redis_client import RedisBaseStore

logger = logging.getLogger(__name__)

class RedisSessionStore(RedisBaseStore):
    """会话管理存储"""
    
    def save_session(self, token: str, session_data: Dict[str, Any], expire_seconds: int = 3600) -> bool:
        """保存会话"""
        try:
            session_key = f"session:{token}"
            session_json = self._serialize_json(session_data)
            
            # 设置会话数据和过期时间
            self.redis.setex(session_key, expire_seconds, session_json)
            
            # 更新最后活动时间
            self.redis.hset(f"session:activity", token, get_current_time().isoformat())
            
            logger.debug(f"会话已保存: {token}")
            return True
            
        except Exception as e:
            logger.error(f"保存会话失败 {token}: {e}")
            return False
    
    def get_session(self, token: str) -> Optional[Dict[str, Any]]:
        """获取会话"""
        try:
            session_key = f"session:{token}"
            session_data = self.redis.get(session_key)
            
            if not session_data:
                return None
            
            # 更新最后活动时间
            self.redis.hset(f"session:activity", token, get_current_time().isoformat())
            
            return self._deserialize_json(session_data)
            
        except Exception as e:
            logger.error(f"获取会话失败 {token}: {e}")
            return None
    
    def delete_session(self, token: str) -> bool:
        """删除会话"""
        try:
            session_key = f"session:{token}"
            self.redis.delete(session_key)
            self.redis.hdel("session:activity", token)
            
            logger.debug(f"会话已删除: {token}")
            return True
            
        except Exception as e:
            logger.error(f"删除会话失败 {token}: {e}")
            return False
    
    def get_active_sessions(self) -> List[str]:
        """获取所有活跃会话"""
        try:
            return [key.replace('session:', '') for key in self.redis.keys('session:*') 
                   if ':' in key and not key.endswith(':activity')]
        except Exception as e:
            logger.error(f"获取活跃会话失败: {e}")
            return []
    
    def extend_session(self, token: str, expire_seconds: int = 3600) -> bool:
        """延长会话过期时间"""
        try:
            session_key = f"session:{token}"
            if self.redis.exists(session_key):
                self.redis.expire(session_key, expire_seconds)
                # 更新最后活动时间
                self.redis.hset(f"session:activity", token, get_current_time().isoformat())
                logger.debug(f"会话已延长: {token}")
                return True
            return False
            
        except Exception as e:
            logger.error(f"延长会话失败 {token}: {e}")
            return False
    
    def session_exists(self, token: str) -> bool:
        """检查会话是否存在"""
        try:
            session_key = f"session:{token}"
            return self.redis.exists(session_key) > 0
        except Exception as e:
            logger.error(f"检查会话存在性失败 {token}: {e}")
            return False
    
    def get_session_activity(self, token: str) -> Optional[str]:
        """获取会话最后活动时间"""
        try:
            return self.redis.hget("session:activity", token)
        except Exception as e:
            logger.error(f"获取会话活动时间失败 {token}: {e}")
            return None
    
    def cleanup_expired_sessions(self) -> int:
        """清理过期的会话活动记录"""
        try:
            # Redis会自动删除过期的会话数据，这里只需要清理活动记录
            active_sessions = self.get_active_sessions()
            all_activity_tokens = self.redis.hkeys("session:activity")
            
            # 找出已经过期的会话活动记录
            expired_tokens = []
            for token in all_activity_tokens:
                session_key = f"session:{token}"
                if not self.redis.exists(session_key):
                    expired_tokens.append(token)
            
            # 批量删除过期的活动记录
            if expired_tokens:
                pipe = self.redis.pipeline()
                for token in expired_tokens:
                    pipe.hdel("session:activity", token)
                pipe.execute()
                
                logger.info(f"清理了 {len(expired_tokens)} 个过期会话活动记录")
                return len(expired_tokens)
            
            return 0
            
        except Exception as e:
            logger.error(f"清理过期会话失败: {e}")
            return 0
    
    def get_session_stats(self) -> Dict[str, Any]:
        """获取会话统计信息"""
        try:
            active_sessions = self.get_active_sessions()
            activity_count = len(self.redis.hkeys("session:activity"))
            
            return {
                'active_sessions': len(active_sessions),
                'activity_records': activity_count,
                'sessions': active_sessions[:10] if len(active_sessions) <= 10 else active_sessions[:10] + [f"... 还有{len(active_sessions) - 10}个"]
            }
            
        except Exception as e:
            logger.error(f"获取会话统计失败: {e}")
            return {
                'active_sessions': 0,
                'activity_records': 0,
                'sessions': []
            }