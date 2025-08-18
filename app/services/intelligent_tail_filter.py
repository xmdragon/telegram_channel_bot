"""
智能尾部过滤器
基于AI语义分析的智能尾部识别和过滤系统
"""
import re
import logging
from typing import Dict, List, Optional, Tuple, Any
import numpy as np
from datetime import datetime
import asyncio

from app.services.tail_feature_extractor import tail_feature_extractor
from app.services.tail_vector_manager import tail_vector_manager
from app.core.path_config import PathConfig
from app.utils.safe_file_ops import SafeFileOperation

logger = logging.getLogger(__name__)

class IntelligentTailFilter:
    """智能尾部过滤器"""
    
    def __init__(self):
        self.feature_extractor = tail_feature_extractor
        self.vector_manager = tail_vector_manager
        
        # 过滤配置（硬编码阈值已移除，由阈值管理器动态管理）
        # self.default_threshold = 0.7  # 已废弃
        self.similarity_threshold = 0.75
        self.confidence_threshold = 0.6
        
        # 分隔符模式
        self.separator_patterns = [
            r'[-—=]{3,}', r'[▔═]{3,}', r'\.{3,}', r'~{3,}', r'\*{3,}', r'#{3,}'
        ]
        
        # 尾部标识
        self.tail_indicators = [
            r'(?:^|\n)[-—=▔═.~*#]{3,}',
            r'(?:^|\n).*订阅.*频道', r'(?:^|\n).*关注.*获取',
            r'(?:^|\n).*投稿.*爆料', r'(?:^|\n).*商务.*合作',
            r'(?:^|\n).*联系.*方式', r'(?:^|\n).*失联.*导航'
        ]
        
        self._load_samples()
    
    def _load_samples(self):
        """加载训练样本"""
        try:
            samples_file = PathConfig.TAIL_FILTER_SAMPLES_FILE
            if samples_file.exists():
                data = SafeFileOperation.read_json_safe(samples_file)
                if data and 'samples' in data:
                    logger.info(f"✅ 加载了 {len(data['samples'])} 个尾部过滤样本")
                else:
                    logger.warning("⚠️ 尾部样本文件格式异常")
            else:
                logger.info("📝 尾部样本文件不存在")
        except Exception as e:
            logger.error(f"❌ 加载尾部样本失败: {e}")
    
    async def analyze_message(self, content: str, context: Dict = None) -> Dict:
        """分析消息，识别可能的尾部"""
        if not content or len(content.strip()) < 10:
            return self._empty_analysis(content)
        
        # 检测尾部边界
        tail_boundary = self._detect_tail_boundary(content)
        if tail_boundary == -1:
            tail_boundary = await self._semantic_boundary_detection(content)
        
        # 提取尾部
        if tail_boundary > 0:
            main_content = content[:tail_boundary].strip()
            tail_content = content[tail_boundary:].strip()
        else:
            main_content = content
            tail_content = ""
        
        # 分析尾部
        if tail_content:
            tail_analysis = await self._analyze_tail_content(tail_content, context)
        else:
            tail_analysis = self._empty_tail_analysis()
        
        return {
            'original_content': content,
            'main_content': main_content,
            'tail_content': tail_content,
            'tail_boundary': tail_boundary,
            'tail_analysis': tail_analysis,
            'should_filter_tail': tail_analysis.get('should_filter', False),
            'confidence': tail_analysis.get('confidence', 0.0),
            'analysis_time': datetime.now().isoformat()
        }
    
    def _detect_tail_boundary(self, content: str) -> int:
        """检测尾部边界位置"""
        # 查找分隔符
        for pattern in self.separator_patterns:
            matches = list(re.finditer(pattern, content))
            if matches:
                return matches[-1].start()
        
        # 查找尾部标识
        for pattern in self.tail_indicators:
            match = re.search(pattern, content)
            if match:
                return match.start()
        
        # 启发式检测
        if len(content) > 200:
            lines = content.split('\n')
            if len(lines) > 5:
                last_lines = lines[-min(3, len(lines)//4):]
                last_part = '\n'.join(last_lines)
                
                link_count = len(re.findall(r'@\w+|t\.me/|https?://', last_part))
                promo_words = ['订阅', '关注', '投稿', '商务', '合作', '联系']
                promo_count = sum(1 for word in promo_words if word in last_part)
                
                if link_count >= 2 or promo_count >= 2:
                    boundary_pos = content.rfind('\n'.join(last_lines))
                    if boundary_pos > len(content) // 2:
                        return boundary_pos
        
        return -1
    
    async def _semantic_boundary_detection(self, content: str) -> int:
        """基于语义的边界检测"""
        if not self.vector_manager.model:
            return -1
        
        lines = content.split('\n')
        if len(lines) < 3:
            return -1
        
        line_scores = []
        for line in lines:
            if len(line.strip()) > 5:
                features = self.feature_extractor.extract_features(line)
                scores = self.feature_extractor.calculate_scores(line, features)
                line_scores.append(scores['overall_score'])
            else:
                line_scores.append(0.0)
        
        if len(line_scores) >= 3:
            for i in range(1, len(line_scores) - 1):
                if (line_scores[i] > 0.6 and 
                    line_scores[i] > line_scores[i-1] * 2 and
                    i > len(line_scores) / 2):
                    
                    boundary_lines = lines[:i]
                    return len('\n'.join(boundary_lines))
        
        return -1
    
    async def _analyze_tail_content(self, tail_content: str, context: Dict = None) -> Dict:
        """分析尾部内容"""
        # 提取特征和得分
        features = self.feature_extractor.extract_features(tail_content)
        scores = self.feature_extractor.calculate_scores(tail_content, features)
        
        # 向量相似度匹配
        similar_samples = self.vector_manager.find_similar(
            tail_content, top_k=5, threshold=self.similarity_threshold
        )
        
        # 调整得分
        if similar_samples:
            avg_confidence = np.mean([s['similarity'] for s in similar_samples])
            if avg_confidence > 0.8:
                scores['overall_score'] = min(scores['overall_score'] + 0.2, 1.0)
        
        if context:
            scores = self._apply_context_adjustment(scores, context, features)
        
        # 综合判断
        # 阈值现在由阈值管理器动态管理，这里仅计算分数
        # should_filter决策已移至TailFilter类中
        should_filter = False  # 将由调用方决定
        confidence = self._calculate_confidence(scores, similar_samples, features)
        
        return {
            'features': features,
            'scores': scores,
            'similar_samples': similar_samples,
            'should_filter': should_filter,
            'confidence': confidence,
            'filter_reason': self._generate_filter_reason(scores, features, similar_samples)
        }
    
    def _apply_context_adjustment(self, scores: Dict, context: Dict, features: Dict) -> Dict:
        """根据上下文调整得分"""
        adjusted_scores = scores.copy()
        
        channel_id = context.get('channel_id')
        if channel_id:
            if 'news' in str(channel_id).lower():
                if features.get('has_channel_mention') and features.get('link_count', 0) <= 2:
                    adjusted_scores['overall_score'] *= 0.8
            elif 'business' in str(channel_id).lower():
                adjusted_scores['overall_score'] *= 1.2
        
        current_hour = datetime.now().hour
        if 9 <= current_hour <= 18:
            if features.get('business_word_count', 0) > 0:
                adjusted_scores['commercial_score'] *= 1.1
        
        return adjusted_scores
    
    def _calculate_confidence(self, scores: Dict, similar_samples: List, features: Dict) -> float:
        """计算过滤决策的置信度"""
        confidence = 0.5
        
        overall_score = scores['overall_score']
        if overall_score > 0.8:
            confidence += 0.3
        elif overall_score > 0.6:
            confidence += 0.2
        elif overall_score > 0.4:
            confidence += 0.1
        
        if similar_samples:
            max_similarity = max(s['similarity'] for s in similar_samples)
            if max_similarity > 0.9:
                confidence += 0.2
            elif max_similarity > 0.8:
                confidence += 0.15
            elif max_similarity > 0.7:
                confidence += 0.1
        
        if features.get('has_telegram_link') and features.get('link_count', 0) > 2:
            confidence += 0.1
        if features.get('business_word_count', 0) > 2:
            confidence += 0.1
        if features.get('action_word_count', 0) > 2:
            confidence += 0.1
        
        return min(confidence, 1.0)
    
    def _generate_filter_reason(self, scores: Dict, features: Dict, similar_samples: List) -> str:
        """生成过滤原因说明"""
        reasons = []
        
        if scores['promotion_score'] > 0.7:
            reasons.append(f"推广得分较高({scores['promotion_score']:.2f})")
        if scores['commercial_score'] > 0.7:
            reasons.append(f"商业化得分较高({scores['commercial_score']:.2f})")
        if features.get('has_telegram_link'):
            reasons.append("包含Telegram链接")
        if features.get('link_count', 0) > 2:
            reasons.append(f"链接数量过多({features['link_count']}个)")
        if features.get('action_word_count', 0) > 0:
            action_words = ', '.join(features.get('action_words', []))
            reasons.append(f"包含动作词汇({action_words})")
        if similar_samples:
            max_sim = max(s['similarity'] for s in similar_samples)
            reasons.append(f"与已知推广样本相似度高({max_sim:.2f})")
        
        return "; ".join(reasons) if reasons else "综合评分超过阈值"
    
    def _empty_analysis(self, content: str) -> Dict:
        """返回空分析结果"""
        return {
            'original_content': content,
            'main_content': content,
            'tail_content': "",
            'tail_boundary': -1,
            'tail_analysis': self._empty_tail_analysis(),
            'should_filter_tail': False,
            'confidence': 0.0,
            'analysis_time': datetime.now().isoformat()
        }
    
    def _empty_tail_analysis(self) -> Dict:
        """返回空尾部分析结果"""
        return {
            'features': {},
            'scores': {'promotion_score': 0.0, 'commercial_score': 0.0, 'relevance_score': 0.0, 'overall_score': 0.0},
            'similar_samples': [],
            'should_filter': False,
            'confidence': 0.0,
            'filter_reason': ""
        }
    
    async def filter_message(self, content: str, context: Dict = None) -> Tuple[str, str, Dict]:
        """过滤消息中的尾部内容"""
        analysis = await self.analyze_message(content, context)
        
        if analysis['should_filter_tail'] and analysis['confidence'] >= self.confidence_threshold:
            filtered_content = analysis['main_content']
            removed_tail = analysis['tail_content']
            
            logger.info(f"🚫 过滤尾部内容 - 长度: {len(removed_tail)}, 置信度: {analysis['confidence']:.2f}")
        else:
            filtered_content = content
            removed_tail = ""
            
            if analysis['tail_content']:
                logger.debug(f"✅ 保留尾部内容 - 置信度不足: {analysis['confidence']:.2f}")
        
        return filtered_content, removed_tail, analysis


# 创建全局实例
# 懒加载全局实例
_intelligent_tail_filter_instance = None

def get_intelligent_tail_filter():
    """获取智能尾部过滤器实例（懒加载）"""
    global _intelligent_tail_filter_instance
    if _intelligent_tail_filter_instance is None:
        _intelligent_tail_filter_instance = IntelligentTailFilter()
    return _intelligent_tail_filter_instance

# 兼容性：保持intelligent_tail_filter属性访问
class IntelligentTailFilterProxy:
    """智能尾部过滤器代理，实现懒加载"""
    def __getattr__(self, name):
        return getattr(get_intelligent_tail_filter(), name)
    
    def __setattr__(self, name, value):
        setattr(get_intelligent_tail_filter(), name, value)

intelligent_tail_filter = IntelligentTailFilterProxy()