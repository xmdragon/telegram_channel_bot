"""
AI配置管理API
提供Web界面管理AI功能开关和模式选择
"""
import logging
from typing import Dict, Any, List
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from app.core.ai_config import get_ai_config
from app.services.lightweight_similarity import get_lightweight_filter
# 临时移除权限检查，AI配置管理暂不需要特殊权限
# from app.core.auth import check_permission

logger = logging.getLogger(__name__)

from app.core.routes import ROUTES

router = APIRouter(tags=["AI配置"])

class AIModuleConfig(BaseModel):
    """AI模块配置"""
    enabled: bool
    mode: str  # auto, lightweight, deep, rule_based, disabled
    description: str

class AIConfigUpdate(BaseModel):
    """AI配置更新请求"""
    module_name: str
    enabled: bool
    mode: str

class AIGlobalConfig(BaseModel):
    """全局AI配置"""
    ai_mode: str  # auto, lightweight, deep, disabled

@router.get(ROUTES.ai.status)
async def get_ai_status():
    """获取AI功能状态"""
    try:
        ai_config = get_ai_config()
        model_cache = get_model_cache_manager()
        lightweight_filter = get_lightweight_filter()
        
        # 获取模块状态
        modules_status = {}
        for module_name, config in ai_config.ai_modules.items():
            actual_mode = ai_config.get_module_mode(module_name)
            modules_status[module_name] = {
                'description': config['description'],
                'enabled': config['enabled'],
                'configured_mode': config['mode'],
                'actual_mode': actual_mode,
                'fallback_to_lightweight': config.get('fallback_to_lightweight', False),
                'is_working': actual_mode != 'disabled'
            }
        
        # 获取依赖状态
        dependencies = {
            'sentence_transformers': False,  # 已移除
            'scikit_learn': True,  # 轻量级模式依赖
            'jieba': True  # 中文分词依赖
        }
        
        # 获取缓存信息
        cache_info = model_cache.get_cache_info()
        
        return {
            'success': True,
            'data': {
                'ai_enabled': ai_config.is_ai_enabled(),
                'startup_mode': ai_config._startup_mode,
                'modules': modules_status,
                'dependencies': dependencies,
                'cache_info': cache_info,
                'lightweight_available': True,  # 轻量级模式总是可用
                'recommendations': _get_recommendations(ai_config, dependencies)
            }
        }
        
    except Exception as e:
        logger.error(f"获取AI状态失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取AI状态失败: {str(e)}")

@router.post(ROUTES.ai.config)
async def update_global_config(config: AIGlobalConfig):
    """更新全局AI配置"""
    try:
        ai_config = get_ai_config()
        
        # 验证模式
        valid_modes = ['auto', 'lightweight', 'deep', 'disabled']
        if config.ai_mode not in valid_modes:
            raise HTTPException(status_code=400, detail=f"无效的AI模式: {config.ai_mode}")
        
        # 更新所有模块配置
        for module_name in ai_config.ai_modules:
            if config.ai_mode == 'disabled':
                ai_config.ai_modules[module_name]['enabled'] = False
            else:
                ai_config.ai_modules[module_name]['enabled'] = True
                ai_config.ai_modules[module_name]['mode'] = config.ai_mode
        
        # 清除缓存
        ai_config._cache.clear()
        
        logger.info(f"全局AI配置已更新为: {config.ai_mode}")
        
        return {
            'success': True,
            'message': f'全局AI配置已更新为: {config.ai_mode}',
            'data': {
                'ai_mode': config.ai_mode,
                'affected_modules': list(ai_config.ai_modules.keys())
            }
        }
        
    except Exception as e:
        logger.error(f"更新全局AI配置失败: {e}")
        raise HTTPException(status_code=500, detail=f"更新全局AI配置失败: {str(e)}")

@router.post(ROUTES.ai.module_config)
async def update_module_config(config: AIConfigUpdate):
    """更新单个模块配置"""
    try:
        ai_config = get_ai_config()
        
        # 验证模块名
        if config.module_name not in ai_config.ai_modules:
            raise HTTPException(status_code=400, detail=f"未知的AI模块: {config.module_name}")
        
        # 验证模式
        valid_modes = ['auto', 'lightweight', 'deep', 'rule_based', 'disabled']
        if config.mode not in valid_modes:
            raise HTTPException(status_code=400, detail=f"无效的模式: {config.mode}")
        
        # 更新配置
        ai_config.ai_modules[config.module_name]['enabled'] = config.enabled
        ai_config.ai_modules[config.module_name]['mode'] = config.mode
        
        # 清除该模块的缓存
        cache_key = f"mode_{config.module_name}"
        if cache_key in ai_config._cache:
            del ai_config._cache[cache_key]
        
        # 获取实际运行模式
        actual_mode = ai_config.get_module_mode(config.module_name)
        
        logger.info(f"模块 {config.module_name} 配置已更新: enabled={config.enabled}, mode={config.mode}, actual={actual_mode}")
        
        return {
            'success': True,
            'message': f'模块 {config.module_name} 配置已更新',
            'data': {
                'module_name': config.module_name,
                'enabled': config.enabled,
                'configured_mode': config.mode,
                'actual_mode': actual_mode
            }
        }
        
    except Exception as e:
        logger.error(f"更新模块配置失败: {e}")
        raise HTTPException(status_code=500, detail=f"更新模块配置失败: {str(e)}")

