"""
广告训练相关API
"""
from fastapi import APIRouter, HTTPException
from typing import List, Dict, Optional
from datetime import datetime
import json
import hashlib
from pathlib import Path
import logging

from app.services.adaptive_learning import adaptive_learning
from app.services.tail_feature_extractor import tail_feature_extractor
from app.services.tail_vector_manager import tail_vector_manager
from app.core.path_config import PathConfig
from app.utils.safe_file_ops import SafeFileOperation

logger = logging.getLogger(__name__)
router = APIRouter()

# 数据文件路径（使用集中配置）
SEPARATOR_PATTERNS_FILE = PathConfig.SEPARATOR_PATTERNS_FILE

# 确保数据目录存在
PathConfig.ensure_directories()


@router.get("/separator-patterns")
async def get_separator_patterns():
    """获取分隔符模式列表"""
    try:
        if SEPARATOR_PATTERNS_FILE.exists():
            with open(SEPARATOR_PATTERNS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return {"patterns": data.get("patterns", [])}
        else:
            # 返回默认模式
            default_patterns = [
                {"regex": "━{10,}", "description": "横线分隔符（10个以上）"},
                {"regex": "═{10,}", "description": "双线分隔符"},
                {"regex": "─{10,}", "description": "细线分隔符"},
                {"regex": "▬{10,}", "description": "粗线分隔符"},
                {"regex": "-{20,}", "description": "短横线（20个以上）"},
                {"regex": "={20,}", "description": "等号线"},
                {"regex": "\\*{20,}", "description": "星号线"}
            ]
            return {"patterns": default_patterns}
    except Exception as e:
        logger.error(f"获取分隔符模式失败: {e}")
        return {"patterns": []}


@router.post("/separator-patterns")
async def save_separator_patterns(request: dict):
    """保存分隔符模式"""
    try:
        patterns = request.get("patterns", [])
        
        # 保存到文件
        with open(SEPARATOR_PATTERNS_FILE, 'w', encoding='utf-8') as f:
            json.dump({
                "patterns": patterns,
                "updated_at": datetime.now().isoformat()
            }, f, ensure_ascii=False, indent=2)
        
        # 更新smart_tail_filter的模式
        from app.services.smart_tail_filter import smart_tail_filter
        smart_tail_filter.separator_patterns = [p['regex'] for p in patterns if p.get('regex')]
        
        logger.info(f"保存了 {len(patterns)} 个分隔符模式")
        return {"success": True, "message": "分隔符模式已保存"}
    except Exception as e:
        logger.error(f"保存分隔符模式失败: {e}")
        return {"success": False, "error": str(e)}



@router.get("/ad-samples")
async def get_ad_samples(page: int = 1, size: int = 20, search: str = "", filter: str = "all"):
    """获取广告训练样本（分页）"""
    try:
        # 收集所有样本并生成统一的样本ID
        samples = []
        sample_id_counter = 1
        
        # 从ad_training_data.json获取样本
        ad_data_file = PathConfig.AD_TRAINING_FILE
        if ad_data_file.exists():
            ad_data = SafeFileOperation.read_json_safe(ad_data_file)
            if ad_data:
                ad_samples = ad_data.get("samples", [])
                for sample in ad_samples:
                    # 统一格式，使用递增的样本ID
                    formatted_sample = {
                        "id": sample_id_counter,  # 使用统一的样本ID
                        "content": sample.get('content', ''),
                        "is_ad": sample.get('is_ad', True),
                        "description": sample.get('description', ''),
                        "created_at": sample.get('created_at', ''),
                        "source": sample.get('source', 'ad_data'),
                        # 保留原始消息信息用于删除操作
                        "_original_message_id": sample.get('message_id'),
                        "_original_id": sample.get('id')
                    }
                    samples.append(formatted_sample)
                    sample_id_counter += 1
        
        
        # 搜索过滤
        if search:
            samples = [s for s in samples if search.lower() in str(s.get('content', '')).lower()]
        
        # 类型过滤
        if filter == "ad":
            samples = [s for s in samples if s.get('is_ad') == True]
        elif filter == "normal":
            samples = [s for s in samples if s.get('is_ad') == False]
        
        # 分页
        total = len(samples)
        start = (page - 1) * size
        end = start + size
        page_samples = samples[start:end]
        
        return {
            "success": True,
            "samples": page_samples,
            "pagination": {
                "current_page": page,
                "page_size": size,
                "total_items": total,
                "total_pages": (total + size - 1) // size
            },
            "total": total
        }
    except Exception as e:
        logger.error(f"获取广告样本失败: {e}")
        return {
            "success": False,
            "samples": [],
            "pagination": {
                "current_page": 1,
                "page_size": size,
                "total_items": 0,
                "total_pages": 0
            },
            "total": 0
        }

@router.get("/ad-statistics")
async def get_ad_statistics():
    """获取广告训练统计信息"""
    try:
        # 从ad_training_data.json获取
        ad_data_file = PathConfig.AD_TRAINING_FILE
        samples = []
        
        if ad_data_file.exists():
            ad_data = SafeFileOperation.read_json_safe(ad_data_file)
            if ad_data:
                samples.extend(ad_data.get("samples", []))
        
        
        # 计算统计数据
        total_samples = len(samples)
        ad_samples = len([s for s in samples if s.get('is_ad') == True])
        normal_samples = len([s for s in samples if s.get('is_ad') == False])
        
        # 计算今日新增
        today = datetime.now().date()
        today_added = 0
        for sample in samples:
            created_at = sample.get('created_at', '')
            if created_at:
                try:
                    sample_date = datetime.fromisoformat(created_at).date()
                    if sample_date == today:
                        today_added += 1
                except:
                    pass
        
        return {
            "success": True,
            "total_samples": total_samples,
            "ad_samples": ad_samples,
            "normal_samples": normal_samples,
            "today_added": today_added,
            "accuracy": round(ad_samples / max(total_samples, 1) * 100, 1) if total_samples > 0 else 0
        }
    except Exception as e:
        logger.error(f"获取广告训练统计失败: {e}")
        return {
            "success": False,
            "total_samples": 0,
            "ad_samples": 0,
            "normal_samples": 0,
            "today_added": 0,
            "accuracy": 0
        }

@router.delete("/ad-samples/{sample_id}")
async def delete_ad_sample(sample_id: int):
    """删除广告训练样本"""
    try:
        # 创建一个稳定的删除方案：使用sample_id作为样本在整体列表中的索引
        all_samples = []
        
        # 从ad_training_data.json获取所有样本
        ad_data_file = PathConfig.AD_TRAINING_FILE
        ad_start_index = 0
        ad_data = None
        
        if ad_data_file.exists():
            ad_data = SafeFileOperation.read_json_safe(ad_data_file)
            if ad_data:
                ad_samples = ad_data.get("samples", [])
                all_samples.extend([(i, sample, 'ad_data') for i, sample in enumerate(ad_samples)])
        
        
        # 检查sample_id是否有效（从1开始计数）
        if sample_id < 1 or sample_id > len(all_samples):
            return {"success": False, "message": "样本不存在"}
        
        # 获取要删除的样本信息（sample_id从1开始，索引从0开始）
        target_index = sample_id - 1
        original_index, target_sample, source = all_samples[target_index]
        
        deleted = False
        
        if source == 'ad_data' and ad_data:
            # 从ad_training_data.json删除
            samples = ad_data.get("samples", [])
            if original_index < len(samples):
                samples.pop(original_index)
                ad_data['samples'] = samples
                ad_data['updated_at'] = datetime.now().isoformat()
                SafeFileOperation.write_json_safe(ad_data_file, ad_data)
                deleted = True
                logger.info(f"从ad_training_data.json删除样本: index={original_index}")
        
        
        if deleted:
            return {"success": True, "message": "样本已删除"}
        else:
            return {"success": False, "message": "删除失败"}
    except Exception as e:
        logger.error(f"删除广告样本失败: {e}")
        return {"success": False, "message": str(e)}

@router.delete("/ad-samples/batch")
async def delete_ad_samples_batch(request: dict):
    """批量删除广告训练样本"""
    try:
        ids = request.get("ids", [])
        if not ids:
            return {"success": False, "message": "没有指定要删除的样本"}
        
        deleted_count = 0
        
        # 从ad_training_data.json批量删除
        ad_data_file = PathConfig.AD_TRAINING_FILE
        if ad_data_file.exists():
            ad_data = SafeFileOperation.read_json_safe(ad_data_file)
            if ad_data:
                samples = ad_data.get("samples", [])
                original_count = len(samples)
                samples = [s for s in samples if s.get('id') not in ids]
                deleted_count += original_count - len(samples)
                if deleted_count > 0:
                    ad_data['samples'] = samples
                    ad_data['updated_at'] = datetime.now().isoformat()
                    SafeFileOperation.write_json_safe(ad_data_file, ad_data)
        
        
        return {
            "success": True, 
            "message": f"成功删除 {deleted_count} 个样本",
            "deleted_count": deleted_count
        }
    except Exception as e:
        logger.error(f"批量删除广告样本失败: {e}")
        return {"success": False, "message": str(e)}

@router.post("/ad-samples/detect-duplicates")
async def detect_ad_duplicates():
    """检测广告训练样本中的重复项"""
    try:
        logger.info("开始检测广告样本重复项...")
        
        # 收集所有样本
        all_samples = []
        
        # 从ad_training_data.json获取
        ad_data_file = PathConfig.AD_TRAINING_FILE
        if ad_data_file.exists():
            ad_data = SafeFileOperation.read_json_safe(ad_data_file)
            if ad_data:
                ad_samples = ad_data.get("samples", [])
                logger.info(f"从ad_training_data.json加载了 {len(ad_samples)} 个样本")
                all_samples.extend(ad_samples)
        
        
        logger.info(f"总共收集了 {len(all_samples)} 个样本进行重复检测")
        
        if len(all_samples) == 0:
            logger.info("没有样本数据，跳过重复检测")
            return {
                "success": True,
                "groups": [],
                "total_duplicates": 0,
                "total_groups": 0
            }
        
        # 检测重复 - 基于内容相似度
        duplicate_groups = []
        processed = set()
        
        for i, sample1 in enumerate(all_samples):
            try:
                sample1_id = sample1.get('id', f"sample_{i}")
                
                if sample1_id in processed:
                    continue
                    
                group = [sample1]
                content1 = str(sample1.get('content', '')).lower().strip()
                
                # 只有内容不为空才进行比较
                if not content1:
                    continue
                
                for j, sample2 in enumerate(all_samples[i+1:], i+1):
                    sample2_id = sample2.get('id', f"sample_{j}")
                    
                    if sample2_id in processed:
                        continue
                        
                    content2 = str(sample2.get('content', '')).lower().strip()
                    
                    # 只有内容不为空才进行比较
                    if not content2:
                        continue
                    
                    # 简单的相似度检测：内容完全相同或包含关系
                    is_duplicate = False
                    if content1 == content2:
                        is_duplicate = True
                    elif len(content1) > 50 and len(content2) > 50:
                        # 对于长文本，检查包含关系
                        if content1 in content2 or content2 in content1:
                            is_duplicate = True
                    
                    if is_duplicate:
                        group.append(sample2)
                        processed.add(sample2_id)
                
                if len(group) > 1:
                    duplicate_groups.append({
                        "similarity": 100,  # 完全匹配
                        "samples": group,
                        "count": len(group)
                    })
                    for sample in group:
                        sample_id = sample.get('id', f"sample_{all_samples.index(sample) if sample in all_samples else 'unknown'}")
                        processed.add(sample_id)
                        
            except Exception as sample_error:
                logger.error(f"处理样本 {i} 时出错: {sample_error}")
                continue
        
        total_duplicates = sum(len(group['samples']) - 1 for group in duplicate_groups)
        
        logger.info(f"重复检测完成: 发现 {len(duplicate_groups)} 组重复，总计 {total_duplicates} 个重复样本")
        
        return {
            "success": True,
            "groups": duplicate_groups,
            "total_duplicates": total_duplicates,
            "total_groups": len(duplicate_groups)
        }
    except Exception as e:
        logger.error(f"检测重复广告样本失败: {e}", exc_info=True)
        return {
            "success": False,
            "groups": [],
            "total_duplicates": 0,
            "total_groups": 0,
            "error": str(e)
        }

@router.post("/ad-samples/deduplicate")
async def deduplicate_ad_samples(request: dict):
    """去重广告训练样本"""
    try:
        # 获取要保留和删除的样本ID
        keep_ids = request.get("keep_ids", [])
        remove_ids = request.get("remove_ids", [])
        
        if not remove_ids:
            return {"success": False, "message": "没有指定要删除的重复样本"}
        
        # 执行删除操作（复用批量删除逻辑）
        delete_request = {"ids": remove_ids}
        result = await delete_ad_samples_batch(delete_request)
        
        return {
            "success": result["success"],
            "message": f"去重完成，删除了 {result.get('deleted_count', 0)} 个重复样本",
            "removed_count": result.get('deleted_count', 0)
        }
    except Exception as e:
        logger.error(f"去重广告样本失败: {e}")
        return {"success": False, "message": str(e)}




@router.get("/learning-stats")
async def get_learning_stats():
    """获取学习统计信息"""
    try:
        stats = await adaptive_learning.get_learning_stats_from_file()
        return {"success": True, "stats": stats}
    except Exception as e:
        logger.error(f"获取学习统计失败: {e}")
        return {"success": False, "error": str(e)}


@router.post("/feedback")
async def record_feedback(request: dict):
    """记录用户反馈用于学习"""
    try:
        message_id = request.get("message_id")
        action = request.get("action")  # 'approved', 'rejected', 'edited'
        reviewer = request.get("reviewer", "Web用户")
        content = request.get("content", "")
        
        if not message_id or not action:
            return {"success": False, "error": "参数不完整"}
        
        # 记录反馈到JSON文件
        feedback_data = {
            "message_id": message_id,
            "action": action,
            "reviewer": reviewer,
            "content": content,
            "timestamp": datetime.now().isoformat()
        }
        
        await adaptive_learning.record_feedback_to_file(feedback_data)
        
        return {"success": True, "message": "反馈已记录"}
        
    except Exception as e:
        logger.error(f"记录反馈失败: {e}")
        return {"success": False, "error": str(e)}


# ==================== 尾部过滤样本 API ====================

@router.get("/tail-samples")
async def get_tail_samples(page: int = 1, size: int = 20, search: str = ""):
    """获取尾部过滤样本（分页）"""
    try:
        samples_file = PathConfig.TAIL_FILTER_SAMPLES_FILE
        if not samples_file.exists():
            return {
                "success": True,
                "samples": [],
                "pagination": {
                    "current_page": 1,
                    "page_size": size,
                    "total_items": 0,
                    "total_pages": 0
                },
                "total": 0
            }
        
        # 读取样本数据
        data = SafeFileOperation.read_json_safe(samples_file)
        if not data or 'samples' not in data:
            return {
                "success": True,
                "samples": [],
                "pagination": {
                    "current_page": 1,
                    "page_size": size,
                    "total_items": 0,
                    "total_pages": 0
                },
                "total": 0
            }
        
        samples = data['samples']
        
        # 搜索过滤
        if search:
            samples = [s for s in samples if search.lower() in str(s.get('tail_part', '')).lower()]
        
        # 分页
        total = len(samples)
        start = (page - 1) * size
        end = start + size
        page_samples = samples[start:end]
        
        # 为展示添加额外信息
        for sample in page_samples:
            if 'characteristics' in sample:
                char = sample['characteristics']
                sample['display_score'] = f"{char.get('promotion_score', 0):.2f}"
                sample['display_commercial'] = f"{char.get('commercial_score', 0):.2f}"
            if 'auto_features' in sample:
                features = sample['auto_features']
                sample['display_features'] = {
                    'has_links': features.get('has_telegram_link', False) or features.get('link_count', 0) > 0,
                    'link_count': features.get('link_count', 0),
                    'action_words': len(features.get('action_words', [])),
                    'business_words': len(features.get('business_words', []))
                }
        
        return {
            "success": True,
            "samples": page_samples,
            "pagination": {
                "current_page": page,
                "page_size": size,
                "total_items": total,
                "total_pages": (total + size - 1) // size
            },
            "total": total,
            "metadata": data.get('metadata', {})
        }
    except Exception as e:
        logger.error(f"获取尾部样本失败: {e}")
        return {
            "success": False,
            "samples": [],
            "pagination": {
                "current_page": 1,
                "page_size": size,
                "total_items": 0,
                "total_pages": 0
            },
            "total": 0
        }

@router.get("/tail-statistics")
async def get_tail_statistics():
    """获取尾部过滤统计信息"""
    try:
        samples_file = PathConfig.TAIL_FILTER_SAMPLES_FILE
        if not samples_file.exists():
            return {
                "success": True,
                "total_samples": 0,
                "high_promotion_samples": 0,
                "has_links_samples": 0,
                "avg_promotion_score": 0.0,
                "vector_count": 0,
                "cluster_count": 0
            }
        
        data = SafeFileOperation.read_json_safe(samples_file)
        if not data or 'samples' not in data:
            return {
                "success": True,
                "total_samples": 0,
                "high_promotion_samples": 0,
                "has_links_samples": 0,
                "avg_promotion_score": 0.0,
                "vector_count": 0,
                "cluster_count": 0
            }
        
        samples = data['samples']
        total_samples = len(samples)
        
        if total_samples == 0:
            return {
                "success": True,
                "total_samples": 0,
                "high_promotion_samples": 0,
                "has_links_samples": 0,
                "avg_promotion_score": 0.0,
                "vector_count": 0,
                "cluster_count": 0
            }
        
        # 统计信息
        promotion_scores = []
        high_promotion_count = 0
        has_links_count = 0
        
        for sample in samples:
            if 'characteristics' in sample:
                char = sample['characteristics']
                score = char.get('promotion_score', 0)
                promotion_scores.append(score)
                if score > 0.7:
                    high_promotion_count += 1
            
            if 'auto_features' in sample:
                features = sample['auto_features']
                if features.get('has_telegram_link', False) or features.get('link_count', 0) > 0:
                    has_links_count += 1
        
        avg_promotion_score = sum(promotion_scores) / len(promotion_scores) if promotion_scores else 0.0
        
        # 向量统计
        vector_stats = tail_vector_manager.get_statistics()
        
        return {
            "success": True,
            "total_samples": total_samples,
            "high_promotion_samples": high_promotion_count,
            "has_links_samples": has_links_count,
            "avg_promotion_score": round(avg_promotion_score, 3),
            "vector_count": vector_stats.get('total_vectors', 0),
            "cluster_count": vector_stats.get('cluster_count', 0),
            "metadata": data.get('metadata', {})
        }
    except Exception as e:
        logger.error(f"获取尾部统计失败: {e}")
        return {
            "success": False,
            "total_samples": 0,
            "high_promotion_samples": 0,
            "has_links_samples": 0,
            "avg_promotion_score": 0.0,
            "vector_count": 0,
            "cluster_count": 0
        }

@router.post("/tail-samples")
async def add_tail_sample(request: dict):
    """添加新的尾部过滤样本（使用AI分析）"""
    try:
        tail_part = request.get("tail_part", "").strip()
        if not tail_part:
            return {"success": False, "message": "尾部内容不能为空"}
        
        # 读取现有数据
        samples_file = PathConfig.TAIL_FILTER_SAMPLES_FILE
        if samples_file.exists():
            data = SafeFileOperation.read_json_safe(samples_file)
            if not data:
                data = {"version": "2.0", "samples": [], "metadata": {}}
        else:
            data = {"version": "2.0", "samples": [], "metadata": {}}
        
        # 生成新样本ID
        existing_ids = [s.get('id', 0) for s in data.get('samples', [])]
        new_id = max(existing_ids) + 1 if existing_ids else 1
        
        # AI特征提取和分析
        features = tail_feature_extractor.extract_features(tail_part)
        scores = tail_feature_extractor.calculate_scores(tail_part, features)
        
        # 向量化并添加到管理器
        vector_index = tail_vector_manager.add_vector(tail_part, new_id)
        
        # 构建新样本
        new_sample = {
            "id": new_id,
            "tail_part": tail_part,
            
            # AI分析结果
            "characteristics": {
                "promotion_score": scores['promotion_score'],
                "commercial_score": scores['commercial_score'],
                "relevance_score": scores['relevance_score']
            },
            
            # 自动提取的特征
            "auto_features": {
                "has_telegram_link": features['has_telegram_link'],
                "has_contact": features['has_contact'],
                "action_words": features['action_words'],
                "business_words": features['business_words'],
                "link_count": features['link_count'],
                "emoji_count": features['emoji_count'],
                "text_length": features['text_length'],
                "word_count": features['word_count']
            },
            
            # 向量信息
            "vector_index": vector_index,
            
            # 时间信息
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
        
        # 添加到数据中
        data['samples'].append(new_sample)
        data['updated_at'] = datetime.now().isoformat()
        
        # 更新元数据
        if 'metadata' not in data:
            data['metadata'] = {}
        data['metadata']['total_samples'] = len(data['samples'])
        data['metadata']['last_added'] = datetime.now().isoformat()
        
        # 保存数据
        SafeFileOperation.write_json_safe(samples_file, data)
        
        # 保存向量数据
        tail_vector_manager.save()
        
        logger.info(f"添加新尾部样本: ID={new_id}, 推广得分={scores['promotion_score']:.2f}")
        
        return {
            "success": True,
            "message": "尾部样本已添加",
            "sample_id": new_id,
            "analysis": {
                "promotion_score": round(scores['promotion_score'], 3),
                "commercial_score": round(scores['commercial_score'], 3),
                "features": {
                    "has_links": features['has_telegram_link'] or features['link_count'] > 0,
                    "link_count": features['link_count'],
                    "action_words_count": len(features['action_words']),
                    "business_words_count": len(features['business_words'])
                }
            }
        }
    except Exception as e:
        logger.error(f"添加尾部样本失败: {e}")
        return {"success": False, "message": str(e)}

@router.delete("/tail-samples/{sample_id}")
async def delete_tail_sample(sample_id: int):
    """删除尾部过滤样本"""
    try:
        # 读取现有数据
        samples_file = PathConfig.TAIL_FILTER_SAMPLES_FILE
        if not samples_file.exists():
            return {"success": False, "message": "样本文件不存在"}
        
        data = SafeFileOperation.read_json_safe(samples_file)
        if not data or 'samples' not in data:
            return {"success": False, "message": "样本数据异常"}
        
        # 查找并删除样本
        original_count = len(data['samples'])
        data['samples'] = [s for s in data['samples'] if s.get('id') != sample_id]
        
        if len(data['samples']) == original_count:
            return {"success": False, "message": "样本不存在"}
        
        # 从向量管理器删除
        tail_vector_manager.remove_vector(sample_id)
        
        # 更新数据
        data['updated_at'] = datetime.now().isoformat()
        if 'metadata' in data:
            data['metadata']['total_samples'] = len(data['samples'])
        
        # 保存数据
        SafeFileOperation.write_json_safe(samples_file, data)
        
        # 保存向量数据
        tail_vector_manager.save()
        
        logger.info(f"删除尾部样本: ID={sample_id}")
        
        return {"success": True, "message": "尾部样本已删除"}
    except Exception as e:
        logger.error(f"删除尾部样本失败: {e}")
        return {"success": False, "message": str(e)}

@router.post("/tail-samples/analyze")
async def analyze_tail_content(request: dict):
    """分析尾部内容（不保存，仅分析）"""
    try:
        tail_part = request.get("tail_part", "").strip()
        if not tail_part:
            return {"success": False, "message": "尾部内容不能为空"}
        
        # AI特征提取和分析
        features = tail_feature_extractor.extract_features(tail_part)
        scores = tail_feature_extractor.calculate_scores(tail_part, features)
        
        # 查找相似样本
        similar_samples = tail_vector_manager.find_similar(
            tail_part, top_k=5, threshold=0.7
        )
        
        return {
            "success": True,
            "analysis": {
                "scores": {
                    "promotion_score": round(scores['promotion_score'], 3),
                    "commercial_score": round(scores['commercial_score'], 3),
                    "relevance_score": round(scores['relevance_score'], 3),
                    "overall_score": round(scores['overall_score'], 3)
                },
                "features": {
                    "has_telegram_link": features['has_telegram_link'],
                    "has_contact": features['has_contact'],
                    "link_count": features['link_count'],
                    "emoji_count": features['emoji_count'],
                    "text_length": features['text_length'],
                    "word_count": features['word_count'],
                    "action_words": features['action_words'],
                    "business_words": features['business_words']
                },
                "similar_samples": similar_samples,
                "recommendation": {
                    "should_filter": scores['overall_score'] >= 0.7,
                    "confidence": min(scores['overall_score'] * 1.2, 1.0),
                    "reason": "高推广得分" if scores['promotion_score'] > 0.7 else 
                             "高商业化得分" if scores['commercial_score'] > 0.7 else 
                             "综合评分较低" if scores['overall_score'] < 0.3 else "中等评分"
                }
            }
        }
    except Exception as e:
        logger.error(f"分析尾部内容失败: {e}")
        return {"success": False, "message": str(e)}