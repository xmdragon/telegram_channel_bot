"""
手动训练API路由 - 数据库版本
"""
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, desc
from datetime import datetime, timedelta
from typing import List, Dict, Any
from pydantic import BaseModel
import logging

from app.core.database import get_db, Channel, Message, AITrainingSample
from app.services.ai_filter import ai_filter
from app.core.training_config import TrainingDataConfig

logger = logging.getLogger(__name__)

router = APIRouter(tags=["training"])

class TrainingSubmission(BaseModel):
    """训练数据提交模型"""
    channel_id: str
    original_message: str
    tail_content: str

@router.get("/channels")
async def get_channels(db: AsyncSession = Depends(get_db)):
    """获取所有频道列表"""
    try:
        # 获取所有源频道
        result = await db.execute(
            select(Channel).where(
                and_(
                    Channel.channel_type == 'source',
                    Channel.is_active == True
                )
            ).order_by(Channel.channel_name)
        )
        channels = result.scalars().all()
        
        # 统计每个频道的训练样本数
        channel_list = []
        for channel in channels:
            # 统计该频道的训练样本数
            count_result = await db.execute(
                select(func.count(AITrainingSample.id)).where(
                    AITrainingSample.channel_id == channel.channel_id
                )
            )
            sample_count = count_result.scalar() or 0
            
            channel_list.append({
                "id": channel.channel_id,
                "name": channel.channel_name or channel.channel_title or "未命名频道",
                "username": channel.channel_id,
                "trained_count": sample_count
            })
        
        return {"channels": channel_list}
    except Exception as e:
        logger.error(f"获取频道列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/stats")
async def get_stats(db: AsyncSession = Depends(get_db)):
    """获取训练统计"""
    try:
        # 总频道数
        total_channels_result = await db.execute(
            select(func.count(Channel.id)).where(
                and_(
                    Channel.channel_type == 'source',
                    Channel.is_active == True
                )
            )
        )
        total_channels = total_channels_result.scalar() or 0
        
        # 已训练频道数（有训练样本的频道）
        trained_channels_result = await db.execute(
            select(func.count(func.distinct(AITrainingSample.channel_id)))
        )
        trained_channels = trained_channels_result.scalar() or 0
        
        # 总训练样本数
        total_samples_result = await db.execute(
            select(func.count(AITrainingSample.id))
        )
        total_samples = total_samples_result.scalar() or 0
        
        # 今日训练数
        today = datetime.now().date()
        today_start = datetime.combine(today, datetime.min.time())
        today_training_result = await db.execute(
            select(func.count(AITrainingSample.id)).where(
                AITrainingSample.created_at >= today_start
            )
        )
        today_training = today_training_result.scalar() or 0
        
        return {
            "totalChannels": total_channels,
            "trainedChannels": trained_channels,
            "totalSamples": total_samples,
            "todayTraining": today_training
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
async def get_history(db: AsyncSession = Depends(get_db)):
    """获取训练历史"""
    try:
        # 获取最近20条训练记录
        result = await db.execute(
            select(AITrainingSample).order_by(
                desc(AITrainingSample.created_at)
            ).limit(20)
        )
        samples = result.scalars().all()
        
        history = []
        for sample in samples:
            history.append({
                "id": sample.id,
                "channel_id": sample.channel_id,
                "channel_name": sample.channel_name or "未知频道",
                "tail_length": len(sample.tail_content),
                "created_at": sample.created_at.isoformat() if sample.created_at else None
            })
        
        return {"history": history}
    except Exception as e:
        logger.error(f"获取历史失败: {e}")
        return {"history": []}

@router.post("/submit")
async def submit_training(
    submission: TrainingSubmission,
    db: AsyncSession = Depends(get_db)
):
    """提交训练数据"""
    try:
        # 获取频道信息
        result = await db.execute(
            select(Channel).where(Channel.channel_id == submission.channel_id)
        )
        channel = result.scalar_one_or_none()
        
        if not channel:
            raise HTTPException(status_code=404, detail="频道不存在")
        
        channel_name = channel.channel_name or channel.channel_title or "未命名频道"
        
        # 创建训练样本
        training_sample = AITrainingSample(
            channel_id=submission.channel_id,
            channel_name=channel_name,
            original_message=submission.original_message,
            tail_content=submission.tail_content,
            is_applied=False,
            created_by='manual'
        )
        
        db.add(training_sample)
        await db.commit()
        
        # 立即应用到当前运行的AI过滤器
        samples = [submission.original_message]
        await ai_filter.learn_channel_pattern(submission.channel_id, samples)
        
        return {"success": True, "message": "训练样本已保存"}
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"提交训练失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{sample_id}")
async def delete_training_sample(sample_id: int, db: AsyncSession = Depends(get_db)):
    """删除训练样本"""
    try:
        # 查找样本
        result = await db.execute(
            select(AITrainingSample).where(AITrainingSample.id == sample_id)
        )
        sample = result.scalar_one_or_none()
        
        if not sample:
            return {"success": False, "message": "训练样本不存在"}
        
        # 删除样本
        await db.delete(sample)
        await db.commit()
        
        return {"success": True, "message": "删除成功"}
    except Exception as e:
        await db.rollback()
        logger.error(f"删除训练样本失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/apply")
