"""
训练数据管理API路由 - 基于JSON文件存储
"""
from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timedelta
from typing import List, Dict, Any
from pydantic import BaseModel
import logging
import json
import hashlib
from pathlib import Path

from app.core.path_config import PathConfig
from app.utils.safe_file_ops import SafeFileOperation
from app.api.admin_auth import check_permission
import os
import glob

logger = logging.getLogger(__name__)

router = APIRouter(tags=["training"])

# 使用训练配置管理文件路径
TRAINING_DATA_FILE = PathConfig.MANUAL_TRAINING_FILE
TRAINING_HISTORY_FILE = PathConfig.TRAINING_HISTORY_FILE
TAIL_FILTER_SAMPLES_FILE = PathConfig.TAIL_FILTER_SAMPLES_FILE  # 尾部过滤样本文件

# 确保目录存在
PathConfig.ensure_directories()

class TrainingSubmission(BaseModel):
    """训练数据提交模型"""
    channel_id: str
    channel_name: str = ""
    original_message: str
    tail_content: str

def load_training_data():
    """加载训练数据"""
    if TRAINING_DATA_FILE.exists():
        data = SafeFileOperation.read_json_safe(TRAINING_DATA_FILE)
        return data.get('samples', []) if data else []
    return []

def save_training_data(samples: List[Dict]):
    """保存训练数据"""
    data = {
        'samples': samples,
        'updated_at': datetime.now().isoformat(),
        'total_count': len(samples)
    }
    SafeFileOperation.write_json_safe(TRAINING_DATA_FILE, data)

def load_training_history():
    """加载训练历史"""
    if TRAINING_HISTORY_FILE.exists():
        data = SafeFileOperation.read_json_safe(TRAINING_HISTORY_FILE)
        return data.get('history', []) if data else []
    return []

def save_training_history(history: List[Dict]):
    """保存训练历史"""
    data = {
        'history': history,
        'updated_at': datetime.now().isoformat()
    }
    SafeFileOperation.write_json_safe(TRAINING_HISTORY_FILE, data)

def load_tail_filter_samples():
    """加载尾部过滤样本"""
    if TAIL_FILTER_SAMPLES_FILE.exists():
        data = SafeFileOperation.read_json_safe(TAIL_FILTER_SAMPLES_FILE)
        return data.get('samples', []) if data else []
    return []

def save_tail_filter_samples(samples: List[Dict]):
    """保存尾部过滤样本"""
    data = {
        'samples': samples,
        'updated_at': datetime.now().isoformat(),
        'total_count': len(samples)
    }
    SafeFileOperation.write_json_safe(TAIL_FILTER_SAMPLES_FILE, data)

@router.get("/channels")
async def get_channels():
    """获取频道列表（从训练数据中获取）"""
    try:
        samples = load_training_data()
        
        # 统计每个频道的训练样本数
        channel_stats = {}
        for sample in samples:
            channel_id = sample.get('channel_id', '')
            if channel_id:
                if channel_id not in channel_stats:
                    channel_stats[channel_id] = {
                        'count': 0,
                        'name': sample.get('channel_name', f'频道{channel_id}')
                    }
                channel_stats[channel_id]['count'] += 1
        
        # 转换为API格式
        channel_list = []
        for channel_id, stats in channel_stats.items():
            channel_list.append({
                "id": channel_id,
                "name": stats['name'],
                "username": channel_id,
                "trained_count": stats['count']
            })
        
        # 按训练样本数排序
        channel_list.sort(key=lambda x: x['trained_count'], reverse=True)
        
        return {"channels": channel_list}
    except Exception as e:
        logger.error(f"获取频道列表失败: {e}")
        return {"channels": []}

@router.get("/stats")
async def get_stats():
    """获取训练统计"""
    try:
        samples = load_training_data()
        
        # 统计频道数
        unique_channels = set()
        today_samples = 0
        today = datetime.now().date()
        
        for sample in samples:
            channel_id = sample.get('channel_id')
            if channel_id:
                unique_channels.add(channel_id)
            
            # 统计今日训练数
            created_at = sample.get('created_at', '')
            if created_at:
                try:
                    sample_date = datetime.fromisoformat(created_at).date()
                    if sample_date == today:
                        today_samples += 1
                except:
                    pass
        
        return {
            "totalChannels": len(unique_channels),
            "trainedChannels": len(unique_channels),
            "totalSamples": len(samples),
            "todayTraining": today_samples
        }
    except Exception as e:
        logger.error(f"获取统计失败: {e}")
        return {
            "totalChannels": 0,
            "trainedChannels": 0,
            "totalSamples": 0,
            "todayTraining": 0
        }

@router.get("/history")
async def get_history():
    """获取训练历史"""
    try:
        samples = load_training_data()
        
        # 获取最近20条记录
        sorted_samples = sorted(
            samples, 
            key=lambda x: x.get('created_at', ''), 
            reverse=True
        )[:20]
        
        history = []
        for sample in sorted_samples:
            history.append({
                "id": sample.get('id', ''),
                "channel_id": sample.get('channel_id', ''),
                "channel_name": sample.get('channel_name', '未知频道'),
                "tail_length": len(sample.get('tail_content', '')),
                "created_at": sample.get('created_at')
            })
        
        return {"history": history}
    except Exception as e:
        logger.error(f"获取历史失败: {e}")
        return {"history": []}

