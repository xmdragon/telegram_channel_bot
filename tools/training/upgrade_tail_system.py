#!/usr/bin/env python3
"""
尾部过滤系统升级脚本
将现有的tail_filter_samples.json升级为智能化结构
"""
import json
import sys
import os
from datetime import datetime
from pathlib import Path
import logging
import hashlib
import shutil

# 添加项目根目录到sys.path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from app.core.path_config import PathConfig
from app.services.tail_feature_extractor import TailFeatureExtractor
from app.services.tail_vector_manager import TailVectorManager
from app.utils.safe_file_ops import SafeFileOperation

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def backup_original_file():
    """备份原始文件"""
    try:
        original_file = PathConfig.TAIL_FILTER_SAMPLES_FILE
        if not original_file.exists():
            logger.warning(f"⚠️ 原始文件不存在: {original_file}")
            return False
        
        # 创建备份 - 统一存放到data/backups目录
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        PathConfig.BACKUP_DIR.mkdir(exist_ok=True)  # 确保备份目录存在
        backup_file = PathConfig.BACKUP_DIR / f"{original_file.stem}_backup_{timestamp}.json"
        
        shutil.copy2(original_file, backup_file)
        logger.info(f"✅ 已备份原始文件到: {backup_file}")
        return True
        
    except Exception as e:
        logger.error(f"❌ 备份文件失败: {e}")
        return False

def load_old_samples():
    """加载旧格式的样本数据"""
    try:
        samples_file = PathConfig.TAIL_FILTER_SAMPLES_FILE
        if not samples_file.exists():
            logger.warning(f"⚠️ 样本文件不存在: {samples_file}")
            return []
        
        data = SafeFileOperation.read_json_safe(samples_file)
        if not data or 'samples' not in data:
            logger.warning("⚠️ 样本文件格式异常")
            return []
        
        old_samples = data['samples']
        logger.info(f"📥 加载了 {len(old_samples)} 个旧格式样本")
        return old_samples
        
    except Exception as e:
        logger.error(f"❌ 加载旧样本失败: {e}")
        return []

def upgrade_sample_structure(old_sample, feature_extractor, vector_manager):
    """升级单个样本到新结构"""
    try:
        # 基础信息
        sample_id = old_sample.get('id')
        tail_part = old_sample.get('tail_part', '')
        created_at = old_sample.get('created_at', datetime.now().isoformat())
        updated_at = old_sample.get('updated_at', created_at)
        
        if not tail_part:
            logger.warning(f"⚠️ 样本 {sample_id} 内容为空，跳过")
            return None
        
        # 提取特征
        features = feature_extractor.extract_features(tail_part)
        scores = feature_extractor.calculate_scores(tail_part, features)
        
        # 向量化
        vector_index = vector_manager.add_vector(tail_part, sample_id)
        
        # 生成新结构
        new_sample = {
            "id": sample_id,
            "tail_part": tail_part,
            
            # AI分析结果
            "characteristics": {
                "promotion_score": scores['promotion_score'],
                "commercial_score": scores['commercial_score'],
                "relevance_score": scores['relevance_score']
            },
            
            # 自动提取的特征
            "auto_features": {
                "has_telegram_link": features['has_telegram_link'],
                "has_contact": features['has_contact'],
                "action_words": features['action_words'],
                "business_words": features['business_words'],
                "link_count": features['link_count'],
                "emoji_count": features['emoji_count'],
                "text_length": features['text_length'],
                "word_count": features['word_count']
            },
            
            # 向量信息
            "vector_index": vector_index,
            
            # 时间信息
            "created_at": created_at,
            "updated_at": updated_at,
            "migrated_at": datetime.now().isoformat()
        }
        
        logger.debug(f"✅ 升级样本 {sample_id} - 推广得分: {scores['promotion_score']:.2f}")
        return new_sample
        
    except Exception as e:
        logger.error(f"❌ 升级样本 {old_sample.get('id', 'unknown')} 失败: {e}")
        return None

def save_new_structure(new_samples, vector_manager):
    """保存新结构的数据"""
    try:
        # 确保目录存在
        PathConfig.ensure_directories()
        
        # 构建新的数据结构
        new_data = {
            "version": "2.0",
            "metadata": {
                "total_samples": len(new_samples),
                "last_vectorized": datetime.now().isoformat(),
                "model_version": "paraphrase-multilingual-MiniLM-L12-v2",
                "migrated_from": "v1.0"
            },
            "samples": new_samples,
            "updated_at": datetime.now().isoformat()
        }
        
        # 保存JSON数据
        samples_file = PathConfig.TAIL_FILTER_SAMPLES_FILE
        SafeFileOperation.write_json_safe(samples_file, new_data)
        logger.info(f"💾 已保存 {len(new_samples)} 个样本到: {samples_file}")
        
        # 保存向量数据
        vector_manager.save()
        logger.info("💾 已保存向量数据")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ 保存新结构失败: {e}")
        return False

