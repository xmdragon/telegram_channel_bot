"""
AI训练数据文件路径集中配置
所有训练相关的JSON文件路径都在这里定义
"""
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class TrainingDataConfig:
    """AI训练数据文件路径配置"""
    
    # 基础路径
    DATA_DIR = Path("data")
    BACKUP_DIR = DATA_DIR / "backups"
    
    # 广告检测相关
    AD_TRAINING_FILE = DATA_DIR / "ad_training_data.json"
    AD_MEDIA_DIR = DATA_DIR / "ad_training_data"
    AD_MEDIA_METADATA_FILE = AD_MEDIA_DIR / "media_metadata.json"
    NORMAL_TRAINING_FILE = DATA_DIR / "normal_training_data.json"
    
    # 尾部过滤相关
    TAIL_FILTER_SAMPLES_FILE = DATA_DIR / "tail_filter_samples.json"
    TAIL_AD_SAMPLES_FILE = DATA_DIR / "tail_ad_samples.json"
    SEPARATOR_PATTERNS_FILE = DATA_DIR / "separator_patterns.json"
    
    # 训练记录相关
    MANUAL_TRAINING_FILE = DATA_DIR / "manual_training_data.json"
    TRAINING_HISTORY_FILE = DATA_DIR / "training_history.json"
    
    # 学习反馈相关
    FEEDBACK_LEARNING_FILE = DATA_DIR / "feedback_learning.json"
    AI_FILTER_PATTERNS_FILE = DATA_DIR / "ai_filter_patterns.json"
    
    @classmethod
    def ensure_directories(cls):
        """确保所有必要的目录存在"""
        try:
            # 创建基础目录
            cls.DATA_DIR.mkdir(exist_ok=True)
            cls.BACKUP_DIR.mkdir(exist_ok=True)
            cls.AD_MEDIA_DIR.mkdir(exist_ok=True)
            
            # 创建媒体子目录
            images_dir = cls.AD_MEDIA_DIR / "images"
            images_dir.mkdir(exist_ok=True)
            
            # 按月份创建图片目录（当前月份）
            from datetime import datetime
            current_month = datetime.now().strftime("%Y-%m")
            month_dir = images_dir / current_month
            month_dir.mkdir(exist_ok=True)
            
            logger.info("训练数据目录初始化完成")
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
        logger.info("训练数据文件配置:")
        for name, path in cls.get_all_paths().items():
            logger.info(f"  {name}: {path}")


# 为了向后兼容，创建一些常用的快捷引用
training_config = TrainingDataConfig

# 导出常用路径（便于直接导入）
AD_TRAINING_FILE = TrainingDataConfig.AD_TRAINING_FILE
TAIL_FILTER_SAMPLES_FILE = TrainingDataConfig.TAIL_FILTER_SAMPLES_FILE
MANUAL_TRAINING_FILE = TrainingDataConfig.MANUAL_TRAINING_FILE
TRAINING_HISTORY_FILE = TrainingDataConfig.TRAINING_HISTORY_FILE