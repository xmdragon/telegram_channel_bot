"""
阈值管理模块 - AI训练阈值的统计、优化和管理
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any
from datetime import datetime
import logging
from pydantic import BaseModel

from .base import handle_api_error
from app.core.route_config import ROUTES
from app.services.auth_service import get_auth_service
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional

security = HTTPBearer(auto_error=False)

# 认证中间件 - 从messages_filter.py复制过来
async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[Dict[str, Any]]:
    """获取当前用户"""
    if not credentials:
        return None
    
    try:
        auth_service = get_auth_service()
        return await auth_service.get_current_user(credentials.credentials)
    except Exception as e:
        logger.error(f"获取当前用户失败: {e}")
        return None

async def require_auth(user: Optional[Dict[str, Any]] = Depends(get_current_user)) -> Dict[str, Any]:
    """要求用户认证"""
    if not user:
        raise HTTPException(status_code=401, detail="未授权访问")
    return user

def check_permission(permission_name: str):
    """检查权限装饰器"""
    def decorator(func):
        return func  # 简化版本，实际项目中应该实现权限检查
    return decorator

logger = logging.getLogger(__name__)

class ManualThresholdUpdateRequest(BaseModel):
    """手动阈值更新请求"""
    filter_name: str
    metric_name: str
    new_value: float

class ThresholdPreviewRequest(BaseModel):
    """阈值预览请求"""
    filter_name: str
    metric_name: str
    test_value: float
    sample_content: str = ""  # 可选的测试内容
    
router = APIRouter(tags=["training-thresholds"])

@router.get(ROUTES.training.thresholds_stats)
@check_permission("filter.view")
async def get_threshold_stats(
    user: Dict[str, Any] = Depends(require_auth)
):
    """
    获取阈值统计信息
    返回各个过滤器的阈值配置、性能指标等
    """
    try:
        from app.core.threshold_manager import threshold_manager
        
        stats = threshold_manager.get_all_stats()
        
        return {
            "success": True,
            "data": stats,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"获取阈值统计失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取统计失败: {str(e)}")


@router.post(ROUTES.training.thresholds_optimize)
@check_permission("filter.admin")
async def optimize_thresholds(
    user: Dict[str, Any] = Depends(require_auth)
):
    """
    优化所有过滤器的阈值
    基于历史反馈数据自动调整阈值以获得最佳性能
    """
    try:
        from app.core.threshold_manager import threshold_manager
        
        logger.info(f"用户 {user.get('user_id')} 开始阈值优化")
        
        # 执行批量优化
        threshold_manager.batch_optimize()
        
        # 获取优化后的统计
        stats = threshold_manager.get_all_stats()
        
        return {
            "success": True,
            "message": "阈值优化完成",
            "data": stats,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"阈值优化失败: {e}")
        raise HTTPException(status_code=500, detail=f"优化失败: {str(e)}")


@router.post(ROUTES.training.thresholds_reset)
@check_permission("filter.admin")
async def reset_threshold(
    filter_name: str,
    metric_name: str,
    user: Dict[str, Any] = Depends(require_auth)
):
    """
    重置指定过滤器的指定指标的阈值到默认值
    """
    try:
        from app.core.threshold_manager import threshold_manager
        
        logger.info(f"用户 {user.get('user_id')} 重置阈值: {filter_name}.{metric_name}")
        
        # 重置阈值
        threshold_manager.reset_threshold(filter_name, metric_name)
        
        # 获取新的阈值
        new_threshold = threshold_manager.get_threshold(filter_name, metric_name)
        
        return {
            "success": True,
            "message": f"阈值已重置",
            "filter_name": filter_name,
            "metric_name": metric_name,
            "new_threshold": new_threshold,
            "timestamp": datetime.now().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"重置阈值失败: {e}")
        raise HTTPException(status_code=500, detail=f"重置失败: {str(e)}")


@router.post(ROUTES.training.thresholds_manual_update)
@check_permission("filter.admin")
async def manual_update_threshold(
    request: ManualThresholdUpdateRequest,
    user: Dict[str, Any] = Depends(require_auth)
):
    """
    手动更新阈值
    允许用户直接设置过滤器的阈值，用于精确调整和实时测试
    """
    try:
        from app.core.threshold_manager import threshold_manager
        
        logger.info(
            f"用户 {user.get('user_id')} 手动更新阈值: "
            f"{request.filter_name}.{request.metric_name} → {request.new_value}"
        )
        
        # 手动设置阈值
        threshold_manager.set_threshold(
            request.filter_name, 
            request.metric_name, 
            request.new_value
        )
        
        # 获取更新后的阈值配置
        updated_config = threshold_manager.get_threshold_config(
            request.filter_name, 
            request.metric_name
        )
        
        return {
            "success": True,
            "message": f"阈值已更新",
            "filter_name": request.filter_name,
            "metric_name": request.metric_name,
            "old_value": updated_config["history"][-2] if len(updated_config.get("history", [])) > 1 else None,
            "new_value": request.new_value,
            "config": updated_config,
            "timestamp": datetime.now().isoformat()
        }
    except ValueError as e:
        # 验证错误，返回400状态码
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"手动更新阈值失败: {e}")
        raise HTTPException(status_code=500, detail=f"更新失败: {str(e)}")


@router.post(ROUTES.training.thresholds_preview)
@check_permission("filter.view")
async def preview_threshold_effect(
    request: ThresholdPreviewRequest,
    user: Dict[str, Any] = Depends(require_auth)
):
    """
    预览阈值调整效果
    临时应用测试阈值，返回预期的过滤效果和性能指标
    """
    try:
        from app.core.threshold_manager import threshold_manager
        
        # 获取当前配置
        current_config = threshold_manager.get_threshold_config(
            request.filter_name, 
            request.metric_name
        )
        current_value = current_config["current"]
        
        # 验证测试阈值范围
        min_val = current_config.get("min", 0.0)
        max_val = current_config.get("max", 1.0)
        
        if request.test_value < min_val or request.test_value > max_val:
            raise HTTPException(
                status_code=400, 
                detail=f"测试阈值 {request.test_value} 超出允许范围 [{min_val}, {max_val}]"
            )
        
        # 计算阈值变化
        threshold_delta = request.test_value - current_value
        delta_percentage = (threshold_delta / current_value * 100) if current_value > 0 else 0
        
        # 基于历史反馈数据模拟性能预期
        feedback_stats = current_config.get("feedback_stats", {"tp": 0, "fp": 0, "tn": 0, "fn": 0})
        total_feedback = sum(feedback_stats.values())
        
        # 简化的预测逻辑：阈值提高通常减少误报但可能增加漏报
        predicted_impact = {
            "threshold_direction": "提高" if threshold_delta > 0 else "降低" if threshold_delta < 0 else "不变",
            "delta_percentage": round(delta_percentage, 1),
            "expected_changes": []
        }
        
        if abs(threshold_delta) > 0.001:
            if threshold_delta > 0:
                # 阈值提高
                predicted_impact["expected_changes"] = [
                    "预期减少误报（更严格的过滤）",
                    "可能增加漏报（部分应该过滤的内容可能通过）",
                    "整体精确率可能提高"
                ]
            else:
                # 阈值降低
                predicted_impact["expected_changes"] = [
                    "预期减少漏报（更宽松的过滤）",
                    "可能增加误报（部分正常内容可能被过滤）",
                    "整体召回率可能提高"
                ]
        else:
            predicted_impact["expected_changes"] = ["阈值几乎无变化，预期影响很小"]
        
        # 根据过滤器类型提供特定建议
        filter_specific_advice = get_filter_specific_advice(
            request.filter_name, 
            request.metric_name, 
            current_value, 
            request.test_value
        )
        
        # 如果提供了测试内容，尝试预测过滤结果
        content_prediction = None
        if request.sample_content.strip():
            content_prediction = await predict_content_filtering(
                request.filter_name,
                request.metric_name,
                request.sample_content,
                request.test_value
            )
        
        return {
            "success": True,
            "current_threshold": current_value,
            "test_threshold": request.test_value,
            "threshold_delta": round(threshold_delta, 3),
            "predicted_impact": predicted_impact,
            "filter_advice": filter_specific_advice,
            "content_prediction": content_prediction,
            "feedback_data_available": total_feedback > 0,
            "feedback_count": total_feedback,
            "timestamp": datetime.now().isoformat()
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"预览阈值效果失败: {e}")
        raise HTTPException(status_code=500, detail=f"预览失败: {str(e)}")


def get_filter_specific_advice(filter_name: str, metric_name: str, current_value: float, test_value: float) -> Dict[str, str]:
    """获取针对特定过滤器的调整建议"""
    
    advice_templates = {
        "promo_vector_filter": {
            "similarity": {
                "increase": "提高相似度阈值将减少误判，但需要确保有足够的训练样本覆盖各种推广模式",
                "decrease": "降低相似度阈值会更敏感地检测推广内容，但可能误判正常内容",
                "optimal_range": "建议范围：0.85-0.95，当前训练样本较少时建议使用较高阈值"
            }
        },
        "tail_filter": {
            "semantic": {
                "increase": "提高语义阈值会减少尾部内容的过滤，适合保留更多信息性内容",
                "decrease": "降低语义阈值会更严格地过滤推广性尾部内容",
                "optimal_range": "建议范围：0.3-0.7，取决于内容类型和用户偏好"
            }
        }
    }
    
    delta = test_value - current_value
    direction = "increase" if delta > 0 else "decrease"
    
    try:
        template = advice_templates.get(filter_name, {}).get(metric_name, {})
        advice = template.get(direction, "阈值调整会影响过滤敏感度")
        optimal_range = template.get("optimal_range", "请参考历史性能数据确定最优范围")
        
        return {
            "specific_advice": advice,
            "optimal_range": optimal_range,
            "recommendation": f"当前值：{current_value:.3f} → 测试值：{test_value:.3f}"
        }
    except:
        return {
            "specific_advice": "阈值调整会影响过滤器的敏感度和准确性",
            "optimal_range": "建议基于实际反馈数据进行调整",
            "recommendation": f"当前值：{current_value:.3f} → 测试值：{test_value:.3f}"
        }


async def predict_content_filtering(filter_name: str, metric_name: str, content: str, test_threshold: float) -> Dict[str, Any]:
    """预测内容在给定阈值下的过滤结果"""
    
    try:
        prediction = {
            "content_length": len(content),
            "predicted_action": "unknown",
            "confidence": 0.0,
            "reasoning": "",
            "filtered_content": content,  # 新增：过滤后的内容
            "removed_content": "",        # 新增：被移除的内容
            "filter_applied": False       # 新增：是否应用了过滤
        }
        
        # 针对promo_vector_filter进行实际过滤测试
        if filter_name == "promo_vector_filter" and metric_name == "similarity":
            try:
                # 尝试调用实际的过滤器进行测试
                filtered_result = await test_promo_vector_filter(content, test_threshold)
                prediction.update(filtered_result)
            except Exception as e:
                # 如果实际过滤器调用失败，使用启发式预测
                prediction.update(await heuristic_promo_prediction(content, test_threshold))
        else:
            # 其他过滤器使用通用启发式预测
            prediction.update(await generic_filter_prediction(filter_name, metric_name, content, test_threshold))
        
        return prediction
        
    except Exception as e:
        logger.error(f"内容过滤预测失败: {e}")
        return {
            "content_length": len(content),
            "predicted_action": "unknown",
            "confidence": 0.0,
            "reasoning": f"预测失败: {str(e)}",
            "filtered_content": content,
            "removed_content": "",
            "filter_applied": False
        }


async def test_promo_vector_filter(content: str, test_threshold: float) -> Dict[str, Any]:
    """实际调用TrailingPromoFilter进行测试"""
    
    try:
        from app.services.filters.trailing_promo_filter import TrailingPromoFilter
        from app.services.filters.base import FilterContext
        
        # 创建过滤器实例并临时设置测试阈值
        filter_instance = TrailingPromoFilter()
        original_threshold = filter_instance.similarity_threshold
        filter_instance.similarity_threshold = test_threshold
        
        # 创建测试上下文
        context = FilterContext(
            message_id=0,
            channel_id="preview_test"
        )
        
        # 执行过滤
        result = await filter_instance.filter(content, context)
        
        # 恢复原始阈值
        filter_instance.similarity_threshold = original_threshold
        
        # 构建预测结果
        prediction = {
            "predicted_action": "filter" if not result.passed else "pass",
            "confidence": result.confidence if hasattr(result, 'confidence') else 0.5,
            "reasoning": result.reason or "实际过滤器测试结果",
            "filtered_content": result.filtered_content,
            "removed_content": content[len(result.filtered_content):] if len(result.filtered_content) < len(content) else "",
            "filter_applied": not result.passed
        }
        
        return prediction
        
    except Exception as e:
        logger.error(f"实际过滤器测试失败: {e}")
        # 降级到启发式预测
        return await heuristic_promo_prediction(content, test_threshold)


async def heuristic_promo_prediction(content: str, test_threshold: float) -> Dict[str, Any]:
    """针对推广内容的启发式预测"""
    
    # 推广关键词检测
    strong_promo_keywords = [
        "订阅", "商务合作", "投稿", "@", "频道", "群组", "联系", "加入",
        "充值", "送", "注册", "娱乐城", "赌博", "彩票", "投资", "理财"
    ]
    
    weak_promo_keywords = [
        "更多", "详情", "了解", "点击", "进入", "查看", "关注"
    ]
    
    # 分析内容
    strong_count = sum(1 for keyword in strong_promo_keywords if keyword in content)
    weak_count = sum(1 for keyword in weak_promo_keywords if keyword in content)
    
    # 计算推广信号强度
    promo_score = (strong_count * 0.3 + weak_count * 0.1)
    
    # 模拟过滤逻辑
    if promo_score >= test_threshold:
        # 预测会被过滤，尝试移除推广部分
        lines = content.split('\n')
        filtered_lines = []
        removed_lines = []
        
        for line in lines:
            line_promo_score = sum(0.3 for keyword in strong_promo_keywords if keyword in line) + \
                              sum(0.1 for keyword in weak_promo_keywords if keyword in line)
            
            if line_promo_score >= 0.2:  # 单行推广阈值
                removed_lines.append(line)
            else:
                filtered_lines.append(line)
        
        filtered_content = '\n'.join(filtered_lines).strip()
        removed_content = '\n'.join(removed_lines)
        
        return {
            "predicted_action": "filter",
            "confidence": min(0.9, promo_score),
            "reasoning": f"检测到推广信号强度{promo_score:.2f}，超过阈值{test_threshold:.3f}",
            "filtered_content": filtered_content,
            "removed_content": removed_content,
            "filter_applied": True
        }
    else:
        return {
            "predicted_action": "pass",
            "confidence": max(0.1, 1.0 - promo_score),
            "reasoning": f"推广信号强度{promo_score:.2f}，低于阈值{test_threshold:.3f}",
            "filtered_content": content,
            "removed_content": "",
            "filter_applied": False
        }


async def generic_filter_prediction(filter_name: str, metric_name: str, content: str, test_threshold: float) -> Dict[str, Any]:
    """通用过滤器预测"""
    
    # 基础预测逻辑
    content_length = len(content)
    
    if content_length < 50:
        return {
            "predicted_action": "pass",
            "confidence": 0.8,
            "reasoning": "内容较短，通常不会被过滤",
            "filtered_content": content,
            "removed_content": "",
            "filter_applied": False
        }
    else:
        return {
            "predicted_action": "unknown",
            "confidence": 0.5,
            "reasoning": f"暂不支持{filter_name}的实时预测",
            "filtered_content": content,
            "removed_content": "",
            "filter_applied": False
        }