@router.post(ROUTES.ai.cache_clear)
async def clear_model_cache():
    """清理模型缓存"""
    try:
        model_cache = get_model_cache_manager()
        
        # 获取清理前的缓存信息
        before_info = model_cache.get_cache_info()
        
        # 清理缓存
        success = model_cache.clear_cache()
        
        if success:
            # 获取清理后的缓存信息
            after_info = model_cache.get_cache_info()
            
            return {
                'success': True,
                'message': '模型缓存已清理',
                'data': {
                    'before': before_info,
                    'after': after_info,
                    'freed_mb': before_info.get('cache_size_mb', 0)
                }
            }
        else:
            raise HTTPException(status_code=500, detail="缓存清理失败")
            
    except Exception as e:
        logger.error(f"清理模型缓存失败: {e}")
        raise HTTPException(status_code=500, detail=f"清理模型缓存失败: {str(e)}")

@router.post(ROUTES.ai.lightweight_train)
async def train_lightweight_model():
    """训练轻量级模型"""
    try:
        lightweight_filter = get_lightweight_filter()
        
        # 这里可以加载训练数据
        # 示例：从训练数据文件加载
        ad_samples = []
        normal_samples = []
        
        # 可以从数据库或文件加载训练样本
        # ad_samples = load_ad_samples()
        # normal_samples = load_normal_samples()
        
        if not ad_samples and not normal_samples:
            return {
                'success': False,
                'message': '缺少训练数据，请先收集足够的广告和正常内容样本'
            }
        
        # 训练模型
        success = lightweight_filter.train_with_samples(ad_samples, normal_samples)
        
        if success:
            return {
                'success': True,
                'message': '轻量级模型训练完成',
                'data': {
                    'ad_samples_count': len(ad_samples),
                    'normal_samples_count': len(normal_samples)
                }
            }
        else:
            return {
                'success': False,
                'message': '轻量级模型训练失败'
            }
            
    except Exception as e:
        logger.error(f"训练轻量级模型失败: {e}")
        raise HTTPException(status_code=500, detail=f"训练轻量级模型失败: {str(e)}")

@router.get(ROUTES.ai.recommendations)
async def get_ai_recommendations():
    """获取AI配置建议"""
    try:
        ai_config = get_ai_config()
        
        dependencies = {
            'sentence_transformers': False,  # 已移除
        }
        
        recommendations = _get_recommendations(ai_config, dependencies)
        
        return {
            'success': True,
            'data': {
                'recommendations': recommendations
            }
        }
        
    except Exception as e:
        logger.error(f"获取AI建议失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取AI建议失败: {str(e)}")

def _get_recommendations(ai_config, dependencies: Dict[str, bool]) -> List[Dict[str, Any]]:
    """生成配置建议"""
    recommendations = []
    
    # 检查sentence_transformers可用性
    if not dependencies.get('sentence_transformers', False):
        recommendations.append({
            'type': 'warning',
            'title': '深度学习模式已废弃',
            'message': '系统已优化为轻量级模式，无需重量级依赖',
            'action': {
                'type': 'install',
                'command': 'pip install sentence-transformers',
                'description': '安装深度学习依赖'
            }
        })
    
    # 检查是否有模块使用了不可用的深度模式
    for module_name, config in ai_config.ai_modules.items():
        if config['mode'] == 'deep' and not dependencies.get('sentence_transformers', False):
            recommendations.append({
                'type': 'error',
                'title': f'模块{module_name}配置问题',
                'message': f'模块设置为deep模式但系统已改为轻量级',
                'action': {
                    'type': 'config',
                    'module': module_name,
                    'suggested_mode': 'lightweight',
                    'description': '切换到轻量级模式'
                }
            })
    
    # 性能建议
    if dependencies.get('sentence_transformers', False):
        recommendations.append({
            'type': 'info',
            'title': '性能优化建议',
            'message': '系统已优化，推荐使用auto或lightweight模式',
            'action': {
                'type': 'config',
                'suggested_mode': 'auto',
                'description': '使用自动模式'
            }
        })
    else:
        recommendations.append({
            'type': 'info',
            'title': '轻量级模式可用',
            'message': '轻量级模式提供良好的性能和准确率，无需额外依赖',
            'action': {
                'type': 'config',
                'suggested_mode': 'lightweight',
                'description': '使用轻量级模式'
            }
        })
    
    return recommendations