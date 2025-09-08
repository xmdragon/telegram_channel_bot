#!/usr/bin/env python3
"""
清理单独消息脚本
删除已有组合版本的单独消息，提升系统性能

用法:
    python3 tools/maintenance/cleanup_single_messages.py --analyze    # 分析影响范围
    python3 tools/maintenance/cleanup_single_messages.py --clean      # 执行清理
    python3 tools/maintenance/cleanup_single_messages.py --dry-run    # 试运行
"""

import sys
import os
sys.path.append('/Users/eric/workspace/telegram_channel_bot')

import asyncio
import argparse
import logging
import json
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Set

from app.storage.redis_manager import redis_manager
from app.utils.timezone import get_current_time

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class SingleMessageCleaner:
    """单独消息清理器"""
    
    def __init__(self):
        # 初始化Redis存储
        from app.storage.redis_manager import redis_manager
        redis_manager.is_healthy()
        self.redis_store = redis_manager
        self.stats = {
            'total_messages': 0,
            'combined_messages': 0,
            'single_messages': 0,
            'single_with_combined': 0,  # 有组合版本的单独消息
            'space_saved': 0,
            'channels_processed': 0
        }
        
    async def analyze_impact(self) -> Dict:
        """分析清理影响范围"""
        logger.info("🔍 开始分析现有数据...")
        
        try:
            # 获取所有消息
            all_messages = self.redis_manager.get_all_messages(limit=10000)
            self.stats['total_messages'] = len(all_messages)
            
            # 按grouped_id分组分析
            grouped_data = defaultdict(list)
            channels = set()
            
            for msg in all_messages:
                channels.add(msg.get('source_channel', 'unknown'))
                
                if msg.get('is_combined'):
                    self.stats['combined_messages'] += 1
                else:
                    self.stats['single_messages'] += 1
                
                grouped_id = msg.get('grouped_id')
                if grouped_id:
                    grouped_data[grouped_id].append(msg)
            
            self.stats['channels_processed'] = len(channels)
            
            # 分析有组合版本的单独消息
            single_to_delete = []
            for grouped_id, messages in grouped_data.items():
                has_combined = any(msg.get('is_combined') for msg in messages)
                single_messages = [msg for msg in messages if not msg.get('is_combined')]
                
                if has_combined and single_messages:
                    self.stats['single_with_combined'] += len(single_messages)
                    single_to_delete.extend(single_messages)
            
            # 估算节省的空间
            self.stats['space_saved'] = self._estimate_space_saved(single_to_delete)
            
            # 生成分析报告
            report = {
                'analysis_time': get_current_time().isoformat(),
                'statistics': self.stats,
                'impact_summary': self._generate_impact_summary(),
                'recommendations': self._generate_recommendations()
            }
            
            return report
            
        except Exception as e:
            logger.error(f"分析失败: {e}")
            raise
    
    def _estimate_space_saved(self, messages: List[Dict]) -> Dict:
        """估算节省的空间"""
        total_size = 0
        content_size = 0
        metadata_size = 0
        
        for msg in messages:
            # 估算内容大小
            content = msg.get('content', '') + msg.get('filtered_content', '')
            content_size += len(content.encode('utf-8'))
            
            # 估算元数据大小
            metadata_size += len(json.dumps(msg, default=str).encode('utf-8'))
        
        total_size = content_size + metadata_size
        
        return {
            'total_bytes': total_size,
            'total_mb': round(total_size / 1024 / 1024, 2),
            'content_bytes': content_size,
            'metadata_bytes': metadata_size,
            'messages_count': len(messages)
        }
    
    def _generate_impact_summary(self) -> Dict:
        """生成影响摘要"""
        total = self.stats['total_messages']
        to_delete = self.stats['single_with_combined']
        
        return {
            'messages_to_delete': to_delete,
            'messages_to_keep': total - to_delete,
            'deletion_percentage': round(to_delete / total * 100, 1) if total > 0 else 0,
            'storage_reduction': f"{self.stats['space_saved']['total_mb']}MB"
        }
    
    def _generate_recommendations(self) -> List[str]:
        """生成建议"""
        recommendations = []
        
        if self.stats['single_with_combined'] == 0:
            recommendations.append("✅ 无需清理，所有数据都是最优状态")
        elif self.stats['single_with_combined'] < 100:
            recommendations.append("✅ 数据量较少，可以安全执行清理")
        elif self.stats['single_with_combined'] < 1000:
            recommendations.append("⚠️ 建议先备份数据，然后分批清理")
        else:
            recommendations.append("🚨 数据量很大，建议先在测试环境验证")
        
        space_mb = self.stats['space_saved']['total_mb']
        if space_mb > 100:
            recommendations.append(f"💾 清理后将节省 {space_mb}MB 存储空间")
        
        return recommendations
    
    async def cleanup_messages(self, dry_run: bool = False) -> Dict:
        """清理消息"""
        action = "试运行" if dry_run else "清理"
        logger.info(f"🗑️ 开始{action}单独消息...")
        
        try:
            cleanup_stats = {
                'deleted_count': 0,
                'failed_count': 0,
                'channels_affected': set(),
                'grouped_ids_processed': set(),
                'start_time': get_current_time(),
                'dry_run': dry_run
            }
            
            # 获取所有消息并分组
            all_messages = self.redis_manager.get_all_messages(limit=10000)
            grouped_data = defaultdict(list)
            
            for msg in all_messages:
                grouped_id = msg.get('grouped_id')
                if grouped_id:
                    grouped_data[grouped_id].append(msg)
            
            # 处理每个组
            for grouped_id, messages in grouped_data.items():
                await self._process_message_group(grouped_id, messages, cleanup_stats, dry_run)
            
            cleanup_stats['end_time'] = get_current_time()
            cleanup_stats['duration'] = (cleanup_stats['end_time'] - cleanup_stats['start_time']).total_seconds()
            cleanup_stats['channels_affected'] = list(cleanup_stats['channels_affected'])
            cleanup_stats['grouped_ids_processed'] = list(cleanup_stats['grouped_ids_processed'])
            
            return cleanup_stats
            
        except Exception as e:
            logger.error(f"{action}失败: {e}")
            raise
    
    async def _process_message_group(self, grouped_id: str, messages: List[Dict], 
                                   stats: Dict, dry_run: bool):
        """处理单个消息组"""
        # 检查是否有组合消息
        has_combined = any(msg.get('is_combined') for msg in messages)
        single_messages = [msg for msg in messages if not msg.get('is_combined')]
        
        if not has_combined or not single_messages:
            return
        
        stats['grouped_ids_processed'].add(grouped_id)
        logger.info(f"处理组 {grouped_id}: {len(single_messages)}条单独消息待清理")
        
        # 删除单独消息
        for msg in single_messages:
            try:
                msg_id = f"{msg.get('source_channel')}:{msg.get('message_id')}"
                channel = msg.get('source_channel')
                
                if dry_run:
                    logger.info(f"[试运行] 将删除消息: {msg_id}")
                    stats['deleted_count'] += 1
                else:
                    success = self.redis_manager.delete_message(msg_id)
                    if success:
                        stats['deleted_count'] += 1
                        stats['channels_affected'].add(channel)
                        logger.debug(f"删除消息成功: {msg_id}")
                    else:
                        stats['failed_count'] += 1
                        logger.warning(f"删除消息失败: {msg_id}")
                        
            except Exception as e:
                stats['failed_count'] += 1
                logger.error(f"删除消息时出错 {msg.get('message_id', 'unknown')}: {e}")

