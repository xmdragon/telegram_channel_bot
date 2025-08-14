"""
配置管理服务
"""
import json
import logging
import threading
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
    
    def _get_store(self) -> JSONConfigStore:
        """获取JSON存储实例"""
        if self._json_store is None:
            self._json_store = get_json_config_store()
        return self._json_store
    
    async def get_config(self, key: str, default: Any = None) -> Any:
        """获取配置值"""
        with self._cache_lock:
            if not self._cache_loaded:
                await self._load_cache()
            
            if key in self._cache:
                return self._parse_value(self._cache[key]['value'], self._cache[key]['config_type'])
            
            return default
    
    async def set_config(self, key: str, value: Any, description: str = "", config_type: str = "string") -> bool:
        """设置配置值"""
        with self._cache_lock:
            # 确保缓存已加载
            if not self._cache_loaded:
                await self._load_cache()
                
            try:
                store = self._get_store()
                
                # 序列化值
                serialized_value = self._serialize_value(value, config_type)
                
                # 获取现有配置信息（保留描述）
                existing_config = None
                if key in self._cache:
                    existing_config = self._cache[key]
                
                # 构建配置数据
                config_data = {
                    'value': serialized_value,
                    'config_type': config_type,
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
        "config_type": "string"
    },
    "telegram.api_hash": {
        "value": "",
        "description": "Telegram API Hash (从 https://my.telegram.org 获取)",
        "config_type": "string"
    },
    "telegram.phone": {
        "value": "",
        "description": "Telegram手机号码 (格式: +8613800138000)",
        "config_type": "string"
    },
    
    # 频道监听配置
    "channels.source_channels": {
        "value": [],
        "description": "监听的源频道列表 (频道ID或用户名)",
        "config_type": "list"
    },
    "channels.review_group_id": {
        "value": "",
        "description": "审核群ID或链接",
        "config_type": "string"
    },
    "channels.review_group_id_cached": {
        "value": "",
        "description": "缓存的审核群ID（由系统自动解析链接后设置）",
        "config_type": "string"
    },
    "channels.target_channel_id": {
        "value": "",
        "description": "目标频道ID",
        "config_type": "string"
    },
    "channels.history_message_limit": {
        "value": 50,
        "description": "首次采集频道时获取的历史消息条数 (包括进程中断后重启)",
        "config_type": "integer"
    },
    
    # 账号采集配置
    "accounts.collect_accounts": {
        "value": True,
        "description": "是否启用账号采集功能",
        "config_type": "boolean"
    },
    "accounts.collected_accounts": {
        "value": [],
        "description": "已采集的账号列表",
        "config_type": "list"
    },
    "accounts.account_blacklist": {
        "value": [],
        "description": "账号黑名单 (不采集这些账号)",
        "config_type": "list"
    },
    "accounts.account_whitelist": {
        "value": [],
        "description": "账号白名单 (只采集这些账号)",
        "config_type": "list"
    },
    "accounts.auto_collect": {
        "value": True,
        "description": "是否自动采集新账号",
        "config_type": "boolean"
    },
    
    # 广告过滤配置 - 文中关键词
    "filter.ad_keywords_text": {
        "value": ["广告", "推广", "代理", "加微信", "联系方式", "优惠", "折扣", "限时", "抢购", "秒杀", "代理", "代购", "批发", "零售", "加盟", "招商", "合作", "投资", "理财", "股票", "基金", "保险", "贷款", "信用卡", "网贷", "高利贷", "赌博", "博彩", "彩票", "六合彩", "时时彩", "快三", "快彩", "时时乐", "11选5", "排列3", "排列5", "福彩3D", "体彩", "足彩", "竞彩", "单场", "任选", "胆拖", "复式", "倍投", "跟单", "计划", "稳赚", "包赚", "必中", "必赢", "稳赢", "包赢", "包中", "包赚", "稳赚", "必赚", "必赢", "稳赢", "包赢", "包中", "包赚", "稳赚", "必赚"],
        "description": "文中出现过滤消息的广告关键词 (消息内容包含这些关键词时过滤)",
        "config_type": "list"
    },
    
    # 广告过滤配置 - 行中关键词
    "filter.ad_keywords_line": {
        "value": ["联系QQ", "联系微信", "联系QQ群", "联系微信群", "加QQ", "加微信", "QQ群", "微信群", "QQ:", "微信:", "QQ：", "微信：", "QQ号:", "微信号:", "QQ号：", "微信号：", "QQ群:", "微信群:", "QQ群：", "微信群：", "QQ号码:", "微信账号:", "QQ号码：", "微信账号：", "QQ联系:", "微信联系:", "QQ联系：", "微信联系：", "QQ客服:", "微信客服:", "QQ客服：", "微信客服：", "QQ咨询:", "微信咨询:", "QQ咨询：", "微信咨询：", "QQ交流:", "微信交流:", "QQ交流：", "微信交流：", "QQ讨论:", "微信讨论:", "QQ讨论：", "微信讨论：", "QQ分享:", "微信分享:", "QQ分享：", "微信分享：", "QQ学习:", "微信学习:", "QQ学习：", "微信学习：", "QQ培训:", "微信培训:", "QQ培训：", "微信培训：", "QQ课程:", "微信课程:", "QQ课程：", "微信课程：", "QQ教程:", "微信教程:", "QQ教程：", "微信教程：", "QQ资料:", "微信资料:", "QQ资料：", "微信资料：", "QQ资源:", "微信资源:", "QQ资源：", "微信资源：", "QQ工具:", "微信工具:", "QQ工具：", "微信工具：", "QQ软件:", "微信软件:", "QQ软件：", "微信软件：", "QQ应用:", "微信应用:", "QQ应用：", "微信应用：", "QQ平台:", "微信平台:", "QQ平台：", "微信平台：", "QQ网站:", "微信网站:", "QQ网站：", "微信网站：", "QQ链接:", "微信链接:", "QQ链接：", "微信链接：", "QQ地址:", "微信地址:", "QQ地址：", "微信地址：", "QQ网址:", "微信网址:", "QQ网址：", "微信网址：", "QQ域名:", "微信域名:", "QQ域名：", "微信域名：", "QQ空间:", "微信空间:", "QQ空间：", "微信空间：", "QQ博客:", "微信博客:", "QQ博客：", "微信博客：", "QQ微博:", "微信微博:", "QQ微博：", "微信微博：", "QQ论坛:", "微信论坛:", "QQ论坛：", "微信论坛：", "QQ贴吧:", "微信贴吧:", "QQ贴吧：", "微信贴吧：", "QQ知道:", "微信知道:", "QQ知道：", "微信知道：", "QQ百科:", "微信百科:", "QQ百科：", "微信百科：", "QQ文库:", "微信文库:", "QQ文库：", "微信文库：", "QQ视频:", "微信视频:", "QQ视频：", "微信视频：", "QQ音乐:", "微信音乐:", "QQ音乐：", "微信音乐：", "QQ游戏:", "微信游戏:", "QQ游戏：", "微信游戏：", "QQ直播:", "微信直播:", "QQ直播：", "微信直播：", "QQ短视频:", "微信短视频:", "QQ短视频：", "微信短视频：", "QQ小视频:", "微信小视频:", "QQ小视频：", "微信小视频：", "QQ朋友圈:", "微信朋友圈:", "QQ朋友圈：", "微信朋友圈：", "QQ动态:", "微信动态:", "QQ动态：", "微信动态：", "QQ说说:", "微信说说:", "QQ说说：", "微信说说：", "QQ日志:", "微信日志:", "QQ日志：", "微信日志：", "QQ相册:", "微信相册:", "QQ相册：", "微信相册：", "QQ收藏:", "微信收藏:", "QQ收藏：", "微信收藏：", "QQ钱包:", "微信钱包:", "QQ钱包：", "微信钱包：", "QQ支付:", "微信支付:", "QQ支付：", "微信支付：", "QQ转账:", "微信转账:", "QQ转账：", "微信转账：", "QQ红包:", "微信红包:", "QQ红包：", "微信红包：", "QQ理财:", "微信理财:", "QQ理财：", "微信理财：", "QQ基金:", "微信基金:", "QQ基金：", "微信基金：", "QQ股票:", "微信股票:", "QQ股票：", "微信股票：", "QQ保险:", "微信保险:", "QQ保险：", "微信保险：", "QQ贷款:", "微信贷款:", "QQ贷款：", "微信贷款：", "QQ信用卡:", "微信信用卡:", "QQ信用卡：", "微信信用卡：", "QQ网贷:", "微信网贷:", "QQ网贷：", "微信网贷：", "QQ高利贷:", "微信高利贷:", "QQ高利贷：", "微信高利贷：", "QQ赌博:", "微信赌博:", "QQ赌博：", "微信赌博：", "QQ博彩:", "微信博彩:", "QQ博彩：", "微信博彩：", "QQ彩票:", "微信彩票:", "QQ彩票：", "微信彩票：", "QQ六合彩:", "微信六合彩:", "QQ六合彩：", "微信六合彩：", "QQ时时彩:", "微信时时彩:", "QQ时时彩：", "微信时时彩：", "QQ快三:", "微信快三:", "QQ快三：", "微信快三：", "QQ快彩:", "微信快彩:", "QQ快彩：", "微信快彩：", "QQ时时乐:", "微信时时乐:", "QQ时时乐：", "微信时时乐：", "QQ11选5:", "微信11选5:", "QQ11选5：", "微信11选5：", "QQ排列3:", "微信排列3:", "QQ排列3：", "微信排列3：", "QQ排列5:", "微信排列5:", "QQ排列5：", "微信排列5：", "QQ福彩3D:", "微信福彩3D:", "QQ福彩3D：", "微信福彩3D：", "QQ体彩:", "微信体彩:", "QQ体彩：", "微信体彩：", "QQ足彩:", "微信足彩:", "QQ足彩：", "微信足彩：", "QQ竞彩:", "微信竞彩:", "QQ竞彩：", "微信竞彩：", "QQ单场:", "微信单场:", "QQ单场：", "微信单场：", "QQ任选:", "微信任选:", "QQ任选：", "微信任选：", "QQ胆拖:", "微信胆拖:", "QQ胆拖：", "微信胆拖：", "QQ复式:", "微信复式:", "QQ复式：", "微信复式：", "QQ倍投:", "微信倍投:", "QQ倍投：", "微信倍投：", "QQ跟单:", "微信跟单:", "QQ跟单：", "微信跟单：", "QQ计划:", "微信计划:", "QQ计划：", "微信计划：", "QQ稳赚:", "微信稳赚:", "QQ稳赚：", "微信稳赚：", "QQ包赚:", "微信包赚:", "QQ包赚：", "微信包赚：", "QQ必中:", "微信必中:", "QQ必中：", "微信必中：", "QQ必赢:", "微信必赢:", "QQ必赢：", "微信必赢：", "QQ稳赢:", "微信稳赢:", "QQ稳赢：", "微信稳赢：", "QQ包赢:", "微信包赢:", "QQ包赢：", "微信包赢：", "QQ包中:", "微信包中:", "QQ包中：", "微信包中：", "QQ包赚:", "微信包赚:", "QQ包赚：", "微信包赚：", "QQ稳赚:", "微信稳赚:", "QQ稳赚：", "微信稳赚：", "QQ必赚:", "微信必赚:", "QQ必赚：", "微信必赚：", "QQ必赢:", "微信必赢:", "QQ必赢：", "微信必赢：", "QQ稳赢:", "微信稳赢:", "QQ稳赢：", "微信稳赢：", "QQ包赢:", "微信包赢:", "QQ包赢：", "微信包赢：", "QQ包中:", "微信包中:", "QQ包中：", "微信包中：", "QQ包赚:", "微信包赚:", "QQ包赚：", "微信包赚：", "QQ稳赚:", "微信稳赚:", "QQ稳赚：", "微信稳赚：", "QQ必赚:", "微信必赚:", "QQ必赚：", "微信必赚："],
        "description": "行中出现过滤本行的广告关键词 (消息行包含这些关键词时过滤整行)",
        "config_type": "list"
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
    "review.auto_filter_ads": {
        "value": False,
        "description": "是否自动过滤广告消息",
        "config_type": "boolean"
    },
    "review.enable_keyword_filter": {
        "value": True,
        "description": "是否启用关键词过滤",
        "config_type": "boolean"
    },
    "review.enable_line_filter": {
        "value": True,
        "description": "是否启用行过滤",
        "config_type": "boolean"
    },
    
    # 频道替换配置
    "filter.channel_replacements": {
        "value": {
            "@原频道": "@你的频道",
            "原频道链接": "你的频道链接"
        },
        "description": "频道信息替换规则",
        "config_type": "json"
    },
    
    # 频道落款配置
    "channels.signature": {
        "value": "",
        "description": "频道落款内容（支持多行，用\\n分隔）",
        "config_type": "string"
    },
    
    # 系统配置
    "system.secret_key": {
        "value": "your-secret-key-change-this-in-production",
        "description": "系统密钥",
        "config_type": "string"
    },
    "system.database_url": {
        "value": "postgresql://postgres:telegram123@postgres:5432/telegram_system",
        "description": "数据库连接URL",
        "config_type": "string"
    },
    "system.redis_url": {
        "value": "redis://localhost:6379",
        "description": "Redis连接URL",
        "config_type": "string"
    }
}

async def init_default_configs():
    """初始化默认配置"""
    logger.info("正在初始化默认配置...")
    
    initialized_count = 0
    for key, config_info in DEFAULT_CONFIGS.items():
        existing_value = await config_manager.get_config(key)
        # 只有当值为None或空字符串时才初始化（对于cached字段，保留已有的值）
        if existing_value is None or (existing_value == "" and not key.endswith("_cached")):
            success = await config_manager.set_config(
                key=key,
                value=config_info["value"],
                description=config_info["description"],
                config_type=config_info["config_type"]
            )
            if success:
                logger.info(f"已初始化配置: {key}")
                initialized_count += 1
            else:
                logger.error(f"初始化配置失败: {key}")
    
    logger.info(f"默认配置初始化完成，共初始化 {initialized_count} 个配置项")