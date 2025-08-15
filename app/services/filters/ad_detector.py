"""
广告检测过滤器
整合结构化检测、AI检测和模式检测的统一广告检测器
检测到广告时返回 should_early_stop=True

Author: Claude
Created: 2025-08-15  
"""

import logging
import re
import json
import time
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from pathlib import Path

from .base import BaseFilter, FilterContext, FilterResult
from app.core.path_config import PathConfig

logger = logging.getLogger(__name__)


class AdDetectorFilter(BaseFilter):
    """广告检测过滤器 - 整合多种检测方法"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("ad_detector", config)
        
        # AI检测器组件
        self._ai_model = None
        self._ai_embeddings = []
        self._ai_initialized = False
        self.ai_threshold = self.config.get('ai_threshold', 0.75)
        
        # 加载AI模型（延迟初始化）
        self._initialize_ai_model()
        
        # 结构化检测参数
        self.semantic_coherence_threshold = self.config.get('semantic_coherence_threshold', 0.35)
        self.suspicious_url_threshold = self.config.get('suspicious_url_threshold', 0.8)
        
        # 模式检测权重配置
        self.pattern_weights = self.config.get('pattern_weights', {})
        self._load_pattern_rules()
        
        # 综合评分阈值
        self.final_threshold = self.config.get('final_threshold', 0.7)
        
    def _initialize_ai_model(self):
        """初始化AI模型"""
        try:
            from sentence_transformers import SentenceTransformer
            self._ai_model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
            self._ai_initialized = True
            logger.info("✅ AI广告检测模型初始化成功")
            
            # 延迟加载训练数据
            self._load_ai_training_data()
            
        except ImportError:
            logger.warning("⚠️ sentence-transformers 未安装，AI广告检测功能暂不可用")
        except Exception as e:
            logger.error(f"AI广告检测模型初始化失败: {e}")
    
    def _load_ai_training_data(self):
        """加载AI训练数据"""
        try:
            ad_samples_file = PathConfig.AD_TRAINING_FILE
            if not ad_samples_file.exists():
                logger.debug("没有找到广告训练数据文件")
                return
            
            with open(ad_samples_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 使用统一的samples字段
            ad_samples = data.get("samples", [])
            if ad_samples:
                # 提取内容
                contents = [s["content"] for s in ad_samples if s.get("content")]
                if contents:
                    logger.info(f"正在加载 {len(contents)} 个广告样本...")
                    self._ai_embeddings = self._ai_model.encode(contents)
                    logger.info(f"✅ 成功加载 {len(self._ai_embeddings)} 个广告样本")
                    
        except Exception as e:
            logger.error(f"加载广告训练数据失败: {e}")
    
    def _load_pattern_rules(self):
        """加载模式检测规则"""
        # 推广内容特征模式（从content_filter.py整合）
        self.promo_patterns = [
            # === 明确的广告/赞助商标识（最高优先级） ===
            (r'(频道|頻道).*(广告|廣告|赞助|贊助|推广|推廣)', 10),
            (r'(广告|廣告|赞助|贊助|推广|推廣).*(频道|頻道)', 10),
            (r'赞助商|贊助商|sponsor|Sponsor|SPONSOR', 10),
            
            # === 商业信息标识（最高优先级） ===
            (r'(营业时间|營業時間|营业中|營業中|营业状态|營業狀態)', 10),
            (r'(店铺地址|店鋪地址|门店地址|門店地址|地址：)', 10),
            (r'(经营项目|經營項目|主营|主營|业务范围|業務範圍)', 10),
            (r'(优惠|優惠|折扣|打折|特价|特價|促销|促銷)', 9),
            (r'(接单|接單|下单|下單|订购|訂購|咨询|諮詢)', 9),
            (r'(微信[:：]|WeChat[:：])', 9),
            (r'(电话[:：]|電話[:：]|手机[:：]|手機[:：]|联系[:：]|聯繫[:：])', 9),
            
            # === 博彩/赌博相关（最高优先级） ===
            (r'(博彩|体育|足球|篮球|彩票|棋牌|娱乐城|赌场|casino|Casino)', 10),
            (r'(U存U提|USDT|泰达币|虚拟币|提款|出款|充值|下注|投注)', 10),
            (r'(线上|線上).*(博彩|平台|娱乐|娛樂)', 10),
            (r'(无需实名|無需實名|不限.*ip|不限.*IP|绑定.*银行|綁定.*銀行)', 10),
            (r'(大额|大額).*(出款|提款)', 10),
            
            # === 非Telegram的HTTP链接（赌博网站等） ===
            (r'\bhttps?://(?!(?:t\.me|telegram\.me|telegra\.ph))[a-zA-Z0-9\-._~:/?#\[\]@!$&\'()*+,;=]+', 10),
            
            # === 推广关键词组合 ===
            (r'^[📢📣🔔💬❤️🔗☎️😍✉️📮📬📭📧🇲🇲🔥✅👌].{0,10}(?:订阅|訂閱|投稿|爆料|商务|商務|联系|聯系|失联|导航|對接|对接|园区|吹水|交友)[^\n]{0,20}@[a-zA-Z]', 10),
            (r'^👌(?:订阅|投稿|爆料|海外交友|商务|联系)', 10),
            (r'本频道(?:推荐|推薦)', 10),
            (r'(?:频道|頻道)(?:推荐|推薦|合作)', 10),
            
            # === 表情符号密集+文字+链接的组合 ===
            (r'^[😊😀☕️🧩🎰🎮🎳🎯♟⚡️😘🎁😍❤💰🔥]{2,}.*https?://', 8),
            (r'^[😊😀☕️🧩🎰🎮🎳🎯♟⚡️😘🎁😍❤💰🔥]{3,}[^\n]{0,50}$', 5),
        ]
        
        # 编译正则表达式
        self.compiled_patterns = [(re.compile(pattern, re.IGNORECASE), weight) for pattern, weight in self.promo_patterns]
    
    async def filter(self, content: str, context: FilterContext) -> FilterResult:
        """执行广告检测"""
        start_time = time.time()
        
        result = FilterResult(
            filtered_content=content,
            passed=True,
            confidence=0.0,
            details={}
        )
        
        try:
            # 获取消息结构信息
            buttons = context.get_metadata('buttons', [])
            entities = context.get_metadata('entities', [])
            message = context.get_metadata('telegram_message')
            
            # 执行多种检测方法
            detection_results = await self._comprehensive_ad_detection(
                content, buttons, entities, message, context
            )
            
            # 综合评估
            final_score, is_ad, main_reason = self._evaluate_detection_results(detection_results)
            
            if is_ad:
                result.passed = False
                result.should_early_stop = True  # 关键：设置早停标志
                result.confidence = final_score
                result.reason = f"检测到广告内容: {main_reason}"
                result.filtered_content = "[广告内容已过滤]"
                
                # 记录详细判定依据
                result.details = {
                    'detection_results': detection_results,
                    'final_score': final_score,
                    'main_reason': main_reason,
                    'threshold': self.final_threshold,
                    'methods_used': list(detection_results.keys())
                }
                
                logger.info(f"✅ 广告检测: 置信度 {final_score:.2f}, 原因: {main_reason}")
            else:
                result.details = {
                    'detection_results': detection_results,
                    'final_score': final_score,
                    'all_methods_passed': True
                }
                logger.debug(f"✅ 广告检测完成，综合评分: {final_score:.2f}，未超过阈值 {self.final_threshold}")
                
        except Exception as e:
            logger.error(f"广告检测失败: {e}", exc_info=True)
            # 异常时不影响消息处理，允许通过
            result.details['error'] = str(e)
        
        # 计算处理时间
        result.processing_time_ms = (time.time() - start_time) * 1000
        
        return result
    
    async def _comprehensive_ad_detection(self, content: str, buttons: List[Dict], 
                                        entities: List[Dict], message: Any,
                                        context: FilterContext) -> Dict[str, Dict]:
        """综合广告检测：整合所有检测方法"""
        results = {}
        
        # 1. AI语义检测
        if self._ai_initialized and content:
            results['ai_detection'] = await self._ai_ad_detection(content)
        
        # 2. 结构化检测（按钮和实体）
        if buttons or entities:
            results['structural_detection'] = await self._structural_ad_detection(
                content, buttons, entities, message
            )
        
        # 3. 模式匹配检测
        if content:
            results['pattern_detection'] = await self._pattern_ad_detection(content)
        
        # 4. 推广实体模式检测
        if entities:
            results['promotional_entity_detection'] = await self._promotional_entity_detection(
                content, entities
            )
        
        return results
    
    async def _ai_ad_detection(self, content: str) -> Dict[str, Any]:
        """AI语义广告检测"""
        result = {
            'is_ad': False,
            'confidence': 0.0,
            'similarity_score': 0.0,
            'method': 'AI语义检测'
        }
        
        if not self._ai_initialized or len(self._ai_embeddings) == 0:
            result['error'] = 'AI模型未初始化或无训练数据'
            return result
        
        try:
            # 计算文本的嵌入向量
            text_embedding = self._ai_model.encode([content])[0].reshape(1, -1)
            
            # 计算与所有广告样本的相似度
            from sklearn.metrics.pairwise import cosine_similarity
            import numpy as np
            
            similarities = cosine_similarity(text_embedding, self._ai_embeddings)
            max_similarity = float(np.max(similarities))
            
            result['similarity_score'] = max_similarity
            
            # 判断是否为广告
            if max_similarity >= self.ai_threshold:
                result['is_ad'] = True
                result['confidence'] = max_similarity
                logger.debug(f"AI检测到广告内容，相似度: {max_similarity:.3f}")
            else:
                result['confidence'] = 1.0 - max_similarity
                
        except Exception as e:
            result['error'] = str(e)
            logger.error(f"AI广告检测失败: {e}")
        
        return result
    
    async def _structural_ad_detection(self, content: str, buttons: List[Dict], 
                                     entities: List[Dict], message: Any) -> Dict[str, Any]:
        """结构化广告检测（按钮和实体分析）"""
        result = {
            'is_ad': False,
            'confidence': 0.0,
            'suspicious_buttons': [],
            'suspicious_entities': [],
            'method': '结构化检测'
        }
        
        confidence_scores = []
        
        # 检查按钮
        if buttons and content:
            button_analysis = self._analyze_buttons_semantics(content, buttons)
            if button_analysis['suspicious']:
                result['suspicious_buttons'] = button_analysis['buttons']
                confidence_scores.append(button_analysis['confidence'])
                
        # 检查实体链接
        if entities and content:
            entity_analysis = self._analyze_entities_semantics(content, entities)
            if entity_analysis['suspicious']:
                result['suspicious_entities'] = entity_analysis['entities']
                confidence_scores.append(entity_analysis['confidence'])
        
        # 检查URL模式
        url_analysis = self._analyze_suspicious_urls(buttons, entities)
        if url_analysis['suspicious']:
            confidence_scores.append(url_analysis['confidence'])
            result['suspicious_urls'] = url_analysis['urls']
        
        if confidence_scores:
            result['is_ad'] = True
            result['confidence'] = max(confidence_scores)
            
        return result
    
    async def _pattern_ad_detection(self, content: str) -> Dict[str, Any]:
        """模式匹配广告检测"""
        result = {
            'is_ad': False,
            'confidence': 0.0,
            'matched_patterns': [],
            'total_weight': 0,
            'method': '模式匹配检测'
        }
        
        total_weight = 0
        matched_patterns = []
        
        # 检查所有预定义模式
        for pattern, weight in self.compiled_patterns:
            matches = pattern.findall(content)
            if matches:
                matched_patterns.append({
                    'pattern': pattern.pattern,
                    'weight': weight,
                    'matches': matches
                })
                total_weight += weight
        
        result['matched_patterns'] = matched_patterns
        result['total_weight'] = total_weight
        
        # 根据权重判断
        if total_weight >= 10:  # 高权重模式
            result['is_ad'] = True
            result['confidence'] = min(1.0, total_weight / 15.0)
        elif total_weight >= 5:  # 中等权重
            result['is_ad'] = True
            result['confidence'] = min(0.8, total_weight / 10.0)
            
        return result
    
    async def _promotional_entity_detection(self, content: str, entities: List[Dict]) -> Dict[str, Any]:
        """推广实体模式检测（基于实体分析）"""
        result = {
            'is_ad': False,
            'confidence': 0.0,
            'entity_density': 0.0,
            'formatting_ratio': 0.0,
            'promotional_patterns': [],
            'method': '推广实体检测'
        }
        
        if not entities or not content:
            return result
        
        text_length = len(content)
        total_entities = len(entities)
        
        # 1. 计算实体密度
        entity_density = (total_entities * 100) / text_length
        result['entity_density'] = entity_density
        
        # 2. 统计格式化实体
        formatting_entities = 0
        for entity in entities:
            entity_type = entity.get('type', '')
            if entity_type in ['MessageEntityBold', 'MessageEntityItalic', 
                              'MessageEntityCode', 'MessageEntityPre',
                              'MessageEntityStrikethrough', 'MessageEntityUnderline']:
                formatting_entities += 1
        
        formatting_ratio = formatting_entities / total_entities if total_entities > 0 else 0
        result['formatting_ratio'] = formatting_ratio
        
        # 3. 检测"本频道推荐"标记
        channel_promo_detected = self._detect_channel_promotion_marker(content)
        if channel_promo_detected:
            result['promotional_patterns'].append('channel_promotion_marker')
        
        # 4. 检测代码块推广内容
        code_block_promo = self._detect_promotional_code_blocks(content, entities)
        if code_block_promo:
            result['promotional_patterns'].append('code_block_promotion')
        
        # 5. 检测实体组合模式
        entity_patterns = self._detect_entity_combination_patterns(entities)
        if entity_patterns:
            result['promotional_patterns'].extend(entity_patterns)
        
        # 综合判定
        confidence_scores = []
        
        # 实体密度过高
        if entity_density > 8.0:
            confidence_scores.append(min(0.8, entity_density / 15.0))
        
        # 格式化实体比例过高
        if formatting_ratio > 0.6 and total_entities > 5:
            confidence_scores.append(min(0.7, formatting_ratio))
        
        # 检测到推广模式
        if result['promotional_patterns']:
            confidence_scores.append(0.85)
        
        if confidence_scores:
            result['is_ad'] = True
            result['confidence'] = max(confidence_scores)
            
        return result
    
    def _analyze_buttons_semantics(self, content: str, buttons: List[Dict]) -> Dict[str, Any]:
        """分析按钮语义相关性"""
        if not self._ai_initialized or not content or not buttons:
            return {'suspicious': False, 'confidence': 0.0, 'buttons': []}
        
        try:
            # 提取按钮文本
            button_texts = [btn.get('text', '') for btn in buttons if btn.get('text')]
            if not button_texts:
                return {'suspicious': False, 'confidence': 0.0, 'buttons': []}
            
            # 检查语义相关性
            coherence = self._check_semantic_coherence(content, button_texts)
            
            # 低相关性表示可能是广告
            if coherence < self.semantic_coherence_threshold:
                return {
                    'suspicious': True,
                    'confidence': 1.0 - coherence,
                    'buttons': buttons,
                    'coherence_score': coherence
                }
            
        except Exception as e:
            logger.debug(f"分析按钮语义时出错: {e}")
        
        return {'suspicious': False, 'confidence': 0.0, 'buttons': []}
    
    def _analyze_entities_semantics(self, content: str, entities: List[Dict]) -> Dict[str, Any]:
        """分析实体语义相关性"""
        if not self._ai_initialized or not content or not entities:
            return {'suspicious': False, 'confidence': 0.0, 'entities': []}
        
        suspicious_entities = []
        max_confidence = 0.0
        
        try:
            for entity in entities:
                if entity.get('url') and entity.get('text'):
                    entity_text = entity['text']
                    # 检查链接文本与正文的相关性
                    coherence = self._check_semantic_coherence(content, [entity_text])
                    
                    if coherence < 0.4:  # 更严格的阈值
                        suspicious_entities.append({
                            **entity,
                            'coherence_score': coherence
                        })
                        max_confidence = max(max_confidence, 1.0 - coherence)
                        
        except Exception as e:
            logger.debug(f"分析实体语义时出错: {e}")
        
        return {
            'suspicious': len(suspicious_entities) > 0,
            'confidence': max_confidence,
            'entities': suspicious_entities
        }
    
    def _analyze_suspicious_urls(self, buttons: List[Dict], entities: List[Dict]) -> Dict[str, Any]:
        """分析可疑URL"""
        suspicious_urls = []
        
        # 检查按钮URL
        for button in buttons:
            url = button.get('url', '')
            if url and self._is_suspicious_url(url):
                suspicious_urls.append({'source': 'button', 'url': url, 'button': button})
        
        # 检查实体URL  
        for entity in entities:
            url = entity.get('url', '')
            if url and self._is_suspicious_url(url):
                suspicious_urls.append({'source': 'entity', 'url': url, 'entity': entity})
        
        return {
            'suspicious': len(suspicious_urls) > 0,
            'confidence': self.suspicious_url_threshold if suspicious_urls else 0.0,
            'urls': suspicious_urls
        }
    
    def _check_semantic_coherence(self, main_text: str, button_texts: List[str]) -> float:
        """检查按钮文本与正文的语义相关性"""
        if not self._ai_initialized or not main_text or not button_texts:
            return 1.0
        
        try:
            # 计算正文的嵌入向量
            main_embedding = self._ai_model.encode([main_text])[0]
            
            # 计算所有按钮文本的组合嵌入向量
            combined_button_text = ' '.join(button_texts)
            button_embedding = self._ai_model.encode([combined_button_text])[0]
            
            # 计算余弦相似度
            from sklearn.metrics.pairwise import cosine_similarity
            similarity = cosine_similarity(
                main_embedding.reshape(1, -1),
                button_embedding.reshape(1, -1)
            )[0][0]
            
            return float(similarity)
            
        except Exception as e:
            logger.debug(f"语义相关性检查失败: {e}")
            return 1.0
    
    def _is_suspicious_url(self, url: str) -> bool:
        """检查URL是否可疑"""
        if not url:
            return False
        
        url_lower = url.lower()
        
        # 短链接服务
        short_url_patterns = [
            r'bit\.ly', r'tinyurl\.com', r'goo\.gl', r'ow\.ly',
            r't\.co', r'short\.link', r'tiny\.cc'
        ]
        
        for pattern in short_url_patterns:
            if re.search(pattern, url_lower):
                return True
        
        # Telegram邀请链接
        if 't.me/+' in url or 't.me/joinchat/' in url:
            return True
        
        # 非Telegram域名的HTTP链接
        if re.match(r'https?://(?!(?:t\.me|telegram\.me|telegra\.ph))', url_lower):
            return True
            
        return False
    
    def _detect_channel_promotion_marker(self, text: str) -> bool:
        """检测"本频道推荐"标记"""
        channel_promo_patterns = [
            r'[😆🎉🔥⭐✨]*\s*本频道推荐\s*[😆🎉🔥⭐✨]*',
            r'[🐾🎯💰🏆⚡]*\s*本频道推荐\s*[🐾🎯💰🏆⚡]*',
            r'\*+\s*本频道推荐\s*\*+',
            r'#+\s*本频道推荐\s*#+',
        ]
        
        for pattern in channel_promo_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        
        return False
    
    def _detect_promotional_code_blocks(self, text: str, entities: List[Dict]) -> bool:
        """检测代码块实体中的推广内容"""
        # 查找代码块实体
        code_block_entities = [
            entity for entity in entities 
            if entity.get('type') == 'MessageEntityPre'
        ]
        
        if not code_block_entities:
            return False
        
        # 推广关键词
        promotional_keywords = [
            '华硕科技', '币盘', 'EX', '交易所', '包网',
            '银河国际', '专属回馈', '现已上线',
            '订阅频道', '投稿爆料', '联系', '@yefan11',
            '坚若磐石', '全天在线', '迎咨询'
        ]
        
        # 检查每个代码块的内容
        for entity in code_block_entities:
            offset = entity.get('offset', 0)
            length = entity.get('length', 0)
            
            if offset + length <= len(text):
                code_content = text[offset:offset + length]
                
                promo_keyword_count = sum(1 for keyword in promotional_keywords if keyword in code_content)
                
                # 如果代码块包含多个推广关键词，判定为推广内容
                if promo_keyword_count >= 2:
                    return True
        
        return False
    
    def _detect_entity_combination_patterns(self, entities: List[Dict]) -> List[str]:
        """检测实体组合模式"""
        patterns = []
        
        if len(entities) < 3:
            return patterns
        
        # 按偏移量排序实体
        sorted_entities = sorted(entities, key=lambda x: x.get('offset', 0))
        entity_types = [entity.get('type', '') for entity in sorted_entities]
        
        # 模式1：连续的Bold实体（装饰性格式化）
        consecutive_bold_count = 0
        max_consecutive_bold = 0
        for entity_type in entity_types:
            if entity_type == 'MessageEntityBold':
                consecutive_bold_count += 1
                max_consecutive_bold = max(max_consecutive_bold, consecutive_bold_count)
            else:
                consecutive_bold_count = 0
        
        if max_consecutive_bold >= 3:
            patterns.append('consecutive_bold_formatting')
        
        # 模式2：Pre + 多个URL的组合
        has_pre = 'MessageEntityPre' in entity_types
        url_count = entity_types.count('MessageEntityUrl') + entity_types.count('MessageEntityTextUrl')
        
        if has_pre and url_count >= 2:
            patterns.append('code_block_with_multiple_urls')
        
        # 模式3：实体类型多样性异常
        unique_types = set(entity_types)
        if len(unique_types) >= 5 and len(entities) <= 15:
            patterns.append('diverse_entity_types')
        
        return patterns
    
    def _evaluate_detection_results(self, detection_results: Dict[str, Dict]) -> Tuple[float, bool, str]:
        """综合评估检测结果"""
        scores = []
        reasons = []
        
        # AI检测结果
        if 'ai_detection' in detection_results:
            ai_result = detection_results['ai_detection']
            if ai_result.get('is_ad', False):
                scores.append(ai_result['confidence'] * 0.9)  # AI检测权重较高
                reasons.append(f"AI检测(相似度:{ai_result.get('similarity_score', 0):.2f})")
        
        # 结构化检测结果
        if 'structural_detection' in detection_results:
            struct_result = detection_results['structural_detection']
            if struct_result.get('is_ad', False):
                scores.append(struct_result['confidence'] * 0.85)
                reasons.append("结构化检测")
        
        # 模式检测结果
        if 'pattern_detection' in detection_results:
            pattern_result = detection_results['pattern_detection']
            if pattern_result.get('is_ad', False):
                scores.append(pattern_result['confidence'] * 0.8)
                reasons.append(f"模式匹配(权重:{pattern_result.get('total_weight', 0)})")
        
        # 推广实体检测结果
        if 'promotional_entity_detection' in detection_results:
            promo_result = detection_results['promotional_entity_detection']
            if promo_result.get('is_ad', False):
                scores.append(promo_result['confidence'] * 0.75)
                reasons.append("推广实体模式")
        
        # 计算最终得分
        if scores:
            final_score = max(scores)  # 使用最高分数
            main_reason = reasons[scores.index(max(scores))]
            is_ad = final_score >= self.final_threshold
        else:
            final_score = 0.0
            main_reason = "无广告特征"
            is_ad = False
        
        return final_score, is_ad, main_reason
    
    async def validate_config(self) -> bool:
        """验证配置是否有效"""
        try:
            # 检查阈值参数
            if not (0.0 < self.ai_threshold <= 1.0):
                logger.error("ai_threshold 必须在 (0, 1] 范围内")
                return False
            
            if not (0.0 < self.semantic_coherence_threshold <= 1.0):
                logger.error("semantic_coherence_threshold 必须在 (0, 1] 范围内")
                return False
            
            if not (0.0 < self.final_threshold <= 1.0):
                logger.error("final_threshold 必须在 (0, 1] 范围内")
                return False
            
            return True
        except Exception as e:
            logger.error(f"验证配置失败: {e}")
            return False


# 创建默认实例
ad_detector_filter = AdDetectorFilter()