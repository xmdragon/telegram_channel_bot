"""
尾部过滤管理模块 - 尾部过滤样本的CRUD和去重功能
"""
from fastapi import APIRouter, HTTPException
from datetime import datetime
from typing import List, Dict, Any
import logging
import hashlib

from .base import (
    TailFilterSample, load_tail_filter_samples, save_tail_filter_samples,
    generate_sample_id, validate_sample_data, calculate_statistics,
    handle_api_error, validate_pagination_params,
    paginate_data
)
from app.core.route_config import ROUTES

logger = logging.getLogger(__name__)
router = APIRouter(tags=["training-tail-filter"])

@router.get(ROUTES.training.tail_filter_statistics)
async def get_tail_filter_statistics():
    """获取尾部过滤统计信息"""
    try:
        samples = load_tail_filter_samples()
        
        # 计算统计数据
        total_samples = len(samples)
        valid_samples = len([s for s in samples if s.get('tail_part')])
        samples_with_separator = len([s for s in samples if s.get('tail_part', '') and any(
            char in s.get('tail_part', '') for char in ['━', '═', '─', '▬', '-', '=', '*', '🔔', '🔗', '☎️', '♾', '😀', '⚡', '📱', '📣', '👌']
        )])
        
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
            "valid_samples": valid_samples,
            "samples_with_separator": samples_with_separator,
            "today_added": today_added
        }
    except Exception as e:
        logger.error(f"获取尾部过滤统计失败: {e}")
        return {
            "success": False,
            "total_samples": 0,
            "valid_samples": 0,
            "samples_with_separator": 0,
            "today_added": 0
        }

@router.get(ROUTES.training.tail_filter_history)
async def get_tail_filter_history(limit: int = 20):
    """获取尾部过滤历史记录"""
    try:
        from .base import load_training_data  # 引用基础训练数据
        samples = load_training_data()
        
        # 获取最近N条记录，按创建时间排序
        sorted_samples = sorted(
            samples, 
            key=lambda x: x.get('created_at', ''), 
            reverse=True
        )[:limit]
        
        history = []
        for sample in sorted_samples:
            history.append({
                "id": sample.get('id', ''),
                "channel_id": sample.get('channel_id', ''),
                "channel_name": sample.get('channel_name', '未知频道'),
                "tail_length": len(sample.get('tail_content', '')),
                "created_at": sample.get('created_at')
            })
        
        return {"success": True, "history": history}
    except Exception as e:
        logger.error(f"获取尾部过滤历史失败: {e}")
        return {"success": False, "history": []}

@router.get(ROUTES.training.tail_filter_samples)
async def get_tail_filter_samples(page: int = 1, page_size: int = 20):
    """获取尾部过滤训练样本列表"""
    try:
        samples = load_tail_filter_samples()
        
        # 格式化样本数据以匹配前端期望的格式
        formatted_samples = []
        for sample in samples:
            # 原始数据格式兼容处理
            content = sample.get('content', sample.get('original_message', ''))
            tail_content = sample.get('tail_part', '')
            
            # 统一使用tail_part字段
            formatted_samples.append({
                "id": sample.get('id', ''),
                "content": content,
                "tail_part": tail_content,  # 统一使用tail_part字段
                "separator": sample.get('separator', ''),
                "normal_part": sample.get('normal_part', ''),
                "created_at": sample.get('created_at', ''),
                "channel_id": sample.get('channel_id', 'unknown'),
                "channel_name": sample.get('channel_name', '历史数据'),
                "is_applied": sample.get('is_applied', True)  # 历史数据默认已应用
            })
        
        # 应用分页
        page, page_size = validate_pagination_params(page, page_size)
        paginated_result = paginate_data(formatted_samples, page, page_size)
        
        return {
            "success": True,
            "samples": paginated_result['items'],
            "total": paginated_result['total'],
            "page": paginated_result['page'],
            "page_size": paginated_result['page_size'],
            "total_pages": paginated_result['total_pages']
        }
    except Exception as e:
        logger.error(f"获取尾部过滤训练样本失败: {e}")
        return {
            "success": False,
            "samples": [],
            "total": 0,
            "page": page,
            "page_size": page_size,
            "total_pages": 0
        }