def print_analysis_report(report: Dict):
    """打印分析报告"""
    print("\n" + "="*60)
    print("📊 单独消息清理影响分析报告")
    print("="*60)
    
    stats = report['statistics']
    impact = report['impact_summary']
    
    print(f"\n📈 数据统计:")
    print(f"  总消息数: {stats['total_messages']:,}")
    print(f"  组合消息: {stats['combined_messages']:,}")
    print(f"  单独消息: {stats['single_messages']:,}")
    print(f"  需删除的单独消息: {stats['single_with_combined']:,}")
    print(f"  涉及频道数: {stats['channels_processed']}")
    
    print(f"\n💾 存储影响:")
    space = stats['space_saved']
    print(f"  可节省空间: {space['total_mb']} MB")
    print(f"  内容数据: {space['content_bytes']:,} bytes")
    print(f"  元数据: {space['metadata_bytes']:,} bytes")
    
    print(f"\n🎯 清理影响:")
    print(f"  删除消息数: {impact['messages_to_delete']:,}")
    print(f"  保留消息数: {impact['messages_to_keep']:,}")
    print(f"  删除比例: {impact['deletion_percentage']}%")
    
    print(f"\n💡 建议:")
    for rec in report['recommendations']:
        print(f"  {rec}")
    
    print("\n" + "="*60)

def print_cleanup_report(report: Dict):
    """打印清理报告"""
    action = "试运行" if report['dry_run'] else "清理"
    print(f"\n🗑️ {action}完成报告")
    print("="*40)
    print(f"删除消息数: {report['deleted_count']:,}")
    print(f"失败数: {report['failed_count']:,}")
    print(f"处理组数: {len(report['grouped_ids_processed'])}")
    print(f"涉及频道: {len(report['channels_affected'])}")
    print(f"用时: {report['duration']:.2f} 秒")

async def main():
    parser = argparse.ArgumentParser(description="清理单独消息工具")
    parser.add_argument('--analyze', action='store_true', help='分析影响范围')
    parser.add_argument('--clean', action='store_true', help='执行清理')
    parser.add_argument('--dry-run', action='store_true', help='试运行（不实际删除）')
    
    args = parser.parse_args()
    
    if not any([args.analyze, args.clean, args.dry_run]):
        parser.print_help()
        return
    
    cleaner = SingleMessageCleaner()
    
    try:
        if args.analyze:
            report = await cleaner.analyze_impact()
            print_analysis_report(report)
            
            # 保存分析报告
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            report_file = f"cleanup_analysis_{timestamp}.json"
            with open(report_file, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2, default=str)
            print(f"\n📄 分析报告已保存: {report_file}")
        
        elif args.clean or args.dry_run:
            report = await cleaner.cleanup_messages(dry_run=args.dry_run)
            print_cleanup_report(report)
            
            # 保存清理报告
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            action = "dry_run" if args.dry_run else "cleanup"
            report_file = f"cleanup_{action}_{timestamp}.json"
            with open(report_file, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2, default=str)
            print(f"\n📄 清理报告已保存: {report_file}")
    
    except Exception as e:
        logger.error(f"执行失败: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)