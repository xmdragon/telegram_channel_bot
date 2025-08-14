"""
自适应学习系统
从用户审核反馈中学习，不断优化广告检测能力
"""
import logging
import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
# 移除数据库依赖，改为基于文件的数据管理
from app.core.training_config import TrainingDataConfig

logger = logging.getLogger(__name__)


class AdaptiveLearningSystem:
    """自适应学习系统"""
    
    def __init__(self):
        self.feedback_file = TrainingDataConfig.FEEDBACK_LEARNING_FILE
        self.ad_samples_file = TrainingDataConfig.AD_TRAINING_FILE
        self.normal_samples_file = TrainingDataConfig.NORMAL_TRAINING_FILE
        self.learning_threshold = 50  # 累积多少反馈后触发学习
        self.feedback_buffer = []
        
        # 确保数据目录存在
        self.feedback_file.parent.mkdir(exist_ok=True)
        
        # 加载历史反馈
        self._load_feedback_history()
    
    def _load_feedback_history(self):
        """加载历史反馈数据"""
        try:
            if self.feedback_file.exists():
                with open(self.feedback_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.feedback_buffer = data.get('feedback_buffer', [])
                    logger.info(f"加载了 {len(self.feedback_buffer)} 条历史反馈")
        except Exception as e:
            logger.error(f"加载反馈历史失败: {e}")
            self.feedback_buffer = []
    
    async def record_feedback_to_file(self, feedback_data: Dict):
        """
        将反馈数据记录到文件
        
        Args:
            feedback_data: 包含message_id, action, reviewer, content等的字典
        """
        try:
            # 添加到缓冲区
            self.feedback_buffer.append(feedback_data)
            
            # 保存到文件
            with open(self.feedback_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'feedback_buffer': self.feedback_buffer,
                    'last_updated': datetime.now().isoformat()
                }, f, ensure_ascii=False, indent=2)
            
            logger.debug(f"记录反馈: {feedback_data['action']} for message {feedback_data['message_id']}")
            
            # 处理拒绝的内容，添加到广告样本
            if feedback_data['action'] == 'rejected' and feedback_data.get('content'):
                await self.add_ad_sample_to_file(feedback_data['content'])
            
            # 检查是否需要触发批量学习
            if len(self.feedback_buffer) >= self.learning_threshold:
                await self._trigger_batch_learning()
        
        except Exception as e:
            logger.error(f"记录反馈失败: {e}")
    
    # 移除数据库相关的方法，改为文件操作
    
    async def _record_feedback(self, learning_data: Dict):
        """记录反馈数据"""
        try:
            # 添加到缓冲区
            self.feedback_buffer.append(learning_data)
            
            # 保存到文件
            with open(self.feedback_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'feedback_buffer': self.feedback_buffer,
                    'last_updated': datetime.now().isoformat()
                }, f, ensure_ascii=False, indent=2)
            
            logger.debug(f"记录反馈: {learning_data['action']} for message {learning_data['message_id']}")
        
        except Exception as e:
            logger.error(f"记录反馈失败: {e}")
    
    # 移除数据库依赖的学习方法
    
    # 移除数据库依赖的学习方法
    
    # 移除数据库依赖的学习方法
    
    async def add_ad_sample_to_file(self, content: str):
        """添加广告样本"""
        if not content:
            return
        
        try:
            # 加载现有样本
            samples = {"samples": []}
            if self.ad_samples_file.exists():
                with open(self.ad_samples_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # 使用统一的samples字段
                    if "samples" in data:
                        samples = data
                    else:
                        samples = {"samples": []}
            
            # 检查是否已存在
            content_hash = hashlib.md5(content.encode()).hexdigest()
            for sample in samples['samples']:
                if sample.get('hash') == content_hash:
                    logger.debug("样本已存在，跳过添加")
                    return
            
            # 添加新样本
            new_sample = {
                'content': content,
                'hash': content_hash,
                'source': 'user_feedback',
                'added_at': datetime.now().isoformat()
            }
            samples['samples'].append(new_sample)
            
            # 限制样本数量
            if len(samples['samples']) > 1000:
                samples['samples'] = samples['samples'][-1000:]
            
            # 保存，保持原有的updated_at字段
            samples['updated_at'] = datetime.now().isoformat()
            with open(self.ad_samples_file, 'w', encoding='utf-8') as f:
                json.dump(samples, f, ensure_ascii=False, indent=2)
            
            logger.info(f"添加新广告样本，当前总数: {len(samples['samples'])}")
        
        except Exception as e:
            logger.error(f"添加广告样本失败: {e}")
    
    async def _add_normal_sample(self, content: str):
        """添加正常内容样本"""
        if not content:
            return
        
        try:
            # 加载现有样本
            samples = {"normal_samples": []}
            if self.normal_samples_file.exists():
                with open(self.normal_samples_file, 'r', encoding='utf-8') as f:
                    samples = json.load(f)
            
            # 检查是否已存在
            content_hash = hashlib.md5(content.encode()).hexdigest()
            for sample in samples['normal_samples']:
                if sample.get('hash') == content_hash:
                    logger.debug("样本已存在，跳过添加")
                    return
            
            # 添加新样本
            new_sample = {
                'content': content,
                'hash': content_hash,
                'source': 'user_feedback',
                'added_at': datetime.now().isoformat()
            }
            samples['normal_samples'].append(new_sample)
            
            # 限制样本数量
            if len(samples['normal_samples']) > 1000:
                samples['normal_samples'] = samples['normal_samples'][-1000:]
            
            # 保存
            with open(self.normal_samples_file, 'w', encoding='utf-8') as f:
                json.dump(samples, f, ensure_ascii=False, indent=2)
            
            logger.info(f"添加新正常样本，当前总数: {len(samples['normal_samples'])}")
        
        except Exception as e:
            logger.error(f"添加正常样本失败: {e}")
    
    async def _trigger_batch_learning(self):
        """触发批量学习"""
        try:
            logger.info(f"触发批量学习，处理 {len(self.feedback_buffer)} 条反馈")
            
            # 分析反馈数据
            ad_samples = []
            normal_samples = []
            
            for feedback in self.feedback_buffer:
                if feedback['action'] == 'rejected':
                    # 拒绝的都是广告
                    if feedback['content']:
                        ad_samples.append(feedback['content'])
                elif feedback['action'] == 'approved':
                    # 批准的都是正常内容
                    if feedback['content'] and feedback['is_ad']:
                        # 如果被误判为广告但批准了，添加到正常样本
                        normal_samples.append(feedback['content'])
            
            # 批量更新样本库
            if ad_samples:
                logger.info(f"批量添加 {len(ad_samples)} 个广告样本")
                for sample in ad_samples:
                    await self.add_ad_sample_to_file(sample)
                
                # 更新广告检测器（如果存在的话）
                try:
                    from app.services.ad_detector import ad_detector
                    await ad_detector.update_ad_samples(ad_samples)
                except ImportError:
                    logger.info("广告检测器模块未找到，跳过更新")
            
            # 不再收集正常样本
            # if normal_samples:
            #     logger.info(f"批量添加 {len(normal_samples)} 个正常样本")
            #     for sample in normal_samples:
            #         await self._add_normal_sample(sample)
            
            # 清空缓冲区（保留最近的20条）
            self.feedback_buffer = self.feedback_buffer[-20:]
            
            # 保存更新后的缓冲区
            with open(self.feedback_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'feedback_buffer': self.feedback_buffer,
                    'last_updated': datetime.now().isoformat()
                }, f, ensure_ascii=False, indent=2)
            
            logger.info("批量学习完成")
        
        except Exception as e:
            logger.error(f"批量学习失败: {e}")
    
    async def get_learning_stats_from_file(self) -> Dict:
        """从文件获取学习统计"""
        stats = {
            'feedback_count': len(self.feedback_buffer),
            'ad_samples': 0,
            'normal_samples': 0,
            'last_learning': None,
            'tail_samples': 0,
            'separator_patterns': 0
        }
        
        try:
            # 统计广告样本
            if self.ad_samples_file.exists():
                with open(self.ad_samples_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    stats['ad_samples'] = len(data.get('samples', []))
            
            # 统计尾部样本
            if TrainingDataConfig.TAIL_FILTER_SAMPLES_FILE.exists():
                with open(TrainingDataConfig.TAIL_FILTER_SAMPLES_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    stats['tail_samples'] = len(data.get('samples', []))
            
            # 统计分隔符模式
            if TrainingDataConfig.SEPARATOR_PATTERNS_FILE.exists():
                with open(TrainingDataConfig.SEPARATOR_PATTERNS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    stats['separator_patterns'] = len(data.get('patterns', []))
            
            # 最后学习时间
            if self.feedback_file.exists():
                with open(self.feedback_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    stats['last_learning'] = data.get('last_updated')
        
        except Exception as e:
            logger.error(f"获取学习统计失败: {e}")
        
        return stats


# 全局实例
adaptive_learning = AdaptiveLearningSystem()