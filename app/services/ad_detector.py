"""
AI广告检测器模块
使用纯AI方法检测广告内容
"""
import logging
import json
import numpy as np
from typing import Tuple, List, Optional
from pathlib import Path
from datetime import datetime
import asyncio
from app.core.training_config import TrainingDataConfig

logger = logging.getLogger(__name__)


class AdDetector:
    """纯AI广告检测器"""
    
    def __init__(self):
        self.model = None
        self.ad_embeddings = []
        self.initialized = False
        self.ad_samples_file = TrainingDataConfig.AD_TRAINING_FILE
        
        # 初始化模型
        self._initialize()
        
        # 加载已有的广告样本（延迟加载，在第一次使用时）
        self._samples_loaded = False
    
    def _initialize(self):
        """初始化AI模型"""
        try:
            from sentence_transformers import SentenceTransformer
            # 使用与ai_filter相同的多语言模型
            self.model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
            self.initialized = True
            logger.info("✅ 广告检测器初始化成功")
        except ImportError:
            logger.warning("⚠️ sentence-transformers 未安装，广告检测功能暂不可用")
        except Exception as e:
            logger.error(f"广告检测器初始化失败: {e}")
    
    def _load_ad_samples_sync(self):
        """同步加载已有的广告训练样本"""
        try:
            if not self.ad_samples_file.exists():
                logger.debug("没有找到广告训练数据文件")
                return
            
            with open(self.ad_samples_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 使用统一的samples字段
            ad_samples = data.get("samples", [])
            if ad_samples:
                # 提取内容
                contents = [s["content"] for s in ad_samples if s.get("content")]
                if contents:
                    # 计算嵌入向量
                    logger.info(f"正在加载 {len(contents)} 个广告样本...")
                    self.ad_embeddings = self.model.encode(contents)
                    logger.info(f"✅ 成功加载 {len(self.ad_embeddings)} 个广告样本")
                    
        except Exception as e:
            logger.error(f"加载广告样本失败: {e}")
    
    async def _load_ad_samples(self):
        """异步加载已有的广告训练样本（保留以兼容）"""
        self._load_ad_samples_sync()
    
    def is_advertisement_ai(self, text: str) -> Tuple[bool, float]:
        """
        使用纯AI方法判断文本是否为广告
        
        Args:
            text: 要检查的文本
            
        Returns:
            (是否为广告, 置信度)
        """
        if not self.initialized:
            # 模型未初始化，默认不是广告
            return False, 0.0
        
        # 延迟加载广告样本
        if not self._samples_loaded:
            self._load_ad_samples_sync()
            self._samples_loaded = True
        
        if len(self.ad_embeddings) == 0:
            # 没有训练样本，默认不是广告
            return False, 0.0
        
        try:
            # 计算文本的嵌入向量
            text_embedding = self.model.encode([text])[0].reshape(1, -1)
            
            # 计算与所有广告样本的相似度
            from sklearn.metrics.pairwise import cosine_similarity
            similarities = cosine_similarity(text_embedding, self.ad_embeddings)
            
            # 获取最高相似度
            max_similarity = float(np.max(similarities))
            
            # 动态阈值判断
            # 如果与任何广告样本的相似度超过0.75，认为是广告
            threshold = 0.75
            is_ad = max_similarity >= threshold
            
            # 置信度为最高相似度
            confidence = max_similarity if is_ad else (1.0 - max_similarity)
            
            if is_ad:
                logger.debug(f"检测到广告内容，相似度: {max_similarity:.3f}")
            
            return is_ad, confidence
            
        except Exception as e:
            logger.error(f"AI广告检测失败: {e}")
            return False, 0.0
    
    def check_semantic_coherence(self, main_text: str, button_texts: List[str]) -> float:
        """
        检查按钮文本与正文的语义相关性
        
        Args:
            main_text: 消息正文
            button_texts: 按钮文本列表
            
        Returns:
            相关性分数 (0-1)，越低表示越可能是广告
        """
        if not self.initialized or not main_text or not button_texts:
            return 1.0
        
        try:
            # 计算正文的嵌入向量
            main_embedding = self.model.encode([main_text])[0]
            
            # 计算所有按钮文本的组合嵌入向量
            combined_button_text = ' '.join(button_texts)
            button_embedding = self.model.encode([combined_button_text])[0]
            
            # 计算余弦相似度
            from sklearn.metrics.pairwise import cosine_similarity
            similarity = cosine_similarity(
                main_embedding.reshape(1, -1),
                button_embedding.reshape(1, -1)
            )[0][0]
            
            logger.debug(f"按钮与正文语义相似度: {similarity:.3f}")
            
            # 如果相似度很低，可能是不相关的广告按钮
            return float(similarity)
            
        except Exception as e:
            logger.error(f"语义相关性检查失败: {e}")
            return 1.0
    
    def analyze_structural_ad(self, text: str, buttons: List[dict], entities: List[dict]) -> dict:
        """
        分析结构化广告
        
        Args:
            text: 消息文本
            buttons: 按钮列表 [{'text': '按钮文字', 'url': '链接'}]
            entities: 实体列表 [{'type': '类型', 'url': '链接', 'text': '文本'}]
            
        Returns:
            分析结果字典
        """
        result = {
            'has_ad': False,
            'confidence': 0.0,
            'ad_type': None,
            'suspicious_buttons': [],
            'suspicious_entities': []
        }
        
        if not self.initialized:
            return result
        
        # 1. 检查按钮的语义相关性
        if buttons:
            button_texts = [btn.get('text', '') for btn in buttons if btn.get('text')]
            if button_texts and text:
                coherence = self.check_semantic_coherence(text, button_texts)
                
                # 如果相关性很低，标记为可疑
                if coherence < 0.3:
                    result['has_ad'] = True
                    result['confidence'] = 1.0 - coherence
                    result['ad_type'] = 'unrelated_buttons'
                    result['suspicious_buttons'] = buttons
                    logger.info(f"检测到不相关的广告按钮，相关性: {coherence:.3f}")
        
        # 2. 检查实体链接的相关性
        if entities and text:
            for entity in entities:
                if entity.get('url'):
                    entity_text = entity.get('text', '')
                    if entity_text:
                        # 检查链接文本与正文的相关性
                        coherence = self.check_semantic_coherence(text, [entity_text])
                        if coherence < 0.4:
                            result['suspicious_entities'].append(entity)
                            if not result['has_ad']:
                                result['has_ad'] = True
                                result['confidence'] = max(result['confidence'], 1.0 - coherence)
                                result['ad_type'] = 'hidden_ad_links'
        
        return result
    
    async def update_ad_samples(self, new_samples: List[str]):
        """
        更新广告样本库
        
        Args:
            new_samples: 新的广告样本列表
        """
        if not self.initialized or not new_samples:
            return
        
        try:
            logger.info(f"正在更新广告检测模型，新增 {len(new_samples)} 个样本...")
            
            # 计算新样本的嵌入向量
            new_embeddings = self.model.encode(new_samples)
            
            # 合并到现有的嵌入向量
            if len(self.ad_embeddings) > 0:
                self.ad_embeddings = np.vstack([self.ad_embeddings, new_embeddings])
            else:
                self.ad_embeddings = new_embeddings
            
            # 限制样本数量，避免内存过大
            max_samples = 1000
            if len(self.ad_embeddings) > max_samples:
                # 保留最新的样本
                self.ad_embeddings = self.ad_embeddings[-max_samples:]
            
            logger.info(f"✅ 广告检测模型更新完成，当前样本数: {len(self.ad_embeddings)}")
            
        except Exception as e:
            logger.error(f"更新广告样本失败: {e}")
    
    def get_stats(self) -> dict:
        """获取检测器统计信息"""
        return {
            "initialized": self.initialized,
            "ad_samples_count": len(self.ad_embeddings),
            "model_name": "paraphrase-multilingual-MiniLM-L12-v2" if self.initialized else None,
            "threshold": 0.75
        }


# 全局实例
ad_detector = AdDetector()