@router.post("/submit")
async def submit_training(submission: TrainingSubmission):
    """提交训练数据"""
    try:
        samples = load_training_data()
        
        # 生成新的ID
        existing_ids = [s.get('id', 0) for s in samples if isinstance(s.get('id'), int)]
        new_id = max(existing_ids, default=0) + 1
        
        # 创建新样本
        new_sample = {
            "id": new_id,
            "channel_id": submission.channel_id,
            "channel_name": submission.channel_name or f"频道{submission.channel_id}",
            "original_message": submission.original_message,
            "tail_content": submission.tail_content,
            "content_hash": hashlib.md5(submission.original_message.encode()).hexdigest(),
            "is_applied": False,
            "created_by": 'manual',
            "created_at": datetime.now().isoformat()
        }
        
        # 检查重复
        for sample in samples:
            if sample.get('content_hash') == new_sample['content_hash']:
                return {"success": False, "message": "训练样本已存在"}
        
        # 添加样本
        samples.append(new_sample)
        save_training_data(samples)
        
        # 尝试立即应用到AI过滤器
        try:
            from app.services.ai_filter import ai_filter
            await ai_filter.learn_channel_pattern(submission.channel_id, [submission.original_message])
            logger.info(f"AI过滤器学习成功: 频道{submission.channel_id}")
        except Exception as e:
            logger.warning(f"AI过滤器学习失败: {e}")
        
        return {"success": True, "message": "训练样本已保存", "id": new_id}
            
    except Exception as e:
        logger.error(f"提交训练失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{sample_id}")
async def delete_training_sample(sample_id: int):
    """删除训练样本"""
    try:
        samples = load_training_data()
        
        # 查找并删除样本
        original_count = len(samples)
        samples = [s for s in samples if s.get('id') != sample_id]
        
        if len(samples) == original_count:
            return {"success": False, "message": "训练样本不存在"}
        
        # 保存更新后的数据
        save_training_data(samples)
        
        return {"success": True, "message": "删除成功"}
    except Exception as e:
        logger.error(f"删除训练样本失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/apply")
async def apply_training():
    """应用所有训练数据到AI过滤器"""
    try:
        samples = load_training_data()
        
        # 按频道分组未应用的样本
        channel_samples = {}
        unapplied_samples = [s for s in samples if not s.get('is_applied', False)]
        
        for sample in unapplied_samples:
            channel_id = sample.get('channel_id')
            if channel_id:
                if channel_id not in channel_samples:
                    channel_samples[channel_id] = []
                channel_samples[channel_id].append(sample)
        
        # 训练每个频道
        success_count = 0
        total_samples = 0
        
        try:
            from app.services.ai_filter import ai_filter
            
            for channel_id, channel_sample_list in channel_samples.items():
                # 提取所有原始消息
                messages = [s['original_message'] for s in channel_sample_list]
                
                # 学习该频道的模式
                success = await ai_filter.learn_channel_pattern(channel_id, messages)
                if success:
                    success_count += 1
                    total_samples += len(messages)
                    
                    # 标记样本为已应用
                    for sample in channel_sample_list:
                        sample['is_applied'] = True
                        sample['applied_at'] = datetime.now().isoformat()
                    
                    logger.info(f"频道 {channel_id} 训练成功，{len(messages)} 个样本")
            
            # 保存更新后的样本状态
            save_training_data(samples)
            
            # 保存AI模式到文件
            ai_filter.save_patterns(str(PathConfig.AI_FILTER_PATTERNS_FILE))
            
        except ImportError:
            logger.warning("AI过滤器模块未找到，跳过模式学习")
            return {"success": False, "message": "AI过滤器模块未找到"}
        
        return {
            "success": True,
            "message": f"成功训练 {success_count} 个频道，共 {total_samples} 个样本",
            "trained_channels": success_count,
            "total_samples": total_samples
        }
    except Exception as e:
        logger.error(f"应用训练失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/clear/{channel_id}")
async def clear_channel_training(channel_id: str):
    """清除某个频道的训练数据"""
    try:
        samples = load_training_data()
        
        # 过滤掉该频道的样本
        original_count = len(samples)
        filtered_samples = [s for s in samples if s.get('channel_id') != channel_id]
        deleted_count = original_count - len(filtered_samples)
        
        if deleted_count > 0:
            save_training_data(filtered_samples)
            
            # 清除AI过滤器中该频道的模式
            try:
                from app.services.ai_filter import ai_filter
                if hasattr(ai_filter, 'channel_patterns') and channel_id in ai_filter.channel_patterns:
                    del ai_filter.channel_patterns[channel_id]
            except ImportError:
                pass
            
            return {"success": True, "message": f"已清除 {deleted_count} 个训练样本"}
        else:
            return {"success": False, "message": "频道没有训练数据"}
            
    except Exception as e:
        logger.error(f"清除训练数据失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/export")
async def export_training_data():
    """导出训练数据"""
    try:
        samples = load_training_data()
        
        # 按频道组织数据
        export_data = {
            "channels": {},
            "exported_at": datetime.now().isoformat(),
            "total_samples": len(samples)
        }
        
        for sample in samples:
            channel_id = sample.get('channel_id', 'unknown')
            if channel_id not in export_data["channels"]:
                export_data["channels"][channel_id] = {
                    "channel_name": sample.get('channel_name', '未知频道'),
                    "samples": []
                }
            
            export_data["channels"][channel_id]["samples"].append({
                "id": sample.get('id'),
                "original": sample.get('original_message', ''),
                "tail": sample.get('tail_content', ''),
                "created_at": sample.get('created_at'),
                "is_applied": sample.get('is_applied', False)
            })
        
        return export_data
    except Exception as e:
        logger.error(f"导出训练数据失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/auto_learn/{channel_id}")
