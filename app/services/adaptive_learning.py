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
from sqlalchemy import select
from app.core.database import AsyncSessionLocal, Message
from app.services.ad_detector import ad_detector

logger = logging.getLogger(__name__)


class AdaptiveLearningSystem:
    """自适应学习系统"""
    
    def __init__(self):
        self.feedback_file = Path("data/feedback_learning.json")
        self.ad_samples_file = Path("data/ad_training_data.json")
        self.normal_samples_file = Path("data/normal_training_data.json")
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
    
    async def learn_from_user_action(self, message_id: int, action: str, reviewer: str = None):
        """
        从用户操作中学习
        
        Args:
            message_id: 消息ID
            action: 用户操作 ('approved', 'rejected', 'edited')
            reviewer: 审核人
        """
        try:
            # 获取消息详情
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Message).where(Message.id == message_id)
                )
                message = result.scalar_one_or_none()
                
                if not message:
                    logger.warning(f"消息 {message_id} 不存在")
                    return
                
                # 提取学习数据
                learning_data = self._extract_learning_data(message, action)
                
                # 记录反馈
                await self._record_feedback(learning_data)
                
                # 根据操作类型进行不同的学习
                if action == 'approved':
                    await self._learn_from_approval(message)
                elif action == 'rejected':
                    await self._learn_from_rejection(message)
                elif action == 'edited':
                    await self._learn_from_edit(message)
                
                # 检查是否需要触发批量学习
                if len(self.feedback_buffer) >= self.learning_threshold:
                    await self._trigger_batch_learning()
        
        except Exception as e:
            logger.error(f"学习失败: {e}")
    
    def _extract_learning_data(self, message: Message, action: str) -> Dict:
        """提取学习数据"""
        return {
            'message_id': message.id,
            'content': message.content,
            'filtered_content': message.filtered_content,
            'is_ad': message.is_ad,
            'action': action,
            'has_buttons': message.has_buttons if hasattr(message, 'has_buttons') else False,
            'button_data': message.button_data if hasattr(message, 'button_data') else None,
            'entity_data': message.entity_data if hasattr(message, 'entity_data') else None,
            'timestamp': datetime.now().isoformat(),
            'content_hash': hashlib.md5(message.content.encode()).hexdigest() if message.content else None
        }
    
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
    
    async def _learn_from_approval(self, message: Message):
        """从批准操作中学习 - 这是正常内容"""
        try:
            if message.is_ad:
                # 用户批准了被标记为广告的内容，可能是误判
                logger.info(f"检测到可能的误判: 消息 {message.id} 被标记为广告但用户批准了")
                
                # 将此内容添加到正常样本库
                await self._add_normal_sample(message.content)
                
                # TODO: 降低相似内容的广告检测阈值
        
        except Exception as e:
            logger.error(f"从批准操作学习失败: {e}")
    
    async def _learn_from_rejection(self, message: Message):
        """从拒绝操作中学习 - 这是广告内容"""
        try:
            if not message.is_ad:
                # 用户拒绝了未被标记为广告的内容，这是漏检
                logger.info(f"检测到漏检: 消息 {message.id} 未被标记为广告但用户拒绝了")
                
                # 将此内容添加到广告样本库
                await self._add_ad_sample(message.content)
                
                # 更新广告检测器
                await ad_detector.update_ad_samples([message.content])
        
        except Exception as e:
            logger.error(f"从拒绝操作学习失败: {e}")
    
    async def _learn_from_edit(self, message: Message):
        """从编辑操作中学习 - 学习编辑模式"""
        try:
            if message.content != message.filtered_content:
                # 用户编辑了内容，学习编辑模式
                logger.info(f"学习编辑模式: 消息 {message.id}")
                
                # 分析编辑差异
                original = message.content
                edited = message.filtered_content
                
                # TODO: 实现编辑模式学习
                # 例如：学习哪些部分被删除，哪些被保留
        
        except Exception as e:
            logger.error(f"从编辑操作学习失败: {e}")
    
    async def _add_ad_sample(self, content: str):
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
                    await self._add_ad_sample(sample)
                
                # 更新广告检测器
                await ad_detector.update_ad_samples(ad_samples)
            
            if normal_samples:
                logger.info(f"批量添加 {len(normal_samples)} 个正常样本")
                for sample in normal_samples:
                    await self._add_normal_sample(sample)
            
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
    
    def get_learning_stats(self) -> Dict:
        """获取学习统计"""
        stats = {
            'feedback_count': len(self.feedback_buffer),
            'ad_samples': 0,
            'normal_samples': 0,
            'last_learning': None
        }
        
        try:
            # 统计广告样本
            if self.ad_samples_file.exists():
                with open(self.ad_samples_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    stats['ad_samples'] = len(data.get('samples', []))
            
            # 统计正常样本
            if self.normal_samples_file.exists():
                with open(self.normal_samples_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    stats['normal_samples'] = len(data.get('normal_samples', []))
            
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