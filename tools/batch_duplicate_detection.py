#!/usr/bin/env python3
"""
批量去重检测工具
功能：
1. 重置去重缓存
2. 对所有现有消息进行去重检测并更新标记

Author: Claude
Created: 2025-09-23
"""

import sys
import os
import json
import redis
import asyncio
import time
from datetime import datetime
from typing import Dict, List, Tuple, Any

# 添加项目路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.duplicate_detector import duplicate_detector
from app.core.logging_config import setup_logging, get_logger

# 初始化日志
setup_logging(service_name="batch_duplicate", log_level="INFO", console_output=True)
logger = get_logger(__name__)


class BatchDuplicateDetector:
    """批量去重检测器"""

    def __init__(self):
        self.redis_client = redis.Redis(
            host='localhost',
            port=6379,
            db=0,
            decode_responses=True
        )
        self.processed_count = 0
        self.duplicate_count = 0
        self.error_count = 0
        self.start_time = None

    def reset_duplicate_cache(self) -> int:
        """重置去重缓存"""
        print("\n[1/2] 清理去重缓存...")

        # 查找所有去重相关的键
        dup_keys = []
        for pattern in ['dup:simhash:*', 'dup:content:*', 'dup:*']:
            keys = self.redis_client.keys(pattern)
            dup_keys.extend(keys)

        # 去重（避免重复删除）
        dup_keys = list(set(dup_keys))

        # 批量删除
        deleted_count = 0
        if dup_keys:
            # 分批删除，每批100个
            for i in range(0, len(dup_keys), 100):
                batch = dup_keys[i:i+100]
                deleted = self.redis_client.delete(*batch)
                deleted_count += deleted

        print(f"✅ 已清理 {deleted_count} 个缓存键")
        return deleted_count

    def get_all_messages(self) -> List[Tuple[str, Dict[str, Any]]]:
        """获取所有消息并按时间排序"""
        print("\n[2/2] 批量去重检测...")

        # 获取所有消息键
        message_keys = self.redis_client.keys('message:*')
        print(f"总消息数: {len(message_keys)}")

        if not message_keys:
            return []

        # 获取消息数据
        messages = []
        for key in message_keys:
            try:
                # 获取消息数据（存储在data字段中）
                data_json = self.redis_client.hget(key, 'data')
                if data_json:
                    data = json.loads(data_json)
                    # 添加Redis键名用于后续更新
                    messages.append((key, data))
            except Exception as e:
                logger.error(f"读取消息失败 {key}: {e}")
                continue

        # 按创建时间排序（早的在前）
        messages.sort(key=lambda x: x[1].get('created_at', ''))

        return messages

    async def process_message(self, redis_key: str, message_data: Dict[str, Any]) -> bool:
        """
        处理单个消息的去重检测

        Args:
            redis_key: Redis中的键名 (如 "message:-1001234:5678")
            message_data: 消息数据字典

        Returns:
            是否检测到重复
        """
        try:
            # 获取消息内容
            content = message_data.get('filtered_content') or message_data.get('content')

            # 跳过空内容或太短的内容
            if not content or len(content.strip()) < 10:
                message_data['duplicate_status'] = 'none'
                message_data['similarity_score'] = 0.0
                return False

            # 构建消息ID（从Redis键提取）
            # redis_key 格式: "message:channel_id:message_id"
            parts = redis_key.split(':')
            if len(parts) >= 3:
                channel_id = parts[1]
                message_id = parts[2]
                full_message_id = f"{channel_id}:{message_id}"
            else:
                full_message_id = redis_key

            # 执行去重检测
            duplicate_result = await duplicate_detector.detect_duplicate(
                content,
                full_message_id
            )

            # 更新消息数据
            if duplicate_result.is_duplicate:
                message_data['duplicate_status'] = 'suspected'
                message_data['original_message_id'] = duplicate_result.original_message_id
                message_data['similarity_score'] = duplicate_result.similarity_score
                message_data['duplicate_reason'] = duplicate_result.detection_reason

                # 记录发现的重复
                print(f"  🔍 发现重复！原消息: {duplicate_result.original_message_id}, 相似度: {duplicate_result.similarity_score:.3f}")
                return True
            else:
                message_data['duplicate_status'] = 'none'
                message_data['similarity_score'] = 0.0
                message_data['original_message_id'] = None
                message_data['duplicate_reason'] = None
                return False

        except Exception as e:
            logger.error(f"处理消息失败 {redis_key}: {e}")
            # 出错时设置为none
            message_data['duplicate_status'] = 'none'
            message_data['similarity_score'] = 0.0
            return False

    def save_message_back(self, redis_key: str, message_data: Dict[str, Any]) -> bool:
        """
        将更新后的消息保存回Redis

        Args:
            redis_key: Redis中的键名
            message_data: 更新后的消息数据

        Returns:
            是否保存成功
        """
        try:
            # 将消息数据序列化为JSON
            data_json = json.dumps(message_data, ensure_ascii=False)

            # 更新Redis中的data字段
            self.redis_client.hset(redis_key, 'data', data_json)

            # 更新时间戳
            self.redis_client.hset(redis_key, 'updated_at', datetime.now().isoformat())

            return True
        except Exception as e:
            logger.error(f"保存消息失败 {redis_key}: {e}")
            return False

    async def run(self):
        """运行批量去重检测"""
        print("=" * 50)
        print("批量去重检测工具")
        print("=" * 50)

        self.start_time = time.time()

        # 步骤1：重置缓存
        self.reset_duplicate_cache()

        # 步骤2：获取所有消息
        messages = self.get_all_messages()

        if not messages:
            print("没有找到消息，退出")
            return

        total = len(messages)
        print(f"开始处理 {total} 条消息...")
        print("-" * 50)

        # 步骤3：批量处理
        for idx, (redis_key, message_data) in enumerate(messages, 1):
            # 显示进度
            if idx % 10 == 0 or idx == 1:
                progress = (idx / total) * 100
                print(f"[{idx}/{total}] {progress:.1f}% - 处理消息 {redis_key}...", end="")

            # 处理消息
            is_duplicate = await self.process_message(redis_key, message_data)

            if is_duplicate:
                self.duplicate_count += 1

            # 保存回Redis
            if self.save_message_back(redis_key, message_data):
                self.processed_count += 1
                if idx % 10 == 0 or idx == 1:
                    if not is_duplicate:
                        print(" ✓")
            else:
                self.error_count += 1
                if idx % 10 == 0 or idx == 1:
                    print(" ✗")

        # 统计结果
        elapsed = time.time() - self.start_time
        print("\n" + "=" * 50)
        print("🎉 检测完成")
        print("=" * 50)
        print(f"总处理: {self.processed_count} 条")
        print(f"发现重复: {self.duplicate_count} 条")
        print(f"处理失败: {self.error_count} 条")
        print(f"耗时: {elapsed:.1f} 秒")

        if self.duplicate_count > 0:
            print(f"\n💡 提示: 发现 {self.duplicate_count} 条重复消息，已标记为 'suspected' 状态")
            print("  可以在前端界面查看并进行人工确认")


async def main():
    """主函数"""
    detector = BatchDuplicateDetector()
    await detector.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️ 用户中断操作")
    except Exception as e:
        print(f"\n❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()