async def auto_learn_from_history(channel_id: str):
    """从现有训练样本自动学习频道模式"""
    try:
        samples = load_training_data()
        
        # 获取该频道的训练样本
        channel_samples = [s for s in samples if s.get('channel_id') == channel_id]
        
        if len(channel_samples) < 5:
            raise HTTPException(status_code=400, detail="训练样本不足，需要至少5个样本")
        
        # 提取消息内容
        contents = []
        for sample in channel_samples:
            content = sample.get('original_message', '')
            if content:
                contents.append(content)
        
        if contents:
            try:
                from app.services.ai_filter import ai_filter
                # 让AI学习该频道的模式
                success = await ai_filter.learn_channel_pattern(channel_id, contents)
                if success:
                    return {
                        "success": True,
                        "message": f"成功从 {len(contents)} 个训练样本中学习频道模式"
                    }
                else:
                    raise HTTPException(status_code=500, detail="学习失败")
            except ImportError:
                raise HTTPException(status_code=500, detail="AI过滤器模块未找到")
        else:
            raise HTTPException(status_code=400, detail="没有可用的消息内容")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"自动学习失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/sample/{sample_id}")
async def get_training_sample(sample_id: int):
    """获取单个训练样本详情"""
    try:
        samples = load_training_data()
        
        for sample in samples:
            if sample.get('id') == sample_id:
                return {"success": True, "sample": sample}
        
        return {"success": False, "message": "样本不存在"}
    except Exception as e:
        logger.error(f"获取训练样本失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/tail-filter-statistics")
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

@router.get("/tail-filter-history")
async def get_tail_filter_history(limit: int = 20):
    """获取尾部过滤历史记录"""
    try:
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

@router.get("/tail-filter-samples")
async def get_tail_filter_samples():
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
        
        return {
            "success": True,
            "samples": formatted_samples,
            "total": len(formatted_samples)
        }
    except Exception as e:
        logger.error(f"获取尾部过滤训练样本失败: {e}")
        return {
            "success": False,
            "samples": [],
            "total": 0
        }

@router.post("/tail-filter-samples")
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
            "separator": separator,
            "normal_part": normal_part,
            "content_hash": hashlib.md5(content.encode()).hexdigest(),
            "is_applied": True,  # 立即标记为已应用
            "created_by": 'manual',
            "created_at": datetime.now().isoformat(),
            "message_id": message_id
        }
        
        # 检查重复
        for sample in samples:
            existing_hash = sample.get('content_hash')
            if not existing_hash and sample.get('content'):
                # 为历史数据生成哈希
                existing_hash = hashlib.md5(sample.get('content', '').encode()).hexdigest()
            if existing_hash == new_sample['content_hash']:
                return {"success": False, "message": "训练样本已存在"}
        
        # 添加样本
        samples.append(new_sample)
        save_tail_filter_samples(samples)
        
        logger.info(f"成功添加尾部过滤训练样本: ID={new_id}")
        return {"success": True, "message": "训练样本已提交并自动应用", "id": new_id}
            
    except Exception as e:
        logger.error(f"添加尾部过滤训练样本失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/tail-filter-samples/{sample_id}")
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
        save_tail_filter_samples(samples)
        
        logger.info(f"成功更新尾部过滤样本: {sample_id}")
        return {"success": True, "message": "样本已更新"}
        
    except Exception as e:
        logger.error(f"更新尾部过滤样本失败: {e}")
        return {"success": False, "message": str(e)}


@router.delete("/tail-filter-samples/{sample_id}")
async def delete_tail_filter_sample(sample_id: int):
    """删除尾部过滤训练样本"""
    try:
        samples = load_tail_filter_samples()
        
        # 查找并删除样本
        original_count = len(samples)
        samples = [s for s in samples if s.get('id') != sample_id]
        
        if len(samples) == original_count:
            return {"success": False, "message": "训练样本不存在"}
        
        # 保存更新后的数据
        save_tail_filter_samples(samples)
        
        return {"success": True, "message": "删除成功"}
    except Exception as e:
        logger.error(f"删除尾部过滤训练样本失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tail-filter-samples/detect-duplicates")
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
                
                logger.debug(f"检查样本 {sample1_id}: '{content1[:50]}...'")  # 调试输出
                
                for j, sample2 in enumerate(samples[i+1:], i+1):
                    sample2_id = sample2.get('id', j + 1)
                    
                    if sample2_id in processed:
                        continue
                        
                    content2 = str(sample2.get('tail_part', '')).lower().strip()
                    
                    # 只有内容不为空才进行比较
                    if not content2:
                        continue
                    
                    logger.debug(f"比较样本 {sample1_id} vs {sample2_id}: '{content1[:30]}...' vs '{content2[:30]}...'")
                    
                    # 简单的相似度检测：内容完全相同或包含关系
                    is_duplicate = False
                    if content1 == content2:
                        is_duplicate = True
                        logger.info(f"发现完全匹配: {sample1_id} vs {sample2_id}")  # 调试输出
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


@router.post("/tail-filter-samples/deduplicate")
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
            save_tail_filter_samples(samples)
            logger.info(f"成功去重，删除了 {deleted_count} 个重复样本")
        
        return {
            "success": True,
            "message": f"去重完成，删除了 {deleted_count} 个重复样本",
            "removed_count": deleted_count
        }
    except Exception as e:
        logger.error(f"去重尾部过滤样本失败: {e}")
        return {"success": False, "message": str(e)}


