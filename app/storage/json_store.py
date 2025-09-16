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
            # 禁用自动备份，由用户自己备份
            success = SafeFileOperation.write_json_safe(file_path, data, backup=False)
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
        """获取所有频道配置（简化版）"""
        channels_data = self._load_json(self.CHANNEL_FILE)
        # 新格式：直接返回数组
        if isinstance(channels_data, list):
            return channels_data
        # 兼容旧格式：转换对象为数组
        elif isinstance(channels_data, dict):
            return list(channels_data.values()) if channels_data else []
        else:
            return []
    
    def add_channel(self, channel_data: Dict[str, Any]) -> bool:
        """添加频道配置（数组版）"""
        try:
            channels = self.get_all_channels()
            
            # 验证频道数据
            channel_id = channel_data.get('channel_id')
            channel_name = channel_data.get('channel_name')
            
            # 检查频道是否已存在（去重）
            for existing_channel in channels:
                if (existing_channel.get('channel_id') == channel_id and channel_id) or \
                   (existing_channel.get('channel_name') == channel_name and channel_name):
                    logger.warning(f"频道已存在: {channel_name} / {channel_id}")
                    return False
                    
            # 生成新ID
            new_id = max(ch.get('id', 0) for ch in channels) + 1 if channels else 1
            channel_data['id'] = new_id
            
            # 添加时间戳
            channel_data = channel_data.copy()
            channel_data['updated_at'] = get_current_time().isoformat()
            if 'created_at' not in channel_data:
                channel_data['created_at'] = get_current_time().isoformat()
            
            # 添加到数组
            channels.append(channel_data)
            return self._save_json(self.CHANNEL_FILE, channels)
            
        except Exception as e:
            logger.error(f"添加频道配置失败: {e}")
            return False
    
    
    def update_channel(self, channel_data: Dict[str, Any]) -> bool:
        """更新频道配置（数组版）"""
        try:
            channels = self.get_all_channels()
            target_id = channel_data.get('id')
            
            # 通过ID查找并更新
            for i, channel in enumerate(channels):
                if channel.get('id') == target_id:
                    # 合并数据并更新时间戳
                    updated_channel = {**channel, **channel_data}
                    updated_channel['updated_at'] = get_current_time().isoformat()
                    channels[i] = updated_channel
                    return self._save_json(self.CHANNEL_FILE, channels)
            
            logger.error(f"未找到ID为 {target_id} 的频道")
            return False
            
        except Exception as e:
            logger.error(f"更新频道配置失败: {e}")
            return False
    
    def delete_channel(self, channel_identifier) -> bool:
        """删除频道配置（数组版）"""
        try:
            channels = self.get_all_channels()
            initial_count = len(channels)
            
            # 根据ID或名称过滤
            if isinstance(channel_identifier, (int, str)) and str(channel_identifier).isdigit():
                target_id = int(channel_identifier)
                channels = [ch for ch in channels if ch.get('id') != target_id]
            else:
                channels = [ch for ch in channels if ch.get('channel_name') != channel_identifier]
            
            # 检查是否删除了频道
            if len(channels) < initial_count:
                return self._save_json(self.CHANNEL_FILE, channels)
            
            return False
            
        except Exception as e:
            logger.error(f"删除频道配置失败 {channel_identifier}: {e}")
            return False

class JSONAdminStore(JSONStore):
    """管理员数据存储"""
    
    ADMIN_FILE = "admins.json"
    
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
    


# 全局实例和初始化同步机制
import threading
_init_lock = threading.RLock()  # 可重入锁，支持嵌套调用
_initialization_complete = False
_initialization_in_progress = False

json_config_store = None
json_channel_store = None
json_admin_store = None

def init_json_stores(data_dir: str = None):
    """初始化JSON存储实例 - 线程安全的单例模式"""
    global json_config_store, json_channel_store, json_admin_store
    global _initialization_complete, _initialization_in_progress
    
    with _init_lock:
        # 如果已经完成初始化，直接返回
        if _initialization_complete:
            logger.debug("JSON存储层已经初始化完成，跳过重复初始化")
            return True
        
        # 如果正在初始化中，等待完成
        if _initialization_in_progress:
            logger.debug("JSON存储层正在初始化中，等待完成...")
            # 释放锁让其他线程完成初始化，然后重新检查
            return _wait_for_initialization()
        
        # 标记初始化开始
        _initialization_in_progress = True
        logger.debug("开始JSON存储层初始化...")
    
    try:
        # 实际的初始化过程（在锁外进行，避免长时间占用锁）
        config_store = JSONConfigStore(data_dir)
        channel_store = JSONChannelStore(data_dir)
        admin_store = JSONAdminStore(data_dir)
        
        
        # 原子性设置全局变量
        with _init_lock:
            json_config_store = config_store
            json_channel_store = channel_store
            json_admin_store = admin_store
            _initialization_complete = True
            _initialization_in_progress = False
        
        logger.info("JSON存储层初始化成功")
        return True
        
    except Exception as e:
        # 重置状态，允许重试
        with _init_lock:
            _initialization_in_progress = False
            _initialization_complete = False
        
        logger.error(f"JSON存储层初始化失败: {e}")
        return False

def _wait_for_initialization(timeout=30):
    """等待其他线程完成初始化"""
    import time
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        with _init_lock:
            if _initialization_complete:
                return True
            if not _initialization_in_progress:
                # 初始化进程异常结束，需要重新初始化
                break
        
        time.sleep(0.1)  # 短暂等待
    
    logger.warning("等待JSON存储层初始化超时或失败")
    return False

def get_json_config_store() -> JSONConfigStore:
    """获取配置存储实例 - 带自动初始化重试"""
    if json_config_store is None:
        logger.debug("配置存储未初始化，尝试自动初始化...")
        if not init_json_stores():
            raise RuntimeError("JSON存储层未初始化且自动初始化失败")
    return json_config_store

def get_json_channel_store() -> JSONChannelStore:
    """获取频道存储实例 - 带自动初始化重试"""
    if json_channel_store is None:
        logger.debug("频道存储未初始化，尝试自动初始化...")
        if not init_json_stores():
            raise RuntimeError("JSON存储层未初始化且自动初始化失败")
    return json_channel_store

def get_json_admin_store() -> JSONAdminStore:
    """获取管理员存储实例 - 带自动初始化重试"""
    if json_admin_store is None:
        logger.debug("管理员存储未初始化，尝试自动初始化...")
        if not init_json_stores():
            raise RuntimeError("JSON存储层未初始化且自动初始化失败")
    return json_admin_store

def force_reinit_json_stores(data_dir: str = None):
    """强制重新初始化JSON存储层"""
    global json_config_store, json_channel_store, json_admin_store
    global _initialization_complete, _initialization_in_progress
    
    logger.info("强制重新初始化JSON存储层...")
    
    with _init_lock:
        # 重置所有状态
        json_config_store = None
        json_channel_store = None
        json_admin_store = None
        _initialization_complete = False
        _initialization_in_progress = False
    
    # 重新初始化
    return init_json_stores(data_dir)

def is_json_stores_initialized() -> bool:
    """检查JSON存储层是否已初始化"""
    with _init_lock:
        return _initialization_complete and all([
            json_config_store is not None,
            json_channel_store is not None, 
            json_admin_store is not None
        ])