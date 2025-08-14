#!/usr/bin/env python3
"""
从数据库中已过滤的消息收集尾部样本
"""

import asyncio
import json
from datetime import datetime
from sqlalchemy import select, and_, func
from app.core.database import AsyncSessionLocal, Message
from app.core.training_config import TrainingDataConfig

async def collect_tail_samples():
    """从数据库收集所有已过滤消息的尾部样本"""
    
    async with AsyncSessionLocal() as db:
        # 查询所有已过滤的消息（filtered_content != content）
        query = select(Message).where(
            and_(
                Message.content.isnot(None),
                Message.filtered_content.isnot(None),
                Message.content != Message.filtered_content
            )
        )
        
        result = await db.execute(query)
        messages = result.scalars().all()
        
        print(f"找到 {len(messages)} 条已过滤的消息")
        
        # 读取现有样本
        tail_file = TrainingDataConfig.TAIL_FILTER_SAMPLES_FILE
        with open(tail_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            existing_samples = data.get('samples', [])
        
        # 现有的尾部内容（用于去重）
        existing_tails = {s.get('tail_part', '').strip() for s in existing_samples if s.get('tail_part')}
        print(f"现有样本: {len(existing_samples)} 个")
        
        # 收集新的尾部样本
        new_samples = []
        sample_id = len(existing_samples) + 1
        
        for msg in messages:
            # 计算尾部内容
            original = msg.content
            filtered = msg.filtered_content
            
            # 找到差异部分（尾部）
            if len(filtered) < len(original):
                # 简单方法：假设尾部是从filtered结束位置到original结束
                tail_content = original[len(filtered):].strip()
                
                # 更精确的方法：找到最后的共同部分
                if not tail_content or len(tail_content) < 10:
                    # 尝试从末尾匹配
                    for i in range(len(original) - 1, 0, -1):
                        if original[:i] == filtered:
                            tail_content = original[i:].strip()
                            break
                
                # 如果找到有效的尾部内容
                if tail_content and len(tail_content) >= 20 and tail_content not in existing_tails:
                    new_samples.append({
                        "id": sample_id,
                        "tail_part": tail_content,
                        "created_at": datetime.now().isoformat(),
                        "message_id": msg.id,
                        "source": "database_collection"
                    })
                    existing_tails.add(tail_content)
                    sample_id += 1
                    
                    if len(new_samples) <= 5:
                        print(f"  样本 {sample_id-1}: {tail_content[:50]}...")
        
        print(f"\n发现 {len(new_samples)} 个新的尾部样本")
        
        if new_samples:
            # 合并并保存
            all_samples = existing_samples + new_samples
            
            with open(tail_file, 'w', encoding='utf-8') as f:
                json.dump({"samples": all_samples}, f, ensure_ascii=False, indent=2)
            
            print(f"✅ 成功保存，总样本数: {len(all_samples)}")
            
            # 显示统计
            print(f"\n📊 样本来源统计:")
            manual_count = sum(1 for s in all_samples if 'source' not in s or s.get('source') == 'manual')
            batch_count = sum(1 for s in all_samples if s.get('source') == 'batch_filter_learning')
            db_count = sum(1 for s in all_samples if s.get('source') == 'database_collection')
            
            print(f"  • 手动添加: {manual_count} 个")
            print(f"  • 批量学习: {batch_count} 个")
            print(f"  • 数据库收集: {db_count} 个")
        else:
            print("✅ 没有发现新的尾部样本")
        
        return len(all_samples) if new_samples else len(existing_samples)

if __name__ == "__main__":
    total = asyncio.run(collect_tail_samples())
    print(f"\n最终样本总数: {total}")