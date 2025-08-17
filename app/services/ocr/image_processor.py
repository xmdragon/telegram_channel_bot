"""
图像预处理和特征检测模块
提供图像增强、特征分析和广告视觉特征检测
"""
import logging
import cv2
import numpy as np
from typing import List, Tuple
from PIL import Image

logger = logging.getLogger(__name__)


class ImageProcessor:
    """图像处理器类"""
    
    def extract_text_features_fallback(self, image_path: str) -> List[str]:
        """回退方案：使用图像特征分析"""
        try:
            # 加载图片
            pil_image = Image.open(image_path)
            if pil_image.mode != 'RGB':
                pil_image = pil_image.convert('RGB')
            
            # 使用OpenCV进行图像分析
            image = cv2.imread(image_path)
            if image is None:
                return []
            
            # 检测广告特征
            detected_texts = []
            
            # 1. 检测文字区域特征
            text_regions = self._detect_text_regions(image)
            if text_regions > 5:
                detected_texts.append("检测到密集文字区域")
            
            # 2. 颜色特征分析
            color_features = self._analyze_color_features(image)
            detected_texts.extend(color_features)
            
            # 3. 几何特征检测
            geometric_features = self._detect_geometric_features(image)
            detected_texts.extend(geometric_features)
            
            # 4. 风险组合判定
            risk_score = self._calculate_risk_score(text_regions, color_features, geometric_features)
            if risk_score >= 2:
                detected_texts.append("高风险广告图像特征组合")
            
            logger.debug(f"图像分析检测到 {len(detected_texts)} 个文字特征")
            return detected_texts
            
        except Exception as e:
            logger.debug(f"文字特征提取失败: {e}")
            return []
    
    def _detect_text_regions(self, image: np.ndarray) -> int:
        """检测文字区域数量"""
        try:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            
            # 边缘检测找文字轮廓
            edges = cv2.Canny(gray, 50, 150)
            
            # 形态学操作连接文字区域
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
            closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)
            
            # 查找轮廓
            contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            # 分析轮廓特征判断是否为文字区域
            text_regions = 0
            for contour in contours:
                area = cv2.contourArea(contour)
                if area > 100 and area < 10000:  # 文字区域大小范围
                    x, y, w, h = cv2.boundingRect(contour)
                    aspect_ratio = w / float(h)
                    # 文字区域通常有特定的宽高比
                    if 0.5 < aspect_ratio < 10:
                        text_regions += 1
            
            return text_regions
            
        except Exception as e:
            logger.debug(f"文字区域检测失败: {e}")
            return 0
    
    def _analyze_color_features(self, image: np.ndarray) -> List[str]:
        """分析颜色特征"""
        features = []
        try:
            hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
            total_pixels = image.shape[0] * image.shape[1]
            
            # 检测红色区域（广告常用）
            red_ratio = self._detect_color_ratio(hsv, [
                (np.array([0, 50, 50]), np.array([10, 255, 255])),
                (np.array([170, 50, 50]), np.array([180, 255, 255]))
            ])
            
            if red_ratio > 0.05:
                features.append("包含醒目红色文字")
            
            # 检测黄色区域
            yellow_ratio = self._detect_color_ratio(hsv, [
                (np.array([20, 100, 100]), np.array([30, 255, 255]))
            ])
            
            if yellow_ratio > 0.05:
                features.append("包含醒目黄色文字")
            
            # 检测绿色区域（赌博网站常用）
            green_ratio = self._detect_color_ratio(hsv, [
                (np.array([40, 50, 50]), np.array([80, 255, 255]))
            ])
            
            if green_ratio > 0.1:
                features.append("包含大量绿色元素")
            
            return features
            
        except Exception as e:
            logger.debug(f"颜色特征分析失败: {e}")
            return []
    
    def _detect_color_ratio(self, hsv_image: np.ndarray, color_ranges: List[Tuple[np.ndarray, np.ndarray]]) -> float:
        """检测指定颜色范围的像素比例"""
        total_pixels = hsv_image.shape[0] * hsv_image.shape[1]
        total_mask = np.zeros(hsv_image.shape[:2], dtype=np.uint8)
        
        for lower, upper in color_ranges:
            mask = cv2.inRange(hsv_image, lower, upper)
            total_mask = cv2.bitwise_or(total_mask, mask)
        
        color_pixels = cv2.countNonZero(total_mask)
        return color_pixels / total_pixels
    
    def _detect_geometric_features(self, image: np.ndarray) -> List[str]:
        """检测几何特征"""
        features = []
        try:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            
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
                features.append("检测到多个圆形元素（疑似老虎机/筹码）")
            
            return features
            
        except Exception as e:
            logger.debug(f"几何特征检测失败: {e}")
            return []
    
    def _calculate_risk_score(self, text_regions: int, color_features: List[str], 
                            geometric_features: List[str]) -> int:
        """计算风险分数"""
        score = 0
        
        # 文字区域权重
        if text_regions > 5:
            score += 1
        
        # 颜色特征权重
        if color_features:
            score += 1
        
        # 几何特征权重
        if geometric_features:
            score += 1
        
        return score
    
    def enhance_image_for_ocr(self, image_path: str) -> List[str]:
        """为OCR优化图像（返回临时文件路径）"""
        try:
            import os
            
            img = cv2.imread(image_path)
            if img is None:
                return []
            
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            temp_paths = []
            
            # 生成多种增强版本
            enhancements = [
                ("contrast", cv2.convertScaleAbs(gray, alpha=1.5, beta=30)),
                ("blur_sharp", self._sharpen_image(gray)),
                ("denoise", cv2.bilateralFilter(gray, 9, 75, 75))
            ]
            
            for name, enhanced_img in enhancements:
                temp_path = image_path.replace('.jpg', f'_enhanced_{name}.jpg')
                cv2.imwrite(temp_path, enhanced_img)
                temp_paths.append(temp_path)
            
            return temp_paths
            
        except Exception as e:
            logger.debug(f"图像增强失败: {e}")
            return []
    
    def _sharpen_image(self, gray_image: np.ndarray) -> np.ndarray:
        """锐化图像"""
        blurred = cv2.GaussianBlur(gray_image, (3, 3), 0)
        return cv2.addWeighted(gray_image, 1.5, blurred, -0.5, 0)
    
    def cleanup_temp_files(self, file_paths: List[str]):
        """清理临时文件"""
        import os
        for path in file_paths:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception as e:
                logger.debug(f"清理临时文件失败 {path}: {e}")