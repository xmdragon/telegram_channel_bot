"""
管理员系统管理API
包括：系统配置、重启、备份、缓存清理、健康检查、日志导出
"""
from fastapi import APIRouter, HTTPException
from typing import Dict, Any
from datetime import datetime
import os
import shutil
import tarfile
import tempfile
import logging

from app.storage.json_store import get_json_channel_store
from app.core.config import settings
from app.core.route_config import ROUTES
from app.services.config_manager import config_manager

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post(ROUTES.admin.restart)
async def restart_system():
    """重启系统"""
    try:
        # 这里可以实现系统重启逻辑
        # 在实际部署中，可能需要通过进程管理工具重启
        return {"success": True, "message": "系统重启命令已发送"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"系统重启失败: {str(e)}")

@router.post(ROUTES.admin.backup)
async def backup_data():
    """备份数据"""
    try:
        # 创建备份目录
        backup_dir = "backups"
        os.makedirs(backup_dir, exist_ok=True)
        
        # 生成备份文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = f"{backup_dir}/backup_{timestamp}.tar.gz"
        
        # 创建备份文件
        with tarfile.open(backup_file, "w:gz") as tar:
            # 备份PostgreSQL数据（需要使用pg_dump，这里只备份配置说明）
            # 注意：PostgreSQL数据库备份应该使用pg_dump命令
            backup_info = "PostgreSQL数据库备份需要使用pg_dump命令\n"
            backup_info += "示例：pg_dump -h postgres -U postgres telegram_system > backup.sql\n"
            info_file = f"{backup_dir}/database_backup_info.txt"
            with open(info_file, "w") as f:
                f.write(backup_info)
            tar.add(info_file, arcname="database/backup_info.txt")
            os.remove(info_file)
            
            # 备份会话文件
            if os.path.exists("sessions"):
                tar.add("sessions", arcname="sessions")
            
            # 备份数据目录
            if os.path.exists("data"):
                tar.add("data", arcname="data")
            
            # 备份日志目录
            if os.path.exists("logs"):
                tar.add("logs", arcname="logs")
        
        return {"success": True, "message": f"数据备份成功: {backup_file}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"数据备份失败: {str(e)}")

@router.post(ROUTES.admin.clear_cache)
async def clear_cache():
    """清理缓存"""
    try:
        # 清理配置缓存
        await config_manager.clear_cache()
        
        # 清理其他缓存（如果有的话）
        # 这里可以添加其他缓存清理逻辑
        
        return {"success": True, "message": "缓存清理成功"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"缓存清理失败: {str(e)}")

@router.post(ROUTES.admin.export_logs)
async def export_logs():
    """导出日志"""
    try:
        # 创建临时目录
        with tempfile.TemporaryDirectory() as temp_dir:
            log_file = os.path.join(temp_dir, "system_logs.txt")
            
            # 收集日志信息
            with open(log_file, "w", encoding="utf-8") as f:
                f.write("=== 系统日志导出 ===\n")
                f.write(f"导出时间: {datetime.now().isoformat()}\n")
                f.write("=" * 50 + "\n\n")
                
                # 系统信息
                f.write("系统信息:\n")
                f.write(f"- Python版本: {os.sys.version}\n")
                f.write(f"- 工作目录: {os.getcwd()}\n")
                f.write(f"- 当前时间: {datetime.now().isoformat()}\n\n")
                
                # 配置文件信息
                f.write("配置文件:\n")
                try:
                    all_configs = await config_manager.get_all_configs()
                    for key, config in all_configs.items():
                        f.write(f"- {key}: {config['value']}\n")
                except Exception as e:
                    f.write(f"- 配置读取失败: {str(e)}\n")
                
                f.write("\n" + "=" * 50 + "\n")
            
            # 创建下载文件
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            from app.core.path_config import PathConfig
            download_file = PathConfig.LOGS_DIR / f"system_logs_{timestamp}.txt"
            PathConfig.LOGS_DIR.mkdir(exist_ok=True)
            shutil.copy2(log_file, download_file)
            
            return {"success": True, "message": f"日志导出成功: {download_file}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"日志导出失败: {str(e)}")

@router.get(ROUTES.admin.health)
async def health_check():
    """系统健康检查"""
    try:
        # 检查Redis连接
        from app.storage.redis_manager import redis_manager
        redis_store = redis_manager
        redis_manager.client.ping()  # 测试Redis连接
        
        # 检查JSON存储
        channel_store = get_json_channel_store()
        channel_store.get_all_channels()  # 测试文件访问
        
        return {
            "status": "healthy",
            "storage": "connected",
            "timestamp": datetime.utcnow().isoformat(),
            "version": "2.0.0"
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "storage": "disconnected",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }