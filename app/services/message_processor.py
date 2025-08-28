"""
消息处理服务
"""
import json
import logging
import time
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
    
    # Linus式重构：删除不必要的HTTP API调用层
    # 自动转发功能已移至collector服务中，直接使用Telegram客户端
    
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
            
            # 🔧 Linus式优化：区分"真重复"和"组合消息重复保存"
            if is_duplicate:
                # 检查是否是对自己的重复保存（组合消息场景）
                current_msg_key = f"{channel_id}:{message_id}"
                if original_msg_id and original_msg_id.endswith(current_msg_key):
                    # 这是对自己的重复检测，检查是否已存在
                    existing_message = self.redis_store.get_message(channel_id, int(message_id), silent=True)
                    if existing_message:
                        logger.info(f"🔄 message_processor: 检测到组合消息重复保存，返回已存在消息: {channel_id}:{message_id}")
                        return existing_message
                    else:
                        logger.warning(f"🔄 message_processor: 重复检测器检测到自己但Redis中不存在，继续保存: {channel_id}:{message_id}")
                else:
                    # 这是真正的重复消息，拒绝处理
                    logger.info(f"🔄 message_processor: 检测到重复消息（{duplicate_type}），原始消息ID: {original_msg_id}，拒绝处理")
                    return None
            
            # 非重复消息或特殊情况，检查Redis中是否已存在
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
                        
                        # 🚀 Linus式优化：同时更新视觉哈希专门索引
                        await self._update_visual_index(channel_id, int(message_id), message_data, message_time)
                        
                        # 检查是否启用采集后自动转发到审核群
                        await self._check_auto_forward_after_collect(saved_message)
                        
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
                            # 🚀 重试成功后也要更新视觉哈希索引
                            await self._update_visual_index(channel_id, int(message_id), message_data, message_time)
                            return saved_message
                    logger.error(f"重试保存消息失败: {channel_id}:{message_id}")
                except Exception as retry_error:
                    logger.error(f"重试Redis操作也失败: {retry_error}")
                
            return None
                
        except Exception as e:
            logger.error(f"处理新消息时出错: {e}")
            raise
    
    async def _update_visual_index(self, channel_id: str, message_id: int, message_data: dict, message_time):
        """更新视觉哈希专门索引（不影响消息存储主流程）"""
        try:
            # 检查是否有视觉哈希数据
            visual_hash_str = message_data.get('visual_hash')
            if not visual_hash_str:
                logger.debug(f"消息无视觉哈希数据，跳过索引更新: {channel_id}:{message_id}")
                return
            
            # 🚀 Linus式健壮解析：支持多种数据格式
            visual_hashes = None
            if isinstance(visual_hash_str, str):
                try:
                    visual_hashes = json.loads(visual_hash_str)
                except json.JSONDecodeError as json_err:
                    try:
                        # 兼容旧格式（但不推荐使用eval）
                        visual_hashes = eval(visual_hash_str)
                        logger.debug(f"使用eval解析视觉哈希: {channel_id}:{message_id}")
                    except Exception as eval_err:
                        logger.warning(f"视觉哈希解析失败: {json_err}, eval也失败: {eval_err}")
                        return
            elif isinstance(visual_hash_str, (dict, list)):
                visual_hashes = visual_hash_str
            else:
                logger.warning(f"不支持的visual_hash类型: {type(visual_hash_str)}")
                return
            
            if not visual_hashes:
                logger.debug(f"视觉哈希数据为空: {channel_id}:{message_id}")
                return
            
            # 更新专门的视觉哈希索引
            from app.storage.visual_index_manager import get_visual_index_manager
            
            visual_index = get_visual_index_manager()
            success = visual_index.add_visual_hash(
                channel_id, 
                message_id, 
                visual_hashes, 
                message_time
            )
            
            if success:
                logger.debug(f"✅ 视觉哈希索引已更新: {channel_id}:{message_id}")
            else:
                logger.warning(f"⚠️ 视觉哈希索引更新失败: {channel_id}:{message_id}")
                
        except Exception as e:
            # 🚀 Linus式错误处理：视觉索引是辅助功能，不能影响核心流程
            logger.warning(f"⚠️ 视觉哈希索引更新异常 {channel_id}:{message_id}: {e} (不影响消息存储)")
            # 添加详细的错误信息用于调试
            import traceback
            logger.debug(f"视觉哈希索引更新异常详情: {traceback.format_exc()}")

    async def _check_auto_forward_after_collect(self, saved_message: dict):
        """检查是否需要采集后自动转发到审核群"""
        try:
            from app.services.config_manager import config_manager
            auto_forward_enabled = await config_manager.get_config('review.auto_forward_after_collect', True)
            
            if not auto_forward_enabled:
                logger.debug("采集后自动转发已禁用")
                return
            
            # 添加转发任务到队列
            from app.services.message_forward_queue import forward_queue
            
            message_id_str = f"{saved_message.get('source_channel')}:{saved_message.get('message_id')}"
            task_id = f"auto_forward_review_{message_id_str}_{int(time.time())}"
            
            # 创建转发到审核群的任务
            task = forward_queue.create_task(
                task_id=task_id,
                action="forward_to_review", 
                message_id=message_id_str,
                priority=5,  # 中等优先级
                max_retries=3,
                data={
                    "source": "auto_forward_after_collect",
                    "message_data": saved_message
                }
            )
            
            if forward_queue.add_task(task):
                logger.info(f"📤 已添加采集后自动转发任务: {message_id_str}")
            else:
                logger.warning(f"添加自动转发任务失败: {message_id_str}")
                
        except Exception as e:
            logger.error(f"检查采集后自动转发时出错: {e}")
            # 不抛出异常，避免影响消息保存流程
    
    async def get_message_stats(self) -> dict:
        """获取消息统计信息 - 使用Linus O(1)计数器"""
        try:
            from app.storage.linus_stats_store import get_linus_stats_store
            stats_store = get_linus_stats_store()
            
            # 获取Linus统计数据
            message_stats = stats_store.get_global_stats()
            rejection_stats = stats_store.get_rejection_stats()
            
            # Linus式纯净统计：只有4个核心字段，消除所有特殊情况
            return {
                "total": message_stats.total,
                "pending": message_stats.pending,
                "approved": message_stats.approved,
                "rejected": message_stats.rejected
            }
            
        except Exception as e:
            logger.error(f"获取Linus统计失败: {e}")
            # 返回默认统计
            return {
                "total": 0, 
                "pending": 0, 
                "approved": 0, 
                "rejected": 0
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
            
            success = await self.redis_store.update_message(channel_id, message_id, update_data)
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
    
    async def forward_message(self, message_id: str) -> bool:
        """
        转发消息到目标频道
        
        Args:
            message_id: 消息ID（格式：channel_id:message_id）
            
        Returns:
            bool: 转发是否成功
        """
        try:
            # 确保redis_store已初始化
            if self.redis_store is None:
                try:
                    self.redis_store = get_redis_message_store()
                except RuntimeError:
                    logger.error("Redis连接失败")
                    return False
            
            # 获取消息数据
            message = self.redis_store.get_message_by_id(message_id)
            if not message:
                logger.error(f"消息不存在: {message_id}")
                return False
            
            # 使用临时客户端转发消息，避免锁等待
            try:
                from app.telegram.message_forwarder import message_forwarder
                
                # 使用发送Session转发（无锁设计）
                await message_forwarder.forward_to_target_with_sender_session(message)
                logger.info(f"消息转发成功: {message_id}")
                return True
                
            except ImportError as e:
                logger.error(f"导入转发组件失败: {e}")
                return False
            except Exception as e:
                logger.error(f"转发消息失败: {e}")
                # 向上传递异常，让API层能获得具体错误信息
                raise
                
        except Exception as e:
            logger.error(f"转发已批准消息失败 {message_id}: {e}")
            # 向上传递异常，让API层能处理具体错误
            raise
    
    async def refetch_media(self, channel_id: str, message_id: int) -> bool:
        """
        重新获取消息的媒体文件
        
        Args:
            channel_id: 频道ID
            message_id: 消息ID
            
        Returns:
            bool: 重新获取是否成功
        """
        try:
            # 确保redis_store已初始化
            if self.redis_store is None:
                try:
                    self.redis_store = get_redis_message_store()
                except RuntimeError:
                    logger.error("Redis连接失败")
                    return False
            
            # 获取消息数据
            message = await self.get_message(channel_id, message_id)
            if not message:
                logger.error(f"消息不存在: {channel_id}:{message_id}")
                return False
            
            # Linus式"好品味"：检查消息是否有任何形式的媒体（消除特殊情况）
            has_single_media = bool(message.get('media_type'))
            has_media_group = bool(message.get('media_group_display'))
            
            if not has_single_media and not has_media_group:
                logger.warning(f"消息没有任何媒体内容: {channel_id}:{message_id}")
                return False
            
            # 使用媒体处理器重新下载媒体
            try:
                from app.services.media_handler import media_handler
                from app.telegram.client_manager import client_manager
                
                # 确保客户端连接并获取实例
                if not await client_manager.ensure_connected():
                    logger.error("Telegram客户端连接失败")
                    return False
                
                client = await client_manager.get_client()
                if not client:
                    logger.error("无法获取Telegram客户端实例")
                    return False
                
                # 获取原始消息对象（用于重新下载媒体）
                original_message = await client.get_messages(
                    int(channel_id), ids=[int(message_id)]
                )
                
                if not original_message or len(original_message) == 0:
                    logger.error(f"无法获取原始消息: {channel_id}:{message_id}")
                    return False
                
                # Linus式"好品味"：统一处理单个媒体和组合消息
                if has_media_group:
                    # 处理组合消息：下载所有子消息的媒体
                    media_group = []
                    combined_messages = message.get('combined_messages', [])
                    
                    if not combined_messages:
                        logger.error(f"组合消息缺少combined_messages数据: {channel_id}:{message_id}")
                        return False
                    
                    for msg_info in combined_messages:
                        msg_id = msg_info.get('message_id')
                        if not msg_id:
                            continue
                            
                        # 获取每个子消息的原始Telegram消息
                        try:
                            sub_messages = await client.get_messages(
                                int(channel_id), ids=[int(msg_id)]
                            )
                            
                            if sub_messages and sub_messages[0] and sub_messages[0].media:
                                # 下载该子消息的媒体
                                media_info = await media_handler.download_media(
                                    client, sub_messages[0], msg_id, timeout=60
                                )
                                if media_info:
                                    # 生成显示URL
                                    file_name = media_info.get('file_path', '').split('/')[-1]
                                    media_group.append({
                                        'message_id': msg_id,
                                        'media_type': media_info.get('media_type'),
                                        'file_path': media_info.get('file_path'),
                                        'media_hash': media_info.get('hash'),
                                        'display_url': f'/media/{file_name}' if file_name else None
                                    })
                                    logger.info(f"组合消息子媒体下载成功: {channel_id}:{msg_id}")
                        except Exception as sub_error:
                            logger.warning(f"下载组合消息子媒体失败 {channel_id}:{msg_id}: {sub_error}")
                            continue
                    
                    # 更新组合消息的媒体组信息
                    update_data = {
                        'media_group': media_group,
                        'media_group_display': media_group,  # 直接使用，已包含display_url
                        'refetch_time': datetime.utcnow().isoformat()
                    }
                    
                else:
                    # 处理单个媒体（保持原有逻辑）
                    telegram_message = original_message[0]
                    
                    # 重新下载媒体
                    media_info = await media_handler.download_media(
                        client, 
                        telegram_message, 
                        message_id,
                        timeout=60  # 60秒超时
                    )
                    
                    if not media_info:
                        logger.error(f"重新下载媒体失败: {channel_id}:{message_id}")
                        return False
                    
                    # 更新单个媒体信息
                    file_name = media_info.get('file_path', '').split('/')[-1]
                    update_data = {
                        'media_url': media_info.get('file_path'),
                        'media_path': media_info.get('file_path'),
                        'media_hash': media_info.get('hash'),
                        'media_display_url': f'/media/{file_name}' if file_name else None,
                        'refetch_time': datetime.utcnow().isoformat()
                    }
                
                # 统一更新Redis
                success = self.redis_store.update_message(channel_id, message_id, update_data)
                if success:
                    logger.info(f"媒体重新获取成功: {channel_id}:{message_id}")
                    
                    # 通过WebSocket通知前端
                    await self._notify_media_refetched(channel_id, message_id, update_data)
                    return True
                else:
                    logger.error(f"更新媒体信息失败: {channel_id}:{message_id}")
                    return False
                    
            except ImportError as e:
                logger.error(f"导入媒体处理器失败: {e}")
                return False
            except Exception as e:
                logger.error(f"重新获取媒体失败: {e}")
                return False
                
        except Exception as e:
            logger.error(f"重新获取媒体失败 {channel_id}:{message_id}: {e}")
            return False
    
    async def _notify_media_refetched(self, channel_id: str, message_id: int, media_data: dict):
        """通过WebSocket通知前端媒体补抓完成"""
        try:
            from app.services.websocket_manager import websocket_manager
            
            # 构造通知数据
            notification_data = {
                "type": "media_refetched",
                "data": {
                    "message_id": f"{channel_id}:{message_id}",
                    "timestamp": datetime.utcnow().isoformat()
                }
            }
            
            # 添加媒体数据
            if media_data.get('media_url'):
                notification_data["data"]["media_url"] = media_data["media_url"]
                notification_data["data"]["media_display_url"] = media_data.get("media_display_url")
            
            if media_data.get('media_group_display'):
                notification_data["data"]["media_group_display"] = media_data["media_group_display"]
            
            # 广播通知
            await websocket_manager.broadcast(notification_data)
            logger.info(f"WebSocket通知已发送: 媒体补抓完成 {channel_id}:{message_id}")
            
        except ImportError:
            logger.warning("WebSocket管理器不可用，跳过媒体补抓通知")
        except Exception as e:
            logger.error(f"发送媒体补抓WebSocket通知失败: {e}")
    
    async def refilter_message(self, channel_id: str, message_id: int, filtered_content: str = None) -> bool:
        """
        重新过滤消息
        
        Args:
            channel_id: 频道ID
            message_id: 消息ID
            filtered_content: 过滤后的内容（可选，如果不提供则重新执行过滤逻辑）
            
        Returns:
            bool: 重新过滤是否成功
        """
        try:
            # 确保redis_store已初始化
            if self.redis_store is None:
                try:
                    self.redis_store = get_redis_message_store()
                except RuntimeError:
                    logger.error("Redis连接失败")
                    return False
            
            # 获取消息数据
            message = await self.get_message(channel_id, message_id)
            if not message:
                logger.error(f"消息不存在: {channel_id}:{message_id}")
                return False
            
            # 如果没有提供filtered_content，重新执行过滤逻辑
            if filtered_content is None:
                original_content = message.get('content') or message.get('filtered_content', '')
                if not original_content:
                    logger.warning(f"消息没有内容可以过滤: {channel_id}:{message_id}")
                    return True
                
                # 执行完整的过滤流程（使用统一过滤引擎，受开关控制）
                from app.services.unified_filter_engine import unified_filter_engine
                
                # 使用统一过滤引擎进行重新过滤
                is_ad, filtered_content, filter_reason = await unified_filter_engine.detect_advertisement(
                    content=original_content,
                    channel_id=channel_id,
                    message_obj=message,
                    media_files=message.get('media_files', [])
                )
                
                logger.info(f"重新过滤: {channel_id}:{message_id} - {len(original_content)} -> {len(filtered_content)} 字符")
                logger.info(f"过滤结果: 是否广告={is_ad}, 过滤原因='{filter_reason}'")
            
            # 更新消息的过滤内容
            update_data = {
                'filtered_content': filtered_content,
                'updated_at': datetime.utcnow().isoformat(),
                'refiltered_at': datetime.utcnow().isoformat()
            }
            
            success = await self.redis_store.update_message(channel_id, message_id, update_data)
            if success:
                logger.info(f"消息重新过滤成功: {channel_id}:{message_id} - 内容长度: {len(filtered_content)}")
                return True
            else:
                logger.error(f"更新过滤结果失败: {channel_id}:{message_id}")
                return False
                
        except Exception as e:
            logger.error(f"重新过滤消息失败 {channel_id}:{message_id}: {e}")
            return False