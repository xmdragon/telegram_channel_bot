#!/usr/bin/env python3
"""
从Redis存储中已过滤的消息收集尾部样本
"""

import asyncio
import json
import os
import sys
from datetime import datetime
sys.path.append('/Users/eric/workspace/telegram_channel_bot')

from app.storage.redis_store import init_redis_stores, get_redis_message_store
from app.core.training_config import TrainingDataConfig

async def collect_tail_samples():
    """从Redis存储收集所有已过滤消息的尾部样本"""
    
    try:
        # 初始化Redis存储
        redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
        if not init_redis_stores(redis_url):
            print("❌ Redis连接失败")
            return 0
        
        store = get_redis_message_store()
        
        # 获取所有消息（限制数量避免内存过载）
        print("🔍 正在获取所有消息...")
        all_messages = store.get_all_messages(limit=2000)  # 限制2000条消息
        
        if not all_messages:
            print("⚠️ 未找到任何消息")
            return 0
        
        print(f"📋 获取到 {len(all_messages)} 条消息")
        
        # 筛选已过滤的消息（filtered_content != content）
        filtered_messages = []
        for msg in all_messages:
            content = msg.get('content', '')
            filtered_content = msg.get('filtered_content', '')
            
            if content and filtered_content and content != filtered_content:
                filtered_messages.append(msg)
        
        print(f"🔍 找到 {len(filtered_messages)} 条已过滤的消息")
        
        if not filtered_messages:
            print("⚠️ 未找到已过滤的消息")
            return 0
        
        # 读取现有样本
        tail_file = TrainingDataConfig.TAIL_FILTER_SAMPLES_FILE
        
        existing_samples = []
        if os.path.exists(tail_file):
            try:
                with open(tail_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    existing_samples = data.get('samples', [])
            except (FileNotFoundError, json.JSONDecodeError) as e:
                print(f"⚠️ 读取现有样本文件失败: {e}")
                existing_samples = []
        
        # 现有的尾部内容（用于去重）
        existing_tails = {s.get('tail_part', '').strip() for s in existing_samples if s.get('tail_part')}
        print(f"📚 现有样本: {len(existing_samples)} 个")
        
        # 收集新的尾部样本
        new_samples = []
        sample_id = len(existing_samples) + 1
        
        print("🔄 正在分析消息并提取尾部样本...")
        
        for i, msg in enumerate(filtered_messages):
            if i % 100 == 0:
                print(f"   处理进度: {i}/{len(filtered_messages)}")
            
            # 计算尾部内容
            original = msg.get('content', '')
            filtered = msg.get('filtered_content', '')
            
            # 找到差异部分（尾部）
            if len(filtered) < len(original):
                tail_content = ""
                
                # 方法1：假设尾部是从filtered结束位置到original结束
                if original.startswith(filtered):
                    tail_content = original[len(filtered):].strip()
                else:
                    # 方法2：尝试从末尾匹配找到最后的共同部分
                    for j in range(min(len(original), len(filtered)), 0, -1):
                        if original[:j] == filtered[:j]:
                            # 找到最长的共同前缀
                            tail_content = original[j:].strip()
                            break
                    
                    # 如果还是找不到，尝试从末尾往前找
                    if not tail_content:
                        for j in range(len(original) - 1, 0, -1):
                            if original[:j] in filtered:
                                tail_content = original[j:].strip()
                                break
                
                # 如果找到有效的尾部内容
                if (tail_content and 
                    len(tail_content) >= 15 and  # 至少15字符
                    len(tail_content) <= 1000 and  # 不超过1000字符
                    tail_content not in existing_tails):
                    
                    # 简单验证是否可能是尾部推广内容
                    tail_keywords = ["@", "订阅", "投稿", "加入", "关注", "群组", "频道", 
                                   "联系", "推广", "👌", "📣", "🎯", "💰", "🔥"]
                    has_keywords = any(keyword in tail_content for keyword in tail_keywords)
                    
                    if has_keywords or len(tail_content) > 50:  # 有关键词或内容较长
                        new_samples.append({
                            "id": sample_id,
                            "tail_part": tail_content,
                            "created_at": datetime.now().isoformat(),
                            "message_id": msg.get('message_id'),
                            "channel_id": msg.get('channel_id'),
                            "source": "redis_collection",
                            "original_length": len(original),
                            "filtered_length": len(filtered),
                            "tail_length": len(tail_content)
                        })
                        existing_tails.add(tail_content)
                        sample_id += 1
                        
                        # 显示前几个样本的预览
                        if len(new_samples) <= 5:
                            preview = tail_content[:50].replace('\n', ' ')
                            print(f"  📝 样本 {sample_id-1}: {preview}...")
        
        print(f"\n✅ 发现 {len(new_samples)} 个新的尾部样本")
        
        if new_samples:
            # 合并并保存
            all_samples = existing_samples + new_samples
            
            # 确保目录存在
            os.makedirs(os.path.dirname(tail_file), exist_ok=True)
            
            try:
                with open(tail_file, 'w', encoding='utf-8') as f:
                    json.dump({
                        "samples": all_samples,
                        "last_updated": datetime.now().isoformat(),
                        "total_count": len(all_samples)
                    }, f, ensure_ascii=False, indent=2)
                
                print(f"💾 成功保存到文件: {tail_file}")
                print(f"📊 总样本数: {len(all_samples)}")
                
                # 显示统计
                print(f"\n📈 样本来源统计:")
                source_stats = {}
                for sample in all_samples:
                    source = sample.get('source', 'manual')
                    source_stats[source] = source_stats.get(source, 0) + 1
                
                for source, count in source_stats.items():
                    source_name = {
                        'manual': '手动添加',
                        'batch_filter_learning': '批量学习',
                        'redis_collection': 'Redis收集',
                        'database_collection': '数据库收集'
                    }.get(source, source)
                    print(f"  • {source_name}: {count} 个")
                
                # 显示样本长度统计
                lengths = [len(s.get('tail_part', '')) for s in all_samples]
                if lengths:
                    print(f"\n📏 尾部长度统计:")
                    print(f"  • 最短: {min(lengths)} 字符")
                    print(f"  • 最长: {max(lengths)} 字符")
                    print(f"  • 平均: {sum(lengths)/len(lengths):.1f} 字符")
                
                return len(all_samples)
                
            except Exception as e:
                print(f"❌ 保存文件失败: {e}")
                return len(existing_samples)
        else:
            print("✅ 没有发现新的尾部样本")
            return len(existing_samples)
            
    except Exception as e:
        print(f"❌ 收集样本失败: {e}")
        import traceback
        traceback.print_exc()
        return 0

async def show_samples_stats():
    """显示现有样本统计"""
    try:
        tail_file = TrainingDataConfig.TAIL_FILTER_SAMPLES_FILE
        
        if not os.path.exists(tail_file):
            print(f"⚠️ 样本文件不存在: {tail_file}")
            return
        
        with open(tail_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            samples = data.get('samples', [])
        
        print(f"📋 尾部样本文件统计:")
        print(f"文件路径: {tail_file}")
        print(f"样本总数: {len(samples)}")
        
        if not samples:
            print("⚠️ 样本文件为空")
            return
        
        # 来源统计
        source_stats = {}
        for sample in samples:
            source = sample.get('source', 'manual')
            source_stats[source] = source_stats.get(source, 0) + 1
        
        print(f"\n📈 来源分布:")
        for source, count in source_stats.items():
            source_name = {
                'manual': '手动添加',
                'batch_filter_learning': '批量学习',
                'redis_collection': 'Redis收集',
                'database_collection': '数据库收集'
            }.get(source, source)
            print(f"  • {source_name}: {count} 个")
        
        # 长度统计
        lengths = [len(s.get('tail_part', '')) for s in samples]
        if lengths:
            print(f"\n📏 长度统计:")
            print(f"  • 最短: {min(lengths)} 字符")
            print(f"  • 最长: {max(lengths)} 字符")
            print(f"  • 平均: {sum(lengths)/len(lengths):.1f} 字符")
        
        # 显示最新的几个样本
        print(f"\n📝 最新的5个样本:")
        recent_samples = sorted(samples, key=lambda x: x.get('created_at', ''), reverse=True)[:5]
        for i, sample in enumerate(recent_samples, 1):
            tail = sample.get('tail_part', '')
            preview = tail[:50].replace('\n', ' ')
            source = sample.get('source', 'manual')
            print(f"  {i}. [{source}] {preview}...")
    
    except Exception as e:
        print(f"❌ 显示统计失败: {e}")

async def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='收集尾部样本工具')
    parser.add_argument('--stats', action='store_true', help='显示现有样本统计')
    parser.add_argument('--collect', action='store_true', help='收集新样本')
    
    args = parser.parse_args()
    
    if args.stats:
        await show_samples_stats()
    elif args.collect or len(sys.argv) == 1:  # 默认行为
        total = await collect_tail_samples()
        print(f"\n🎯 最终样本总数: {total}")
    else:
        parser.print_help()

if __name__ == "__main__":
    asyncio.run(main())