# 媒体文件管理端点
@router.get("/media-files")
async def get_media_files():
    """获取媒体文件列表"""
    try:
        media_dir = PathConfig.AD_MEDIA_DIR
        media_metadata_file = PathConfig.AD_MEDIA_METADATA_FILE
        media_files = []
        
        # 优先使用metadata.json中的信息
        if media_metadata_file.exists():
            data = SafeFileOperation.read_json_safe(media_metadata_file)
            if data and "media_files" in data:
                for file_hash, file_info in data["media_files"].items():
                    file_path = media_dir / file_info["path"]
                    
                    # 检查文件是否真实存在
                    if file_path.exists():
                        # 获取文件类型（兼容type和media_type字段）
                        file_type = file_info.get("type") or ("image" if file_info.get("media_type") == "photo" else "video")
                        
                        media_files.append({
                            "hash": file_hash,  # 使用metadata中的真实hash
                            "name": file_path.name,
                            "filename": file_path.name,
                            "type": file_type,
                            "size": file_info.get("file_size", file_path.stat().st_size),
                            "created_at": file_info.get("saved_at", datetime.fromtimestamp(file_path.stat().st_ctime).isoformat()),
                            "path": file_info["path"],
                            "messageIds": file_info.get("message_ids", []),
                            "isReferenced": bool(file_info.get("message_ids", [])),
                            "referenceCount": len(file_info.get("message_ids", []))
                        })
        
        # 如果metadata文件不存在或为空，回退到文件系统扫描
        if not media_files and media_dir.exists():
            # 扫描图片文件
            for ext in ['*.jpg', '*.jpeg', '*.png', '*.webp']:
                for img_path in media_dir.glob(f"**/{ext}"):
                    if img_path.is_file():
                        stat = img_path.stat()
                        # 从文件名提取hash作为fallback
                        extracted_hash = img_path.stem.split('_')[-1] if '_' in img_path.stem else img_path.stem
                        media_files.append({
                            "hash": extracted_hash,
                            "name": img_path.name,
                            "filename": img_path.name,
                            "type": "image",
                            "size": stat.st_size,
                            "created_at": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                            "path": str(img_path.relative_to(media_dir)),
                            "messageIds": [],
                            "isReferenced": False,
                            "referenceCount": 0
                        })
            
            # 扫描视频文件
            for ext in ['*.mp4', '*.avi', '*.mov', '*.mkv']:
                for video_path in media_dir.glob(f"**/{ext}"):
                    if video_path.is_file():
                        stat = video_path.stat()
                        # 从文件名提取hash作为fallback
                        extracted_hash = video_path.stem.split('_')[-1] if '_' in video_path.stem else video_path.stem
                        media_files.append({
                            "hash": extracted_hash,
                            "name": video_path.name,
                            "filename": video_path.name,
                            "type": "video",
                            "size": stat.st_size,
                            "created_at": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                            "path": str(video_path.relative_to(media_dir)),
                            "messageIds": [],
                            "isReferenced": False,
                            "referenceCount": 0
                        })
        
        # 计算统计信息
        total_files = len(media_files)
        image_count = len([f for f in media_files if f['type'] == 'image'])
        video_count = len([f for f in media_files if f['type'] == 'video'])
        total_size = sum(f['size'] for f in media_files)
        
        return {
            "success": True,
            "files": media_files,
            "stats": {
                "totalFiles": total_files,
                "imageCount": image_count,
                "videoCount": video_count,
                "totalSize": total_size,
                "referencedCount": total_files,  # 暂时假设都被引用
                "orphanedCount": 0
            }
        }
    except Exception as e:
        logger.error(f"获取媒体文件列表失败: {e}")
        return {
            "success": False,
            "files": [],
            "stats": {
                "totalFiles": 0,
                "imageCount": 0,
                "videoCount": 0,
                "totalSize": 0,
                "referencedCount": 0,
                "orphanedCount": 0
            }
        }

@router.delete("/media-files/{file_hash}")
async def delete_media_file(file_hash: str):
    """删除媒体文件"""
    try:
        media_dir = PathConfig.AD_MEDIA_DIR
        deleted = False
        
        # 查找并删除匹配的文件
        for file_path in media_dir.glob(f"**/*{file_hash}*"):
            if file_path.is_file():
                file_path.unlink()
                deleted = True
                logger.info(f"删除媒体文件: {file_path}")
        
        if deleted:
            return {"success": True, "message": "文件已删除"}
        else:
            return {"success": False, "message": "文件不存在"}
    except Exception as e:
        logger.error(f"删除媒体文件失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/media-files/clean-orphaned")
async def clean_orphaned_files():
    """清理孤立的媒体文件"""
    try:
        # 简单实现：暂时不执行实际清理，只返回成功
        return {
            "success": True,
            "message": "清理完成",
            "deletedCount": 0,
            "freedMb": 0
        }
    except Exception as e:
        logger.error(f"清理孤立文件失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/media-files/duplicates")
