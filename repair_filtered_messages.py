#!/usr/bin/env python3
"""
修复已过滤消息脚本
根据新的过滤机制重新处理所有待审核的广告消息
"""
import asyncio
import logging
import sys
from datetime import datetime
from sqlalchemy import select, update, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Dict, Any, Tuple

# 添加项目路径
sys.path.append('/Users/eric/workspace/telegram_channel_bot')

from app.core.database import AsyncSessionLocal, Message, engine
from app.services.content_filter import ContentFilter
from app.services.ai_filter import ai_filter

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class MessageRepairer:
    """消息修复器"""
    
    def __init__(self):
        self.content_filter = ContentFilter()
        self.ai_filter = ai_filter  # 使用全局实例
        self.stats = {
            'total': 0,
            'repaired': 0,
            'unchanged': 0,
            'improved': 0,
            'content_restored': 0,
            'errors': 0
        }
        self.repair_log = []
        
    async def get_messages_to_repair(self, session: AsyncSession) -> List[Message]:
        """获取需要修复的消息"""
        try:
            # 查询所有待审核且被判定为广告的消息
            # 或者内容被过度过滤的消息
            query = select(Message).where(
                and_(
                    Message.status == 'pending',  # 待审核
                    or_(
                        Message.is_ad == True,  # 被判定为广告
                        Message.filtered_content == '',  # 内容被完全过滤
                        Message.filtered_content == None,  # 或者为空
                    ),
                    Message.content != None,  # 有原始内容
                    Message.content != ''  # 原始内容不为空
                )
            ).order_by(Message.created_at.desc())
            
            result = await session.execute(query)
            messages = result.scalars().all()
            
            logger.info(f"找到 {len(messages)} 条需要修复的消息")
            return messages
            
        except Exception as e:
            logger.error(f"查询消息失败: {e}")
            return []
    
    async def repair_message(self, message: Message) -> Tuple[bool, str, str]:
        """
        修复单条消息
        
        Returns:
            (是否修改, 修复后内容, 修复说明)
        """
        try:
            original_content = message.content
            old_filtered = message.filtered_content or ""
            
            # 使用新的过滤机制重新处理
            # 同步版本（不包含OCR等异步操作）
            is_ad, new_filtered, filter_reason = self.content_filter.filter_message_sync(
                original_content,
                channel_id=message.source_channel
            )
            
            # 判断是否有改进
            changed = False
            repair_notes = []
            
            # 比较新旧过滤结果
            if new_filtered != old_filtered:
                changed = True
                
                # 分析改进情况
                old_len = len(old_filtered)
                new_len = len(new_filtered)
                orig_len = len(original_content)
                
                if old_len == 0 and new_len > 0:
                    repair_notes.append(f"恢复内容: 0 -> {new_len} 字符")
                    self.stats['content_restored'] += 1
                elif new_len > old_len:
                    repair_notes.append(f"增加内容: {old_len} -> {new_len} 字符 (+{new_len - old_len})")
                    self.stats['improved'] += 1
                elif new_len < old_len:
                    repair_notes.append(f"减少内容: {old_len} -> {new_len} 字符 (-{old_len - new_len})")
                
                # 检查关键内容是否被恢复
                keywords = ['曝光', '爆料', '骗子', '黑店', '举报', '揭露']
                for keyword in keywords:
                    if keyword in original_content:
                        if keyword not in old_filtered and keyword in new_filtered:
                            repair_notes.append(f"恢复关键词: {keyword}")
                        break
                
                # 检查链接处理
                if '[' in original_content and '](' in original_content:
                    # 有Markdown链接
                    if '曝光' in original_content or '爆料' in original_content:
                        if '[' not in old_filtered and '[' in new_filtered:
                            repair_notes.append("恢复新闻链接")
            
            repair_note = ' | '.join(repair_notes) if repair_notes else "内容无变化"
            
            return changed, new_filtered, repair_note
            
        except Exception as e:
            logger.error(f"修复消息 {message.id} 失败: {e}")
            self.stats['errors'] += 1
            return False, message.filtered_content or "", f"修复失败: {str(e)}"
    
    async def update_message(self, session: AsyncSession, message: Message, 
                            new_filtered: str, repair_note: str) -> bool:
        """更新消息到数据库"""
        try:
            # 更新消息
            stmt = (
                update(Message)
                .where(Message.id == message.id)
                .values(
                    filtered_content=new_filtered,
                    updated_at=datetime.now()
                )
            )
            
            await session.execute(stmt)
            
            # 记录修复日志
            self.repair_log.append({
                'message_id': message.id,
                'source_channel': message.source_channel,
                'created_at': message.created_at.isoformat() if message.created_at else None,
                'original_length': len(message.content) if message.content else 0,
                'old_filtered_length': len(message.filtered_content) if message.filtered_content else 0,
                'new_filtered_length': len(new_filtered),
                'repair_note': repair_note
            })
            
            return True
            
        except Exception as e:
            logger.error(f"更新消息 {message.id} 失败: {e}")
            return False
    
    async def run_repair(self, batch_size: int = 100, dry_run: bool = False):
        """运行修复流程"""
        logger.info("=" * 60)
        logger.info("开始修复消息")
        logger.info(f"模式: {'测试模式（不保存）' if dry_run else '正式修复'}")
        logger.info("=" * 60)
        
        async with AsyncSessionLocal() as session:
            # 获取需要修复的消息
            messages = await self.get_messages_to_repair(session)
            self.stats['total'] = len(messages)
            
            if not messages:
                logger.info("没有需要修复的消息")
                return
            
            # 批量处理
            for i in range(0, len(messages), batch_size):
                batch = messages[i:i + batch_size]
                logger.info(f"处理批次 {i//batch_size + 1}/{(len(messages) + batch_size - 1)//batch_size}")
                
                for message in batch:
                    # 修复消息
                    changed, new_filtered, repair_note = await self.repair_message(message)
                    
                    if changed:
                        self.stats['repaired'] += 1
                        
                        # 显示修复信息
                        logger.info(f"修复消息 #{message.id}:")
                        logger.info(f"  频道: {message.source_channel}")
                        logger.info(f"  原始长度: {len(message.content) if message.content else 0}")
                        logger.info(f"  旧过滤: {len(message.filtered_content) if message.filtered_content else 0}")
                        logger.info(f"  新过滤: {len(new_filtered)}")
                        logger.info(f"  说明: {repair_note}")
                        
                        # 更新数据库（非测试模式）
                        if not dry_run:
                            success = await self.update_message(session, message, new_filtered, repair_note)
                            if not success:
                                self.stats['errors'] += 1
                    else:
                        self.stats['unchanged'] += 1
                
                # 提交批次（非测试模式）
                if not dry_run and self.stats['repaired'] > 0:
                    await session.commit()
                    logger.info(f"已提交 {self.stats['repaired']} 条修复")
            
            # 最终提交
            if not dry_run:
                await session.commit()
    
    def generate_report(self):
        """生成修复报告"""
        report = []
        report.append("\n" + "=" * 60)
        report.append("修复报告")
        report.append("=" * 60)
        report.append(f"总消息数: {self.stats['total']}")
        report.append(f"已修复: {self.stats['repaired']}")
        report.append(f"未变化: {self.stats['unchanged']}")
        report.append(f"内容改进: {self.stats['improved']}")
        report.append(f"内容恢复: {self.stats['content_restored']}")
        report.append(f"错误: {self.stats['errors']}")
        report.append("-" * 60)
        
        if self.stats['repaired'] > 0:
            success_rate = (self.stats['repaired'] / self.stats['total']) * 100
            report.append(f"修复率: {success_rate:.1f}%")
            
            if self.stats['content_restored'] > 0:
                restore_rate = (self.stats['content_restored'] / self.stats['repaired']) * 100
                report.append(f"内容恢复率: {restore_rate:.1f}%")
        
        # 显示前10条修复记录
        if self.repair_log:
            report.append("\n最近修复记录:")
            report.append("-" * 40)
            for log in self.repair_log[:10]:
                report.append(f"消息 #{log['message_id']}: {log['repair_note']}")
        
        report.append("=" * 60)
        
        return "\n".join(report)
    
    async def save_report(self, filename: str = None):
        """保存修复报告到文件"""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"repair_report_{timestamp}.json"
        
        import json
        
        report_data = {
            'timestamp': datetime.now().isoformat(),
            'statistics': self.stats,
            'repairs': self.repair_log
        }
        
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(report_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"报告已保存到: {filename}")
        except Exception as e:
            logger.error(f"保存报告失败: {e}")

async def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='修复被过度过滤的消息')
    parser.add_argument('--dry-run', action='store_true', help='测试模式，不保存到数据库')
    parser.add_argument('--batch-size', type=int, default=100, help='批处理大小')
    parser.add_argument('--save-report', action='store_true', help='保存详细报告到文件')
    
    args = parser.parse_args()
    
    # 创建修复器
    repairer = MessageRepairer()
    
    try:
        # 运行修复
        await repairer.run_repair(
            batch_size=args.batch_size,
            dry_run=args.dry_run
        )
        
        # 生成报告
        report = repairer.generate_report()
        print(report)
        
        # 保存报告
        if args.save_report:
            await repairer.save_report()
        
        # 如果是测试模式，提示用户
        if args.dry_run:
            print("\n⚠️  这是测试模式，没有实际修改数据库")
            print("💡 要执行实际修复，请运行: python3 repair_filtered_messages.py")
        else:
            print("\n✅ 修复完成！")
            
    except Exception as e:
        logger.error(f"修复过程出错: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)