"""
手动训练API路由
"""
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import asyncio
import json
import os
import fcntl
import time
import shutil
import hashlib
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import threading

from app.core.database import get_db, Channel, Message, Admin
from app.services.ai_filter import ai_filter
from app.services.adaptive_learning import adaptive_learning
from app.api.admin_auth import check_permission, require_admin
from app.utils.safe_file_ops import SafeFileOperation
from app.core.training_config import TrainingDataConfig
from pydantic import BaseModel
import logging

logger = logging.getLogger(__name__)

router = APIRouter(tags=["training"])

# 使用集中配置的文件路径
SEPARATOR_PATTERNS_FILE = TrainingDataConfig.SEPARATOR_PATTERNS_FILE
TAIL_FILTER_SAMPLES_FILE = TrainingDataConfig.TAIL_FILTER_SAMPLES_FILE

# 确保数据目录存在（现在由配置类处理）
TrainingDataConfig.ensure_directories()

async def update_message_after_training(
    db: AsyncSession,
    message_id: int,
    original_message: str,  # 这个参数保留但不使用
    tail_content: str
):
    """
    训练后更新消息内容
    1. 使用ContentFilter应用所有已训练的尾部过滤规则
    2. 更新数据库中的filtered_content
    """
    try:
        # 获取消息记录
        result = await db.execute(
            select(Message).where(Message.id == message_id)
        )
        message = result.scalar_one_or_none()
        
        if not message:
            logger.warning(f"消息 {message_id} 不存在")
            return
        
        # 使用数据库中的实际内容
        actual_content = message.content
        
        if not actual_content:
            logger.warning(f"消息 {message_id} 内容为空")
            return
        
        # 使用全局的content_filter实例（已重新加载最新训练模式）
        from app.services.content_filter import content_filter
        
        # 应用尾部过滤（使用已重新加载的训练样本）
        filtered_content = content_filter.filter_promotional_content(
            actual_content,
            channel_id=str(message.source_channel) if message.source_channel else None
        )
        
        # 更新数据库中的过滤内容
        message.filtered_content = filtered_content
        message.is_ad = False  # 训练后通常意味着不是广告
        await db.commit()
        
        logger.info(f"消息 {message_id} 过滤完成: {len(actual_content)} -> {len(filtered_content)} 字符")
        
        logger.info(f"消息 {message_id} 内容已更新: {len(original_message)} -> {len(filtered_content)} 字符")
        
        # 如果有审核群消息ID，尝试更新审核群中的消息
        if message.review_message_id:
            try:
                from app.telegram.bot import telegram_bot
                if telegram_bot and telegram_bot.client:
                    # 调用更新审核群消息的方法
                    await telegram_bot.update_review_message(message)
                    logger.info(f"审核群消息 {message.review_message_id} 已更新")
            except Exception as e:
                logger.error(f"更新审核群消息失败: {e}")
                # 不抛出异常，因为数据库已经更新成功
        
    except Exception as e:
        logger.error(f"更新消息 {message_id} 失败: {e}")
        raise

# 训练数据文件路径（使用集中配置）
TRAINING_DATA_FILE = TrainingDataConfig.MANUAL_TRAINING_FILE
TRAINING_HISTORY_FILE = TrainingDataConfig.TRAINING_HISTORY_FILE
AD_TRAINING_FILE = TrainingDataConfig.AD_TRAINING_FILE

class TrainingSubmission(BaseModel):
    """训练数据提交模型"""
    original_message: str
    tail_content: str
    message_id: Optional[int] = None  # 消息ID，用于更新数据库记录

