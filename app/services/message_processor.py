"""
消息处理服务
"""
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any
from pathlib import Path
from app.storage.redis_manager import redis_manager
from app.utils.timezone import get_current_time

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
        return get_current_time()
    
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
            auto_forward_delay = await config_manager.get_config('target.auto_forward_delay', 1800)  # 默认30分钟
            
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

            # 🎯 新增: 智能去重检测
            await self._perform_duplicate_detection(message_data, channel_id, message_id)

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
            
            result = self.redis_store.delete_message(channel_id, message_id)
            if result:
                logger.info(f"✅ 删除消息: {channel_id}:{message_id}")
            else:
                logger.warning(f"❌ 删除失败: {channel_id}:{message_id}")
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
        """获取需要清理的旧消息 - 只根据created_at判断"""
        try:
            # 确保redis_store已初始化
            if self.redis_store is None:
                try:
                    self.redis_store = redis_manager
                except RuntimeError:
                    logger.error("Redis连接失败")
                    return []
            
            old_messages = []
            
            # 所有状态的消息都使用统一的配置时间进行清理
            # 不再硬编码，完全依赖于配置的scheduler.data_cleanup_interval_hours
            from datetime import datetime
            
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
                        
                        # 简化：只检查消息创建时间
                        created_at = msg_data.get('created_at')
                        if not created_at:
                            continue

                        # 解析创建时间
                        try:
                            from datetime import datetime
                            created_time = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                        except:
                            continue

                        # 只根据创建时间判断是否清理
                        if created_time < cutoff_time:
                            # 构造消息对象以兼容原有清理逻辑
                            message_obj = type('Message', (), {
                                'channel_id': channel_id,
                                'message_id': int(message_id),
                                'status': msg_data.get('status'),
                                'media_url': msg_data.get('media_url'),
                                'is_combined': msg_data.get('is_combined', False),
                                'combined_messages': msg_data.get('combined_messages', []),
                                'created_at': created_at
                            })()
                            old_messages.append(message_obj)
                            
                except Exception as status_e:
                    logger.error(f"处理状态 {status} 的消息时出错: {status_e}")
                    continue
            
            if old_messages:
                pending_count = sum(1 for msg in old_messages if msg.status == 'pending')
                approved_count = sum(1 for msg in old_messages if msg.status == 'approved')
                rejected_count = sum(1 for msg in old_messages if msg.status == 'rejected')
                logger.debug(f"[清理任务] 检索到 {len(old_messages)} 条需要清理的消息 (pending:{pending_count}, approved:{approved_count}, rejected:{rejected_count})")
            else:
                logger.debug("[清理任务] 没有找到需要清理的旧消息")
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
                'reviewed_at': get_current_time().isoformat(),
                'not_ad_marked_at': get_current_time().isoformat()
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
                'updated_at': get_current_time().isoformat(),
                'refiltered_at': get_current_time().isoformat()
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

    async def _perform_duplicate_detection(self, message_data: dict, channel_id: str, message_id: int):
        """
        执行智能去重检测

        Args:
            message_data: 消息数据字典
            channel_id: 频道ID
            message_id: 消息ID
        """
        try:
            # 检查是否启用去重检测
            from app.services.config_manager import config_manager
            duplicate_detection_enabled = await config_manager.get_config('duplicate_detection.enabled', True)

            if not duplicate_detection_enabled:
                logger.debug("去重检测已禁用")
                return

            # 获取消息内容（优先使用过滤后的文本，保持与前端一致）
            message_content = (
                message_data.get('filtered_content')
                or message_data.get('content')
                or ''
            )
            normalized_preview = message_content.strip()

            full_message_id = f"{channel_id}:{message_id}"
            duplicate_found = False
            duplicate_result = None

            # Step 1: 文本去重检测（保持原逻辑）
            if not normalized_preview:
                logger.debug(f"消息内容为空，跳过文本去重检测: {full_message_id}")
            else:
                # 执行文本去重检测
                from app.services.duplicate_detector import duplicate_detector

                text_duplicate_result = await duplicate_detector.detect_duplicate(message_content, full_message_id)

                if text_duplicate_result.is_duplicate:
                    # 文本检测到重复
                    duplicate_found = True
                    duplicate_result = text_duplicate_result
                    logger.info(
                        f"📝 文本重复: {full_message_id} "
                        f"-> {text_duplicate_result.original_message_id} "
                        f"(相似度: {text_duplicate_result.similarity_score:.3f})"
                    )

            # Step 2: 如果文本未检测到重复，进行媒体去重
            if not duplicate_found:
                media_paths = await self._extract_media_paths(message_data)

                if media_paths:
                    logger.debug(f"执行媒体去重检测: {full_message_id}, 媒体数: {len(media_paths)}")
                    from app.services.media_duplicate_detector import media_duplicate_detector

                    # 对组消息：任一媒体重复则整组重复
                    for idx, media_path in enumerate(media_paths):
                        # 提取媒体文件大小（如果有）
                        file_size = None
                        if message_data.get('media_info') and isinstance(message_data['media_info'], dict):
                            file_size = message_data['media_info'].get('file_size')
                        elif message_data.get('messages') and idx < len(message_data['messages']):
                            # 对于组消息，从对应的子消息中获取
                            sub_msg = message_data['messages'][idx]
                            if sub_msg.get('media_info') and isinstance(sub_msg['media_info'], dict):
                                file_size = sub_msg['media_info'].get('file_size')

                        media_result = await media_duplicate_detector.detect_duplicate(
                            media_path, f"{full_message_id}:media{idx}", file_size
                        )

                        if media_result.is_duplicate:
                            logger.info(
                                f"🖼️ 媒体重复: {full_message_id} "
                                f"-> {media_result.original_message_id} "
                                f"(相似度: {media_result.similarity_score:.3f})"
                            )
                            duplicate_found = True
                            duplicate_result = media_result
                            break  # 找到一个重复就停止

            # 根据检测结果更新消息数据
            if duplicate_found and duplicate_result:
                # 发现重复消息
                message_data['duplicate_status'] = 'suspected'
                message_data['original_message_id'] = duplicate_result.original_message_id
                message_data['similarity_score'] = duplicate_result.similarity_score
                message_data['duplicate_reason'] = duplicate_result.detection_reason

                logger.info(
                    f"✅ 检测到重复消息: {full_message_id} "
                    f"-> {duplicate_result.original_message_id} "
                    f"(方式: {duplicate_result.detection_reason})"
                )
            else:
                # 非重复消息
                message_data['duplicate_status'] = 'none'
                message_data['original_message_id'] = None
                message_data['similarity_score'] = 0.0
                message_data['duplicate_reason'] = "no_duplicate_found"

                logger.debug(f"✅ 消息无重复: {full_message_id}")

        except Exception as e:
            logger.error(f"去重检测失败 {channel_id}:{message_id}: {e}")
            # 检测失败时设置默认值，不影响消息保存
            message_data['duplicate_status'] = 'none'
            message_data['original_message_id'] = None
            message_data['similarity_score'] = 0.0
            message_data['duplicate_reason'] = f"detection_error: {str(e)[:100]}"

    async def _extract_media_paths(self, message_data: Dict) -> List[str]:
        """
        提取消息的所有媒体路径
        支持单消息和组消息

        Args:
            message_data: 消息数据

        Returns:
            媒体文件路径列表
        """
        media_paths = []

        try:
            # 检查是否是组消息
            if message_data.get('is_grouped') and message_data.get('messages'):
                # 组消息：提取所有子消息的媒体
                messages = message_data.get('messages', [])
                for msg in messages:
                    path = await self._get_single_media_path(msg)
                    if path:
                        media_paths.append(path)
            else:
                # 单消息
                path = await self._get_single_media_path(message_data)
                if path:
                    media_paths.append(path)

        except Exception as e:
            logger.error(f"提取媒体路径失败: {e}")

        return media_paths

    async def _get_single_media_path(self, msg_data: Dict) -> Optional[str]:
        """
        获取单个消息的媒体路径

        Args:
            msg_data: 单个消息数据

        Returns:
            媒体文件路径，如果没有则返回None
        """
        try:
            # 优先使用已下载的路径
            if msg_data.get('media_path'):
                path = msg_data['media_path']
                if Path(path).exists():
                    return path

            # 从media_info获取
            media_info = msg_data.get('media_info', {})

            # 检查文件路径
            if media_info.get('file_path'):
                path = media_info['file_path']
                if Path(path).exists():
                    return path

            # 视频使用缩略图
            if media_info.get('thumbnail_path'):
                path = media_info['thumbnail_path']
                if Path(path).exists():
                    return path

            # 如果有媒体但没有下载，尝试下载
            if media_info.get('has_media') or media_info.get('media_id'):
                # 检查是否有原始消息对象
                telegram_message = msg_data.get('telegram_message')
                if not telegram_message:
                    logger.debug("没有原始消息对象，无法下载媒体")
                    return None

                try:
                    from app.services.media_handler import media_handler

                    # 注意：media_handler.download_media 需要 TelegramClient 作为第一个参数
                    # 这里暂时返回None，避免下载整个媒体文件
                    # TODO: 实现缩略图提取功能
                    logger.debug(f"媒体文件未下载，暂不支持动态下载: {msg_data.get('message_id')}")
                    return None

                except Exception as e:
                    logger.warning(f"下载媒体失败: {e}")

        except Exception as e:
            logger.error(f"获取单个媒体路径失败: {e}")

        return None

    async def mark_not_duplicate(self, channel_id: str, message_id: int, user_id: str = None) -> bool:
        """
        标记消息为非重复

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

            # 检查消息是否确实被标记为疑似重复
            if msg_data.get('duplicate_status') != 'suspected':
                logger.info(f"消息 {channel_id}:{message_id} 未被标记为疑似重复，无需操作")
                return True

            # 更新消息状态
            update_data = {
                'duplicate_status': 'not_duplicate',  # 标记为非重复
                'reviewed_by': user_id or 'system',
                'reviewed_at': get_current_time().isoformat(),
                'not_duplicate_marked_at': get_current_time().isoformat()
            }

            success = await self.redis_store.update_message(channel_id, message_id, update_data)
            if not success:
                logger.error(f"更新消息状态失败: {channel_id}:{message_id}")
                return False

            # 记录用户反馈到去重检测器
            from app.services.duplicate_detector import duplicate_detector
            full_message_id = f"{channel_id}:{message_id}"
            await duplicate_detector.mark_not_duplicate(full_message_id, user_id or 'system')

            logger.info(f"消息 {channel_id}:{message_id} 已标记为非重复")
            return True

        except Exception as e:
            logger.error(f"标记非重复失败 {channel_id}:{message_id}: {e}")
            return False

    async def confirm_duplicate(self, channel_id: str, message_id: int, user_id: str = None) -> bool:
        """
        确认消息为重复

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

            # 更新消息状态
            update_data = {
                'duplicate_status': 'confirmed',  # 确认为重复
                'status': 'rejected',  # 同时设置为已拒绝
                'reject_reason': f"确认为重复消息 (原消息: {msg_data.get('original_message_id', 'unknown')})",
                'reviewed_by': user_id or 'system',
                'reviewed_at': get_current_time().isoformat(),
                'duplicate_confirmed_at': get_current_time().isoformat()
            }

            success = await self.redis_store.update_message(channel_id, message_id, update_data)
            if not success:
                logger.error(f"更新消息状态失败: {channel_id}:{message_id}")
                return False

            # 记录用户反馈到去重检测器
            from app.services.duplicate_detector import duplicate_detector
            full_message_id = f"{channel_id}:{message_id}"
            await duplicate_detector.confirm_duplicate(full_message_id, user_id or 'system')

            logger.info(f"消息 {channel_id}:{message_id} 已确认为重复")
            return True

        except Exception as e:
            logger.error(f"确认重复失败 {channel_id}:{message_id}: {e}")
            return False