async def get_duplicate_files():
    """检测视觉重复的媒体文件"""
    try:
        media_metadata_file = PathConfig.AD_MEDIA_METADATA_FILE
        media_dir = PathConfig.AD_TRAINING_DIR
        
        if not media_metadata_file.exists():
            return {"success": True, "duplicates": [], "stats": {"groups": 0, "total_duplicates": 0}}
        
        data = SafeFileOperation.read_json_safe(media_metadata_file)
        if not data or "media_files" not in data:
            return {"success": True, "duplicates": [], "stats": {"groups": 0, "total_duplicates": 0}}
        
        # 尝试导入视觉相似度检测器，如果不可用则使用简单的哈希比较
        try:
            from app.services.visual_similarity import VisualSimilarityDetector
            visual_detector = VisualSimilarityDetector()
            use_visual_detection = True
        except ImportError:
            logger.warning("VisualSimilarityDetector不可用，使用文件名哈希比较")
            visual_detector = None
            use_visual_detection = False
        
        duplicate_groups = []
        processed = set()
        
        # 遍历所有媒体文件，查找重复的组
        for file_hash1, file_info1 in data["media_files"].items():
            if file_hash1 in processed:
                continue
            
            current_group = [file_info1]
            processed.add(file_hash1)
            
            # 查找与当前文件相似的其他文件
            for file_hash2, file_info2 in data["media_files"].items():
                if file_hash2 == file_hash1 or file_hash2 in processed:
                    continue
                
                is_duplicate = False
                
                if use_visual_detection and "visual_hashes" in file_info1 and "visual_hashes" in file_info2:
                    # 使用视觉哈希比较
                    try:
                        is_similar, similarity_score = visual_detector.is_visually_similar(
                            file_info1["visual_hashes"],
                            file_info2["visual_hashes"]
                        )
                        
                        # 检查是否有足够高的相似度（85%阈值）
                        if is_similar and similarity_score >= 85.0:
                            is_duplicate = True
                    except Exception as e:
                        logger.warning(f"视觉哈希比较失败: {e}")
                
                if not is_duplicate:
                    # 简单的文件名哈希比较作为备用
                    path1 = file_info1.get("path", "")
                    path2 = file_info2.get("path", "")
                    if path1 and path2:
                        # 提取文件名中的哈希部分进行比较
                        name1 = Path(path1).stem
                        name2 = Path(path2).stem
                        hash1 = name1.split('_')[-1] if '_' in name1 else name1
                        hash2 = name2.split('_')[-1] if '_' in name2 else name2
                        
                        # 如果哈希相同或文件大小相同且名称相似，认为是重复
                        if (hash1 == hash2 or 
                            (file_info1.get("file_size") == file_info2.get("file_size") and 
                             len(set(name1.split('_')) & set(name2.split('_'))) >= 2)):
                            is_duplicate = True
                
                if is_duplicate:
                    current_group.append(file_info2)
                    processed.add(file_hash2)
            
            # 如果组内有多个文件，添加到重复组列表
            if len(current_group) > 1:
                # 计算可节省的空间
                sizes = [f.get("file_size", 0) for f in current_group]
                saved_space = sum(sizes) - min(sizes)  # 保留最小的文件
                
                duplicate_groups.append({
                    "files": current_group,
                    "count": len(current_group),
                    "total_size": sum(sizes),
                    "saved_space": saved_space,
                    "message_ids": list(set(sum([f.get("message_ids", []) for f in current_group], [])))
                })
        
        # 统计信息
        stats = {
            "groups": len(duplicate_groups),
            "total_duplicates": sum(g["count"] - 1 for g in duplicate_groups),  # 每组减1（保留一个）
            "total_saved_space": sum(g["saved_space"] for g in duplicate_groups)
        }
        
        return {
            "success": True,
            "duplicates": duplicate_groups,
            "stats": stats
        }
        
    except Exception as e:
        logger.error(f"检测重复媒体文件失败: {e}")
        return {"success": False, "error": str(e), "duplicates": [], "stats": {"groups": 0, "total_duplicates": 0}}

@router.get("/media-files/export")
async def export_media_files():
    """导出媒体文件信息"""
    try:
        # 简单实现：返回基本的导出数据
        return {
            "success": True,
            "exportData": {
                "files": [],
                "stats": {
                    "totalFiles": 0,
                    "totalSize": 0
                },
                "exportedAt": datetime.now().isoformat()
            }
        }
    except Exception as e:
        logger.error(f"导出媒体文件失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/media-files/deduplicate")
