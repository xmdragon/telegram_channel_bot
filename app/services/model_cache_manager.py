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
    
    def get_model(self, model_name: str = 'paraphrase-multilingual-MiniLM-L12-v2') -> Optional[Any]:
        """获取模型实例（带缓存）"""
        with self._lock:
            # 检查内存缓存
            if model_name in self._models:
                logger.debug(f"从内存缓存获取模型: {model_name}")
                return self._models[model_name]
            
            # 加载模型
            try:
                logger.info(f"首次加载模型: {model_name}")
                
                # 检查本地是否已有模型文件
                local_model_path = self.cache_dir / model_name.replace('/', '_')
                if local_model_path.exists():
                    logger.info(f"发现本地模型缓存: {local_model_path}")
                else:
                    logger.warning(f"模型将从网络下载到: {local_model_path}")
                
                from sentence_transformers import SentenceTransformer
                
                model = SentenceTransformer(
                    model_name,
                    cache_folder=str(self.cache_dir),
                    device='cpu'  # 优先使用CPU避免GPU初始化延迟
                )
                
                # 缓存到内存
                self._models[model_name] = model
                logger.info(f"✅ 模型加载完成并缓存: {model_name}")
                
                return model
                
            except Exception as e:
                logger.error(f"模型加载失败: {model_name}, 错误: {e}")
                return None
    
    def preload_models(self) -> bool:
        """预加载常用模型（可在后台异步执行）"""
        try:
            import threading
            
            def preload():
                logger.info("🚀 开始预加载模型...")
                model = self.get_model()
                if model:
                    logger.info("✅ 模型预加载完成")
                else:
                    logger.error("❌ 模型预加载失败")
            
            # 后台线程预加载
            thread = threading.Thread(target=preload, daemon=True)
            thread.start()
            return True
            
        except Exception as e:
            logger.error(f"预加载模型失败: {e}")
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

def get_cached_model(model_name: str = 'paraphrase-multilingual-MiniLM-L12-v2') -> Optional[Any]:
    """便利函数：获取缓存的模型"""
    return get_model_cache_manager().get_model(model_name)