@router.post(ROUTES.training.tail_filter_samples)
async def add_tail_filter_sample(request: dict):
    """添加尾部过滤训练样本"""
    try:
        # 提取参数
        content = request.get("content", "")
        separator = request.get("separator", "")
        normal_part = request.get("normalPart", "")
        tail_part = request.get("tailPart", "")
        message_id = request.get("message_id")
        
        logger.info(f"收到尾部过滤训练样本: 内容长度={len(content)}, 尾部长度={len(tail_part)}")
        
        if not content or not tail_part:
            return {"success": False, "message": "内容和尾部内容不能为空"}
        
        samples = load_tail_filter_samples()
        
        # 生成新的ID
        new_id = max([s.get('id', 0) for s in samples], default=0) + 1
        
        # 创建新样本
        new_sample = {
            "id": new_id,
            "channel_id": "general",  # 通用样本，不限制频道
            "channel_name": "通用训练样本",
            "content": content,  # 使用content字段（兼容原格式）
            "tail_content": tail_part,
            "tail_part": tail_part,  # 同时保存为tail_part
            "separator": separator,
            "normal_part": normal_part,
            "content_hash": hashlib.md5(content.encode()).hexdigest(),
            "is_applied": True,  # 立即标记为已应用
            "created_by": 'manual',
            "created_at": datetime.now().isoformat(),
            "message_id": message_id
        }
        
        # 检查重复
        existing_sample = None
        for sample in samples:
            existing_hash = sample.get('content_hash')
            if not existing_hash and sample.get('content'):
                # 为历史数据生成哈希
                existing_hash = hashlib.md5(sample.get('content', '').encode()).hexdigest()
            if existing_hash == new_sample['content_hash']:
                existing_sample = sample
                break
        
        if existing_sample:
            # 样本已存在，但仍然返回成功，只是不添加重复样本
            logger.info(f"尾部过滤训练样本已存在，跳过添加: {existing_sample.get('id')}")
            sample_id = existing_sample.get('id')
        else:
            # 添加新样本
            samples.append(new_sample)
            if not save_tail_filter_samples(samples):
                raise HTTPException(status_code=500, detail="保存样本失败")
            sample_id = new_id
            logger.info(f"新尾部过滤训练样本已保存: {sample_id}")
        
        # 如果有message_id，自动重新过滤该消息（无论是否重复）
        if message_id:
            try:
                from app.services.message_processor import MessageProcessor
                message_processor = MessageProcessor()
                
                # 解析消息ID
                if ':' in message_id:
                    channel_id, msg_id = message_id.split(':', 1)
                    success = await message_processor.refilter_message(channel_id, int(msg_id))
                    if success:
                        logger.info(f"成功重新过滤消息: {message_id}")
                        if existing_sample:
                            return {"success": True, "message": "训练样本已存在，消息重新过滤成功", "id": sample_id}
                        else:
                            return {"success": True, "message": "训练样本已提交并自动应用到消息", "id": sample_id}
                    else:
                        logger.warning(f"重新过滤消息失败: {message_id}")
                        if existing_sample:
                            return {"success": True, "message": "训练样本已存在，但重新过滤失败，请手动重新过滤", "id": sample_id}
                        else:
                            return {"success": True, "message": "训练样本已提交，但重新过滤失败，请手动重新过滤", "id": sample_id}
            except Exception as filter_error:
                logger.error(f"自动重新过滤失败: {filter_error}")
                if existing_sample:
                    return {"success": True, "message": "训练样本已存在，但自动应用失败，请手动重新过滤", "id": sample_id}
                else:
                    return {"success": True, "message": "训练样本已提交，但自动应用失败，请手动重新过滤", "id": sample_id}
        
        # 返回成功，提供适当的消息
        if existing_sample:
            logger.info(f"尾部过滤训练样本已存在: ID={sample_id}")
            return {"success": True, "message": "训练样本已存在，数据保存成功", "id": sample_id}
        else:
            logger.info(f"成功添加尾部过滤训练样本: ID={sample_id}")
            return {"success": True, "message": "训练样本已提交", "id": sample_id}
            
    except Exception as e:
        raise handle_api_error(e, "添加尾部过滤训练样本")

@router.put(ROUTES.training.tail_filter_samples_by_id)
async def update_tail_filter_sample(sample_id: int, request: dict):
    """更新尾部过滤训练样本"""
    try:
        # 验证参数 - 支持新旧字段名
        tail_content = request.get('tail_content') or request.get('tail_part', '')
        tail_content = tail_content.strip()
        
        if not tail_content:
            return {"success": False, "message": "尾部内容不能为空"}
        
        # 加载样本
        samples = load_tail_filter_samples()
        
        # 查找样本并更新
        sample_found = False
        for sample in samples:
            if sample.get('id') == sample_id:
                # 更新样本数据 - 直接存储到tail_part
                sample['tail_part'] = tail_content
                sample['updated_at'] = datetime.now().isoformat()
                # 清除旧的tail_content字段（如果存在）
                if 'tail_content' in sample:
                    del sample['tail_content']
                sample_found = True
                break
        
        if not sample_found:
            return {"success": False, "message": "样本不存在"}
        
        # 保存更新后的数据
        if not save_tail_filter_samples(samples):
            raise HTTPException(status_code=500, detail="保存数据失败")
        
        
        logger.info(f"成功更新尾部过滤样本: {sample_id}")
        return {"success": True, "message": "样本已更新"}
        
    except Exception as e:
        logger.error(f"更新尾部过滤样本失败: {e}")
        return {"success": False, "message": str(e)}

