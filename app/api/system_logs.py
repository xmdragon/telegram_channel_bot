"""
系统日志管理API
负责系统日志的查看、过滤和实时更新
"""
from fastapi import APIRouter, HTTPException
from typing import Dict, Any
import logging
import os
import glob
from datetime import datetime

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/system", tags=["system-logs"])

@router.get("/logs")
async def get_system_logs(limit: int = 100) -> Dict[str, Any]:
    """获取系统日志"""
    try:
        import glob
        logs = []
        log_sources = []
        
        # 查找所有日志文件（包括轮转的历史文件）
        log_pattern = "./logs/app.log*"
        log_files = glob.glob(log_pattern)
        
        # 按修改时间排序，最新的在前
        log_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
        
        # 读取日志文件直到获取足够的行数
        for log_file in log_files[:3]:  # 最多读取最近3个文件
            if not os.path.exists(log_file):
                continue
                
            log_sources.append(log_file)
            try:
                # 读取日志文件
                with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                    file_lines = f.readlines()
                    
                    # 从文件末尾开始读取
                    for log_line in reversed(file_lines):
                        if log_line.strip():
                            # 解析日志行
                            timestamp = extract_timestamp(log_line)
                            level = extract_log_level(log_line)
                            # 提取实际的消息内容
                            message = extract_message(log_line)
                            
                            logs.append({
                                "time": timestamp,
                                "level": level,
                                "message": message
                            })
                            
                            # 如果已经收集够了，停止
                            if len(logs) >= limit:
                                break
                                
            except Exception as e:
                logger.error(f"读取日志文件 {log_file} 失败: {e}")
                continue
            
            if len(logs) >= limit:
                break
        
        # 如果没有找到日志文件，显示基本系统信息
        if not logs:
            logs.append({
                "time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "level": "INFO",
                "message": f"系统正在运行 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            })
        else:
            # 日志已经是倒序读取的，不需要再排序
            # 只需要限制返回的行数
            logs = logs[:limit]
        
        return {
            "success": True,
            "logs": logs
        }
    except Exception as e:
        logger.error(f"获取系统日志失败: {e}")
        # 返回基本信息而不是抛出异常
        return {
            "success": True,
            "data": {
                "logs": [{
                    "time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    "level": "INFO",
                    "message": f"系统运行中 - 无法读取详细日志: {str(e)}"
                }],
                "sources": [],
                "total": 1,
                "timestamp": datetime.now().isoformat()
            }
        }

def extract_timestamp(log_line: str) -> str:
    """从日志行中提取时间戳"""
    try:
        # 尝试匹配常见的时间戳格式
        import re
        timestamp_patterns = [
            r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})',
            r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})',
            r'(\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2})'
        ]
        
        for pattern in timestamp_patterns:
            match = re.search(pattern, log_line)
            if match:
                return match.group(1)
        
        # 如果没有找到时间戳，返回当前时间
        return datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    except:
        return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

def extract_log_level(log_line: str) -> str:
    """从日志行中提取日志级别"""
    try:
        import re
        level_pattern = r'\b(DEBUG|INFO|WARNING|ERROR|CRITICAL)\b'
        match = re.search(level_pattern, log_line.upper())
        if match:
            return match.group(1)
        return "INFO"
    except:
        return "INFO"

def extract_message(log_line: str) -> str:
    """从日志行中提取消息内容"""
    try:
        import re
        # 标准格式: 2025-08-07 20:33:37,197 - module.name - LEVEL - message
        pattern = r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:,\d+)? - [\w\.]+ - \w+ - (.+)$'
        match = re.match(pattern, log_line)
        if match:
            return match.group(1)
        
        # 如果不匹配标准格式，尝试提取 - 后面的内容
        parts = log_line.split(' - ')
        if len(parts) >= 4:
            return ' - '.join(parts[3:])
        
        # 返回原始内容
        return log_line.strip()
    except:
        return log_line.strip()