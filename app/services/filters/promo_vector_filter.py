"""
推广内容向量过滤器
基于向量相似度检测推广内容，避免误判
"""
import re
import logging
from typing import Tuple, Optional, List, Dict

from app.services.filters.base import BaseFilter, FilterResult, FilterContext
from app.services.promo_vector_manager import promo_vector_manager
from app.core.threshold_manager import threshold_manager
from app.services.rule_manager import RuleManager

logger = logging.getLogger(__name__)

class PromoVectorFilter(BaseFilter):
    """推广内容向量过滤器"""
    
    def __init__(self):
        super().__init__("promo_vector_filter")
        self.description = "基于向量相似度检测推广内容"
        
        # 获取动态阈值
        self.similarity_threshold = threshold_manager.get_threshold(
            self.name, "similarity"
        )
        self.min_length_threshold = threshold_manager.get_threshold(
            self.name, "min_length"
        )
        
        # 初始化关键词配置
        self.rule_manager = RuleManager()
        self.keywords = {}
        self._load_keywords()
        
    def _split_into_segments(self, content: str) -> List[str]:
        """
        将内容分割成语义段落
        避免因一句推广内容过滤整篇文章
        
        改进策略：按段落/行分割，不再按句子分割
        保持推广内容的完整性
        """
        segments = []
        
        # 🚀 Linus式预处理：将多个连续空格转换为段落分隔符
        # 与TailFilterEngine保持一致的处理逻辑
        import re
        if re.search(r' {5,}', content):
            content = re.sub(r' {5,}', '\n\n', content)
            logger.debug(f"推广向量过滤器：多空格预处理完成")
        
        # 先按双换行分割（段落）
        paragraphs = content.split('\n\n')
        
        for paragraph in paragraphs:
            paragraph = paragraph.strip()
            if not paragraph:
                continue
                
            # 再按单换行分割（处理单行的推广内容）
            lines = paragraph.split('\n')
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                    
                # 每行作为独立段落处理
                # 避免句号分割破坏推广内容完整性
                if len(line) >= self.min_length_threshold:
                    segments.append(line)
        
        return segments
    
    def _load_keywords(self):
        """从配置文件加载关键词"""
        try:
            # 初始化rule_manager
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 如果已有事件循环运行，使用同步方式
                if not hasattr(self.rule_manager, 'rules_data') or not self.rule_manager.rules_data:
                    import json
                    from pathlib import Path
                    from app.core.path_config import PathConfig
                    
                    config_path = Path(PathConfig.DATA_DIR) / "config" / "filter_rules.json"
                    if config_path.exists():
                        with open(config_path, 'r', encoding='utf-8') as f:
                            self.rule_manager.rules_data = json.load(f)
            else:
                # 如果没有事件循环，创建一个临时的
                loop.run_until_complete(self.rule_manager.load_rules())
            
            # 加载关键词配置
            promo_vector_config = self.rule_manager.rules_data.get('rule_categories', {}).get('promo_vector_keywords', {})
            
            if promo_vector_config.get('enabled', True):
                keyword_categories = promo_vector_config.get('keyword_categories', {})
                
                # 加载各类关键词
                self.keywords = {
                    'strong_promo_signals': keyword_categories.get('strong_promo_signals', {}).get('keywords', []),
                    'weak_promo_signals': keyword_categories.get('weak_promo_signals', {}).get('keywords', []),
                    'educational_signals': keyword_categories.get('educational_signals', {}).get('keywords', []),
                    'entertainment_signals': keyword_categories.get('entertainment_signals', {}).get('keywords', []),
                    'news_signals': keyword_categories.get('news_signals', {}).get('keywords', [])
                }
                
                logger.info(f"成功加载关键词配置，共{sum(len(keywords) for keywords in self.keywords.values())}个关键词")
            else:
                self._set_default_keywords()
                logger.warning("关键词配置已禁用，使用默认关键词")
                
        except Exception as e:
            logger.error(f"加载关键词配置失败: {e}")
            self._set_default_keywords()
    
    def _set_default_keywords(self):
        """设置默认关键词（作为fallback）"""
        self.keywords = {
            'strong_promo_signals': [
                '订阅', '关注', '加群', '联系', '@', '商务合作', '投稿',
                '频道', '群组', '客服', '咨询', '报名', '购买', '下单',
                '优惠', '折扣', '促销', '限时', '活动', '奖励'
            ],
            'weak_promo_signals': [
                '更多', '详情', '了解', '点击', '进入', '查看'
            ],
            'educational_signals': [
                '学习', '教育', '知识', '技能', '课程', '培训', '指导',
                '方法', '技巧', '经验', '分享', '总结', '分析', '研究',
                '理论', '实践', '案例', '建议', '提醒', '注意', '避免'
            ],
            'entertainment_signals': [
                '搞笑', '有趣', '娱乐', '故事', '段子', '笑话', '趣闻',
                '八卦', '明星', '影视', '游戏', '音乐', '视频'
            ],
            'news_signals': [
                '新闻', '报道', '发布', '宣布', '公告', '通知', '政策',
                '法规', '规定', '决定', '会议', '讨论', '发言', '表示'
            ]
        }
        logger.debug("使用默认关键词配置")
    
    def _check_segment_promo(self, segment: str) -> Tuple[bool, float, str]:
        """
        检查单个段落是否为推广内容
        
        改进算法：添加上下文理解和多维度特征分析
        
        Returns:
            (是否推广, 最高相似度, 匹配样本)
        """
        if not segment or len(segment) < self.min_length_threshold:
            return False, 0.0, ""
        
        try:
            # 🧠 第一步：上下文理解 - 内容类型分析
            content_analysis = self._analyze_content_type(segment)
            
            # 🛡️ 第二步：训练样本充分性检查
            cache_stats = promo_vector_manager.get_cache_stats()
            sample_count = cache_stats.get('total_vectors', 0)
            
            # 🚀 Linus式优化：只要有训练样本就使用向量检测，提高检测准确性
            # 保守策略仅在完全没有训练样本时使用
            if sample_count == 0:
                logger.debug(f"无训练样本，采用保守检测策略")
                return self._conservative_promo_detection(segment, content_analysis)
            
            # 🔍 第三步：向量相似度检测（作为参考）
            similar_samples = promo_vector_manager.find_similar_samples(
                segment, 
                threshold=self.similarity_threshold,
                top_k=3
            )
            
            vector_similarity = 0.0
            matched_sample = ""
            
            if similar_samples:
                best_match = similar_samples[0]
                vector_similarity = best_match[1]
                matched_sample = best_match[0]
            
            # 🎯 第四步：综合判断 - 融合多种特征
            final_decision, final_confidence = self._make_comprehensive_decision(
                segment, content_analysis, vector_similarity, sample_count
            )
            
            # 📊 记录详细分析结果
            logger.debug(
                f"推广内容综合分析: "
                f"内容类型={content_analysis['content_type']}, "
                f"向量相似度={vector_similarity:.3f}, "
                f"最终判断={final_decision}, "
                f"置信度={final_confidence:.3f}, "
                f"样本数={sample_count}"
            )
            
            return final_decision, final_confidence, matched_sample[:50]
            
        except Exception as e:
            logger.error(f"段落推广检测失败: {e}")
            return False, 0.0, ""
    
    def _analyze_content_type(self, segment: str) -> dict:
        """
        分析内容类型和语义特征
        
        Returns:
            {
                'content_type': str,  # 'educational', 'entertainment', 'promotional', 'news'
                'promotional_signals': int,  # 推广信号强度 0-10
                'educational_signals': int,  # 教育信号强度 0-10
                'context_clarity': float,  # 上下文清晰度 0.0-1.0
            }
        """
        analysis = {
            'content_type': 'unknown',
            'promotional_signals': 0,
            'educational_signals': 0,
            'context_clarity': 0.5
        }
        
        # 从配置文件加载的关键词
        strong_promo_signals = self.keywords.get('strong_promo_signals', [])
        weak_promo_signals = self.keywords.get('weak_promo_signals', [])
        educational_signals = self.keywords.get('educational_signals', [])
        entertainment_signals = self.keywords.get('entertainment_signals', [])
        news_signals = self.keywords.get('news_signals', [])
        
        # 统计各类信号
        strong_promo_count = sum(1 for signal in strong_promo_signals if signal in segment)
        weak_promo_count = sum(1 for signal in weak_promo_signals if signal in segment)
        educational_count = sum(1 for signal in educational_signals if signal in segment)
        entertainment_count = sum(1 for signal in entertainment_signals if signal in segment)
        news_count = sum(1 for signal in news_signals if signal in segment)
        
        # 计算推广信号强度 (0-10)
        analysis['promotional_signals'] = min(10, strong_promo_count * 3 + weak_promo_count)
        
        # 计算教育信号强度 (0-10)
        analysis['educational_signals'] = min(10, educational_count * 2)
        
        # 确定内容类型
        if strong_promo_count >= 2 or analysis['promotional_signals'] >= 6:
            analysis['content_type'] = 'promotional'
            analysis['context_clarity'] = 0.8
        elif educational_count >= 2 or '教学' in segment or '学会' in segment:
            analysis['content_type'] = 'educational'
            analysis['context_clarity'] = 0.9
        elif entertainment_count >= 2:
            analysis['content_type'] = 'entertainment'  
            analysis['context_clarity'] = 0.7
        elif news_count >= 2:
            analysis['content_type'] = 'news'
            analysis['context_clarity'] = 0.8
        else:
            analysis['content_type'] = 'general'
            analysis['context_clarity'] = 0.5
            
        # 特殊情况：明显的情感表达或个人经历分享
        emotional_expressions = ['爱', '恨', '喜欢', '讨厌', '感动', '难过', '开心', '愤怒']
        if any(expr in segment for expr in emotional_expressions):
            if analysis['content_type'] == 'general':
                analysis['content_type'] = 'personal'
                analysis['context_clarity'] = 0.9
        
        return analysis
    
    def _conservative_promo_detection(self, segment: str, content_analysis: dict) -> Tuple[bool, float, str]:
        """
        训练样本不足时的保守检测策略
        主要依赖启发式规则，避免过度依赖向量相似度
        """
        # 保守策略：只有明确的推广信号才判定为推广内容
        promotional_signals = content_analysis['promotional_signals']
        content_type = content_analysis['content_type']
        
        # 明确的推广内容特征
        definite_promo_patterns = [
            r'@\w+',  # @用户名
            r'加群.*\d+',  # 加群 + 数字
            r'联系.*[：:]\s*@?\w+',  # 联系：@用户名
            r'订阅.*频道',  # 订阅频道
            r'商务合作.*[：:]',  # 商务合作：
            r'投稿.*[：:]'   # 投稿：
        ]
        
        import re
        pattern_matches = sum(1 for pattern in definite_promo_patterns 
                            if re.search(pattern, segment))
        
        # 综合判断
        if content_type == 'promotional' and promotional_signals >= 6:
            return True, 0.8, "明确推广特征"
        elif pattern_matches >= 2:
            return True, 0.7, "推广模式匹配"
        elif content_type in ['educational', 'personal'] and promotional_signals <= 2:
            return False, 0.1, "教育/个人内容"
        else:
            # 模糊情况，偏向保守（不过滤）
            return False, 0.3, "保守策略-保留"
    
    def _make_comprehensive_decision(self, segment: str, content_analysis: dict, 
                                   vector_similarity: float, sample_count: int) -> Tuple[bool, float]:
        """
        综合多种特征做出最终判断
        
        Args:
            segment: 文本段落
            content_analysis: 内容类型分析结果
            vector_similarity: 向量相似度
            sample_count: 训练样本数量
            
        Returns:
            (是否推广内容, 置信度)
        """
        promotional_signals = content_analysis['promotional_signals']
        educational_signals = content_analysis['educational_signals']
        content_type = content_analysis['content_type']
        context_clarity = content_analysis['context_clarity']
        
        # 🎯 规则1: 明确的教育/个人内容，强制不过滤
        if content_type in ['educational', 'personal'] and educational_signals >= 3:
            return False, max(0.1, 1.0 - vector_similarity)
        
        # 🎯 规则2: 明确的推广内容，必须过滤
        if content_type == 'promotional' and promotional_signals >= 6:
            return True, min(0.9, max(0.7, vector_similarity))
        
        # 🎯 规则3: 训练样本少时，降低向量相似度权重
        vector_weight = min(0.4, sample_count / 20.0)  # 样本越少权重越低
        context_weight = 1.0 - vector_weight
        
        # 计算综合置信度
        # 向量相似度贡献 (降权)
        vector_score = vector_similarity * vector_weight
        
        # 上下文分析贡献 (提权)
        if promotional_signals > educational_signals + 2:
            context_score = (promotional_signals / 10.0) * context_weight
        elif educational_signals > promotional_signals:
            context_score = -(educational_signals / 10.0) * context_weight
        else:
            context_score = 0.0
        
        final_score = vector_score + context_score
        
        # 🎯 规则4: 动态阈值调整
        adjusted_threshold = self.similarity_threshold
        
        # 如果是明显的非推广内容，提高阈值
        if content_type in ['educational', 'personal', 'news']:
            adjusted_threshold = min(0.95, self.similarity_threshold + 0.1)
        
        # 如果训练样本很少，提高阈值
        if sample_count < 3:
            adjusted_threshold = min(0.95, self.similarity_threshold + 0.2)
        
        is_promo = final_score >= adjusted_threshold
        confidence = abs(final_score)
        
        return is_promo, confidence
    
    async def filter(self, content: str, context: FilterContext) -> FilterResult:
        """
        执行推广内容向量过滤
        
        策略：
        1. 将内容分割成语义段落
        2. 逐个检测段落是否为推广
        3. 只移除确认为推广的段落
        4. 保留正常内容段落
        """
        if not content or not content.strip():
            return FilterResult(
                filtered_content=content,
                passed=True,
                processing_time_ms=0.0,
                reason=""
            )
        
        try:
            # 更新动态阈值
            self.similarity_threshold = threshold_manager.get_threshold(
                self.name, "similarity"
            )
            self.min_length_threshold = threshold_manager.get_threshold(
                self.name, "min_length"
            )
            
            # 检查是否有推广样本数据
            cache_stats = promo_vector_manager.get_cache_stats()
            if cache_stats['total_vectors'] == 0:
                logger.debug("没有推广样本向量，跳过向量过滤")
                return FilterResult(
                    filtered_content=content,
                    passed=True,
                    processing_time_ms=0.0,
                    reason="无推广样本数据",
                    confidence=0.0
                )
            
            # 分割内容为段落
            segments = self._split_into_segments(content)
            
            if not segments:
                return FilterResult(
                    filtered_content=content,
                    passed=True,
                    processing_time_ms=0.0,
                    reason="无有效段落",
                    confidence=0.0
                )
            
            # 逐个检测段落
            clean_segments = []
            promo_segments = []
            max_similarity = 0.0
            best_match = ""
            
            for segment in segments:
                is_promo, similarity, matched_sample = self._check_segment_promo(segment)
                
                if is_promo:
                    promo_segments.append({
                        'content': segment[:50] + "..." if len(segment) > 50 else segment,
                        'similarity': similarity,
                        'matched': matched_sample
                    })
                    
                    # 记录最高相似度
                    if similarity > max_similarity:
                        max_similarity = similarity
                        best_match = matched_sample
                else:
                    clean_segments.append(segment)
            
            # 判断过滤结果
            if not promo_segments:
                # 没有推广段落
                return FilterResult(
                    filtered_content=content,
                    passed=True,
                    processing_time_ms=0.0,
                    reason="",
                    confidence=0.0
                )
            
            # 构建过滤后内容
            filtered_content = "\n\n".join(clean_segments).strip()
            
            # 计算置信度
            confidence = max_similarity
            
            # 构建过滤原因
            reason = f"检测到{len(promo_segments)}个推广段落"
            if best_match:
                reason += f"（相似度{max_similarity:.2f}）"
            
            # 判断是否应该通过
            # 如果移除的推广内容比例太高，可能是误判
            original_length = len(content)
            filtered_length = len(filtered_content)
            removal_ratio = (original_length - filtered_length) / original_length if original_length > 0 else 0
            
            # 保护措施：如果移除内容超过80%且置信度不高，认为可能误判
            if removal_ratio > 0.8 and filtered_length < 50 and confidence < 0.9:
                logger.warning(
                    f"推广过滤移除内容过多（{removal_ratio:.1%}），"
                    f"置信度{confidence:.3f}不够高，可能误判，保留原内容"
                )
                return FilterResult(
                    filtered_content=content,
                    passed=True,
                    processing_time_ms=0.0,
                    reason=f"移除比例过高({removal_ratio:.1%})，保留原内容",
                    confidence=confidence
                )
            
            # 记录过滤统计
            logger.info(
                f"推广向量过滤: 移除{len(promo_segments)}个段落, "
                f"保留{len(clean_segments)}个段落, "
                f"最高相似度{max_similarity:.3f}"
            )
            
            # 🎯 Linus式逻辑：只有过滤后没有有效内容才拒绝
            # 如果还有有效内容，说明过滤成功，应该通过
            has_valid_content = bool(filtered_content.strip())
            
            return FilterResult(
                filtered_content=filtered_content,
                passed=has_valid_content,  # 有有效内容就通过，没有才拒绝
                processing_time_ms=0.0,
                reason=reason,
                confidence=confidence,
                details={
                    'promo_segments': len(promo_segments),
                    'clean_segments': len(clean_segments),
                    'max_similarity': max_similarity,
                    'removal_ratio': removal_ratio,
                    'matched_sample': best_match,
                    'has_valid_content': has_valid_content
                }
            )
            
        except Exception as e:
            logger.error(f"推广向量过滤失败: {e}")
            # 出错时不过滤内容
            return FilterResult(
                filtered_content=content,
                passed=True,
                processing_time_ms=0.0,
                reason=f"过滤器错误: {str(e)}",
                confidence=0.0
            )