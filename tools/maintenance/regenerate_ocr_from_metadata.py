#!/usr/bin/env python3
"""
根据media_metadata.json中的90个文件重新生成OCR样本数据
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

def generate_mock_ocr_text(file_path: Path, file_info: dict) -> list:
    """根据文件名和元数据生成模拟的OCR文本"""
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
            f"创建时间: {file_info.get('saved_at', datetime.now().strftime('%Y-%m-%d %H:%M'))}"
        ]

def generate_ocr_from_metadata():
    """基于media_metadata.json重新生成OCR样本数据"""
    
    # 读取媒体元数据
    media_metadata_file = PathConfig.AD_MEDIA_METADATA_FILE
    if not media_metadata_file.exists():
        print(f"❌ 媒体元数据文件不存在: {media_metadata_file}")
        return False
    
    print(f"📖 读取媒体元数据: {media_metadata_file}")
    metadata = SafeFileOperation.read_json_safe(media_metadata_file)
    if not metadata or "media_files" not in metadata:
        print("❌ 媒体元数据为空或格式错误")
        return False
    
    media_files = metadata["media_files"]
    print(f"📊 找到 {len(media_files)} 个媒体文件记录")
    
    # 生成OCR样本
    samples = []
    media_dir = PathConfig.AD_MEDIA_DIR
    
    for file_hash, file_info in media_files.items():
        # 使用元数据中的hash作为真实hash
        file_path = media_dir / file_info["path"]
        
        # 检查文件是否存在
        if not file_path.exists():
            print(f"⚠️  跳过不存在的文件: {file_path}")
            continue
        
        # 生成样本ID
        sample_id = file_hash[:12]
        
        # 生成OCR文本
        ocr_texts = generate_mock_ocr_text(file_path, file_info)
        
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
            "image_hash": file_hash,  # 使用metadata中的完整hash
            "image_path": file_info["path"],  # 使用相对路径
            "ocr_texts": ocr_texts,
            "qr_codes": [],
            "ad_score": ad_score,
            "is_ad": is_ad,
            "keywords_detected": keywords_detected,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "auto_rejected": False,
            "rejection_reason": "",
            "message_id": file_info.get("message_ids", [None])[0] if file_info.get("message_ids") else None,
            "source_channel": None
        }
        
        samples.append(sample)
        print(f"✅ 生成样本: {file_path.name} ({'广告' if is_ad else '正常'})")
    
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
        "version": "2.1",
        "source": "media_metadata.json"
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
    print(f"\n📊 基于media_metadata.json重新生成OCR样本完成:")
    print(f"   ✅ 总样本数: {ocr_data['statistics']['total_samples']}")
    print(f"   🚫 广告样本: {ocr_data['statistics']['ad_samples']}")
    print(f"   ✅ 正常样本: {ocr_data['statistics']['non_ad_samples']}")
    print(f"   ⚠️  高风险样本: {ocr_data['statistics']['high_score_samples']}")
    print(f"   📁 基于元数据文件: {len(media_files)} 条记录")
    
    return True

if __name__ == "__main__":
    print("🔧 基于media_metadata.json重新生成OCR样本数据...")
    success = generate_ocr_from_metadata()
    if success:
        print("✅ OCR样本数据重新生成完成")
    else:
        print("❌ OCR样本数据重新生成失败")
        sys.exit(1)