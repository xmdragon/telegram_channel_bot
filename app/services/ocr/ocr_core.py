"""
OCR引擎核心模块
负责EasyOCR初始化和基础文字提取功能
"""
import logging
import os
from typing import List, Optional
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)


class OCRCore:
    """OCR引擎核心类"""
    
    def __init__(self):
        self.ocr_reader = None
        self.initialized = False
        self.thread_pool = ThreadPoolExecutor(max_workers=2)
        
        # 初始化OCR引擎
        self._initialize_easyocr()
    
    def _initialize_easyocr(self):
        """初始化EasyOCR引擎"""
        try:
            import easyocr
            import warnings
            import logging as torch_logging
            
            if self.ocr_reader is None:
                logger.info("正在初始化EasyOCR（支持中英文识别）...")
                
                # 多重设置抑制PyTorch警告
                os.environ['PYTORCH_ENABLE_MPS_FALLBACK'] = '1'
                os.environ['TORCH_LOGS'] = 'error'
                
                # 抑制torch的dataloader警告
                torch_logging.getLogger('torch.utils.data.dataloader').setLevel(torch_logging.ERROR)
                
                # 临时抑制特定警告
                with warnings.catch_warnings():
                    warnings.filterwarnings("ignore", category=UserWarning)
                    warnings.filterwarnings("ignore", message=".*pin_memory.*")
                    warnings.filterwarnings("ignore", module="torch")
                    warnings.simplefilter("ignore")
                    
                    # 创建中英文OCR识别器，gpu=False确保兼容性
                    self.ocr_reader = easyocr.Reader(['ch_sim', 'en'], gpu=False)
                    
                logger.info("EasyOCR初始化成功")
            self.initialized = True
        except Exception as e:
            logger.error(f"EasyOCR初始化失败: {e}")
            self.initialized = False
    
    def extract_text_sync(self, image_path: str) -> List[str]:
        """同步提取图片文字"""
        if not self.initialized or self.ocr_reader is None:
            logger.warning("OCR未初始化或EasyOCR不可用")
            return []
        
        try:
            # 直接识别策略
            texts = self._extract_direct(image_path)
            
            # 如果直接识别失败，使用增强策略
            if not texts:
                texts = self._extract_with_enhancement(image_path)
            
            # 清理和去重
            texts = self._clean_texts(texts)
            
            logger.debug(f"EasyOCR识别到 {len(texts)} 个文字: {texts}")
            return texts
            
        except Exception as e:
            logger.error(f"EasyOCR文字识别失败: {e}")
            return []
    
    def _extract_direct(self, image_path: str) -> List[str]:
        """直接文字识别"""
        import warnings
        texts = []
        
        # 在实际识别时抑制PyTorch警告
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=UserWarning)
            warnings.filterwarnings("ignore", module="torch")
            warnings.simplefilter("ignore")
            result = self.ocr_reader.readtext(image_path)
        
        for bbox, text, confidence in result:
            if confidence > 0.3 and text.strip():
                texts.append(text.strip())
            elif confidence > 0.05 and len(text.strip()) > 2:
                # 对于较长的文字，允许更低的置信度
                texts.append(text.strip())
        
        return texts
    
    def _extract_with_enhancement(self, image_path: str) -> List[str]:
        """使用图像增强的文字识别"""
        try:
            import cv2
            import numpy as np
            
            img = cv2.imread(image_path)
            if img is None:
                return []
            
            texts = []
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
            # 多种预处理策略
            strategies = [
                ("enhanced", lambda x: cv2.convertScaleAbs(x, alpha=1.8, beta=40)),
                ("clahe", lambda x: cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8)).apply(x)),
                ("sharpened", lambda x: cv2.addWeighted(x, 1.5, cv2.GaussianBlur(x, (3, 3), 0), -0.5, 0)),
                ("morph", lambda x: cv2.morphologyEx(x, cv2.MORPH_CLOSE, np.ones((2,2), np.uint8))),
                ("bilateral", lambda x: cv2.bilateralFilter(x, 9, 75, 75))
            ]
            
            for strategy_name, processor in strategies:
                processed_img = processor(gray)
                temp_path = image_path.replace('.jpg', f'_temp_{strategy_name}.jpg')
                cv2.imwrite(temp_path, processed_img)
                
                try:
                    import warnings
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore")
                        result = self.ocr_reader.readtext(temp_path)
                    for bbox, text, confidence in result:
                        if confidence > 0.1 and text.strip() and text.strip() not in texts:
                            texts.append(text.strip())
                            logger.debug(f"{strategy_name}策略识别到: {text} (置信度: {confidence:.3f})")
                except Exception as e:
                    logger.debug(f"{strategy_name}策略OCR失败: {e}")
                
                # 清理临时文件
                try:
                    os.remove(temp_path)
                except:
                    pass
            
            # 极限策略：强对比度+二值化
            if not texts:
                _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                temp_path = image_path.replace('.jpg', '_temp_extreme.jpg')
                cv2.imwrite(temp_path, binary)
                
                try:
                    import warnings
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore")
                        result = self.ocr_reader.readtext(temp_path)
                    for bbox, text, confidence in result:
                        if confidence > 0.05 and text.strip():
                            texts.append(text.strip())
                            logger.debug(f"极限策略识别到: {text} (置信度: {confidence:.3f})")
                except Exception as e:
                    logger.debug(f"极限策略OCR失败: {e}")
                
                try:
                    os.remove(temp_path)
                except:
                    pass
            
            return texts
            
        except Exception as e:
            logger.debug(f"增强图像预处理失败: {e}")
            return []
    
    def _clean_texts(self, texts: List[str]) -> List[str]:
        """清理和去重文字"""
        # 去重并保持顺序
        cleaned = list(dict.fromkeys(texts))
        # 过滤空字符串
        cleaned = [t for t in cleaned if len(t.strip()) > 0]
        return cleaned
    
    def is_available(self) -> bool:
        """检查OCR是否可用"""
        return self.initialized and self.ocr_reader is not None
    
    def __del__(self):
        """析构函数，清理资源"""
        try:
            if hasattr(self, 'thread_pool'):
                self.thread_pool.shutdown(wait=True)
        except:
            pass