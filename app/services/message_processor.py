"""
消息处理服务
"""
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from app.storage.redis_store import get_redis_message_store, RedisMessageStore
from .duplicate_detector import DuplicateDetector

logger = logging.getLogger(__name__)

class MessageProcessor:
    """消息处理器"""
    
    def __init__(self):
        self.duplicate_detector = DuplicateDetector()
        self.redis_store = None  # 延迟初始化
    
    async def get_pending_messages(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取待审核的消息"""
        try:
            if self.redis_store is None:
                try:
                    self.redis_store = get_redis_message_store()
                except RuntimeError:
                    return []
            return self.redis_store.get_pending_messages(limit=limit)
        except Exception as e:
            logger.error(f"获取待审核消息失败: {e}")
            return []
    
    async def get_auto_forward_messages(self) -> List[Dict[str, Any]]:
        """获取需要自动转发的消息"""
        try:
            # 确保redis_store已初始化
            if self.redis_store is None:
                try:
                    self.redis_store = get_redis_message_store()
                except RuntimeError:
                    return []
            
            # 获取自动转发延迟配置
            from app.services.config_manager import ConfigManager
            config_manager = ConfigManager()
            auto_forward_delay = await config_manager.get_config('review.auto_forward_delay', 1800)  # 默认30分钟
            
            cutoff_time = datetime.utcnow() - timedelta(seconds=auto_forward_delay)
            
            # 获取所有待审核消息
            pending_messages = self.redis_store.get_pending_messages(limit=500)
            
            # 过滤出需要自动转发的消息
            auto_forward_messages = []
            for msg in pending_messages:
                try:
                    # 检查创建时间
                    created_at_str = msg.get('created_at')
                    if created_at_str:
                        created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
                        if created_at.replace(tzinfo=None) <= cutoff_time:
                            # 检查是否为非广告消息
                            is_ad = msg.get('is_ad', False)
                            if isinstance(is_ad, str):
                                is_ad = is_ad.lower() == 'true'
                            
                            if not is_ad:
                                auto_forward_messages.append(msg)
                except Exception as e:
                    logger.error(f"解析消息时间失败: {e}")
                    continue
                    
            return auto_forward_messages
            
        except Exception as e:
            logger.error(f"获取自动转发消息失败: {e}")
            return []
    
    async def auto_forward_message(self, message: Dict[str, Any]):
        """自动转发消息"""
        try:
            # 首先检查审核群是否已配置
            from app.services.config_manager import ConfigManager
            config_manager = ConfigManager()
            review_group = await config_manager.get_config('channels.review_group_id')
            
            if not review_group:
                logger.error("❌ 审核群未配置，阻止自动转发！所有消息必须经过审核群。")
                # 更新消息状态为错误状态
                channel_id = message.get('source_channel')
                message_id = message.get('message_id')
                
                if channel_id and message_id:
                    success = self.redis_store.update_message_status(
                        channel_id, int(message_id), "error"
                    )
                    if success:
                        # 更新拒绝原因
                        msg_key = f"msg:{channel_id}:{message_id}"
                        self.redis_store.redis.hset(msg_key, "reject_reason", "审核群未配置，自动转发被阻止")
                return
            
            # 这里应该调用Telegram API转发消息
            # 为了简化，这里只更新状态
            channel_id = message.get('source_channel')
            message_id = message.get('message_id')
            
            if channel_id and message_id:
                success = self.redis_store.update_message_status(
                    channel_id, int(message_id), "auto_forwarded"
                )
                if success:
                    # 更新转发时间
                    msg_key = f"msg:{channel_id}:{message_id}"
                    self.redis_store.redis.hset(msg_key, "forwarded_time", datetime.utcnow().isoformat())
                    
                logger.info(f"自动转发消息 ID: {channel_id}:{message_id}")
            
        except Exception as e:
            logger.error(f"自动转发消息失败: {e}")
    
    async def check_and_filter_duplicates(self, message: Dict[str, Any]) -> bool:
        """
        检查并过滤重复消息
        
        Args:
            message: 要检查的消息字典
            
        Returns:
            True如果是重复消息，False如果不重复
        """
        try:
            # 准备视觉哈希（如果有）
            visual_hashes = None
            if 'visual_hash' in message and message['visual_hash']:
                try:
                    if isinstance(message['visual_hash'], str):
                        # 优先使用JSON解析，兼容旧的Python dict格式
                        import json
                        try:
                            visual_hashes = json.loads(message['visual_hash'])
                        except json.JSONDecodeError:
                            visual_hashes = eval(message['visual_hash'])  # 兼容旧格式
                    else:
                        visual_hashes = message['visual_hash']
                except Exception as e:
                    logger.debug(f"解析视觉哈希失败: {e}")
            
            # 解析创建时间
            message_time = datetime.utcnow()
            if 'created_at' in message and message['created_at']:
                try:
                    message_time = datetime.fromisoformat(message['created_at'].replace('Z', '+00:00')).replace(tzinfo=None)
                except:
                    pass
            
            # 构造消息ID（由于新系统中没有自增主ID，使用channel:message_id组合）
            msg_id = f"{message.get('source_channel')}:{message.get('message_id')}"
            
            is_duplicate, orig_id, dup_type = await self.duplicate_detector.is_duplicate_message(
                source_channel=message.get('source_channel'),
                media_hash=message.get('media_hash'),
                combined_media_hash=message.get('combined_media_hash'),
                content=message.get('content'),
                message_time=message_time,
                message_id=msg_id,
                visual_hashes=visual_hashes
            )
            
            if is_duplicate and orig_id:
                # 直接标记为重复并指向原始消息
                # 解析channel_id和message_id
                if ':' in str(msg_id):
                    ch_id, m_id = str(msg_id).split(':', 1)
                    await self.duplicate_detector.mark_as_duplicate(
                        channel_id=ch_id,
                        message_id=int(m_id),
                        original_message_id=orig_id
                    )
                
                logger.info(f"消息 {msg_id} 被检测为{dup_type}重复消息（原消息ID: {orig_id}），已自动过滤")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"检查重复消息时出错: {e}")
            return False
    
    async def process_new_message(self, message_data: dict) -> Optional[Dict[str, Any]]:
        """
        处理新消息，包括重复检测
        
        Args:
            message_data: 消息数据字典
            
        Returns:
            处理后的消息字典，如果重复则返回None
        """
        try:
            # 确保redis_store已初始化
            if self.redis_store is None:
                self.redis_store = get_redis_message_store()
            
            channel_id = str(message_data.get('source_channel', ''))
            message_id = message_data.get('message_id')
            
            if not channel_id or not message_id:
                logger.error("消息数据缺少必要字段: source_channel 或 message_id")
                return None
            
            # 先进行重复检测（在保存之前）
            message_time = datetime.utcnow()
            if message_data.get('created_at'):
                try:
                    message_time = datetime.fromisoformat(message_data['created_at'].replace('Z', '+00:00')).replace(tzinfo=None)
                except:
                    pass
                    
            is_duplicate, original_msg_id, duplicate_type = await self.duplicate_detector.is_duplicate_message(
                source_channel=channel_id,
                media_hash=message_data.get('media_hash'),
                combined_media_hash=message_data.get('combined_media_hash'),
                content=message_data.get('content'),
                message_time=message_time,
                visual_hashes=message_data.get('visual_hash')
            )
            
            if is_duplicate:
                logger.info(f"🔄 message_processor: 检测到重复消息（{duplicate_type}），原始消息ID: {original_msg_id}，拒绝处理")
                return None
            
            # 非重复消息，检查Redis中是否已存在
            existing_message = self.redis_store.get_message(channel_id, int(message_id))
            
            if existing_message:
                logger.info(f"📋 message_processor: 消息已存在于Redis中：频道 {channel_id}，消息ID {message_id}")
                return existing_message
            
            # 保存新消息到Redis
            try:
                success = self.redis_store.save_message(channel_id, int(message_id), message_data)
                
                if success:
                    # 获取保存后的消息
                    saved_message = self.redis_store.get_message(channel_id, int(message_id))
                    if saved_message:
                        logger.info(f"💾 message_processor: 新消息 {channel_id}:{message_id} 成功保存到Redis [状态: {saved_message.get('status', 'unknown')}]")
                        return saved_message
                    else:
                        logger.error(f"保存成功但无法获取消息: {channel_id}:{message_id}")
                else:
                    logger.error(f"保存消息失败: {channel_id}:{message_id}")
                    
            except Exception as redis_error:
                logger.error(f"Redis操作失败 {channel_id}:{message_id}: {redis_error}")
                # 重新初始化Redis连接并重试一次
                try:
                    self.redis_store = get_redis_message_store()
                    success = self.redis_store.save_message(channel_id, int(message_id), message_data)
                    if success:
                        saved_message = self.redis_store.get_message(channel_id, int(message_id))
                        if saved_message:
                            logger.info(f"💾 message_processor: 重试成功，消息 {channel_id}:{message_id} 已保存")
                            return saved_message
                    logger.error(f"重试保存消息失败: {channel_id}:{message_id}")
                except Exception as retry_error:
                    logger.error(f"重试Redis操作也失败: {retry_error}")
                
            return None
                
        except Exception as e:
            logger.error(f"处理新消息时出错: {e}")
            raise
    
    async def get_message_stats(self) -> dict:
        """获取消息统计信息"""
        try:
            # 确保redis_store已初始化
            if self.redis_store is None:
                try:
                    self.redis_store = get_redis_message_store()
                except RuntimeError:
                    logger.warning("Redis存储未初始化，返回默认统计")
                    return {
                        "total": 0,
                        "pending": 0,
                        "approved": 0,
                        "rejected": 0,
                        "auto_forwarded": 0,
                        "ads": 0,
                        "duplicates": 0,
                        "channels": 0
                    }
            
            # 使用Redis计数器获取统计数据
            stats = {
                "total": 0,
                "pending": self.redis_store.get_message_count(status="pending"),
                "approved": self.redis_store.get_message_count(status="approved"),
                "rejected": self.redis_store.get_message_count(status="rejected"),
                "auto_forwarded": self.redis_store.get_message_count(status="auto_forwarded"),
                "ads": 0,
                "duplicates": 0,
                "channels": 0
            }
            
            # 计算总数
            stats["total"] = stats["pending"] + stats["approved"] + stats["rejected"] + stats["auto_forwarded"]
            
            # 获取所有频道的计数器键
            pattern = "msg:count:*:total"
            total_keys = self.redis_store.redis.keys(pattern)
            
            # 计算广告数量和重复数量（需要遍历所有消息）
            ad_count = 0
            duplicate_count = 0
            channel_set = set()
            
            # 从所有频道计数器中提取频道ID
            for key in total_keys:
                # key格式: msg:count:channel_id:total
                parts = key.split(':')
                if len(parts) >= 3:
                    channel_id = parts[2]
                    channel_set.add(channel_id)
            
            # 获取活跃源频道数量
            try:
                from app.services.unified_channel_service import unified_channel_service
                active_channels = await unified_channel_service.get_all_channels(channel_type="source", active_only=True)
                stats["channels"] = len(active_channels)
            except Exception as e:
                logger.warning(f"获取活跃频道数失败，使用消息频道数: {e}")
                stats["channels"] = len(channel_set)
            
            # 通过采样方式估算广告和重复数量（避免遍历所有消息）
            sample_size = min(100, stats["total"])  # 最多采样100条
            if sample_size > 0:
                sample_messages = self.redis_store.get_pending_messages(limit=sample_size)
                
                for msg in sample_messages:
                    # 检查广告标记
                    is_ad = msg.get('is_ad', False)
                    if isinstance(is_ad, str):
                        is_ad = is_ad.lower() == 'true'
                    if is_ad:
                        ad_count += 1
                    
                    # 检查重复标记（通过filtered_content判断）
                    filtered_content = msg.get('filtered_content', '')
                    if '重复消息' in filtered_content:
                        duplicate_count += 1
                
                # 按比例推算全局数量
                if sample_size > 0:
                    ratio = stats["total"] / sample_size
                    stats["ads"] = int(ad_count * ratio)
                    stats["duplicates"] = int(duplicate_count * ratio)
            
            logger.debug(f"消息统计: {stats}")
            return stats
            
        except Exception as e:
            logger.error(f"获取消息统计失败: {e}")
            # 返回默认统计
            return {
                "total": 0,
                "pending": 0,
                "approved": 0,
                "rejected": 0,
                "ads": 0,
                "duplicates": 0,
                "channels": 0,
                "auto_forwarded": 0
            }
    
    async def get_message(self, channel_id: str, message_id: int) -> Optional[Dict[str, Any]]:
        """获取单条消息"""
        try:
            logger.debug(f"MessageProcessor获取消息: {channel_id}:{message_id}")
            message = self.redis_store.get_message(channel_id, message_id)
            
            if message is None:
                logger.warning(f"MessageProcessor: 消息不存在 {channel_id}:{message_id}")
                return None
            
            logger.debug(f"MessageProcessor: 成功获取消息 {channel_id}:{message_id}, 状态: {message.get('status', 'unknown')}")
            return message
            
        except Exception as e:
            logger.error(f"MessageProcessor获取消息失败 {channel_id}:{message_id}: {e}", exc_info=True)
            return None
    
    async def update_message_status(self, channel_id: str, message_id: int, 
                                  new_status: str, reviewed_by: str = None) -> bool:
        """更新消息状态"""
        try:
            return self.redis_store.update_message_status(
                channel_id, message_id, new_status, reviewed_by
            )
        except Exception as e:
            logger.error(f"更新消息状态失败 {channel_id}:{message_id}: {e}")
            return False
    
    async def delete_message(self, channel_id: str, message_id: int) -> bool:
        """删除消息"""
        try:
            return self.redis_store.delete_message(channel_id, message_id)
        except Exception as e:
            logger.error(f"删除消息失败 {channel_id}:{message_id}: {e}")
            return False
    
    async def get_messages_by_channel(self, channel_id: str, 
                                    limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """获取频道消息列表"""
        try:
            return self.redis_store.get_messages_by_channel(channel_id, limit, offset)
        except Exception as e:
            logger.error(f"获取频道消息失败 {channel_id}: {e}")
            return []
    
    async def batch_update_status(self, message_ids: List[tuple], 
                                new_status: str, reviewed_by: str = None) -> Dict[str, bool]:
        """批量更新消息状态
        
        Args:
            message_ids: [(channel_id, message_id), ...] 消息ID元组列表
            new_status: 新状态
            reviewed_by: 审核人
            
        Returns:
            {f"{channel_id}:{message_id}": success_status, ...}
        """
        results = {}
        
        try:
            for channel_id, message_id in message_ids:
                key = f"{channel_id}:{message_id}"
                try:
                    success = await self.update_message_status(
                        str(channel_id), int(message_id), new_status, reviewed_by
                    )
                    results[key] = success
                    
                    if success:
                        logger.debug(f"批量更新成功: {key} -> {new_status}")
                    else:
                        logger.warning(f"批量更新失败: {key}")
                        
                except Exception as e:
                    logger.error(f"批量更新单个消息失败 {key}: {e}")
                    results[key] = False
                    
            success_count = sum(1 for v in results.values() if v)
            logger.info(f"批量状态更新完成: {success_count}/{len(message_ids)} 成功")
            
        except Exception as e:
            logger.error(f"批量更新消息状态失败: {e}")
            
        return results
    
    async def find_duplicate_messages(self, media_hash: str) -> List[Dict[str, Any]]:
        """根据媒体哈希查找重复消息"""
        try:
            duplicate_keys = self.redis_store.find_duplicate_by_hash(media_hash)
            messages = []
            
            for key in duplicate_keys:
                try:
                    channel_id, message_id = key.split(':', 1)
                    msg = self.redis_store.get_message(channel_id, int(message_id))
                    if msg:
                        messages.append(msg)
                except Exception as e:
                    logger.debug(f"解析重复消息键失败 {key}: {e}")
                    
            return messages
            
        except Exception as e:
            logger.error(f"查找重复消息失败: {e}")
            return []
    
    async def cleanup_expired_data(self):
        """清理过期数据"""
        try:
            self.redis_store.cleanup_expired_indexes()
            logger.info("过期数据清理完成")
        except Exception as e:
            logger.error(f"清理过期数据失败: {e}")