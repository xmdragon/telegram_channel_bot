"""
事件处理器
负责处理回调按钮和审核命令
"""
import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)

class EventHandler:
    """事件处理器"""
    
    def __init__(self):
        self.callback_processors = {}
        self.command_processors = {}
    
    def register_callback_processor(self, action: str, processor: Callable):
        """注册回调处理器"""
        self.callback_processors[action] = processor
    
    def register_command_processor(self, command: str, processor: Callable):
        """注册命令处理器"""
        self.command_processors[command] = processor
    
    async def handle_callback(self, event):
        """处理回调按钮"""
        try:
            data = event.data.decode()
            action, message_id = data.split('_', 1)
            message_id = int(message_id)
            
            logger.info(f"处理回调: {action} for message {message_id}")
            
            if action in self.callback_processors:
                await self.callback_processors[action](message_id, event.sender.username)
            elif action == "approve":
                await self.approve_message(message_id, event.sender.username)
            elif action == "reject":
                await self.reject_message(message_id, event.sender.username)
            elif action == "edit":
                await self.edit_message(message_id)
            elif action == "detail":
                await self.show_message_detail(message_id)
            else:
                logger.warning(f"未知的回调动作: {action}")
                
        except Exception as e:
            logger.error(f"处理回调时出错: {e}")
    
    async def handle_command(self, message, text: str):
        """处理命令"""
        try:
            if text.startswith('/approve_'):
                message_id = int(text.split('_')[1])
                await self.approve_message(message_id, message.sender.username)
            elif text.startswith('/reject_'):
                message_id = int(text.split('_')[1])
                await self.reject_message(message_id, message.sender.username)
            elif text.startswith('/edit_'):
                message_id = int(text.split('_')[1])
                await self.edit_message(message_id)
            elif text.startswith('/detail_'):
                message_id = int(text.split('_')[1])
                await self.show_message_detail(message_id)
            else:
                # 检查是否有注册的命令处理器
                command = text.split()[0] if text.split() else text
                if command in self.command_processors:
                    await self.command_processors[command](message, text)
                else:
                    logger.debug(f"未处理的命令: {text}")
                
        except Exception as e:
            logger.error(f"处理命令时出错: {e}")
    
    async def approve_message(self, message_id: int, reviewer: str):
        """批准消息"""
        try:
            logger.info(f"批准消息 {message_id} by {reviewer}")
            
            # 这里可以调用API或服务来处理批准逻辑
            # 由于避免循环依赖，使用延迟导入
            try:
                from app.api.messages import approve_message_api
                result = await approve_message_api(message_id, reviewer)
                if result:
                    logger.info(f"✅ 消息 {message_id} 批准成功")
                else:
                    logger.error(f"❌ 消息 {message_id} 批准失败")
            except ImportError:
                logger.warning(f"无法导入批准API，使用兼容模式")
                # 兼容旧系统
                await self._legacy_approve_message(message_id, reviewer)
                
        except Exception as e:
            logger.error(f"批准消息时出错: {e}")
    
    async def reject_message(self, message_id: int, reviewer: str):
        """拒绝消息"""
        try:
            logger.info(f"拒绝消息 {message_id} by {reviewer}")
            
            # 这里可以调用API或服务来处理拒绝逻辑
            try:
                from app.api.messages import reject_message_api
                result = await reject_message_api(message_id, reviewer)
                if result:
                    logger.info(f"✅ 消息 {message_id} 拒绝成功")
                else:
                    logger.error(f"❌ 消息 {message_id} 拒绝失败")
            except ImportError:
                logger.warning(f"无法导入拒绝API，使用兼容模式")
                # 兼容旧系统
                await self._legacy_reject_message(message_id, reviewer)
                
        except Exception as e:
            logger.error(f"拒绝消息时出错: {e}")
    
    async def edit_message(self, message_id: int):
        """编辑消息（预留功能）"""
        logger.info(f"编辑消息功能待实现: {message_id}")
        pass
    
    async def show_message_detail(self, message_id: int):
        """显示消息详情（预留功能）"""
        logger.info(f"显示消息详情功能待实现: {message_id}")
        pass
    
    async def _legacy_approve_message(self, message_id: int, reviewer: str):
        """兼容旧系统的批准逻辑"""
        try:
            logger.warning(f"使用了旧的approve_message接口，消息ID: {message_id}")
            logger.info("建议使用新的统一消息处理器进行消息审核")
            
            # 这里可以添加兼容性代码
            # 例如：直接操作Redis或数据库
            from app.storage.redis_manager import redis_manager
            redis_store = redis_manager
            
            # 获取消息
            message = await redis_manager.get_message(message_id)
            if message:
                # 更新状态
                message['status'] = 'approved'
                message['reviewer'] = reviewer
                await redis_manager.update_message(message_id, message)
                logger.info(f"✅ 兼容模式：消息 {message_id} 已批准")
            else:
                logger.error(f"❌ 兼容模式：找不到消息 {message_id}")
                
        except Exception as e:
            logger.error(f"兼容模式批准消息失败: {e}")
    
    async def _legacy_reject_message(self, message_id: int, reviewer: str):
        """兼容旧系统的拒绝逻辑"""
        try:
            logger.warning(f"使用了旧的reject_message接口，消息ID: {message_id}")
            logger.info("建议使用新的统一消息处理器进行消息审核")
            
            # 这里可以添加兼容性代码
            from app.storage.redis_manager import redis_manager
            redis_store = redis_manager
            
            # 获取消息
            message = await redis_manager.get_message(message_id)
            if message:
                # 更新状态
                message['status'] = 'rejected'
                message['reviewer'] = reviewer
                await redis_manager.update_message(message_id, message)
                logger.info(f"✅ 兼容模式：消息 {message_id} 已拒绝")
            else:
                logger.error(f"❌ 兼容模式：找不到消息 {message_id}")
                
        except Exception as e:
            logger.error(f"兼容模式拒绝消息失败: {e}")
    
    async def handle_batch_operation(self, operation: str, message_ids: list, reviewer: str):
        """处理批量操作"""
        try:
            logger.info(f"执行批量操作: {operation} for {len(message_ids)} messages by {reviewer}")
            
            results = []
            for message_id in message_ids:
                try:
                    if operation == "approve":
                        await self.approve_message(message_id, reviewer)
                        results.append({"message_id": message_id, "status": "success"})
                    elif operation == "reject":
                        await self.reject_message(message_id, reviewer)
                        results.append({"message_id": message_id, "status": "success"})
                    else:
                        results.append({"message_id": message_id, "status": "error", "error": f"未知操作: {operation}"})
                except Exception as e:
                    logger.error(f"批量操作中处理消息 {message_id} 失败: {e}")
                    results.append({"message_id": message_id, "status": "error", "error": str(e)})
            
            # 统计结果
            success_count = len([r for r in results if r["status"] == "success"])
            error_count = len([r for r in results if r["status"] == "error"])
            
            logger.info(f"批量操作完成: {success_count} 成功, {error_count} 失败")
            return {
                "total": len(message_ids),
                "success": success_count,
                "error": error_count,
                "results": results
            }
            
        except Exception as e:
            logger.error(f"批量操作失败: {e}")
            return {
                "total": len(message_ids),
                "success": 0,
                "error": len(message_ids),
                "error_message": str(e)
            }
    
    def add_custom_handler(self, event_type: str, handler: Callable):
        """添加自定义事件处理器"""
        if event_type == "callback":
            # 回调处理器需要接受 (event) 参数
            self._custom_callback_handler = handler
        elif event_type == "command":
            # 命令处理器需要接受 (message, text) 参数
            self._custom_command_handler = handler
        else:
            logger.warning(f"不支持的事件类型: {event_type}")
    
    async def process_custom_callback(self, event):
        """处理自定义回调"""
        if hasattr(self, '_custom_callback_handler'):
            try:
                await self._custom_callback_handler(event)
            except Exception as e:
                logger.error(f"自定义回调处理器出错: {e}")
        else:
            await self.handle_callback(event)
    
    async def process_custom_command(self, message, text: str):
        """处理自定义命令"""
        if hasattr(self, '_custom_command_handler'):
            try:
                await self._custom_command_handler(message, text)
            except Exception as e:
                logger.error(f"自定义命令处理器出错: {e}")
        else:
            await self.handle_command(message, text)

# 全局实例
event_handler = EventHandler()