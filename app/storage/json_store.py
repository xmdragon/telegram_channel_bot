"""
JSON文件存储层
处理系统配置、用户权限等数据的存储
"""
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
from app.utils.safe_file_ops import SafeFileOperation
from app.utils.timezone import get_current_time

logger = logging.getLogger(__name__)

class JSONStore:
    """JSON文件存储基类"""
    
    def __init__(self, data_dir: str = None):
        if data_dir is None:
            data_dir = "./data/config"
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"JSON存储初始化: {self.data_dir}")
    
    def _get_file_path(self, filename: str) -> Path:
        """获取文件完整路径"""
        return self.data_dir / filename
    
    def _load_json(self, filename: str) -> Dict[str, Any]:
        """加载JSON文件（使用SafeFileOperation统一锁机制）"""
        file_path = self._get_file_path(filename)
        
        try:
            # 使用SafeFileOperation统一的文件锁机制
            data = SafeFileOperation.read_json_safe(file_path)
            return data or {}
            
        except Exception as e:
            logger.error(f"加载JSON文件失败 {filename}: {e}")
            return {}
    
    def _save_json(self, filename: str, data: Dict[str, Any]) -> bool:
        """保存JSON文件（使用SafeFileOperation统一锁机制）"""
        file_path = self._get_file_path(filename)
        
        try:
            # system.json频繁更新，不需要备份；其他文件保持备份
            should_backup = filename != "system.json"
            success = SafeFileOperation.write_json_safe(file_path, data, backup=should_backup)
            if success:
                logger.debug(f"JSON文件已保存: {filename}")
            return success
            
        except Exception as e:
            logger.error(f"保存JSON文件失败 {filename}: {e}")
            return False

class JSONConfigStore(JSONStore):
    """系统配置存储"""
    
    CONFIG_FILE = "system.json"
    
    def __init__(self, data_dir: str = None):
        super().__init__(data_dir)
        self._config_cache = None
        self._cache_time = None
        
    def _get_config(self, refresh: bool = False) -> Dict[str, Any]:
        """获取配置（带缓存）"""
        if refresh or self._config_cache is None or \
           (self._cache_time and (datetime.now() - self._cache_time).seconds > 60):
            self._config_cache = self._load_json(self.CONFIG_FILE)
            self._cache_time = datetime.now()
        
        return self._config_cache
    
    def get_config(self, key: str, default: Any = None) -> Any:
        """获取配置项"""
        try:
            config = self._get_config()
            return config.get(key, default)
        except Exception as e:
            logger.error(f"获取配置失败 {key}: {e}")
            return default
    
    def set_config(self, key: str, value: Any) -> bool:
        """设置配置项"""
        try:
            config = self._get_config()
            config[key] = value
            config['updated_at'] = get_current_time().isoformat()
            
            if self._save_json(self.CONFIG_FILE, config):
                self._config_cache = config  # 更新缓存
                return True
            return False
            
        except Exception as e:
            logger.error(f"设置配置失败 {key}: {e}")
            return False
    
    def get_all_config(self) -> Dict[str, Any]:
        """获取所有配置"""
        return self._get_config().copy()
    
    def set_multiple_config(self, configs: Dict[str, Any]) -> bool:
        """批量设置配置"""
        try:
            config = self._get_config()
            config.update(configs)
            config['updated_at'] = get_current_time().isoformat()
            
            if self._save_json(self.CONFIG_FILE, config):
                self._config_cache = config
                return True
            return False
            
        except Exception as e:
            logger.error(f"批量设置配置失败: {e}")
            return False
    
    def delete_config(self, key: str) -> bool:
        """删除配置项"""
        try:
            config = self._get_config()
            if key in config:
                del config[key]
                config['updated_at'] = get_current_time().isoformat()
                
                if self._save_json(self.CONFIG_FILE, config):
                    self._config_cache = config
                    return True
            return False
            
        except Exception as e:
            logger.error(f"删除配置失败 {key}: {e}")
            return False

