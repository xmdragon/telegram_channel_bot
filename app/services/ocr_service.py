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
        self.cache_memory_limit = 50 * 1024 * 1024  # 50MB内存限制
        self._cache_lock = asyncio.Lock()  # 缓存操作锁
        
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
            # 检查必要的库
            import cv2
            from PIL import Image
            import numpy as np
            
            # 尝试初始化EasyOCR进行真实文字识别
            try:
                self._initialize_easyocr()
                if self.ocr_reader is not None:
                    logger.info("✅ OCR服务初始化成功 (使用EasyOCR真实文字识别)")
                    self.initialized = True
                    return
            except Exception as e:
                logger.warning(f"⚠️ EasyOCR初始化失败，降级到图像特征分析: {e}")
            
            # 如果EasyOCR初始化失败，标记为已初始化但使用图像特征分析
            self.initialized = True
            logger.info("✅ OCR服务初始化成功 (使用图像特征分析)")
            
        except ImportError as e:
            logger.warning(f"⚠️ OCR依赖缺失: {e}")
            self.initialized = False
        except Exception as e:
            logger.error(f"❌ OCR服务初始化失败: {e}")
            self.initialized = False
    
    def _calculate_image_hash(self, image_data: bytes) -> str:
        """计算图片数据的哈希值用于缓存"""
        return hashlib.md5(image_data).hexdigest()[:16]
    
    def _extract_text_sync(self, image_path: str) -> List[str]:
        """同步提取图片文字（使用EasyOCR真实文字识别）"""
        try:
            # 检查OCR是否初始化且EasyOCR可用
            if not self.initialized or self.ocr_reader is None:
                logger.warning("OCR未初始化或EasyOCR不可用，使用图像特征分析")
                return self._extract_text_features_fallback(image_path)
            
            # 使用EasyOCR进行真实文字识别
            try:
                result = self.ocr_reader.readtext(image_path)
                
                # 提取识别到的文字
                texts = []
                for bbox, text, confidence in result:
                    # 过滤置信度太低的结果
                    if confidence > 0.5 and text.strip():
                        texts.append(text.strip())
                
                logger.debug(f"EasyOCR识别到 {len(texts)} 个文字: {texts}")
                return texts
                
            except Exception as e:
                logger.error(f"EasyOCR文字识别失败: {e}")
                # 如果EasyOCR失败，使用图像特征分析作为回退
                return self._extract_text_features_fallback(image_path)
                
        except Exception as e:
            logger.error(f"文字提取失败: {e}")
            return []
    
    def _initialize_easyocr(self):
        """初始化EasyOCR"""
        try:
            import easyocr
            if self.ocr_reader is None:
                logger.info("正在初始化EasyOCR（支持中英文识别）...")
                # 创建中英文OCR识别器，gpu=False确保兼容性
                self.ocr_reader = easyocr.Reader(['ch_sim', 'en'], gpu=False)
                logger.info("EasyOCR初始化成功")
            self.initialized = True
        except Exception as e:
            logger.error(f"EasyOCR初始化失败: {e}")
            self.initialized = False
    
    def _extract_text_features_fallback(self, image_path: str) -> List[str]:
        """回退方案：使用图像特征分析（原方法）"""
        try:
            from PIL import Image
            import numpy as np
            
            # 加载图片
            try:
                pil_image = Image.open(image_path)
            except Exception as e:
                logger.warning(f"无法加载图片: {image_path} - {e}")
                return []
            
            # 转换为RGB
            if pil_image.mode != 'RGB':
                pil_image = pil_image.convert('RGB')
            
            # 使用OpenCV进行图像分析
            image = cv2.imread(image_path)
            if image is None:
                return []
            
            # 基于图像特征的广告文字检测
            # 虽然不能真正提取文字内容，但可以检测文字区域特征
            detected_texts = []
            
            # 1. 检测高对比度区域（文字通常有高对比度）
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            
            # 2. 边缘检测找文字轮廓
            edges = cv2.Canny(gray, 50, 150)
            
            # 3. 形态学操作连接文字区域
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
            closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)
            
            # 4. 查找轮廓
            contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            # 5. 分析轮廓特征判断是否为文字区域
            text_regions = 0
            for contour in contours:
                area = cv2.contourArea(contour)
                if area > 100 and area < 10000:  # 文字区域大小范围
                    x, y, w, h = cv2.boundingRect(contour)
                    aspect_ratio = w / float(h)
                    # 文字区域通常有特定的宽高比
                    if 0.5 < aspect_ratio < 10:
                        text_regions += 1
            
            # 基于检测到的文字区域数量返回模拟结果
            if text_regions > 5:
                # 检测到多个文字区域，可能包含广告文字
                detected_texts.append("检测到密集文字区域")
                
            # 6. 颜色分析 - 广告文字通常使用鲜艳颜色
            hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
            
            # 检测红色区域（广告常用）
            lower_red1 = np.array([0, 50, 50])
            upper_red1 = np.array([10, 255, 255])
            lower_red2 = np.array([170, 50, 50])
            upper_red2 = np.array([180, 255, 255])
            
            mask1 = cv2.inRange(hsv, lower_red1, upper_red1)
            mask2 = cv2.inRange(hsv, lower_red2, upper_red2)
            red_mask = mask1 | mask2
            
            red_pixels = cv2.countNonZero(red_mask)
            total_pixels = image.shape[0] * image.shape[1]
            red_ratio = red_pixels / total_pixels
            
            if red_ratio > 0.05:  # 降低阈值到5%
                detected_texts.append("包含醒目红色文字")
            
            # 检测黄色区域（广告常用）
            lower_yellow = np.array([20, 100, 100])
            upper_yellow = np.array([30, 255, 255])
            yellow_mask = cv2.inRange(hsv, lower_yellow, upper_yellow)
            
            yellow_pixels = cv2.countNonZero(yellow_mask)
            yellow_ratio = yellow_pixels / total_pixels
            
            if yellow_ratio > 0.05:  # 降低阈值到5%
                detected_texts.append("包含醒目黄色文字")
            
            # 检测绿色区域（赌博网站常用绿色）
            lower_green = np.array([40, 50, 50])
            upper_green = np.array([80, 255, 255])
            green_mask = cv2.inRange(hsv, lower_green, upper_green)
            
            green_pixels = cv2.countNonZero(green_mask)
            green_ratio = green_pixels / total_pixels
            
            if green_ratio > 0.1:  # 超过10%的绿色区域
                detected_texts.append("包含大量绿色元素")
                
            # 7. 特殊图像特征检测（赌博相关）
            # 检测圆形区域（老虎机转盘、筹码等）
            circles = cv2.HoughCircles(
                gray,
                cv2.HOUGH_GRADIENT, 
                dp=1,
                minDist=50,
                param1=50,
                param2=30,
                minRadius=20,
                maxRadius=100
            )
            
            if circles is not None and len(circles[0]) >= 3:
                detected_texts.append("检测到多个圆形元素（疑似老虎机/筹码）")
                
            # 8. 组合特征检测（高风险组合）
            has_text_regions = text_regions > 5
            has_bright_colors = red_ratio > 0.05 or yellow_ratio > 0.05 or green_ratio > 0.1
            has_circles = circles is not None and len(circles[0]) >= 3
            
            # 高风险组合判定
            risk_factors = sum([has_text_regions, has_bright_colors, has_circles])
            if risk_factors >= 2:
                detected_texts.append("高风险广告图像特征组合")
            
            logger.debug(f"图像分析检测到 {len(detected_texts)} 个文字特征")
            return detected_texts
            
        except Exception as e:
            logger.debug(f"文字特征提取失败: {e}")
            return []
    
    def _detect_qrcodes_sync(self, image_path: str) -> List[Dict[str, Any]]:
        """同步检测二维码（在线程池中执行）"""
        try:
            # 只使用OpenCV内置的二维码检测器
            return self._detect_with_opencv(image_path)
        except Exception as e:
            logger.debug(f"二维码检测失败: {e}")
            return []
    
    def _detect_with_opencv(self, image_path: str) -> List[Dict[str, Any]]:
        """使用OpenCV内置检测器检测二维码（无需外部依赖）"""
        try:
            # 使用OpenCV加载图片
            image = cv2.imread(image_path)
            if image is None:
                return []
            
            # 转换为灰度
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            
            # 使用OpenCV的QRCodeDetector
            qr_detector = cv2.QRCodeDetector()
            
            # 检测和解码二维码
            retval, decoded_info, points, straight_qrcode = qr_detector.detectAndDecodeMulti(gray)
            
            results = []
            if retval:
                for i, info in enumerate(decoded_info):
                    if info:  # 如果解码成功
                        # 计算边界框
                        if points is not None and i < len(points):
                            pts = points[i].reshape((-1, 1, 2)).astype(int)
                            x, y, w, h = cv2.boundingRect(pts)
                            
                            results.append({
                                'type': 'QRCODE',
                                'data': info,
                                'position': {
                                    'x': int(x),
                                    'y': int(y), 
                                    'width': int(w),
                                    'height': int(h)
                                }
                            })
            
            if results:
                logger.debug(f"OpenCV检测到 {len(results)} 个二维码")
            
            return results
        except Exception as e:
            logger.debug(f"OpenCV二维码检测出错: {e}")
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
            
            # 异步检查缓存
            async with self._cache_lock:
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
            async with self._cache_lock:
                # 检查缓存大小和内存使用
                if len(self.cache) >= self.cache_max_size or self._estimate_cache_memory() > self.cache_memory_limit:
                    # LRU：删除最老的1/3项
                    items = list(self.cache.items())
                    keep_count = int(len(items) * 2/3)
                    self.cache = dict(items[-keep_count:])
                    logger.debug(f"缓存清理：保留 {keep_count} 项")
                
                # 限制单个结果大小，避免大对象占用过多内存
                if self._estimate_object_size(result) < 1024 * 1024:  # 1MB限制
                    self.cache[image_hash] = result
            
            logger.info(f"图片内容提取完成: 文字{len(texts)}条, 二维码{len(qr_codes)}个, 广告分数{ad_score:.2f}")
            
            # 保存OCR样本（异步执行，不影响主流程）
            try:
                asyncio.create_task(self._save_ocr_sample(
                    image_path=image_path,
                    image_hash=image_hash,
                    texts=texts,
                    qr_codes=[qr.get('data', '') for qr in qr_codes if qr.get('data')],
                    ad_score=ad_score,
                    is_ad=has_ad_content,
                    keywords_detected=ad_indicators
                ))
            except Exception as e:
                logger.debug(f"保存OCR样本失败（不影响主流程）: {e}")
            
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
        
        # 1.5 基于检测到的特征文字进行赌博广告检测
        gambling_indicators = [
            "检测到密集文字区域",
            "包含醒目红色文字", 
            "包含醒目黄色文字",
            "包含大量绿色元素",
            "检测到多个圆形元素",
            "高风险广告图像特征组合"
        ]
        
        # 统计赌博相关视觉特征
        visual_gambling_score = 0
        for text in texts:
            if text in gambling_indicators:
                if "高风险" in text:
                    visual_gambling_score += 25
                elif "密集文字" in text or "圆形元素" in text:
                    visual_gambling_score += 15
                elif "醒目" in text or "大量" in text:
                    visual_gambling_score += 10
                    
        ad_score += visual_gambling_score
        if visual_gambling_score > 0:
            ad_indicators.append(f"赌博视觉特征检测: {visual_gambling_score}分")
        
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
    
    async def clear_cache(self):
        """清除缓存"""
        async with self._cache_lock:
            self.cache.clear()
            import gc
            gc.collect()  # 强制垃圾回收
        logger.info("OCR缓存已清除")
    
    def _estimate_cache_memory(self) -> int:
        """估算缓存占用的内存（字节）"""
        import sys
        total_size = 0
        for key, value in self.cache.items():
            total_size += sys.getsizeof(key)
            total_size += self._estimate_object_size(value)
        return total_size
    
    def _estimate_object_size(self, obj) -> int:
        """递归估算对象大小"""
        import sys
        size = sys.getsizeof(obj)
        
        if isinstance(obj, dict):
            size += sum(self._estimate_object_size(k) + self._estimate_object_size(v) 
                       for k, v in obj.items())
        elif isinstance(obj, (list, tuple)):
            size += sum(self._estimate_object_size(item) for item in obj)
        
        return size
    
    async def _save_ocr_sample(
        self,
        image_path: str,
        image_hash: str,
        texts: List[str],
        qr_codes: List[str],
        ad_score: float,
        is_ad: bool,
        keywords_detected: List[str],
        auto_rejected: bool = False,
        rejection_reason: str = "",
        message_id: Optional[int] = None,
        source_channel: Optional[str] = None
    ):
        """保存OCR识别样本"""
        try:
            # 延迟导入，避免循环依赖
            from app.services.ocr_sample_manager import ocr_sample_manager
            
            await ocr_sample_manager.save_sample(
                image_hash=image_hash,
                image_path=image_path,
                ocr_texts=texts,
                qr_codes=qr_codes,
                ad_score=ad_score,
                is_ad=is_ad,
                keywords_detected=keywords_detected,
                auto_rejected=auto_rejected,
                rejection_reason=rejection_reason,
                message_id=message_id,
                source_channel=source_channel
            )
            
        except Exception as e:
            logger.debug(f"保存OCR样本失败: {e}")
    
    def __del__(self):
        """析构函数，清理资源"""
        try:
            if hasattr(self, 'thread_pool'):
                self.thread_pool.shutdown(wait=True)
        except:
            pass


# 全局OCR服务实例
ocr_service = OCRService()