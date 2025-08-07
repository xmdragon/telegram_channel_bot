"""
进程锁状态API
"""
from fastapi import APIRouter, HTTPException
from app.telegram.process_lock import telegram_lock

router = APIRouter()

@router.get("/lock/status")
async def get_lock_status():
    """获取进程锁状态"""
    try:
        is_locked = await telegram_lock.is_locked()
        lock_info = await telegram_lock.get_lock_info()
        
        if not lock_info:
            return {
                "locked": is_locked,
                "owner": None,
                "message": "没有进程持有锁"
            }
        
        return {
            "locked": is_locked,
            "owner": lock_info.get("owner_id"),
            "is_mine": lock_info.get("is_mine"),
            "last_heartbeat": lock_info.get("last_heartbeat"),
            "heartbeat_age": lock_info.get("heartbeat_age"),
            "message": "锁已被持有" if is_locked else "锁未被持有"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取锁状态失败: {str(e)}")

@router.post("/lock/force-release")
async def force_release_lock():
    """强制释放锁（仅紧急情况使用）"""
    try:
        await telegram_lock.force_release()
        return {
            "success": True,
            "message": "锁已强制释放"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"强制释放锁失败: {str(e)}")