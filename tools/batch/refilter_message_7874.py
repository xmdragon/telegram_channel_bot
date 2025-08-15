#!/usr/bin/env python3
"""
重新过滤消息的工具脚本（通用版本）
"""
import asyncio
import logging
from pathlib import Path
import sys
import os

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

from app.storage.redis_store import init_redis_stores, get_redis_message_store
from app.services.content_filter import ContentFilter

async def refilter_message(message_id: str = None):
    """重新过滤指定消息"""
    try:
        # 初始化Redis存储
        redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
        if not init_redis_stores(redis_url):
            logger.error("❌ Redis连接失败")
            return
        
        store = get_redis_message_store()
        
        # 默认消息ID，如果未提供参数
        if not message_id:
            message_id = "7874"  # 保持向后兼容
        
        # 解析消息ID
        if ':' in str(message_id):
            channel_id, msg_id = str(message_id).split(':', 1)
            msg_id = int(msg_id)
        else:
            # 搜索所有频道中的消息
            msg_id = int(message_id)
            channel_id = None
            
            # 尝试从所有消息中查找
            all_messages = store.get_all_messages(limit=1000)
            target_msg = None
            for msg in all_messages:
                if msg.get('message_id') == msg_id:
                    target_msg = msg
                    channel_id = msg.get('channel_id')
                    break
            
            if not target_msg:
                logger.error(f"❌ 未找到消息 #{msg_id}")
                return
        
        # 获取消息数据
        msg_data = store.get_message(channel_id, msg_id)
        
        if not msg_data:
            logger.error(f"❌ 未找到消息 {channel_id}:{msg_id}")
            return
        
        logger.info(f"✅ 找到消息 {channel_id}:{msg_id}")
        logger.info(f"源频道: {channel_id}")
        logger.info(f"创建时间: {msg_data.get('created_at', '未知')}")
        
        # 显示原始内容
        print("\n" + "="*60)
        print("原始内容:")
        print("-"*60)
        content = msg_data.get('content', '')
        print(content if content else "[无内容]")
        
        # 显示当前过滤后内容
        print("\n" + "="*60)
        print("当前过滤后内容:")
        print("-"*60)
        filtered_content = msg_data.get('filtered_content', '')
        print(filtered_content if filtered_content else "[无内容]")
        
        # 重新过滤
        logger.info("\n🔄 正在重新过滤...")
        
        # 创建内容过滤器
        content_filter = ContentFilter()
        
        # 准备媒体文件列表（如果有）
        media_files = []
        media_url = msg_data.get('media_url')
        if media_url and Path(media_url).exists():
            media_files.append(media_url)
        
        # 执行过滤
        is_ad, new_filtered_content, filter_reason, ocr_result = await content_filter.filter_message(
            content,
            channel_id=channel_id,
            media_files=media_files
        )
        
        # 显示新的过滤结果
        print("\n" + "="*60)
        print("重新过滤后的内容:")
        print("-"*60)
        print(new_filtered_content if new_filtered_content else "[无内容]")
        
        # 比较结果
        print("\n" + "="*60)
        print("过滤结果对比:")
        content_len = len(content) if content else 0
        old_filtered_len = len(filtered_content) if filtered_content else 0
        new_filtered_len = len(new_filtered_content) if new_filtered_content else 0
        
        print(f"原始长度: {content_len} 字符")
        print(f"之前过滤后: {old_filtered_len} 字符")
        print(f"重新过滤后: {new_filtered_len} 字符")
        
        if content_len > 0:
            old_removed = content_len - old_filtered_len
            new_removed = content_len - new_filtered_len
            print(f"之前过滤掉: {old_removed} 字符 ({old_removed/content_len*100:.1f}%)")
            print(f"现在过滤掉: {new_removed} 字符 ({new_removed/content_len*100:.1f}%)")
        
        print(f"\n📊 广告检测: {is_ad}")
        if filter_reason:
            print(f"过滤原因: {filter_reason}")
        
        # 询问是否更新
        print("\n" + "="*60)
        try:
            response = input("是否更新Redis存储中的过滤后内容？(y/n): ")
        except EOFError:
            # 非交互环境，默认更新
            response = 'y'
            print("非交互环境，自动更新")
        
        if response.lower() == 'y':
            # 更新消息数据
            msg_data['filtered_content'] = new_filtered_content
            msg_data['is_ad'] = is_ad
            
            success = store.save_message(channel_id, msg_id, msg_data)
            
            if success:
                logger.info("✅ 已更新消息的过滤后内容")
            else:
                logger.error("❌ 更新失败")
        else:
            logger.info("⚠️ 未更新消息内容")
            
    except Exception as e:
        logger.error(f"❌ 处理失败: {e}")
        import traceback
        traceback.print_exc()

async def main():
    """主函数"""
    message_id = None
    if len(sys.argv) > 1:
        message_id = sys.argv[1]
    
    await refilter_message(message_id)

if __name__ == "__main__":
    asyncio.run(main())