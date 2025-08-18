#!/usr/bin/env python3
"""
根据实际的媒体文件重新生成OCR样本数据
"""
import json
import hashlib
from pathlib import Path
import sys
import os
import time
from datetime import datetime

# 添加项目根目录到path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.core.path_config import PathConfig
from app.utils.safe_file_ops import SafeFileOperation

def calculate_file_hash(file_path: Path) -> str:
    """计算文件的SHA256哈希值"""
    if not file_path.exists():
        return ""
    
    hash_sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_sha256.update(chunk)
    return hash_sha256.hexdigest()

def scan_media_files():
    """扫描媒体文件目录"""
    media_files = []
    
    # 扫描广告训练数据目录
    ad_media_dir = PathConfig.AD_MEDIA_DIR
    if ad_media_dir.exists():
        print(f"📁 扫描广告媒体目录: {ad_media_dir}")
        for file_path in ad_media_dir.rglob("*"):
            if file_path.is_file() and file_path.suffix.lower() in ['.jpg', '.jpeg', '.png', '.webp', '.mp4', '.avi', '.mov']:
                media_files.append(file_path)
    
    # 扫描临时媒体目录
    temp_media_dir = PathConfig.TEMP_MEDIA_DIR
    if temp_media_dir.exists():
        print(f"📁 扫描临时媒体目录: {temp_media_dir}")
        for file_path in temp_media_dir.rglob("*"):
            if file_path.is_file() and file_path.suffix.lower() in ['.jpg', '.jpeg', '.png', '.webp', '.mp4', '.avi', '.mov']:
                media_files.append(file_path)
    
    return media_files

def generate_mock_ocr_text(file_path: Path) -> list:
    """根据文件名和路径生成模拟的OCR文本"""
    filename = file_path.name.lower()
    
    # 根据文件名特征生成不同的OCR内容
    if "casino" in filename or "gambling" in filename or "bet" in filename:
        return [
            "🎰 VIP赌场",
            "💰 百家乐 德州扑克",
            "🃏 真人荷官在线",
            "📱 立即注册送888元"
        ]
    elif "ad" in str(file_path) or "advertisement" in filename:
        return [
            "🔥 限时优惠",
            "💎 点击领取红包",
            "📢 推广链接",
            "🎁 新用户专享"
        ]
    elif "game" in filename:
        return [
            "🎮 热门游戏",
            "⭐ 五星好评",
            "🏆 排行榜第一",
            "🆓 免费下载"
        ]
    elif "finance" in filename or "money" in filename:
        return [
            "💰 投资理财",
            "📈 稳定收益",
            "🏦 银行合作",
            "💳 安全保障"
        ]
    else:
        # 默认的通用OCR文本
        return [
            "检测到文字内容",
            f"文件名: {filename}",
            f"创建时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        ]

def generate_ocr_samples():
    """生成新的OCR样本数据"""
    
    # 扫描媒体文件
    media_files = scan_media_files()
    print(f"📊 找到 {len(media_files)} 个媒体文件")
    
    if not media_files:
        print("❌ 没有找到媒体文件")
        return False
    
    # 生成OCR样本
    samples = []
    
    for i, file_path in enumerate(media_files):
        # 计算文件hash
        file_hash = calculate_file_hash(file_path)
        if not file_hash:
            print(f"⚠️  跳过文件（无法计算hash）: {file_path}")
            continue
        
        # 生成样本ID
        sample_id = file_hash[:12]
        
        # 生成相对路径
        try:
            # 使用当前工作目录作为根目录
            project_root = Path.cwd()
            if PathConfig.AD_MEDIA_DIR in file_path.parents:
                relative_path = file_path.relative_to(project_root)
            elif PathConfig.TEMP_MEDIA_DIR in file_path.parents:
                relative_path = file_path.relative_to(project_root)
            else:
                relative_path = file_path
        except ValueError:
            relative_path = file_path
        
        # 生成OCR文本
        ocr_texts = generate_mock_ocr_text(file_path)
        
        # 判断是否为广告
        is_ad = "ad" in str(file_path).lower() or any(
            keyword in " ".join(ocr_texts).lower() 
            for keyword in ["赌场", "投资", "理财", "红包", "优惠", "casino", "bet", "gambling"]
        )
        
        # 计算广告分数
        ad_score = 0.0
        if is_ad:
            ad_score = 60.0 if "赌" in " ".join(ocr_texts) else 30.0
        
        # 生成关键词
        keywords_detected = []
        if is_ad:
            if "赌" in " ".join(ocr_texts) or "casino" in " ".join(ocr_texts).lower():
                keywords_detected.append("赌博相关内容检测")
            if "投资" in " ".join(ocr_texts) or "理财" in " ".join(ocr_texts):
                keywords_detected.append("金融投资广告")
            if "红包" in " ".join(ocr_texts) or "优惠" in " ".join(ocr_texts):
                keywords_detected.append("营销推广内容")
        
        # 创建样本
        sample = {
            "id": sample_id,
            "image_hash": file_hash,
            "image_path": str(relative_path),
            "ocr_texts": ocr_texts,
            "qr_codes": [],
            "ad_score": ad_score,
            "is_ad": is_ad,
            "keywords_detected": keywords_detected,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "auto_rejected": False,
            "rejection_reason": "",
            "message_id": None,
            "source_channel": None
        }
        
        samples.append(sample)
        print(f"✅ 生成样本 {i+1}/{len(media_files)}: {file_path.name} ({'广告' if is_ad else '正常'})")
    
    # 生成完整的OCR数据结构
    ocr_data = {
        "samples": samples,
        "learned_patterns": {
            "high_risk_keywords": ["赌场", "投资理财", "红包", "优惠"],
            "common_ad_phrases": ["立即注册", "点击领取", "限时优惠", "新用户专享"],
            "qr_code_patterns": []
        },
        "statistics": {
            "total_samples": len(samples),
            "ad_samples": len([s for s in samples if s["is_ad"]]),
            "non_ad_samples": len([s for s in samples if not s["is_ad"]]),
            "auto_rejected_samples": 0,
            "high_score_samples": len([s for s in samples if s["ad_score"] >= 50.0]),
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        },
        "version": "2.0"
    }
    
    # 备份原始文件
    ocr_samples_file = PathConfig.OCR_SAMPLES_FILE
    if ocr_samples_file.exists():
        backup_file = ocr_samples_file.parent / f"ocr_samples_backup_{int(time.time())}.json"
        try:
            import shutil
            shutil.copy2(ocr_samples_file, backup_file)
            print(f"💾 备份原始文件: {backup_file}")
        except Exception as e:
            print(f"⚠️  创建备份失败: {e}")
    
    # 保存新的OCR数据
    if SafeFileOperation.write_json_safe(ocr_samples_file, ocr_data):
        print(f"💾 保存新的OCR样本数据: {ocr_samples_file}")
    else:
        print(f"❌ 保存OCR数据失败")
        return False
    
    # 输出统计信息
    print(f"\n📊 OCR样本生成完成:")
    print(f"   ✅ 总样本数: {ocr_data['statistics']['total_samples']}")
    print(f"   🚫 广告样本: {ocr_data['statistics']['ad_samples']}")
    print(f"   ✅ 正常样本: {ocr_data['statistics']['non_ad_samples']}")
    print(f"   ⚠️  高风险样本: {ocr_data['statistics']['high_score_samples']}")
    
    return True

if __name__ == "__main__":
    print("🔧 开始重新生成OCR样本数据...")
    success = generate_ocr_samples()
    if success:
        print("✅ OCR样本数据生成完成")
    else:
        print("❌ OCR样本数据生成失败")
        sys.exit(1)