#!/usr/bin/env python3
"""
批量过滤未审核消息的脚本
使用新的智能尾部过滤器处理数据库中的所有未审核消息
"""

import asyncio
import logging
from datetime import datetime
from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal, Message
from app.services.intelligent_tail_filter import intelligent_tail_filter
import json

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class FilterReport:
    """过滤报告统计"""
    def __init__(self):
        self.total_messages = 0
        self.filtered_messages = 0
        self.total_chars_removed = 0
        self.messages_details = []
        self.new_patterns_learned = set()
        self.start_time = datetime.now()
        
    def add_result(self, message_id, original_len, filtered_len, has_tail, tail_content):
        """添加一条过滤结果"""
        self.total_messages += 1
        if has_tail:
            self.filtered_messages += 1
            chars_removed = original_len - filtered_len
            self.total_chars_removed += chars_removed
            self.messages_details.append({
                'id': message_id,
                'original_len': original_len,
                'filtered_len': filtered_len,
                'removed_chars': chars_removed,
                'tail_preview': tail_content[:100] if tail_content else ''
            })
            # 记录新学习的模式
            if tail_content and len(tail_content) > 20:
                self.new_patterns_learned.add(tail_content[:50])
    
    def generate_report(self):
        """生成报告"""
        end_time = datetime.now()
        duration = (end_time - self.start_time).total_seconds()
        
        report = {
            'summary': {
                'total_messages': self.total_messages,
                'filtered_messages': self.filtered_messages,
                'filter_rate': f"{(self.filtered_messages/self.total_messages*100):.1f}%" if self.total_messages > 0 else "0%",
                'total_chars_removed': self.total_chars_removed,
                'avg_chars_removed': self.total_chars_removed // self.filtered_messages if self.filtered_messages > 0 else 0,
                'new_patterns_learned': len(self.new_patterns_learned),
                'processing_time': f"{duration:.2f}秒",
                'processing_speed': f"{self.total_messages/duration:.1f}条/秒" if duration > 0 else "N/A"
            },
            'details': {
                'top_filtered': self.messages_details[:10],  # 前10条过滤最多的
                'patterns_learned': list(self.new_patterns_learned)[:20]  # 前20个新学习的模式
            },
            'model_stats': intelligent_tail_filter.get_statistics()
        }
        
        return report

async def batch_filter_messages():
    """批量过滤未审核的消息"""
    report = FilterReport()
    
    async with AsyncSessionLocal() as db:
        try:
            # 查询所有未审核的消息（status = 'pending'）
            logger.info("正在查询未审核的消息...")
            query = select(Message).where(
                and_(
                    Message.status == 'pending',
                    Message.content.isnot(None),
                    Message.content != ''
                )
            ).order_by(Message.created_at.desc())
            
            result = await db.execute(query)
            messages = result.scalars().all()
            
            logger.info(f"找到 {len(messages)} 条未审核消息")
            
            # 获取过滤前的模型状态
            initial_stats = intelligent_tail_filter.get_statistics()
            logger.info(f"初始模型状态: 样本数={initial_stats['total_samples']}, 关键词={initial_stats['learned_keywords']}")
            
            # 处理每条消息
            batch_size = 50
            for i in range(0, len(messages), batch_size):
                batch = messages[i:i+batch_size]
                logger.info(f"处理批次 {i//batch_size + 1}/{(len(messages)-1)//batch_size + 1}")
                
                for message in batch:
                    try:
                        # 使用智能过滤器处理
                        original_content = message.content
                        filtered_content, has_tail, tail_content = intelligent_tail_filter.filter_message(original_content)
                        
                        # 记录结果
                        report.add_result(
                            message.id,
                            len(original_content),
                            len(filtered_content),
                            has_tail,
                            tail_content
                        )
                        
                        # 如果检测到尾部，更新数据库
                        if has_tail:
                            message.filtered_content = filtered_content
                            
                            # 注意：不在这里调用add_training_sample，因为会导致重复重载
                            # 而是收集所有新样本，最后一次性保存
                            
                            logger.debug(f"消息 {message.id}: 移除了 {len(tail_content)} 个字符")
                        else:
                            # 没有尾部，保持原样
                            message.filtered_content = original_content
                    
                    except Exception as e:
                        logger.error(f"处理消息 {message.id} 时出错: {e}")
                        continue
                
                # 批量提交更改
                await db.commit()
                logger.info(f"已保存批次 {i//batch_size + 1} 的更改")
            
            # 获取过滤后的模型状态
            final_stats = intelligent_tail_filter.get_statistics()
            logger.info(f"最终模型状态: 样本数={final_stats['total_samples']}, 关键词={final_stats['learned_keywords']}")
            
            # 生成报告
            filter_report = report.generate_report()
            
            # 保存报告到文件
            report_file = f"filter_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(report_file, 'w', encoding='utf-8') as f:
                json.dump(filter_report, f, ensure_ascii=False, indent=2)
            
            logger.info(f"过滤报告已保存到: {report_file}")
            
            # 打印报告摘要
            print("\n" + "="*60)
            print("📊 智能尾部过滤报告")
            print("="*60)
            print(f"📈 处理统计:")
            print(f"  • 总消息数: {filter_report['summary']['total_messages']}")
            print(f"  • 过滤消息数: {filter_report['summary']['filtered_messages']}")
            print(f"  • 过滤率: {filter_report['summary']['filter_rate']}")
            print(f"  • 总移除字符: {filter_report['summary']['total_chars_removed']}")
            print(f"  • 平均每条移除: {filter_report['summary']['avg_chars_removed']} 字符")
            print(f"\n🧠 模型学习:")
            print(f"  • 新学习模式: {filter_report['summary']['new_patterns_learned']} 个")
            print(f"  • 当前总样本: {final_stats['total_samples']}")
            print(f"  • 学习关键词: {final_stats['learned_keywords']}")
            print(f"\n⚡ 性能指标:")
            print(f"  • 处理时间: {filter_report['summary']['processing_time']}")
            print(f"  • 处理速度: {filter_report['summary']['processing_speed']}")
            
            if filter_report['details']['top_filtered']:
                print(f"\n📝 过滤最多的消息 (前5条):")
                for msg in filter_report['details']['top_filtered'][:5]:
                    print(f"  • 消息 #{msg['id']}: 移除 {msg['removed_chars']} 字符")
                    if msg['tail_preview']:
                        preview = msg['tail_preview'][:50]
                        print(f"    尾部预览: {preview}...")
            
            print("\n" + "="*60)
            print("✅ 批量过滤完成！")
            print("="*60)
            
            return filter_report
            
        except Exception as e:
            logger.error(f"批量过滤失败: {e}")
            raise

async def main():
    """主函数"""
    try:
        report = await batch_filter_messages()
        return report
    except Exception as e:
        logger.error(f"执行失败: {e}")
        return None

if __name__ == "__main__":
    asyncio.run(main())