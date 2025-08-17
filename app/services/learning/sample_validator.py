"""
样本验证器模块
负责确保训练样本的质量和合理性
"""
import re
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class SampleValidator:
    """
    样本验证器 - 确保训练样本的质量
    """
    
    def __init__(self):
        self.news_keywords = {
            '政府', '国家', '总统', '部长', '警方', '法院',
            '亿', '万', '美元', '人民币', '股票', '经济',
            '公司', '企业', '集团', '发布', '宣布', '表示'
        }
        self.min_sample_length = 20
        self.max_sample_length = 500
    
    def validate(self, sample: str, original_message: str, message_id: int = None) -> Dict[str, Any]:
        """
        验证训练样本的合理性
        
        Args:
            sample: 训练样本
            original_message: 原始消息
            message_id: 消息ID（用于防止自引用）
            
        Returns:
            验证结果
        """
        results = {
            'is_valid': False,
            'confidence': 0.0,
            'checks': {},
            'errors': []
        }
        
        # 1. 基础检查
        if not sample or not original_message:
            results['errors'].append("样本或原始消息为空")
            return results
        
        # 2. 长度检查
        results['checks']['length_valid'] = self.min_sample_length <= len(sample) <= self.max_sample_length
        if not results['checks']['length_valid']:
            results['errors'].append(f"样本长度不合理: {len(sample)}")
        
        # 3. 推广内容检查
        results['checks']['is_promotional'] = self._check_promotional_content(sample)
        if not results['checks']['is_promotional']:
            results['errors'].append("样本不包含推广特征")
        
        # 4. 非正文内容检查
        results['checks']['not_news_content'] = self._check_not_news_content(sample)
        if not results['checks']['not_news_content']:
            results['errors'].append("样本包含新闻正文内容")
        
        # 5. 位置合理性检查
        results['checks']['position_valid'] = self._check_position_validity(sample, original_message)
        if not results['checks']['position_valid']:
            results['errors'].append("样本不在消息尾部")
        
        # 6. 自引用检查
        if message_id:
            results['checks']['no_self_reference'] = self._check_no_self_reference(sample, message_id)
            if not results['checks']['no_self_reference']:
                results['errors'].append("不能用消息自己的内容作为训练样本")
        
        # 计算置信度
        passed_checks = sum(1 for v in results['checks'].values() if v)
        total_checks = len(results['checks'])
        results['confidence'] = passed_checks / max(total_checks, 1)
        
        # 判断是否有效
        results['is_valid'] = (
            results['confidence'] >= 0.7 and
            results['checks'].get('is_promotional', False) and
            results['checks'].get('position_valid', False)
        )
        
        return results
    
    def _check_promotional_content(self, sample: str) -> bool:
        """检查是否包含推广特征"""
        promo_indicators = [
            '@',  # Telegram用户名
            't.me/',  # Telegram链接
            '订阅', '訂閱', '关注', '關注',
            '频道', '頻道', '投稿', '爆料',
            '联系', '聯繫', '商务', '商務'
        ]
        
        # 至少包含2个推广特征
        indicator_count = sum(1 for indicator in promo_indicators if indicator in sample)
        return indicator_count >= 2
    
    def _check_not_news_content(self, sample: str) -> bool:
        """检查是否不包含新闻正文"""
        # 检查是否包含过多新闻关键词
        news_word_count = sum(1 for keyword in self.news_keywords if keyword in sample)
        
        # 如果包含超过3个新闻关键词，可能是正文
        if news_word_count > 3:
            return False
        
        # 检查是否包含日期、金额等
        if re.search(r'\d{4}年\d{1,2}月\d{1,2}日', sample):
            return False
        if re.search(r'\d+[亿万]', sample):
            return False
        
        return True
    
    def _check_position_validity(self, sample: str, original: str) -> bool:
        """检查位置合理性"""
        if sample not in original:
            return False
        
        # 找到样本在原文中的位置
        position = original.rfind(sample)
        if position == -1:
            return False
        
        # 检查是否在消息末尾附近
        after_content = original[position + len(sample):].strip()
        
        # 后面的内容不应该太多
        return len(after_content) < 100
    
    def _check_no_self_reference(self, sample: str, message_id: int) -> bool:
        """检查是否自引用"""
        # 这里需要查询数据库，检查样本是否来自同一条消息
        # 暂时返回True，实际实现时需要查询数据库
        return True