class JSONChannelStore(JSONStore):
    """频道配置存储"""
    
    CHANNEL_FILE = "channels.json"
    
    def get_channel(self, channel_id: str) -> Optional[Dict[str, Any]]:
        """获取频道配置"""
        try:
            channels = self._load_json(self.CHANNEL_FILE)
            return channels.get(channel_id)
        except Exception as e:
            logger.error(f"获取频道配置失败 {channel_id}: {e}")
            return None
    
    def save_channel(self, channel_id: str, channel_data: Dict[str, Any]) -> bool:
        """保存频道配置"""
        try:
            channels = self._load_json(self.CHANNEL_FILE)
            
            # 添加时间戳
            channel_data = channel_data.copy()
            channel_data['updated_at'] = get_current_time().isoformat()
            if 'created_at' not in channel_data:
                channel_data['created_at'] = get_current_time().isoformat()
            
            channels[channel_id] = channel_data
            return self._save_json(self.CHANNEL_FILE, channels)
            
        except Exception as e:
            logger.error(f"保存频道配置失败 {channel_id}: {e}")
            return False
    
    def get_all_channels(self) -> List[Dict[str, Any]]:
        """获取所有频道配置"""
        channels_dict = self._load_json(self.CHANNEL_FILE)
        # 转换为列表格式，兼容旧的API
        return list(channels_dict.values()) if channels_dict else []
    
    def add_channel(self, channel_data: Dict[str, Any]) -> bool:
        """添加频道配置"""
        try:
            channels = self._load_json(self.CHANNEL_FILE)
            
            # 验证频道数据
            channel_id = channel_data.get('channel_id')
            channel_name = channel_data.get('channel_name')
            channel_type = channel_data.get('channel_type', 'source')
            
            # 防止目标频道被添加为源频道
            if channel_type == 'source' and channel_id:
                try:
                    # 获取目标频道配置进行比较
                    from app.services.config_manager import config_manager
                    import asyncio
                    
                    # 在同步方法中运行异步代码
                    loop = None
                    try:
                        loop = asyncio.get_event_loop()
                    except RuntimeError:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                    
                    target_channel_id = loop.run_until_complete(config_manager.get_config('target.channel_id'))
                    target_channel = loop.run_until_complete(config_manager.get_config('target.channel_link'))
                    
                    if channel_id == target_channel_id or channel_name == target_channel:
                        logger.error(f"拒绝添加目标频道为源频道: {channel_name} ({channel_id})")
                        return False
                except Exception as e:
                    logger.warning(f"验证目标频道时出错，跳过验证: {e}")
            
            if channel_id:
                # 检查是否已存在
                for existing_key, existing_data in channels.items():
                    if existing_data.get('channel_id') == channel_id:
                        logger.warning(f"频道已存在，跳过添加: {channel_id}")
                        return True  # 返回True避免错误，但不重复添加
            
            # 生成一致的键格式 channel_{id}
            channel_key = None
            if 'id' in channel_data:
                # 如果有数字ID，使用channel_前缀格式
                channel_key = f"channel_{channel_data['id']}"
            else:
                # 如果没有数字ID，生成一个新的ID
                existing_ids = []
                for key, data in channels.items():
                    if key.startswith('channel_') and data.get('id'):
                        existing_ids.append(data['id'])
                new_id = max(existing_ids, default=0) + 1
                channel_data['id'] = new_id
                channel_key = f"channel_{new_id}"
            
            if not channel_key:
                logger.error("无法生成频道键")
                return False
            
            # 添加时间戳
            channel_data = channel_data.copy()
            channel_data['updated_at'] = get_current_time().isoformat()
            if 'created_at' not in channel_data:
                channel_data['created_at'] = get_current_time().isoformat()
            
            channels[channel_key] = channel_data
            return self._save_json(self.CHANNEL_FILE, channels)
            
        except Exception as e:
            logger.error(f"添加频道配置失败: {e}")
            return False
    
    def get_channels_by_type(self, channel_type: str) -> List[Dict[str, Any]]:
        """根据类型获取频道"""
        try:
            channels = self._load_json(self.CHANNEL_FILE)
            result = []
            
            for channel_key, channel_data in channels.items():
                if channel_data.get('channel_type') == channel_type:
                    # 复制频道数据，但不要覆盖原有的channel_id字段
                    channel_data = channel_data.copy()
                    # 保持原有的channel_id字段不变（它包含正确的Telegram ID）
                    result.append(channel_data)
            
            return result
            
        except Exception as e:
            logger.error(f"获取频道类型失败 {channel_type}: {e}")
            return []
    
    def update_channel(self, channel_data: Dict[str, Any]) -> bool:
        """更新频道配置"""
        try:
            channels = self._load_json(self.CHANNEL_FILE)
            
            # 查找频道键
            channel_key = None
            
            # 优先通过数字ID查找（最可靠的方式）
            if 'id' in channel_data:
                target_id = channel_data['id']
                for key, data in channels.items():
                    if data.get('id') == target_id:
                        channel_key = key
                        break
            
            # 如果没找到，尝试通过channel_id查找
            if not channel_key and 'channel_id' in channel_data:
                target_channel_id = channel_data['channel_id']
                for key, data in channels.items():
                    if data.get('channel_id') == target_channel_id:
                        channel_key = key
                        break
            
            # 如果还没找到，尝试通过channel_name查找
            if not channel_key and 'channel_name' in channel_data:
                target_name = channel_data['channel_name']
                for key, data in channels.items():
                    if data.get('channel_name') == target_name:
                        channel_key = key
                        break
            
            if not channel_key:
                logger.error(f"未找到频道键，搜索条件: {channel_data}")
                return False
            
            if channel_key not in channels:
                logger.error(f"频道不存在: {channel_key}")
                return False
            
            # 更新频道数据
            updated_data = channels[channel_key].copy()
            updated_data.update(channel_data)
            updated_data['updated_at'] = get_current_time().isoformat()
            
            channels[channel_key] = updated_data
            return self._save_json(self.CHANNEL_FILE, channels)
            
        except Exception as e:
            logger.error(f"更新频道配置失败: {e}")
            return False
    
    def delete_channel(self, channel_identifier) -> bool:
        """删除频道配置（支持名称或ID）"""
        try:
            channels = self._load_json(self.CHANNEL_FILE)
            
            # 如果是数字ID，查找对应的channel_name
            if isinstance(channel_identifier, (int, str)) and str(channel_identifier).isdigit():
                target_id = int(channel_identifier)
                channel_key = None
                for name, data in channels.items():
                    if data.get('id') == target_id:
                        channel_key = name
                        break
                
                if channel_key and channel_key in channels:
                    del channels[channel_key]
                    return self._save_json(self.CHANNEL_FILE, channels)
            else:
                # 直接使用名称删除
                if channel_identifier in channels:
                    del channels[channel_identifier]
                    return self._save_json(self.CHANNEL_FILE, channels)
            
            return False
            
        except Exception as e:
            logger.error(f"删除频道配置失败 {channel_identifier}: {e}")
            return False

