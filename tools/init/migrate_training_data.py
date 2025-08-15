#!/usr/bin/env python3
"""
训练数据迁移脚本
将旧的训练样本迁移到新的智能学习系统
"""
import json
import logging
from pathlib import Path
from datetime import datetime
import asyncio
from sqlalchemy import select

from app.services.intelligent_learning_system import intelligent_learning_system
from app.core.database import AsyncSessionLocal, Message

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TrainingDataMigrator:
    """训练数据迁移器"""
    
    def __init__(self):
        self.old_samples_file = Path("data/tail_filter_samples.json")
        self.backup_dir = Path("data/migration_backup")
        self.backup_dir.mkdir(exist_ok=True)
        
        self.stats = {
            'total_samples': 0,
            'valid_samples': 0,
            'invalid_samples': 0,
            'patterns_learned': 0,
            'errors': []
        }
    
    async def migrate(self):
        """执行迁移"""
        logger.info("开始训练数据迁移...")
        
        # 1. 备份现有数据
        self._backup_existing_data()
        
        # 2. 加载旧样本
        old_samples = self._load_old_samples()
        if not old_samples:
            logger.warning("没有找到旧的训练样本")
            return
        
        self.stats['total_samples'] = len(old_samples)
        logger.info(f"找到 {len(old_samples)} 个旧样本")
        
        # 3. 验证并迁移每个样本
        for i, sample in enumerate(old_samples, 1):
            logger.info(f"处理样本 {i}/{len(old_samples)}")
            await self._process_sample(sample)
        
        # 4. 生成报告
        self._generate_report()
    
    def _backup_existing_data(self):
        """备份现有数据"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 备份旧的训练样本文件
        if self.old_samples_file.exists():
            backup_path = self.backup_dir / f"tail_filter_samples_{timestamp}.json"
            with open(self.old_samples_file, 'r') as src:
                with open(backup_path, 'w') as dst:
                    dst.write(src.read())
            logger.info(f"备份旧样本文件到: {backup_path}")
        
        # 备份学习的模式（如果存在）
        patterns_file = Path("data/learned_patterns.json")
        if patterns_file.exists():
            backup_path = self.backup_dir / f"learned_patterns_{timestamp}.json"
            with open(patterns_file, 'r') as src:
                with open(backup_path, 'w') as dst:
                    dst.write(src.read())
            logger.info(f"备份模式文件到: {backup_path}")
    
    def _load_old_samples(self):
        """加载旧的训练样本"""
        if not self.old_samples_file.exists():
            return []
        
        try:
            with open(self.old_samples_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('samples', [])
        except Exception as e:
            logger.error(f"加载旧样本失败: {e}")
            return []
    
    async def _process_sample(self, sample_data):
        """处理单个样本"""
        try:
            tail_part = sample_data.get('tail_part', '')
            message_id = sample_data.get('message_id')
            
            if not tail_part:
                logger.warning(f"样本 {sample_data.get('id')} 没有尾部内容，跳过")
                self.stats['invalid_samples'] += 1
                return
            
            # 如果有消息ID，尝试获取原始消息
            original_message = await self._get_original_message(message_id)
            
            if not original_message:
                # 如果没有原始消息，构造一个模拟的
                original_message = self._construct_mock_message(tail_part)
            
            # 验证样本质量
            validation_result = self._validate_sample(tail_part, original_message, message_id)
            
            if validation_result['is_valid']:
                # 使用智能学习系统学习
                result = intelligent_learning_system.add_training_sample(
                    tail_part, 
                    original_message,
                    message_id
                )
                
                if result['success']:
                    self.stats['valid_samples'] += 1
                    self.stats['patterns_learned'] += 1
                    logger.info(f"成功迁移样本: {result['message']}")
                else:
                    self.stats['invalid_samples'] += 1
                    logger.warning(f"样本验证通过但学习失败: {result['message']}")
            else:
                self.stats['invalid_samples'] += 1
                reasons = validation_result.get('errors', ['未知原因'])
                logger.warning(f"样本无效: {', '.join(reasons)}")
                self.stats['errors'].append({
                    'sample_id': sample_data.get('id'),
                    'reasons': reasons
                })
        
        except Exception as e:
            logger.error(f"处理样本时出错: {e}")
            self.stats['errors'].append({
                'sample_id': sample_data.get('id'),
                'error': str(e)
            })
    
    async def _get_original_message(self, message_id):
        """获取原始消息"""
        if not message_id:
            return None
        
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Message).where(Message.id == message_id)
                )
                message = result.scalar_one_or_none()
                if message:
                    return message.content
        except Exception as e:
            logger.debug(f"获取消息 {message_id} 失败: {e}")
        
        return None
    
    def _construct_mock_message(self, tail_part):
        """构造模拟消息"""
        # 构造一个包含尾部的模拟消息
        mock_content = """
这是一条模拟的新闻消息内容。
包含一些正文内容用于验证。
新闻事件描述等等。

""" + tail_part
        return mock_content
    
    def _validate_sample(self, tail_part, original_message, message_id):
        """验证样本质量"""
        # 使用智能学习系统的验证器
        from app.services.intelligent_learning_system import SampleValidator
        validator = SampleValidator()
        
        # 特殊检查：防止自引用
        if message_id and original_message:
            # 检查样本是否包含正文内容
            # 尾部应该只包含推广内容，不应该包含新闻正文
            news_keywords = ['马云', '阿里', '腾讯', '政府', '国家', '亿', '万']
            contains_news = sum(1 for kw in news_keywords if kw in tail_part)
            
            if contains_news > 2:
                return {
                    'is_valid': False,
                    'errors': ['样本包含过多新闻关键词，可能是正文内容']
                }
        
        return validator.validate(tail_part, original_message, message_id)
    
    def _generate_report(self):
        """生成迁移报告"""
        report = {
            'migration_time': datetime.now().isoformat(),
            'statistics': self.stats,
            'success_rate': self.stats['valid_samples'] / max(self.stats['total_samples'], 1),
            'system_stats': intelligent_learning_system.get_statistics()
        }
        
        # 保存报告
        report_file = self.backup_dir / f"migration_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        # 打印摘要
        print("\n" + "=" * 60)
        print("📊 训练数据迁移报告")
        print("=" * 60)
        print(f"处理样本总数: {self.stats['total_samples']}")
        print(f"有效样本数: {self.stats['valid_samples']}")
        print(f"无效样本数: {self.stats['invalid_samples']}")
        print(f"学习的模式数: {self.stats['patterns_learned']}")
        print(f"成功率: {report['success_rate']:.1%}")
        
        if self.stats['errors']:
            print(f"\n⚠️ 发现 {len(self.stats['errors'])} 个错误")
            for error in self.stats['errors'][:5]:  # 只显示前5个
                print(f"  - 样本 {error.get('sample_id')}: {error.get('reasons', error.get('error'))}")
        
        print(f"\n报告已保存到: {report_file}")
        print("=" * 60)


async def main():
    """主函数"""
    migrator = TrainingDataMigrator()
    await migrator.migrate()


if __name__ == "__main__":
    asyncio.run(main())