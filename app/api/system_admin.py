"""
系统管理API
负责服务管理、启动停止控制和状态查询
"""
from fastapi import APIRouter, HTTPException
from typing import Dict, Any
import logging
import json
from pathlib import Path
from app.core.routes import ROUTES

logger = logging.getLogger(__name__)
router = APIRouter(tags=["system-admin"])

@router.post(ROUTES.system.service_start)
async def start_service(service_name: str) -> Dict[str, Any]:
    """启动服务（通过配置）"""
    try:
        from app.services.config_manager import config_manager
        
        if service_name == "collector":
            await config_manager.set_config('collection.enabled', True, "手动启用采集服务")
            return {"success": True, "message": "采集服务已启用"}
        elif service_name == "scheduler":
            await config_manager.set_config('scheduler.enabled', True, "手动启用调度服务") 
            return {"success": True, "message": "调度服务已启用"}
        else:
            return {"success": False, "message": f"未知服务: {service_name}"}
            
    except Exception as e:
        logger.error(f"启动服务失败: {e}")
        return {"success": False, "message": f"启动服务失败: {str(e)}"}

@router.post(ROUTES.system.service_stop)
async def stop_service(service_name: str) -> Dict[str, Any]:
    """停止服务（通过配置）"""
    try:
        from app.services.config_manager import config_manager
        
        if service_name == "collector":
            await config_manager.set_config('collection.enabled', False, "手动停止采集服务")
            return {"success": True, "message": "采集服务已停止"}
        elif service_name == "scheduler":
            await config_manager.set_config('scheduler.enabled', False, "手动停止调度服务")
            return {"success": True, "message": "调度服务已停止"}
        else:
            return {"success": False, "message": f"未知服务: {service_name}"}
            
    except Exception as e:
        logger.error(f"停止服务失败: {e}")
        return {"success": False, "message": f"停止服务失败: {str(e)}"}

@router.post(ROUTES.system.service_restart)
async def restart_service(service_name: str) -> Dict[str, Any]:
    """重启服务（先停止再启动）"""
    try:
        from app.services.config_manager import config_manager
        
        if service_name == "collector":
            # 先停止
            await config_manager.set_config('collection.enabled', False, "重启服务 - 停止阶段")
            # 等待一下让服务停止
            import asyncio
            await asyncio.sleep(2)
            # 再启动  
            await config_manager.set_config('collection.enabled', True, "重启服务 - 启动阶段")
            return {"success": True, "message": "采集服务已重启"}
        elif service_name == "scheduler":
            await config_manager.set_config('scheduler.enabled', False, "重启服务 - 停止阶段")
            import asyncio
            await asyncio.sleep(2)
            await config_manager.set_config('scheduler.enabled', True, "重启服务 - 启动阶段")
            return {"success": True, "message": "调度服务已重启"}
        else:
            return {"success": False, "message": f"未知服务: {service_name}"}
            
    except Exception as e:
        logger.error(f"重启服务失败: {e}")
        return {"success": False, "message": f"重启服务失败: {str(e)}"}

@router.get(ROUTES.system.service_status)
async def get_service_status(service_name: str) -> Dict[str, Any]:
    """获取服务状态"""
    try:
        from app.services.config_manager import config_manager
        
        # 获取配置状态
        config_enabled = False
        if service_name == "collector":
            config_enabled = await config_manager.get_config('collection.enabled', True)
        elif service_name == "scheduler":
            config_enabled = await config_manager.get_config('scheduler.enabled', True)
        else:
            return {"success": False, "message": f"未知服务: {service_name}"}
        
        # 获取进程状态
        process_status = "unknown"
        process_info = {}
        
        from app.core.path_config import PathConfig
        supervisor_status_file = PathConfig.SUPERVISOR_STATUS_FILE
        if supervisor_status_file.exists():
            try:
                with open(supervisor_status_file, 'r', encoding='utf-8') as f:
                    status_data = json.load(f)
                    services_status = status_data.get('services', {})
                    
                    if service_name in services_status:
                        service_data = services_status[service_name]
                        process_status = service_data.get('status', 'unknown')
                        process_info = {
                            'uptime': service_data.get('uptime'),
                            'restart_count': service_data.get('restart_count', 0),
                            'pid': service_data.get('pid')
                        }
            except Exception as e:
                logger.warning(f"读取supervisor状态失败: {e}")
        
        # 综合状态判断
        if config_enabled and process_status == "running":
            overall_status = "running"
        elif not config_enabled:
            overall_status = "disabled"  
        elif process_status == "stopped":
            overall_status = "stopped"
        else:
            overall_status = process_status
            
        return {
            "success": True,
            "service": service_name,
            "status": overall_status,
            "config_enabled": config_enabled,
            "process_status": process_status,
            "process_info": process_info
        }
        
    except Exception as e:
        logger.error(f"获取服务状态失败: {e}")
        return {"success": False, "message": f"获取服务状态失败: {str(e)}"}

@router.get(ROUTES.system.services)
async def get_all_services_status() -> Dict[str, Any]:
    """获取所有服务状态"""
    try:
        services = ["collector", "scheduler"]
        result = {}
        
        for service_name in services:
            status_response = await get_service_status(service_name)
            if status_response.get("success"):
                result[service_name] = {
                    "status": status_response["status"],
                    "config_enabled": status_response["config_enabled"],
                    "process_status": status_response["process_status"],
                    "process_info": status_response["process_info"]
                }
            else:
                result[service_name] = {"status": "error", "message": status_response.get("message")}
        
        return {"success": True, "services": result}
        
    except Exception as e:
        logger.error(f"获取所有服务状态失败: {e}")
        return {"success": False, "message": f"获取所有服务状态失败: {str(e)}"}