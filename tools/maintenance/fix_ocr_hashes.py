#!/usr/bin/env python3
"""
修正OCR数据中的hash值，使其与媒体文件的实际hash匹配
"""
import json
import hashlib
from pathlib import Path
import sys
import os
import time

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

def fix_ocr_hashes():
    """修正OCR数据中的hash值"""
    
    # 读取OCR样本数据
    ocr_samples_file = PathConfig.OCR_SAMPLES_FILE
    if not ocr_samples_file.exists():
        print(f"❌ OCR样本文件不存在: {ocr_samples_file}")
        return False
    
    print(f"📖 读取OCR样本数据: {ocr_samples_file}")
    data = SafeFileOperation.read_json_safe(ocr_samples_file)
    if not data or "samples" not in data:
        print("❌ OCR数据为空或格式错误")
        return False
    
    samples = data["samples"]
    print(f"📊 找到 {len(samples)} 个OCR样本")
    
    # 统计信息
    fixed_count = 0
    missing_files = 0
    unchanged_count = 0
    
    # 处理每个样本
    for i, sample in enumerate(samples):
        image_path = sample.get("image_path", "")
        old_hash = sample.get("image_hash", "")
        
        if not image_path:
            print(f"⚠️  样本 {i+1}: 缺少image_path")
            continue
        
        # 构建完整的文件路径
        # 如果路径是相对路径，尝试不同的基础目录
        file_path = None
        possible_paths = [
            Path(image_path),  # 绝对路径
            Path.cwd() / image_path,  # 相对于当前目录
            PathConfig.TEMP_MEDIA_DIR / Path(image_path).name,  # temp_media目录
            PathConfig.AD_MEDIA_DIR / Path(image_path).name,  # ad训练数据目录
        ]
        
        # 如果路径包含data/training/ad，尝试对应的路径
        if "data/training/ad" in image_path:
            # 提取文件名，在ad目录中查找
            filename = Path(image_path).name
            for subdir in ["images", "videos"]:
                for year_month in ["2025-08", "2025-07", "2025-06"]:  # 常见的年月目录
                    possible_path = PathConfig.AD_TRAINING_DIR / subdir / year_month / filename
                    possible_paths.append(possible_path)
        
        # 尝试找到文件
        for path in possible_paths:
            if path.exists() and path.is_file():
                file_path = path
                break
        
        if not file_path:
            print(f"❌ 样本 {i+1}: 文件不存在 - {image_path}")
            missing_files += 1
            continue
        
        # 计算实际的文件hash
        actual_hash = calculate_file_hash(file_path)
        if not actual_hash:
            print(f"❌ 样本 {i+1}: 无法计算hash - {file_path}")
            continue
        
        # 检查是否需要更新
        if actual_hash == old_hash:
            unchanged_count += 1
            continue
        
        # 更新hash
        sample["image_hash"] = actual_hash
        print(f"✅ 样本 {i+1}: 更新hash")
        print(f"   文件: {file_path.name}")
        print(f"   旧hash: {old_hash}")
        print(f"   新hash: {actual_hash}")
        fixed_count += 1
    
    # 保存更新后的数据
    if fixed_count > 0:
        # 创建备份
        backup_file = ocr_samples_file.parent / f"ocr_samples_backup_{int(time.time())}.json"
        try:
            backup_data = json.dumps(data, indent=2, ensure_ascii=False)
            with open(backup_file, 'w', encoding='utf-8') as f:
                f.write(backup_data)
            print(f"💾 备份原始数据: {backup_file}")
        except Exception as e:
            print(f"⚠️  创建备份失败: {e}")
        
        # 保存修正后的数据
        if SafeFileOperation.write_json_safe(ocr_samples_file, data):
            print(f"💾 保存修正后的OCR数据")
        else:
            print(f"❌ 保存OCR数据失败")
            return False
    
    # 输出统计信息
    print(f"\n📊 修正完成:")
    print(f"   ✅ 修正了 {fixed_count} 个hash")
    print(f"   ⚠️  {missing_files} 个文件缺失")
    print(f"   📝 {unchanged_count} 个hash无需更改")
    print(f"   📊 总计 {len(samples)} 个样本")
    
    return True

if __name__ == "__main__":
    print("🔧 开始修正OCR数据中的hash值...")
    success = fix_ocr_hashes()
    if success:
        print("✅ OCR hash修正完成")
    else:
        print("❌ OCR hash修正失败")
        sys.exit(1)