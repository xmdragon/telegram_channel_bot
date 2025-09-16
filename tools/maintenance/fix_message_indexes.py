#!/usr/bin/env python3
"""
索引修复脚本 - 消除所有特殊情况

按照Linus Torvalds的"好品味"原则：
1. 强制所有消息必须有有效status字段
2. 清理并重建所有索引，确保100%一致性
3. 用最简单直接的方式解决问题

Author: Linus Torvalds (当然是开玩笑的)
Date: 2025-09-08
"""

import sys
import os
import time
from typing import Dict, Any, List, Set
import redis
import json
import logging
from datetime import datetime

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.storage.redis_manager import RedisManager

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

class MessageIndexFixer:
    """消息索引修复器"""
    
    def __init__(self, dry_run: bool = True):
        self.redis_manager = RedisManager()
        self.dry_run = dry_run
        self.stats = {
            'total_messages': 0,
            'fixed_messages': 0,
            'invalid_messages': 0,
            'rebuilt_indexes': 0,
            'errors': []
        }
        
    def analyze_current_state(self) -> Dict[str, Any]:
        """分析当前数据状态 - 设计原则：先了解问题"""
        logger.info("🔍 开始分析当前数据状态...")
        
        try:
            # 获取所有消息键
            message_keys = self.redis_manager.client.keys("message:*")
            logger.info(f"找到 {len(message_keys)} 条消息")
            
            # 统计状态分布
            status_counts = {'pending': 0, 'approved': 0, 'rejected': 0, 'unknown': 0, 'missing': 0}
            index_counts = {}
            
            # 检查消息状态
            for key in message_keys:
                try:
                    key_str = key.decode() if isinstance(key, bytes) else key
                    channel_id, message_id = key_str.replace("message:", "").rsplit(":", 1)
                    
                    message_data = self.redis_manager.get_message(channel_id, int(message_id), silent=True)
                    if message_data:
                        status = message_data.get('status')
                        if status in ['pending', 'approved', 'rejected']:
                            status_counts[status] += 1
                        elif status is None:
                            status_counts['missing'] += 1
                        else:
                            status_counts['unknown'] += 1
                            logger.warning(f"发现未知状态 '{status}': {channel_id}:{message_id}")
                            
                except Exception as e:
                    logger.error(f"分析消息失败 {key}: {e}")
                    self.stats['errors'].append(f"分析消息失败 {key}: {e}")
            
            # 检查索引状态
            for status in ['pending', 'approved', 'rejected']:
                index_key = f"index:msg:{status}"
                count = self.redis_manager.client.zcard(index_key)
                index_counts[status] = count
                
            self.stats['total_messages'] = len(message_keys)
            
            analysis = {
                'message_counts': status_counts,
                'index_counts': index_counts,
                'total_messages': len(message_keys),
                'inconsistencies': []
            }
            
            # 检查一致性问题
            for status in ['pending', 'approved', 'rejected']:
                if status_counts[status] != index_counts[status]:
                    inconsistency = f"状态 {status}: 消息{status_counts[status]}条 vs 索引{index_counts[status]}条"
                    analysis['inconsistencies'].append(inconsistency)
                    logger.warning(f"❌ 发现不一致: {inconsistency}")
            
            logger.info(f"📊 分析结果:")
            logger.info(f"  - 消息状态分布: {status_counts}")  
            logger.info(f"  - 索引统计: {index_counts}")
            logger.info(f"  - 不一致问题: {len(analysis['inconsistencies'])}个")
            
            return analysis
            
        except Exception as e:
            logger.error(f"分析当前状态失败: {e}")
            raise
    
    def fix_message_statuses(self) -> int:
        """修复所有消息的status字段 - 设计原则：强制数据完整性"""
        logger.info("🔧 开始修复消息status字段...")
        
        fixed_count = 0
        message_keys = self.redis_manager.client.keys("message:*")
        
        for key in message_keys:
            try:
                key_str = key.decode() if isinstance(key, bytes) else key
                channel_id, message_id = key_str.replace("message:", "").rsplit(":", 1)
                
                message_data = self.redis_manager.get_message(channel_id, int(message_id), silent=True)
                if not message_data:
                    continue
                    
                status = message_data.get('status')
                
                # 设计原则：消除特殊情况，强制所有消息必须有有效status
                if status not in ['pending', 'approved', 'rejected']:
                    if self.dry_run:
                        logger.info(f"[DRY RUN] 将修复: {channel_id}:{message_id} status='{status}' -> 'pending'")
                        fixed_count += 1
                    else:
                        # 强制设置为pending状态
                        message_data['status'] = 'pending'
                        message_data['updated_at'] = datetime.now().isoformat()
                        message_data['fixed_by_tool'] = True  # 标记为工具修复
                        
                        # 直接更新Redis，不通过update_message（避免索引问题）
                        message_key = f"message:{channel_id}:{message_id}"
                        message_json = json.dumps(message_data, ensure_ascii=False, default=str)
                        
                        self.redis_manager.client.hset(message_key, mapping={
                            "data": message_json,
                            "updated_at": datetime.now().isoformat()
                        })
                        
                        logger.info(f"✅ 已修复: {channel_id}:{message_id} status -> 'pending'")
                        fixed_count += 1
                        
            except Exception as e:
                error_msg = f"修复消息status失败 {key}: {e}"
                logger.error(error_msg)
                self.stats['errors'].append(error_msg)
        
        self.stats['fixed_messages'] = fixed_count
        logger.info(f"🎯 status字段修复完成: {fixed_count}条消息")
        return fixed_count
    
    def rebuild_all_indexes(self) -> int:
        """重建所有状态索引 - 设计原则：从零开始，确保正确性"""
        logger.info("🏗️ 开始重建所有状态索引...")
        
        # 1. 清空所有现有索引
        for status in ['pending', 'approved', 'rejected']:
            index_key = f"index:msg:{status}"
            if not self.dry_run:
                deleted_count = self.redis_manager.client.delete(index_key)
                logger.info(f"🗑️ 清空索引 {index_key}: {deleted_count}个")
            else:
                count = self.redis_manager.client.zcard(index_key)
                logger.info(f"[DRY RUN] 将清空索引 {index_key}: {count}个条目")
        
        # 2. 扫描所有消息，重建索引
        message_keys = self.redis_manager.client.keys("message:*")
        rebuilt_count = 0
        current_time = time.time()
        
        # 批量重建索引
        if not self.dry_run:
            pipeline = self.redis_manager.client.pipeline()
        
        for key in message_keys:
            try:
                key_str = key.decode() if isinstance(key, bytes) else key
                channel_id, message_id = key_str.replace("message:", "").rsplit(":", 1)
                full_message_id = f"{channel_id}:{message_id}"
                
                message_data = self.redis_manager.get_message(channel_id, int(message_id), silent=True)
                if not message_data:
                    continue
                    
                status = message_data.get('status', 'pending')  # 默认pending
                
                if status in ['pending', 'approved', 'rejected']:
                    if self.dry_run:
                        logger.debug(f"[DRY RUN] 将添加到索引 {status}: {full_message_id}")
                    else:
                        index_key = f"index:msg:{status}"
                        pipeline.zadd(index_key, {full_message_id: current_time})
                        
                    rebuilt_count += 1
                    
            except Exception as e:
                error_msg = f"重建索引失败 {key}: {e}"
                logger.error(error_msg)
                self.stats['errors'].append(error_msg)
        
        # 执行批量操作
        if not self.dry_run:
            pipeline.execute()
            
        self.stats['rebuilt_indexes'] = rebuilt_count
        logger.info(f"🎯 索引重建完成: {rebuilt_count}条记录")
        return rebuilt_count
    
    def verify_fix(self) -> Dict[str, Any]:
        """验证修复结果 - 设计原则：验证结果的正确性"""
        logger.info("✅ 开始验证修复结果...")
        
        # 重新分析状态
        final_analysis = self.analyze_current_state()
        
        verification = {
            'all_messages_have_status': True,
            'indexes_consistent': len(final_analysis['inconsistencies']) == 0,
            'final_stats': final_analysis,
            'success': True
        }
        
        # 检查是否还有missing或unknown状态
        message_counts = final_analysis['message_counts']
        if message_counts['missing'] > 0 or message_counts['unknown'] > 0:
            verification['all_messages_have_status'] = False
            verification['success'] = False
            
        if not verification['indexes_consistent']:
            verification['success'] = False
            
        return verification
    
    def run_fix(self) -> Dict[str, Any]:
        """执行完整的修复流程"""
        start_time = time.time()
        logger.info(f"🚀 开始索引修复 (dry_run={self.dry_run})...")
        
        try:
            # 1. 分析当前状态
            initial_analysis = self.analyze_current_state()
            
            # 2. 修复消息status字段
            fixed_messages = self.fix_message_statuses()
            
            # 3. 重建所有索引
            rebuilt_indexes = self.rebuild_all_indexes()
            
            # 4. 验证修复结果
            verification = self.verify_fix()
            
            duration = time.time() - start_time
            
            result = {
                'dry_run': self.dry_run,
                'duration': f"{duration:.2f}s",
                'initial_analysis': initial_analysis,
                'fixed_messages': fixed_messages,
                'rebuilt_indexes': rebuilt_indexes,
                'verification': verification,
                'stats': self.stats,
                'success': verification['success'] and len(self.stats['errors']) == 0
            }
            
            # 输出最终报告
            self._print_final_report(result)
            
            return result
            
        except Exception as e:
            logger.error(f"修复过程失败: {e}")
            return {'success': False, 'error': str(e)}
    
    def _print_final_report(self, result: Dict[str, Any]):
        """输出最终报告"""
        logger.info("="*60)
        logger.info("📋 索引修复 - 最终报告")
        logger.info("="*60)
        
        if result.get('success'):
            logger.info("🎉 修复成功！")
        else:
            logger.error("❌ 修复失败！")
            
        logger.info(f"⏱️  耗时: {result.get('duration', 'N/A')}")
        logger.info(f"📊 修复统计:")
        logger.info(f"  - 总消息数: {self.stats['total_messages']}")
        logger.info(f"  - 修复消息: {self.stats['fixed_messages']}")
        logger.info(f"  - 重建索引: {self.stats['rebuilt_indexes']}")
        logger.info(f"  - 错误数: {len(self.stats['errors'])}")
        
        verification = result.get('verification', {})
        logger.info(f"✅ 验证结果:")
        logger.info(f"  - 所有消息有有效status: {verification.get('all_messages_have_status')}")
        logger.info(f"  - 索引一致性: {verification.get('indexes_consistent')}")
        
        if self.stats['errors']:
            logger.warning(f"⚠️  错误详情:")
            for error in self.stats['errors'][:5]:  # 只显示前5个错误
                logger.warning(f"  - {error}")
            if len(self.stats['errors']) > 5:
                logger.warning(f"  - ... 还有 {len(self.stats['errors']) - 5} 个错误")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="消息索引修复工具")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="只分析不修改（默认）")
    parser.add_argument("--fix", action="store_true",
                        help="执行实际修复（危险操作！）")
    parser.add_argument("--analyze-only", action="store_true",
                        help="只分析当前状态")
    parser.add_argument("--force", action="store_true",
                        help="强制执行修复，跳过确认（危险！）")
    
    args = parser.parse_args()
    
    # 安全检查
    if args.fix:
        if not args.force:
            print("⚠️  警告：您即将执行实际的数据修复操作！")
            print("⚠️  这将修改Redis中的消息数据和索引！")
            print("⚠️  强烈建议先进行数据备份！")
            try:
                confirm = input("确认继续吗？输入 'YES' 继续，其他任何输入将取消: ")
                if confirm != "YES":
                    print("操作已取消")
                    return
            except (EOFError, KeyboardInterrupt):
                print("\n操作已取消")
                return
        else:
            print("🚀 强制执行模式：跳过确认，直接修复")
        dry_run = False
    else:
        dry_run = True
    
    fixer = MessageIndexFixer(dry_run=dry_run)
    
    if args.analyze_only:
        # 只分析不修复
        analysis = fixer.analyze_current_state()
        print("\n" + "="*60)
        print("📊 当前数据状态分析")
        print("="*60)
        print(json.dumps(analysis, indent=2, ensure_ascii=False))
    else:
        # 执行修复
        result = fixer.run_fix()
        
        if not result.get('success'):
            sys.exit(1)


if __name__ == "__main__":
    main()