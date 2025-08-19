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
            from app.services.config_manager import config_manager
            auto_forward_delay = await config_manager.get_config('review.auto_forward_delay', 1800)  # 默认30分钟
            
            cutoff_time = datetime.utcnow() - timedelta(seconds=int(auto_forward_delay))
            
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
                            # 检查是否为非广告消息（双重安全检查）
                            is_ad = msg.get('is_ad', False)
                            if isinstance(is_ad, str):
                                is_ad = is_ad.lower() == 'true'
                            
                            # 额外安全检查：拒绝原因包含广告相关内容也不自动转发
                            reject_reason = msg.get('reject_reason', '').lower()
                            filter_reason = msg.get('filter_reason', '').lower()
                            has_ad_reason = ('广告' in reject_reason or '广告' in filter_reason or 
                                           'ad' in reject_reason or 'ad' in filter_reason)
                            
                            if not is_ad and not has_ad_reason:
                                auto_forward_messages.append(msg)
                            elif is_ad or has_ad_reason:
                                logger.debug(f"跳过广告消息自动转发: {msg.get('source_channel')}:{msg.get('message_id')} (is_ad: {is_ad}, ad_reason: {has_ad_reason})")
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
            # 首先检查审核群是否已配置（从Redis缓存）
            from app.services.channel_cache import channel_cache
            review_group = await channel_cache.get_review_group_id()
            
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
                        # 解析JSON格式的visual_hash
                        import json
                        visual_hashes = json.loads(message['visual_hash'])
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
            existing_message = self.redis_store.get_message(channel_id, int(message_id), silent=True)
            
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
                "chats": 0,
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
            
            # 🔧 修复：通过采样方式估算广告、重复和聊天数量（避免遍历所有消息）
            sample_size = min(500, stats["total"])  # 增加采样数量提高准确性
            chat_count = 0
            
            if sample_size > 0:
                # 获取不同状态的消息样本进行分析
                sample_messages = []
                
                # 从不同状态中采样
                pending_sample = self.redis_store.get_pending_messages(limit=min(200, sample_size // 2))
                sample_messages.extend(pending_sample)
                
                # 获取被拒绝的消息样本（包含聊天消息）
                try:
                    rejected_sample = self.redis_store.get_messages_by_status("rejected", limit=min(300, sample_size))
                    sample_messages.extend(rejected_sample)
                except:
                    # 降级方案：直接查询rejected消息
                    pattern = "msg:*"
                    keys = self.redis_store.redis.keys(pattern)
                    rejected_keys = []
                    for key in keys[:500]:  # 限制检查数量
                        try:
                            msg_data = self.redis_store.redis.hgetall(key)
                            if msg_data.get(b'status') == b'rejected':
                                rejected_keys.append(key)
                                if len(rejected_keys) >= 300:
                                    break
                        except:
                            continue
                    
                    # 解析rejected消息
                    for key in rejected_keys:
                        try:
                            msg_data = self.redis_store.redis.hgetall(key)
                            # 转换为统一格式
                            msg = {}
                            for k, v in msg_data.items():
                                if isinstance(k, bytes):
                                    k = k.decode('utf-8')
                                if isinstance(v, bytes):
                                    v = v.decode('utf-8')
                                msg[k] = v
                            sample_messages.append(msg)
                        except:
                            continue
                
                # 分析样本消息
                for msg in sample_messages:
                    filter_reason = msg.get('filter_reason', '')
                    reject_reason = msg.get('reject_reason', '')
                    all_reasons = f"{filter_reason} {reject_reason}".lower()
                    
                    # 🔧 修复：检查广告标记 - 包含自动拒绝的广告
                    is_ad = msg.get('is_ad', False)
                    if isinstance(is_ad, str):
                        is_ad = is_ad.lower() == 'true'
                    
                    # 广告识别：直接标记为广告 OR 拒绝原因包含广告关键词
                    if (is_ad or '广告' in all_reasons or 'ad' in all_reasons or 
                        '高风险广告' in all_reasons or '赌博' in all_reasons or 
                        '色情' in all_reasons or '诈骗' in all_reasons):
                        ad_count += 1
                    
                    # 检查重复标记
                    elif '重复' in all_reasons or 'duplicate' in all_reasons:
                        duplicate_count += 1
                    
                    # 🔧 检查聊天内容标记
                    elif ('聊天内容' in all_reasons or 'chat' in all_reasons or 
                          'chatcontentfilter' in all_reasons.replace('_', '').replace(' ', '') or
                          '检测到聊天内容' in all_reasons):
                        chat_count += 1
                
                # 按比例推算全局数量
                if len(sample_messages) > 0:
                    ratio = stats["total"] / len(sample_messages)
                    stats["ads"] = int(ad_count * ratio)
                    stats["duplicates"] = int(duplicate_count * ratio)
                    stats["chats"] = int(chat_count * ratio)
                    
                    logger.info(f"📊 消息统计采样: 样本{len(sample_messages)}条, 聊天{chat_count}条, 广告{ad_count}条, 重复{duplicate_count}条")
                else:
                    stats["chats"] = 0
            
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
                "chats": 0,
                "channels": 0,
                "auto_forwarded": 0
            }
    
    async def get_message(self, channel_id: str, message_id: int) -> Optional[Dict[str, Any]]:
        """获取单条消息"""
        try:
            logger.debug(f"MessageProcessor获取消息: {channel_id}:{message_id}")
            
            # 确保redis_store已初始化
            if self.redis_store is None:
                try:
                    self.redis_store = get_redis_message_store()
                    logger.debug("MessageProcessor: redis_store初始化成功")
                except RuntimeError as e:
                    logger.error(f"MessageProcessor: redis_store初始化失败: {e}")
                    return None
            
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
            # 🔧 修复：确保redis_store已初始化
            if self.redis_store is None:
                try:
                    self.redis_store = get_redis_message_store()
                    logger.debug("MessageProcessor: redis_store初始化成功（状态更新）")
                except RuntimeError as e:
                    logger.error(f"MessageProcessor: redis_store初始化失败（状态更新）: {e}")
                    return False
            
            result = self.redis_store.update_message_status(
                channel_id, message_id, new_status, reviewed_by
            )
            
            if result:
                logger.debug(f"✅ 状态更新成功: {channel_id}:{message_id} -> {new_status}")
            else:
                logger.warning(f"❌ 状态更新失败: {channel_id}:{message_id} -> {new_status}")
                
            return result
        except Exception as e:
            logger.error(f"更新消息状态异常 {channel_id}:{message_id}: {e}", exc_info=True)
            return False
    
    async def delete_message(self, channel_id: str, message_id: int) -> bool:
        """删除消息"""
        try:
            # 确保redis_store已初始化
            if self.redis_store is None:
                try:
                    self.redis_store = get_redis_message_store()
                    logger.debug("MessageProcessor: redis_store初始化成功（删除操作）")
                except RuntimeError as e:
                    logger.error(f"MessageProcessor: redis_store初始化失败（删除操作）: {e}")
                    return False
            
            logger.info(f"MessageProcessor开始删除: {channel_id}:{message_id}")
            result = self.redis_store.delete_message(channel_id, message_id)
            logger.info(f"MessageProcessor删除结果: {channel_id}:{message_id} -> {result}")
            return result
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
                                new_status: str, reviewed_by: str = None, reason: str = None) -> Dict[str, bool]:
        """批量更新消息状态
        
        Args:
            message_ids: [(channel_id, message_id), ...] 消息ID元组列表
            new_status: 新状态
            reviewed_by: 审核人
            reason: 拒绝原因（可选）
            
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
                    
                    # 如果有reason且为rejected状态，记录到日志
                    if reason and new_status == "rejected":
                        logger.info(f"批量拒绝原因 {channel_id}:{message_id}: {reason}")
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
                    msg = self.redis_store.get_message(channel_id, int(message_id), silent=True)
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
    
    async def mark_as_not_ad(self, channel_id: str, message_id: int, user_id: str = None) -> bool:
        """
        标记消息为非广告
        会将消息状态从广告改为待审核，并清理相关训练数据
        
        Args:
            channel_id: 频道ID
            message_id: 消息ID
            user_id: 操作用户ID
            
        Returns:
            bool: 操作是否成功
        """
        try:
            # 确保redis_store已初始化
            if self.redis_store is None:
                try:
                    self.redis_store = get_redis_message_store()
                except RuntimeError:
                    logger.error("Redis连接失败")
                    return False
            
            # 获取消息
            msg_data = await self.get_message(channel_id, message_id)
            if not msg_data:
                logger.warning(f"消息不存在: {channel_id}:{message_id}")
                return False
            
            # 检查消息是否确实被标记为广告
            if msg_data.get('is_ad') != 'True':
                logger.info(f"消息 {channel_id}:{message_id} 未被标记为广告，无需操作")
                return True
            
            # 更新消息状态
            update_data = {
                'status': 'pending',  # 改回待审核状态
                'is_ad': 'False',     # 标记为非广告
                'reviewed_by': user_id or 'system',
                'reviewed_at': datetime.utcnow().isoformat(),
                'not_ad_marked_at': datetime.utcnow().isoformat()
            }
            
            success = self.redis_store.update_message(channel_id, message_id, update_data)
            if not success:
                logger.error(f"更新消息状态失败: {channel_id}:{message_id}")
                return False
            
            # 清理相关训练数据
            try:
                from app.services.training_media_manager import training_media_manager
                deleted_count = await training_media_manager.remove_training_media_by_message(message_id)
                logger.info(f"消息 {channel_id}:{message_id} 标记为非广告，清理了 {deleted_count} 个训练文件")
            except Exception as e:
                logger.error(f"清理训练数据失败: {e}")
                # 不因为清理失败而让整个操作失败
            
            logger.info(f"消息 {channel_id}:{message_id} 已标记为非广告")
            return True
            
        except Exception as e:
            logger.error(f"标记非广告失败 {channel_id}:{message_id}: {e}")
            return False