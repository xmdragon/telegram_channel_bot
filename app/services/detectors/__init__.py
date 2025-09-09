"""
内容检测器模块

负责判断内容性质，与filters（内容清理）并列：
- filters/ = 内容清理（去除推广内容、格式化处理）
- detectors/ = 内容检测（判断是否为广告等）

核心设计理念：
- 基于关键词的简洁高效检测
- 消除ONNX复杂性，回归简单规则
- 支持双轨检测（原始内容+过滤内容）

Author: Claude
Created: 2025-09-08
Updated: 2025-09-09 (移除ONNX，改为关键词检测)
"""

from .keyword_ad_detector import KeywordAdDetector
from .detector_layer import DetectorLayer, DetectorLayerConfig

__all__ = [
    'KeywordAdDetector',
    'DetectorLayer', 
    'DetectorLayerConfig'
]

# 版本信息
__version__ = '2.0.0'
__author__ = 'Claude'
__description__ = '内容检测器模块 - 基于关键词的广告检测'