"""
AI功能配置管理
提供AI功能的开关和配置选项
"""
import os
import logging
from typing import Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

class AIConfig:
    """AI功能配置管理器"""
    
    def __init__(self):
        # 从环境变量或配置文件读取AI功能开关
        self._ai_enabled = self._get_ai_enabled()
        self._startup_mode = self._get_startup_mode()
        self._sentence_transformers_available = None
        self._cache = {}
        
        # AI模块列表
        self.ai_modules = {
            'ai_filter': {
                'enabled': self._ai_enabled,
                'mode': 'auto',  # auto, lightweight, deep, disabled
                'fallback_to_lightweight': True,
                'description': 'AI智能过滤器',
                'startup_required': False  # 启动时不必需
            },
            'ad_detector': {
                'enabled': self._ai_enabled,
                'mode': 'auto',
                'fallback_to_lightweight': True,
                'description': '广告检测器',
                'startup_required': False
            },
            'ai_ad_detector': {
                'enabled': self._ai_enabled,
                'mode': 'auto',
                'fallback_to_lightweight': True,
                'description': 'AI广告检测器',
                'startup_required': False
            },
            'semantic_tail_filter': {
                'enabled': self._ai_enabled,
                'mode': 'auto',
                'fallback_to_lightweight': True,
                'description': '语义尾部过滤器',
                'startup_required': False
            },
            'intelligent_tail_filter': {
                'enabled': self._ai_enabled,
                'mode': 'auto',
                'fallback_to_lightweight': True,
                'description': '智能尾部过滤器',
                'startup_required': False
            },
            'semantic_analyzer': {
                'enabled': True,
                'mode': 'rule_based',  # rule_based, ai_enhanced
                'fallback_to_lightweight': False,
                'description': '语义分析器',
                'startup_required': False
            }
        }
        
        # 从环境变量读取模式配置
        self._load_env_config()
        
        logger.info(f"AI功能配置: {'启用' if self._ai_enabled else '禁用'}, 启动模式: {self._startup_mode}")
    
    def _load_env_config(self):
        """从环境变量加载配置"""
        try:
            # AI_MODE: auto, lightweight, deep, disabled
            ai_mode = os.getenv('AI_MODE', 'auto').lower()
            
            if ai_mode in ['auto', 'lightweight', 'deep', 'disabled']:
                for module in self.ai_modules:
                    if ai_mode == 'disabled':
                        self.ai_modules[module]['enabled'] = False
                    else:
                        self.ai_modules[module]['mode'] = ai_mode
            
            # 单独模块控制
            for module in self.ai_modules:
                env_key = f'AI_{module.upper()}_ENABLED'
                if os.getenv(env_key):
                    self.ai_modules[module]['enabled'] = os.getenv(env_key).lower() == 'true'
                
                env_mode_key = f'AI_{module.upper()}_MODE'
                if os.getenv(env_mode_key):
                    self.ai_modules[module]['mode'] = os.getenv(env_mode_key).lower()
            
        except Exception as e:
            logger.error(f"加载AI配置失败：{e}")
    
    def is_sentence_transformers_available(self) -> bool:
        """检查sentence_transformers是否可用"""
        if self._sentence_transformers_available is None:
            try:
                import sentence_transformers
                self._sentence_transformers_available = True
                logger.info("✅ sentence_transformers 可用")
            except ImportError:
                self._sentence_transformers_available = False
                logger.info("⚠️ sentence_transformers 不可用")
        
        return self._sentence_transformers_available
    
    def get_module_mode(self, module_name: str) -> str:
        """
        获取模块的实际运行模式
        
        Args:
            module_name: 模块名称
            
        Returns:
            实际模式: lightweight, deep, rule_based, disabled
        """
        cache_key = f"mode_{module_name}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        if module_name not in self.ai_modules:
            return 'disabled'
        
        config = self.ai_modules[module_name]
        
        # 如果模块被禁用
        if not config['enabled']:
            self._cache[cache_key] = 'disabled'
            return 'disabled'
        
        mode = config['mode']
        
        # auto模式：自动选择
        if mode == 'auto':
            if self.is_sentence_transformers_available():
                mode = 'deep'
            elif config['fallback_to_lightweight']:
                mode = 'lightweight'
            else:
                mode = 'rule_based'
        
        # deep模式但sentence_transformers不可用
        elif mode == 'deep' and not self.is_sentence_transformers_available():
            if config['fallback_to_lightweight']:
                mode = 'lightweight'
                logger.warning(f"模块 {module_name} 从deep模式降级到lightweight模式")
            else:
                mode = 'disabled'
                logger.warning(f"模块 {module_name} 因缺少依赖而禁用")
        
        self._cache[cache_key] = mode
        logger.debug(f"模块 {module_name} 运行模式：{mode}")
        return mode
    
    def use_deep_learning(self, module_name: str) -> bool:
        """检查模块是否使用深度学习"""
        return self.get_module_mode(module_name) == 'deep'
    
    def use_lightweight(self, module_name: str) -> bool:
        """检查模块是否使用轻量级模式"""
        return self.get_module_mode(module_name) == 'lightweight'
    
    def _get_ai_enabled(self) -> bool:
        """获取AI功能启用状态"""
        # 优先级：环境变量 > 配置文件 > 默认值
        
        # 1. 环境变量
        env_value = os.environ.get('AI_ENABLED', '').lower()
        if env_value in ('true', '1', 'yes', 'on'):
            return True
        elif env_value in ('false', '0', 'no', 'off'):
            return False
        
        # 2. 配置文件
        try:
            config_file = Path("data/config/ai_config.json")
            if config_file.exists():
                import json
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                return config.get('ai_enabled', True)
        except Exception as e:
            logger.warning(f"读取AI配置文件失败: {e}")
        
        # 3. 默认值：生产环境启用，开发环境可选择
        is_dev = os.environ.get('ENVIRONMENT', 'production').lower() == 'development'
        return not is_dev  # 生产环境默认启用，开发环境默认禁用
    
    def _get_startup_mode(self) -> str:
        """获取启动模式"""
        mode = os.environ.get('AI_STARTUP_MODE', 'lazy').lower()
        if mode in ('eager', 'lazy', 'disabled'):
            return mode
        return 'lazy'  # 默认懒加载
    
    def is_ai_enabled(self) -> bool:
        """检查AI功能是否启用"""
        return self._ai_enabled
    
    def is_module_enabled(self, module_name: str) -> bool:
        """检查特定AI模块是否启用"""
        if not self._ai_enabled:
            return False
        
        module = self.ai_modules.get(module_name, {})
        return module.get('enabled', False)
    
    def should_load_at_startup(self, module_name: str) -> bool:
        """检查模块是否应在启动时加载"""
        if not self.is_module_enabled(module_name):
            return False
        
        if self._startup_mode == 'disabled':
            return False
        elif self._startup_mode == 'eager':
            return True
        else:  # lazy
            module = self.ai_modules.get(module_name, {})
            return module.get('startup_required', False)
    
    def get_config(self) -> Dict[str, Any]:
        """获取完整配置"""
        return {
            'ai_enabled': self._ai_enabled,
            'startup_mode': self._startup_mode,
            'modules': self.ai_modules
        }
    
    def set_ai_enabled(self, enabled: bool, save_to_file: bool = True) -> bool:
        """设置AI功能启用状态"""
        try:
            self._ai_enabled = enabled
            
            # 更新所有模块状态
            for module in self.ai_modules.values():
                module['enabled'] = enabled
            
            # 保存到配置文件
            if save_to_file:
                self._save_config()
            
            logger.info(f"AI功能已{'启用' if enabled else '禁用'}")
            return True
            
        except Exception as e:
            logger.error(f"设置AI功能状态失败: {e}")
            return False
    
    def _save_config(self):
        """保存配置到文件"""
        try:
            config_file = Path("data/config/ai_config.json")
            config_file.parent.mkdir(parents=True, exist_ok=True)
            
            config = {
                'ai_enabled': self._ai_enabled,
                'startup_mode': self._startup_mode,
                'updated_at': __import__('datetime').datetime.now().isoformat()
            }
            
            import json
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            logger.error(f"保存AI配置失败: {e}")

# 全局实例
_ai_config = None

def get_ai_config() -> AIConfig:
    """获取AI配置实例"""
    global _ai_config
    if _ai_config is None:
        _ai_config = AIConfig()
    return _ai_config

def is_ai_enabled() -> bool:
    """便利函数：检查AI功能是否启用"""
    return get_ai_config().is_ai_enabled()

def is_module_enabled(module_name: str) -> bool:
    """便利函数：检查特定AI模块是否启用"""
    return get_ai_config().is_module_enabled(module_name)