class JSONAdminStore(JSONStore):
    """管理员数据存储"""
    
    ADMIN_FILE = "admins.json"
    PERMISSION_FILE = "permissions.json"
    ADMIN_PERM_FILE = "admin_permissions.json"
    
    def get_admin_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """根据用户名获取管理员"""
        try:
            admins = self._load_json(self.ADMIN_FILE)
            for admin_id, admin_data in admins.items():
                if admin_data.get('username') == username:
                    admin_data = admin_data.copy()
                    admin_data['id'] = int(admin_id)
                    return admin_data
            return None
            
        except Exception as e:
            logger.error(f"获取管理员失败 {username}: {e}")
            return None
    
    def get_admin_by_id(self, admin_id: int) -> Optional[Dict[str, Any]]:
        """根据ID获取管理员"""
        try:
            admins = self._load_json(self.ADMIN_FILE)
            admin_data = admins.get(str(admin_id))
            if admin_data:
                admin_data = admin_data.copy()
                admin_data['id'] = admin_id
            return admin_data
            
        except Exception as e:
            logger.error(f"获取管理员失败 {admin_id}: {e}")
            return None
    
    def save_admin(self, admin_data: Dict[str, Any]) -> bool:
        """保存管理员"""
        try:
            admins = self._load_json(self.ADMIN_FILE)
            
            # 生成新ID或使用现有ID
            if 'id' in admin_data:
                admin_id = str(admin_data['id'])
                del admin_data['id']  # 移除ID字段，不存储在数据中
            else:
                # 生成新ID
                existing_ids = [int(k) for k in admins.keys() if k.isdigit()]
                admin_id = str(max(existing_ids, default=0) + 1)
            
            # 添加时间戳
            admin_data = admin_data.copy()
            admin_data['updated_at'] = get_current_time().isoformat()
            if 'created_at' not in admin_data:
                admin_data['created_at'] = get_current_time().isoformat()
            
            admins[admin_id] = admin_data
            return self._save_json(self.ADMIN_FILE, admins)
            
        except Exception as e:
            logger.error(f"保存管理员失败: {e}")
            return False
    
    def get_admin_permissions(self, admin_id: int) -> List[str]:
        """获取管理员权限"""
        try:
            admin_perms = self._load_json(self.ADMIN_PERM_FILE)
            permissions = self._load_json(self.PERMISSION_FILE)
            
            result = []
            for perm_id in admin_perms.get(str(admin_id), []):
                perm_data = permissions.get(str(perm_id))
                if perm_data:
                    result.append(perm_data.get('name', ''))
            
            return result
            
        except Exception as e:
            logger.error(f"获取管理员权限失败 {admin_id}: {e}")
            return []
    
    def set_admin_permissions(self, admin_id: int, permission_names: List[str]) -> bool:
        """设置管理员权限"""
        try:
            permissions = self._load_json(self.PERMISSION_FILE)
            admin_perms = self._load_json(self.ADMIN_PERM_FILE)
            
            # 根据权限名称找到权限ID
            permission_ids = []
            for perm_id, perm_data in permissions.items():
                if perm_data.get('name') in permission_names:
                    permission_ids.append(int(perm_id))
            
            admin_perms[str(admin_id)] = permission_ids
            return self._save_json(self.ADMIN_PERM_FILE, admin_perms)
            
        except Exception as e:
            logger.error(f"设置管理员权限失败 {admin_id}: {e}")
            return False
    
    def get_all_permissions(self) -> List[Dict[str, Any]]:
        """获取所有权限"""
        try:
            permissions = self._load_json(self.PERMISSION_FILE)
            result = []
            
            for perm_id, perm_data in permissions.items():
                perm_data = perm_data.copy()
                perm_data['id'] = int(perm_id)
                result.append(perm_data)
            
            return result
            
        except Exception as e:
            logger.error(f"获取所有权限失败: {e}")
            return []
    
    def has_permission(self, admin_id: int, permission_name: str) -> bool:
        """检查管理员是否有指定权限"""
        try:
            # 检查是否为超级管理员
            admin = self.get_admin_by_id(admin_id)
            if admin and admin.get('is_super_admin'):
                return True
            
            # 检查具体权限
            admin_permissions = self.get_admin_permissions(admin_id)
            return permission_name in admin_permissions
            
        except Exception as e:
            logger.error(f"检查权限失败 {admin_id} {permission_name}: {e}")
            return False

    def init_default_permissions(self):
        """初始化默认权限"""
        try:
            permissions = self._load_json(self.PERMISSION_FILE)
            
            # 如果权限文件为空，创建默认权限
            if not permissions:
                default_permissions = {
                    "1": {"name": "messages.view", "module": "messages", "action": "view", "description": "查看消息"},
                    "2": {"name": "messages.edit", "module": "messages", "action": "edit", "description": "编辑消息"},
                    "3": {"name": "messages.delete", "module": "messages", "action": "delete", "description": "删除消息"},
                    "4": {"name": "config.view", "module": "config", "action": "view", "description": "查看配置"},
                    "5": {"name": "config.edit", "module": "config", "action": "edit", "description": "编辑配置"},
                    "6": {"name": "admin.manage", "module": "admin", "action": "manage", "description": "管理员管理"},
                    "7": {"name": "system.monitor", "module": "system", "action": "monitor", "description": "系统监控"},
                }
                
                for perm_id, perm_data in default_permissions.items():
                    perm_data['created_at'] = get_current_time().isoformat()
                
                self._save_json(self.PERMISSION_FILE, default_permissions)
                logger.info("默认权限已创建")
                
        except Exception as e:
            logger.error(f"初始化权限失败: {e}")

