"""
配置管理服务
"""
import json
import logging
import threading
import os
from typing import Any, Dict, List, Optional, Union, Callable
from datetime import datetime

from app.storage.json_store import get_json_config_store, JSONConfigStore

logger = logging.getLogger(__name__)

class ConfigManager:
    """配置管理器 - Redis单一真相源版本"""
    
    def __init__(self):
        self._change_listeners = []  # 配置变更监听器
        self._json_store: Optional[JSONConfigStore] = None
        self._redis_manager = None  # Redis管理器（延迟初始化）
    
    def _get_store(self, max_retries: int = 3) -> Optional[JSONConfigStore]:
        """获取JSON存储实例 - 修复状态同步问题"""
        if self._json_store is None:
            for attempt in range(max_retries):
                try:
                    # 关键修复：每次重试都尝试获取新的存储实例
                    store = get_json_config_store()
                    
                    # 验证存储实例是否真正可用
                    if store is not None:
                        # 尝试简单的操作验证存储实例
                        try:
                            _ = store.get_all_config()
                            # 验证成功，更新实例状态
                            self._json_store = store
                            logger.debug(f"JSON存储实例获取并验证成功 (尝试 {attempt + 1}/{max_retries})")
                            return self._json_store
                        except Exception as verify_e:
                            logger.warning(f"JSON存储实例验证失败: {verify_e}")
                            store = None
                    
                    if store is None and attempt < max_retries - 1:
                        logger.debug(f"JSON存储实例获取失败，重试 {attempt + 1}/{max_retries}")
                        
                except RuntimeError as e:
                    if "未初始化" in str(e):
                        if attempt < max_retries - 1:
                            logger.debug(f"JSON存储层未初始化，重试 {attempt + 1}/{max_retries}")
                            # 尝试强制重新初始化
                            from app.storage.json_store import force_reinit_json_stores
                            if force_reinit_json_stores():
                                logger.info("JSON存储层强制重新初始化成功")
                                # 重新初始化后不使用continue，让循环自然重试
                            else:
                                logger.warning("JSON存储层强制重新初始化失败")
                        else:
                            logger.error("JSON存储层多次初始化失败")
                            return None
                    else:
                        logger.error(f"获取JSON存储实例时发生异常: {e}")
                        if attempt == max_retries - 1:
                            return None
                except Exception as e:
                    logger.error(f"获取JSON存储实例失败 (尝试 {attempt + 1}/{max_retries}): {e}")
                    if attempt == max_retries - 1:
                        return None
                        
                # 最后一次尝试失败
                if attempt == max_retries - 1:
                    logger.error("JSON存储实例获取多次重试后仍然失败")
                    return None
                    
        return self._json_store
    
    def _get_redis_manager(self):
        """获取Redis管理器实例"""
        if self._redis_manager is None:
            from app.storage.redis_manager import get_redis_manager
            self._redis_manager = get_redis_manager()
        return self._redis_manager
    
    async def get_config(self, key: str, default: Any = None) -> Any:
        """获取配置值 - Redis单一真相源版本"""
        try:
            # 首先尝试从Redis读取
            redis_manager = self._get_redis_manager()
            config_data = redis_manager.cache_get(f"config:{key}")
            
            if config_data and isinstance(config_data, dict):
                if config_data.get('is_active', True):
                    return self._parse_value(config_data['value'], config_data['config_type'])
            
            # Redis未命中，从JSON文件读取（兜底机制）
            store = self._get_store()
            if store is not None:
                config_data = store.get_config(key)
                if config_data and isinstance(config_data, dict) and config_data.get('is_active', True):
                    # 更新Redis缓存
                    redis_manager.cache_set(f"config:{key}", config_data, expire=0)  # 无过期时间
                    return self._parse_value(config_data['value'], config_data['config_type'])
            
            return default
            
        except Exception as e:
            logger.error(f"获取配置 {key} 失败: {e}")
            return default
    
    async def set_config(self, key: str, value: Any, description: str = "", config_type: str = None) -> bool:
        """
        设置配置值 - Redis单一真相源版本
        同时更新JSON文件（持久化）和Redis缓存（实时生效）
        """
        try:
            store = self._get_store()
            redis_manager = self._get_redis_manager()
            
            # 智能类型推断
            actual_config_type = self._determine_config_type(key, value, config_type)
            
            # 类型验证
            if not self._validate_value_type(value, actual_config_type):
                logger.error(f"配置{key}类型验证失败：期望{actual_config_type}，得到{type(value).__name__}，值：{value}")
                return False
            
            # 序列化值
            serialized_value = self._serialize_value(value, actual_config_type)
            
            # 获取现有配置信息（从Redis或JSON）
            existing_config = redis_manager.cache_get(f"config:{key}")
            if not existing_config:
                existing_config = store.get_config(key) if store else None
            
            # 构建配置数据
            config_data = {
                'value': serialized_value,
                'config_type': actual_config_type,
                'description': description or (existing_config.get('description', '') if existing_config else ''),
                'is_active': True
            }
            
            # 设置创建时间
            if existing_config is None:
                config_data['created_at'] = datetime.now().isoformat()
            else:
                config_data['created_at'] = existing_config.get('created_at', datetime.now().isoformat())
            
            # 1. 首先保存到JSON文件（持久化）
            json_success = store.set_config(key, config_data) if store else False
            if not json_success:
                logger.error(f"保存配置到JSON文件失败: {key}")
                return False
            
            # 2. 然后更新Redis缓存（实时生效）
            redis_success = redis_manager.cache_set(f"config:{key}", config_data, expire=0)
            if not redis_success:
                logger.warning(f"更新Redis缓存失败: {key}，但JSON文件已保存")
            
            # 3. 通知监听器
            self._notify_config_change(key, value, actual_config_type)
            
            logger.debug(f"配置已更新: {key} = {value} (JSON: {json_success}, Redis: {redis_success})")
            return True
            
        except Exception as e:
            logger.error(f"设置配置失败: {key} = {value}, 错误: {e}")
            return False
    
    # === Linus风格的类型安全便捷方法 ===
    async def set_boolean(self, key: str, value: bool, description: str = "") -> bool:
        """设置布尔配置 - 类型安全，无需指定config_type"""
        return await self.set_config(key, value, description, config_type="boolean")
    
    async def set_integer(self, key: str, value: int, description: str = "") -> bool:
        """设置整数配置 - 类型安全，无需指定config_type"""
        return await self.set_config(key, value, description, config_type="integer")
    
    async def set_string(self, key: str, value: str, description: str = "") -> bool:
        """设置字符串配置 - 类型安全，无需指定config_type"""
        return await self.set_config(key, value, description, config_type="string")
    
    async def set_json(self, key: str, value: dict, description: str = "") -> bool:
        """设置JSON配置 - 类型安全，无需指定config_type"""
        return await self.set_config(key, value, description, config_type="json")
    
    async def load_all_to_redis(self) -> bool:
        """从JSON文件加载所有配置到Redis - 系统启动时调用"""
        try:
            store = self._get_store()
            redis_manager = self._get_redis_manager()
            
            if not store:
                logger.error("JSON存储不可用，无法加载配置到Redis")
                return False
            
            # 获取所有配置
            all_configs = store.get_all_config()
            if not all_configs:
                logger.warning("未找到任何配置，Redis缓存为空")
                return True  # 空配置也算成功
            
            # 批量加载到Redis
            loaded_count = 0
            failed_count = 0
            
            for key, config_data in all_configs.items():
                if isinstance(config_data, dict) and config_data.get('is_active', True):
                    success = redis_manager.cache_set(f"config:{key}", config_data, expire=0)
                    if success:
                        loaded_count += 1
                    else:
                        failed_count += 1
                        logger.warning(f"加载配置到Redis失败: {key}")
            
            logger.info(f"✅ 配置已加载到Redis: 成功 {loaded_count} 个，失败 {failed_count} 个")
            return failed_count == 0
            
        except Exception as e:
            logger.error(f"加载配置到Redis失败: {e}")
            return False

    async def get_all_configs(self) -> Dict[str, Dict]:
        """获取所有配置 - Redis单一真相源版本"""
        try:
            store = self._get_store()
            if not store:
                return {}
                
            all_configs = store.get_all_config()
            result = {}
            
            for key, config_data in all_configs.items():
                if config_data.get('is_active', True):
                    result[key] = {
                        'value': self._parse_value(config_data['value'], config_data['config_type']),
                        'raw_value': config_data['value'],
                        'description': config_data.get('description', ''),
                        'config_type': config_data['config_type'],
                        'created_at': config_data.get('created_at', ''),
                        'updated_at': config_data.get('updated_at', '')
                    }
            
            return result
            
        except Exception as e:
            logger.error(f"获取所有配置失败: {e}")
            return {}
    
    async def delete_config(self, key: str) -> bool:
        """删除配置"""
        try:
            store = self._get_store()
            redis_manager = self._get_redis_manager()
            
            # 从JSON存储中删除
            success = store.delete_config(key)
            
            if success:
                # 从Redis中移除
                redis_manager.cache_delete(f"config:{key}")
                
                # 通知监听器
                self._notify_config_change(key, None, 'deleted')
                
                logger.debug(f"配置已删除: {key}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"删除配置失败: {key}, 错误: {e}")
            return False
    
    async def set_multiple_configs(self, configs: Dict[str, Dict[str, Any]]) -> bool:
        """批量设置配置"""
        try:
            store = self._get_store()
            redis_manager = self._get_redis_manager()
            
            # 构建所有配置数据
            config_data_map = {}
            for key, config_info in configs.items():
                value = config_info.get('value')
                description = config_info.get('description', '')
                config_type = config_info.get('config_type', 'string')
                
                # 序列化值
                serialized_value = self._serialize_value(value, config_type)
                
                # 获取现有配置信息（从Redis或JSON）
                existing_config = await self.get_config_raw(key) if hasattr(self, 'get_config_raw') else None
                
                config_data_map[key] = {
                    'value': serialized_value,
                    'config_type': config_type,
                    'description': description or (existing_config.get('description', '') if existing_config else ''),
                    'is_active': True,
                    'created_at': existing_config.get('created_at', datetime.now().isoformat()) if existing_config else datetime.now().isoformat()
                }
            
            # 批量保存到JSON存储
            success = store.set_multiple_config(config_data_map)
            
            if success:
                # 批量更新到Redis和通知监听器
                for key, config_data in config_data_map.items():
                    # 更新到Redis
                    redis_manager.cache_set(f"config:{key}", config_data, expire=0)
                    
                    # 通知监听器
                    original_value = configs[key]['value']
                    config_type = configs[key].get('config_type', 'string')
                    self._notify_config_change(key, original_value, config_type)
                
                logger.debug(f"批量配置已更新：{len(configs)} 个配置项")
                return True
            else:
                logger.error(f"批量保存配置到存储失败")
                return False
                
        except Exception as e:
            logger.error(f"批量设置配置失败: {e}")
            return False
    
    async def reload_redis(self, force_reinit_storage: bool = False):
        """重新从JSON加载配置到Redis"""
        logger.info("开始重新加载配置到Redis...")
        
        try:
            if force_reinit_storage:
                logger.info("强制重新初始化存储层...")
                # 重置存储实例
                self._json_store = None
                # 强制重新初始化JSON存储层
                from app.storage.json_store import force_reinit_json_stores
                if not force_reinit_json_stores():
                    logger.error("强制重新初始化存储层失败")
                    return False
            
            # 从JSON重新加载所有配置到Redis
            success = await self.load_all_to_redis()
            
            if success:
                logger.info("配置已重新加载到Redis")
                return True
            else:
                logger.error("配置重新加载到Redis失败")
                return False
                
        except Exception as e:
            logger.error(f"重新加载配置到Redis时发生异常: {e}")
            return False

    async def force_reload_with_retry(self, max_retries: int = 3):
        """强制重载配置到Redis，带存储层重新初始化和多次重试"""
        logger.info("开始强制重载配置到Redis...")
        
        for attempt in range(max_retries):
            try:
                # 第一次尝试普通重载，后续尝试强制重新初始化存储层
                force_storage = attempt > 0
                success = await self.reload_redis(force_reinit_storage=force_storage)
                
                if success:
                    logger.info(f"强制重载配置到Redis成功 (尝试 {attempt + 1}/{max_retries})")
                    return True
                    
            except Exception as e:
                logger.error(f"强制重载配置到Redis失败 (尝试 {attempt + 1}/{max_retries}): {e}")
            
            if attempt < max_retries - 1:
                import asyncio
                await asyncio.sleep(2.0 * (attempt + 1))  # 递增等待时间
        
        logger.error("强制重载配置到Redis多次重试后仍然失败")
        return False

    def is_storage_healthy(self) -> bool:
        """检查存储层健康状态"""
        try:
            from app.storage.json_store import is_json_stores_initialized
            return is_json_stores_initialized()
        except Exception as e:
            logger.error(f"检查存储层健康状态失败: {e}")
            return False

    async def get_storage_diagnostics(self) -> dict:
        """获取存储层诊断信息 - 区分全局和实例状态"""
        # 检查全局存储状态
        global_storage_healthy = self.is_storage_healthy()
        
        # 检查实例存储状态
        instance_store_available = self._json_store is not None
        
        # 尝试获取存储实例（如果当前为None）
        store_access_test = None
        if not instance_store_available:
            try:
                test_store = self._get_store()
                store_access_test = test_store is not None
            except Exception as e:
                store_access_test = f"获取失败: {e}"
        
        # 获取Redis连接状态
        redis_manager = self._get_redis_manager()
        redis_healthy = redis_manager.is_healthy()
        
        # 获取Redis中配置项数量（替代原缓存大小）
        cache_size = 0
        try:
            if redis_healthy:
                config_keys = redis_manager.redis_client.keys("config:*")
                cache_size = len(config_keys)
        except Exception as e:
            logger.debug(f"获取Redis配置项数量失败: {e}")
        
        diagnostics = {
            "redis_healthy": redis_healthy,
            "redis_connected": redis_healthy,
            "storage_healthy": global_storage_healthy,
            "json_store_available": instance_store_available,
            "store_access_test": store_access_test,
            "state_sync_ok": global_storage_healthy and instance_store_available and redis_healthy,
            "cache_size": cache_size,  # 兼容性：Redis中的配置项数量
            "critical_configs_status": {}
        }
        
        # 检查关键配置
        critical_configs = [
            'telegram.api_id',
            'telegram.api_hash', 
            'telegram.sender_session',
            'telegram.listener_session'
        ]
        
        for config_key in critical_configs:
            try:
                value = await self.get_config(config_key)
                diagnostics["critical_configs_status"][config_key] = {
                    "exists": value is not None,
                    "has_value": bool(value) if value is not None else False,
                    "type": type(value).__name__ if value is not None else "None"
                }
            except Exception as e:
                diagnostics["critical_configs_status"][config_key] = {
                    "exists": False,
                    "error": str(e)
                }
        
        return diagnostics
    
    def sync_instance_state(self) -> bool:
        """同步实例状态 - 修复状态不一致问题"""
        try:
            # 如果全局存储健康但实例存储不可用，尝试同步
            if self.is_storage_healthy() and self._json_store is None:
                logger.debug("检测到状态不同步，尝试修复...")
                
                # 强制重新获取存储实例
                store = self._get_store()
                if store is not None:
                    logger.info("实例状态同步成功")
                    return True
                else:
                    logger.warning("实例状态同步失败")
                    return False
            
            return True  # 已经同步或无需同步
            
        except Exception as e:
            logger.error(f"同步实例状态时发生异常: {e}")
            return False
    
    async def ensure_ready(self) -> bool:
        """确保ConfigManager处于就绪状态"""
        try:
            # 1. 检查并修复状态同步
            if not self.sync_instance_state():
                logger.error("ConfigManager状态同步失败")
                return False
            
            # 2. 检查Redis连接状态
            redis_manager = self._get_redis_manager()
            if not redis_manager.is_healthy():
                logger.error("Redis连接不健康")
                return False
            
            # 3. 验证关键配置
            await self._validate_critical_configs()
            
            logger.debug("ConfigManager已就绪")
            return True
            
        except Exception as e:
            logger.error(f"确保ConfigManager就绪时发生异常: {e}")
            return False
    
    async def clear_redis_configs(self):
        """清理Redis中的配置键"""
        try:
            redis_manager = self._get_redis_manager()
            
            # 获取所有config:*键并删除
            import redis
            r = redis_manager._redis
            config_keys = r.keys("config:*")
            
            if config_keys:
                r.delete(*config_keys)
                logger.info(f"已清理 {len(config_keys)} 个Redis配置键")
            else:
                logger.info("Redis中无配置键需要清理")
                
        except Exception as e:
            logger.error(f"清理Redis配置键失败: {e}")
    
    def add_change_listener(self, listener: Callable[[str, Any, str], None]):
        """添加配置变更监听器"""
        self._change_listeners.append(listener)
    
    def remove_change_listener(self, listener: Callable[[str, Any, str], None]):
        """移除配置变更监听器"""
        if listener in self._change_listeners:
            self._change_listeners.remove(listener)
    
    def _notify_config_change(self, key: str, value: Any, config_type: str):
        """通知配置变更"""
        for listener in self._change_listeners:
            try:
                listener(key, value, config_type)
            except Exception as e:
                logger.error(f"配置变更监听器错误: {e}")
    

    async def _validate_critical_configs(self):
        """验证关键配置是否存在"""
        critical_configs = [
            'telegram.api_id',
            'telegram.api_hash',
            'telegram.sender_session',
            'telegram.listener_session'
        ]
        
        redis_manager = self._get_redis_manager()
        missing_configs = []
        
        for config_key in critical_configs:
            # 从Redis获取配置
            config_data = redis_manager.cache_get(f"config:{config_key}")
            if not config_data or not config_data.get('value'):
                missing_configs.append(config_key)
        
        if missing_configs:
            logger.warning(f"关键配置缺失: {', '.join(missing_configs)}")
        else:
            logger.debug("所有关键配置验证通过")
    
    def _determine_config_type(self, key: str, value: Any, explicit_type: str = None) -> str:
        """
        Linus风格类型推断：消除手动指定config_type的特殊情况
        优先级：
        1. 如果提供了explicit_type，使用它（向后兼容）
        2. 如果key在DEFAULT_CONFIGS中，使用定义的类型
        3. 根据Python类型自动推断
        """
        # 优先级1：显式指定的类型（向后兼容）
        if explicit_type is not None:
            return explicit_type
            
        # 优先级2：根据Python类型自动推断
        return self._infer_type_from_value(value)
    
    def _infer_type_from_value(self, value: Any) -> str:
        """根据Python类型推断配置类型"""
        type_mapping = {
            bool: "boolean",
            int: "integer", 
            str: "string",
            list: "list",
            dict: "json"
        }
        return type_mapping.get(type(value), "string")
    
    def _validate_value_type(self, value: Any, expected_type: str) -> bool:
        """验证值是否符合期望的配置类型"""
        try:
            if expected_type == "boolean":
                return isinstance(value, (bool, int, str))  # 允许多种布尔值表示
            elif expected_type == "integer":
                return isinstance(value, (int, str)) and str(value).isdigit()
            elif expected_type == "string":
                return True  # 所有值都可以转为字符串
            elif expected_type == "json" or expected_type == "list":
                return isinstance(value, (dict, list, str))
            else:
                return True
        except:
            return False

    def _serialize_value(self, value: Any, config_type: str) -> str:
        """序列化配置值"""
        if config_type == "json" or config_type == "list":
            return json.dumps(value, ensure_ascii=False)
        elif config_type == "boolean":
            return str(bool(value)).lower()
        elif config_type == "integer":
            return str(int(value))
        else:
            return str(value)
    
    def _parse_value(self, value: str, config_type: str) -> Any:
        """解析配置值"""
        # 只有真正的None才返回None，空字符串应该保持
        if value is None:
            return None
        
        # 空字符串按类型处理
        if value == "":
            if config_type == "integer":
                return 0
            elif config_type == "boolean":
                return False
            else:
                return ""  # 字符串类型保持空字符串
            
        try:
            if config_type == "json" or config_type == "list":
                return json.loads(value)
            elif config_type == "boolean":
                return value.lower() in ('true', '1', 'yes', 'on')
            elif config_type == "integer":
                return int(value)
            else:
                return value
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"解析配置值失败: {value}, 类型: {config_type}, 错误: {e}")
            return value

# 全局配置管理器实例
config_manager = ConfigManager()

# 配置项定义



async def validate_config_types():
    """
    配置类型验证器 - 已废弃
    配置直接从system.json读取，无需验证
    """
    logger.info("ℹ️ validate_config_types 已废弃，配置由system.json直接管理")
    return