#!/usr/bin/env python3
"""
PostgreSQL到Redis+JSON数据迁移工具
将现有的PostgreSQL数据迁移到新的存储架构
"""
import asyncio
import json
import logging
import sys
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import AsyncSessionLocal, Message, Channel, SystemConfig, Admin, Permission, AdminPermission, AdminSession
from app.storage.redis_store import init_redis_stores, get_redis_message_store, get_redis_session_store, get_redis_channel_store
from app.storage.json_store import init_json_stores, get_json_config_store, get_json_channel_store, get_json_admin_store
from sqlalchemy import select
from sqlalchemy.orm import selectinload

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PostgreSQLMigrator:
    """PostgreSQL数据迁移器"""
    
    def __init__(self):
        self.migration_report = {
            "start_time": datetime.now().isoformat(),
            "tables": {},
            "errors": [],
            "success": False
        }
    
    async def export_all_data(self) -> Dict[str, Any]:
        """导出所有PostgreSQL数据"""
        logger.info("开始导出PostgreSQL数据...")
        
        exported_data = {
            "messages": [],
            "channels": [],
            "system_configs": [],
            "admins": [],
            "permissions": [],
            "admin_permissions": [],
            "admin_sessions": [],
            "export_time": datetime.now().isoformat()
        }
        
        try:
            async with AsyncSessionLocal() as session:
                # 导出消息数据
                await self._export_messages(session, exported_data)
                
                # 导出频道数据
                await self._export_channels(session, exported_data)
                
                # 导出系统配置
                await self._export_system_configs(session, exported_data)
                
                # 导出管理员数据
                await self._export_admins(session, exported_data)
                
                # 导出权限数据
                await self._export_permissions(session, exported_data)
                
                # 导出管理员权限关联
                await self._export_admin_permissions(session, exported_data)
                
                # 导出会话数据
                await self._export_admin_sessions(session, exported_data)
                
            logger.info("数据导出完成")
            return exported_data
            
        except Exception as e:
            logger.error(f"数据导出失败: {e}")
            self.migration_report["errors"].append(f"导出失败: {str(e)}")
            raise
    
    async def _export_messages(self, session, exported_data):
        """导出消息数据"""
        try:
            result = await session.execute(
                select(Message).order_by(Message.created_at.desc())
            )
            messages = result.scalars().all()
            
            logger.info(f"找到 {len(messages)} 条消息")
            
            for msg in messages:
                message_data = {
                    "source_channel": msg.source_channel,
                    "message_id": msg.message_id,
                    "content": msg.content,
                    "media_type": msg.media_type,
                    "media_url": msg.media_url,
                    "grouped_id": msg.grouped_id,
                    "is_combined": msg.is_combined,
                    "combined_messages": msg.combined_messages,
                    "media_group": msg.media_group,
                    "review_message_id": msg.review_message_id,
                    "status": msg.status,
                    "reviewed_by": msg.reviewed_by,
                    "review_time": msg.review_time.isoformat() if msg.review_time else None,
                    "target_message_id": msg.target_message_id,
                    "forwarded_time": msg.forwarded_time.isoformat() if msg.forwarded_time else None,
                    "is_ad": msg.is_ad,
                    "filtered_content": msg.filtered_content,
                    "filter_reason": msg.filter_reason,
                    "media_hash": msg.media_hash,
                    "combined_media_hash": msg.combined_media_hash,
                    "visual_hash": msg.visual_hash,
                    "ocr_text": msg.ocr_text,
                    "qr_codes": msg.qr_codes,
                    "ocr_ad_score": msg.ocr_ad_score,
                    "ocr_processed": msg.ocr_processed,
                    "entities": msg.entities,
                    "removed_hidden_links": msg.removed_hidden_links,
                    "created_at": msg.created_at.isoformat() if msg.created_at else None,
                    "updated_at": msg.updated_at.isoformat() if msg.updated_at else None
                }
                exported_data["messages"].append(message_data)
            
            self.migration_report["tables"]["messages"] = len(messages)
            
        except Exception as e:
            logger.error(f"导出消息数据失败: {e}")
            self.migration_report["errors"].append(f"消息导出失败: {str(e)}")
            raise
    
    async def _export_channels(self, session, exported_data):
        """导出频道数据"""
        try:
            result = await session.execute(select(Channel))
            channels = result.scalars().all()
            
            logger.info(f"找到 {len(channels)} 个频道")
            
            for channel in channels:
                channel_data = {
                    "channel_id": channel.channel_id,
                    "channel_name": channel.channel_name,
                    "channel_title": channel.channel_title,
                    "channel_type": channel.channel_type,
                    "is_active": channel.is_active,
                    "config": channel.config,
                    "description": channel.description,
                    "last_collected_message_id": channel.last_collected_message_id,
                    "created_at": channel.created_at.isoformat() if channel.created_at else None,
                    "updated_at": channel.updated_at.isoformat() if channel.updated_at else None
                }
                exported_data["channels"].append(channel_data)
            
            self.migration_report["tables"]["channels"] = len(channels)
            
        except Exception as e:
            logger.error(f"导出频道数据失败: {e}")
            self.migration_report["errors"].append(f"频道导出失败: {str(e)}")
            raise
    
    async def _export_system_configs(self, session, exported_data):
        """导出系统配置"""
        try:
            result = await session.execute(select(SystemConfig))
            configs = result.scalars().all()
            
            logger.info(f"找到 {len(configs)} 个配置项")
            
            for config in configs:
                config_data = {
                    "key": config.key,
                    "value": config.value,
                    "description": config.description,
                    "config_type": config.config_type,
                    "is_active": config.is_active,
                    "created_at": config.created_at.isoformat() if config.created_at else None,
                    "updated_at": config.updated_at.isoformat() if config.updated_at else None
                }
                exported_data["system_configs"].append(config_data)
            
            self.migration_report["tables"]["system_configs"] = len(configs)
            
        except Exception as e:
            logger.error(f"导出系统配置失败: {e}")
            self.migration_report["errors"].append(f"配置导出失败: {str(e)}")
            raise
    
    async def _export_admins(self, session, exported_data):
        """导出管理员数据"""
        try:
            result = await session.execute(select(Admin))
            admins = result.scalars().all()
            
            logger.info(f"找到 {len(admins)} 个管理员")
            
            for admin in admins:
                admin_data = {
                    "id": admin.id,
                    "username": admin.username,
                    "password_hash": admin.password_hash,
                    "is_super_admin": admin.is_super_admin,
                    "is_active": admin.is_active,
                    "last_login": admin.last_login.isoformat() if admin.last_login else None,
                    "created_at": admin.created_at.isoformat() if admin.created_at else None,
                    "updated_at": admin.updated_at.isoformat() if admin.updated_at else None
                }
                exported_data["admins"].append(admin_data)
            
            self.migration_report["tables"]["admins"] = len(admins)
            
        except Exception as e:
            logger.error(f"导出管理员数据失败: {e}")
            self.migration_report["errors"].append(f"管理员导出失败: {str(e)}")
            raise
    
    async def _export_permissions(self, session, exported_data):
        """导出权限数据"""
        try:
            result = await session.execute(select(Permission))
            permissions = result.scalars().all()
            
            logger.info(f"找到 {len(permissions)} 个权限")
            
            for perm in permissions:
                perm_data = {
                    "id": perm.id,
                    "name": perm.name,
                    "module": perm.module,
                    "action": perm.action,
                    "description": perm.description,
                    "created_at": perm.created_at.isoformat() if perm.created_at else None
                }
                exported_data["permissions"].append(perm_data)
            
            self.migration_report["tables"]["permissions"] = len(permissions)
            
        except Exception as e:
            logger.error(f"导出权限数据失败: {e}")
            self.migration_report["errors"].append(f"权限导出失败: {str(e)}")
            raise
    
    async def _export_admin_permissions(self, session, exported_data):
        """导出管理员权限关联"""
        try:
            result = await session.execute(
                select(AdminPermission).options(
                    selectinload(AdminPermission.admin),
                    selectinload(AdminPermission.permission)
                )
            )
            admin_perms = result.scalars().all()
            
            logger.info(f"找到 {len(admin_perms)} 个权限关联")
            
            for admin_perm in admin_perms:
                perm_data = {
                    "admin_id": admin_perm.admin_id,
                    "permission_id": admin_perm.permission_id,
                    "granted_by": admin_perm.granted_by,
                    "granted_at": admin_perm.granted_at.isoformat() if admin_perm.granted_at else None
                }
                exported_data["admin_permissions"].append(perm_data)
            
            self.migration_report["tables"]["admin_permissions"] = len(admin_perms)
            
        except Exception as e:
            logger.error(f"导出管理员权限失败: {e}")
            self.migration_report["errors"].append(f"管理员权限导出失败: {str(e)}")
            raise
    
    async def _export_admin_sessions(self, session, exported_data):
        """导出管理员会话"""
        try:
            result = await session.execute(
                select(AdminSession).where(AdminSession.is_active == True)
            )
            sessions = result.scalars().all()
            
            logger.info(f"找到 {len(sessions)} 个活跃会话")
            
            for session_obj in sessions:
                session_data = {
                    "admin_id": session_obj.admin_id,
                    "token": session_obj.token,
                    "ip_address": session_obj.ip_address,
                    "user_agent": session_obj.user_agent,
                    "is_active": session_obj.is_active,
                    "created_at": session_obj.created_at.isoformat() if session_obj.created_at else None,
                    "expires_at": session_obj.expires_at.isoformat() if session_obj.expires_at else None,
                    "last_activity": session_obj.last_activity.isoformat() if session_obj.last_activity else None
                }
                exported_data["admin_sessions"].append(session_data)
            
            self.migration_report["tables"]["admin_sessions"] = len(sessions)
            
        except Exception as e:
            logger.error(f"导出会话数据失败: {e}")
            self.migration_report["errors"].append(f"会话导出失败: {str(e)}")
            # 会话导出失败不是致命错误，继续执行
    
    async def migrate_to_new_storage(self, exported_data: Dict[str, Any]):
        """迁移到新存储系统"""
        logger.info("开始迁移到新存储系统...")
        
        try:
            # 初始化存储系统
            redis_success = init_redis_stores()
            json_success = init_json_stores()
            
            if not redis_success or not json_success:
                raise RuntimeError("存储系统初始化失败")
            
            # 迁移消息到Redis
            await self._migrate_messages_to_redis(exported_data["messages"])
            
            # 迁移会话到Redis
            await self._migrate_sessions_to_redis(exported_data["admin_sessions"])
            
            # 迁移频道采集点到Redis
            await self._migrate_channel_checkpoints_to_redis(exported_data["channels"])
            
            # 迁移系统配置到JSON
            await self._migrate_configs_to_json(exported_data["system_configs"])
            
            # 迁移频道配置到JSON
            await self._migrate_channels_to_json(exported_data["channels"])
            
            # 迁移管理员数据到JSON
            await self._migrate_admins_to_json(
                exported_data["admins"], 
                exported_data["permissions"], 
                exported_data["admin_permissions"]
            )
            
            logger.info("数据迁移完成")
            
        except Exception as e:
            logger.error(f"数据迁移失败: {e}")
            self.migration_report["errors"].append(f"迁移失败: {str(e)}")
            raise
    
    async def _migrate_messages_to_redis(self, messages: List[Dict[str, Any]]):
        """迁移消息到Redis"""
        logger.info(f"开始迁移 {len(messages)} 条消息到Redis...")
        
        redis_store = get_redis_message_store()
        success_count = 0
        error_count = 0
        
        for msg_data in messages:
            try:
                channel_id = msg_data["source_channel"]
                message_id = msg_data["message_id"]
                
                if redis_store.save_message(channel_id, message_id, msg_data):
                    success_count += 1
                else:
                    error_count += 1
                    
            except Exception as e:
                logger.error(f"迁移消息失败 {msg_data.get('source_channel')}:{msg_data.get('message_id')}: {e}")
                error_count += 1
        
        logger.info(f"消息迁移完成: 成功 {success_count}, 失败 {error_count}")
        self.migration_report["redis_messages"] = {"success": success_count, "error": error_count}
    
    async def _migrate_sessions_to_redis(self, sessions: List[Dict[str, Any]]):
        """迁移会话到Redis"""
        logger.info(f"开始迁移 {len(sessions)} 个会话到Redis...")
        
        redis_store = get_redis_session_store()
        success_count = 0
        error_count = 0
        
        for session_data in sessions:
            try:
                token = session_data["token"]
                
                # 计算过期时间
                expires_at = datetime.fromisoformat(session_data["expires_at"]) if session_data["expires_at"] else None
                if expires_at and expires_at > datetime.now():
                    expire_seconds = int((expires_at - datetime.now()).total_seconds())
                    
                    if redis_store.save_session(token, session_data, expire_seconds):
                        success_count += 1
                    else:
                        error_count += 1
                else:
                    # 会话已过期，跳过
                    continue
                    
            except Exception as e:
                logger.error(f"迁移会话失败 {session_data.get('token')}: {e}")
                error_count += 1
        
        logger.info(f"会话迁移完成: 成功 {success_count}, 失败 {error_count}")
        self.migration_report["redis_sessions"] = {"success": success_count, "error": error_count}
    
    async def _migrate_channel_checkpoints_to_redis(self, channels: List[Dict[str, Any]]):
        """迁移频道采集点到Redis"""
        logger.info("开始迁移频道采集点到Redis...")
        
        redis_store = get_redis_channel_store()
        success_count = 0
        error_count = 0
        
        for channel_data in channels:
            try:
                channel_id = channel_data["channel_id"]
                last_message_id = channel_data.get("last_collected_message_id")
                
                if channel_id and last_message_id:
                    if redis_store.set_checkpoint(channel_id, last_message_id):
                        success_count += 1
                    else:
                        error_count += 1
                        
            except Exception as e:
                logger.error(f"迁移采集点失败 {channel_data.get('channel_id')}: {e}")
                error_count += 1
        
        logger.info(f"采集点迁移完成: 成功 {success_count}, 失败 {error_count}")
        self.migration_report["redis_checkpoints"] = {"success": success_count, "error": error_count}
    
    async def _migrate_configs_to_json(self, configs: List[Dict[str, Any]]):
        """迁移系统配置到JSON"""
        logger.info(f"开始迁移 {len(configs)} 个配置项到JSON...")
        
        json_store = get_json_config_store()
        success_count = 0
        error_count = 0
        
        config_data = {}
        for config in configs:
            try:
                key = config["key"]
                value = config["value"]
                
                # 尝试解析JSON值
                if config.get("config_type") == "json":
                    try:
                        value = json.loads(value) if value else None
                    except json.JSONDecodeError:
                        pass
                
                config_data[key] = value
                success_count += 1
                
            except Exception as e:
                logger.error(f"处理配置失败 {config.get('key')}: {e}")
                error_count += 1
        
        # 批量保存配置
        if json_store.set_multiple_config(config_data):
            logger.info(f"配置迁移完成: 成功 {success_count}, 失败 {error_count}")
        else:
            logger.error("配置批量保存失败")
            error_count = len(configs)
            success_count = 0
        
        self.migration_report["json_configs"] = {"success": success_count, "error": error_count}
    
    async def _migrate_channels_to_json(self, channels: List[Dict[str, Any]]):
        """迁移频道配置到JSON"""
        logger.info(f"开始迁移 {len(channels)} 个频道到JSON...")
        
        json_store = get_json_channel_store()
        success_count = 0
        error_count = 0
        
        for channel_data in channels:
            try:
                channel_id = channel_data["channel_id"]
                if not channel_id:
                    continue
                
                # 移除采集点字段（已迁移到Redis）
                channel_data = channel_data.copy()
                channel_data.pop("last_collected_message_id", None)
                
                if json_store.save_channel(channel_id, channel_data):
                    success_count += 1
                else:
                    error_count += 1
                    
            except Exception as e:
                logger.error(f"迁移频道失败 {channel_data.get('channel_id')}: {e}")
                error_count += 1
        
        logger.info(f"频道迁移完成: 成功 {success_count}, 失败 {error_count}")
        self.migration_report["json_channels"] = {"success": success_count, "error": error_count}
    
    async def _migrate_admins_to_json(self, admins: List[Dict[str, Any]], 
                                   permissions: List[Dict[str, Any]], 
                                   admin_permissions: List[Dict[str, Any]]):
        """迁移管理员数据到JSON"""
        logger.info("开始迁移管理员数据到JSON...")
        
        json_store = get_json_admin_store()
        
        try:
            # 保存权限定义
            permission_data = {}
            for perm in permissions:
                permission_data[str(perm["id"])] = {
                    "name": perm["name"],
                    "module": perm["module"],
                    "action": perm["action"],
                    "description": perm["description"],
                    "created_at": perm["created_at"]
                }
            
            json_store._save_json(json_store.PERMISSION_FILE, permission_data)
            
            # 构建管理员权限映射
            admin_perm_map = {}
            for admin_perm in admin_permissions:
                admin_id = str(admin_perm["admin_id"])
                perm_id = admin_perm["permission_id"]
                
                if admin_id not in admin_perm_map:
                    admin_perm_map[admin_id] = []
                admin_perm_map[admin_id].append(perm_id)
            
            json_store._save_json(json_store.ADMIN_PERM_FILE, admin_perm_map)
            
            # 保存管理员数据
            admin_data = {}
            for admin in admins:
                admin_id = str(admin["id"])
                admin_info = admin.copy()
                admin_info.pop("id", None)  # 移除ID字段
                admin_data[admin_id] = admin_info
            
            json_store._save_json(json_store.ADMIN_FILE, admin_data)
            
            logger.info(f"管理员数据迁移完成: 管理员 {len(admins)}, 权限 {len(permissions)}")
            self.migration_report["json_admins"] = {
                "admins": len(admins),
                "permissions": len(permissions),
                "admin_permissions": len(admin_permissions)
            }
            
        except Exception as e:
            logger.error(f"管理员数据迁移失败: {e}")
            self.migration_report["errors"].append(f"管理员迁移失败: {str(e)}")
            raise
    
    def save_migration_report(self):
        """保存迁移报告"""
        try:
            self.migration_report["end_time"] = datetime.now().isoformat()
            self.migration_report["success"] = len(self.migration_report["errors"]) == 0
            
            report_file = Path(__file__).parent.parent / "data" / f"migration_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            report_file.parent.mkdir(exist_ok=True)
            
            with open(report_file, 'w', encoding='utf-8') as f:
                json.dump(self.migration_report, f, ensure_ascii=False, indent=2)
            
            logger.info(f"迁移报告已保存: {report_file}")
            
        except Exception as e:
            logger.error(f"保存迁移报告失败: {e}")

async def main():
    """主函数"""
    migrator = PostgreSQLMigrator()
    
    try:
        # 导出数据
        exported_data = await migrator.export_all_data()
        
        # 保存备份文件
        backup_file = Path(__file__).parent.parent / "data" / f"postgresql_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        backup_file.parent.mkdir(exist_ok=True)
        
        with open(backup_file, 'w', encoding='utf-8') as f:
            json.dump(exported_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"数据备份已保存: {backup_file}")
        
        # 迁移到新存储
        await migrator.migrate_to_new_storage(exported_data)
        
        logger.info("✅ 数据迁移成功完成!")
        
    except Exception as e:
        logger.error(f"❌ 数据迁移失败: {e}")
        return False
    
    finally:
        # 保存迁移报告
        migrator.save_migration_report()
    
    return True

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)