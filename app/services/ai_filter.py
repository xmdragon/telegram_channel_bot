"""
AI智能过滤模块
使用句子嵌入和机器学习技术实现智能的广告检测和尾部过滤
"""
import logging
import json
import numpy as np
from typing import Dict, List, Tuple, Optional
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.cluster import DBSCAN
from collections import defaultdict
import asyncio
from datetime import datetime, timedelta
import threading

logger = logging.getLogger(__name__)

class IntelligentFilter:
    """智能过滤器 - 基于AI的内容过滤"""
    
    def __init__(self):
        self.model = None
        self.channel_patterns = {}  # 存储每个频道的尾部模式
        self.ad_embeddings = []  # 广告样本的嵌入向量
        self.normal_embeddings = []  # 正常内容的嵌入向量
        self.initialized = False
        self._lock = threading.RLock()  # 保护共享数据的锁
        
        # 尝试加载模型
        self._initialize()
        
        # 尝试加载已保存的模式
        if self.initialized:
            try:
                import os
                patterns_file = "data/ai_filter_patterns.json"
                if os.path.exists(patterns_file):
                    self.load_patterns(patterns_file)
                    logger.info(f"✅ 从 {patterns_file} 加载了AI过滤模式")
            except Exception as e:
                logger.error(f"加载AI过滤模式失败: {e}")
    
    def _initialize(self):
        """初始化模型"""
        try:
            from sentence_transformers import SentenceTransformer
            # 使用多语言模型，支持中文
            self.model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
            self.initialized = True
            logger.info("✅ AI过滤器初始化成功")
        except ImportError:
            logger.warning("⚠️ sentence-transformers 未安装，AI过滤功能暂不可用")
        except Exception as e:
            logger.error(f"AI过滤器初始化失败: {e}")
    
    async def learn_channel_pattern(self, channel_id: str, messages: List[str]) -> bool:
        """
        学习特定频道的尾部模式
        
        Args:
            channel_id: 频道ID
            messages: 该频道的历史消息列表
            
        Returns:
            是否学习成功
        """
        if not self.initialized or not messages:
            return False
        
        try:
            # 更智能地提取尾部内容
            tails = []
            for msg in messages:
                tail = self._extract_real_tail(msg)
                if tail and len(tail) > 20:  # 只收集有效的尾部
                    tails.append(tail)
            
            # 动态判断样本数量 - 不再固定要求10个
            min_samples = min(5, len(tails))  # 最少5个样本，或者所有可用样本
            if len(tails) < min_samples:
                logger.info(f"频道 {channel_id} 样本不足（{len(tails)}个），跳过学习")
                return False
            
            # 计算尾部的嵌入向量
            logger.info(f"正在学习频道 {channel_id} 的尾部模式...")
            tail_embeddings = self.model.encode(tails)
            
            # 使用DBSCAN聚类找出重复的模式
            # 动态调整聚类参数：样本少时降低要求
            min_cluster_size = max(2, len(tails) // 5)  # 至少占20%的样本
            clustering = DBSCAN(eps=0.3, min_samples=min_cluster_size, metric='cosine')
            labels = clustering.fit_predict(tail_embeddings)
            
            # 找出最大的聚类（最常见的尾部模式）
            label_counts = defaultdict(int)
            for label in labels:
                if label != -1:  # -1 表示噪声点
                    label_counts[label] += 1
            
            if not label_counts:
                logger.info(f"频道 {channel_id} 没有发现重复的尾部模式（可能无固定尾部）")
                return False
            
            # 获取最大聚类的中心向量
            max_label = max(label_counts, key=label_counts.get)
            cluster_indices = [i for i, l in enumerate(labels) if l == max_label]
            cluster_embeddings = tail_embeddings[cluster_indices]
            
            # 存储该频道的尾部模式（使用聚类中心）
            with self._lock:
                self.channel_patterns[channel_id] = {
                    'centroid': np.mean(cluster_embeddings, axis=0),
                    'samples': cluster_embeddings[:5],  # 保存几个样本用于验证
                    'threshold': 0.75,  # 相似度阈值
                    'learned_at': datetime.now().isoformat(),
                    'sample_count': len(cluster_indices)
                }
            
            logger.info(f"✅ 频道 {channel_id} 尾部模式学习完成，发现 {len(cluster_indices)} 个相似样本")
            return True
            
        except Exception as e:
            logger.error(f"学习频道 {channel_id} 模式失败: {e}")
            return False
    
    def is_channel_tail(self, channel_id: str, text: str) -> Tuple[bool, float]:
        """
        判断文本是否为特定频道的尾部内容
        
        Args:
            channel_id: 频道ID
            text: 要检查的文本
            
        Returns:
            (是否为尾部, 相似度分数)
        """
        if not self.initialized:
            return False, 0.0
        
        with self._lock:
            if channel_id not in self.channel_patterns:
                return False, 0.0
            pattern = self.channel_patterns[channel_id].copy()
        
        try:
            text_embedding = self.model.encode([text])[0]
            
            # 计算与频道尾部模式的相似度
            similarity = cosine_similarity(
                text_embedding.reshape(1, -1),
                pattern['centroid'].reshape(1, -1)
            )[0][0]
            
            is_tail = similarity >= pattern['threshold']
            return is_tail, float(similarity)
            
        except Exception as e:
            logger.error(f"检查尾部内容失败: {e}")
            return False, 0.0
    
    def _extract_real_tail(self, content: str) -> str:
        """
        智能提取消息的真正尾部（推广内容）
        
        Args:
            content: 消息内容
            
        Returns:
            真正的尾部内容，如果没有则返回空字符串
        """
        import re
        lines = content.split('\n')
        if len(lines) < 3:
            return ""
        
        # 寻找明确的分隔标志
        separator_patterns = [
            r'^[-=_—➖▪▫◆◇■□●○•～~]{5,}$',  # 符号分隔线
            r'^[📢📣🔔💬❤️🔗🔍✉️📮😍]*\s*$',  # 表情分隔
            r'^\s*[-=]{3,}\s*$',  # 简单分隔线
        ]
        
        # 推广内容的特征
        promo_indicators = [
            r'https?://',  # 链接
            r'@[a-zA-Z][a-zA-Z0-9_]{4,}',  # Telegram用户名
            r't\.me/',  # Telegram链接
            r'(?:订阅|關注|投稿|商务|联系|失联|导航)',  # 推广关键词
            r'\[.*\]\(.*\)',  # Markdown链接
        ]
        
        # 从后向前查找分隔符
        separator_index = -1
        for i in range(len(lines) - 1, max(0, len(lines) - 15), -1):
            line = lines[i].strip()
            # 检查是否是分隔符
            for pattern in separator_patterns:
                if re.match(pattern, line):
                    # 验证分隔符后面是否有推广内容
                    has_promo = False
                    for j in range(i + 1, min(i + 5, len(lines))):
                        for promo in promo_indicators:
                            if re.search(promo, lines[j], re.IGNORECASE):
                                has_promo = True
                                break
                        if has_promo:
                            break
                    
                    if has_promo:
                        separator_index = i
                        break
            
            if separator_index != -1:
                break
        
        # 如果找到分隔符，返回分隔符之后的内容
        if separator_index != -1:
            tail = '\n'.join(lines[separator_index + 1:])
            return tail.strip()
        
        # 如果没有分隔符，寻找推广内容的起始位置
        promo_start = -1
        for i in range(len(lines) - 1, max(0, len(lines) - 10), -1):
            line = lines[i]
            # 检查是否包含多个推广特征
            promo_count = sum(1 for p in promo_indicators if re.search(p, line, re.IGNORECASE))
            if promo_count >= 2:  # 至少2个推广特征
                promo_start = i
        
        # 如果找到推广内容，返回从那里开始的内容
        if promo_start != -1 and promo_start < len(lines) - 1:
            tail = '\n'.join(lines[promo_start:])
            return tail.strip()
        
        # 如果既没有分隔符也没有明显的推广内容，返回空
        return ""
    
    def filter_channel_tail(self, channel_id: str, content: str) -> str:
        """
        过滤掉频道特定的尾部内容 - 智能版本
        
        Args:
            channel_id: 频道ID
            content: 原始内容
            
        Returns:
            过滤后的内容
        """
        # 优先使用规则检测，找到明确的尾部边界
        rule_based_result = self._filter_by_rules(content)
        if rule_based_result != content:
            logger.info(f"规则检测过滤了尾部: {len(content)} -> {len(rule_based_result)} 字符")
            return rule_based_result
        
        # 如果规则无法判断，才使用AI模型
        if not self.initialized:
            return content
        
        with self._lock:
            has_pattern = channel_id in self.channel_patterns
        
        if not has_pattern:
            return content
        
        lines = content.split('\n')
        if len(lines) <= 3:
            return content
        
        # 使用更智能的边界检测
        tail_boundary = self._find_tail_boundary(content, channel_id)
        
        if tail_boundary != -1 and tail_boundary < len(lines):
            filtered = '\n'.join(lines[:tail_boundary])
            keep_ratio = tail_boundary / len(lines)
            logger.info(f"AI检测过滤频道 {channel_id} 尾部: {len(content)} -> {len(filtered)} 字符 (保留{keep_ratio*100:.0f}%)")
            return filtered.strip()
        
        return content
    
    def _filter_by_rules(self, content: str) -> str:
        """
        使用规则优先过滤尾部推广内容
        
        Args:
            content: 原始内容
            
        Returns:
            过滤后的内容
        """
        import re
        lines = content.split('\n')
        
        # 分隔符模式
        separator_patterns = [
            r'^[-=_—➖▪▫◆◇■□●○•～~]{5,}$',
            r'^[📢📣🔔💬❤️🔗🔍✉️📮😍]{2,}.*$',
            r'^\s*[-=]{3,}\s*$',
        ]
        
        # 推广内容特征
        promo_indicators = [
            r'\[.*\]\(https?://.*\)',  # Markdown链接
            r't\.me/[a-zA-Z][a-zA-Z0-9_]{4,}',  # Telegram链接
            r'@[a-zA-Z][a-zA-Z0-9_]{4,}',  # Telegram用户名
            r'(?:订阅|關注|投稿|商务|联系|失联|导航).*(?:@|t\.me/)',  # 推广词+链接
        ]
        
        # 从后向前查找分隔符
        for i in range(len(lines) - 1, max(0, len(lines) - 15), -1):
            line = lines[i].strip()
            
            # 检查是否是分隔符
            is_separator = any(re.match(p, line) for p in separator_patterns)
            
            if is_separator:
                # 验证分隔符后面是否有推广内容
                has_promo_after = False
                for j in range(i + 1, min(i + 5, len(lines))):
                    if any(re.search(p, lines[j], re.IGNORECASE) for p in promo_indicators):
                        has_promo_after = True
                        break
                
                if has_promo_after:
                    # 找到了真正的尾部边界
                    return '\n'.join(lines[:i]).strip()
        
        return content
    
    def _find_tail_boundary(self, content: str, channel_id: str) -> int:
        """
        使用AI模型智能查找尾部边界
        
        Args:
            content: 消息内容
            channel_id: 频道ID
            
        Returns:
            尾部开始的行号，如果没找到返回-1
        """
        lines = content.split('\n')
        
        # 只在最后30%的内容中查找尾部
        search_start = max(0, int(len(lines) * 0.7))
        
        # 从后向前检查，但限制范围
        for i in range(len(lines) - 1, search_start, -1):
            # 检查从第i行到结尾的内容
            test_tail = '\n'.join(lines[i:])
            is_tail, score = self.is_channel_tail(channel_id, test_tail)
            
            # 提高阈值，避免误判
            if is_tail and score > 0.85:
                # 双向验证
                # 1. 检查是否包含推广内容
                if not self._contains_promo_content(test_tail):
                    continue  # 不包含推广内容，跳过
                
                # 2. 检查前面的内容是否是正文
                if i > 0:
                    test_main = '\n'.join(lines[:i])
                    if self._is_main_content(test_main):
                        # 前面确实是正文，这里是合理的边界
                        return i
                    else:
                        # 前面不像正文，可能整个都是推广，继续向前查找
                        continue
                else:
                    # 如果i=0，意味着要删除整个内容，需要特别谨慎
                    if self._is_main_content(test_tail):
                        # 内容包含正文特征，不应该全部删除
                        return -1
                    else:
                        # 确实都是推广内容
                        return i
        
        return -1
    
    def _contains_promo_content(self, text: str) -> bool:
        """
        检查文本是否包含推广内容特征
        
        Args:
            text: 要检查的文本
            
        Returns:
            是否包含推广内容
        """
        import re
        promo_patterns = [
            r'https?://',
            r't\.me/',
            r'@[a-zA-Z][a-zA-Z0-9_]{4,}',
            r'(?:订阅|關注|投稿|商务|联系)',
            r'\[.*\]\(.*\)',
        ]
        
        # 至少包含2个推广特征才认为是推广内容
        promo_count = sum(1 for p in promo_patterns if re.search(p, text, re.IGNORECASE))
        return promo_count >= 2
    
    def _is_main_content(self, text: str) -> bool:
        """
        判断文本是否是正文内容（双向验证）
        
        Args:
            text: 要检查的文本
            
        Returns:
            是否是正文内容
        """
        import re
        
        # 正文内容的特征
        content_indicators = [
            # 叙事性内容
            r'(?:我|你|他|她|它|们|咱|俺|您)',  # 人称代词
            r'(?:了|着|过|的|地|得)',  # 助词
            r'(?:是|有|在|到|去|来|说|做|看|想|要)',  # 常用动词
            r'(?:今天|昨天|明天|现在|当时|后来|然后)',  # 时间词
            r'(?:因为|所以|但是|可是|如果|虽然)',  # 连词
            
            # 情感表达
            r'(?:喜欢|讨厌|高兴|难过|生气|害怕|希望)',
            r'(?:😊|😂|😭|😍|😤|😱|🤔|💔)',  # 情感表情
            
            # 故事性内容
            r'(?:故事|经历|发生|遇到|发现|记得|曾经)',
            r'(?:第一|第二|首先|其次|最后|终于)',
            
            # 观点表达
            r'(?:认为|觉得|感觉|建议|应该|可能|也许)',
        ]
        
        # 计算正文特征数量
        content_score = 0
        for pattern in content_indicators:
            if re.search(pattern, text, re.IGNORECASE):
                content_score += 1
        
        # 如果包含多个正文特征，认为是正文
        if content_score >= 3:
            return True
        
        # 检查文本长度和句子结构
        sentences = re.split(r'[。！？\n]', text)
        long_sentences = [s for s in sentences if len(s) > 20]
        
        # 如果有多个长句子，可能是正文
        if len(long_sentences) >= 2:
            return True
        
        return False
    
    async def train_ad_classifier(self, ad_samples: List[str], normal_samples: List[str]):
        """
        训练广告分类器
        
        Args:
            ad_samples: 广告样本列表
            normal_samples: 正常内容样本列表
        """
        if not self.initialized:
            logger.warning("AI过滤器未初始化，无法训练")
            return
        
        try:
            logger.info(f"开始训练广告分类器: {len(ad_samples)} 个广告样本, {len(normal_samples)} 个正常样本")
            
            # 计算嵌入向量
            ad_emb = self.model.encode(ad_samples) if ad_samples else []
            normal_emb = self.model.encode(normal_samples) if normal_samples else []
            
            with self._lock:
                if len(ad_emb) > 0:
                    self.ad_embeddings = ad_emb
                if len(normal_emb) > 0:
                    self.normal_embeddings = normal_emb
            
            logger.info("✅ 广告分类器训练完成")
            
        except Exception as e:
            logger.error(f"训练广告分类器失败: {e}")
    
    def is_advertisement(self, text: str) -> Tuple[bool, float]:
        """
        判断文本是否为广告
        
        Args:
            text: 要检查的文本
            
        Returns:
            (是否为广告, 置信度)
        """
        if not self.initialized:
            return False, 0.0
        
        with self._lock:
            ad_emb_copy = self.ad_embeddings.copy() if len(self.ad_embeddings) > 0 else []
            normal_emb_copy = self.normal_embeddings.copy() if len(self.normal_embeddings) > 0 else []
        
        if len(ad_emb_copy) == 0 and len(normal_emb_copy) == 0:
            return False, 0.0
        
        try:
            text_embedding = self.model.encode([text])[0].reshape(1, -1)
            
            # 计算与广告样本的相似度
            ad_similarity = 0.0
            if len(ad_emb_copy) > 0:
                ad_similarities = cosine_similarity(text_embedding, ad_emb_copy)
                ad_similarity = np.max(ad_similarities)
            
            # 计算与正常内容的相似度
            normal_similarity = 0.0
            if len(normal_emb_copy) > 0:
                normal_similarities = cosine_similarity(text_embedding, normal_emb_copy)
                normal_similarity = np.max(normal_similarities)
            
            # 如果更像广告，则判定为广告
            is_ad = ad_similarity > normal_similarity and ad_similarity > 0.7
            confidence = float(ad_similarity) if is_ad else float(1 - ad_similarity)
            
            return is_ad, confidence
            
        except Exception as e:
            logger.error(f"广告检测失败: {e}")
            return False, 0.0
    
    def save_patterns(self, filepath: str):
        """保存学习的模式到文件"""
        try:
            data = {
                'channel_patterns': {},
                'ad_sample_count': len(self.ad_embeddings),
                'normal_sample_count': len(self.normal_embeddings),
                'saved_at': datetime.now().isoformat()
            }
            
            # 转换numpy数组为列表以便JSON序列化
            with self._lock:
                for channel_id, pattern in self.channel_patterns.items():
                    data['channel_patterns'][channel_id] = {
                        'centroid': pattern['centroid'].tolist(),
                        'threshold': pattern['threshold'],
                        'learned_at': pattern['learned_at'],
                        'sample_count': pattern['sample_count']
                    }
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"模式已保存到 {filepath}")
            
        except Exception as e:
            logger.error(f"保存模式失败: {e}")
    
    def load_patterns(self, filepath: str):
        """从文件加载学习的模式"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 恢复numpy数组
            with self._lock:
                for channel_id, pattern_data in data['channel_patterns'].items():
                    self.channel_patterns[channel_id] = {
                        'centroid': np.array(pattern_data['centroid']),
                        'threshold': pattern_data['threshold'],
                        'learned_at': pattern_data['learned_at'],
                        'sample_count': pattern_data['sample_count'],
                        'samples': []  # 加载时不恢复样本
                    }
            
            logger.info(f"从 {filepath} 加载了 {len(self.channel_patterns)} 个频道模式")
            
        except Exception as e:
            logger.error(f"加载模式失败: {e}")


# 全局实例
ai_filter = IntelligentFilter()