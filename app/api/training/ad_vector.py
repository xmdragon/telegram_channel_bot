"""
关键词管理模块 - 关键词规则的CRUD、统计和处理功能
"""
from fastapi import APIRouter, HTTPException
from datetime import datetime
from typing import List, Dict, Any, Optional
import logging
from pydantic import BaseModel

from .base import handle_api_error, validate_pagination_params
from app.core.route_config import ROUTES

logger = logging.getLogger(__name__)
router = APIRouter(tags=["training-ad-vector"])

class VectorTestRequest(BaseModel):
    content: str

class AddVectorRequest(BaseModel):
    content: str
    source: str = "manual"

@router.get(ROUTES.training.ad_vectors)
async def get_ad_vectors(page: int = 1, page_size: int = 20, search: str = ""):
    """获取广告过滤规则列表（分页）- 现在从filter_rules.json读取"""
    try:
        import json
        import os
        from pathlib import Path
        
        # 读取过滤规则文件
        filter_rules_file = Path(__file__).parent.parent.parent.parent / "data" / "config" / "filter_rules.json"
        
        if not os.path.exists(filter_rules_file):
            # 文件不存在，返回空数据
            return {
                "success": True,
                "vectors": [],
                "total": 0,
                "page": page,
                "page_size": page_size,
                "total_pages": 0
            }
        
        # 读取过滤规则数据
        with open(filter_rules_file, 'r', encoding='utf-8') as f:
            rules_data = json.load(f)
        
        # 收集所有广告相关模式
        all_patterns = []
        
        # 高危关键词模式
        high_risk_patterns = rules_data.get('rule_categories', {}).get('high_risk_keywords', {}).get('patterns', [])
        for pattern in high_risk_patterns:
            all_patterns.append({
                'storage_category': 'high_risk_keywords',  # JSON中的存储位置
                'category': pattern.get('category', 'high_risk_keywords'),  # 实际分类
                **pattern
            })
        
        # 推广模式
        promo_patterns = rules_data.get('rule_categories', {}).get('promo_patterns', {}).get('patterns', [])
        for pattern in promo_patterns:
            all_patterns.append({
                'storage_category': 'promo_patterns',  # JSON中的存储位置
                'category': pattern.get('category', 'promo_patterns'),  # 实际分类
                **pattern
            })
        
        # 学习模式
        learned_patterns = rules_data.get('rule_categories', {}).get('learned_patterns', {}).get('patterns', [])
        for pattern in learned_patterns:
            all_patterns.append({
                'storage_category': 'learned_patterns',  # JSON中的存储位置
                'category': pattern.get('category', 'learned_patterns'),  # 实际分类
                **pattern
            })
        
        # 搜索过滤
        if search:
            search_lower = search.lower()
            all_patterns = [p for p in all_patterns if 
                           search_lower in p.get('pattern', '').lower() or 
                           search_lower in p.get('description', '').lower()]
        
        # 按创建时间倒序排列
        all_patterns.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        
        # 分页处理
        total = len(all_patterns)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        page_patterns = all_patterns[start_idx:end_idx]
        
        # 格式化数据供前端使用（适配原有的向量格式）
        formatted_vectors = []
        for i, pattern in enumerate(page_patterns):
            formatted_vectors.append({
                'id': f"{pattern.get('category', 'unknown')}_{start_idx + i}",  # 使用类别和索引作为ID
                'content': pattern.get('pattern', ''),  # 正则表达式模式
                'source': 'auto_learned' if pattern.get('auto_learned', False) else 'manual',  # 自动学习或手动
                'created_at': pattern.get('created_at', ''),
                'vector_length': len(pattern.get('pattern', '')),  # 使用模式长度
                'metadata': {
                    'category': pattern.get('category', 'unknown'),
                    'description': pattern.get('description', ''),
                    'weight': pattern.get('weight', 0),
                    'auto_learned': pattern.get('auto_learned', False),
                    'source_count': pattern.get('source_count', 0)
                }
            })
        
        return {
            "success": True,
            "vectors": formatted_vectors,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size
        }
    except Exception as e:
        logger.error(f"获取广告规则列表失败: {e}")
        return handle_api_error(e, "获取广告规则列表")

