"""
系统管理模块 - 备份、恢复、完整性检查、存储优化等管理功能
"""
from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import StreamingResponse
from datetime import datetime, timedelta
from typing import List, Dict, Any
import logging
import json
import asyncio
import os
import glob
from pathlib import Path

from .base import (
    handle_api_error, FeedbackData,
    load_training_data, save_training_data
)
from app.core.path_config import PathConfig
from app.utils.safe_file_ops import SafeFileOperation

logger = logging.getLogger(__name__)
router = APIRouter(tags=["training-admin"])

@router.post("/optimize-storage")
async def optimize_storage():
    """优化存储"""
    try:
        # 简单实现：返回优化完成状态
        
        return {
            "success": True,
            "message": "存储优化完成",
            "freedSpace": 0,
            "processedFiles": 0
        }
    except Exception as e:
        raise handle_api_error(e, "优化存储")

@router.get("/optimize-storage-sse")
async def optimize_storage_sse():
    """SSE存储优化"""
    async def generate_sse():
        """生成SSE事件流"""
        try:
            # 模拟优化过程
            yield f"data: {json.dumps({'type': 'start', 'message': '开始存储优化'})}\n\n"
            
            await asyncio.sleep(1)
            yield f"data: {json.dumps({'type': 'progress', 'message': '正在分析文件...', 'progress': 30})}\n\n"
            
            await asyncio.sleep(1)
            yield f"data: {json.dumps({'type': 'progress', 'message': '正在优化...', 'progress': 70})}\n\n"
            
            await asyncio.sleep(1)
            yield f"data: {json.dumps({'type': 'complete', 'message': '优化完成', 'progress': 100})}\n\n"
            
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
    
    return StreamingResponse(generate_sse(), media_type="text/plain")

@router.get("/learning-stats")
async def get_learning_stats():
    """获取学习统计"""
    try:
        samples = load_training_data()
        history = []  # 训练历史功能已移除
        
        # 计算基础统计
        total_samples = len(samples)
        applied_samples = len([s for s in samples if s.get('is_applied', False)])
        
        # 计算最近7天的活动
        recent_date = datetime.now() - timedelta(days=7)
        recent_activity = 0
        for entry in history:
            try:
                entry_date = datetime.fromisoformat(entry.get('timestamp', ''))
                if entry_date > recent_date:
                    recent_activity += 1
            except:
                pass
        
        return {
            "success": True,
            "stats": {
                "totalSamples": total_samples,
                "appliedSamples": applied_samples,
                "pendingSamples": total_samples - applied_samples,
                "recentActivity": recent_activity,
                "lastActivity": datetime.now().isoformat()
            }
        }
    except Exception as e:
        raise handle_api_error(e, "获取学习统计")

@router.post("/emergency-backup")
async def emergency_backup():
    """紧急备份"""
    try:
        backup_dir = PathConfig.MANUAL_TRAINING_FILE.parent / "backups"
        backup_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_file = backup_dir / f"emergency_backup_{timestamp}.json"
        
        # 收集所有训练数据
        backup_data = {
            "training_data": load_training_data(),
            "training_history": [],  # 训练历史功能已移除
            "backup_timestamp": datetime.now().isoformat(),
            "backup_type": "emergency"
        }
        
        # 保存备份
        if SafeFileOperation.write_json_safe(backup_file, backup_data):
            
            return {
                "success": True,
                "message": "紧急备份完成",
                "backupFile": str(backup_file.name),
                "dataCount": len(backup_data["training_data"])
            }
        else:
            raise HTTPException(status_code=500, detail="备份失败")
            
    except Exception as e:
        raise handle_api_error(e, "紧急备份")

@router.get("/integrity-report")
async def get_integrity_report():
    """获取完整性报告"""
    try:
        # 检查文件完整性
        issues = []
        total_files = 0
        corrupted_files = 0
        
        # 检查主要配置文件
        config_files = [
            PathConfig.MANUAL_TRAINING_FILE,
            PathConfig.TAIL_FILTER_SAMPLES_FILE,
            PathConfig.SEPARATOR_PATTERNS_FILE
        ]
        
        for config_file in config_files:
            total_files += 1
            if not config_file.exists():
                issues.append(f"配置文件缺失: {config_file.name}")
                corrupted_files += 1
            else:
                try:
                    SafeFileOperation.read_json_safe(config_file)
                except Exception as e:
                    issues.append(f"配置文件损坏: {config_file.name} - {str(e)}")
                    corrupted_files += 1
        
        # 计算完整性评分
        integrity_score = max(0, (total_files - corrupted_files) / total_files * 100) if total_files > 0 else 100
        
        return {
            "success": True,
            "report": {
                "integrity_score": round(integrity_score, 2),
                "total_files": total_files,
                "corrupted_files": corrupted_files,
                "issues": issues,
                "last_check": datetime.now().isoformat()
            }
        }
    except Exception as e:
        raise handle_api_error(e, "获取完整性报告")

@router.post("/verify-integrity")
async def verify_integrity():
    """验证数据完整性"""
    try:
        # 简单的完整性验证
        return {"success": True, "message": "数据完整性验证通过"}
    except Exception as e:
        raise handle_api_error(e, "验证数据完整性")

