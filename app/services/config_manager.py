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
    """配置管理器"""
    
    def __init__(self):
        self._cache = {}
        self._cache_loaded = False
        self._cache_lock = threading.RLock()
        self._change_listeners = []  # 配置变更监听器
        self._json_store: Optional[JSONConfigStore] = None
        self._last_file_mtime = 0.0  # 上次文件修改时间
    
    def _get_store(self) -> Optional[JSONConfigStore]:
        """获取JSON存储实例"""
        if self._json_store is None:
            try:
                self._json_store = get_json_config_store()
            except RuntimeError as e:
                if "未初始化" in str(e):
                    logger.debug("JSON存储层未初始化")
                    return None
                raise
        return self._json_store
    
    def _check_file_updated(self) -> bool:
        """检查配置文件是否已更新"""
        try:
            config_file_path = "data/config/system.json"
            if os.path.exists(config_file_path):
                current_mtime = os.path.getmtime(config_file_path)
                if current_mtime > self._last_file_mtime:
                    self._last_file_mtime = current_mtime
                    return True
            return False
        except Exception as e:
            logger.debug(f"检查配置文件更新时间失败: {e}")
            return False
    
    async def get_config(self, key: str, default: Any = None) -> Any:
        """获取配置值"""
        with self._cache_lock:
            # 检查配置文件是否已更新，如果是则重新加载缓存
            if self._cache_loaded and self._check_file_updated():
                logger.debug("检测到配置文件更新，重新加载缓存")
                self._cache = {}
                self._cache_loaded = False
            
            # 尝试从缓存加载（考虑存储层时序）
            if not self._cache_loaded:
                await self._load_cache()
            
            # 缓存命中
            if key in self._cache:
                return self._parse_value(self._cache[key]['value'], self._cache[key]['config_type'])
            
            # 缓存未命中，直接从文件读取（按需加载）
            try:
                store = self._get_store()
                if store is not None:  # 存储层已可用
                    config_data = store.get_config(key) 
                    if config_data and isinstance(config_data, dict) and config_data.get('is_active', True):
                        # 保存到缓存
                        self._cache[key] = config_data
                        return self._parse_value(config_data['value'], config_data['config_type'])
            except Exception as e:
                logger.debug(f"按需读取配置 {key} 失败: {e}")
            
            return default
    
    async def set_config(self, key: str, value: Any, description: str = "", config_type: str = None) -> bool:
        """
        设置配置值 - Linus风格重构版本
        
        核心原则：消除特殊情况，类型自动推断
        - 如果key在DEFAULT_CONFIGS中，自动使用其定义的类型
        - 如果未定义，根据Python类型自动推断
        - 类型验证，防止错误数据
        """
        with self._cache_lock:
            # 确保缓存已加载
            if not self._cache_loaded:
                await self._load_cache()
                
            try:
                store = self._get_store()
                
                # Linus风格改进：智能类型推断（消除特殊情况）
                actual_config_type = self._determine_config_type(key, value, config_type)
                
                # 类型验证
                if not self._validate_value_type(value, actual_config_type):
                    logger.error(f"配置{key}类型验证失败：期望{actual_config_type}，得到{type(value).__name__}，值：{value}")
                    return False
                
                # 序列化值
                serialized_value = self._serialize_value(value, actual_config_type)
                
                # 获取现有配置信息（保留描述）
                existing_config = None
                if key in self._cache:
                    existing_config = self._cache[key]
                
                # 构建配置数据
                config_data = {
                    'value': serialized_value,
                    'config_type': actual_config_type,
                    'description': description or (existing_config.get('description', '') if existing_config else ''),
                    'is_active': True
                }
                
                # 如果是新配置，添加创建时间
                if existing_config is None:
                    config_data['created_at'] = datetime.now().isoformat()
                else:
                    config_data['created_at'] = existing_config.get('created_at', datetime.now().isoformat())
                
                # 保存到JSON存储
                success = store.set_config(key, config_data)
                
                if success:
                    # 更新缓存
                    self._cache[key] = config_data
                    
                    # 通知监听器
                    self._notify_config_change(key, value, config_type)
                    
                    logger.debug(f"配置已更新: {key} = {value}")
                    return True
                else:
                    logger.error(f"保存配置到存储失败: {key}")
                    return False
                    
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

    async def get_all_configs(self) -> Dict[str, Dict]:
        """获取所有配置"""
        with self._cache_lock:
            if not self._cache_loaded:
                await self._load_cache()
            
            result = {}
            for key, config_data in self._cache.items():
                if config_data.get('is_active', True):  # 默认为激活状态
                    result[key] = {
                        'value': self._parse_value(config_data['value'], config_data['config_type']),
                        'raw_value': config_data['value'],
                        'description': config_data.get('description', ''),
                        'config_type': config_data['config_type'],
                        'created_at': config_data.get('created_at', ''),
                        'updated_at': config_data.get('updated_at', '')
                    }
            
            return result
    
    async def delete_config(self, key: str) -> bool:
        """删除配置"""
        with self._cache_lock:
            try:
                store = self._get_store()
                
                # 从JSON存储中删除
                success = store.delete_config(key)
                
                if success:
                    # 从缓存中移除
                    if key in self._cache:
                        del self._cache[key]
                    
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
        with self._cache_lock:
            # 确保缓存已加载
            if not self._cache_loaded:
                await self._load_cache()
                
            try:
                store = self._get_store()
                
                # 构建所有配置数据
                config_data_map = {}
                for key, config_info in configs.items():
                    value = config_info.get('value')
                    description = config_info.get('description', '')
                    config_type = config_info.get('config_type', 'string')
                    
                    # 序列化值
                    serialized_value = self._serialize_value(value, config_type)
                    
                    # 获取现有配置信息
                    existing_config = self._cache.get(key)
                    
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
                    # 批量更新缓存和通知监听器
                    for key, config_data in config_data_map.items():
                        self._cache[key] = config_data
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
    
    async def reload_cache(self):
        """重新加载缓存"""
        with self._cache_lock:
            self._cache = {}
            self._cache_loaded = False
            await self._load_cache()
            logger.info("配置缓存已重新加载")
    
    async def clear_cache(self):
        """清理缓存"""
        with self._cache_lock:
            self._cache = {}
            self._cache_loaded = False
            logger.info("配置缓存已清理")
    
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
    
    async def _load_cache(self):
        """加载配置到缓存"""
        try:
            store = self._get_store()
            # 检查存储层是否已初始化
            if store is None:
                logger.debug("JSON存储层未初始化，稍后重试")
                return  # 不标记为已加载，允许后续重试
                
            all_configs = store.get_all_config()
            
            # 只加载活跃的配置
            for key, config_data in all_configs.items():
                if isinstance(config_data, dict) and config_data.get('is_active', True):
                    self._cache[key] = config_data
            
            self._cache_loaded = True
            logger.info(f"已从JSON存储加载 {len(self._cache)} 个配置项到缓存")
            
        except Exception as e:
            logger.error(f"加载配置缓存失败: {e}")
            # 不标记为已加载，允许后续重试
    
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