@router.get(ROUTES.training.ad_vector_statistics)
async def get_ad_vector_statistics():
    """获取广告过滤规则统计信息 - 现在从filter_rules.json读取"""
    try:
        import json
        import os
        from datetime import datetime
        from pathlib import Path
        
        # 读取过滤规则文件
        filter_rules_file = Path(__file__).parent.parent.parent.parent / "data" / "config" / "filter_rules.json"
        
        if not os.path.exists(filter_rules_file):
            return {
                "success": True,
                "statistics": {
                    "total_vectors": 0,
                    "source_distribution": {},
                    "similarity_threshold": 0.7,
                    "duplicate_threshold": 0.95,
                    "storage_path": str(filter_rules_file),
                    "last_updated": '',
                    "created_at": ''
                }
            }
        
        # 读取过滤规则数据
        with open(filter_rules_file, 'r', encoding='utf-8') as f:
            rules_data = json.load(f)
        
        # 收集所有广告相关模式
        all_patterns = []
        
        # 高危关键词模式
        high_risk_patterns = rules_data.get('rule_categories', {}).get('high_risk_keywords', {}).get('patterns', [])
        all_patterns.extend(high_risk_patterns)
        
        # 推广模式
        promo_patterns = rules_data.get('rule_categories', {}).get('promo_patterns', {}).get('patterns', [])
        all_patterns.extend(promo_patterns)
        
        # 学习模式
        learned_patterns = rules_data.get('rule_categories', {}).get('learned_patterns', {}).get('patterns', [])
        all_patterns.extend(learned_patterns)
        
        # 统计来源分布（自动学习vs手动）
        source_distribution = {}
        for pattern in all_patterns:
            source = 'auto_learned' if pattern.get('auto_learned', False) else 'manual'
            source_distribution[source] = source_distribution.get(source, 0) + 1
        
        # 获取文件修改时间
        last_modified = datetime.fromtimestamp(os.path.getmtime(filter_rules_file)).isoformat()
        
        # 获取最早的模式创建时间
        created_at = ''
        if all_patterns:
            created_dates = [p.get('created_at', '') for p in all_patterns if p.get('created_at')]
            if created_dates:
                created_at = min(created_dates)
        
        # 获取学习统计
        learning_stats = rules_data.get('learning_stats', {})
        
        return {
            "success": True,
            "statistics": {
                "total_vectors": len(all_patterns),
                "source_distribution": source_distribution,
                "similarity_threshold": 0.7,  # 保留兼容性
                "duplicate_threshold": 0.95,  # 保留兼容性
                "storage_path": str(filter_rules_file),
                "last_updated": last_modified,
                "created_at": created_at,
                "learning_stats": learning_stats,
                "category_breakdown": {
                    "high_risk_keywords": len(high_risk_patterns),
                    "promo_patterns": len(promo_patterns), 
                    "learned_patterns": len(learned_patterns)
                }
            }
        }
    except Exception as e:
        logger.error(f"获取广告规则统计失败: {e}")
        return handle_api_error(e, "获取广告规则统计")