class TrainingRecord:
    """训练记录 - 加强版数据保护机制"""
    def __init__(self):
        self.data_file = TRAINING_DATA_FILE
        self.history_file = TRAINING_HISTORY_FILE
        self.backup_dir = Path("data/backups")
        self.lock_dir = Path("data/locks")
        self._file_locks = {}
        self._lock = threading.RLock()
        
        # 确保关键目录存在
        self._ensure_directories()
        # 确保文件存在且安全初始化
        self._safe_ensure_files()
        
        # 启动时执行完整性检查
        self._startup_integrity_check()
    
    def _startup_integrity_check(self):
        """启动时的完整性检查"""
        logger.info("正在执行启动时数据完整性检查...")
        
        # 检查主数据文件
        if not self._verify_json_integrity(self.data_file):
            logger.error("训练数据文件损坏，尝试恢复...")
            if self._restore_from_latest_backup(self.data_file, "manual_training_data"):
                logger.info("训练数据文件恢复成功")
            else:
                logger.error("无法恢复训练数据文件")
        
        # 检查历史数据文件
        if not self._verify_json_integrity(self.history_file):
            logger.error("历史数据文件损坏，尝试恢复...")
            if self._restore_from_latest_backup(self.history_file, "training_history"):
                logger.info("历史数据文件恢复成功")
            else:
                logger.error("无法恢复历史数据文件")
        
        # 统计备份文件
        backup_count = len(list(self.backup_dir.glob("*.json")))
        logger.info(f"完整性检查完成，发现 {backup_count} 个备份文件")
    
    def create_emergency_backup(self) -> bool:
        """创建紧急备份（用于手动触发）"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # 备份主数据文件
            data_backup = None
            if self.data_file.exists() and self.data_file.stat().st_size > 0:
                data_backup = self._create_backup(self.data_file, f"emergency_training_data_{timestamp}")
            
            # 备份历史文件
            history_backup = None
            if self.history_file.exists() and self.history_file.stat().st_size > 0:
                history_backup = self._create_backup(self.history_file, f"emergency_training_history_{timestamp}")
            
            success = (data_backup is not None or not self.data_file.exists()) and \
                     (history_backup is not None or not self.history_file.exists())
            
            if success:
                logger.info(f"紧急备份创建成功: {timestamp}")
            else:
                logger.error("紧急备份创建失败")
            
            return success
            
        except Exception as e:
            logger.error(f"创建紧急备份失败: {e}")
            return False
    
    def get_integrity_report(self) -> dict:
        """获取详细的数据完整性报告"""
        report = {
            "timestamp": datetime.now().isoformat(),
            "files": {},
            "backups": {},
            "overall_status": "unknown"
        }
        
        try:
            # 检查主数据文件
            report["files"]["training_data"] = {
                "exists": self.data_file.exists(),
                "size": self.data_file.stat().st_size if self.data_file.exists() else 0,
                "valid_json": self._verify_json_integrity(self.data_file),
                "hash": self._calculate_file_hash(self.data_file)
            }
            
            # 检查历史数据文件
            report["files"]["training_history"] = {
                "exists": self.history_file.exists(),
                "size": self.history_file.stat().st_size if self.history_file.exists() else 0,
                "valid_json": self._verify_json_integrity(self.history_file),
                "hash": self._calculate_file_hash(self.history_file)
            }
            
            # 检查备份文件
            backup_files = list(self.backup_dir.glob("*.json"))
            report["backups"]["total_count"] = len(backup_files)
            report["backups"]["valid_backups"] = sum(1 for f in backup_files if self._verify_json_integrity(f))
            
            if backup_files:
                latest_backup = max(backup_files, key=lambda f: f.stat().st_mtime)
                report["backups"]["latest"] = {
                    "file": latest_backup.name,
                    "timestamp": datetime.fromtimestamp(latest_backup.stat().st_mtime).isoformat(),
                    "size": latest_backup.stat().st_size,
                    "valid": self._verify_json_integrity(latest_backup)
                }
            
            # 判断整体状态
            main_files_ok = (report["files"]["training_data"]["valid_json"] and 
                           report["files"]["training_history"]["valid_json"])
            has_valid_backups = report["backups"]["valid_backups"] > 0
            
            if main_files_ok:
                report["overall_status"] = "healthy"
            elif has_valid_backups:
                report["overall_status"] = "recoverable"
            else:
                report["overall_status"] = "critical"
            
        except Exception as e:
            logger.error(f"生成完整性报告失败: {e}")
            report["overall_status"] = "error"
            report["error"] = str(e)
        
        return report
    
    def _ensure_directories(self):
        """确保所有必要的目录存在"""
        for directory in ["data", self.backup_dir, self.lock_dir]:
            os.makedirs(directory, exist_ok=True)
    
    def _calculate_file_hash(self, file_path: Path) -> Optional[str]:
        """计算文件哈希值用于完整性验证"""
        if not file_path.exists():
            return None
        try:
            with open(file_path, 'rb') as f:
                return hashlib.sha256(f.read()).hexdigest()
        except Exception as e:
            logger.error(f"计算文件哈希失败 {file_path}: {e}")
            return None
    
    def _verify_json_integrity(self, file_path: Path) -> bool:
        """验证JSON文件完整性"""
        if not file_path.exists() or file_path.stat().st_size == 0:
            return True  # 空文件视为合法
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # 基本结构验证
                if file_path.name == 'manual_training_data.json':
                    return isinstance(data, dict) and 'channels' in data
                elif file_path.name == 'training_history.json':
                    return isinstance(data, dict) and 'history' in data and 'stats' in data
            return True
        except Exception as e:
            logger.error(f"JSON完整性验证失败 {file_path}: {e}")
            return False
    
    def _create_backup(self, file_path: Path, backup_prefix: str) -> Optional[Path]:
        """创建文件备份，返回备份文件路径"""
        if not file_path.exists() or file_path.stat().st_size == 0:
            return None
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]  # 精确到毫秒
        backup_file = self.backup_dir / f"{backup_prefix}_{timestamp}.json"
        
        try:
            # 验证源文件完整性
            if not self._verify_json_integrity(file_path):
                logger.error(f"源文件损坏，拒绝备份: {file_path}")
                return None
            
            # 创建备份
            shutil.copy2(file_path, backup_file)
            
            # 验证备份完整性
            if not self._verify_json_integrity(backup_file):
                backup_file.unlink()
                logger.error(f"备份文件损坏，已删除: {backup_file}")
                return None
            
            # 记录备份信息
            backup_hash = self._calculate_file_hash(backup_file)
            logger.info(f"成功创建备份: {backup_file} (SHA256: {backup_hash[:16]}...)")
            
            return backup_file
        except Exception as e:
            logger.error(f"创建备份失败 {file_path}: {e}")
            if backup_file.exists():
                try:
                    backup_file.unlink()
                except:
                    pass
            return None
    
    def _safe_ensure_files(self):
        """安全地确保文件存在，绝对不会覆盖现有有效数据"""
        # 处理训练数据文件
        self._safe_ensure_single_file(
            self.data_file,
            "manual_training_data",
            {
                "channels": {},
                "updated_at": datetime.now().isoformat(),
                "version": "2.0",
                "integrity_hash": ""
            }
        )
        
        # 处理历史数据文件
        self._safe_ensure_single_file(
            self.history_file,
            "training_history",
            {
                "history": [],
                "stats": {
                    "total_samples": 0,
                    "channels_trained": 0
                },
                "version": "2.0",
                "integrity_hash": ""
            }
        )
    
    def _safe_ensure_single_file(self, file_path: Path, backup_prefix: str, default_data: dict):
        """安全地确保单个文件存在"""
        # 如果文件存在且有内容
        if file_path.exists() and file_path.stat().st_size > 0:
            # 验证文件完整性
            if self._verify_json_integrity(file_path):
                # 文件有效，创建预防性备份
                backup_file = self._create_backup(file_path, backup_prefix)
                if backup_file:
                    logger.info(f"现有文件有效，已创建预防性备份: {backup_file}")
                return
            else:
                # 文件损坏，尝试从备份恢复
                logger.warning(f"检测到文件损坏: {file_path}")
                if self._restore_from_latest_backup(file_path, backup_prefix):
                    logger.info(f"已从备份恢复文件: {file_path}")
                    return
                else:
                    # 无法恢复，重命名损坏文件
                    corrupted_file = file_path.with_suffix(f".corrupted_{int(time.time())}")
                    shutil.move(file_path, corrupted_file)
                    logger.error(f"无法恢复，已将损坏文件重命名为: {corrupted_file}")
        
        # 文件不存在或为空或损坏，创建新文件
        try:
            # 计算默认数据的哈希
            data_str = json.dumps(default_data, ensure_ascii=False, separators=(',', ':'))
            default_data["integrity_hash"] = hashlib.sha256(data_str.encode()).hexdigest()
            
            # 原子写入
            self._atomic_write(file_path, default_data)
            logger.info(f"创建新的数据文件: {file_path}")
            
        except Exception as e:
            logger.error(f"创建新文件失败 {file_path}: {e}")
            raise RuntimeError(f"无法初始化数据文件: {file_path}")
    
    def _acquire_file_lock(self, file_path: Path, timeout: int = 30):
        """获取文件锁（防止并发写入）"""
        lock_file = self.lock_dir / f"{file_path.name}.lock"
        
        with self._lock:
            if lock_file in self._file_locks:
                lock_fd = self._file_locks[lock_file]
            else:
                try:
                    lock_fd = open(lock_file, 'w')
                    self._file_locks[lock_file] = lock_fd
                except Exception as e:
                    logger.error(f"创建锁文件失败 {lock_file}: {e}")
                    raise
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                logger.debug(f"获取文件锁成功: {file_path}")
                return lock_fd
            except BlockingIOError:
                time.sleep(0.1)
        
        raise TimeoutError(f"获取文件锁超时: {file_path}")
    
    def _release_file_lock(self, lock_fd):
        """释放文件锁"""
        try:
            fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
            logger.debug("文件锁已释放")
        except Exception as e:
            logger.error(f"释放文件锁失败: {e}")
    
    def _atomic_write(self, file_path: Path, data: dict):
        """原子写入文件（带完整性验证）"""
        # 生成临时文件名
        temp_file = file_path.with_suffix(f".tmp_{int(time.time())}_{os.getpid()}")
        
        try:
            # 更新时间戳
            data["updated_at"] = datetime.now().isoformat()
            
            # 计算数据完整性哈希（排除hash字段本身）
            data_copy = data.copy()
            data_copy.pop("integrity_hash", None)
            data_str = json.dumps(data_copy, ensure_ascii=False, separators=(',', ':'), sort_keys=True)
            data["integrity_hash"] = hashlib.sha256(data_str.encode()).hexdigest()
            
            # 写入临时文件
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())  # 确保写入磁盘
            
            # 验证临时文件完整性
            if not self._verify_json_integrity(temp_file):
                raise ValueError("写入的临时文件完整性验证失败")
            
            # 原子替换
            if os.name == 'nt':  # Windows
                if file_path.exists():
                    file_path.unlink()
                temp_file.rename(file_path)
            else:  # Unix/Linux
                temp_file.replace(file_path)
            
            logger.debug(f"原子写入成功: {file_path}")
            
        except Exception as e:
            # 清理临时文件
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except:
                    pass
            raise e
    
    def _safe_load_data(self, file_path: Path, default_data: dict) -> dict:
        """安全加载数据，包含完整性验证和自动恢复"""
        # 获取文件锁
        lock_fd = None
        try:
            lock_fd = self._acquire_file_lock(file_path)
            
            # 文件不存在
            if not file_path.exists():
                logger.warning(f"数据文件不存在: {file_path}")
                return default_data.copy()
            
            # 文件为空
            if file_path.stat().st_size == 0:
                logger.warning(f"数据文件为空: {file_path}")
                return default_data.copy()
            
            # 加载并验证数据
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # 基本结构验证
                if not isinstance(data, dict):
                    raise ValueError("数据格式错误：不是有效的字典")
                
                # 完整性哈希验证（如果存在）
                if "integrity_hash" in data:
                    stored_hash = data["integrity_hash"]
                    data_copy = data.copy()
                    data_copy.pop("integrity_hash", None)
                    data_str = json.dumps(data_copy, ensure_ascii=False, separators=(',', ':'), sort_keys=True)
                    calculated_hash = hashlib.sha256(data_str.encode()).hexdigest()
                    
                    if stored_hash != calculated_hash:
                        logger.warning(f"数据完整性验证失败 {file_path}")
                        # 尝试从备份恢复
                        backup_prefix = file_path.stem
                        if self._restore_from_latest_backup(file_path, backup_prefix):
                            return self._safe_load_data(file_path, default_data)
                        else:
                            logger.error(f"无法从备份恢复，使用默认数据: {file_path}")
                            return default_data.copy()
                
                logger.debug(f"数据加载成功: {file_path}")
                return data
                
            except (json.JSONDecodeError, ValueError) as e:
                logger.error(f"数据文件格式错误 {file_path}: {e}")
                # 尝试从备份恢复
                backup_prefix = file_path.stem
                if self._restore_from_latest_backup(file_path, backup_prefix):
                    return self._safe_load_data(file_path, default_data)
                else:
                    return default_data.copy()
        
        except Exception as e:
            logger.error(f"加载数据失败 {file_path}: {e}")
            return default_data.copy()
        
        finally:
            if lock_fd:
                self._release_file_lock(lock_fd)
    
    def load_data(self) -> Dict:
        """加载训练数据（安全版本）"""
        return self._safe_load_data(
            self.data_file,
            {"channels": {}, "updated_at": datetime.now().isoformat(), "version": "2.0"}
        )
    
    def _restore_from_latest_backup(self, file_path: Path, backup_prefix: str) -> bool:
        """从最新备份恢复文件"""
        try:
            # 查找最新的有效备份
            backup_files = list(self.backup_dir.glob(f"{backup_prefix}_*.json"))
            if not backup_files:
                logger.warning(f"没有找到备份文件: {backup_prefix}_*.json")
                return False
            
            # 按时间排序，获取最新的
            backup_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
            
            for backup_file in backup_files:
                try:
                    # 验证备份文件完整性
                    if self._verify_json_integrity(backup_file):
                        # 恢复文件
                        shutil.copy2(backup_file, file_path)
                        logger.info(f"从备份恢复成功: {backup_file} -> {file_path}")
                        return True
                    else:
                        logger.warning(f"备份文件损坏，跳过: {backup_file}")
                except Exception as e:
                    logger.error(f"恢复备份失败 {backup_file}: {e}")
            
            logger.error(f"所有备份文件都无效: {backup_prefix}")
            return False
            
        except Exception as e:
            logger.error(f"恢复备份过程失败: {e}")
            return False
    
    def save_data(self, data: Dict):
        """保存训练数据（安全版本，带多重保护）"""
        lock_fd = None
        backup_file = None
        
        try:
            # 获取文件锁
            lock_fd = self._acquire_file_lock(self.data_file)
            
            # 验证输入数据
            if not isinstance(data, dict) or "channels" not in data:
                raise ValueError("无效的训练数据格式")
            
            # 创建保存前备份
            if self.data_file.exists() and self.data_file.stat().st_size > 0:
                backup_file = self._create_backup(self.data_file, "manual_training_data_before_save")
                if not backup_file:
                    logger.warning("创建保存前备份失败，但继续保存")
            
            # 原子写入
            self._atomic_write(self.data_file, data)
            
            # 验证保存结果
            if not self._verify_json_integrity(self.data_file):
                raise RuntimeError("保存后完整性验证失败")
            
            logger.info(f"成功保存训练数据，包含 {len(data.get('channels', {}))} 个频道")
            
            # 清理过期备份（保留最近50个）
            self._cleanup_old_backups("manual_training_data", keep_count=50)
            
        except Exception as e:
            logger.error(f"保存训练数据失败: {e}")
            
            # 尝试从备份恢复
            if backup_file and backup_file.exists():
                try:
                    shutil.copy2(backup_file, self.data_file)
                    logger.info(f"已从备份恢复数据: {backup_file}")
                except Exception as restore_error:
                    logger.error(f"从备份恢复失败: {restore_error}")
            
            raise e
            
        finally:
            if lock_fd:
                self._release_file_lock(lock_fd)
    
    def add_training_sample(self, channel_id: str, channel_name: str, 
                           original: str, tail: str) -> bool:
        """添加训练样本（安全版本，带完整数据验证）"""
        # 输入验证
        if not all([channel_id, channel_name, original]):
            logger.error("输入参数不完整")
            return False
        
        if len(original) > 50000:  # 限制消息长度
            logger.error("消息内容过长")
            return False
        
        lock_fd = None
        backup_file = None
        
        try:
            # 获取文件锁
            lock_fd = self._acquire_file_lock(self.data_file)
            
            # 加载现有数据
            data = self.load_data()
            
            # 创建保存前备份
            if self.data_file.exists() and self.data_file.stat().st_size > 0:
                backup_file = self._create_backup(self.data_file, "manual_training_data_before_add_sample")
            
            # 初始化频道数据
            if channel_id not in data["channels"]:
                data["channels"][channel_id] = {
                    "channel_name": channel_name,
                    "samples": [],
                    "created_at": datetime.now().isoformat()
                }
            
            # 检查重复样本（简单去重）
            existing_samples = data["channels"][channel_id].get("samples", [])
            for sample in existing_samples:
                if (sample.get("original") == original and 
                    sample.get("tail") == tail):
                    logger.warning(f"检测到重复样本，跳过添加: {channel_name}")
                    return True  # 重复不算错误
            
            # 添加新样本
            sample = {
                "original": original,
                "tail": tail,
                "created_at": datetime.now().isoformat(),
                "original_length": len(original),
                "tail_length": len(tail),
                "sample_hash": hashlib.sha256(f"{original}|{tail}".encode()).hexdigest()[:16]
            }
            data["channels"][channel_id]["samples"].append(sample)
            
            # 更新频道信息
            data["channels"][channel_id]["channel_name"] = channel_name
            data["channels"][channel_id]["last_updated"] = datetime.now().isoformat()
            data["channels"][channel_id]["sample_count"] = len(data["channels"][channel_id]["samples"])
            
            # 保存数据
            self.save_data(data)
            
            # 更新历史记录（在主数据保存成功后）
            self.add_history(channel_id, channel_name, len(tail))
            
            logger.info(f"成功添加训练样本: {channel_name}, 样本哈希: {sample['sample_hash']}")
            return True
            
        except Exception as e:
            logger.error(f"添加训练样本失败: {e}")
            
            # 尝试从备份恢复
            if backup_file and backup_file.exists():
                try:
                    shutil.copy2(backup_file, self.data_file)
                    logger.info(f"已从备份恢复数据: {backup_file}")
                except Exception as restore_error:
                    logger.error(f"从备份恢复失败: {restore_error}")
            
            return False
        
        finally:
            if lock_fd:
                self._release_file_lock(lock_fd)
    
    def _cleanup_old_backups(self, backup_prefix: str, keep_count: int = 50):
        """清理过期备份文件"""
        try:
            backup_files = list(self.backup_dir.glob(f"{backup_prefix}_*.json"))
            if len(backup_files) <= keep_count:
                return
            
            # 按修改时间排序，删除最旧的
            backup_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
            files_to_delete = backup_files[keep_count:]
            
            deleted_count = 0
            for file in files_to_delete:
                try:
                    file.unlink()
                    deleted_count += 1
                except Exception as e:
                    logger.error(f"删除备份文件失败 {file}: {e}")
            
            if deleted_count > 0:
                logger.info(f"已清理 {deleted_count} 个过期备份文件")
                
        except Exception as e:
            logger.error(f"清理备份文件失败: {e}")
    
    def add_history(self, channel_id: str, channel_name: str, tail_length: int):
        """添加历史记录（安全版本）"""
        lock_fd = None
        backup_file = None
        
        try:
            # 获取文件锁
            lock_fd = self._acquire_file_lock(self.history_file)
            
            # 加载现有历史数据
            history_data = self._safe_load_data(
                self.history_file,
                {
                    "history": [],
                    "stats": {"total_samples": 0, "channels_trained": 0},
                    "version": "2.0"
                }
            )
            
            # 创建保存前备份
            if self.history_file.exists() and self.history_file.stat().st_size > 0:
                backup_file = self._create_backup(self.history_file, "training_history_before_update")
            
            # 添加新记录
            new_record = {
                "id": len(history_data["history"]) + 1,
                "channel_id": channel_id,
                "channel_name": channel_name,
                "tail_length": tail_length,
                "created_at": datetime.now().isoformat()
            }
            history_data["history"].insert(0, new_record)
            
            # 只保留最近200条（增加保留数量）
            history_data["history"] = history_data["history"][:200]
            
            # 更新统计
            history_data["stats"]["total_samples"] += 1
            
            # 原子保存
            self._atomic_write(self.history_file, history_data)
            
            # 验证保存结果
            if not self._verify_json_integrity(self.history_file):
                raise RuntimeError("历史记录保存后完整性验证失败")
            
            logger.debug(f"成功添加历史记录: {channel_name}")
            
            # 清理过期备份
            self._cleanup_old_backups("training_history", keep_count=30)
            
        except Exception as e:
            logger.error(f"添加历史记录失败: {e}")
            
            # 尝试从备份恢复
            if backup_file and backup_file.exists():
                try:
                    shutil.copy2(backup_file, self.history_file)
                    logger.info(f"已从备份恢复历史数据: {backup_file}")
                except Exception as restore_error:
                    logger.error(f"从备份恢复历史数据失败: {restore_error}")
        
        finally:
            if lock_fd:
                self._release_file_lock(lock_fd)
    
    def get_stats(self) -> Dict:
        """获取统计信息（安全版本）"""
        try:
            # 安全加载数据
            data = self.load_data()
            history_data = self._safe_load_data(
                self.history_file,
                {
                    "history": [],
                    "stats": {"total_samples": 0, "channels_trained": 0},
                    "version": "2.0"
                }
            )
            
            # 计算今日训练数
            today = datetime.now().date()
            today_count = 0
            try:
                today_count = sum(1 for h in history_data.get("history", [])
                                if datetime.fromisoformat(h["created_at"]).date() == today)
            except Exception as e:
                logger.error(f"计算今日训练数失败: {e}")
            
            # 计算统计信息 - 现在只统计全局训练样本
            global_data = data.get("channels", {}).get("global", {})
            total_samples = len(global_data.get("samples", []))
            # 不再需要频道相关的统计
            total_channels = 0
            trained_channels = 0
            
            # 数据完整性检查
            integrity_status = {
                "data_file_valid": self._verify_json_integrity(self.data_file),
                "history_file_valid": self._verify_json_integrity(self.history_file),
                "backup_count": len(list(self.backup_dir.glob("*.json"))),
                "last_backup": None
            }
            
            # 获取最新备份时间
            backup_files = list(self.backup_dir.glob("manual_training_data_*.json"))
            if backup_files:
                latest_backup = max(backup_files, key=lambda f: f.stat().st_mtime)
                integrity_status["last_backup"] = datetime.fromtimestamp(
                    latest_backup.stat().st_mtime
                ).isoformat()
            
            return {
                "totalChannels": total_channels,
                "trainedChannels": trained_channels,
                "totalSamples": total_samples,
                "todayTraining": today_count,
                "integrity": integrity_status
            }
            
        except Exception as e:
            logger.error(f"获取统计失败: {e}")
            return {
                "totalChannels": 0,
                "trainedChannels": 0,
                "totalSamples": 0,
                "todayTraining": 0,
                "integrity": {
                    "data_file_valid": False,
                    "history_file_valid": False,
                    "backup_count": 0,
                    "last_backup": None
                }
            }

# 创建全局训练记录实例
training_record = TrainingRecord()


class AdTrainingManager:
    """广告训练数据管理器"""
    def __init__(self):
        self.data_file = AD_TRAINING_FILE
        self._ensure_file()
    
    def _ensure_file(self):
        """确保广告训练数据文件存在"""
        os.makedirs(self.data_file.parent, exist_ok=True)
        if not self.data_file.exists():
            self._save_data({
                "ad_samples": [],
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            })
    
    def _load_data(self) -> dict:
        """加载广告训练数据"""
        try:
            if self.data_file.exists():
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                    # 兼容处理：将ad_samples统一为samples
                    if "ad_samples" in data and "samples" not in data:
                        data["samples"] = data["ad_samples"]
                        del data["ad_samples"]
                        # 保存更新后的格式
                        self._save_data(data)
                        logger.info("已将'ad_samples'统一为'samples'")
                    elif "ad_samples" in data and "samples" in data:
                        # 如果两个字段都存在，合并它们
                        data["samples"].extend(data["ad_samples"])
                        del data["ad_samples"]
                        self._save_data(data)
                        logger.info("已合并ad_samples到samples")
                    
                    # 确保必要字段存在
                    if "samples" not in data:
                        data["samples"] = []
                    
                    return data
        except Exception as e:
            logger.error(f"加载广告训练数据失败: {e}")
        
        return {
            "samples": [],
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
    
    def _save_data(self, data: dict):
        """保存广告训练数据"""
        try:
            data["updated_at"] = datetime.now().isoformat()
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"保存广告训练数据失败: {e}")
            return False
    
    def add_ad_sample(self, message_id: int, channel_id: str, content: str, 
                      channel_name: str = None, media_paths: List[str] = None) -> bool:
        """添加广告样本"""
        try:
            data = self._load_data()
            
            # 确保字段存在
            if "samples" not in data:
                data["samples"] = []
            
            # 检查是否已存在
            for sample in data["samples"]:
                if sample.get("message_id") == message_id:
                    logger.info(f"广告样本已存在: {message_id}")
                    return True
            
            # 添加新样本
            sample = {
                "message_id": message_id,
                "channel_id": channel_id,
                "channel_name": channel_name,
                "content": content,
                "content_length": len(content),
                "media_paths": media_paths or [],  # 新增媒体文件路径
                "has_media": bool(media_paths),  # 标记是否有媒体
                "created_at": datetime.now().isoformat(),
                "sample_hash": hashlib.sha256(content.encode()).hexdigest()[:16]
            }
            
            data["samples"].append(sample)
            
            # 只保留最近1000个样本
            if len(data["samples"]) > 1000:
                data["samples"] = data["samples"][-1000:]
            
            return self._save_data(data)
            
        except Exception as e:
            logger.error(f"添加广告样本失败: {e}")
            return False
    
    def get_ad_samples(self) -> List[str]:
        """获取所有广告样本内容"""
        data = self._load_data()
        return [s["content"] for s in data.get("samples", [])]
    
    def get_stats(self) -> dict:
        """获取统计信息"""
        data = self._load_data()
        samples = data.get("samples", [])
        
        # 统计每个频道的广告数
        channel_stats = {}
        for sample in samples:
            channel = sample.get("channel_name", sample.get("channel_id", "未知"))
            channel_stats[channel] = channel_stats.get(channel, 0) + 1
        
        return {
            "total_samples": len(samples),
            "channels": len(set(s.get("channel_id") for s in samples if s.get("channel_id"))),
            "channel_stats": channel_stats,
            "last_updated": data.get("updated_at")
        }


# 创建全局广告训练管理器实例
ad_training_manager = AdTrainingManager()

# 新增的API端点
@router.post("/emergency-backup")
async def create_emergency_backup():
    """创建紧急备份"""
    try:
        success = training_record.create_emergency_backup()
        if success:
            return {"success": True, "message": "紧急备份创建成功"}
        else:
            raise HTTPException(status_code=500, detail="紧急备份创建失败")
    except Exception as e:
        logger.error(f"创建紧急备份失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/integrity-report")
async def get_integrity_report():
    """获取数据完整性报告"""
    try:
        report = training_record.get_integrity_report()
        return report
    except Exception as e:
        logger.error(f"获取完整性报告失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/verify-integrity")
async def verify_data_integrity():
    """验证所有数据文件的完整性"""
    try:
        results = {
            "training_data": {
                "file": str(training_record.data_file),
                "exists": training_record.data_file.exists(),
                "valid": training_record._verify_json_integrity(training_record.data_file),
                "size": training_record.data_file.stat().st_size if training_record.data_file.exists() else 0
            },
            "training_history": {
                "file": str(training_record.history_file),
                "exists": training_record.history_file.exists(),
                "valid": training_record._verify_json_integrity(training_record.history_file),
                "size": training_record.history_file.stat().st_size if training_record.history_file.exists() else 0
            }
        }
        
        # 检查备份文件
        backup_files = list(training_record.backup_dir.glob("*.json"))
        results["backups"] = {
            "total_count": len(backup_files),
            "valid_count": sum(1 for f in backup_files if training_record._verify_json_integrity(f)),
            "files": []
        }
        
        for backup_file in sorted(backup_files, key=lambda f: f.stat().st_mtime, reverse=True)[:10]:
            results["backups"]["files"].append({
                "filename": backup_file.name,
                "valid": training_record._verify_json_integrity(backup_file),
                "size": backup_file.stat().st_size
            })
        
        # 判断整体状态
        all_valid = (results["training_data"]["valid"] and 
                    results["training_history"]["valid"])
        
        results["overall_status"] = "healthy" if all_valid else "needs_attention"
        
        return results
        
    except Exception as e:
        logger.error(f"验证数据完整性失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/cleanup-backups")
async def cleanup_old_backups(keep_count: int = 50):
    """清理旧备份文件"""
    try:
        if keep_count < 10:
            raise HTTPException(status_code=400, detail="保留数量不能少于10")
        
        training_record._cleanup_old_backups("manual_training_data", keep_count)
        training_record._cleanup_old_backups("training_history", keep_count)
        training_record._cleanup_old_backups("emergency", keep_count // 2)
        
        # 统计清理后的情况
        remaining_backups = len(list(training_record.backup_dir.glob("*.json")))
        
        return {
            "success": True,
            "message": f"已清理旧备份文件，保留 {keep_count} 个最新备份",
            "remaining_backups": remaining_backups
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"清理备份文件失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/channels")
async def get_channels(db: AsyncSession = Depends(get_db)):
    """获取所有频道列表"""
    try:
        result = await db.execute(
            select(Channel).where(
                and_(
                    Channel.channel_type == 'source',
                    Channel.is_active == True
                )
            ).order_by(Channel.channel_name)
        )
        channels = result.scalars().all()
        
        # 加载训练数据统计
        training_data = training_record.load_data()
        
        channel_list = []
        for channel in channels:
            channel_data = training_data["channels"].get(channel.channel_id, {})
            channel_list.append({
                "id": channel.channel_id,
                "title": channel.channel_title or channel.channel_name or "未命名频道",
                "name": channel.channel_name,
                "username": channel.channel_name,
                "trained_count": len(channel_data.get("samples", []))
            })
        
        return {"channels": channel_list}
    except Exception as e:
        logger.error(f"获取频道列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/stats")
async def get_stats():
    """获取训练统计"""
    return training_record.get_stats()

@router.get("/history")
async def get_history():
    """获取训练历史"""
    try:
        history_data = json.loads(TRAINING_HISTORY_FILE.read_text())
        return {"history": history_data["history"][:20]}  # 返回最近20条
    except Exception as e:
        logger.error(f"获取历史失败: {e}")
        return {"history": []}

@router.post("/submit")
async def submit_training(
    submission: TrainingSubmission,
    db: AsyncSession = Depends(get_db)
):
    """提交训练数据并自动应用"""
    try:
        # 保存训练数据 - 不再需要频道信息，系统是频道无关的
        success = training_record.add_training_sample(
            "global",  # 使用全局标识符代替频道ID
            "全局训练样本",  # 统一名称
            submission.original_message,
            submission.tail_content
        )
        
        if success:
            # 立即应用到当前运行的AI过滤器 - 使用全局模式
            samples = [submission.original_message]
            await ai_filter.learn_channel_pattern("global", samples)
            
            # 自动应用所有全局训练数据
            training_data = training_record.load_data()
            global_data = training_data.get("channels", {}).get("global", {})
            if global_data and global_data.get("samples"):
                # 提取所有原始消息
                all_messages = [s["original"] for s in global_data["samples"]]
                # 学习所有全局模式
                await ai_filter.learn_channel_pattern("global", all_messages)
                logger.info(f"自动应用了 {len(all_messages)} 个全局训练样本")
            
            # 保存AI模式
            ai_filter.save_patterns("data/ai_filter_patterns.json")
            
            # 如果提供了message_id，更新数据库中的消息内容
            if submission.message_id:
                await update_message_after_training(
                    db,
                    submission.message_id,
                    submission.original_message,
                    submission.tail_content
                )
            
            return {"success": True, "message": "训练样本已保存并自动应用"}
        else:
            raise HTTPException(status_code=500, detail="保存训练数据失败")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"提交训练失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/apply")
async def apply_training():
    """应用所有训练数据"""
    try:
        training_data = training_record.load_data()
        
        # 只处理全局训练数据
        global_data = training_data.get("channels", {}).get("global", {})
        samples = global_data.get("samples", [])
        
        if samples:
            # 提取所有原始消息
            messages = [s["original"] for s in samples]
            # 学习全局模式
            success = await ai_filter.learn_channel_pattern("global", messages)
            if success:
                logger.info(f"全局训练成功，{len(samples)} 个样本")
        
        # 保存AI模式
        ai_filter.save_patterns("data/ai_filter_patterns.json")
        
        return {
            "success": True,
            "message": f"成功应用 {len(samples) if samples else 0} 个全局训练样本",
            "trained_samples": len(samples) if samples else 0
        }
    except Exception as e:
        logger.error(f"应用训练失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/clear")
async def clear_training():
    """清除全局训练数据"""
    try:
        data = training_record.load_data()
        
        # 清除全局训练数据
        if "global" in data.get("channels", {}):
            del data["channels"]["global"]
            training_record.save_data(data)
            return {"success": True, "message": "全局训练数据已清除"}
        else:
            return {"success": False, "message": "没有全局训练数据"}
            
    except Exception as e:
        logger.error(f"清除训练数据失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/export")
async def export_training_data():
    """导出训练数据"""
    try:
        data = training_record.load_data()
        return data
    except Exception as e:
        logger.error(f"导出训练数据失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/backups")
async def list_backups():
    """列出所有备份文件"""
    try:
        backup_dir = Path("data/backups")
        if not backup_dir.exists():
            return {"backups": []}
        
        backups = []
        for file in backup_dir.glob("*.json"):
            stat = file.stat()
            backups.append({
                "filename": file.name,
                "size": stat.st_size,
                "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat()
            })
        
        # 按创建时间倒序排序
        backups.sort(key=lambda x: x["created_at"], reverse=True)
        return {"backups": backups}
    except Exception as e:
        logger.error(f"列出备份失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/restore/{backup_filename}")
async def restore_from_backup(backup_filename: str):
    """从备份恢复训练数据"""
    try:
        backup_file = Path("data/backups") / backup_filename
        if not backup_file.exists():
            raise HTTPException(status_code=404, detail="备份文件不存在")
        
        # 读取备份数据
        backup_data = json.loads(backup_file.read_text())
        
        # 备份当前数据
        current_data = training_record.load_data()
        if current_data.get("channels"):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_before_restore = Path("data/backups") / f"before_restore_{timestamp}.json"
            backup_before_restore.write_text(json.dumps(current_data, ensure_ascii=False, indent=2))
            logger.info(f"恢复前备份当前数据到: {backup_before_restore}")
        
        # 恢复数据
        training_record.save_data(backup_data)
        
        return {
            "success": True,
            "message": f"成功从备份 {backup_filename} 恢复数据",
            "restored_channels": len(backup_data.get("channels", {}))
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"恢复备份失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/mark-ad")
async def mark_message_as_ad(
    request: dict,
    db: AsyncSession = Depends(get_db),
    admin: Admin = Depends(check_permission("training.mark_ad"))
):
    """将消息标记为广告并加入训练样本"""
    try:
        message_id = request.get("message_id")
        if not message_id:
            raise HTTPException(status_code=400, detail="缺少消息ID")
        
        # 获取消息详情
        result = await db.execute(
            select(Message).where(Message.id == message_id)
        )
        message = result.scalar_one_or_none()
        
        if not message:
            raise HTTPException(status_code=404, detail="消息不存在")
        
        # 获取频道信息
        channel_result = await db.execute(
            select(Channel).where(Channel.channel_id == message.source_channel)
        )
        channel = channel_result.scalar_one_or_none()
        channel_name = channel.channel_title or channel.channel_name if channel else "未知频道"
        
        # 保存媒体文件到训练目录（如果有）
        saved_media_paths = []
        if message.media_url or message.media_group:
            from app.services.training_media_manager import training_media_manager
            
            # 处理单个媒体文件
            if message.media_url and os.path.exists(message.media_url):
                saved_path = await training_media_manager.save_training_media(
                    source_path=message.media_url,
                    message_id=message.id,
                    media_type=message.media_type,
                    channel_id=message.source_channel,
                    is_ad=True
                )
                if saved_path:
                    saved_media_paths.append(saved_path)
                    logger.info(f"已保存广告媒体文件: {saved_path}")
            
            # 处理组合媒体
            if message.media_group:
                for media_item in message.media_group:
                    file_path = media_item.get('file_path')
                    if file_path and os.path.exists(file_path):
                        saved_path = await training_media_manager.save_training_media(
                            source_path=file_path,
                            message_id=message.id,
                            media_type=media_item.get('media_type', 'photo'),
                            channel_id=message.source_channel,
                            is_ad=True
                        )
                        if saved_path:
                            saved_media_paths.append(saved_path)
                            logger.info(f"已保存广告媒体文件（组合）: {saved_path}")
        
        # 添加到广告训练样本
        content = message.filtered_content or message.content
        if content:
            # 增强训练数据，包含媒体文件路径
            success = ad_training_manager.add_ad_sample(
                message_id=message.id,
                channel_id=message.source_channel,
                content=content,
                channel_name=channel_name,
                media_paths=saved_media_paths  # 新增媒体文件路径
            )
            
            if not success:
                logger.error(f"添加广告样本失败: {message_id}")
                raise HTTPException(
                    status_code=500, 
                    detail="添加广告样本失败，请检查训练数据文件"
                )
        
        # 更新消息状态
        message.is_ad = True
        message.status = "rejected"
        message.filter_reason = "手动标记为广告训练样本"
        message.reviewed_by = "AI训练"
        message.review_time = datetime.now()
        
        await db.commit()
        
        # 触发AI重新训练（异步）
        try:
            ad_samples = ad_training_manager.get_ad_samples()
            if ad_samples:
                # 这里可以调用AI过滤器的训练方法
                await ai_filter.train_ad_classifier(ad_samples, [])
                logger.info(f"已使用 {len(ad_samples)} 个广告样本更新AI模型")
        except Exception as e:
            logger.error(f"更新AI模型失败: {e}")
        
        return {
            "success": True,
            "message": "已标记为广告并加入训练样本"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"标记广告失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ad-stats")
async def get_ad_training_stats():
    """获取广告训练统计信息"""
    try:
        stats = ad_training_manager.get_stats()
        return stats
    except Exception as e:
        logger.error(f"获取广告统计失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# 这个路由已经被下面更完整的实现替代，删除以避免冲突


# ===== 新增的分隔符训练端点 =====

@router.get("/separator-patterns")
async def get_separator_patterns():
    """获取分隔符模式列表"""
    try:
        if SEPARATOR_PATTERNS_FILE.exists():
            data = SafeFileOperation.read_json_safe(SEPARATOR_PATTERNS_FILE)
            return {"patterns": data.get("patterns", [])} if data else {"patterns": []}
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
        if not SafeFileOperation.write_json_safe(SEPARATOR_PATTERNS_FILE, {
            "patterns": patterns,
            "updated_at": datetime.now().isoformat()
        }):
            return {"success": False, "error": "保存数据失败"}
        
        # 更新smart_tail_filter的模式
        from app.services.smart_tail_filter import smart_tail_filter
        smart_tail_filter.separator_patterns = [p['regex'] for p in patterns if p.get('regex')]
        
        logger.info(f"保存了 {len(patterns)} 个分隔符模式")
        return {"success": True, "message": "分隔符模式已保存"}
    except Exception as e:
        logger.error(f"保存分隔符模式失败: {e}")
        return {"success": False, "error": str(e)}


@router.get("/tail-filter-samples")
async def get_tail_filter_samples():
    """获取尾部过滤训练样本（用户真实数据）"""
    try:
        if TAIL_FILTER_SAMPLES_FILE.exists():
            data = SafeFileOperation.read_json_safe(TAIL_FILTER_SAMPLES_FILE)
            samples = data.get("samples", []) if data else []
            
            # 清理样本数据，只保留必要字段
            cleaned_samples = []
            for sample in samples:
                cleaned_sample = {
                    'id': sample.get('id'),
                    'tail_part': sample.get('tail_part', ''),
                    'created_at': sample.get('created_at', '')
                }
                cleaned_samples.append(cleaned_sample)
            
            logger.info(f"返回 {len(cleaned_samples)} 个真实尾部样本")
            return {"samples": cleaned_samples}
        else:
            return {"samples": []}
    except Exception as e:
        logger.error(f"获取尾部过滤样本失败: {e}")
        return {"samples": []}


@router.get("/tail-filter-statistics")
async def get_tail_filter_statistics():
    """获取尾部过滤训练样本统计（只返回数量，不返回内容）"""
    try:
        total_samples = 0
        valid_samples = 0
        samples_with_separator = 0
        today_added = 0
        
        if TAIL_FILTER_SAMPLES_FILE.exists():
            data = SafeFileOperation.read_json_safe(TAIL_FILTER_SAMPLES_FILE)
            samples = data.get("samples", []) if data else []
            
            # 计算统计信息
            total_samples = len(samples)
            valid_samples = len([s for s in samples if s.get('tail_part')])
            samples_with_separator = len([s for s in samples if s.get('separator')])
            
            # 计算今日新增
            today = datetime.now().date().isoformat()
            today_added = len([s for s in samples if s.get('created_at', '').startswith(today)])
        
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
    """获取尾部过滤训练历史（只返回最近记录）"""
    try:
        history = []
        
        if TAIL_FILTER_SAMPLES_FILE.exists():
            data = SafeFileOperation.read_json_safe(TAIL_FILTER_SAMPLES_FILE)
            samples = data.get("samples", []) if data else []
            
            # 筛选有创建时间的样本
            samples_with_time = [s for s in samples if s.get('created_at')]
            
            # 排序并限制数量
            samples_with_time.sort(key=lambda x: x['created_at'], reverse=True)
            samples_with_time = samples_with_time[:limit]
            
            # 转换为历史记录格式
            for sample in samples_with_time:
                history.append({
                    'id': sample.get('id'),
                    'channel_name': '尾部过滤',
                    'message_preview': sample.get('content', '')[:50] + '...' if sample.get('content') else '',
                    'tail_preview': sample.get('tail_part', '')[:30] + '...' if sample.get('tail_part') else '',
                    'created_at': sample.get('created_at')
                })
        
        return {
            "success": True,
            "history": history
        }
    except Exception as e:
        logger.error(f"获取尾部过滤历史失败: {e}")
        return {
            "success": False,
            "history": []
        }


@router.post("/add-ad-sample")
async def add_ad_sample(
    request: dict,
    _admin = Depends(check_permission("training.submit"))
):
    """添加广告训练样本（带相似度检查）"""
    try:
        # 提取参数
        content = request.get("content", "")
        is_ad = request.get("is_ad", True)
        description = request.get("description", "")
        force_add = request.get("force_add", False)  # 强制添加标志
        
        if not content:
            return {"success": False, "message": "内容不能为空"}
        
        # 加载现有的广告训练数据
        ad_training_file = TrainingDataConfig.AD_TRAINING_FILE
        training_data = {"samples": [], "updated_at": None}
        
        if ad_training_file.exists():
            training_data = SafeFileOperation.read_json_safe(ad_training_file)
            if not training_data:
                training_data = {"samples": [], "updated_at": None}
        
        # 检查相似度（如果不是强制添加）
        if not force_add and training_data.get("samples"):
            try:
                from sklearn.feature_extraction.text import TfidfVectorizer
                from sklearn.metrics.pairwise import cosine_similarity
                
                # 获取现有样本内容
                existing_contents = [s.get("content", "") for s in training_data["samples"]]
                
                # 计算相似度
                vectorizer = TfidfVectorizer()
                all_contents = existing_contents + [content]
                tfidf_matrix = vectorizer.fit_transform(all_contents)
                
                # 计算新内容与现有内容的相似度
                new_content_vector = tfidf_matrix[-1]
                existing_vectors = tfidf_matrix[:-1]
                similarities = cosine_similarity(new_content_vector, existing_vectors)[0]
                
                # 检查最高相似度
                max_similarity = similarities.max() if len(similarities) > 0 else 0
                
                if max_similarity >= 0.95:
                    # 完全相同或几乎相同，拒绝添加
                    similar_idx = similarities.argmax()
                    return {
                        "success": False,
                        "message": f"样本已存在（相似度: {int(max_similarity * 100)}%）",
                        "similarity": int(max_similarity * 100),
                        "similar_sample_id": training_data["samples"][similar_idx].get("id")
                    }
                elif max_similarity >= 0.85:
                    # 高度相似，需要确认
                    similar_idx = similarities.argmax()
                    return {
                        "success": False,
                        "message": f"发现相似样本（相似度: {int(max_similarity * 100)}%），确定要添加吗？",
                        "similarity": int(max_similarity * 100),
                        "similar_sample_id": training_data["samples"][similar_idx].get("id"),
                        "need_confirm": True
                    }
                
            except ImportError:
                logger.warning("scikit-learn未安装，跳过相似度检查")
            except Exception as e:
                logger.error(f"相似度检查失败: {e}")
        
        # 生成新样本
        new_sample = {
            "id": len(training_data.get("samples", [])) + 1,
            "content": content,
            "is_ad": is_ad,
            "description": description,
            "created_at": datetime.now().isoformat()
        }
        
        # 添加到样本列表
        if "samples" not in training_data:
            training_data["samples"] = []
        training_data["samples"].append(new_sample)
        training_data["updated_at"] = datetime.now().isoformat()
        
        # 保存到文件
        ad_training_file.parent.mkdir(parents=True, exist_ok=True)
        if not SafeFileOperation.write_json_safe(ad_training_file, training_data):
            return {"success": False, "message": "保存数据失败"}
        
        logger.info(f"添加广告训练样本: is_ad={is_ad}, 长度={len(content)}")
        
        # 触发模型重新加载
        from app.services.ad_detector import ad_detector
        ad_detector._samples_loaded = False
        
        return {
            "success": True,
            "message": "广告样本已添加",
            "sample_id": new_sample["id"]
        }
        
    except Exception as e:
        logger.error(f"添加广告样本失败: {e}")
        return {"success": False, "message": str(e)}


@router.post("/tail-filter-samples")
async def add_tail_filter_sample(
    request: dict,
    db: AsyncSession = Depends(get_db),
    _admin = Depends(check_permission("training.mark_tail"))
):
    """手动添加尾部过滤训练样本（保存到文件 + 智能学习）"""
    try:
        # 提取参数，注意：只保存尾部数据，不保存原始内容
        tail_part = request.get("tailPart", request.get("adPart", ""))  # 兼容旧字段名
        message_id = request.get("message_id")  # 获取消息ID
        
        # 记录接收到的数据（增强日志）
        tail_lines = tail_part.split('\n')
        logger.info(f"收到手动尾部训练请求: tail_part长度={len(tail_part)}字符, {len(tail_lines)}行, message_id={message_id}")
        logger.debug(f"尾部内容预览: {tail_part[:100]}..." if len(tail_part) > 100 else f"尾部内容: {tail_part}")
        
        if not tail_part:
            logger.warning("尾部内容为空")
            return {"success": False, "message": "尾部内容不能为空"}
        
        # 1. 保存到用户的样本文件（只保留尾部数据）
        samples = []
        if TAIL_FILTER_SAMPLES_FILE.exists():
            data = SafeFileOperation.read_json_safe(TAIL_FILTER_SAMPLES_FILE)
            samples = data.get("samples", []) if data else []
        
        # 检查重复
        is_duplicate = False
        existing_id = None
        content_hash = hashlib.md5(tail_part.encode()).hexdigest()
        for sample in samples:
            existing_hash = hashlib.md5(sample.get('tail_part', '').encode()).hexdigest()
            if existing_hash == content_hash:
                is_duplicate = True
                existing_id = sample.get('id')
                logger.info(f"样本已存在，ID: {existing_id}，跳过添加")
                break
        
        # 如果是重复的，使用已存在的ID；否则生成新ID
        if is_duplicate:
            new_id = existing_id
        else:
            new_id = max([s.get('id', 0) for s in samples], default=0) + 1
        
        # 创建新样本（严格只保留尾部数据）
        new_sample = {
            "id": new_id,
            "tail_part": tail_part,
            "created_at": datetime.now().isoformat()
        }
        
        # 如果不是重复，才添加样本并保存
        if not is_duplicate:
            samples.append(new_sample)
            
            # 保存到文件
            if not SafeFileOperation.write_json_safe(TAIL_FILTER_SAMPLES_FILE, {
                "samples": samples,
                "updated_at": datetime.now().isoformat(),
                "description": "尾部过滤训练样本 - 只保留尾部数据"
            }):
                return {"success": False, "message": "保存数据失败"}
            
            logger.info(f"成功保存新的尾部过滤样本: {new_id}")
        
        # 2. 触发智能学习系统学习（基于用户手动样本）
        try:
            from app.services.intelligent_learning_system import intelligent_learning_system
            
            # 从用户添加的样本中学习（不提供原始内容）
            learning_result = intelligent_learning_system.add_training_sample(
                tail_part=tail_part,
                original_content=None,  # 不提供原始内容
                message_id=None  # 不关联特定消息
            )
            logger.info(f"智能学习结果: {learning_result.get('message', 'unknown')}")
        except Exception as e:
            logger.warning(f"智能学习失败，但样本已保存: {e}")
        
        # 3. 重新加载ContentFilter的训练模式
        try:
            from app.services.content_filter import content_filter
            content_filter.reload_trained_patterns()
            logger.info("已重新加载ContentFilter的训练模式")
        except Exception as e:
            logger.error(f"重新加载训练模式失败: {e}")
        
        # 4. 更新消息（如果有message_id）
        if message_id:
            try:
                message_id = int(message_id)
                logger.info(f"更新消息 {message_id} 的过滤内容")
                
                # 调用更新函数
                await update_message_after_training(
                    db,
                    message_id,
                    "",  # 不提供原始内容
                    tail_part  # 尾部内容
                )
                
                logger.info(f"消息 {message_id} 已更新过滤内容")
            except Exception as e:
                logger.error(f"更新消息 {message_id} 失败: {e}")
                if is_duplicate:
                    return {"success": True, "message": f"样本已存在，但更新消息失败: {str(e)}"}
                else:
                    return {"success": True, "message": f"样本已添加，但更新消息失败: {str(e)}"}
        
        # 返回成功消息（对用户来说都是成功的）
        if is_duplicate:
            if message_id:
                return {"success": True, "message": "样本已提交，消息内容已更新", "id": new_id}
            else:
                return {"success": True, "message": "样本已提交成功", "id": new_id}
        else:
            if message_id:
                return {"success": True, "message": "样本已添加，消息内容已更新", "id": new_id}
            else:
                return {"success": True, "message": "样本已添加成功", "id": new_id}
        
    except Exception as e:
        logger.error(f"添加尾部过滤样本失败: {e}")
        return {"success": False, "message": str(e)}


@router.delete("/tail-filter-samples/{sample_id}")
async def delete_tail_filter_sample(sample_id: int):
    """删除尾部过滤训练样本"""
    try:
        # 加载样本
        if not TAIL_FILTER_SAMPLES_FILE.exists():
            return {"success": False, "error": "样本文件不存在"}
        
        with open(TAIL_FILTER_SAMPLES_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            samples = data.get("samples", [])
        
        # 查找并删除
        original_count = len(samples)
        samples = [s for s in samples if s.get('id') != sample_id]
        
        if len(samples) == original_count:
            return {"success": False, "error": "样本不存在"}
        
        # 保存
        if not SafeFileOperation.write_json_safe(TAIL_FILTER_SAMPLES_FILE, {
            "samples": samples,
            "updated_at": datetime.now().isoformat()
        }):
            return {"success": False, "error": "保存数据失败"}
        
        logger.info(f"删除尾部过滤样本: {sample_id}")
        return {"success": True, "message": "样本已删除"}
        
    except Exception as e:
        logger.error(f"删除尾部过滤样本失败: {e}")
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


# ==================== 训练数据管理API ====================

@router.get("/ad-samples")
async def get_ad_samples(
    page: int = 1,
    size: int = 20,
    search: str = None,
    filter: str = "all",
    _admin = Depends(check_permission("training.view"))
):
    """获取广告训练样本列表"""
    try:
        # 加载训练数据
        ad_training_file = TrainingDataConfig.AD_TRAINING_FILE
        
        if not ad_training_file.exists():
            logger.warning(f"训练数据文件不存在: {ad_training_file}")
            return {"samples": [], "total": 0}
        
        data = SafeFileOperation.read_json_safe(ad_training_file)
        
        if not data:
            logger.error("无法读取训练数据文件")
            return {"samples": [], "total": 0}
        
        samples = data.get("samples", [])
        
        # 搜索过滤
        if search:
            samples = [s for s in samples if search.lower() in s.get("content", "").lower()]
        
        # 类型过滤
        if filter == "with_media":
            # TODO: 加载媒体元数据并过滤
            pass
        elif filter == "text_only":
            # TODO: 过滤纯文本样本
            pass
        elif filter == "duplicate":
            # TODO: 标记疑似重复的样本
            pass
        
        # 分页
        total = len(samples)
        start = (page - 1) * size
        end = start + size
        page_samples = samples[start:end]
        
        # 加载媒体文件信息
        media_metadata_file = TrainingDataConfig.AD_MEDIA_METADATA_FILE
        media_files_map = {}
        if media_metadata_file.exists():
            media_data = SafeFileOperation.read_json_safe(media_metadata_file)
            if media_data:
                for file_hash, info in media_data.get("media_files", {}).items():
                    for msg_id in info.get("message_ids", []):
                        if msg_id not in media_files_map:
                            media_files_map[msg_id] = []
                        media_files_map[msg_id].append(info["path"])
        
        # 添加媒体文件信息到样本
        for sample in page_samples:
            sample_id = sample.get("id")
            if sample_id in media_files_map:
                sample["media_files"] = media_files_map[sample_id]
        
        return {
            "samples": page_samples,
            "total": total
        }
        
    except Exception as e:
        logger.error(f"获取广告样本失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ad-samples/{sample_id}")
async def get_ad_sample_detail(
    sample_id: int,
    _admin = Depends(check_permission("training.view"))
):
    """获取单个广告样本详情"""
    try:
        ad_training_file = TrainingDataConfig.AD_TRAINING_FILE
        if not ad_training_file.exists():
            raise HTTPException(status_code=404, detail="训练数据文件不存在")
        
        data = SafeFileOperation.read_json_safe(ad_training_file)
        if not data:
            raise HTTPException(status_code=404, detail="无法读取训练数据文件")
        
        samples = data.get("samples", [])
        for sample in samples:
            if sample.get("id") == sample_id:
                # 加载媒体文件信息
                media_metadata_file = TrainingDataConfig.AD_MEDIA_METADATA_FILE
                if media_metadata_file.exists():
                    with open(media_metadata_file, 'r', encoding='utf-8') as f:
                        media_data = json.load(f)
                        media_files = []
                        for file_hash, info in media_data.get("media_files", {}).items():
                            if sample_id in info.get("message_ids", []):
                                media_files.append(info["path"])
                        if media_files:
                            sample["media_files"] = media_files
                
                return sample
        
        raise HTTPException(status_code=404, detail="样本不存在")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取样本详情失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/ad-samples/{sample_id}")
async def delete_ad_sample(
    sample_id: int,
    _admin = Depends(check_permission("training.manage"))
):
    """删除单个广告样本"""
    try:
        # 加载训练数据
        ad_training_file = TrainingDataConfig.AD_TRAINING_FILE
        if not ad_training_file.exists():
            raise HTTPException(status_code=404, detail="训练数据文件不存在")
        
        data = SafeFileOperation.read_json_safe(ad_training_file)
        if not data:
            raise HTTPException(status_code=404, detail="无法读取训练数据文件")
        
        samples = data.get("samples", [])
        
        # 查找并删除样本
        deleted = False
        for i, sample in enumerate(samples):
            if sample.get("id") == sample_id:
                # 删除媒体文件
                await _delete_sample_media_files(sample_id)
                
                # 删除样本
                samples.pop(i)
                deleted = True
                break
        
        if not deleted:
            raise HTTPException(status_code=404, detail="样本不存在")
        
        # 保存更新后的数据
        data["samples"] = samples
        data["updated_at"] = datetime.now().isoformat()
        
        if not SafeFileOperation.write_json_safe(ad_training_file, data):
            raise HTTPException(status_code=500, detail="保存数据失败")
        
        logger.info(f"删除广告样本 ID={sample_id}")
        return {"success": True, "message": "样本已删除"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除样本失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/ad-samples/batch")
async def delete_ad_samples_batch(
    request: dict,
    _admin = Depends(check_permission("training.manage"))
):
    """批量删除广告样本"""
    try:
        ids = request.get("ids", [])
        if not ids:
            raise HTTPException(status_code=400, detail="未提供要删除的ID")
        
        # 加载训练数据
        ad_training_file = TrainingDataConfig.AD_TRAINING_FILE
        if not ad_training_file.exists():
            raise HTTPException(status_code=404, detail="训练数据文件不存在")
        
        data = SafeFileOperation.read_json_safe(ad_training_file)
        if not data:
            raise HTTPException(status_code=404, detail="无法读取训练数据文件")
        
        samples = data.get("samples", [])
        original_count = len(samples)
        
        # 删除指定的样本
        for sample_id in ids:
            # 删除媒体文件
            await _delete_sample_media_files(sample_id)
        
        # 过滤掉要删除的样本
        samples = [s for s in samples if s.get("id") not in ids]
        deleted_count = original_count - len(samples)
        
        # 保存更新后的数据
        data["samples"] = samples
        data["updated_at"] = datetime.now().isoformat()
        
        if not SafeFileOperation.write_json_safe(ad_training_file, data):
            raise HTTPException(status_code=500, detail="保存数据失败")
        
        logger.info(f"批量删除 {deleted_count} 个广告样本")
        return {"success": True, "message": f"成功删除 {deleted_count} 个样本"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"批量删除失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/statistics")
async def get_training_statistics(
    _admin = Depends(check_permission("training.view"))
):
    """获取训练数据统计信息"""
    try:
        stats = {
            "totalSamples": 0,
            "uniqueSamples": 0,
            "mediaFiles": 0,
            "storageSize": 0
        }
        
        # 统计文本样本
        ad_training_file = TrainingDataConfig.AD_TRAINING_FILE
        if ad_training_file.exists():
            with open(ad_training_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                samples = data.get("samples", [])
                stats["totalSamples"] = len(samples)
                
                # 统计唯一内容
                unique_contents = set()
                for sample in samples:
                    content_hash = hashlib.md5(sample.get("content", "").encode()).hexdigest()
                    unique_contents.add(content_hash)
                stats["uniqueSamples"] = len(unique_contents)
        
        # 统计媒体文件
        media_dir = Path("data/ad_training_data")
        if media_dir.exists():
            total_size = 0
            file_count = 0
            
            # 统计图片
            images_dir = media_dir / "images"
            if images_dir.exists():
                for img_file in images_dir.rglob("*"):
                    if img_file.is_file():
                        file_count += 1
                        total_size += img_file.stat().st_size
            
            # 统计视频
            videos_dir = media_dir / "videos"
            if videos_dir.exists():
                for vid_file in videos_dir.rglob("*"):
                    if vid_file.is_file():
                        file_count += 1
                        total_size += vid_file.stat().st_size
            
            stats["mediaFiles"] = file_count
            stats["storageSize"] = total_size
        
        return stats
        
    except Exception as e:
        logger.error(f"获取统计信息失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ad-samples/reload")
async def reload_ad_samples(
    _admin = Depends(check_permission("training.manage"))
):
    """重新加载广告训练数据到模型"""
    try:
        from app.services.ad_detector import ad_detector
        
        # 清除缓存并重新加载
        ad_detector._samples_loaded = False
        ad_detector.ad_embeddings = []
        
        # 触发重新加载
        ad_detector._load_ad_samples_sync()
        
        logger.info("广告训练数据已重新加载")
        return {"success": True, "message": "模型已重新加载训练数据"}
        
    except Exception as e:
        logger.error(f"重载模型失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def _delete_sample_media_files(sample_id: int):
    """删除样本关联的媒体文件"""
    try:
        media_metadata_file = TrainingDataConfig.AD_MEDIA_METADATA_FILE
        if not media_metadata_file.exists():
            return
        
        with open(media_metadata_file, 'r', encoding='utf-8') as f:
            media_data = json.load(f)
        
        media_files = media_data.get("media_files", {})
        files_to_delete = []
        hashes_to_remove = []
        
        # 查找要删除的文件
        for file_hash, info in media_files.items():
            if sample_id in info.get("message_ids", []):
                info["message_ids"].remove(sample_id)
                
                # 如果没有其他消息引用此文件，标记删除
                if not info["message_ids"]:
                    file_path = Path("data") / info["path"]
                    if file_path.exists():
                        files_to_delete.append(file_path)
                    hashes_to_remove.append(file_hash)
        
        # 删除文件
        for file_path in files_to_delete:
            try:
                file_path.unlink()
                logger.debug(f"删除媒体文件: {file_path}")
            except Exception as e:
                logger.error(f"删除文件失败 {file_path}: {e}")
        
        # 更新元数据
        for hash_key in hashes_to_remove:
            del media_files[hash_key]
        
        media_data["media_files"] = media_files
        media_data["updated_at"] = datetime.now().isoformat()
        
        SafeFileOperation.write_json_safe(media_metadata_file, media_data)
            
    except Exception as e:
        logger.error(f"删除媒体文件失败: {e}")


@router.post("/ad-samples/detect-duplicates")
async def detect_duplicate_samples(
    _admin = Depends(check_permission("training.view"))
):
    """检测重复或相似的样本"""
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
        import numpy as np
        
        # 加载训练数据
        ad_training_file = TrainingDataConfig.AD_TRAINING_FILE
        if not ad_training_file.exists():
            return {"groups": [], "total_duplicates": 0}
        
        data = SafeFileOperation.read_json_safe(ad_training_file)
        if not data:
            raise HTTPException(status_code=404, detail="无法读取训练数据文件")
        
        samples = data.get("samples", [])
        if len(samples) < 2:
            return {"groups": [], "total_duplicates": 0}
        
        # 提取内容
        contents = [s.get("content", "") for s in samples]
        
        # 使用TF-IDF计算相似度
        vectorizer = TfidfVectorizer()
        tfidf_matrix = vectorizer.fit_transform(contents)
        similarity_matrix = cosine_similarity(tfidf_matrix, tfidf_matrix)
        
        # 查找相似样本组
        duplicate_groups = []
        processed = set()
        threshold = 0.95  # 相似度阈值（提高到0.95，只检测高度相似的内容）
        
        # 获取样本的唯一标识
        def get_sample_identifier(sample):
            """获取样本的唯一标识（支持id和message_id）"""
            return sample.get("id") or sample.get("message_id")
        
        for i in range(len(samples)):
            if i in processed:
                continue
            
            # 找出与当前样本相似的所有样本
            similar_indices = np.where(similarity_matrix[i] > threshold)[0]
            if len(similar_indices) > 1:  # 至少有一个相似的（除了自己）
                group = {
                    "similarity": int(similarity_matrix[i][similar_indices].max() * 100),
                    "samples": []
                }
                
                for idx in similar_indices:
                    if idx not in processed:
                        sample_copy = samples[idx].copy()
                        # 确保有正确的ID字段
                        sample_id = get_sample_identifier(sample_copy)
                        if not sample_copy.get("id"):
                            sample_copy["id"] = sample_id  # 确保返回数据中有id字段
                        # 确保keep是Python原生bool类型，而不是numpy.bool_
                        sample_copy["keep"] = bool(idx == similar_indices[0])  # 默认保留第一个
                        # 限制内容长度，避免返回数据过大
                        if len(sample_copy.get("content", "")) > 200:
                            sample_copy["content"] = sample_copy["content"][:200] + "..."
                        group["samples"].append(sample_copy)
                        processed.add(idx)
                
                if len(group["samples"]) > 1:
                    duplicate_groups.append(group)
        
        total_duplicates = sum(len(g["samples"]) for g in duplicate_groups)
        
        return {
            "groups": duplicate_groups,
            "total_duplicates": total_duplicates
        }
        
    except ImportError as e:
        logger.error(f"scikit-learn未安装，无法进行相似度检测: {e}")
        return {"error": "相似度检测功能不可用，请安装scikit-learn"}
    except Exception as e:
        import traceback
        logger.error(f"检测重复样本失败: {e}")
        logger.error(f"详细错误: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"检测重复失败: {str(e)}")


@router.post("/ad-samples/deduplicate")
async def deduplicate_samples(
    request: dict,
    _admin = Depends(check_permission("training.manage"))
):
    """执行去重操作"""
    try:
        to_delete = request.get("to_delete", [])
        
        if not to_delete:
            return {"success": False, "message": "没有要删除的样本"}
        
        # 加载训练数据
        ad_training_file = TrainingDataConfig.AD_TRAINING_FILE
        if not ad_training_file.exists():
            raise HTTPException(status_code=404, detail="训练数据文件不存在")
        
        # 备份原文件
        backup_file = ad_training_file.parent / f"ad_training_data_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        shutil.copy2(ad_training_file, backup_file)
        logger.info(f"创建备份: {backup_file}")
        
        data = SafeFileOperation.read_json_safe(ad_training_file)
        if not data:
            raise HTTPException(status_code=404, detail="无法读取训练数据文件")
        
        samples = data.get("samples", [])
        original_count = len(samples)
        
        # 安全检查：限制单次删除数量
        if len(to_delete) > original_count * 0.2:
            logger.warning(f"尝试删除过多样本: {len(to_delete)}/{original_count}")
            return {
                "success": False,
                "message": f"安全保护：单次删除不能超过总样本数的20%（最多{int(original_count * 0.2)}个）"
            }
        
        # 获取样本的唯一标识
        def get_sample_id(sample):
            """获取样本的唯一标识（支持id和message_id）"""
            return sample.get("id") or sample.get("message_id")
        
        # 删除媒体文件
        for sample_id in to_delete:
            await _delete_sample_media_files(sample_id)
        
        # 过滤掉重复的样本（修复：支持多种ID字段）
        to_delete_set = set(to_delete)  # 转为集合提高性能
        new_samples = []
        for sample in samples:
            sample_id = get_sample_id(sample)
            if sample_id not in to_delete_set:
                new_samples.append(sample)
        
        deleted_count = original_count - len(new_samples)
        samples = new_samples
        
        # 保存更新后的数据
        data["samples"] = samples
        data["updated_at"] = datetime.now().isoformat()
        
        if not SafeFileOperation.write_json_safe(ad_training_file, data):
            raise HTTPException(status_code=500, detail="保存数据失败")
        
        logger.info(f"去重完成: 删除 {deleted_count} 个重复样本")
        
        # 重新加载模型
        from app.services.ad_detector import ad_detector
        ad_detector._samples_loaded = False
        ad_detector._load_ad_samples_sync()
        
        return {
            "success": True,
            "message": f"去重完成，删除了 {deleted_count} 个重复样本",
            "deleted": deleted_count,
            "remaining": len(samples)
        }
        
    except Exception as e:
        logger.error(f"去重操作失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reload-model")
async def reload_training_model(
    _admin = Depends(check_permission("training.manage"))
):
    """重新加载训练模型"""
    try:
        from app.services.ad_detector import ad_detector
        
        # 重新加载广告检测模型
        ad_detector._samples_loaded = False
        ad_detector._load_ad_samples_sync()
        
        # 获取当前样本数量
        ad_training_file = TrainingDataConfig.AD_TRAINING_FILE
        sample_count = 0
        if ad_training_file.exists():
            data = SafeFileOperation.read_json_safe(ad_training_file)
            if data:
                sample_count = len(data.get("samples", []))
        
        logger.info(f"模型重载成功，当前样本数: {sample_count}")
        return {
            "success": True,
            "message": f"模型重载成功，已加载 {sample_count} 个训练样本"
        }
        
    except Exception as e:
        logger.error(f"模型重载失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/media-files")
async def get_media_files(
    _admin = Depends(check_permission("training.view"))
):
    """获取所有媒体文件列表"""
    try:
        media_metadata_file = TrainingDataConfig.AD_MEDIA_METADATA_FILE
        media_dir = Path("data/ad_training_data")
        
        files = []
        stats = {
            "totalFiles": 0,
            "imageCount": 0,
            "videoCount": 0,
            "totalSize": 0,
            "referencedCount": 0,
            "orphanedCount": 0
        }
        
        if media_metadata_file.exists():
            data = SafeFileOperation.read_json_safe(media_metadata_file)
            if data:
                for file_hash, info in data.get("media_files", {}).items():
                    file_path = media_dir / info["path"]
                    
                    # 获取文件大小
                    file_size = 0
                    if file_path.exists():
                        try:
                            file_size = file_path.stat().st_size
                        except:
                            file_size = 0
                    
                    # 使用display_path（缩略图）或原始path
                    display_path = info.get('display_path', info['path'])
                    
                    # 根据实际返回的路径判断文件类型，而不是原始媒体类型
                    file_type = "video" if display_path.startswith("videos/") else "image"
                    
                    file_info = {
                        "hash": file_hash,
                        "name": Path(info["path"]).name,
                        "path": display_path,  # 使用display_path以显示缩略图
                        "originalPath": info['path'],  # 保留原始路径
                        "type": file_type,
                        "size": file_size,
                        "messageIds": info.get("message_ids", []),
                        "createdAt": info.get("saved_at", info.get("created_at", "")),
                        "hasThumbnail": "thumbnail_path" in info or "display_path" in info
                    }
                    
                    files.append(file_info)
                    
                    # 更新统计
                    stats["totalFiles"] += 1
                    if file_type == "image":
                        stats["imageCount"] += 1
                    else:
                        stats["videoCount"] += 1
                    stats["totalSize"] += file_info["size"]
                    
                    if file_info["messageIds"]:
                        stats["referencedCount"] += 1
                    else:
                        stats["orphanedCount"] += 1
        
        return {
            "files": files,
            "stats": stats
        }
        
    except Exception as e:
        logger.error(f"获取媒体文件列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/media-files/{file_hash}")
async def delete_media_file(
    file_hash: str,
    _admin = Depends(check_permission("training.manage"))
):
    """删除指定的媒体文件"""
    try:
        media_metadata_file = TrainingDataConfig.AD_MEDIA_METADATA_FILE
        media_dir = Path("data/ad_training_data")
        
        if not media_metadata_file.exists():
            raise HTTPException(status_code=404, detail="媒体元数据文件不存在")
        
        data = SafeFileOperation.read_json_safe(media_metadata_file)
        if not data or file_hash not in data.get("media_files", {}):
            raise HTTPException(status_code=404, detail="文件不存在")
        
        # 获取文件信息
        file_info = data["media_files"][file_hash]
        file_path = media_dir / file_info["path"]
        
        # 删除实际文件
        if file_path.exists():
            file_path.unlink()
            logger.info(f"删除媒体文件: {file_path}")
        
        # 更新元数据
        del data["media_files"][file_hash]
        data["updated_at"] = datetime.now().isoformat()
        
        SafeFileOperation.write_json_safe(media_metadata_file, data)
        
        return {"success": True, "message": "文件已删除"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除媒体文件失败: {e}")
        return {"success": False, "error": str(e)}


@router.post("/media-files/clean-orphaned")
async def clean_orphaned_media(
    _admin = Depends(check_permission("training.manage"))
):
    """清理未引用的媒体文件"""
    try:
        media_metadata_file = TrainingDataConfig.AD_MEDIA_METADATA_FILE
        media_dir = Path("data/ad_training_data")
        
        if not media_metadata_file.exists():
            return {"success": True, "deleted": 0}
        
        data = SafeFileOperation.read_json_safe(media_metadata_file)
        if not data:
            return {"success": True, "deleted": 0}
        
        deleted_count = 0
        hashes_to_remove = []
        
        for file_hash, info in data.get("media_files", {}).items():
            if not info.get("message_ids", []):
                # 未引用的文件
                file_path = media_dir / info["path"]
                if file_path.exists():
                    file_path.unlink()
                    deleted_count += 1
                    logger.info(f"清理未引用文件: {file_path}")
                hashes_to_remove.append(file_hash)
        
        # 更新元数据
        for hash_key in hashes_to_remove:
            del data["media_files"][hash_key]
        
        data["updated_at"] = datetime.now().isoformat()
        SafeFileOperation.write_json_safe(media_metadata_file, data)
        
        return {"success": True, "deleted": deleted_count}
        
    except Exception as e:
        logger.error(f"清理未引用媒体文件失败: {e}")
        return {"success": False, "error": str(e)}


@router.get("/media-files/duplicates")
async def find_duplicate_media(
    _admin = Depends(check_permission("training.view"))
):
    """检测视觉重复的媒体文件"""
    try:
        from app.services.visual_similarity import VisualSimilarityDetector
        from app.services.training_media_manager import training_media_manager
        
        media_metadata_file = TrainingDataConfig.AD_MEDIA_METADATA_FILE
        media_dir = Path("data/ad_training_data")
        
        if not media_metadata_file.exists():
            return {"success": True, "duplicates": [], "stats": {"groups": 0, "total_duplicates": 0}}
        
        data = SafeFileOperation.read_json_safe(media_metadata_file)
        if not data or "media_files" not in data:
            return {"success": True, "duplicates": [], "stats": {"groups": 0, "total_duplicates": 0}}
        
        visual_detector = VisualSimilarityDetector()
        duplicate_groups = []
        processed = set()
        
        # 遍历所有媒体文件，查找视觉相似的组
        for file_hash1, file_info1 in data["media_files"].items():
            if file_hash1 in processed:
                continue
            
            # 如果没有视觉哈希，跳过
            if "visual_hashes" not in file_info1:
                continue
            
            current_group = [file_info1]
            processed.add(file_hash1)
            
            # 查找与当前文件相似的其他文件
            for file_hash2, file_info2 in data["media_files"].items():
                if file_hash2 == file_hash1 or file_hash2 in processed:
                    continue
                
                if "visual_hashes" not in file_info2:
                    continue
                
                # 比较视觉哈希
                similarities = visual_detector.compare_hashes(
                    file_info1["visual_hashes"],
                    file_info2["visual_hashes"]
                )
                
                # 检查是否有足够高的相似度
                for hash_type, similarity, distance in similarities:
                    if similarity >= 0.85:  # 85%相似度阈值
                        current_group.append(file_info2)
                        processed.add(file_hash2)
                        break
            
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
        return {"success": False, "error": str(e)}


@router.post("/media-files/deduplicate")
async def deduplicate_media(
    _admin = Depends(check_permission("training.manage"))
):
    """执行视觉去重"""
    try:
        from app.services.visual_similarity import VisualSimilarityDetector
        import shutil
        
        media_metadata_file = TrainingDataConfig.AD_MEDIA_METADATA_FILE
        media_dir = Path("data/ad_training_data")
        
        if not media_metadata_file.exists():
            return {"success": True, "deleted": 0, "merged": 0}
        
        # 备份元数据
        backup_file = media_metadata_file.parent / f"media_metadata_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        shutil.copy2(media_metadata_file, backup_file)
        logger.info(f"已备份元数据到: {backup_file}")
        
        data = SafeFileOperation.read_json_safe(media_metadata_file)
        if not data or "media_files" not in data:
            return {"success": True, "deleted": 0, "merged": 0}
        
        visual_detector = VisualSimilarityDetector()
        deleted_count = 0
        merged_count = 0
        processed = set()
        
        # 创建新的媒体文件字典（去重后的）
        new_media_files = {}
        
        # 遍历所有媒体文件，查找视觉相似的组
        for file_hash, file_info in data["media_files"].items():
            if file_hash in processed:
                continue
            
            # 如果没有视觉哈希，直接保留
            if "visual_hashes" not in file_info:
                new_media_files[file_hash] = file_info
                processed.add(file_hash)
                continue
            
            # 收集与当前文件相似的所有文件
            similar_files = [(file_hash, file_info)]
            processed.add(file_hash)
            
            for other_hash, other_info in data["media_files"].items():
                if other_hash == file_hash or other_hash in processed:
                    continue
                
                if "visual_hashes" not in other_info:
                    continue
                
                # 比较视觉哈希
                similarities = visual_detector.compare_hashes(
                    file_info["visual_hashes"],
                    other_info["visual_hashes"]
                )
                
                # 检查是否有足够高的相似度
                for hash_type, similarity, distance in similarities:
                    if similarity >= 0.85:  # 85%相似度阈值
                        similar_files.append((other_hash, other_info))
                        processed.add(other_hash)
                        break
            
            # 如果有多个相似文件，合并它们
            if len(similar_files) > 1:
                # 选择要保留的文件（优先保留引用最多的，其次是最小的）
                best_file = max(similar_files, key=lambda x: (
                    len(x[1].get("message_ids", [])),  # 引用数量
                    -x[1].get("file_size", float('inf'))  # 文件大小（越小越好）
                ))
                
                # 合并所有message_ids到保留的文件
                all_message_ids = list(set(sum([f[1].get("message_ids", []) for f in similar_files], [])))
                best_file[1]["message_ids"] = all_message_ids
                
                # 保留最佳文件
                new_media_files[best_file[0]] = best_file[1]
                
                # 删除其他文件
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
        
        SafeFileOperation.write_json_safe(media_metadata_file, data)
        
        return {
            "success": True,
            "deleted": deleted_count,
            "merged": merged_count,
            "backup_file": str(backup_file.name)
        }
        
    except Exception as e:
        logger.error(f"执行视觉去重失败: {e}")
        return {"success": False, "error": str(e)}


@router.post("/media-files/rebuild-visual-hashes")
async def rebuild_visual_hashes(
    _admin = Depends(check_permission("training.manage"))
):
    """为所有现有媒体文件重建视觉哈希"""
    try:
        from app.services.visual_similarity import VisualSimilarityDetector
        import cv2
        
        media_metadata_file = TrainingDataConfig.AD_MEDIA_METADATA_FILE
        media_dir = Path("data/ad_training_data")
        
        if not media_metadata_file.exists():
            return {"success": True, "processed": 0, "skipped": 0}
        
        data = SafeFileOperation.read_json_safe(media_metadata_file)
        if not data or "media_files" not in data:
            return {"success": True, "processed": 0, "skipped": 0}
        
        visual_detector = VisualSimilarityDetector()
        processed_count = 0
        skipped_count = 0
        error_count = 0
        
        # 遍历所有媒体文件
        for file_hash, file_info in data["media_files"].items():
            # 如果已有视觉哈希，跳过（除非强制重建）
            if "visual_hashes" in file_info:
                skipped_count += 1
                continue
            
            file_path = media_dir / file_info["path"]
            if not file_path.exists():
                logger.warning(f"文件不存在，跳过: {file_path}")
                error_count += 1
                continue
            
            try:
                media_data = None
                media_type = file_info.get("media_type", "")
                
                if media_type in ["photo", "image"] or file_path.suffix.lower() in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
                    # 读取图片数据
                    with open(file_path, 'rb') as f:
                        media_data = f.read()
                elif media_type in ["video", "animation"] or file_path.suffix.lower() in ['.mp4', '.avi', '.mov', '.webm']:
                    # 提取视频第一帧
                    cap = cv2.VideoCapture(str(file_path))
                    ret, frame = cap.read()
                    cap.release()
                    
                    if ret:
                        _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                        media_data = buffer.tobytes()
                
                if media_data:
                    # 计算视觉哈希
                    visual_hashes = visual_detector.calculate_perceptual_hashes(media_data)
                    file_info["visual_hashes"] = visual_hashes
                    processed_count += 1
                    logger.info(f"已为文件生成视觉哈希: {file_path}")
                else:
                    skipped_count += 1
                    
            except Exception as e:
                logger.error(f"处理文件失败 {file_path}: {e}")
                error_count += 1
        
        # 保存更新后的元数据
        data["updated_at"] = datetime.now().isoformat()
        data["visual_hash_rebuild"] = {
            "timestamp": datetime.now().isoformat(),
            "processed": processed_count,
            "skipped": skipped_count,
            "errors": error_count
        }
        SafeFileOperation.write_json_safe(media_metadata_file, data)
        
        return {
            "success": True,
            "processed": processed_count,
            "skipped": skipped_count,
            "errors": error_count
        }
        
    except Exception as e:
        logger.error(f"重建视觉哈希失败: {e}")
        return {"success": False, "error": str(e)}


@router.post("/optimize-storage")
async def optimize_storage(
    _admin = Depends(check_permission("training.manage"))
):
    """优化存储空间（视频转快照等）"""
    try:
        import cv2
        from app.services.training_media_manager import training_media_manager
        
        saved_space = 0
        processed_videos = 0
        errors = []
        
        # 处理视频文件
        videos_dir = Path("data/ad_training_data/videos")
        media_metadata_file = TrainingDataConfig.AD_MEDIA_METADATA_FILE
        
        if videos_dir.exists():
            # 支持 .mp4 和 .MP4 扩展名
            video_files = list(videos_dir.rglob("*.mp4")) + list(videos_dir.rglob("*.MP4"))
            
            # 读取元数据
            metadata = {}
            if media_metadata_file.exists():
                metadata = SafeFileOperation.read_json_safe(media_metadata_file) or {}
            
            for video_file in video_files:
                try:
                    # 读取视频第一帧
                    cap = cv2.VideoCapture(str(video_file))
                    ret, frame = cap.read()
                    cap.release()
                    
                    if ret:
                        # 保存为图片，使用原文件名格式（不加_snapshot后缀）
                        image_name = video_file.stem + ".jpg"
                        # 保存到相同的年月目录结构中
                        image_path = videos_dir.parent / "images" / video_file.parent.name / image_name
                        image_path.parent.mkdir(parents=True, exist_ok=True)
                        
                        # 使用质量70（减少文件大小，保持可接受的质量）
                        cv2.imwrite(str(image_path), frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
                        
                        # 计算节省的空间
                        original_size = video_file.stat().st_size
                        new_size = image_path.stat().st_size
                        saved_space += original_size - new_size
                        
                        # 更新元数据
                        if "media_files" in metadata:
                            # 查找并更新该视频的元数据
                            # 确保路径不包含ad_training_data前缀
                            relative_video_path = str(video_file.relative_to(Path("data/ad_training_data")))
                            relative_image_path = str(image_path.relative_to(Path("data/ad_training_data")))
                            
                            # 移除可能的ad_training_data前缀
                            if relative_video_path.startswith("ad_training_data/"):
                                relative_video_path = relative_video_path.replace("ad_training_data/", "", 1)
                            if relative_image_path.startswith("ad_training_data/"):
                                relative_image_path = relative_image_path.replace("ad_training_data/", "", 1)
                            
                            for file_hash, info in metadata["media_files"].items():
                                if info.get("path") == relative_video_path:
                                    # 更新路径和类型
                                    info["path"] = relative_image_path
                                    info["type"] = "image"
                                    info["optimized"] = True
                                    info["original_size"] = original_size
                                    info["optimized_size"] = new_size
                                    logger.debug(f"更新元数据: {relative_video_path} -> {relative_image_path}")
                                    break
                        
                        # 删除原视频
                        video_file.unlink()
                        processed_videos += 1
                        
                        logger.info(f"转换视频为快照: {video_file.name} -> {image_name}, 节省 {(original_size - new_size) / 1024:.1f}KB")
                    else:
                        errors.append(f"无法读取视频: {video_file.name}")
                        logger.warning(f"无法读取视频第一帧: {video_file}")
                    
                except Exception as e:
                    errors.append(f"{video_file.name}: {str(e)}")
                    logger.error(f"处理视频失败 {video_file}: {e}")
            
            # 保存更新后的元数据
            if metadata and "media_files" in metadata:
                metadata["updated_at"] = datetime.now().isoformat()
                SafeFileOperation.write_json_safe(media_metadata_file, metadata)
                logger.info("元数据已更新")
        
        result = {
            "success": True,
            "message": f"优化完成，处理了 {processed_videos} 个视频",
            "saved_space": saved_space,
            "processed_videos": processed_videos,
            "saved_mb": round(saved_space / 1024 / 1024, 2)
        }
        
        if errors:
            result["errors"] = errors
            result["message"] += f"，{len(errors)} 个失败"
        
        return result
        
    except ImportError:
        return {"success": False, "error": "OpenCV未正确安装，无法进行视频处理"}
    except Exception as e:
        logger.error(f"优化存储失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/optimize-storage-sse")
async def optimize_storage_sse(
    _admin = Depends(check_permission("training.manage"))
):
    """优化存储空间（支持进度推送的SSE版本）"""
    
    async def generate():
        try:
            import cv2
            from app.services.training_media_manager import training_media_manager
            
            saved_space = 0
            processed_videos = 0
            errors = []
            
            # 发送初始化消息
            yield f"data: {json.dumps({'type': 'init', 'message': '开始优化视频存储...'})}\n\n"
            await asyncio.sleep(0.1)
            
            # 处理视频文件
            videos_dir = Path("data/ad_training_data/videos")
            media_metadata_file = TrainingDataConfig.AD_MEDIA_METADATA_FILE
            
            if not videos_dir.exists():
                yield f"data: {json.dumps({'type': 'error', 'message': '视频目录不存在'})}\n\n"
                return
            
            # 支持 .mp4 和 .MP4 扩展名
            video_files = list(videos_dir.rglob("*.mp4")) + list(videos_dir.rglob("*.MP4"))
            total_videos = len(video_files)
            
            if total_videos == 0:
                yield f"data: {json.dumps({'type': 'complete', 'message': '没有找到视频文件', 'processed': 0, 'total': 0, 'saved_mb': 0, 'errors': 0})}\n\n"
                return
            
            # 发送统计信息
            total_size = sum(f.stat().st_size for f in video_files)
            yield f"data: {json.dumps({'type': 'stats', 'total': total_videos, 'total_size_mb': round(total_size/1024/1024, 2)})}\n\n"
            await asyncio.sleep(0.1)
            
            # 读取元数据
            metadata = {}
            if media_metadata_file.exists():
                metadata = SafeFileOperation.read_json_safe(media_metadata_file) or {}
            
            # 处理每个视频
            for index, video_file in enumerate(video_files):
                try:
                    # 发送当前处理进度
                    progress = (index / total_videos) * 100
                    yield f"data: {json.dumps({'type': 'progress', 'current': index + 1, 'total': total_videos, 'percent': round(progress, 1), 'file': video_file.name})}\n\n"
                    await asyncio.sleep(0.01)  # 让出控制权
                    
                    # 读取视频第一帧
                    cap = cv2.VideoCapture(str(video_file))
                    ret, frame = cap.read()
                    cap.release()
                    
                    if ret:
                        # 保存为图片
                        image_name = video_file.stem + ".jpg"
                        image_path = videos_dir.parent / "images" / video_file.parent.name / image_name
                        image_path.parent.mkdir(parents=True, exist_ok=True)
                        
                        # 使用质量70
                        cv2.imwrite(str(image_path), frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
                        
                        # 计算节省的空间
                        original_size = video_file.stat().st_size
                        new_size = image_path.stat().st_size
                        saved_space += original_size - new_size
                        
                        # 更新元数据
                        if "media_files" in metadata:
                            # 确保路径不包含ad_training_data前缀
                            relative_video_path = str(video_file.relative_to(Path("data/ad_training_data")))
                            relative_image_path = str(image_path.relative_to(Path("data/ad_training_data")))
                            
                            # 移除可能的ad_training_data前缀
                            if relative_video_path.startswith("ad_training_data/"):
                                relative_video_path = relative_video_path.replace("ad_training_data/", "", 1)
                            if relative_image_path.startswith("ad_training_data/"):
                                relative_image_path = relative_image_path.replace("ad_training_data/", "", 1)
                            
                            for file_hash, info in metadata["media_files"].items():
                                if info.get("path") == relative_video_path:
                                    info["path"] = relative_image_path
                                    info["type"] = "image"
                                    info["optimized"] = True
                                    info["original_size"] = original_size
                                    info["optimized_size"] = new_size
                                    break
                        
                        # 删除原视频
                        video_file.unlink()
                        processed_videos += 1
                        
                        # 发送成功消息
                        saved_kb = (original_size - new_size) / 1024
                        yield f"data: {json.dumps({'type': 'file_done', 'file': video_file.name, 'saved_kb': round(saved_kb, 1)})}\n\n"
                        
                    else:
                        error_msg = f"无法读取视频: {video_file.name}"
                        errors.append(error_msg)
                        yield f"data: {json.dumps({'type': 'file_error', 'file': video_file.name, 'error': '无法读取视频第一帧'})}\n\n"
                        logger.warning(f"无法读取视频第一帧: {video_file}")
                    
                except Exception as e:
                    error_msg = f"{video_file.name}: {str(e)}"
                    errors.append(error_msg)
                    yield f"data: {json.dumps({'type': 'file_error', 'file': video_file.name, 'error': str(e)})}\n\n"
                    logger.error(f"处理视频失败 {video_file}: {e}")
                
                await asyncio.sleep(0.01)  # 让出控制权
            
            # 保存更新后的元数据
            if metadata and "media_files" in metadata:
                metadata["updated_at"] = datetime.now().isoformat()
                SafeFileOperation.write_json_safe(media_metadata_file, metadata)
                logger.info("元数据已更新")
            
            # 发送完成消息
            result = {
                'type': 'complete',
                'processed': processed_videos,
                'total': total_videos,
                'saved_mb': round(saved_space / 1024 / 1024, 2),
                'errors': len(errors)
            }
            
            if errors:
                result['error_list'] = errors[:5]  # 只显示前5个错误
            
            yield f"data: {json.dumps(result)}\n\n"
            await asyncio.sleep(0.1)  # 确保完成消息被发送
            
        except ImportError:
            yield f"data: {json.dumps({'type': 'error', 'message': 'OpenCV未正确安装，无法进行视频处理'})}\n\n"
            await asyncio.sleep(0.1)
        except Exception as e:
            logger.error(f"优化存储失败: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
            await asyncio.sleep(0.1)
        finally:
            # 记录SSE流结束
            logger.info("SSE流处理完成")
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用nginx缓冲
            "Access-Control-Allow-Origin": "*",
        }
    )


# =================== OCR样本管理相关API ===================

@router.get("/ocr-samples")
async def get_ocr_samples(
    limit: int = 100,
    offset: int = 0,
    is_ad: Optional[bool] = None,
    auto_rejected: Optional[bool] = None,
    min_score: Optional[float] = None,
    _admin = Depends(check_permission("training.view"))
):
    """获取OCR样本列表"""
    try:
        from app.services.ocr_sample_manager import ocr_sample_manager
        
        samples = await ocr_sample_manager.get_samples(
            limit=limit,
            offset=offset,
            is_ad=is_ad,
            auto_rejected=auto_rejected,
            min_score=min_score
        )
        
        return {
            "success": True,
            "samples": samples,
            "total": len(samples),
            "params": {
                "limit": limit,
                "offset": offset,
                "is_ad": is_ad,
                "auto_rejected": auto_rejected,
                "min_score": min_score
            }
        }
        
    except Exception as e:
        logger.error(f"获取OCR样本失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ocr-samples/statistics")
async def get_ocr_statistics(
    _admin = Depends(check_permission("training.view"))
):
    """获取OCR样本统计信息"""
    try:
        from app.services.ocr_sample_manager import ocr_sample_manager
        
        stats = await ocr_sample_manager.get_statistics()
        
        return {
            "success": True,
            "statistics": stats
        }
        
    except Exception as e:
        logger.error(f"获取OCR统计信息失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ocr-samples/learn")
async def learn_from_ocr_samples(
    _admin = Depends(check_permission("training.manage"))
):
    """从OCR样本中学习新的广告模式"""
    try:
        from app.services.ocr_sample_manager import ocr_sample_manager
        
        result = await ocr_sample_manager.learn_from_samples()
        
        return result
        
    except Exception as e:
        logger.error(f"OCR样本学习失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/ocr-samples/{sample_id}")
async def delete_ocr_sample(
    sample_id: str,
    _admin = Depends(check_permission("training.manage"))
):
    """删除OCR样本"""
    try:
        from app.services.ocr_sample_manager import ocr_sample_manager
        
        success = await ocr_sample_manager.delete_sample(sample_id)
        
        if success:
            return {"success": True, "message": "样本已删除"}
        else:
            return {"success": False, "message": "样本不存在或删除失败"}
        
    except Exception as e:
        logger.error(f"删除OCR样本失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ocr-samples/export")
async def export_ocr_samples(
    _admin = Depends(check_permission("training.manage"))
):
    """导出OCR样本用于训练"""
    try:
        from app.services.ocr_sample_manager import ocr_sample_manager
        
        output_file = await ocr_sample_manager.export_for_training()
        
        return {
            "success": True,
            "export_file": output_file,
            "message": "OCR训练数据导出成功"
        }
        
    except Exception as e:
        logger.error(f"导出OCR样本失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/media-files/{file_hash}/ocr")
async def get_media_file_ocr(
    file_hash: str,
    _admin = Depends(check_permission("training.view"))
):
    """获取指定媒体文件的OCR识别结果"""
    try:
        from app.services.ocr_service import ocr_service
        
        # 获取文件信息
        media_metadata_file = TrainingDataConfig.AD_MEDIA_METADATA_FILE
        media_dir = Path("data/ad_training_data")
        
        if not media_metadata_file.exists():
            raise HTTPException(status_code=404, detail="媒体元数据文件不存在")
        
        data = SafeFileOperation.read_json_safe(media_metadata_file)
        if not data or file_hash not in data.get("media_files", {}):
            raise HTTPException(status_code=404, detail="文件不存在")
        
        file_info = data["media_files"][file_hash]
        file_path = media_dir / file_info["path"]
        
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="媒体文件不存在")
        
        # 只处理图片文件
        if file_info.get("type") != "image":
            raise HTTPException(status_code=400, detail="只支持图片文件的OCR识别")
        
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