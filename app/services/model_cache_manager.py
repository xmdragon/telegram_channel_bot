"""
SentenceTransformer模型缓存管理器
解决重复下载和初始化延迟问题
"""
import os
import threading
import logging
from typing import Optional, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)

class ModelCacheManager:
    """SentenceTransformer模型缓存管理器"""
    
    def __init__(self):
        self._models: Dict[str, Any] = {}
        self._lock = threading.RLock()
        
        # 设置本地缓存目录
        from app.core.path_config import PathConfig
        self.cache_dir = PathConfig.SENTENCE_TRANSFORMERS_CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # 设置环境变量，强制使用本地缓存
        os.environ['SENTENCE_TRANSFORMERS_HOME'] = str(self.cache_dir)
        os.environ['HF_HOME'] = str(self.cache_dir.parent / "huggingface")
        
        # 优化网络设置
        os.environ['HF_HUB_DISABLE_PROGRESS_BARS'] = "1"
        os.environ['TOKENIZERS_PARALLELISM'] = "false"
        
        logger.info(f"✅ 模型缓存管理器初始化，缓存目录: {self.cache_dir}")
    
    def _load_config(self) -> Dict:
        """加载AI模型配置"""
        try:
            import json
            config_file = self.cache_dir.parent / "config" / "ai_models.json" 
            if config_file.exists():
                with open(config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"读取AI模型配置失败: {e}")
        
        # 🔧 Linus式降级：配置不可用时使用硬编码最小配置
        return {
            "models": {
                "nano": {
                    "name": "all-MiniLM-L6-v2",
                    "repo": "sentence-transformers/all-MiniLM-L6-v2",
                    "local_path": None,
                    "enabled": True
                }
            },
            "default_model": "nano",
            "fallback_chain": ["nano"]
        }
    
    def _get_model_config(self, model_key: Optional[str] = None) -> Optional[Dict]:
        """获取指定模型的配置"""
        config = self._load_config()
        
        if model_key is None:
            model_key = config.get('default_model', 'nano')
        
        models = config.get('models', {})
        if model_key in models and models[model_key].get('enabled', True):
            return models[model_key]
        
        # 降级到fallback链
        fallback_chain = config.get('fallback_chain', ['nano'])
        for fallback_key in fallback_chain:
            if fallback_key in models and models[fallback_key].get('enabled', True):
                logger.warning(f"模型 {model_key} 不可用，降级到 {fallback_key}")
                return models[fallback_key]
        
        return None
    
    def get_model(self, model_key: Optional[str] = None) -> Optional[Any]:
        """获取模型实例（带缓存）"""
        # 获取模型配置
        model_config = self._get_model_config(model_key)
        if not model_config:
            logger.error(f"无法获取模型配置: {model_key}")
            return None
        
        # 确定模型标识符（用于缓存key）
        model_id = model_config.get('name', model_key or 'unknown')
        
        with self._lock:
            # 检查内存缓存
            if model_id in self._models:
                logger.debug(f"从内存缓存获取模型: {model_id}")
                return self._models[model_id]
            
            # 🔧 Linus式：应用层延迟，确保不同worker错开模型初始化
            import os
            import time
            pid = os.getpid()
            
            # 根据进程ID计算延迟，确保错开模型加载
            pid_delay = (pid % 8) * 0.3  # 0, 0.3, 0.6, 0.9...秒延迟
            if pid_delay > 0:
                logger.info(f"Worker {pid} 应用层延迟 {pid_delay:.1f}秒后加载模型: {model_id}")
                time.sleep(pid_delay)
            else:
                logger.info(f"Worker {pid} 立即开始加载模型: {model_id}")
            
            # 加载模型
            try:
                model = self._load_model_from_config(model_config)
                if model:
                    # 缓存到内存
                    self._models[model_id] = model
                    logger.info(f"✅ Worker {pid} 模型加载完成: {model_id}")
                    return model
                
            except Exception as e:
                logger.error(f"Worker {pid} 模型加载失败: {model_id}, 错误: {e}")
        
        return None
    
    def _load_model_from_config(self, model_config: Dict) -> Optional[Any]:
        """根据配置加载模型"""
        try:
            from sentence_transformers import SentenceTransformer
            
            # 优先使用本地路径
            local_path = model_config.get('local_path')
            if local_path and Path(local_path).exists():
                logger.info(f"从本地路径加载模型: {local_path}")
                return SentenceTransformer(local_path, device='cpu')
            
            # 使用仓库地址
            repo = model_config.get('repo')
            if repo:
                logger.info(f"加载模型: {repo} (使用本地缓存)")
                return SentenceTransformer(
                    repo,
                    cache_folder=str(self.cache_dir),
                    device='cpu'
                )
            
            # 降级到模型名称
            model_name = model_config.get('name')
            if model_name:
                logger.info(f"使用模型名称加载: {model_name}")
                return SentenceTransformer(
                    model_name,
                    cache_folder=str(self.cache_dir), 
                    device='cpu'
                )
            
            logger.error("模型配置中没有可用的加载路径")
            return None
            
        except Exception as e:
            logger.error(f"模型加载异常: {e}")
            return None
    
    def preload_models(self) -> bool:
        """预加载常用模型（可在后台异步执行）"""
        try:
            import threading
            import os
            
            def preload():
                pid = os.getpid()
                logger.info(f"🚀 Worker {pid} 开始预加载模型...")
                model = self.get_model()
                if model:
                    logger.info(f"✅ Worker {pid} 模型预加载完成")
                else:
                    logger.error(f"❌ Worker {pid} 模型预加载失败")
            
            # 🔧 Linus式简化：直接加载，不用额外线程增加复杂度
            # 多进程环境下，每个worker预加载自己的模型副本
            preload()
            return True
            
        except Exception as e:
            import os
            logger.error(f"Worker {os.getpid()} 预加载模型失败: {e}")
            return False
    
    def get_cache_info(self) -> Dict[str, Any]:
        """获取缓存信息"""
        info = {
            "cache_dir": str(self.cache_dir),
            "cached_models": list(self._models.keys()),
            "cache_exists": self.cache_dir.exists()
        }
        
        # 检查磁盘缓存大小
        try:
            if self.cache_dir.exists():
                total_size = sum(f.stat().st_size for f in self.cache_dir.rglob('*') if f.is_file())
                info["cache_size_mb"] = round(total_size / 1024 / 1024, 2)
            else:
                info["cache_size_mb"] = 0
        except Exception as e:
            logger.error(f"计算缓存大小失败: {e}")
            info["cache_size_mb"] = "unknown"
        
        return info
    
    def clear_cache(self) -> bool:
        """清理缓存"""
        try:
            with self._lock:
                # 清理内存缓存
                self._models.clear()
                
                # 清理磁盘缓存（可选）
                import shutil
                if self.cache_dir.exists():
                    shutil.rmtree(self.cache_dir)
                    self.cache_dir.mkdir(parents=True, exist_ok=True)
                
                logger.info("✅ 模型缓存已清理")
                return True
                
        except Exception as e:
            logger.error(f"清理缓存失败: {e}")
            return False

# 全局实例（懒加载）
_model_cache_manager = None

def get_model_cache_manager() -> ModelCacheManager:
    """获取模型缓存管理器（单例）"""
    global _model_cache_manager
    if _model_cache_manager is None:
        _model_cache_manager = ModelCacheManager()
    return _model_cache_manager

def get_cached_model(model_key: Optional[str] = None) -> Optional[Any]:
    """便利函数：获取缓存的模型（使用配置文件中的默认模型）"""
    return get_model_cache_manager().get_model(model_key)