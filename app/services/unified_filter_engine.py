"""
统一的消息过滤引擎
整合所有广告检测、尾部过滤、AI检测逻辑
确保所有消息处理路径使用相同的过滤逻辑
"""
import re
import logging
import asyncio
from typing import Tuple, List, Optional, Dict, Any
from pathlib import Path
import json

logger = logging.getLogger(__name__)

class UnifiedFilterEngine:
    """统一的消息过滤引擎"""
    
    def __init__(self):
        """初始化引擎"""
        self.ai_filter = None
        self.semantic_tail_filter = None
        self.ad_training_data = []
        self.high_risk_patterns = []
        self._initialized = False
        
        # 初始化组件
        self._initialize_components()
        
    def _initialize_components(self):
        """初始化所有组件"""
        try:
            # 导入AI过滤器
            from app.services.ai_filter import ai_filter
            self.ai_filter = ai_filter
            
            # 导入语义尾部过滤器（使用语义分析和训练样本）
            from app.services.semantic_tail_filter import semantic_tail_filter
            self.semantic_tail_filter = semantic_tail_filter
            
            # 加载训练数据
            self._load_training_data()
            
            # 初始化高风险模式
            self._init_high_risk_patterns()
            
            self._initialized = True
            logger.info("✅ 统一过滤引擎初始化成功")
            
        except Exception as e:
            logger.error(f"统一过滤引擎初始化失败: {e}")
            
    def _load_training_data(self):
        """加载所有训练数据"""
        try:
            # 加载广告训练数据
            ad_file = Path("data/ad_training_data.json")
            if ad_file.exists():
                with open(ad_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # 处理JSON结构：{"samples": [...]}
                    if isinstance(data, dict) and 'samples' in data:
                        self.ad_training_data = data['samples']
                    else:
                        self.ad_training_data = data if isinstance(data, list) else []
                        
                logger.info(f"加载了 {len(self.ad_training_data)} 个广告训练样本")
                
                # 让AI过滤器学习这些样本
                if self.ai_filter and self.ai_filter.initialized:
                    ad_texts = []
                    for item in self.ad_training_data:
                        if isinstance(item, dict) and item.get('content'):
                            ad_texts.append(item['content'])
                    
                    if ad_texts:
                        # 异步训练AI模型（需要在事件循环中运行）
                        try:
                            loop = asyncio.get_running_loop()
                            loop.create_task(self._train_ai_with_samples(ad_texts))
                            logger.info(f"准备训练AI模型，样本数: {len(ad_texts)}")
                        except RuntimeError:
                            # 没有运行的事件循环，记录但不阻塞
                            logger.debug(f"无法异步训练AI模型（无事件循环），样本数: {len(ad_texts)}")
                        
        except Exception as e:
            logger.error(f"加载训练数据失败: {e}")
            
    async def _train_ai_with_samples(self, samples: List[str]):
        """用训练样本训练AI模型"""
        try:
            if self.ai_filter and self.ai_filter.initialized:
                # 将样本添加到AI过滤器的广告样本库
                for sample in samples[:100]:  # 限制数量避免内存过大
                    if sample and len(sample) > 20:
                        # 计算嵌入向量并存储
                        embedding = self.ai_filter.model.encode([sample])[0]
                        self.ai_filter.ad_embeddings.append(embedding)
                logger.info(f"AI模型已学习 {len(samples[:100])} 个广告样本")
        except Exception as e:
            logger.error(f"AI训练失败: {e}")
            
    def _init_high_risk_patterns(self):
        """初始化高风险广告检测模式"""
        self.high_risk_patterns = [
            # === 通用赌博模式 ===
            # 充值赠送模式
            r'首[存充]\d+.*[赠送]\d+',
            r'首[存充].*送.*\d+[%％]',
            r'充值.*[返赠].*\d+',
            r'存款.*优惠.*\d+',
            
            # 无需实名模式
            r'无需实名|無需實名',
            r'不限.*[Ii][Pp]',
            r'匿名.*[登錄]',
            r'免实名|免實名',
            
            # 大额提款模式
            r'[千万萬].*无忧|無憂',
            r'巨额.*出款',
            r'日[出入赚賺].*\d+[万萬uU]',
            r'单日.*盈利.*\d+',
            r'提款.*不限.*额度',
            
            # 平台特征词
            r'娱乐城|娛樂城',
            r'[国國][际際].*平台',
            r'线上.*博彩|線上.*博彩',
            r'体育.*平台|體育.*平台',
            r'棋牌.*游戏|遊戲',
            r'真人.*视讯|視訊',
            r'电子.*游艺|遊藝',
            
            # 支付方式
            r'[Uu]存[Uu]提',
            r'USDT.*[存充].*款',
            r'泰达币|泰達幣',
            r'虚拟币.*充值|虛擬幣.*充值',
            r'数字货币.*支付|數字貨幣.*支付',
            
            # 诱导词汇
            r'日赚|日賺|月入|月赚|月賺',
            r'暴富|暴利|稳赚|穩賺',
            r'零风险|零風險|包赢|包贏',
            r'内幕|內幕|必中|必赢|必贏',
            
            # 客服账号模式（只在有赌博背景时才算高风险）
            # 注释掉这些通用客服模式，避免误判
            
            # 多个赌博相关词汇组合
            r'(?:博彩|棋牌|体育|娱乐|平台).*(?:博彩|棋牌|体育|娱乐|平台)',
            r'(?:首存|首充|优惠|返水).*(?:首存|首充|优惠|返水)',
        ]
        
    def is_high_risk_ad(self, content: str) -> Tuple[bool, List[str]]:
        """
        检测是否为高风险广告
        
        Returns:
            (是否高风险, 匹配的模式列表)
        """
        if not content:
            return False, []
            
        matched_patterns = []
        
        # 检查高风险模式
        for pattern in self.high_risk_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                matched_patterns.append(pattern[:30])  # 记录匹配的模式
                
        # 检查多链接模式（3个以上不同域名）
        urls = re.findall(r'https?://([^/\s]+)', content)
        unique_domains = set(urls)
        if len(unique_domains) >= 3:
            matched_patterns.append("多个不同域名链接")
            
        # 特殊关键词组合检测（赌博相关组合）
        special_keywords = {
            '担保': ['担保', '联名担保', '保证'],
            '娱乐': ['娱乐城', '博彩', '体验金', '派发'],
            '赌博': ['首存', '二存', '三存', '存款', '充值', '赠送', '返水'],
            '平台': ['平台', '官网', '注册', '登录']
        }
        
        keyword_hits = 0
        for category, keywords in special_keywords.items():
            for keyword in keywords:
                if keyword in content:
                    keyword_hits += 1
                    break
                    
        if keyword_hits >= 3:
            matched_patterns.append("多个赌博关键词组合")
            
        # 判定逻辑：更严格的高风险判定
        # 1. 匹配3个或以上模式 -> 高风险
        # 2. 匹配"首存"相关模式 + 其他2个以上赌博特征 -> 高风险
        # 3. 多个赌博关键词组合达到3个以上 -> 高风险  
        is_high_risk = (
            len(matched_patterns) >= 3 or
            (any('首[存充]' in p for p in matched_patterns) and keyword_hits >= 3) or
            keyword_hits >= 4
        )
        
        if is_high_risk:
            logger.warning(f"检测到高风险广告，匹配模式: {matched_patterns}")
            
        return is_high_risk, matched_patterns
        
    async def detect_advertisement(
        self,
        content: str,
        channel_id: Optional[str] = None,
        message_obj: Any = None,
        media_files: Optional[List[str]] = None
    ) -> Tuple[bool, str, str]:
        """
        统一的广告检测方法 - 优化检测优先级
        
        Args:
            content: 消息内容
            channel_id: 频道ID
            message_obj: 消息对象
            media_files: 媒体文件列表
            
        Returns:
            (是否广告, 过滤后内容, 过滤原因)
        """
        if not content:
            return False, content, ""
            
        is_ad = False
        filtered_content = content
        reasons = []
        
        # 0. 优先级最高：实体结构检测（新增，基于Telegram原生结构）
        if message_obj:
            try:
                from app.services.structural_ad_detector import structural_detector
                structural_result = await structural_detector.detect_structural_ads(message_obj)
                
                if structural_result['has_structural_ad']:
                    is_ad = True
                    filtered_content = structural_result['clean_text']
                    reasons.append(f"结构化检测({structural_result['ad_type']})")
                    logger.info(f"实体结构检测到推广: {structural_result['ad_type']}, 置信度: {structural_result['confidence']:.2f}")
                    
                    # 如果结构化检测置信度很高，直接返回结果
                    if structural_result['confidence'] > 0.85:
                        return True, filtered_content, " | ".join(reasons)
                        
            except Exception as e:
                logger.debug(f"实体结构检测失败: {e}")
        
        # 1. 智能尾部过滤 - 优先移除推广尾部
        # 使用ContentFilter的逻辑进行尾部过滤
        try:
            from app.services.content_filter import ContentFilter
            temp_filter = ContentFilter()
            
            # 使用ContentFilter的推广内容过滤来处理尾部
            has_media = media_files and len(media_files) > 0
            temp_filtered = temp_filter.filter_promotional_content(filtered_content, channel_id, has_media)
            if temp_filtered != filtered_content:
                original_len = len(filtered_content)
                filtered_len = len(temp_filtered)
                filtered_content = temp_filtered
                
                # 如果过滤后完全没有内容，且原始内容不为空
                if not filtered_content.strip() and original_len > 0:
                    is_ad = True
                    reasons.append("完全是尾部推广")
                else:
                    # 仅移除了尾部，不标记为广告
                    reasons.append("移除尾部内容（非广告）")
                    
                logger.info(f"移除了尾部推广: {original_len - filtered_len} 字符")
        except Exception as e:
            logger.debug(f"尾部过滤失败: {e}")
                
        # 2. 高风险广告检测（在尾部过滤后的内容上检测）
        if not is_ad:  # 只有在尾部过滤没有标记为广告时才检测
            is_high_risk, risk_patterns = self.is_high_risk_ad(filtered_content)
            if is_high_risk:
                is_ad = True
                reasons.append(f"高风险广告({len(risk_patterns)}个特征)")
                # 高风险广告直接清空内容
                filtered_content = ""
                logger.warning(f"检测到高风险广告，内容已清空")
                return True, "", " | ".join(reasons)
                
        # 3. AI广告检测（使用训练数据）- 只有在前面检测都未识别时才运行
        if not is_ad and self.ai_filter and self.ai_filter.initialized:
            try:
                is_ad_by_ai, ai_confidence = self.ai_filter.is_advertisement(filtered_content)
                if is_ad_by_ai and ai_confidence > 0.8:
                    is_ad = True
                    reasons.append(f"AI检测(置信度:{ai_confidence:.2f})")
                    logger.info(f"AI检测到广告，置信度: {ai_confidence:.2f}")
            except Exception as e:
                logger.debug(f"AI检测失败: {e}")
                
        # 4. OCR检测（如果有媒体文件）
        if media_files and not is_ad:
            try:
                from app.services.ocr_service import ocr_service
                
                # 过滤出图片文件
                image_files = []
                for media_file in media_files:
                    if media_file and any(media_file.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']):
                        image_files.append(media_file)
                
                if image_files and ocr_service.initialized:
                    logger.info(f"统一引擎OCR处理 {len(image_files)} 个图片文件")
                    
                    # 批量处理图片
                    ocr_results = await ocr_service.batch_extract_content(image_files)
                    
                    # 分析OCR结果
                    total_ad_score = 0
                    ocr_ad_indicators = []
                    
                    for file_path, result in ocr_results.items():
                        if result.get('error'):
                            logger.warning(f"OCR处理失败: {file_path} - {result['error']}")
                            continue
                        
                        ad_score = result.get('ad_score', 0)
                        ad_indicators = result.get('ad_indicators', [])
                        
                        total_ad_score = max(total_ad_score, ad_score)
                        ocr_ad_indicators.extend(ad_indicators)
                    
                    # OCR广告检测
                    if total_ad_score >= 50:  # 50分以上直接判定为广告
                        is_ad = True
                        reasons.append(f"OCR检测高风险广告(分数:{total_ad_score:.0f})")
                        # 清空内容，因为是纯广告媒体
                        filtered_content = ""
                        logger.warning(f"OCR检测到高风险广告媒体，分数: {total_ad_score}")
                        return True, "", " | ".join(reasons)
                    elif total_ad_score >= 30:  # 30-49分标记为广告但保留内容
                        is_ad = True
                        reasons.append(f"OCR检测广告内容(分数:{total_ad_score:.0f})")
                        logger.info(f"OCR检测到广告媒体，分数: {total_ad_score}")
                        
            except Exception as e:
                logger.debug(f"OCR检测失败: {e}")
            
        # 5. 最终判定：只有明确被识别为广告的才标记为广告
        # 不再因为内容被过滤就标记为广告
        # 已经在上面的各个检测步骤中设置了is_ad标志
                
        filter_reason = " | ".join(reasons) if reasons else ""
        
        return is_ad, filtered_content, filter_reason
        
    def detect_advertisement_sync(
        self,
        content: str,
        channel_id: Optional[str] = None,
        message_obj: Any = None
    ) -> Tuple[bool, str, str]:
        """
        同步版本的广告检测（向后兼容）- 优先使用实体检测
        通过asyncio.run调用异步版本，确保实体检测和AI检测生效
        """
        try:
            # 创建新的事件循环运行异步方法
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(
                self.detect_advertisement(content, channel_id, message_obj)
            )
            loop.close()
            return result
        except RuntimeError:
            # 如果已经在事件循环中，尝试直接调用
            try:
                future = asyncio.ensure_future(
                    self.detect_advertisement(content, channel_id, message_obj)
                )
                # 等待完成（这在某些情况下可能不工作）
                return asyncio.get_event_loop().run_until_complete(future)
            except:
                # 降级到基本检测，但仍然尝试使用实体检测
                logger.warning("无法运行异步检测，降级到基本检测")
                
                # 尝试同步调用实体检测
                if message_obj:
                    try:
                        from app.services.structural_ad_detector import structural_detector
                        # 同步调用实体检测（不使用await）
                        components = structural_detector._extract_message_components(message_obj)
                        entity_result = structural_detector._detect_promotional_entity_patterns(message_obj, components)
                        
                        if entity_result['has_ad']:
                            logger.info(f"同步实体检测到推广: {entity_result['ad_type']}")
                            return True, entity_result['clean_text'], f"结构化检测({entity_result['ad_type']})"
                    except Exception as e:
                        logger.debug(f"同步实体检测失败: {e}")
                
                # 最后降级到高风险检测
                is_high_risk, _ = self.is_high_risk_ad(content)
                if is_high_risk:
                    return True, "", "高风险广告"
                return False, content, ""

# 全局实例
unified_filter_engine = UnifiedFilterEngine()