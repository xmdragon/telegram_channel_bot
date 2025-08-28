"""
Session配置迁移工具 - Linus式清晰迁移
将旧的telegram.session迁移到telegram.listener_session
避免配置混乱，一次性完成迁移
"""
import logging
from typing import Optional, Dict, Any

from app.services.config_manager import ConfigManager

logger = logging.getLogger(__name__)

class SessionMigrator:
    """Session配置迁移器 - 一次性清理旧配置"""
    
    def __init__(self):
        self.config_manager = ConfigManager()
    
    async def migrate_legacy_session(self) -> Dict[str, Any]:
        """
        迁移旧Session配置到新的双Session结构
        
        Returns:
            dict: 迁移结果报告
        """
        try:
            # 检查是否需要迁移
            old_session = await self.config_manager.get_config("telegram.session")
            old_api_id = await self.config_manager.get_config("telegram.api_id")
            old_api_hash = await self.config_manager.get_config("telegram.api_hash")
            
            # 检查新配置是否已存在
            listener_session = await self.config_manager.get_config("telegram.listener_session")
            
            if not old_session and not listener_session:
                logger.info("无需迁移：没有找到任何Session配置")
                return {
                    "migrated": False,
                    "reason": "no_sessions_found",
                    "message": "未找到需要迁移的Session配置"
                }
            
            if listener_session and not old_session:
                logger.info("无需迁移：新配置结构已存在")
                return {
                    "migrated": False,
                    "reason": "already_migrated", 
                    "message": "已使用新的双Session配置结构"
                }
            
            if old_session:
                logger.info("开始迁移旧Session配置...")
                
                # 迁移Session到listener_session
                await self.config_manager.set_config(
                    "telegram.listener_session",
                    old_session,
                    "Telegram采集Session (从旧配置迁移)",
                    "string"
                )
                logger.info("✅ Session已迁移到telegram.listener_session")
                
                # 迁移API凭据到listener配置
                if old_api_id:
                    await self.config_manager.set_config(
                        "telegram.listener_api_id",
                        old_api_id,
                        "Telegram采集API ID (从旧配置迁移)",
                        "string"
                    )
                    logger.info("✅ API ID已迁移到telegram.listener_api_id")
                
                if old_api_hash:
                    await self.config_manager.set_config(
                        "telegram.listener_api_hash", 
                        old_api_hash,
                        "Telegram采集API Hash (从旧配置迁移)",
                        "string"
                    )
                    logger.info("✅ API Hash已迁移到telegram.listener_api_hash")
                
                # 删除旧配置（Linus式：不留包袱）
                await self.config_manager.delete_config("telegram.session")
                await self.config_manager.delete_config("telegram.api_id")
                await self.config_manager.delete_config("telegram.api_hash")
                logger.info("🗑️ 已删除旧配置，避免混乱")
                
                return {
                    "migrated": True,
                    "reason": "migration_completed",
                    "message": "Session配置已成功迁移到双Session结构",
                    "details": {
                        "listener_session": bool(old_session),
                        "listener_api_id": bool(old_api_id),
                        "listener_api_hash": bool(old_api_hash),
                        "old_configs_deleted": True
                    }
                }
            
            return {
                "migrated": False,
                "reason": "no_action_needed",
                "message": "配置状态正常，无需迁移"
            }
            
        except Exception as e:
            logger.error(f"Session迁移失败: {e}")
            return {
                "migrated": False,
                "reason": "migration_error",
                "message": f"迁移过程中出错: {str(e)}",
                "error": str(e)
            }
    
    async def check_dual_session_status(self) -> Dict[str, Any]:
        """
        检查双Session配置状态
        
        Returns:
            dict: 配置状态报告
        """
        try:
            # 检查采集Session配置
            listener_session = await self.config_manager.get_config("telegram.listener_session")
            listener_api_id = await self.config_manager.get_config("telegram.listener_api_id") 
            listener_api_hash = await self.config_manager.get_config("telegram.listener_api_hash")
            
            # 检查发送Session配置
            sender_session = await self.config_manager.get_config("telegram.sender_session")
            sender_api_id = await self.config_manager.get_config("telegram.sender_api_id")
            sender_api_hash = await self.config_manager.get_config("telegram.sender_api_hash")
            
            # 检查旧配置残留
            old_session = await self.config_manager.get_config("telegram.session")
            
            return {
                "listener_configured": all([listener_session, listener_api_id, listener_api_hash]),
                "sender_configured": all([sender_session, sender_api_id, sender_api_hash]),
                "has_legacy_config": bool(old_session),
                "details": {
                    "listener": {
                        "session": bool(listener_session),
                        "api_id": bool(listener_api_id),
                        "api_hash": bool(listener_api_hash)
                    },
                    "sender": {
                        "session": bool(sender_session),
                        "api_id": bool(sender_api_id),
                        "api_hash": bool(sender_api_hash)
                    },
                    "legacy": {
                        "old_session": bool(old_session)
                    }
                }
            }
            
        except Exception as e:
            logger.error(f"检查双Session状态失败: {e}")
            return {
                "listener_configured": False,
                "sender_configured": False,
                "has_legacy_config": False,
                "error": str(e)
            }

# 全局迁移器实例
session_migrator = SessionMigrator()