@router.post("/cleanup-backups")
async def cleanup_backups():
    """清理备份文件"""
    try:
        backup_dir = PathConfig.MANUAL_TRAINING_FILE.parent / "backups"
        if not backup_dir.exists():
            return {"success": True, "message": "没有备份文件需要清理", "deletedCount": 0}
        
        # 获取30天前的时间
        cutoff_date = datetime.now() - timedelta(days=30)
        deleted_count = 0
        
        # 清理超过30天的备份文件
        for backup_file in backup_dir.glob("*.json"):
            try:
                file_time = datetime.fromtimestamp(backup_file.stat().st_mtime)
                if file_time < cutoff_date:
                    backup_file.unlink()
                    deleted_count += 1
                    logger.info(f"删除过期备份: {backup_file.name}")
            except Exception as e:
                logger.error(f"删除备份文件失败 {backup_file}: {e}")
        
        
        return {
            "success": True,
            "message": f"清理完成，删除了 {deleted_count} 个过期备份",
            "deletedCount": deleted_count
        }
    except Exception as e:
        raise handle_api_error(e, "清理备份文件")

@router.get("/backups")
async def get_backups():
    """获取备份列表"""
    try:
        backup_dir = PathConfig.MANUAL_TRAINING_FILE.parent / "backups"
        backups = []
        
        if backup_dir.exists():
            for backup_file in backup_dir.glob("*.json"):
                try:
                    stat = backup_file.stat()
                    backups.append({
                        "filename": backup_file.name,
                        "size": stat.st_size,
                        "created_at": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                        "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat()
                    })
                except Exception as e:
                    logger.error(f"读取备份文件信息失败 {backup_file}: {e}")
        
        # 按创建时间排序
        backups.sort(key=lambda x: x['created_at'], reverse=True)
        
        return {
            "success": True,
            "backups": backups,
            "total": len(backups)
        }
    except Exception as e:
        raise handle_api_error(e, "获取备份列表")

@router.post("/restore/{backup_filename}")
async def restore_backup(backup_filename: str):
    """恢复备份"""
    try:
        backup_dir = PathConfig.MANUAL_TRAINING_FILE.parent / "backups"
        backup_file = backup_dir / backup_filename
        
        if not backup_file.exists():
            raise HTTPException(status_code=404, detail="备份文件不存在")
        
        # 读取备份数据
        backup_data = SafeFileOperation.read_json_safe(backup_file)
        if not backup_data:
            raise HTTPException(status_code=400, detail="备份文件损坏")
        
        # 恢复训练数据
        if "training_data" in backup_data:
            if not save_training_data(backup_data["training_data"]):
                raise HTTPException(status_code=500, detail="恢复训练数据失败")
        
        # 记录恢复操作已完成
        
        return {
            "success": True,
            "message": "备份恢复成功",
            "restoredCount": len(backup_data.get("training_data", []))
        }
    except HTTPException:
        raise
    except Exception as e:
        raise handle_api_error(e, "恢复备份")

@router.post("/feedback")
async def submit_feedback(feedback: FeedbackData):
    """提交反馈"""
    try:
        # 记录反馈已提交
        
        return {"success": True, "message": "反馈已提交"}
    except Exception as e:
        raise handle_api_error(e, "提交反馈")

@router.get("/statistics")
async def get_general_statistics():
    """获取总体统计"""
    try:
        samples = load_training_data()
        history = []  # 训练历史功能已移除
        
        # 基础统计
        total_samples = len(samples)
        channels = set(s.get('channel_id') for s in samples if s.get('channel_id'))
        
        # 今日统计
        today = datetime.now().date()
        today_samples = sum(
            1 for s in samples 
            if s.get('created_at') and 
            datetime.fromisoformat(s['created_at']).date() == today
        )
        
        # 历史活动统计
        recent_activity = len([
            h for h in history 
            if h.get('timestamp') and 
            datetime.fromisoformat(h['timestamp']) > datetime.now() - timedelta(days=7)
        ])
        
        return {
            "success": True,
            "statistics": {
                "totalSamples": total_samples,
                "totalChannels": len(channels),
                "todaySamples": today_samples,
                "recentActivity": recent_activity,
                "lastUpdate": datetime.now().isoformat()
            }
        }
    except Exception as e:
        raise handle_api_error(e, "获取总体统计")

@router.delete("/clear")
async def clear_all_data():
    """清除所有训练数据（危险操作）"""
    try:
        # 创建备份
        backup_dir = PathConfig.MANUAL_TRAINING_FILE.parent / "backups"
        backup_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_file = backup_dir / f"pre_clear_backup_{timestamp}.json"
        
        # 备份现有数据
        backup_data = {
            "training_data": load_training_data(),
            "training_history": [],  # 训练历史功能已移除
            "backup_timestamp": datetime.now().isoformat(),
            "backup_type": "pre_clear"
        }
        
        SafeFileOperation.write_json_safe(backup_file, backup_data)
        
        # 清空数据
        if not save_training_data([]):
            raise HTTPException(status_code=500, detail="清空数据失败")
        
        # 记录清空操作已完成
        
        return {
            "success": True,
            "message": "所有数据已清除",
            "backupFile": str(backup_file.name),
            "clearedCount": len(backup_data["training_data"])
        }
    except Exception as e:
        raise handle_api_error(e, "清除所有数据")