@router.delete(ROUTES.training.ad_vector_by_id)
async def delete_ad_vector(vector_id: str):
    """删除单个广告过滤规则 - 现在操作filter_rules.json"""
    try:
        import json
        import os
        from pathlib import Path
        
        # 读取过滤规则文件
        filter_rules_file = Path(__file__).parent.parent.parent.parent / "data" / "config" / "filter_rules.json"
        
        if not os.path.exists(filter_rules_file):
            return {"success": False, "message": "过滤规则文件不存在"}
        
        # 读取过滤规则数据
        with open(filter_rules_file, 'r', encoding='utf-8') as f:
            rules_data = json.load(f)
        
        # 解析vector_id（格式：category_index）
        try:
            category, index_str = vector_id.rsplit('_', 1)
            index = int(index_str)
        except (ValueError, AttributeError):
            return {"success": False, "message": "无效的规则ID格式"}
        
        # 根据类别和索引删除对应的模式
        deleted = False
        deleted_pattern = None
        
        # 首先，重建和获取列表时相同的全局模式列表
        all_patterns = []
        rule_categories = rules_data.get('rule_categories', {})
        
        # 按照获取列表时相同的顺序收集所有模式
        for category_name in ['high_risk_keywords', 'promo_patterns', 'learned_patterns']:
            patterns = rule_categories.get(category_name, {}).get('patterns', [])
            for pattern in patterns:
                all_patterns.append({
                    'storage_category': category_name,  # JSON中的存储位置
                    'category': pattern.get('category', category_name),  # 实际分类
                    'pattern_data': pattern,
                    **pattern
                })
        
        # 按创建时间倒序排列（与获取时相同）
        all_patterns.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        
        # 查找匹配的ID并删除
        for global_index, pattern_info in enumerate(all_patterns):
            expected_id = f"{pattern_info.get('category', 'unknown')}_{global_index}"
            if expected_id == vector_id:
                # 找到了匹配的模式，从存储类别中删除
                storage_category = pattern_info['storage_category']
                pattern_data = pattern_info['pattern_data']
                
                # 从存储类别的模式列表中删除
                storage_patterns = rule_categories.get(storage_category, {}).get('patterns', [])
                if pattern_data in storage_patterns:
                    storage_patterns.remove(pattern_data)
                    deleted_pattern = pattern_data
                    deleted = True
                    logger.info(f"删除关键词规则 (存储在{storage_category}): {pattern_data.get('description', pattern_data.get('pattern', 'N/A'))}")
                break
        
        if not deleted:
            return {"success": False, "message": "过滤规则不存在或索引无效"}
        
        # 更新学习统计
        if 'learning_stats' in rules_data:
            rules_data['learning_stats']['patterns_removed'] = rules_data['learning_stats'].get('patterns_removed', 0) + 1
            rules_data['learning_stats']['last_cleanup'] = datetime.now().isoformat()
        
        # 保存更新后的规则
        with open(filter_rules_file, 'w', encoding='utf-8') as f:
            json.dump(rules_data, f, ensure_ascii=False, indent=2)
        
        return {"success": True, "message": "过滤规则删除成功"}
            
    except Exception as e:
        logger.error(f"删除过滤规则失败: {e}")
        return handle_api_error(e, "删除广告过滤规则")

