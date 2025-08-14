"""
训练数据管理API路由 - 基于JSON文件存储
"""
from fastapi import APIRouter, HTTPException
from datetime import datetime, timedelta
from typing import List, Dict, Any
from pydantic import BaseModel
import logging
import json
import hashlib
from pathlib import Path

from app.core.training_config import TrainingDataConfig
from app.utils.safe_file_ops import SafeFileOperation

logger = logging.getLogger(__name__)

router = APIRouter(tags=["training"])

# 使用训练配置管理文件路径
TRAINING_DATA_FILE = TrainingDataConfig.MANUAL_TRAINING_FILE
TRAINING_HISTORY_FILE = TrainingDataConfig.TRAINING_HISTORY_FILE

# 确保目录存在
TrainingDataConfig.ensure_directories()

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
            ai_filter.save_patterns(str(TrainingDataConfig.AI_FILTER_PATTERNS_FILE))
            
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