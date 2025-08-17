"""
二维码检测模块
使用OpenCV内置检测器进行二维码识别
"""
import logging
import cv2
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


class QRDetector:
    """二维码检测器类"""
    
    def __init__(self):
        self.qr_detector = cv2.QRCodeDetector()
    
    def detect_qrcodes_sync(self, image_path: str) -> List[Dict[str, Any]]:
        """同步检测二维码"""
        try:
            return self._detect_with_opencv(image_path)
        except Exception as e:
            logger.debug(f"二维码检测失败: {e}")
            return []
    
    def _detect_with_opencv(self, image_path: str) -> List[Dict[str, Any]]:
        """使用OpenCV内置检测器检测二维码"""
        try:
            # 使用OpenCV加载图片
            image = cv2.imread(image_path)
            if image is None:
                return []
            
            # 转换为灰度
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            
            # 检测和解码二维码
            retval, decoded_info, points, straight_qrcode = self.qr_detector.detectAndDecodeMulti(gray)
            
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
    
    def extract_qr_data(self, qr_codes: List[Dict[str, Any]]) -> List[str]:
        """提取二维码数据文本"""
        return [qr.get('data', '') for qr in qr_codes if qr.get('data')]
    
    def analyze_qr_content(self, qr_codes: List[Dict[str, Any]]) -> Dict[str, Any]:
        """分析二维码内容特征"""
        if not qr_codes:
            return {
                'has_urls': False,
                'has_telegram_links': False,
                'has_external_links': False,
                'url_count': 0,
                'telegram_count': 0,
                'external_count': 0
            }
        
        import re
        
        urls = []
        telegram_links = []
        external_links = []
        
        for qr in qr_codes:
            data = qr.get('data', '')
            
            # 检查是否为URL
            if re.match(r'https?://', data, re.IGNORECASE):
                urls.append(data)
                
                # 检查是否为Telegram链接
                if re.search(r'(?:t\.me|telegram\.me|telegra\.ph)', data, re.IGNORECASE):
                    telegram_links.append(data)
                else:
                    external_links.append(data)
        
        return {
            'has_urls': len(urls) > 0,
            'has_telegram_links': len(telegram_links) > 0,
            'has_external_links': len(external_links) > 0,
            'url_count': len(urls),
            'telegram_count': len(telegram_links),
            'external_count': len(external_links),
            'urls': urls[:3],  # 最多返回3个URL样本
            'telegram_links': telegram_links[:3],
            'external_links': external_links[:3]
        }