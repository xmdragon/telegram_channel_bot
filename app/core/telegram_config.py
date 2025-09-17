"""
Telegram配置常量统一定义
所有Telegram相关配置键都在这里集中定义，禁止在其他地方硬编码
"""

class TelegramConfig:
    """Telegram配置常量类"""

    # Telegram API配置键
    API_ID = "telegram.api_id"
    API_HASH = "telegram.api_hash"

    # Session配置键
    LISTENER_SESSION = "telegram.listener_session"
    SENDER_SESSION = "telegram.sender_session"

    # Bot配置键（如果需要）
    BOT_TOKEN = "telegram.bot_token"
    BOT_SESSION = "telegram.bot_session"

    # 连接配置键
    CONNECTION_RETRIES = "telegram.connection_retries"
    RETRY_DELAY = "telegram.retry_delay"
    TIMEOUT = "telegram.timeout"

    @classmethod
    def get_all_keys(cls) -> list:
        """获取所有配置键"""
        keys = []
        for attr_name in dir(cls):
            if not attr_name.startswith('_') and not callable(getattr(cls, attr_name)):
                attr_value = getattr(cls, attr_name)
                if isinstance(attr_value, str) and '.' in attr_value:
                    keys.append(attr_value)
        return keys

    @classmethod
    def validate_keys(cls, config_dict: dict) -> dict:
        """验证配置键的完整性"""
        missing_keys = []
        present_keys = []

        for key in cls.get_all_keys():
            if key in config_dict:
                present_keys.append(key)
            else:
                missing_keys.append(key)

        return {
            'missing': missing_keys,
            'present': present_keys,
            'total_keys': len(cls.get_all_keys())
        }

# 便捷导入
telegram_config = TelegramConfig