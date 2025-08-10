"""
OCR文字提取和二维码识别服务
结合EasyOCR和pyzbar实现全面的图像内容提取
"""
import asyncio
import logging
import re
import cv2
import numpy as np
from typing import Dict, List, Tuple, Optional, Any
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import io
import hashlib

logger = logging.getLogger(__name__)

class OCRService:
    """OCR文字提取和二维码识别服务"""
    
    def __init__(self):
        self.ocr_reader = None
        self.initialized = False
        self.thread_pool = ThreadPoolExecutor(max_workers=2)  # 限制并发数量
        self.cache = {}  # 简单的缓存机制
        self.cache_max_size = 100
        
        # 广告相关的模式匹配
        self.ad_patterns = [
            # 联系方式模式
            r'(?:微信|WeChat|wechat|WX|wx)[\s:：]*[A-Za-z0-9_-]+',
            r'(?:QQ|qq)[\s:：]*[0-9]{5,}',
            r'(?:电话|手机|Tel|tel|电話|手機)[\s:：]*[0-9\-\+\(\)\s]{7,}',
            r'[0-9]{3,4}[-\s][0-9]{7,8}',  # 电话号码格式
            r'1[3-9][0-9]{9}',  # 中国手机号
            
            # URL模式（非Telegram）
            r'(?:http[s]?://|www\.)[^\s]+',
            r'[a-zA-Z0-9.-]+\.(?:com|cn|net|org|info|biz|co|me|io|tv)[^\s]*',
            
            # 商业模式
            r'(?:营业时间|營業時間|营业中|營業中)',
            r'(?:店铺|店鋪|门店|門店|商店|店面)[\s]*(?:地址|位置)',
            r'(?:优惠|優惠|折扣|打折|特价|特價|促销|促銷)',
            r'(?:接单|接單|下单|下單|订购|訂購|咨询|諮詢)',
            
            # 赌博相关
            r'(?:博彩|体育|足球|篮球|彩票|棋牌|娱乐城|赌场|casino)',
            r'(?:USDT|usdt|泰达币|虚拟币|充值|提款|出款)',
            r'(?:返水|首充|注册就送|日出千万)',
            
            # 金融投资
            r'(?:投资|投資|理财|理財|炒股|股票|基金)',
            r'(?:贷款|貸款|借钱|借錢|放贷|放貸)',
            r'(?:利率|年化|收益|盈利|赚钱|賺錢)',
        ]
        
        # 初始化OCR
        self._initialize_ocr()
        
    def _initialize_ocr(self):
        """初始化OCR引擎"""
        try:
            import easyocr
            # 支持中英文识别
            self.ocr_reader = easyocr.Reader(['ch_sim', 'en'], gpu=False)
            self.initialized = True
            logger.info("✅ OCR服务初始化成功 (支持中英文)")
        except ImportError:
            logger.warning("⚠️ EasyOCR未安装，OCR功能不可用")
        except Exception as e:
            logger.error(f"❌ OCR服务初始化失败: {e}")
    
    def _calculate_image_hash(self, image_data: bytes) -> str:
        """计算图片数据的哈希值用于缓存"""
        return hashlib.md5(image_data).hexdigest()[:16]
    
    def _extract_text_sync(self, image_path: str) -> List[str]:
        """同步提取图片文字（在线程池中执行）"""
        try:
            if not self.initialized:
                return []
            
            # 使用OpenCV加载图片
            image = cv2.imread(image_path)
            if image is None:
                logger.warning(f"无法加载图片: {image_path}")
                return []
            
            # 图片预处理 - 增强文字清晰度
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            
            # 自适应阈值处理
            processed = cv2.adaptiveThreshold(
                gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
            )
            
            # 使用EasyOCR提取文字
            results = self.ocr_reader.readtext(processed, detail=0, paragraph=False)
            
            # 过滤和清理文字
            cleaned_texts = []
            for text in results:
                # 去除空白和特殊字符
                clean_text = re.sub(r'\s+', ' ', text.strip())
                if len(clean_text) >= 2:  # 至少2个字符
                    cleaned_texts.append(clean_text)
            
            logger.debug(f"从图片提取到 {len(cleaned_texts)} 条文字")
            return cleaned_texts
            
        except Exception as e:
            logger.error(f"文字提取失败: {e}")
            return []
    
    def _detect_qrcodes_sync(self, image_path: str) -> List[Dict[str, Any]]:
        """同步检测二维码（在线程池中执行）"""
        try:
            import pyzbar.pyzbar as pyzbar
            
            # 使用OpenCV加载图片
            image = cv2.imread(image_path)
            if image is None:
                return []
            
            # 转换为灰度
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            
            # 检测二维码
            qr_codes = pyzbar.decode(gray)
            
            results = []
            for qr in qr_codes:
                try:
                    # 解码数据
                    data = qr.data.decode('utf-8')
                    qr_type = qr.type
                    
                    results.append({
                        'type': qr_type,
                        'data': data,
                        'position': {
                            'x': qr.rect.left,
                            'y': qr.rect.top,
                            'width': qr.rect.width,
                            'height': qr.rect.height
                        }
                    })
                except UnicodeDecodeError:
                    # 尝试其他编码
                    try:
                        data = qr.data.decode('gbk')
                        results.append({
                            'type': qr_type,
                            'data': data,
                            'position': {
                                'x': qr.rect.left,
                                'y': qr.rect.top,
                                'width': qr.rect.width,
                                'height': qr.rect.height
                            }
                        })
                    except:
                        logger.warning(f"无法解码二维码数据: {qr.data[:50]}")
            
            if results:
                logger.debug(f"检测到 {len(results)} 个二维码")
            
            return results
            
        except ImportError:
            logger.warning("⚠️ pyzbar未安装，二维码识别功能不可用")
            return []
        except Exception as e:
            logger.error(f"二维码检测失败: {e}")
            return []
    
    async def extract_image_content(self, image_path: str) -> Dict[str, Any]:
        """
        从图片中提取文字和二维码内容
        
        Args:
            image_path: 图片文件路径
            
        Returns:
            包含文字和二维码信息的字典
        """
        if not Path(image_path).exists():
            logger.warning(f"图片文件不存在: {image_path}")
            return {
                'texts': [],
                'qr_codes': [],
                'combined_text': '',
                'has_ad_content': False,
                'ad_score': 0.0,
                'ad_indicators': []
            }
        
        try:
            # 检查缓存
            with open(image_path, 'rb') as f:
                image_data = f.read()
            
            image_hash = self._calculate_image_hash(image_data)
            if image_hash in self.cache:
                logger.debug(f"使用缓存的OCR结果: {image_path}")
                return self.cache[image_hash]
            
            # 并行执行文字提取和二维码检测
            text_task = asyncio.get_event_loop().run_in_executor(
                self.thread_pool, self._extract_text_sync, image_path
            )
            qr_task = asyncio.get_event_loop().run_in_executor(
                self.thread_pool, self._detect_qrcodes_sync, image_path
            )
            
            # 等待两个任务完成
            texts, qr_codes = await asyncio.gather(text_task, qr_task)
            
            # 合并所有文字内容
            all_texts = texts.copy()
            for qr in qr_codes:
                if qr.get('data'):
                    all_texts.append(qr['data'])
            
            combined_text = ' '.join(all_texts)
            
            # 分析广告内容
            has_ad_content, ad_score, ad_indicators = self._analyze_ad_content(
                texts, qr_codes, combined_text
            )
            
            result = {
                'texts': texts,
                'qr_codes': qr_codes,
                'combined_text': combined_text,
                'has_ad_content': has_ad_content,
                'ad_score': ad_score,
                'ad_indicators': ad_indicators
            }
            
            # 更新缓存
            if len(self.cache) >= self.cache_max_size:
                # 简单的LRU：清除一半缓存
                items = list(self.cache.items())
                self.cache = dict(items[self.cache_max_size//2:])
            
            self.cache[image_hash] = result
            
            logger.info(f"图片内容提取完成: 文字{len(texts)}条, 二维码{len(qr_codes)}个, 广告分数{ad_score:.2f}")
            
            return result
            
        except Exception as e:
            logger.error(f"图片内容提取失败: {e}")
            return {
                'texts': [],
                'qr_codes': [],
                'combined_text': '',
                'has_ad_content': False,
                'ad_score': 0.0,
                'ad_indicators': []
            }
    
    def _analyze_ad_content(self, texts: List[str], qr_codes: List[Dict], combined_text: str) -> Tuple[bool, float, List[str]]:
        """
        分析图片内容中的广告特征
        
        Args:
            texts: 提取的文字列表
            qr_codes: 二维码信息列表
            combined_text: 合并的文字内容
            
        Returns:
            (是否包含广告, 广告分数, 广告指标列表)
        """
        ad_score = 0.0
        ad_indicators = []
        
        # 1. 检查文字中的广告模式
        for pattern in self.ad_patterns:
            matches = re.findall(pattern, combined_text, re.IGNORECASE)
            if matches:
                ad_score += len(matches) * 10  # 每个匹配加10分
                ad_indicators.extend([f"文字广告模式: {match[:20]}" for match in matches[:3]])
        
        # 2. 检查二维码内容
        for qr in qr_codes:
            qr_data = qr.get('data', '')
            
            # 检查二维码中的URL
            if re.match(r'https?://', qr_data, re.IGNORECASE):
                # 排除Telegram链接
                if not re.search(r'(?:t\.me|telegram\.me|telegra\.ph)', qr_data, re.IGNORECASE):
                    ad_score += 25  # 非Telegram链接加25分
                    ad_indicators.append(f"外部链接二维码: {qr_data[:30]}")
                else:
                    ad_score += 5  # Telegram链接加5分
                    ad_indicators.append(f"Telegram二维码: {qr_data[:30]}")
            
            # 检查二维码中的联系信息
            for pattern in self.ad_patterns[:5]:  # 只检查联系方式相关模式
                if re.search(pattern, qr_data, re.IGNORECASE):
                    ad_score += 15
                    ad_indicators.append(f"联系信息二维码: {qr_data[:30]}")
                    break
        
        # 3. 特殊加权
        # 如果有多个不同类型的广告指标，增加权重
        if len(set(indicator.split(':')[0] for indicator in ad_indicators)) >= 2:
            ad_score *= 1.2  # 提高20%
            ad_indicators.append("多种广告特征组合")
        
        # 4. 文字密度检查（文字很少但有联系方式的情况）
        if len(combined_text) < 50 and ad_score > 10:
            ad_score *= 1.5  # 简短文字+广告信息，提高权重
            ad_indicators.append("简短文字包含广告信息")
        
        # 标准化分数到0-100
        ad_score = min(ad_score, 100)
        has_ad = ad_score >= 30  # 30分以上认为是广告
        
        return has_ad, ad_score, ad_indicators
    
    def analyze_image_for_ads(self, texts: List[str], qr_codes: List[Dict]) -> Dict[str, Any]:
        """
        专门用于广告检测的图片内容分析
        
        Args:
            texts: 文字列表
            qr_codes: 二维码列表
            
        Returns:
            广告分析结果
        """
        combined_text = ' '.join(texts + [qr.get('data', '') for qr in qr_codes])
        has_ad, ad_score, ad_indicators = self._analyze_ad_content(texts, qr_codes, combined_text)
        
        return {
            'is_ad': has_ad,
            'confidence': ad_score / 100.0,
            'score': ad_score,
            'indicators': ad_indicators,
            'text_count': len(texts),
            'qr_count': len(qr_codes),
            'combined_text_length': len(combined_text)
        }
    
    async def batch_extract_content(self, image_paths: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        批量提取多张图片的内容
        
        Args:
            image_paths: 图片路径列表
            
        Returns:
            以图片路径为key的结果字典
        """
        tasks = []
        for path in image_paths:
            task = self.extract_image_content(path)
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        output = {}
        for i, result in enumerate(results):
            path = image_paths[i]
            if isinstance(result, Exception):
                logger.error(f"批量OCR处理失败 {path}: {result}")
                output[path] = {
                    'texts': [],
                    'qr_codes': [],
                    'combined_text': '',
                    'has_ad_content': False,
                    'ad_score': 0.0,
                    'ad_indicators': [],
                    'error': str(result)
                }
            else:
                output[path] = result
        
        return output
    
    def get_stats(self) -> Dict[str, Any]:
        """获取OCR服务统计信息"""
        return {
            'initialized': self.initialized,
            'cache_size': len(self.cache),
            'cache_max_size': self.cache_max_size,
            'thread_pool_workers': self.thread_pool._max_workers,
            'supported_languages': ['中文', '英文'] if self.initialized else [],
            'ad_patterns_count': len(self.ad_patterns)
        }
    
    def clear_cache(self):
        """清除缓存"""
        self.cache.clear()
        logger.info("OCR缓存已清除")
    
    def __del__(self):
        """析构函数，清理资源"""
        try:
            if hasattr(self, 'thread_pool'):
                self.thread_pool.shutdown(wait=True)
        except:
            pass


# 全局OCR服务实例
ocr_service = OCRService()