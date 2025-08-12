"""
广告训练相关API
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Dict, Optional
from datetime import datetime
import json
import hashlib
from pathlib import Path
import logging

from app.core.database import get_db
from app.services.adaptive_learning import adaptive_learning
from app.core.training_config import TrainingDataConfig

logger = logging.getLogger(__name__)
router = APIRouter()

# 数据文件路径（使用集中配置）
SEPARATOR_PATTERNS_FILE = TrainingDataConfig.SEPARATOR_PATTERNS_FILE
TAIL_AD_SAMPLES_FILE = TrainingDataConfig.TAIL_AD_SAMPLES_FILE

# 确保数据目录存在
TrainingDataConfig.ensure_directories()


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


@router.post("/tail-ad-samples")
async def add_tail_ad_sample(request: dict):
    """添加尾部广告训练样本"""
    try:
        # 提取参数
        description = request.get("description", "")
        content = request.get("content", "")
        separator = request.get("separator", "")
        normal_part = request.get("normalPart", "")
        ad_part = request.get("adPart", "")
        
        if not content or not separator:
            return {"success": False, "error": "内容和分隔符不能为空"}
        
        # 加载现有样本
        samples = []
        if TAIL_AD_SAMPLES_FILE.exists():
            with open(TAIL_AD_SAMPLES_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                samples = data.get("samples", [])
        
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
                return {"success": False, "error": "样本已存在"}
        
        # 添加样本
        samples.append(new_sample)
        
        # 保存到文件
        with open(TAIL_AD_SAMPLES_FILE, 'w', encoding='utf-8') as f:
            json.dump({
                "samples": samples,
                "updated_at": datetime.now().isoformat()
            }, f, ensure_ascii=False, indent=2)
        
        # 同时添加到广告样本库用于AI学习
        await adaptive_learning._add_ad_sample(ad_part)
        
        logger.info(f"添加新的尾部广告样本: {new_id}")
        return {"success": True, "message": "样本已添加", "id": new_id}
        
    except Exception as e:
        logger.error(f"添加尾部广告样本失败: {e}")
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
        stats = adaptive_learning.get_learning_stats()
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
        
        if not message_id or not action:
            return {"success": False, "error": "参数不完整"}
        
        # 记录反馈
        await adaptive_learning.learn_from_user_action(message_id, action, reviewer)
        
        return {"success": True, "message": "反馈已记录"}
        
    except Exception as e:
        logger.error(f"记录反馈失败: {e}")
        return {"success": False, "error": str(e)}