# 全局实例
json_config_store = None
json_channel_store = None
json_admin_store = None

def init_json_stores(data_dir: str = None):
    """初始化JSON存储实例 - 单例模式，避免重复初始化"""
    global json_config_store, json_channel_store, json_admin_store
    
    # 检查是否已经初始化
    if json_config_store is not None and json_channel_store is not None and json_admin_store is not None:
        logger.debug("JSON存储层已经初始化，跳过重复初始化")
        return True
    
    try:
        json_config_store = JSONConfigStore(data_dir)
        json_channel_store = JSONChannelStore(data_dir)
        json_admin_store = JSONAdminStore(data_dir)
        
        # 初始化默认权限
        json_admin_store.init_default_permissions()
        
        logger.info("JSON存储层初始化成功")
        return True
        
    except Exception as e:
        logger.error(f"JSON存储层初始化失败: {e}")
        return False

def get_json_config_store() -> JSONConfigStore:
    """获取配置存储实例"""
    if json_config_store is None:
        raise RuntimeError("JSON存储层未初始化")
    return json_config_store

def get_json_channel_store() -> JSONChannelStore:
    """获取频道存储实例"""
    if json_channel_store is None:
        raise RuntimeError("JSON存储层未初始化")
    return json_channel_store

def get_json_admin_store() -> JSONAdminStore:
    """获取管理员存储实例"""
    if json_admin_store is None:
        raise RuntimeError("JSON存储层未初始化")
    return json_admin_store