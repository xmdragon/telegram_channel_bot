#!/usr/bin/env python3
"""
批量重新处理未审核消息
使用训练好的尾部过滤和广告检测模型
"""
import asyncio
import sys
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Tuple, List, Dict, Any

from sqlalchemy import select, and_, or_, func
from app.core.database import AsyncSessionLocal, Message
from app.services.content_filter import ContentFilter
from app.services.ad_detector import AdDetector
from app.core.training_config import TrainingDataConfig
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class MessageReprocessor:
    """消息批量重处理器"""
    
    def __init__(self):
        self.content_filter = ContentFilter()
        self.ad_detector = AdDetector()
        
        # 统计信息
        self.stats = {
            'total_processed': 0,
            'tail_filtered': 0,
            'ad_detected': 0,
            'both_filtered': 0,
            'unchanged': 0,
            'errors': 0,
            'total_chars_removed': 0,
            'processing_time': 0
        }
        
        # 详细记录
        self.details = []
        self.error_messages = []
        
    async def process_message(self, message: Message) -> Dict[str, Any]:
        """处理单条消息"""
        start_time = time.time()
        result = {
            'id': message.id,
            'channel_id': message.source_channel,
            'original_length': len(message.content or ''),
            'filtered_length': 0,
            'tail_filtered': False,
            'chars_removed': 0,
            'is_ad': False,
            'ad_confidence': 0.0,
            'error': None,
            'processing_time': 0
        }
        
        try:
            if not message.content:
                result['error'] = '消息内容为空'
                return result
            
            original_content = message.content
            original_length = len(original_content)
            
            # 1. 应用尾部过滤（过滤频道推广信息）
            filtered_content = self.content_filter.filter_promotional_content(
                original_content, 
                channel_id=str(message.source_channel) if message.source_channel else None
            )
            
            # 检查是否进行了尾部过滤
            tail_filtered = len(filtered_content) < original_length
            chars_removed = original_length - len(filtered_content)
            
            result['tail_filtered'] = tail_filtered
            result['chars_removed'] = chars_removed
            
            # 2. 广告检测（使用过滤后的内容）
            is_ad, confidence = self.ad_detector.is_advertisement_ai(filtered_content)
            result['is_ad'] = is_ad
            result['ad_confidence'] = confidence
            
            # 3. 更新消息
            message.filtered_content = filtered_content
            message.is_ad = is_ad
            
            result['filtered_length'] = len(filtered_content)
            
            # 更新统计
            if tail_filtered:
                self.stats['tail_filtered'] += 1
                self.stats['total_chars_removed'] += chars_removed
            if is_ad:
                self.stats['ad_detected'] += 1
            if tail_filtered and is_ad:
                self.stats['both_filtered'] += 1
            if not tail_filtered and not is_ad:
                self.stats['unchanged'] += 1
                
        except Exception as e:
            result['error'] = str(e)
            self.stats['errors'] += 1
            self.error_messages.append({
                'message_id': message.id,
                'error': str(e)
            })
            logger.error(f"处理消息 {message.id} 时出错: {e}")
            
        result['processing_time'] = time.time() - start_time
        self.stats['processing_time'] += result['processing_time']
        
        return result
    
    async def process_batch(self, db, messages: List[Message], batch_num: int, total_batches: int):
        """处理一批消息"""
        print(f"\n处理批次 {batch_num}/{total_batches} ({len(messages)} 条消息)...")
        
        batch_start = time.time()
        batch_results = []
        
        for i, message in enumerate(messages):
            # 显示进度
            if i % 10 == 0:
                progress = i * 100 / len(messages)
                elapsed = time.time() - batch_start
                speed = i / elapsed if elapsed > 0 else 0
                print(f"  进度: {i}/{len(messages)} ({progress:.1f}%) - 速度: {speed:.1f} 条/秒", end='\r')
            
            result = await self.process_message(message)
            batch_results.append(result)
            self.details.append(result)
            self.stats['total_processed'] += 1
            
            # 可选：添加小延迟模拟实时处理
            # await asyncio.sleep(0.01)
        
        # 提交数据库更改
        try:
            await db.commit()
            print(f"\n  ✓ 批次 {batch_num} 完成 - 耗时: {time.time() - batch_start:.2f}秒")
        except Exception as e:
            logger.error(f"提交批次 {batch_num} 时出错: {e}")
            await db.rollback()
            print(f"\n  ✗ 批次 {batch_num} 提交失败: {e}")
        
        return batch_results
    
    async def run(self, batch_size: int = 100, limit: int = None):
        """执行批量处理"""
        print("=" * 70)
        print("批量重新处理未审核消息")
        print("=" * 70)
        
        overall_start = time.time()
        
        async with AsyncSessionLocal() as db:
            # 查询待处理消息总数
            total_query = select(func.count(Message.id)).where(
                and_(
                    Message.status == 'pending',
                    Message.content.isnot(None),
                    Message.content != ''
                )
            )
            total_count = await db.scalar(total_query)
            
            print(f"\n📊 数据统计:")
            print(f"  • 待处理消息总数: {total_count}")
            
            if limit:
                actual_limit = min(limit, total_count)
                print(f"  • 本次处理数量: {actual_limit} (限制)")
            else:
                actual_limit = total_count
                print(f"  • 本次处理数量: {actual_limit}")
            
            if actual_limit == 0:
                print("\n没有需要处理的消息")
                return
            
            # 查询待处理消息
            query = select(Message).where(
                and_(
                    Message.status == 'pending',
                    Message.content.isnot(None),
                    Message.content != ''
                )
            ).order_by(Message.id)
            
            if limit:
                query = query.limit(limit)
            
            result = await db.execute(query)
            all_messages = result.scalars().all()
            
            # 分批处理
            total_batches = (len(all_messages) + batch_size - 1) // batch_size
            print(f"  • 批次大小: {batch_size}")
            print(f"  • 总批次数: {total_batches}")
            print("\n开始处理...")
            print("-" * 70)
            
            for batch_num in range(total_batches):
                start_idx = batch_num * batch_size
                end_idx = min(start_idx + batch_size, len(all_messages))
                batch_messages = all_messages[start_idx:end_idx]
                
                await self.process_batch(db, batch_messages, batch_num + 1, total_batches)
        
        # 计算总耗时
        total_time = time.time() - overall_start
        
        # 生成报告
        self.generate_report(total_time)
    
    def generate_report(self, total_time: float):
        """生成处理报告"""
        print("\n" + "=" * 70)
        print("处理报告")
        print("=" * 70)
        
        if self.stats['total_processed'] == 0:
            print("没有处理任何消息")
            return
        
        print(f"\n📊 总体统计:")
        print(f"  • 总处理消息数: {self.stats['total_processed']:,}")
        print(f"  • 处理总耗时: {total_time:.2f} 秒")
        print(f"  • 平均处理速度: {self.stats['total_processed']/total_time:.1f} 条/秒")
        print(f"  • 平均单条耗时: {self.stats['processing_time']/self.stats['total_processed']*1000:.2f} 毫秒")
        
        print(f"\n🎯 过滤效果:")
        tail_pct = self.stats['tail_filtered'] * 100 / self.stats['total_processed']
        ad_pct = self.stats['ad_detected'] * 100 / self.stats['total_processed']
        both_pct = self.stats['both_filtered'] * 100 / self.stats['total_processed']
        unchanged_pct = self.stats['unchanged'] * 100 / self.stats['total_processed']
        
        print(f"  • 尾部过滤: {self.stats['tail_filtered']:,} 条 ({tail_pct:.1f}%)")
        if self.stats['tail_filtered'] > 0:
            avg_removed = self.stats['total_chars_removed'] / self.stats['tail_filtered']
            print(f"    - 平均移除字符: {avg_removed:.0f}")
            print(f"    - 总移除字符: {self.stats['total_chars_removed']:,}")
        
        print(f"  • 广告检测: {self.stats['ad_detected']:,} 条 ({ad_pct:.1f}%)")
        print(f"  • 双重过滤: {self.stats['both_filtered']:,} 条 ({both_pct:.1f}%)")
        print(f"  • 内容未变: {self.stats['unchanged']:,} 条 ({unchanged_pct:.1f}%)")
        
        if self.stats['errors'] > 0:
            print(f"\n⚠️ 错误统计:")
            print(f"  • 处理错误: {self.stats['errors']} 条")
            if len(self.error_messages) > 0:
                print(f"  • 错误示例:")
                for err in self.error_messages[:5]:
                    print(f"    - 消息 {err['message_id']}: {err['error']}")
        
        # 显示一些处理示例
        print(f"\n📝 处理示例:")
        examples = [d for d in self.details if d['tail_filtered'] or d['is_ad']][:5]
        for i, example in enumerate(examples, 1):
            print(f"\n  示例 {i} - 消息ID: {example['id']}")
            print(f"    • 原始长度: {example['original_length']} 字符")
            print(f"    • 过滤后长度: {example['filtered_length']} 字符")
            if example['tail_filtered']:
                print(f"    • 尾部过滤: 移除 {example['chars_removed']} 字符")
            if example['is_ad']:
                print(f"    • 广告检测: 是 (置信度: {example['ad_confidence']:.2f})")
        
        # 保存详细报告
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_file = Path(f"data/reprocess_report_{timestamp}.json")
        report_data = {
            'timestamp': datetime.now().isoformat(),
            'total_time': total_time,
            'stats': self.stats,
            'errors': self.error_messages[:50],  # 保存前50个错误
            'examples': examples[:20]  # 保存前20个示例
        }
        
        try:
            report_file.parent.mkdir(exist_ok=True)
            with open(report_file, 'w', encoding='utf-8') as f:
                json.dump(report_data, f, ensure_ascii=False, indent=2)
            print(f"\n💾 详细报告已保存至: {report_file}")
        except Exception as e:
            print(f"\n⚠️ 保存报告失败: {e}")
        
        print("\n✅ 批量处理完成！")
        print("=" * 70)


async def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='批量重新处理未审核消息')
    parser.add_argument('--batch-size', type=int, default=100, help='每批处理的消息数量（默认100）')
    parser.add_argument('--limit', type=int, help='限制处理的总消息数')
    parser.add_argument('--test', action='store_true', help='测试模式，只处理10条消息')
    
    args = parser.parse_args()
    
    if args.test:
        args.limit = 10
        print("🧪 测试模式：只处理10条消息\n")
    
    processor = MessageReprocessor()
    await processor.run(batch_size=args.batch_size, limit=args.limit)


if __name__ == '__main__':
    asyncio.run(main())