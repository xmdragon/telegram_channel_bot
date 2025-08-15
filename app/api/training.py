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
from app.core.path_config import PathConfig
from app.utils.safe_file_ops import SafeFileOperation

logger = logging.getLogger(__name__)
router = APIRouter()

# 数据文件路径（使用集中配置）
SEPARATOR_PATTERNS_FILE = PathConfig.SEPARATOR_PATTERNS_FILE
TAIL_AD_SAMPLES_FILE = PathConfig.TAIL_AD_SAMPLES_FILE

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


@router.get("/tail-ad-samples")
async def get_tail_ad_samples():
    """获取尾部广告训练样本"""
    try:
        if TAIL_AD_SAMPLES_FILE.exists():
            with open(TAIL_AD_SAMPLES_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                samples = data.get("samples", [])
                
                # 添加ID如果没有
                for i, sample in enumerate(samples):
                    if 'id' not in sample:
                        sample['id'] = i + 1
                
                return {"samples": samples}
        else:
            return {"samples": []}
    except Exception as e:
        logger.error(f"获取尾部广告样本失败: {e}")
        return {"samples": []}

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
        
        # 从tail_ad_samples获取样本
        if TAIL_AD_SAMPLES_FILE.exists():
            with open(TAIL_AD_SAMPLES_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                tail_samples = data.get("samples", [])
                
                for sample in tail_samples:
                    formatted_sample = {
                        "id": sample_id_counter,  # 使用统一的样本ID
                        "content": sample.get('content', ''),
                        "is_ad": True,  # tail_ad_samples都是广告样本
                        "description": sample.get('description', ''),
                        "created_at": sample.get('created_at', ''),
                        "source": "tail_ad",
                        # 保留原始ID用于删除操作
                        "_original_tail_id": sample.get('id')
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
        
        # 从tail_ad_samples获取
        if TAIL_AD_SAMPLES_FILE.exists():
            with open(TAIL_AD_SAMPLES_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                tail_samples = data.get("samples", [])
                samples.extend(tail_samples)
        
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
        
        # 从tail_ad_samples获取所有样本
        tail_start_index = len(all_samples)
        tail_data = None
        
        if TAIL_AD_SAMPLES_FILE.exists():
            with open(TAIL_AD_SAMPLES_FILE, 'r', encoding='utf-8') as f:
                tail_data = json.load(f)
                tail_samples = tail_data.get("samples", [])
                all_samples.extend([(i, sample, 'tail_ad') for i, sample in enumerate(tail_samples)])
        
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
        
        elif source == 'tail_ad' and tail_data:
            # 从tail_ad_samples删除
            samples = tail_data.get("samples", [])
            if original_index < len(samples):
                samples.pop(original_index)
                tail_data['samples'] = samples
                tail_data['updated_at'] = datetime.now().isoformat()
                with open(TAIL_AD_SAMPLES_FILE, 'w', encoding='utf-8') as f:
                    json.dump(tail_data, f, ensure_ascii=False, indent=2)
                deleted = True
                logger.info(f"从tail_ad_samples.json删除样本: index={original_index}")
        
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
        
        # 从tail_ad_samples批量删除
        if TAIL_AD_SAMPLES_FILE.exists():
            with open(TAIL_AD_SAMPLES_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                samples = data.get("samples", [])
                original_count = len(samples)
                samples = [s for s in samples if s.get('id') not in ids]
                batch_deleted = original_count - len(samples)
                if batch_deleted > 0:
                    deleted_count += batch_deleted
                    data['samples'] = samples
                    data['updated_at'] = datetime.now().isoformat()
                    with open(TAIL_AD_SAMPLES_FILE, 'w', encoding='utf-8') as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
        
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
        
        # 从tail_ad_samples获取
        if TAIL_AD_SAMPLES_FILE.exists():
            with open(TAIL_AD_SAMPLES_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                tail_samples = data.get("samples", [])
                logger.info(f"从tail_ad_samples.json加载了 {len(tail_samples)} 个样本")
                
                # 转换格式并确保ID存在
                for i, sample in enumerate(tail_samples):
                    formatted_sample = {
                        "id": sample.get('id', f"tail_{i}"),  # 确保ID存在
                        "content": sample.get('content', ''),
                        "is_ad": True,
                        "description": sample.get('description', ''),
                        "created_at": sample.get('created_at', ''),
                        "source": "tail_ad"
                    }
                    all_samples.append(formatted_sample)
        
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


@router.post("/tail-ad-samples")
async def add_tail_ad_sample(request: dict):
    """添加尾部广告训练样本"""
    logger.info(f"📥 收到尾部数据提交请求 - 请求数据键: {list(request.keys()) if request else 'None'}")
    try:
        # 提取参数
        description = request.get("description", "")
        content = request.get("content", "")
        separator = request.get("separator", "")
        normal_part = request.get("normalPart", "")
        ad_part = request.get("adPart", "")
        
        logger.debug(f"提取的参数 - 内容长度: {len(content) if content else 0}, 分隔符: '{separator[:20]}...', 描述: '{description[:30]}...'")
        logger.debug(f"正常部分长度: {len(normal_part) if normal_part else 0}, 广告部分长度: {len(ad_part) if ad_part else 0}")
        
        if not content:
            logger.warning("❌ 参数验证失败 - 内容为空")
            return {"success": False, "error": "内容不能为空"}
        
        # 对于纯广告样本（没有分隔符的情况），separator可以为空
        
        # 加载现有样本
        samples = []
        if TAIL_AD_SAMPLES_FILE.exists():
            logger.debug(f"加载现有样本文件: {TAIL_AD_SAMPLES_FILE}")
            with open(TAIL_AD_SAMPLES_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                samples = data.get("samples", [])
                logger.debug(f"当前样本数量: {len(samples)}")
        else:
            logger.debug("样本文件不存在，创建新文件")
        
        # 生成ID
        new_id = max([s.get('id', 0) for s in samples], default=0) + 1
        
        # 创建新样本
        new_sample = {
            "id": new_id,
            "description": description,
            "content": content,
            "separator": separator,
            "normal_part": normal_part,
            "ad_part": ad_part,
            "content_hash": hashlib.md5(content.encode()).hexdigest(),
            "created_at": datetime.now().isoformat()
        }
        
        # 检查重复
        for sample in samples:
            if sample.get("content_hash") == new_sample["content_hash"]:
                logger.warning(f"❌ 检测到重复样本 - hash: {new_sample['content_hash'][:8]}...")
                return {"success": False, "error": "样本已存在"}
        
        # 添加样本
        samples.append(new_sample)
        logger.debug(f"➕ 添加新样本 - ID: {new_id}, 总数量: {len(samples)}")
        
        # 保存到文件
        logger.debug(f"保存数据到文件: {TAIL_AD_SAMPLES_FILE}")
        with open(TAIL_AD_SAMPLES_FILE, 'w', encoding='utf-8') as f:
            json.dump({
                "samples": samples,
                "updated_at": datetime.now().isoformat()
            }, f, ensure_ascii=False, indent=2)
        logger.debug("✅ 文件保存成功")
        
        # 同时添加到广告样本库用于AI学习
        if ad_part:
            logger.debug(f"添加广告部分到AI学习库 - 长度: {len(ad_part)}")
            await adaptive_learning.add_ad_sample_to_file(ad_part)
        else:
            logger.warning("广告部分为空，跳过AI学习库添加")
        
        logger.info(f"✅ 成功添加新的尾部广告样本: ID={new_id}, 内容长度={len(content)}, 广告长度={len(ad_part)}")
        return {"success": True, "message": "样本已添加", "id": new_id}
        
    except Exception as e:
        logger.error(f"❌ 添加尾部广告样本失败: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@router.delete("/tail-ad-samples/{sample_id}")
async def delete_tail_ad_sample(sample_id: int):
    """删除尾部广告训练样本"""
    try:
        # 加载样本
        if not TAIL_AD_SAMPLES_FILE.exists():
            return {"success": False, "error": "样本文件不存在"}
        
        with open(TAIL_AD_SAMPLES_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            samples = data.get("samples", [])
        
        # 查找并删除
        original_count = len(samples)
        samples = [s for s in samples if s.get('id') != sample_id]
        
        if len(samples) == original_count:
            return {"success": False, "error": "样本不存在"}
        
        # 保存
        with open(TAIL_AD_SAMPLES_FILE, 'w', encoding='utf-8') as f:
            json.dump({
                "samples": samples,
                "updated_at": datetime.now().isoformat()
            }, f, ensure_ascii=False, indent=2)
        
        logger.info(f"删除尾部广告样本: {sample_id}")
        return {"success": True, "message": "样本已删除"}
        
    except Exception as e:
        logger.error(f"删除尾部广告样本失败: {e}")
        return {"success": False, "error": str(e)}


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