@router.delete(ROUTES.training.ad_vectors_batch)
async def batch_delete_ad_vectors(request: dict):
    """批量删除关键词规则"""
    try:
        vector_ids = request.get("vector_ids", [])
        
        if not vector_ids:
            return {"success": False, "message": "没有指定要删除的关键词规则"}
        
        import json
        import os
        from app.core.path_config import PathConfig
        
        # 读取广告训练数据文件
        ad_training_file = PathConfig.AD_TRAINING_FILE
        
        if not os.path.exists(ad_training_file):
            return {"success": False, "message": "训练数据文件不存在"}
        
        # 读取训练数据
        with open(ad_training_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            samples = data.get('samples', [])
        
        # 删除指定样本（vector_ids对应message_ids）
        original_count = len(samples)
        samples = [s for s in samples if s.get('message_id') not in vector_ids]
        deleted_count = original_count - len(samples)
        
        if deleted_count > 0:
            # 保存数据
            with open(ad_training_file, 'w', encoding='utf-8') as f:
                json.dump({"samples": samples}, f, ensure_ascii=False, indent=2)
        
        logger.info(f"成功删除 {deleted_count} 个关键词规则")
        return {
            "success": True,
            "message": f"批量删除完成，删除了 {deleted_count} 个关键词规则",
            "deleted_count": deleted_count
        }
    except Exception as e:
        logger.error(f"批量删除向量失败: {e}")
        return handle_api_error(e, "批量删除广告向量")

@router.post(ROUTES.training.ad_vector_test_detection)
async def test_ad_detection(request: VectorTestRequest):
    """测试广告检测（现在基于关键词检测）"""
    try:
        content = request.content.strip()
        
        if not content:
            return {"success": False, "message": "测试内容不能为空"}
        
        from app.services.unified_ad_detector import unified_ad_detector
        
        # 使用统一广告检测器进行检测
        detection_result = unified_ad_detector.detect(content)
        
        return {
            "success": True,
            "is_ad": detection_result.is_ad,
            "confidence": detection_result.confidence,
            "threshold": 0.7,  # 保留兼容性
            "details": {"reason": detection_result.reason} if detection_result.reason else {},
            "test_content": content[:200]  # 返回前200字符
        }
    except Exception as e:
        logger.error(f"测试广告检测失败: {e}")
        return handle_api_error(e, "测试广告检测")

@router.post(ROUTES.training.ad_vector_add_from_text)
async def add_vector_from_text(request: AddVectorRequest):
    """添加广告过滤规则 - 现在添加到filter_rules.json"""
    try:
        import json
        import os
        from datetime import datetime
        from pathlib import Path
        import re
        
        content = request.content.strip()
        source = request.source
        
        if not content:
            return {"success": False, "message": "规则内容不能为空"}
        
        # 读取过滤规则文件
        filter_rules_file = Path(__file__).parent.parent.parent.parent / "data" / "config" / "filter_rules.json"
        
        # 读取现有规则数据
        if os.path.exists(filter_rules_file):
            with open(filter_rules_file, 'r', encoding='utf-8') as f:
                rules_data = json.load(f)
        else:
            return {"success": False, "message": "过滤规则文件不存在"}
        
        # 验证是否为有效的正则表达式
        try:
            re.compile(content)
        except re.error as e:
            return {"success": False, "message": f"无效的正则表达式: {str(e)}"}
        
        # 检查是否已存在相同模式
        all_patterns = []
        for category in ['high_risk_keywords', 'promo_patterns', 'learned_patterns']:
            patterns = rules_data.get('rule_categories', {}).get(category, {}).get('patterns', [])
            all_patterns.extend(patterns)
        
        for pattern in all_patterns:
            if pattern.get('pattern') == content:
                return {"success": False, "message": "该规则已存在"}
        
        # 创建新规则模式
        new_pattern = {
            "pattern": content,
            "weight": 8,  # 手动添加的规则权重适中
            "description": f"手动添加的广告规则 - {source}",
            "category": "manual_addition",
            "auto_learned": False,
            "created_at": datetime.now().isoformat(),
            "added_by": source
        }
        
        # 根据内容判断添加到哪个类别（简单启发式）
        if any(keyword in content.lower() for keyword in ['博彩', '赌场', 'usdt', '娱乐城', '出款', '充值']):
            # 高危关键词类别
            rules_data['rule_categories']['high_risk_keywords']['patterns'].append(new_pattern)
            category = 'high_risk_keywords'
        else:
            # 推广模式类别  
            rules_data['rule_categories']['promo_patterns']['patterns'].append(new_pattern)
            category = 'promo_patterns'
        
        # 更新学习统计
        if 'learning_stats' in rules_data:
            rules_data['learning_stats']['total_learned'] = rules_data['learning_stats'].get('total_learned', 0) + 1
            rules_data['learning_stats']['last_learning'] = datetime.now().isoformat()
            rules_data['learning_stats']['patterns_by_category']['manual_addition'] = rules_data['learning_stats']['patterns_by_category'].get('manual_addition', 0) + 1
        
        # 更新最后修改时间
        rules_data['last_updated'] = datetime.now().isoformat()
        
        # 保存规则数据
        with open(filter_rules_file, 'w', encoding='utf-8') as f:
            json.dump(rules_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"添加广告过滤规则到 {category}: {content}")
        return {"success": True, "message": f"关键词规则已添加到 {category} 类别"}
            
    except Exception as e:
        logger.error(f"添加过滤规则失败: {e}")
        return handle_api_error(e, "添加广告过滤规则")

@router.get(ROUTES.training.ad_vector_stats)
async def get_ad_vector_stats():
    """获取关键词规则简化统计"""
    try:
        import json
        import os
        from datetime import datetime
        from app.core.path_config import PathConfig
        
        # 读取广告训练数据文件
        ad_training_file = PathConfig.AD_TRAINING_FILE
        
        if not os.path.exists(ad_training_file):
            return {
                "success": True,
                "stats": {
                    "totalVectors": 0,
                    "lastUpdate": datetime.now().isoformat()
                }
            }
        
        # 读取训练数据
        with open(ad_training_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            samples = data.get('samples', [])
        
        # 获取最后更新时间
        last_update = datetime.fromtimestamp(os.path.getmtime(ad_training_file)).isoformat()
        
        return {
            "success": True,
            "stats": {
                "totalVectors": len(samples),
                "lastUpdate": last_update
            }
        }
    except Exception as e:
        logger.error(f"获取向量统计失败: {e}")
        return handle_api_error(e, "获取广告向量统计")