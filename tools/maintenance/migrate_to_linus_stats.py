#!/usr/bin/env python3
"""
数据迁移到Linus式统计系统
将复杂的遗留统计数据迁移到简化的3状态+元数据模型

使用方法:
    python3 migrate_to_linus_stats.py --dry-run       # 预览迁移
    python3 migrate_to_linus_stats.py --migrate       # 执行迁移
    python3 migrate_to_linus_stats.py --validate      # 验证迁移结果

迁移策略:
1. 扫描现有所有消息
2. 将复杂状态映射到3种基本状态
3. 提取拒绝原因作为元数据
4. 重新计算统计计数器
5. 验证数据一致性
"""
import sys
import os
import asyncio
import argparse
from typing import Dict, List, Optional, Any
from datetime import datetime
from collections import defaultdict

# 添加项目路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from app.storage.redis_store import get_redis_message_store, init_redis_stores
from app.storage.linus_stats_store import get_linus_stats_store, init_linus_stats_store, MessageState, RejectionReason
from app.core.message_status import StatusMapper, normalize_message_data
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class LinusStatsMigrator:
    """Linus式统计数据迁移器"""
    
    def __init__(self):
        init_redis_stores()
        init_linus_stats_store()
        self.redis_store = get_redis_message_store()
        self.linus_stats = get_linus_stats_store()
        
        # 迁移统计
        self.migration_stats = {
            'total_messages': 0,
            'migrated_messages': 0,
            'error_messages': 0,
            'status_mapping': defaultdict(int),
            'rejection_reasons': defaultdict(int),
            'channels_processed': 0
        }
    
    async def analyze_existing_data(self) -> Dict[str, Any]:
        """分析现有数据结构"""
        print("🔍 分析现有数据结构...")
        
        analysis = {
            'message_count': 0,
            'channels': set(),
            'status_distribution': defaultdict(int),
            'filter_reasons': defaultdict(int),
            'boolean_flags': defaultdict(int),
            'sample_messages': []
        }
        
        try:
            # 获取所有消息键
            pattern = "msg:*"
            keys = self.redis_store.redis.keys(pattern)
            
            # 过滤出消息数据键（排除计数器和索引）
            message_keys = [k for k in keys if not any(x in (k.decode() if isinstance(k, bytes) else k) for x in ['count:', 'idx:', 'hash:', 'group:'])]
            
            print(f"📊 发现 {len(message_keys)} 个消息记录")
            
            # 抽样分析前100条消息
            sample_keys = message_keys[:100]
            
            for i, key in enumerate(sample_keys):
                try:
                    msg_data = self.redis_store.redis.hgetall(key)
                    if not msg_data:
                        continue
                    
                    # 解码数据
                    decoded_data = {}
                    for k, v in msg_data.items():
                        try:
                            key = k.decode() if isinstance(k, bytes) else k
                            value = v.decode() if isinstance(v, bytes) else str(v)
                            decoded_data[key] = value
                        except Exception as e:
                            key = str(k)
                            value = str(v)
                            decoded_data[key] = value
                    
                    analysis['message_count'] += 1
                    
                    # 分析状态
                    status = decoded_data.get('status', 'unknown')
                    analysis['status_distribution'][status] += 1
                    
                    # 分析过滤原因
                    filter_reason = decoded_data.get('filter_reason')
                    if filter_reason:
                        analysis['filter_reasons'][filter_reason] += 1
                    
                    # 分析布尔标志
                    for flag in ['is_ad', 'is_duplicate']:
                        if decoded_data.get(flag) == 'True':
                            analysis['boolean_flags'][flag] += 1
                    
                    # 提取频道信息
                    source_channel = decoded_data.get('source_channel')
                    if source_channel:
                        analysis['channels'].add(source_channel)
                    
                    # 保存样本消息
                    if len(analysis['sample_messages']) < 10:
                        analysis['sample_messages'].append({
                            'key': key.decode() if isinstance(key, bytes) else key,
                            'status': status,
                            'filter_reason': filter_reason,
                            'source_channel': source_channel,
                            'is_ad': decoded_data.get('is_ad'),
                            'is_duplicate': decoded_data.get('is_duplicate'),
                        })
                
                except Exception as e:
                    logger.warning(f"分析消息失败 {key}: {e}")
                    continue
            
            analysis['channels'] = list(analysis['channels'])
            
            return analysis
            
        except Exception as e:
            logger.error(f"数据分析失败: {e}")
            return analysis
    
    async def dry_run_migration(self) -> Dict[str, Any]:
        """预览迁移（不实际修改数据）"""
        print("🧪 执行迁移预览...")
        
        # 先分析现有数据
        analysis = await self.analyze_existing_data()
        
        print(f"\n📋 迁移预览报告:")
        print(f"消息总数: {analysis['message_count']}")
        print(f"涉及频道: {len(analysis['channels'])}")
        
        print(f"\n🔄 状态映射预览:")
        for old_status, count in analysis['status_distribution'].items():
            new_status = StatusMapper.map_legacy_status(old_status)
            print(f"  {old_status} ({count}条) -> {new_status.value}")
        
        print(f"\n🚫 拒绝原因映射预览:")
        for reason, count in analysis['filter_reasons'].items():
            mapped_reason = StatusMapper.map_legacy_reason(reason)
            mapped_name = mapped_reason.value if mapped_reason else 'other'
            print(f"  {reason} ({count}条) -> {mapped_name}")
        
        print(f"\n🏷️  布尔标志统计:")
        for flag, count in analysis['boolean_flags'].items():
            print(f"  {flag}: {count}条")
        
        # 计算迁移后的统计预览
        preview_stats = {
            'pending': 0,
            'accepted': 0,
            'rejected': 0,
            'ad_rejection': 0,
            'duplicate_rejection': 0,
            'chat_rejection': 0,
            'other_rejection': 0
        }
        
        for old_status, count in analysis['status_distribution'].items():
            new_status = StatusMapper.map_legacy_status(old_status)
            preview_stats[new_status.value] += count
        
        for reason, count in analysis['filter_reasons'].items():
            mapped_reason = StatusMapper.map_legacy_reason(reason)
            if mapped_reason:
                key = f"{mapped_reason.value}_rejection"
                if key in preview_stats:
                    preview_stats[key] += count
        
        print(f"\n📊 迁移后统计预览:")
        print(f"  总计: {sum([preview_stats['pending'], preview_stats['accepted'], preview_stats['rejected']])}")
        print(f"  待处理: {preview_stats['pending']}")
        print(f"  已接受: {preview_stats['accepted']}")
        print(f"  已拒绝: {preview_stats['rejected']}")
        print(f"    └─ 广告: {preview_stats['ad_rejection']}")
        print(f"    └─ 重复: {preview_stats['duplicate_rejection']}")
        print(f"    └─ 聊天: {preview_stats['chat_rejection']}")
        print(f"    └─ 其他: {preview_stats['other_rejection']}")
        
        return {
            'analysis': analysis,
            'preview_stats': preview_stats
        }
    
    async def execute_migration(self) -> Dict[str, Any]:
        """执行实际迁移"""
        print("🚀 开始执行数据迁移...")
        
        # 重置Linus统计
        print("🔄 重置Linus统计计数器...")
        self.linus_stats.reset_stats()
        
        try:
            # 获取所有消息键
            pattern = "msg:*"
            keys = self.redis_store.redis.keys(pattern)
            message_keys = [k for k in keys if not any(x in (k.decode() if isinstance(k, bytes) else k) for x in ['count:', 'idx:', 'hash:', 'group:'])]
            
            print(f"📝 开始处理 {len(message_keys)} 个消息...")
            
            processed = 0
            errors = 0
            
            for i, key in enumerate(message_keys):
                try:
                    # 读取消息数据
                    msg_data = self.redis_store.redis.hgetall(key)
                    if not msg_data:
                        continue
                    
                    # 解码数据
                    decoded_data = {}
                    for k, v in msg_data.items():
                        try:
                            key = k.decode() if isinstance(k, bytes) else k
                            value = v.decode() if isinstance(v, bytes) else str(v)
                            decoded_data[key] = value
                        except Exception as e:
                            key = str(k)
                            value = str(v)
                            decoded_data[key] = value
                    
                    # 规范化数据
                    normalized_data = normalize_message_data(decoded_data)
                    
                    # 提取状态和拒绝原因
                    status_str = normalized_data.get('status', 'pending')
                    try:
                        status = MessageState(status_str)
                    except ValueError:
                        status = MessageState.PENDING
                    
                    rejection_reason = None
                    if status == MessageState.REJECTED:
                        reason_str = normalized_data.get('rejection_reason')
                        if reason_str:
                            try:
                                rejection_reason = RejectionReason(reason_str)
                            except ValueError:
                                rejection_reason = RejectionReason.OTHER
                    
                    # 提取频道信息
                    channel_id = decoded_data.get('source_channel')
                    
                    # 更新Linus统计
                    self.linus_stats.increment_message(status, channel_id)
                    
                    # 如果是拒绝消息，更新拒绝原因统计
                    if status == MessageState.REJECTED and rejection_reason:
                        # 这里需要手动增加拒绝原因计数，因为increment_message不处理原因
                        self.linus_stats.redis.hincrby(
                            self.linus_stats.REJECTION_STATS_KEY, 
                            rejection_reason.value, 
                            1
                        )
                    
                    # 更新迁移统计
                    self.migration_stats['total_messages'] += 1
                    self.migration_stats['migrated_messages'] += 1
                    self.migration_stats['status_mapping'][status.value] += 1
                    
                    if rejection_reason:
                        self.migration_stats['rejection_reasons'][rejection_reason.value] += 1
                    
                    processed += 1
                    
                    # 定期输出进度
                    if processed % 100 == 0:
                        print(f"  处理进度: {processed}/{len(message_keys)} ({(processed/len(message_keys)*100):.1f}%)")
                
                except Exception as e:
                    logger.error(f"迁移消息失败 {key}: {e}")
                    errors += 1
                    self.migration_stats['error_messages'] += 1
                    continue
            
            print(f"\n✅ 迁移完成!")
            print(f"成功处理: {processed} 条消息")
            print(f"错误: {errors} 条消息")
            
            # 验证迁移结果
            validation = await self.validate_migration()
            
            return {
                'processed': processed,
                'errors': errors,
                'migration_stats': self.migration_stats,
                'validation': validation
            }
            
        except Exception as e:
            logger.error(f"迁移执行失败: {e}")
            raise
    
    async def validate_migration(self) -> Dict[str, Any]:
        """验证迁移结果"""
        print("✅ 验证迁移结果...")
        
        # 获取Linus统计
        global_stats = self.linus_stats.get_global_stats()
        rejection_stats = self.linus_stats.get_rejection_stats()
        
        # 验证一致性
        consistency = self.linus_stats.validate_consistency()
        
        print(f"\n📊 迁移后统计结果:")
        print(f"总消息数: {global_stats.total}")
        print(f"待处理: {global_stats.pending}")
        print(f"已接受: {global_stats.accepted}")
        print(f"已拒绝: {global_stats.rejected}")
        
        print(f"\n🚫 拒绝原因统计:")
        print(f"广告: {rejection_stats.ad}")
        print(f"重复: {rejection_stats.duplicate}")
        print(f"聊天: {rejection_stats.chat}")
        print(f"其他: {rejection_stats.other}")
        
        print(f"\n🔍 数据一致性检查:")
        print(f"一致性: {'✅ 通过' if consistency['consistent'] else '❌ 失败'}")
        
        if not consistency['consistent']:
            print(f"详细信息: {consistency}")
        
        return {
            'global_stats': {
                'total': global_stats.total,
                'pending': global_stats.pending,
                'accepted': global_stats.accepted,
                'rejected': global_stats.rejected
            },
            'rejection_stats': {
                'ad': rejection_stats.ad,
                'duplicate': rejection_stats.duplicate,
                'chat': rejection_stats.chat,
                'other': rejection_stats.other
            },
            'consistency': consistency
        }


async def main():
    parser = argparse.ArgumentParser(description='Linus式统计系统数据迁移工具')
    parser.add_argument('--dry-run', action='store_true', help='预览迁移（不修改数据）')
    parser.add_argument('--migrate', action='store_true', help='执行实际迁移')
    parser.add_argument('--validate', action='store_true', help='验证迁移结果')
    parser.add_argument('--analyze', action='store_true', help='分析现有数据')
    
    args = parser.parse_args()
    
    if not any([args.dry_run, args.migrate, args.validate, args.analyze]):
        parser.print_help()
        return
    
    migrator = LinusStatsMigrator()
    
    try:
        if args.analyze:
            print("=" * 60)
            print("📊 数据分析")
            print("=" * 60)
            analysis = await migrator.analyze_existing_data()
            print(f"\n✅ 分析完成")
        
        if args.dry_run:
            print("=" * 60)
            print("🧪 迁移预览")
            print("=" * 60)
            preview = await migrator.dry_run_migration()
            print(f"\n✅ 预览完成")
        
        if args.migrate:
            print("=" * 60)
            print("🚀 执行迁移")
            print("=" * 60)
            
            # 确认操作
            confirm = input("\n⚠️  这将修改现有统计数据，是否继续？(y/N): ")
            if confirm.lower() != 'y':
                print("❌ 迁移已取消")
                return
            
            result = await migrator.execute_migration()
            print(f"\n✅ 迁移完成")
        
        if args.validate:
            print("=" * 60)
            print("✅ 验证数据")
            print("=" * 60)
            validation = await migrator.validate_migration()
            print(f"\n✅ 验证完成")
            
    except KeyboardInterrupt:
        print("\n\n⏸️  用户中断操作")
    except Exception as e:
        print(f"\n❌ 执行失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())