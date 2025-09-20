"""
消息处理服务
"""
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any
from app.storage.redis_manager import redis_manager

logger = logging.getLogger(__name__)

class MessageProcessor:
    """消息处理器"""
    
    def __init__(self):
        self.redis_store = None  # 延迟初始化
    
    def _extract_message_time(self, message_data: dict) -> datetime:
        """从消息数据中提取时间信息"""
        if message_data.get('created_at'):
            try:
                return datetime.fromisoformat(message_data['created_at'].replace('Z', '+00:00')).replace(tzinfo=None)
            except:
                pass
        return datetime.utcnow()
    
    async def get_pending_messages(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取待审核的消息"""
        try:
            if self.redis_store is None:
                try:
                    self.redis_store = redis_manager
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
                    self.redis_store = redis_manager
                except RuntimeError:
                    return []
            
            # 获取自动转发延迟配置
            from app.services.config_manager import config_manager
            auto_forward_delay = await config_manager.get_config('review.auto_forward_delay', 1800)  # 默认30分钟
            
            cutoff_time = datetime.now(timezone.utc) - timedelta(seconds=int(auto_forward_delay))
            
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
                        if created_at <= cutoff_time:
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
    
    # ：删除不必要的HTTP API调用层
    # 自动转发功能已移至collector服务中，直接使用Telegram客户端
    
    
    async def process_new_message(self, message_data: dict) -> Optional[Dict[str, Any]]:
        """
        处理新消息，包括智能去重检测 - 优化版本

        Args:
            message_data: 消息数据字典

        Returns:
            处理后的消息字典，如果重复则返回None
        """
        try:
            # 确保redis_store已初始化
            if self.redis_store is None:
                self.redis_store = redis_manager

            channel_id = str(message_data.get('source_channel', ''))
            message_id = message_data.get('message_id')

            if not channel_id or not message_id:
                logger.error("消息数据缺少必要字段: source_channel 或 message_id")
                return None

            # 优化1: 快速检查Redis中是否已存在（O(1)操作）
            existing_message = self.redis_store.get_message(channel_id, int(message_id), silent=True)
            if existing_message:
                logger.info(f"📋 快速去重: 消息已存在 {channel_id}:{message_id}")
                return existing_message

            # 保存新消息到Redis
            try:
                success = self.redis_store.save_message(channel_id, int(message_id), message_data)
                
                if success:
                    # 获取保存后的消息
                    saved_message = self.redis_store.get_message(channel_id, int(message_id))
                    if saved_message:
                        logger.info(f"💾 message_processor: 新消息 {channel_id}:{message_id} 成功保存到Redis [状态: {saved_message.get('status', 'unknown')}]")
                        
                        
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
                    self.redis_store = redis_manager
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
    

    async def _check_auto_forward_after_collect(self, saved_message: dict):
        """检查是否需要采集后自动转发到审核群"""
        try:
            from app.services.config_manager import config_manager
            auto_forward_enabled = await config_manager.get_config('review.auto_forward_after_collect', True)
            
            if not auto_forward_enabled:
                logger.debug("采集后自动转发已禁用")
                return
            
            # 消息已保存为pending状态，scheduler + auto_forwarder会自动处理转发
            message_id_str = f"{saved_message.get('source_channel')}:{saved_message.get('message_id')}"
            logger.info(f"📤 消息已保存为pending状态，等待自动转发: {message_id_str}")
                
        except Exception as e:
            logger.error(f"检查采集后自动转发时出错: {e}")
            # 不抛出异常，避免影响消息保存流程
    
    async def get_message_stats(self) -> dict:
        """获取消息统计信息 - 使用O(1)计数器"""
        try:
            from app.storage.message_stats_store import get_message_stats_store
            stats_store = get_message_stats_store()
            
            # 获取消息统计数据
            message_stats = stats_store.get_global_stats()

            # 纯净统计：只有4个核心字段，消除所有特殊情况
            return {
                "total": message_stats.total,
                "pending": message_stats.pending,
                "approved": message_stats.approved,
                "rejected": message_stats.rejected
            }
            
        except Exception as e:
            logger.error(f"获取统计失败: {e}")
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
                    self.redis_store = redis_manager
                    logger.debug("MessageProcessor: redis_store初始化成功")
                except RuntimeError as e:
                    logger.error(f"MessageProcessor: redis_store初始化失败: {e}")
                    return None
            
            message = self.redis_store.get_message(channel_id, message_id)
            
            if message is None:
                logger.debug(f"MessageProcessor: 消息不存在 {channel_id}:{message_id}")
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
                    self.redis_store = redis_manager
                    logger.debug("MessageProcessor: redis_store初始化成功（状态更新）")
                except RuntimeError as e:
                    logger.error(f"MessageProcessor: redis_store初始化失败（状态更新）: {e}")
                    return False
            
            # 修复：将参数格式化为Redis Manager期望的格式
            full_message_id = f"{channel_id}:{message_id}"
            result = self.redis_store.update_message_status(
                full_message_id, new_status, reviewed_by
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
                    self.redis_store = redis_manager
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
                                    limit: int = 50, offset: int = 0, status: str = None) -> List[Dict[str, Any]]:
        """获取频道消息列表"""
        try:
            return self.redis_store.get_messages_by_channel(channel_id, limit, offset, status)
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
    
    async def get_old_messages_for_cleanup(self, cutoff_time):
        """获取需要清理的旧消息 - 业务逻辑层实现"""
        try:
            # 确保redis_store已初始化
            if self.redis_store is None:
                try:
                    self.redis_store = redis_manager
                except RuntimeError:
                    logger.error("Redis连接失败")
                    return []
            
            old_messages = []
            
            # 针对不同状态设置不同的清理时间
            # pending消息保留更长时间（7天），避免误删待审核消息
            from datetime import datetime, timedelta, timezone
            pending_cutoff_time = datetime.now(timezone.utc) - timedelta(days=7)
            
            # 获取所有状态的消息
            for status in ['approved', 'rejected', 'pending']:
                try:
                    # 使用Redis存储获取指定状态的消息
                    message_keys = self.redis_store.redis.zrange(f"index:msg:{status}", 0, -1)
                    
                    for key in message_keys:
                        if ':' not in key:
                            continue
                        
                        channel_id, message_id = key.split(':', 1)
                        msg_data = await self.get_message(channel_id, int(message_id))
                        
                        if not msg_data:
                            # 清理孤儿索引条目
                            logger.debug(f"清理孤儿索引: {status} -> {key}")
                            self.redis_store.redis.zrem(f"index:msg:{status}", key)
                            continue
                        
                        # 检查消息是否足够旧
                        created_at = msg_data.get('created_at')
                        review_time = msg_data.get('review_time') 
                        forwarded_time = msg_data.get('forwarded_time')
                        
                        # 解析时间字符串
                        times_to_check = []
                        for time_str in [created_at, review_time, forwarded_time]:
                            if time_str:
                                try:
                                    from datetime import datetime
                                    time_obj = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
                                    times_to_check.append(time_obj)
                                except:
                                    continue
                        
                        # 根据状态使用不同的清理时间阈值
                        # pending消息使用7天阈值，其他使用配置的阈值
                        threshold = pending_cutoff_time if status == 'pending' else cutoff_time
                        
                        # 如果任何时间早于对应的阈值，则加入清理列表
                        if times_to_check and any(t < threshold for t in times_to_check):
                            # 构造消息对象以兼容原有清理逻辑
                            message_obj = type('Message', (), {
                                'channel_id': channel_id,
                                'message_id': int(message_id),
                                'status': msg_data.get('status'),
                                'media_url': msg_data.get('media_url'),
                                'is_combined': msg_data.get('is_combined', False),
                                'combined_messages': msg_data.get('combined_messages', []),
                                'created_at': created_at,
                                'review_time': review_time,
                                'forwarded_time': forwarded_time
                            })()
                            old_messages.append(message_obj)
                            
                except Exception as status_e:
                    logger.error(f"处理状态 {status} 的消息时出错: {status_e}")
                    continue
            
            if old_messages:
                pending_count = sum(1 for msg in old_messages if msg.status == 'pending')
                other_count = len(old_messages) - pending_count
                logger.info(f"找到 {len(old_messages)} 条需要清理的旧消息 (待审核7天以上: {pending_count}, 已处理24小时以上: {other_count})")
            else:
                logger.debug("没有找到需要清理的旧消息")
            return old_messages
            
        except Exception as e:
            logger.error(f"获取旧消息失败: {e}")
            return []
    
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
                    self.redis_store = redis_manager
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
            
            # 注意：已移除媒体训练数据清理功能
            
            # 注意：已移除向量数据库功能
            
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
                    self.redis_store = redis_manager
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
                    self.redis_store = redis_manager
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
                original_content = message.get('content', '')
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