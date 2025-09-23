#!/usr/bin/env python3
"""
持续监控重复消息检测情况
实时显示去重系统运行状态

Author: Claude
Created: 2025-09-23
"""

import sys
import time
import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.storage.redis_manager import redis_manager

def monitor_duplicates():
    """持续监控重复消息"""
    print("🔍 开始监控重复消息检测系统")
    print("=" * 70)

    last_check_time = datetime.now()
    duplicate_cases = []
    stats = defaultdict(int)

    try:
        while True:
            # 获取所有消息
            message_keys = redis_manager.client.keys("message:*")
            total_messages = len(message_keys)

            # 获取SimHash索引数量
            simhash_keys = redis_manager.client.keys("dup:simhash:*")
            simhash_count = len(simhash_keys)

            # 统计重复消息
            duplicates_found = 0
            new_duplicates = []

            for key in message_keys:
                try:
                    message_data = redis_manager.client.hget(key, "data")
                    if message_data:
                        message = json.loads(message_data)
                        if message.get('is_duplicate'):
                            duplicates_found += 1
                            original_id = message.get('original_message_id')

                            # 记录新发现的重复
                            duplicate_key = f"{key} -> {original_id}"
                            if duplicate_key not in duplicate_cases:
                                duplicate_cases.append(duplicate_key)
                                new_duplicates.append({
                                    'duplicate_id': key.replace('message:', ''),
                                    'original_id': original_id,
                                    'similarity': message.get('similarity_score', 0),
                                    'time': datetime.now().strftime("%H:%M:%S")
                                })
                except:
                    continue

            # 显示实时状态
            current_time = datetime.now()
            elapsed = (current_time - last_check_time).total_seconds()

            print(f"\r⏰ {current_time.strftime('%H:%M:%S')} | "
                  f"📊 消息总数: {total_messages} | "
                  f"🔗 SimHash索引: {simhash_count} | "
                  f"♻️ 重复消息: {duplicates_found}", end="")

            # 如果发现新的重复消息，详细显示
            if new_duplicates:
                print("\n" + "=" * 70)
                print("🎯 发现新的重复消息:")
                for dup in new_duplicates:
                    print(f"  [{dup['time']}] {dup['duplicate_id']} → {dup['original_id']} "
                          f"(相似度: {dup['similarity']:.2f})")
                print("=" * 70)

            # 每30秒显示一次统计
            if elapsed > 30:
                print(f"\n\n📈 统计汇总 ({current_time.strftime('%H:%M:%S')}):")
                print(f"  • 总消息数: {total_messages}")
                print(f"  • SimHash索引数: {simhash_count}")
                print(f"  • 发现重复: {duplicates_found}")
                print(f"  • 重复率: {duplicates_found/max(total_messages,1)*100:.2f}%")
                print(f"  • 累计发现重复对: {len(duplicate_cases)}")
                print("-" * 70)
                last_check_time = current_time

            # 统计
            stats['total_checks'] += 1
            stats['max_messages'] = max(stats['max_messages'], total_messages)
            stats['max_duplicates'] = max(stats['max_duplicates'], duplicates_found)

            # 每2秒检查一次
            time.sleep(2)

    except KeyboardInterrupt:
        print("\n\n🛑 监控结束")
        print("=" * 70)
        print("📊 最终统计:")
        print(f"  • 检查次数: {stats['total_checks']}")
        print(f"  • 最大消息数: {stats['max_messages']}")
        print(f"  • 最大重复数: {stats['max_duplicates']}")
        print(f"  • 发现的重复对总数: {len(duplicate_cases)}")

        if duplicate_cases:
            print("\n🔍 所有发现的重复消息:")
            for case in duplicate_cases[-10:]:  # 显示最后10个
                print(f"  • {case}")
            if len(duplicate_cases) > 10:
                print(f"  ... 还有 {len(duplicate_cases) - 10} 个重复对")

if __name__ == "__main__":
    monitor_duplicates()