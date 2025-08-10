"""
图片文字提取服务
使用OCR技术从图片中提取文字，用于广告检测
"""
import logging
import re
import cv2
import numpy as np
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# 延迟导入EasyOCR，避免启动时加载过慢
_ocr_reader = None
_ocr_initialized = False


def get_ocr_reader():
    """获取OCR读取器（延迟初始化）"""
    global _ocr_reader, _ocr_initialized
    
    if not _ocr_initialized:
        try:
            import easyocr
            # 支持中文、英文、俄文（适用于多语言频道）
            _ocr_reader = easyocr.Reader(['ch_sim', 'en', 'ru'], gpu=False)
            _ocr_initialized = True
            logger.info("✅ OCR读取器初始化成功")
        except ImportError:
            logger.error("❌ EasyOCR未安装，图片文字提取功能不可用")
        except Exception as e:
            logger.error(f"❌ OCR初始化失败: {e}")
    
    return _ocr_reader


class ImageTextExtractor:
    """图片文字提取器"""
    
    def __init__(self):
        self.cache = {}  # 简单的内存缓存
        self.cache_ttl = 3600  # 缓存1小时
        self.max_cache_size = 100
        
        # 广告相关关键词（用于重点检测）
        self.ad_keywords = [
            # 赌博相关
            '赌场', '赌博', '娱乐城', '百家乐', '真人', '棋牌',
            '彩票', '博彩', 'casino', 'poker', 'slot',
            # 金融诈骗
            '投资', '理财', '返利', '返水', '充值', '提现',
            '日赚', '月入', '躺赚', '暴富',
            # 联系方式
            '客服', '微信', 'QQ', 'telegram', '@', 't.me',
            # 推广词汇
            '注册', '下载', '免费', '优惠', '折扣', '特价',
            '火爆', '爆款', '限时', '秒杀'
        ]
        
        # URL正则
        self.url_pattern = re.compile(
            r'(?:https?://|www\.|t\.me/|@)[^\s]+',
            re.IGNORECASE
        )
        
        # 联系方式正则
        self.contact_patterns = {
            'wechat': re.compile(r'(?:微信|WeChat|VX)[：:\s]*[\w\-]+', re.IGNORECASE),
            'qq': re.compile(r'(?:QQ|扣扣)[：:\s]*[\d]+', re.IGNORECASE),
            'telegram': re.compile(r'(?:@[\w]+|t\.me/[\w]+)', re.IGNORECASE),
            'phone': re.compile(r'(?:1[3-9]\d{9}|[\d\-\s]{7,})', re.IGNORECASE)
        }
    
    async def extract_text(self, image_path: str) -> str:
        """
        从图片中提取文字
        
        Args:
            image_path: 图片文件路径
            
        Returns:
            提取的文字内容
        """
        try:
            # 检查缓存
            cache_key = self._get_cache_key(image_path)
            if cache_key in self.cache:
                cached_data = self.cache[cache_key]
                if datetime.now() - cached_data['time'] < timedelta(seconds=self.cache_ttl):
                    logger.debug(f"使用缓存的OCR结果: {image_path}")
                    return cached_data['text']
            
            # 获取OCR读取器
            reader = get_ocr_reader()
            if not reader:
                return ""
            
            # 执行OCR
            result = reader.readtext(image_path)
            
            # 提取文字
            texts = []
            for (bbox, text, confidence) in result:
                if confidence > 0.5:  # 只保留置信度大于0.5的文字
                    texts.append(text)
            
            extracted_text = ' '.join(texts)
            
            # 更新缓存
            self._update_cache(cache_key, extracted_text)
            
            logger.info(f"OCR提取文字成功，长度: {len(extracted_text)}")
            return extracted_text
            
        except Exception as e:
            logger.error(f"OCR提取文字失败: {e}")
            return ""
    
    async def detect_qr_codes(self, image_path: str) -> List[str]:
        """
        检测图片中的二维码
        
        Args:
            image_path: 图片文件路径
            
        Returns:
            二维码内容列表
        """
        try:
            from pyzbar import pyzbar
            
            # 读取图片
            image = cv2.imread(image_path)
            if image is None:
                return []
            
            # 检测二维码
            qr_codes = pyzbar.decode(image)
            
            results = []
            for qr in qr_codes:
                data = qr.data.decode('utf-8')
                results.append(data)
                logger.info(f"检测到二维码: {data[:50]}...")
            
            return results
            
        except ImportError:
            logger.warning("pyzbar未安装，二维码检测功能不可用")
            return []
        except Exception as e:
            logger.error(f"二维码检测失败: {e}")
            return []
    
    async def extract_urls(self, text: str) -> List[str]:
        """
        从文字中提取URL
        
        Args:
            text: 文字内容
            
        Returns:
            URL列表
        """
        if not text:
            return []
        
        urls = self.url_pattern.findall(text)
        return list(set(urls))  # 去重
    
    async def detect_contact_info(self, text: str) -> Dict[str, List[str]]:
        """
        检测联系方式
        
        Args:
            text: 文字内容
            
        Returns:
            联系方式字典
        """
        if not text:
            return {}
        
        contacts = {}
        for contact_type, pattern in self.contact_patterns.items():
            matches = pattern.findall(text)
            if matches:
                contacts[contact_type] = list(set(matches))  # 去重
        
        return contacts
    
    async def analyze_ad_content(self, image_path: str) -> Dict[str, any]:
        """
        分析图片中的广告内容
        
        Args:
            image_path: 图片文件路径
            
        Returns:
            分析结果字典
        """
        result = {
            'has_text': False,
            'text': '',
            'has_qr': False,
            'qr_codes': [],
            'urls': [],
            'contacts': {},
            'ad_keywords': [],
            'ad_score': 0.0
        }
        
        try:
            # 提取文字
            text = await self.extract_text(image_path)
            if text:
                result['has_text'] = True
                result['text'] = text
                
                # 提取URL
                result['urls'] = await self.extract_urls(text)
                
                # 检测联系方式
                result['contacts'] = await self.detect_contact_info(text)
                
                # 检测广告关键词
                text_lower = text.lower()
                for keyword in self.ad_keywords:
                    if keyword.lower() in text_lower:
                        result['ad_keywords'].append(keyword)
            
            # 检测二维码
            qr_codes = await self.detect_qr_codes(image_path)
            if qr_codes:
                result['has_qr'] = True
                result['qr_codes'] = qr_codes
                
                # 从二维码中提取URL
                for qr_text in qr_codes:
                    qr_urls = await self.extract_urls(qr_text)
                    result['urls'].extend(qr_urls)
            
            # 计算广告分数
            result['ad_score'] = self._calculate_ad_score(result)
            
            return result
            
        except Exception as e:
            logger.error(f"分析广告内容失败: {e}")
            return result
    
    def _calculate_ad_score(self, analysis: Dict) -> float:
        """计算广告分数（0-1）"""
        score = 0.0
        
        # 有二维码 +0.3
        if analysis['has_qr']:
            score += 0.3
        
        # 有URL +0.2
        if analysis['urls']:
            score += 0.2
        
        # 有联系方式 +0.2
        if analysis['contacts']:
            score += 0.2
        
        # 广告关键词
        keyword_count = len(analysis['ad_keywords'])
        if keyword_count > 0:
            score += min(0.3, keyword_count * 0.1)  # 最多加0.3
        
        return min(1.0, score)  # 确保不超过1.0
    
    def _get_cache_key(self, image_path: str) -> str:
        """生成缓存键"""
        return f"ocr_{Path(image_path).name}"
    
    def _update_cache(self, key: str, text: str):
        """更新缓存"""
        # 限制缓存大小
        if len(self.cache) >= self.max_cache_size:
            # 删除最旧的缓存项
            oldest_key = min(self.cache.keys(), 
                           key=lambda k: self.cache[k]['time'])
            del self.cache[oldest_key]
        
        self.cache[key] = {
            'text': text,
            'time': datetime.now()
        }


# 全局实例
image_text_extractor = ImageTextExtractor()