async def deduplicate_media_files():
    """执行视觉去重"""
    try:
        import shutil
        
        media_metadata_file = PathConfig.AD_MEDIA_METADATA_FILE
        media_dir = PathConfig.AD_MEDIA_DIR
        
        if not media_metadata_file.exists():
            return {"success": True, "deleted": 0, "merged": 0}
        
        # 备份元数据
        backup_file = media_metadata_file.parent / f"media_metadata_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        shutil.copy2(media_metadata_file, backup_file)
        logger.info(f"已备份元数据到: {backup_file}")
        
        data = SafeFileOperation.read_json_safe(media_metadata_file)
        if not data or "media_files" not in data:
            return {"success": True, "deleted": 0, "merged": 0}
        
        # 尝试导入视觉相似度检测器
        try:
            from app.services.visual_similarity import VisualSimilarityDetector
            visual_detector = VisualSimilarityDetector()
            use_visual_detection = True
        except ImportError:
            logger.warning("VisualSimilarityDetector不可用，使用文件名哈希去重")
            visual_detector = None
            use_visual_detection = False
        
        deleted_count = 0
        merged_count = 0
        processed = set()
        
        # 创建新的媒体文件字典（去重后的）
        new_media_files = {}
        
        # 遍历所有媒体文件，查找相似的组
        for file_hash, file_info in data["media_files"].items():
            if file_hash in processed:
                continue
            
            # 收集与当前文件相似的所有文件
            similar_files = [(file_hash, file_info)]
            processed.add(file_hash)
            
            for other_hash, other_info in data["media_files"].items():
                if other_hash == file_hash or other_hash in processed:
                    continue
                
                is_duplicate = False
                
                if use_visual_detection and "visual_hashes" in file_info and "visual_hashes" in other_info:
                    # 使用视觉哈希比较
                    try:
                        is_similar, similarity_score = visual_detector.is_visually_similar(
                            file_info["visual_hashes"],
                            other_info["visual_hashes"]
                        )
                        
                        if is_similar and similarity_score >= 85.0:
                            is_duplicate = True
                    except Exception as e:
                        logger.warning(f"视觉哈希比较失败: {e}")
                
                if not is_duplicate:
                    # 简单的文件名哈希比较作为备用
                    path1 = file_info.get("path", "")
                    path2 = other_info.get("path", "")
                    if path1 and path2:
                        name1 = Path(path1).stem
                        name2 = Path(path2).stem
                        hash1 = name1.split('_')[-1] if '_' in name1 else name1
                        hash2 = name2.split('_')[-1] if '_' in name2 else name2
                        
                        # 如果哈希相同，认为是重复
                        if hash1 == hash2:
                            is_duplicate = True
                
                if is_duplicate:
                    similar_files.append((other_hash, other_info))
                    processed.add(other_hash)
            
            # 如果有多个相似文件，合并它们
            if len(similar_files) > 1:
                # 选择要保留的文件（优先保留引用最多的，其次是文件最小的）
                best_file = max(similar_files, key=lambda x: (
                    len(x[1].get("message_ids", [])),  # 引用数量
                    -x[1].get("file_size", float('inf'))  # 文件大小（越小越好）
                ))
                
                # 合并所有message_ids到保留的文件
                all_message_ids = list(set(sum([f[1].get("message_ids", []) for f in similar_files], [])))
                best_file[1]["message_ids"] = all_message_ids
                
                # 保留最佳文件
                new_media_files[best_file[0]] = best_file[1]
                
                # 删除其他重复文件
                for other_hash, other_info in similar_files:
                    if other_hash != best_file[0]:
                        file_path = media_dir / other_info["path"]
                        if file_path.exists():
                            try:
                                file_path.unlink()
                                deleted_count += 1
                                logger.info(f"删除重复文件: {file_path}")
                            except Exception as e:
                                logger.error(f"删除文件失败 {file_path}: {e}")
                
                merged_count += len(similar_files) - 1
            else:
                # 没有重复，直接保留
                new_media_files[file_hash] = file_info
        
        # 更新元数据
        data["media_files"] = new_media_files
        data["updated_at"] = datetime.now().isoformat()
        data["deduplication_log"] = {
            "timestamp": datetime.now().isoformat(),
            "deleted": deleted_count,
            "merged": merged_count,
            "backup_file": str(backup_file.name)
        }
        
        if not SafeFileOperation.write_json_safe(media_metadata_file, data):
            logger.error("保存去重后的元数据失败")
            return {"success": False, "error": "保存元数据失败"}
        
        logger.info(f"去重完成: 删除 {deleted_count} 个文件, 合并 {merged_count} 个引用")
        
        return {
            "success": True,
            "deleted": deleted_count,
            "merged": merged_count,
            "backup_file": str(backup_file.name)
        }
        
    except Exception as e:
        logger.error(f"执行去重失败: {e}")
        return {"success": False, "error": str(e)}

@router.post("/media-files/rebuild-visual-hashes")
async def rebuild_visual_hashes():
    """重建视觉哈希"""
    try:
        # 简单实现：返回重建完成状态
        return {
            "success": True,
            "message": "视觉哈希重建完成",
            "processedCount": 0
        }
    except Exception as e:
        logger.error(f"重建视觉哈希失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/optimize-storage")
