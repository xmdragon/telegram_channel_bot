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
    PERMISSIONS_CONFIG_FILE = CONFIG_DIR / "permissions.json"
    
    # 广告检测相关
    AD_TRAINING_DIR = TRAINING_DIR / "ad"
    AD_JSON_DIR = AD_TRAINING_DIR / "json"
    AD_TRAINING_FILE = AD_JSON_DIR / "ad_training_data.json"
    AD_MEDIA_DIR = AD_TRAINING_DIR
    AD_MEDIA_METADATA_FILE = AD_JSON_DIR / "media_metadata.json"
    AD_IMAGE_HASHES_FILE = AD_JSON_DIR / "ad_image_hashes.json"
    NORMAL_TRAINING_FILE = AD_JSON_DIR / "normal_training_data.json"
    
    # 尾部过滤相关
    TAIL_TRAINING_DIR = TRAINING_DIR / "tail"
    TAIL_FILTER_SAMPLES_FILE = TAIL_TRAINING_DIR / "tail_filter_samples.json"
    SEPARATOR_PATTERNS_FILE = TAIL_TRAINING_DIR / "separator_patterns.json"
    
    # 推广链接过滤相关
    PROMO_TRAINING_DIR = TRAINING_DIR / "promo"
    PROMO_SAMPLES_FILE = PROMO_TRAINING_DIR / "promo_samples.json"
    
    # 其他训练数据
    OTHER_TRAINING_DIR = TRAINING_DIR / "other"
    AI_FILTER_PATTERNS_FILE = OTHER_TRAINING_DIR / "ai_filter_patterns.json"
    LEARNED_PATTERNS_FILE = OTHER_TRAINING_DIR / "learned_patterns.json"
    OCR_SAMPLES_FILE = OTHER_TRAINING_DIR / "ocr_samples.json"
    
    # 模型和缓存目录
    MODELS_DIR = DATA_DIR / "models"
    # SENTENCE_TRANSFORMERS_CACHE_DIR = MODELS_DIR / "sentence_transformers"  # 已移除
    LIGHTWEIGHT_SIMILARITY_CACHE_FILE = MODELS_DIR / "lightweight_similarity_cache.pkl"
    
    # 日志文件
    APP_LOG_FILE = LOGS_DIR / "app.log"
    ERROR_LOG_FILE = LOGS_DIR / "error.log"
    SUPERVISOR_STATUS_FILE = LOGS_DIR / "supervisor_status.json"
    
    # AI配置文件
    AI_CONFIG_FILE = CONFIG_DIR / "ai_config.json"
    
    # OCR导出文件目录
    OCR_EXPORT_DIR = DATA_DIR / "exports"
    
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
            
            # 创建广告检测相关目录
            cls.AD_TRAINING_DIR.mkdir(exist_ok=True)
            cls.AD_JSON_DIR.mkdir(exist_ok=True)
            (cls.AD_TRAINING_DIR / "images").mkdir(exist_ok=True)
            (cls.AD_TRAINING_DIR / "videos").mkdir(exist_ok=True)
            
            # 按月份创建图片目录（当前月份）
            from datetime import datetime
            current_month = datetime.now().strftime("%Y-%m")
            month_dir = cls.AD_TRAINING_DIR / "images" / current_month
            month_dir.mkdir(exist_ok=True)
            
            # 创建尾部过滤相关目录
            cls.TAIL_TRAINING_DIR.mkdir(exist_ok=True)
            
            # 创建推广链接过滤相关目录
            cls.PROMO_TRAINING_DIR.mkdir(exist_ok=True)
            
            # 创建其他训练数据目录
            cls.OTHER_TRAINING_DIR.mkdir(exist_ok=True)
            
            # 创建模型缓存目录
            cls.MODELS_DIR.mkdir(exist_ok=True)
            # cls.SENTENCE_TRANSFORMERS_CACHE_DIR.mkdir(exist_ok=True)  # 已移除
            
            # 创建OCR导出目录
            cls.OCR_EXPORT_DIR.mkdir(exist_ok=True)
            
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