@router.delete(ROUTES.training.tail_filter_samples_by_id)
async def delete_tail_filter_sample(sample_id: int):
    """删除尾部过滤训练样本"""
    try:
        samples = load_tail_filter_samples()
        
        # 查找并删除样本
        original_count = len(samples)
        sample_to_delete = None
        for sample in samples:
            if sample.get('id') == sample_id:
                sample_to_delete = sample
                break
        
        if not sample_to_delete:
            return {"success": False, "message": "训练样本不存在"}
        
        samples = [s for s in samples if s.get('id') != sample_id]
        
        # 保存更新后的数据
        if not save_tail_filter_samples(samples):
            raise HTTPException(status_code=500, detail="保存数据失败")
        
        
        return {"success": True, "message": "删除成功"}
    except Exception as e:
        raise handle_api_error(e, "删除尾部过滤训练样本")

@router.post(ROUTES.training.tail_filter_detect_duplicates)
async def detect_tail_filter_duplicates():
    """检测尾部过滤样本中的重复项"""
    try:
        logger.info("开始检测尾部过滤样本重复项...")
        
        # 加载所有样本
        samples = load_tail_filter_samples()
        logger.info(f"加载了 {len(samples)} 个尾部过滤样本进行重复检测")
        
        if len(samples) == 0:
            logger.info("没有样本数据，跳过重复检测")
            return {
                "success": True,
                "groups": [],
                "total_duplicates": 0,
                "total_groups": 0
            }
        
        # 检测重复 - 基于尾部内容相似度
        duplicate_groups = []
        processed = set()
        
        for i, sample1 in enumerate(samples):
            try:
                sample1_id = sample1.get('id', i + 1)
                
                if sample1_id in processed:
                    continue
                    
                group = [sample1]
                content1 = str(sample1.get('tail_part', '')).lower().strip()
                
                # 只有内容不为空才进行比较
                if not content1:
                    continue
                
                logger.debug(f"检查样本 {sample1_id}: '{content1[:50]}...'")
                
                for j, sample2 in enumerate(samples[i+1:], i+1):
                    sample2_id = sample2.get('id', j + 1)
                    
                    if sample2_id in processed:
                        continue
                        
                    content2 = str(sample2.get('tail_part', '')).lower().strip()
                    
                    # 只有内容不为空才进行比较
                    if not content2:
                        continue
                    
                    logger.debug(f"比较样本 {sample1_id} vs {sample2_id}: '{content1[:30]}...' vs '{content2[:30]}...'")
                    
                    # 相似度检测
                    is_duplicate = False
                    if content1 == content2:
                        is_duplicate = True
                        logger.info(f"发现完全匹配: {sample1_id} vs {sample2_id}")
                    elif len(content1) > 20 and len(content2) > 20:
                        # 对于长文本，检查包含关系
                        if content1 in content2 or content2 in content1:
                            is_duplicate = True
                        # 检查高相似度（简单字符匹配）
                        similarity = len(set(content1) & set(content2)) / len(set(content1) | set(content2))
                        if similarity > 0.8:
                            is_duplicate = True
                    
                    if is_duplicate:
                        group.append(sample2)
                        processed.add(sample2_id)
                
                if len(group) > 1:
                    # 计算相似度百分比
                    similarity_percentage = 100  # 默认完全匹配
                    if len(group) > 1:
                        # 简单计算组内平均相似度
                        content1 = str(group[0].get('tail_part', '')).lower().strip()
                        content2 = str(group[1].get('tail_part', '')).lower().strip()
                        if content1 != content2 and content1 and content2:
                            similarity_percentage = int(len(set(content1) & set(content2)) / len(set(content1) | set(content2)) * 100)
                    
                    duplicate_groups.append({
                        "similarity": similarity_percentage,
                        "samples": group,
                        "count": len(group)
                    })
                    for sample in group:
                        sample_id = sample.get('id', samples.index(sample) + 1 if sample in samples else 'unknown')
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
        logger.error(f"检测重复尾部过滤样本失败: {e}", exc_info=True)
        return {
            "success": False,
            "groups": [],
            "total_duplicates": 0,
            "total_groups": 0,
            "error": str(e)
        }

@router.post(ROUTES.training.tail_filter_deduplicate)
async def deduplicate_tail_filter_samples(request: dict):
    """去重尾部过滤样本"""
    try:
        # 获取要删除的样本ID
        remove_ids = request.get("remove_ids", [])
        
        if not remove_ids:
            return {"success": False, "message": "没有指定要删除的重复样本"}
        
        # 加载所有样本
        samples = load_tail_filter_samples()
        
        # 删除指定的样本
        original_count = len(samples)
        samples = [s for s in samples if s.get('id') not in remove_ids]
        deleted_count = original_count - len(samples)
        
        if deleted_count > 0:
            # 保存更新后的数据
            if not save_tail_filter_samples(samples):
                raise HTTPException(status_code=500, detail="保存数据失败")
            
            
            logger.info(f"成功去重，删除了 {deleted_count} 个重复样本")
        
        return {
            "success": True,
            "message": f"去重完成，删除了 {deleted_count} 个重复样本",
            "removed_count": deleted_count
        }
    except Exception as e:
        return handle_api_error(e, "去重尾部过滤样本")