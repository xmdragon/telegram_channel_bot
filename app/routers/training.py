"""
手动训练API路由
"""
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import json
import os
import fcntl
import time
import shutil
import hashlib
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import threading

from app.core.database import get_db, Channel, Message
from app.services.ai_filter import ai_filter
from pydantic import BaseModel
import logging

logger = logging.getLogger(__name__)

router = APIRouter(tags=["training"])

async def update_message_after_training(
    db: AsyncSession,
    message_id: int,
    original_message: str,
    tail_content: str
):
    """
    训练后更新消息内容
    1. 更新数据库中的filtered_content
    2. 编辑审核群中的消息
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
        
        # 计算过滤后的内容（去除尾部）
        if tail_content and tail_content in original_message:
            # 找到尾部内容的位置并截断
            tail_index = original_message.find(tail_content)
            filtered_content = original_message[:tail_index].rstrip()
        else:
            filtered_content = original_message
        
        # 更新数据库中的过滤内容
        message.filtered_content = filtered_content
        message.is_ad = False  # 训练后通常意味着不是广告
        await db.commit()
        
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

# 训练数据文件路径（挂载到./data目录）
TRAINING_DATA_FILE = Path("data/manual_training_data.json")
TRAINING_HISTORY_FILE = Path("data/training_history.json")
AD_TRAINING_FILE = Path("data/ad_training_data.json")  # 新增：广告训练数据文件

class TrainingSubmission(BaseModel):
    """训练数据提交模型"""
    channel_id: str
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
            
            # 计算统计信息
            channels = data.get("channels", {})
            total_channels = len(channels)
            trained_channels = sum(1 for c in channels.values() 
                                 if c.get("samples") and len(c.get("samples", [])) > 0)
            total_samples = sum(len(c.get("samples", [])) for c in channels.values())
            
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
                    return json.load(f)
        except Exception as e:
            logger.error(f"加载广告训练数据失败: {e}")
        
        return {
            "ad_samples": [],
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
                      channel_name: str = None) -> bool:
        """添加广告样本"""
        try:
            data = self._load_data()
            
            # 检查是否已存在
            for sample in data["ad_samples"]:
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
                "created_at": datetime.now().isoformat(),
                "sample_hash": hashlib.sha256(content.encode()).hexdigest()[:16]
            }
            
            data["ad_samples"].append(sample)
            
            # 只保留最近1000个样本
            if len(data["ad_samples"]) > 1000:
                data["ad_samples"] = data["ad_samples"][-1000:]
            
            return self._save_data(data)
            
        except Exception as e:
            logger.error(f"添加广告样本失败: {e}")
            return False
    
    def get_ad_samples(self) -> List[str]:
        """获取所有广告样本内容"""
        data = self._load_data()
        return [s["content"] for s in data.get("ad_samples", [])]
    
    def get_stats(self) -> dict:
        """获取统计信息"""
        data = self._load_data()
        samples = data.get("ad_samples", [])
        
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
    """提交训练数据"""
    try:
        # 获取频道信息
        result = await db.execute(
            select(Channel).where(Channel.channel_id == submission.channel_id)
        )
        channel = result.scalar_one_or_none()
        
        if not channel:
            raise HTTPException(status_code=404, detail="频道不存在")
        
        channel_name = channel.channel_name or "未命名频道"
        
        # 保存训练数据
        success = training_record.add_training_sample(
            submission.channel_id,
            channel_name,
            submission.original_message,
            submission.tail_content
        )
        
        if success:
            # 立即应用到当前运行的AI过滤器
            samples = [submission.original_message]
            await ai_filter.learn_channel_pattern(submission.channel_id, samples)
            
            # 如果提供了message_id，更新数据库中的消息内容
            if submission.message_id:
                await update_message_after_training(
                    db,
                    submission.message_id,
                    submission.original_message,
                    submission.tail_content
                )
            
            return {"success": True, "message": "训练样本已保存，消息内容已更新"}
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
        
        success_count = 0
        for channel_id, channel_data in training_data["channels"].items():
            samples = channel_data.get("samples", [])
            if samples:
                # 提取所有原始消息
                messages = [s["original"] for s in samples]
                # 学习该频道的模式
                success = await ai_filter.learn_channel_pattern(channel_id, messages)
                if success:
                    success_count += 1
                    logger.info(f"频道 {channel_id} 训练成功，{len(samples)} 个样本")
        
        # 保存AI模式
        ai_filter.save_patterns("data/ai_filter_patterns.json")
        
        return {
            "success": True,
            "message": f"成功训练 {success_count} 个频道",
            "trained_channels": success_count
        }
    except Exception as e:
        logger.error(f"应用训练失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/clear/{channel_id}")
async def clear_channel_training(channel_id: str):
    """清除某个频道的训练数据"""
    try:
        data = training_record.load_data()
        
        if channel_id in data["channels"]:
            del data["channels"][channel_id]
            training_record.save_data(data)
            return {"success": True, "message": "频道训练数据已清除"}
        else:
            return {"success": False, "message": "频道没有训练数据"}
            
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
    db: AsyncSession = Depends(get_db)
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
        
        # 添加到广告训练样本
        content = message.filtered_content or message.content
        if content:
            success = ad_training_manager.add_ad_sample(
                message_id=message.id,
                channel_id=message.source_channel,
                content=content,
                channel_name=channel_name
            )
            
            if not success:
                logger.warning(f"添加广告样本失败，但继续处理消息: {message_id}")
        
        # 更新消息状态
        message.is_ad = True
        message.status = "rejected"
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


@router.get("/ad-samples")
async def get_ad_samples(limit: int = 10):
    """获取最近的广告样本"""
    try:
        data = ad_training_manager._load_data()
        samples = data.get("ad_samples", [])
        
        # 返回最近的样本
        recent_samples = samples[-limit:] if len(samples) > limit else samples
        recent_samples.reverse()  # 最新的在前
        
        return {
            "total": len(samples),
            "samples": recent_samples
        }
    except Exception as e:
        logger.error(f"获取广告样本失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))