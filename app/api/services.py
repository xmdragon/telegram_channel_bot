"""
服务管理API
提供服务状态查看、启停、重启、日志查看等功能
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Any, List, Optional
import logging
from app.services.supervisor_manager import supervisor_manager
from app.core.supervisor_config import SupervisorConfig
from app.core.route_config import ROUTES

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/services", tags=["services"])

@router.get(ROUTES.services.status)
async def get_services_status() -> Dict[str, Any]:
    """
    获取所有服务状态

    Returns:
        包含所有服务状态的字典
    """
    try:
        services = supervisor_manager.get_all_services_status()
        is_connected = supervisor_manager.is_connected()

        return {
            "success": True,
            "connected": is_connected,
            "services": services,
            "message": "服务状态获取成功" if is_connected else "Supervisor未连接，显示降级状态"
        }
    except Exception as e:
        logger.error(f"获取服务状态失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get(ROUTES.services.status_by_service)
async def get_service_status(service_name: str) -> Dict[str, Any]:
    """
    获取单个服务状态

    Args:
        service_name: 服务名称（web/collector/scheduler）

    Returns:
        服务状态信息
    """
    try:
        status = supervisor_manager.get_service_status(service_name)
        if status is None:
            raise HTTPException(status_code=404, detail=f"服务{service_name}不存在")

        return {
            "success": True,
            "service": status
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取服务{service_name}状态失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post(ROUTES.services.start)
async def start_service(service_name: str) -> Dict[str, Any]:
    """
    启动服务

    Args:
        service_name: 服务名称（web/collector/scheduler）

    Returns:
        操作结果
    """
    try:
        if service_name == "all":
            success = supervisor_manager.start_all_services()
            message = "所有服务启动成功" if success else "启动失败，请检查日志"
        else:
            success = supervisor_manager.start_service(service_name)
            message = f"服务{service_name}启动成功" if success else f"服务{service_name}启动失败"

        return {
            "success": success,
            "message": message
        }
    except Exception as e:
        logger.error(f"启动服务{service_name}失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post(ROUTES.services.stop)
async def stop_service(service_name: str) -> Dict[str, Any]:
    """
    停止服务

    Args:
        service_name: 服务名称（web/collector/scheduler）

    Returns:
        操作结果
    """
    try:
        if service_name == "all":
            success = supervisor_manager.stop_all_services()
            message = "所有服务停止成功" if success else "停止失败，请检查日志"
        else:
            success = supervisor_manager.stop_service(service_name)
            message = f"服务{service_name}停止成功" if success else f"服务{service_name}停止失败"

        return {
            "success": success,
            "message": message
        }
    except Exception as e:
        logger.error(f"停止服务{service_name}失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post(ROUTES.services.restart)
async def restart_service(service_name: str) -> Dict[str, Any]:
    """
    重启服务

    Args:
        service_name: 服务名称（web/collector/scheduler）

    Returns:
        操作结果
    """
    try:
        if service_name == "all":
            # 重启所有服务
            stop_success = supervisor_manager.stop_all_services()
            start_success = supervisor_manager.start_all_services()
            success = stop_success and start_success
            message = "所有服务重启成功" if success else "重启失败，请检查日志"
        else:
            success = supervisor_manager.restart_service(service_name)
            message = f"服务{service_name}重启成功" if success else f"服务{service_name}重启失败"

        return {
            "success": success,
            "message": message
        }
    except Exception as e:
        logger.error(f"重启服务{service_name}失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get(ROUTES.services.logs)
async def get_service_logs(
    service_name: str,
    log_type: str = Query("stdout", description="日志类型: stdout 或 stderr"),
    lines: int = Query(100, description="返回的日志行数", ge=1, le=1000)
) -> Dict[str, Any]:
    """
    获取服务日志

    Args:
        service_name: 服务名称（web/collector/scheduler）
        log_type: 日志类型（stdout/stderr）
        lines: 返回的日志行数（1-1000）

    Returns:
        日志内容
    """
    try:
        if log_type not in ["stdout", "stderr"]:
            raise HTTPException(status_code=400, detail="日志类型必须是stdout或stderr")

        logs = supervisor_manager.get_service_logs(
            service_name,
            log_type=log_type,
            length=lines * 200  # 假设平均每行200字符
        )

        # 按行分割并取最后N行
        log_lines = logs.strip().split('\n')
        if len(log_lines) > lines:
            log_lines = log_lines[-lines:]

        return {
            "success": True,
            "service": service_name,
            "log_type": log_type,
            "logs": '\n'.join(log_lines),
            "lines": len(log_lines)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取服务{service_name}日志失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post(ROUTES.services.reload_config)
async def reload_config() -> Dict[str, Any]:
    """
    重新加载Supervisor配置

    Returns:
        操作结果
    """
    try:
        success = supervisor_manager.reload_config()
        return {
            "success": success,
            "message": "配置重载成功" if success else "配置重载失败"
        }
    except Exception as e:
        logger.error(f"重载配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get(ROUTES.services.info)
async def get_supervisor_info() -> Dict[str, Any]:
    """
    获取Supervisor连接信息

    Returns:
        Supervisor连接配置信息
    """
    try:
        return {
            "success": True,
            "info": {
                "host": SupervisorConfig.SUPERVISOR_HOST,
                "port": SupervisorConfig.SUPERVISOR_PORT,
                "connected": supervisor_manager.is_connected(),
                "services": list(SupervisorConfig.SERVICE_MAPPING.keys())
            }
        }
    except Exception as e:
        logger.error(f"获取Supervisor信息失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