def validate_upgrade(new_samples):
    """验证升级结果"""
    try:
        issues = []
        
        for i, sample in enumerate(new_samples):
            # 检查必需字段
            required_fields = ['id', 'tail_part', 'characteristics', 'auto_features', 'vector_index']
            for field in required_fields:
                if field not in sample:
                    issues.append(f"样本 {i}: 缺少字段 {field}")
            
            # 检查特征的合理性
            if 'characteristics' in sample:
                char = sample['characteristics']
                for score_key in ['promotion_score', 'commercial_score', 'relevance_score']:
                    if score_key in char:
                        score = char[score_key]
                        if not (0 <= score <= 1):
                            issues.append(f"样本 {sample.get('id')}: {score_key} 超出范围 [0,1]: {score}")
        
        if issues:
            logger.warning(f"⚠️ 发现 {len(issues)} 个验证问题:")
            for issue in issues[:10]:  # 只显示前10个
                logger.warning(f"  - {issue}")
            if len(issues) > 10:
                logger.warning(f"  - ... 还有 {len(issues)-10} 个问题")
        else:
            logger.info("✅ 数据验证通过")
        
        return len(issues) == 0
        
    except Exception as e:
        logger.error(f"❌ 验证失败: {e}")
        return False

def print_upgrade_summary(old_samples, new_samples):
    """打印升级摘要"""
    print("\n" + "="*60)
    print("🚀 尾部过滤系统升级完成!")
    print("="*60)
    print(f"原始样本数量: {len(old_samples)}")
    print(f"升级样本数量: {len(new_samples)}")
    print(f"成功率: {len(new_samples)/len(old_samples)*100:.1f}%")
    
    if new_samples:
        # 统计特征
        total_promotion = sum(s['characteristics']['promotion_score'] for s in new_samples)
        avg_promotion = total_promotion / len(new_samples)
        
        high_promotion = len([s for s in new_samples if s['characteristics']['promotion_score'] > 0.7])
        has_links = len([s for s in new_samples if s['auto_features']['has_telegram_link']])
        
        print(f"平均推广得分: {avg_promotion:.2f}")
        print(f"高推广得分样本: {high_promotion} ({high_promotion/len(new_samples)*100:.1f}%)")
        print(f"包含链接的样本: {has_links} ({has_links/len(new_samples)*100:.1f}%)")
    
    print("\n新功能:")
    print("✅ AI语义分析")
    print("✅ 向量相似度匹配")
    print("✅ 自动特征提取")
    print("✅ 智能评分系统")
    print("="*60)

def main():
    """主升级流程"""
    logger.info("🚀 开始尾部过滤系统升级...")
    
    try:
        # 1. 备份原始文件
        if not backup_original_file():
            logger.error("备份失败，升级中断")
            return False
        
        # 2. 加载旧数据
        old_samples = load_old_samples()
        if not old_samples:
            logger.error("没有找到可升级的样本")
            return False
        
        # 3. 初始化AI组件
        logger.info("🤖 初始化AI组件...")
        feature_extractor = TailFeatureExtractor()
        vector_manager = TailVectorManager()
        
        if not feature_extractor.model:
            logger.error("❌ 特征提取器初始化失败")
            return False
        
        if not vector_manager.model:
            logger.error("❌ 向量管理器初始化失败")
            return False
        
        # 4. 升级样本
        logger.info("🔄 升级样本结构...")
        new_samples = []
        
        for i, old_sample in enumerate(old_samples):
            logger.info(f"处理样本 {i+1}/{len(old_samples)}: ID={old_sample.get('id')}")
            
            new_sample = upgrade_sample_structure(old_sample, feature_extractor, vector_manager)
            if new_sample:
                new_samples.append(new_sample)
        
        if not new_samples:
            logger.error("❌ 没有成功升级的样本")
            return False
        
        # 5. 执行聚类分析
        logger.info("📊 执行聚类分析...")
        cluster_result = vector_manager.cluster_analysis()
        logger.info(f"聚类结果: {cluster_result['cluster_count']} 个聚类, {cluster_result['noise_points']} 个噪声点")
        
        # 6. 保存新结构
        logger.info("💾 保存升级后的数据...")
        if not save_new_structure(new_samples, vector_manager):
            logger.error("❌ 保存失败")
            return False
        
        # 7. 验证结果
        logger.info("🔍 验证升级结果...")
        if not validate_upgrade(new_samples):
            logger.warning("⚠️ 验证发现问题，但升级已完成")
        
        # 8. 打印摘要
        print_upgrade_summary(old_samples, new_samples)
        
        logger.info("🎉 升级完成!")
        return True
        
    except Exception as e:
        logger.error(f"❌ 升级过程中发生错误: {e}")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)