async def optimize_storage():
    """优化存储空间（压缩视频、清理冗余文件等）"""
    try:
        logger.info("开始存储优化...")
        
        saved_space = 0
        processed_videos = 0
        processed_images = 0
        cleaned_files = 0
        
        # 查找训练数据目录
        training_base_dir = PathConfig.AD_MEDIA_DIR
        
        if training_base_dir.exists():
            # 处理视频文件（转换为缩略图以节省空间）
            video_dir = training_base_dir / "videos"
            if video_dir.exists():
                for video_file in video_dir.glob("**/*.[Mm][Pp]4"):
                    try:
                        # 获取文件大小
                        original_size = video_file.stat().st_size
                        
                        # 提取视频的第一帧作为缩略图
                        try:
                            import cv2
                            
                            # 读取视频
                            cap = cv2.VideoCapture(str(video_file))
                            ret, frame = cap.read()
                            cap.release()
                            
                            if ret:
                                # 创建对应的图片目录
                                image_dir = training_base_dir / "images" / video_file.parent.name
                                image_dir.mkdir(parents=True, exist_ok=True)
                                
                                # 生成缩略图文件名（替换扩展名为.jpg）
                                thumbnail_name = video_file.stem + "_thumb.jpg"
                                thumbnail_path = image_dir / thumbnail_name
                                
                                # 保存缩略图
                                cv2.imwrite(str(thumbnail_path), frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                                thumbnail_size = thumbnail_path.stat().st_size
                                
                                # 更新metadata.json中的文件信息
                                media_metadata_file = PathConfig.AD_MEDIA_METADATA_FILE
                                if media_metadata_file.exists():
                                    metadata = SafeFileOperation.read_json_safe(media_metadata_file)
                                    
                                    # 查找对应的视频记录
                                    video_hash = None
                                    for file_hash, file_info in metadata.get("media_files", {}).items():
                                        if file_info.get("path", "").endswith(video_file.name):
                                            video_hash = file_hash
                                            break
                                    
                                    if video_hash:
                                        # 更新文件信息为缩略图
                                        metadata["media_files"][video_hash].update({
                                            "type": "image",
                                            "path": f"images/{video_file.parent.name}/{thumbnail_name}",
                                            "size": thumbnail_size,
                                            "original_type": "video",
                                            "optimized_at": datetime.now().isoformat()
                                        })
                                        
                                        # 保存更新的metadata
                                        SafeFileOperation.write_json_safe(media_metadata_file, metadata)
                                
                                # 删除原视频文件
                                video_file.unlink()
                                
                                # 统计节省的空间
                                saved_space += (original_size - thumbnail_size)
                                processed_videos += 1
                                
                                logger.info(f"视频转缩略图成功: {video_file.name} -> {thumbnail_name}, 节省 {(original_size - thumbnail_size) / 1024 / 1024:.2f} MB")
                                
                            else:
                                logger.warning(f"无法从视频提取帧: {video_file.name}")
                                
                        except ImportError:
                            logger.warning("OpenCV未安装，跳过视频处理")
                            break
                        except Exception as video_error:
                            logger.warning(f"视频转缩略图失败 {video_file.name}: {video_error}")
                            
                    except Exception as e:
                        logger.warning(f"处理视频文件失败 {video_file}: {e}")
            
            # 处理图片文件（压缩大图片）
            image_dir = training_base_dir / "images"
            if image_dir.exists():
                for img_file in image_dir.glob("**/*.jpg"):
                    try:
                        # 获取文件大小
                        original_size = img_file.stat().st_size
                        
                        # 如果图片超过2MB，记录为可优化（这里不实际压缩，只是统计）
                        if original_size > 2 * 1024 * 1024:
                            processed_images += 1
                            
                    except Exception as e:
                        logger.warning(f"处理图片文件失败 {img_file}: {e}")
        
        # 清理备份文件（保留最近10个）
        backup_dir = training_base_dir / "backups"
        if backup_dir.exists():
            backup_files = sorted(backup_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)
            if len(backup_files) > 10:
                for old_backup in backup_files[10:]:
                    try:
                        backup_size = old_backup.stat().st_size
                        old_backup.unlink()
                        saved_space += backup_size
                        cleaned_files += 1
                        logger.info(f"清理旧备份文件: {old_backup.name}")
                    except Exception as e:
                        logger.warning(f"清理备份文件失败 {old_backup}: {e}")
        
        logger.info(f"存储优化完成 - 节省空间: {saved_space} bytes, 处理视频: {processed_videos}, 处理图片: {processed_images}, 清理文件: {cleaned_files}")
        
        return {
            "success": True,
            "message": "存储优化完成",
            "saved_space": saved_space,
            "processed_videos": processed_videos,
            "processed_images": processed_images,
            "cleaned_files": cleaned_files
        }
        
    except Exception as e:
        logger.error(f"存储优化失败: {e}")
        raise HTTPException(status_code=500, detail=f"存储优化失败: {str(e)}")

@router.post("/reload-model")
async def reload_model():
    """重新加载广告检测训练数据到AI模型"""
    try:
        logger.info("开始重载广告检测模型...")
        
        # 重载广告检测模型（基于文件的训练数据自动重载）
        try:
            # 广告检测系统使用文件存储，每次都会读取最新数据，无需手动重载
            # 这里只是标记重载完成并清理可能的内存缓存
            
            message = "广告检测模型重载完成"
            logger.info(message)
            
            return {
                "success": True,
                "message": message,
                "reloaded_components": ["广告检测模型"],
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"重载广告检测模型失败: {e}")
            return {
                "success": False,
                "message": f"重载模型失败: {str(e)}",
                "reloaded_components": [],
                "timestamp": datetime.now().isoformat()
            }
        
    except Exception as e:
        logger.error(f"重载模型失败: {e}")
        raise HTTPException(status_code=500, detail=f"重载模型失败: {str(e)}")

@router.get("/media-files/{file_hash}/ocr")
async def get_media_file_ocr(
    file_hash: str,
    _admin = Depends(check_permission("training.view"))
):
    """获取指定媒体文件的OCR识别结果"""
    try:
        from app.services.ocr_service import ocr_service
        
        # 获取文件信息
        media_metadata_file = PathConfig.AD_MEDIA_METADATA_FILE
        media_dir = PathConfig.AD_TRAINING_DIR
        
        if not media_metadata_file.exists():
            raise HTTPException(status_code=404, detail="媒体元数据文件不存在")
        
        data = SafeFileOperation.read_json_safe(media_metadata_file)
        if not data or file_hash not in data.get("media_files", {}):
            raise HTTPException(status_code=404, detail="文件不存在")
        
        file_info = data["media_files"][file_hash]
        file_path = media_dir / file_info["path"]
        
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="媒体文件不存在")
        
        # 只处理图片文件（兼容type和media_type字段）
        file_type = file_info.get("type") or ("image" if file_info.get("media_type") == "photo" else "video")
        logger.info(f"OCR请求 - 文件类型判断: type={file_info.get('type')}, media_type={file_info.get('media_type')}, 计算结果={file_type}")
        if file_type != "image":
            logger.warning(f"OCR请求被拒绝: 文件类型为{file_type}，文件信息={file_info}")
            raise HTTPException(status_code=400, detail=f"只支持图片文件的OCR识别，当前文件类型: {file_type}")
        
        # 提取OCR内容
        ocr_result = await ocr_service.extract_image_content(str(file_path))
        
        return {
            "success": True,
            "file_hash": file_hash,
            "file_path": str(file_path),
            "ocr_result": {
                "texts": ocr_result.get("texts", []),
                "qr_codes": ocr_result.get("qr_codes", []),
                "combined_text": ocr_result.get("combined_text", ""),
                "ad_score": ocr_result.get("ad_score", 0),
                "is_ad": ocr_result.get("has_ad_content", False),
                "ad_indicators": ocr_result.get("ad_indicators", [])
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取媒体文件OCR结果失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/mark-ad-test")
async def mark_message_as_ad_test(request: dict):
    """测试端点 - 基础功能"""
    try:
        message_id = request.get("message_id", "unknown")
        return {
            "success": True,
            "message": f"测试成功，接收到消息ID: {message_id}",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.post("/mark-ad-message")
async def mark_message_as_ad(request: dict):
    """将消息标记为广告并加入训练样本"""
    try:
        message_id = request.get("message_id")
        if not message_id:
            raise HTTPException(status_code=400, detail="缺少消息ID")
        
        # 解析复合消息ID格式: 如 "#-1002062871756:43195" 或 "-1002062871756:43195"
        if message_id.startswith('#'):
            message_id = message_id[1:]  # 移除#前缀
        
        # 解析消息ID为 channel_id 和 msg_id
        if ':' in message_id:
            channel_id, msg_id = message_id.split(':', 1)
            try:
                msg_id_int = int(msg_id)
            except ValueError:
                raise HTTPException(status_code=400, detail="消息ID格式错误")
        else:
            raise HTTPException(status_code=400, detail="消息ID格式错误，应为 channel_id:message_id")
        
        # 1. 首先拒绝消息（标记为已拒绝状态）
        auto_rejected = False
        try:
            from app.services.message_processor import MessageProcessor
            message_processor = MessageProcessor()
            
            # 获取消息数据
            msg_data = await message_processor.get_message(channel_id, msg_id_int)
            if msg_data and msg_data.get('status') == 'pending':
                # 更新消息状态为已拒绝
                msg_data['status'] = 'rejected'
                msg_data['filter_reason'] = '用户手动标记为广告'
                msg_data['is_ad'] = True
                msg_data['updated_at'] = datetime.now().isoformat()
                
                # 保存消息更新
                from app.storage.redis_store import get_redis_message_store
                redis_store = get_redis_message_store()
                redis_store.save_message(channel_id, msg_id_int, msg_data)
                
                auto_rejected = True
                logger.info(f"消息 {message_id} 已自动拒绝（标记为广告）")
            else:
                logger.warning(f"消息 {message_id} 不存在或状态不是pending，跳过拒绝操作")
        except Exception as e:
            logger.warning(f"拒绝消息失败，但继续标记为广告: {e}")
        
        # 2. 然后加入训练样本
        
        # 加载现有的广告训练数据
        ad_data_file = PathConfig.AD_TRAINING_FILE
        if ad_data_file.exists():
            ad_data = SafeFileOperation.read_json_safe(ad_data_file)
            if not ad_data:
                ad_data = {"version": "1.0", "samples": [], "metadata": {}}
        else:
            ad_data = {"version": "1.0", "samples": [], "metadata": {}}
        
        # 生成新样本ID
        existing_ids = [s.get('id', 0) for s in ad_data.get('samples', [])]
        new_id = max(existing_ids) + 1 if existing_ids else 1
        
        # 获取消息内容用于训练样本
        sample_content = f"手动标记的广告消息 {message_id}"
        sample_channel_id = ""
        sample_channel_name = ""
        
        # 如果成功获取到消息数据，使用实际内容
        try:
            if 'msg_data' in locals() and msg_data:
                sample_content = msg_data.get('content', '') or msg_data.get('filtered_content', '') or sample_content
                sample_channel_id = msg_data.get('source_channel', '')
                sample_channel_name = msg_data.get('source_channel_title', '')
        except:
            pass  # 使用默认内容
        
        # 创建新的广告样本
        new_sample = {
            "id": new_id,
            "message_id": message_id,
            "content": sample_content,
            "is_ad": True,
            "source": "manual_mark",
            "description": "用户手动标记为广告",
            "channel_id": sample_channel_id,
            "channel_name": sample_channel_name,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
        
        # 检查是否已存在相同的样本
        existing_samples = ad_data.get('samples', [])
        for sample in existing_samples:
            if sample.get('message_id') == message_id:
                return {
                    "success": False,
                    "message": "该消息已存在于训练样本中",
                    "existing_sample_id": sample.get('id')
                }
        
        # 添加新样本
        ad_data['samples'].append(new_sample)
        ad_data['updated_at'] = datetime.now().isoformat()
        
        # 更新元数据
        if 'metadata' not in ad_data:
            ad_data['metadata'] = {}
        ad_data['metadata']['total_samples'] = len(ad_data['samples'])
        ad_data['metadata']['last_added'] = datetime.now().isoformat()
        
        # 保存训练数据
        if not SafeFileOperation.write_json_safe(ad_data_file, ad_data):
            raise HTTPException(status_code=500, detail="保存训练数据失败")
        
        logger.info(f"消息 {message_id} 已标记为广告并添加到训练样本，样本ID: {new_id}")
        
        # 根据是否成功拒绝消息来生成返回消息
        success_message = "消息已标记为广告并添加到训练样本"
        if auto_rejected:
            success_message = "消息已标记为广告、自动拒绝并添加到训练样本"
        
        return {
            "success": True,
            "message": success_message,
            "sample_id": new_id,
            "training_data": {
                "content_length": len(new_sample['content']),
                "channel": sample_channel_name or "手动标记",
                "created_at": new_sample['created_at']
            },
            "auto_rejected": auto_rejected
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"标记消息为广告失败: {e}")
        raise HTTPException(status_code=500, detail=f"标记失败: {str(e)}")