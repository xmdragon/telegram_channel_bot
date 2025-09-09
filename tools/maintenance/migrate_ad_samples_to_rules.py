#!/usr/bin/env python3
"""
广告样本迁移到过滤规则脚本
将ad_training_data.json中的广告样本转换为filter_rules.json中的正则表达式规则

Author: Claude (Linus Torvalds思维模式)
Created: 2025-09-09
"""

import json
import os
import sys
import re
import shutil
from datetime import datetime
from collections import Counter
from typing import List, Dict, Set, Tuple
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root))

from app.core.path_config import PathConfig


class AdSampleMigrator:
    """广告样本迁移器 - Linus式设计：简单、直接、有效"""
    
    def __init__(self):
        self.ad_training_file = PathConfig.AD_TRAINING_FILE
        self.filter_rules_file = Path(project_root) / "data" / "config" / "filter_rules.json"
        self.backup_dir = Path(project_root) / "backups"
        
        # 确保备份目录存在
        self.backup_dir.mkdir(exist_ok=True)
        
        # 分析结果存储
        self.extracted_patterns = []
        self.analysis_stats = {}
    
    def load_ad_samples(self) -> List[Dict]:
        """加载广告训练样本"""
        if not os.path.exists(self.ad_training_file):
            print(f"⚠️  广告训练文件不存在: {self.ad_training_file}")
            return []
        
        try:
            with open(self.ad_training_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                samples = data.get('samples', [])
                print(f"✅ 成功加载 {len(samples)} 个广告样本")
                return samples
        except Exception as e:
            print(f"❌ 加载广告样本失败: {e}")
            return []
    
    def load_filter_rules(self) -> Dict:
        """加载现有过滤规则"""
        try:
            with open(self.filter_rules_file, 'r', encoding='utf-8') as f:
                rules = json.load(f)
                print(f"✅ 成功加载现有过滤规则")
                return rules
        except Exception as e:
            print(f"❌ 加载过滤规则失败: {e}")
            return {}
    
    def analyze_samples(self, samples: List[Dict]) -> None:
        """分析广告样本，提取特征模式"""
        print("\n🔍 开始分析广告样本...")
        
        all_content = []
        for sample in samples:
            content = sample.get('content', '')
            all_content.append(content)
        
        # 1. 提取常见关键词
        self._extract_keywords(all_content)
        
        # 2. 提取数字模式
        self._extract_number_patterns(all_content) 
        
        # 3. 提取URL和联系方式模式
        self._extract_contact_patterns(all_content)
        
        # 4. 提取表情符号模式
        self._extract_emoji_patterns(all_content)
        
        # 5. 提取品牌和平台名称
        self._extract_brand_patterns(all_content)
        
        print(f"✅ 分析完成，提取了 {len(self.extracted_patterns)} 个新模式")
    
    def _extract_keywords(self, contents: List[str]) -> None:
        """提取高频关键词"""
        # 合并所有内容
        all_text = ' '.join(contents)
        
        # 定义关键词类别
        gambling_keywords = []
        fraud_keywords = []
        promotion_keywords = []
        
        # 赌博相关关键词检测
        gambling_terms = [
            '娱乐城', '娛樂城', '博彩', '赌场', '賭場', '棋牌', '体育投注', '彩票',
            'USDT', '泰达币', '虚拟币', 'U存U提', '出款', '提款', '充值',
            '首存', '二存', '三存', '返水', '优惠', '優惠', '赠送', '贈送',
            '盘总', '盤總', '狗庄', '狗莊', '提刀', '千倍', '爆奖', '爆獎'
        ]
        
        for term in gambling_terms:
            if term in all_text:
                count = all_text.count(term)
                if count >= 3:  # 出现3次以上的关键词才考虑
                    pattern = f"(?:{term})"
                    gambling_keywords.append({
                        "pattern": pattern,
                        "weight": 10,
                        "description": f"广告样本提取: {term}",
                        "category": "gambling",
                        "auto_learned": True,
                        "created_at": datetime.now().isoformat(),
                        "source_count": count
                    })
        
        # 诈骗相关关键词
        fraud_terms = [
            '日入.*[0-9]+.*万', '月入.*[0-9]+.*万', '日赚.*[0-9]+.*万',
            '奔驰', '奔馳', '宝马', '寶馬', '豪车', '套房',
            '百亿', '百億', '巨额', '巨額', '千万', '千萬'
        ]
        
        for term in fraud_terms:
            if re.search(term, all_text):
                pattern = term if '.*' in term else f"(?:{term})"
                fraud_keywords.append({
                    "pattern": pattern,
                    "weight": 10,
                    "description": f"广告样本提取: {term}诈骗模式",
                    "category": "fraud", 
                    "auto_learned": True,
                    "created_at": datetime.now().isoformat()
                })
        
        # 添加到提取的模式中
        self.extracted_patterns.extend(gambling_keywords)
        self.extracted_patterns.extend(fraud_keywords)
        
        print(f"   提取关键词: 赌博 {len(gambling_keywords)} 个, 诈骗 {len(fraud_keywords)} 个")
    
    def _extract_number_patterns(self, contents: List[str]) -> None:
        """提取数字相关模式"""
        number_patterns = []
        
        all_text = ' '.join(contents)
        
        # 大额数字模式
        patterns = [
            {
                "pattern": r"[0-9]+万[UuＵｕ美金]",
                "description": "大额资金宣传",
                "category": "gambling"
            },
            {
                "pattern": r"[0-9]+亿.*(?:资金|資金|投入)",
                "description": "巨额资金投入宣传", 
                "category": "gambling"
            },
            {
                "pattern": r"单笔.*[0-9]+万.*(?:出款|提款)",
                "description": "单笔大额出款承诺",
                "category": "gambling"
            }
        ]
        
        for pattern_info in patterns:
            if re.search(pattern_info["pattern"], all_text):
                number_patterns.append({
                    "pattern": pattern_info["pattern"],
                    "weight": 10,
                    "description": f"广告样本提取: {pattern_info['description']}",
                    "category": pattern_info["category"],
                    "auto_learned": True,
                    "created_at": datetime.now().isoformat()
                })
        
        self.extracted_patterns.extend(number_patterns)
        print(f"   提取数字模式: {len(number_patterns)} 个")
    
    def _extract_contact_patterns(self, contents: List[str]) -> None:
        """提取联系方式模式"""
        contact_patterns = []
        
        all_text = ' '.join(contents)
        
        # Telegram用户名模式
        telegram_usernames = re.findall(r'@[a-zA-Z][a-zA-Z0-9_]{3,30}', all_text)
        if len(telegram_usernames) >= 10:  # 用户名数量较多时才创建模式
            contact_patterns.append({
                "pattern": r"(?:客服|代理|官方|频道|招商).*@[a-zA-Z][a-zA-Z0-9_]{3,30}",
                "weight": 8,
                "description": "广告样本提取: 官方联系方式模式",
                "category": "contact",
                "auto_learned": True,
                "created_at": datetime.now().isoformat()
            })
        
        # 域名模式
        domains = re.findall(r'[a-zA-Z0-9][a-zA-Z0-9\-]{1,61}[a-zA-Z0-9]\.[a-zA-Z]{2,}', all_text)
        unique_domains = set(domains)
        if len(unique_domains) >= 5:
            contact_patterns.append({
                "pattern": r"[a-zA-Z0-9]+\d+\.(?:com|vip|top|net)",
                "weight": 9,
                "description": "广告样本提取: 赌博网站域名模式",
                "category": "gambling",
                "auto_learned": True,
                "created_at": datetime.now().isoformat()
            })
        
        self.extracted_patterns.extend(contact_patterns)
        print(f"   提取联系模式: {len(contact_patterns)} 个")
    
    def _extract_emoji_patterns(self, contents: List[str]) -> None:
        """提取表情符号模式"""
        emoji_patterns = []
        
        # 检查表情密集使用模式
        for content in contents:
            # 计算表情符号密度
            emoji_count = len(re.findall(r'[😀-🙏🌀-🗿🚀-🛿🇦-🇿]', content))
            if emoji_count > 10:  # 表情超过10个
                # 创建表情密集模式
                if not any(p.get('description') == '广告样本提取: 表情符号密集使用' 
                          for p in self.extracted_patterns):
                    emoji_patterns.append({
                        "pattern": r"[😀-🙏🌀-🗿🚀-🛿🇦-🇿]{8,}",
                        "weight": 6,
                        "description": "广告样本提取: 表情符号密集使用",
                        "category": "promotion",
                        "auto_learned": True,
                        "created_at": datetime.now().isoformat()
                    })
                    break
        
        self.extracted_patterns.extend(emoji_patterns)
        print(f"   提取表情模式: {len(emoji_patterns)} 个")
    
    def _extract_brand_patterns(self, contents: List[str]) -> None:
        """提取品牌和平台名称模式"""
        brand_patterns = []
        
        all_text = ' '.join(contents)
        
        # 常见赌博品牌
        brands = ['UU', '9Y', '2028', 'N9', '西港', '永旺']
        for brand in brands:
            if brand in all_text and all_text.count(brand) >= 2:
                brand_patterns.append({
                    "pattern": f"(?:{brand}).*(?:娱乐|娛樂|国际|國際|平台|体育)",
                    "weight": 10,
                    "description": f"广告样本提取: {brand}赌博平台",
                    "category": "gambling",
                    "auto_learned": True,
                    "created_at": datetime.now().isoformat()
                })
        
        self.extracted_patterns.extend(brand_patterns)
        print(f"   提取品牌模式: {len(brand_patterns)} 个")
    
    def backup_files(self) -> bool:
        """备份现有文件"""
        print("\n💾 备份现有文件...")
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        try:
            # 备份ad_training_data.json
            if os.path.exists(self.ad_training_file):
                backup_ad_file = self.backup_dir / f"ad_training_data_{timestamp}.json"
                shutil.copy2(self.ad_training_file, backup_ad_file)
                print(f"   ✅ 已备份: {backup_ad_file}")
            
            # 备份filter_rules.json
            if os.path.exists(self.filter_rules_file):
                backup_rules_file = self.backup_dir / f"filter_rules_{timestamp}.json"
                shutil.copy2(self.filter_rules_file, backup_rules_file)
                print(f"   ✅ 已备份: {backup_rules_file}")
            
            return True
        except Exception as e:
            print(f"   ❌ 备份失败: {e}")
            return False
    
    def merge_patterns_to_rules(self, rules: Dict) -> Dict:
        """将提取的模式合并到过滤规则中"""
        print(f"\n🔄 合并 {len(self.extracted_patterns)} 个新模式到过滤规则...")
        
        # 统计各类别的新增数量
        category_counts = {}
        
        for pattern in self.extracted_patterns:
            category = pattern.get('category', 'other')
            
            # 根据类别添加到对应的规则组
            if category in ['gambling', 'fraud', 'pornography']:
                # 高危关键词组
                rules['rule_categories']['high_risk_keywords']['patterns'].append(pattern)
                category_counts[category] = category_counts.get(category, 0) + 1
            else:
                # 推广模式组
                rules['rule_categories']['promo_patterns']['patterns'].append(pattern)
                category_counts[category] = category_counts.get(category, 0) + 1
        
        # 更新学习统计
        rules['learning_stats']['total_learned'] += len(self.extracted_patterns)
        rules['learning_stats']['last_learning'] = datetime.now().isoformat()
        
        for category, count in category_counts.items():
            rules['learning_stats']['patterns_by_category'][category] += count
        
        # 更新版本信息
        rules['last_updated'] = datetime.now().isoformat()
        
        print(f"   ✅ 合并完成: {category_counts}")
        return rules
    
    def save_filter_rules(self, rules: Dict) -> bool:
        """保存更新的过滤规则"""
        try:
            with open(self.filter_rules_file, 'w', encoding='utf-8') as f:
                json.dump(rules, f, ensure_ascii=False, indent=2)
            print(f"   ✅ 过滤规则已保存: {self.filter_rules_file}")
            return True
        except Exception as e:
            print(f"   ❌ 保存过滤规则失败: {e}")
            return False
    
    def clear_ad_training_file(self) -> bool:
        """清空广告训练数据文件，保留基本结构"""
        try:
            empty_structure = {
                "samples": [],
                "metadata": {
                    "total_samples": 0,
                    "created_at": datetime.now().isoformat(),
                    "last_updated": datetime.now().isoformat(),
                    "migrated_to_filter_rules": True,
                    "migration_date": datetime.now().isoformat()
                }
            }
            
            with open(self.ad_training_file, 'w', encoding='utf-8') as f:
                json.dump(empty_structure, f, ensure_ascii=False, indent=2)
            
            print(f"   ✅ 广告训练文件已清空: {self.ad_training_file}")
            return True
        except Exception as e:
            print(f"   ❌ 清空训练文件失败: {e}")
            return False
    
    def migrate(self) -> bool:
        """执行完整的迁移流程"""
        print("🚀 开始广告样本数据迁移...")
        print("=" * 60)
        
        # 1. 加载数据
        samples = self.load_ad_samples()
        if not samples:
            print("❌ 没有广告样本需要迁移")
            return False
        
        rules = self.load_filter_rules()
        if not rules:
            print("❌ 无法加载过滤规则")
            return False
        
        # 2. 备份文件
        if not self.backup_files():
            print("❌ 文件备份失败，终止迁移")
            return False
        
        # 3. 分析样本
        self.analyze_samples(samples)
        
        # 4. 合并规则
        updated_rules = self.merge_patterns_to_rules(rules)
        
        # 5. 保存更新的规则
        if not self.save_filter_rules(updated_rules):
            print("❌ 保存过滤规则失败")
            return False
        
        # 6. 清空训练文件
        if not self.clear_ad_training_file():
            print("❌ 清空训练文件失败")
            return False
        
        # 7. 生成报告
        self.generate_migration_report(samples, updated_rules)
        
        print("\n🎉 广告样本迁移完成！")
        print("=" * 60)
        return True
    
    def generate_migration_report(self, samples: List[Dict], rules: Dict) -> None:
        """生成迁移报告"""
        print(f"\n📊 迁移报告")
        print("-" * 40)
        print(f"原始广告样本数量: {len(samples)}")
        print(f"提取的新规则数量: {len(self.extracted_patterns)}")
        
        # 统计各类别
        category_stats = {}
        for pattern in self.extracted_patterns:
            category = pattern.get('category', 'other')
            category_stats[category] = category_stats.get(category, 0) + 1
        
        print("按类别分布:")
        for category, count in category_stats.items():
            print(f"  {category}: {count} 个")
        
        # 当前规则总数
        total_high_risk = len(rules['rule_categories']['high_risk_keywords']['patterns'])
        total_promo = len(rules['rule_categories']['promo_patterns']['patterns'])
        print(f"\n当前规则总数:")
        print(f"  高危关键词: {total_high_risk} 个")
        print(f"  推广模式: {total_promo} 个")


def main():
    """主函数"""
    print("广告样本数据迁移工具")
    print("将ad_training_data.json中的样本转换为filter_rules.json中的规则")
    print()
    
    migrator = AdSampleMigrator()
    
    # 执行迁移
    success = migrator.migrate()
    
    if success:
        print("\n✅ 迁移成功完成！")
        print("现在所有广告检测规则统一存储在 filter_rules.json 中")
        print("原始样本数据已备份到 backups/ 目录")
    else:
        print("\n❌ 迁移失败！请检查错误信息")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())