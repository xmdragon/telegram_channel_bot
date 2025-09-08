"""
内容检测器模块

负责判断内容性质，与filters（内容清理）并列：
- filters/ = 内容清理（去除推广内容、格式化处理）
- detectors/ = 内容检测（判断是否为广告等）

核心设计理念：
- 基于ONNX语义理解的统一检测
- 消除正则表达式等特殊情况
- 支持双轨检测（原始内容+过滤内容）

Author: Claude
Created: 2025-09-08
"""

from .semantic_ad_detector import SemanticAdDetector
from .detector_layer import DetectorLayer, DetectorLayerConfig

__all__ = [
    'SemanticAdDetector',
    'DetectorLayer', 
    'DetectorLayerConfig'
]

# 版本信息
__version__ = '1.0.0'
__author__ = 'Claude'
__description__ = '内容检测器模块 - 基于ONNX语义理解的广告检测'