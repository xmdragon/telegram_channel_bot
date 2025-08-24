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
    
    def _get_store(self) -> JSONConfigStore:
        """获取JSON存储实例"""
        if self._json_store is None:
            self._json_store = get_json_config_store()
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
            # 🔄 检查配置文件是否已更新，如果是则重新加载缓存
            if self._cache_loaded and self._check_file_updated():
                logger.debug("检测到配置文件更新，重新加载缓存")
                self._cache = {}
                self._cache_loaded = False
            
            if not self._cache_loaded:
                await self._load_cache()
            
            if key in self._cache:
                return self._parse_value(self._cache[key]['value'], self._cache[key]['config_type'])
            
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
                    'is_active': True,
                    'updated_at': datetime.now().isoformat()
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
                        'updated_at': datetime.now().isoformat(),
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
            all_configs = store.get_all_config()
            
            # 只加载活跃的配置
            for key, config_data in all_configs.items():
                if isinstance(config_data, dict) and config_data.get('is_active', True):
                    self._cache[key] = config_data
            
            self._cache_loaded = True
            logger.info(f"已从JSON存储加载 {len(self._cache)} 个配置项到缓存")
            
        except Exception as e:
            logger.error(f"加载配置缓存失败: {e}")
            # 如果加载失败，至少标记为已加载，避免无限循环
            self._cache_loaded = True
    
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
            
        # 优先级2：DEFAULT_CONFIGS中的类型定义（单一真相源）
        if key in DEFAULT_CONFIGS:
            return DEFAULT_CONFIGS[key]['config_type']
            
        # 优先级3：根据Python类型自动推断
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
        if not value:
            return None
            
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
DEFAULT_CONFIGS = {
    # Telegram配置
    "telegram.api_id": {
        "value": "",
        "description": "Telegram API ID (从 https://my.telegram.org 获取)",
        "config_type": "integer"
    },
    "telegram.api_hash": {
        "value": "",
        "description": "Telegram API Hash (从 https://my.telegram.org 获取)",
        "config_type": "string"
    },
    
    # 目标频道配置
    "target.channel_link": {
        "value": "",
        "description": "目标频道链接（用户配置）",
        "config_type": "string"
    },
    "target.channel_id": {
        "value": "",
        "description": "目标频道ID（系统解析缓存）",
        "config_type": "string"
    },
    "target.signature": {
        "value": "",
        "description": "频道落款内容（支持多行，用\\n分隔）",
        "config_type": "string"
    },
    
    # 审核群配置
    "review.group_link": {
        "value": "",
        "description": "审核群链接（用户配置）",
        "config_type": "string"
    },
    "review.group_id": {
        "value": "",
        "description": "审核群ID（系统解析缓存）",
        "config_type": "string"
    },
    
    # 消息采集配置
    "source.history_limit": {
        "value": 50,
        "description": "首次采集频道时获取的历史消息条数 (包括进程中断后重启)",
        "config_type": "integer"
    },
    
    
    
    # 审核配置
    "review.auto_forward_enabled": {
        "value": False,
        "description": "是否启用自动转发",
        "config_type": "boolean"
    },
    "review.auto_forward_delay": {
        "value": 1800,
        "description": "自动转发延迟(秒)",
        "config_type": "integer"
    },
    
    
    # 服务控制配置
    "collection.enabled": {
        "value": True,
        "description": "启用Telegram消息采集",
        "config_type": "boolean"
    },
    "scheduler.enabled": {
        "value": True, 
        "description": "启用消息调度服务（自动转发、清理）",
        "config_type": "boolean"
    },
    
}

async def init_default_configs():
    """初始化默认配置"""
    logger.info("正在初始化默认配置...")
    
    initialized_count = 0
    for key, config_info in DEFAULT_CONFIGS.items():
        existing_value = await config_manager.get_config(key)
        # 只有当值为None或空字符串时才初始化（对于cached字段，保留已有的值）
        if existing_value is None or (existing_value == "" and not key.endswith("_cached")):
            # Linus风格：使用类型推断而不是显式传递config_type
            success = await config_manager.set_config(
                key=key,
                value=config_info["value"],
                description=config_info["description"]
                # config_type自动从DEFAULT_CONFIGS推断，消除重复信息
            )
            if success:
                logger.info(f"已初始化配置: {key}")
                initialized_count += 1
            else:
                logger.error(f"初始化配置失败: {key}")
    
    logger.info(f"默认配置初始化完成，共初始化 {initialized_count} 个配置项")
    
    # 执行配置类型验证（Linus风格防御）
    await validate_config_types()


async def validate_config_types():
    """
    Linus风格配置类型验证器
    启动时验证所有配置的类型是否与DEFAULT_CONFIGS一致
    发现不一致时自动修复
    """
    logger.info("🔍 执行配置类型一致性验证...")
    
    fixed_count = 0
    all_configs = await config_manager.get_all_configs()
    
    for key, expected_config in DEFAULT_CONFIGS.items():
        expected_type = expected_config['config_type']
        
        if key in all_configs:
            stored_config = all_configs[key]
            
            # 🚨 Linus风格防护：检查数据类型，避免在字符串上调用.get()
            if not isinstance(stored_config, dict):
                logger.error(f"🔧 配置数据格式错误: {key} 不是字典格式，是 {type(stored_config)}")
                continue
                
            actual_type = stored_config.get('config_type', 'unknown')
            
            if actual_type != expected_type:
                logger.warning(f"🔧 配置类型不一致修复: {key} ({actual_type} -> {expected_type})")
                
                # 重新保存配置以修复类型
                current_value = await config_manager.get_config(key)
                success = await config_manager.set_config(
                    key=key,
                    value=current_value if current_value is not None else expected_config['value'],
                    description=stored_config.get('description', expected_config['description'])
                )
                
                if success:
                    fixed_count += 1
                    logger.info(f"✅ 修复完成: {key}")
                else:
                    logger.error(f"❌ 修复失败: {key}")
    
    if fixed_count > 0:
        logger.info(f"🎯 配置类型验证完成，修复了 {fixed_count} 个问题")
    else:
        logger.info("✅ 所有配置类型验证通过")