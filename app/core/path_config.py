"""
系统路径统一配置
所有文件路径都在这里集中定义，禁止在其他地方硬编码路径
"""
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class PathConfig:
    """系统路径统一配置类"""
    
    # 基础目录
    DATA_DIR = Path("data")
    CONFIG_DIR = DATA_DIR / "config"
    TRAINING_DIR = DATA_DIR / "training"
    BACKUP_DIR = DATA_DIR / "backups"
    LOGS_DIR = Path("logs")
    TEMP_MEDIA_DIR = Path("temp_media")
    
    # 配置文件（统一管理）
    SYSTEM_CONFIG_FILE = CONFIG_DIR / "system.json"
    ADMINS_CONFIG_FILE = CONFIG_DIR / "admins.json"
    CHANNELS_CONFIG_FILE = CONFIG_DIR / "channels.json"
    # 过滤器配置文件（统一在训练目录根部）
    AD_KEYWORDS_FILE = TRAINING_DIR / "ad_keywords.json"  # 广告关键词配置
    TAIL_FILTER_SAMPLES_FILE = TRAINING_DIR / "tail_filter_samples.json"  # 尾部过滤样本
    SEPARATOR_PATTERNS_FILE = TRAINING_DIR / "separator_patterns.json"  # 分隔符模式
    
    # 其他训练数据
    OTHER_TRAINING_DIR = TRAINING_DIR / "other"
    LEARNED_PATTERNS_FILE = OTHER_TRAINING_DIR / "learned_patterns.json"
    
    # 日志文件
    APP_LOG_FILE = LOGS_DIR / "app.log"
    ERROR_LOG_FILE = LOGS_DIR / "error.log"
    SUPERVISOR_STATUS_FILE = LOGS_DIR / "supervisor_status.json"
    
    
    @classmethod
    def ensure_directories(cls):
        """确保所有必要的目录存在"""
        try:
            # 创建基础目录
            cls.DATA_DIR.mkdir(exist_ok=True)
            cls.CONFIG_DIR.mkdir(exist_ok=True)
            cls.TRAINING_DIR.mkdir(exist_ok=True)
            cls.BACKUP_DIR.mkdir(exist_ok=True)
            cls.LOGS_DIR.mkdir(exist_ok=True)
            cls.TEMP_MEDIA_DIR.mkdir(exist_ok=True)

            # 创建训练数据目录
            cls.OTHER_TRAINING_DIR.mkdir(exist_ok=True)   # 用于其他训练数据

            logger.info("所有系统目录结构初始化完成")
            return True

        except Exception as e:
            logger.error(f"创建目录失败: {e}")
            return False
    
    @classmethod
    def validate_paths(cls):
        """验证所有路径的有效性"""
        invalid_paths = []
        
        # 检查所有文件路径的父目录
        for attr_name in dir(cls):
            if attr_name.endswith('_FILE'):
                path = getattr(cls, attr_name)
                if isinstance(path, Path) and not path.parent.exists():
                    logger.warning(f"目录不存在: {path.parent}")
                    invalid_paths.append(str(path))
        
        if invalid_paths:
            logger.warning(f"发现 {len(invalid_paths)} 个无效路径")
            return False
        
        logger.info("所有路径验证通过")
        return True
    
    @classmethod
    def get_all_paths(cls) -> dict:
        """获取所有配置的路径"""
        paths = {}
        for attr_name in dir(cls):
            if attr_name.isupper() and not attr_name.startswith('_'):
                attr_value = getattr(cls, attr_name)
                if isinstance(attr_value, Path):
                    paths[attr_name] = str(attr_value)
        return paths
    
    @classmethod
    def initialize(cls):
        """初始化配置（应在应用启动时调用）"""
        cls.ensure_directories()
        cls.validate_paths()
        
        # 打印配置信息
        logger.info("系统路径配置:")
        for name, path in cls.get_all_paths().items():
            logger.info(f"  {name}: {path}")


# 便捷导入常用路径（避免在其他地方硬编码）
path_config = PathConfig