async def apply_training(db: AsyncSession = Depends(get_db)):
    """应用所有训练数据"""
    try:
        # 获取所有未应用的训练样本，按频道分组
        result = await db.execute(
            select(AITrainingSample).where(
                AITrainingSample.is_applied == False
            ).order_by(AITrainingSample.channel_id)
        )
        samples = result.scalars().all()
        
        # 按频道分组
        channel_samples = {}
        for sample in samples:
            if sample.channel_id not in channel_samples:
                channel_samples[sample.channel_id] = []
            channel_samples[sample.channel_id].append(sample)
        
        # 训练每个频道
        success_count = 0
        total_samples = 0
        
        for channel_id, channel_sample_list in channel_samples.items():
            # 提取所有原始消息
            messages = [s.original_message for s in channel_sample_list]
            
            # 学习该频道的模式
            success = await ai_filter.learn_channel_pattern(channel_id, messages)
            if success:
                success_count += 1
                total_samples += len(messages)
                
                # 标记样本为已应用
                for sample in channel_sample_list:
                    sample.is_applied = True
                
                logger.info(f"频道 {channel_id} 训练成功，{len(messages)} 个样本")
        
        # 提交数据库更改
        await db.commit()
        
        # 保存AI模式到文件（作为备份）
        ai_filter.save_patterns(str(TrainingDataConfig.AI_FILTER_PATTERNS_FILE))
        
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
async def clear_channel_training(
    channel_id: str,
    db: AsyncSession = Depends(get_db)
):
    """清除某个频道的训练数据"""
    try:
        # 删除该频道的所有训练样本
        result = await db.execute(
            select(AITrainingSample).where(
                AITrainingSample.channel_id == channel_id
            )
        )
        samples = result.scalars().all()
        
        if samples:
            for sample in samples:
                await db.delete(sample)
            await db.commit()
            
            # 清除AI过滤器中该频道的模式
            if channel_id in ai_filter.channel_patterns:
                del ai_filter.channel_patterns[channel_id]
            
            return {"success": True, "message": f"已清除 {len(samples)} 个训练样本"}
        else:
            return {"success": False, "message": "频道没有训练数据"}
            
    except Exception as e:
        logger.error(f"清除训练数据失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/export")
async def export_training_data(db: AsyncSession = Depends(get_db)):
    """导出训练数据"""
    try:
        # 获取所有训练样本
        result = await db.execute(
            select(AITrainingSample).order_by(
                AITrainingSample.channel_id,
                AITrainingSample.created_at
            )
        )
        samples = result.scalars().all()
        
        # 按频道组织数据
        export_data = {
            "channels": {},
            "exported_at": datetime.now().isoformat(),
            "total_samples": len(samples)
        }
        
        for sample in samples:
            if sample.channel_id not in export_data["channels"]:
                export_data["channels"][sample.channel_id] = {
                    "channel_name": sample.channel_name,
                    "samples": []
                }
            
            export_data["channels"][sample.channel_id]["samples"].append({
                "original": sample.original_message,
                "tail": sample.tail_content,
                "created_at": sample.created_at.isoformat() if sample.created_at else None,
                "is_applied": sample.is_applied
            })
        
        return export_data
    except Exception as e:
        logger.error(f"导出训练数据失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/auto_learn")
async def auto_learn_from_history(
    channel_id: str,
    db: AsyncSession = Depends(get_db)
):
    """从历史消息自动学习频道尾部模式"""
    try:
        # 获取该频道的历史消息
        result = await db.execute(
            select(Message).where(
                Message.source_channel == channel_id
            ).order_by(desc(Message.created_at)).limit(100)
        )
        messages = result.scalars().all()
        
        if len(messages) < 10:
            raise HTTPException(status_code=400, detail="历史消息不足，需要至少10条消息")
        
        # 提取消息内容
        contents = []
        for msg in messages:
            content = msg.content or msg.filtered_content
            if content:
                contents.append(content)
        
        if contents:
            # 让AI学习该频道的模式
            success = await ai_filter.learn_channel_pattern(channel_id, contents)
            if success:
                return {
                    "success": True,
                    "message": f"成功从 {len(contents)} 条历史消息中学习频道模式"
                }
            else:
                raise HTTPException(status_code=500, detail="学习失败")
        else:
            raise HTTPException(status_code=400, detail="没有可用的消息内容")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"自动学习失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))