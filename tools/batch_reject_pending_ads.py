#!/usr/bin/env python3
"""
批量拒绝所有pending状态的广告消息
用于修复历史遗留问题
"""
import json
import redis
import sys
from datetime import datetime

def main():
    try:
        # 连接Redis
        r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

        # 获取所有消息
        all_messages = r.keys("message:*")
        pending_ads = []
        total_pending = 0
        total_ads = 0

        print("扫描所有消息...")
        for key in all_messages:
            data = r.hget(key, "data")
            if data:
                msg = json.loads(data)
                if msg.get('status') == 'pending':
                    total_pending += 1
                    if msg.get('is_ad') == 'True':
                        total_ads += 1
                        pending_ads.append({
                            'key': key,
                            'id': f"{msg.get('source_channel')}:{msg.get('message_id')}",
                            'weight': msg.get('ad_weight'),
                            'created': msg.get('created_at')
                        })

        print(f"\n发现 {total_ads} 条被标记为广告但仍在pending状态的消息")
        print(f"（共 {total_pending} 条pending消息）")

        if total_ads == 0:
            print("没有需要处理的消息")
            return

        # 显示前10条
        print("\n前10条将被拒绝的消息:")
        for i, ad in enumerate(pending_ads[:10], 1):
            print(f"  {i}. {ad['id']} - 权重:{ad['weight']} - {ad['created'][:10]}")

        if len(pending_ads) > 10:
            print(f"  ... 还有 {len(pending_ads) - 10} 条")

        # 确认操作
        response = input(f"\n确定要将这 {total_ads} 条广告消息标记为rejected吗？(yes/no): ")
        if response.lower() != 'yes':
            print("操作已取消")
            return

        # 批量更新
        success_count = 0
        failed_count = 0

        for ad in pending_ads:
            try:
                # 获取完整消息数据
                msg_data = r.hget(ad['key'], "data")
                if msg_data:
                    msg = json.loads(msg_data)

                    # 更新状态
                    msg['status'] = 'rejected'
                    msg['reject_reason'] = f'批量清理：自动拒绝广告(权重:{ad["weight"]})'
                    msg['updated_at'] = datetime.now().isoformat()

                    # 保存回Redis
                    r.hset(ad['key'], "data", json.dumps(msg, ensure_ascii=False))

                    # 更新索引
                    msg_key = ad['key']
                    channel_id = msg.get('source_channel')
                    message_id = msg.get('message_id')

                    # 从pending集合移除
                    r.srem('messages:status:pending', msg_key)
                    # 添加到rejected集合
                    r.sadd('messages:status:rejected', msg_key)

                    success_count += 1

                    if success_count % 10 == 0:
                        print(f"  已处理 {success_count} 条...")

            except Exception as e:
                print(f"  处理 {ad['id']} 时出错: {e}")
                failed_count += 1

        print(f"\n处理完成:")
        print(f"  成功: {success_count} 条")
        print(f"  失败: {failed_count} 条")

        # 验证结果
        print("\n验证结果...")
        remaining = 0
        for key in all_messages[:100]:  # 只验证前100条
            data = r.hget(key, "data")
            if data:
                msg = json.loads(data)
                if msg.get('status') == 'pending' and msg.get('is_ad') == 'True':
                    remaining += 1

        if remaining == 0:
            print("✅ 所有广告消息已成功从pending状态移除")
        else:
            print(f"⚠️ 仍有 {remaining} 条广告消息在pending状态")

    except Exception as e:
        print(f"错误: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()