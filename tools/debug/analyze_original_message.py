#!/usr/bin/env python3
"""
分析原始Telegram消息内容的脚本
专门用于检查消息 https://t.me/feilvbingi/7243 的原始文本内容
"""

import asyncio
import logging
import os
import json
from pathlib import Path
from telethon import TelegramClient
from telethon.tl.types import Message as TLMessage

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('analyze_message.log')
    ]
)
logger = logging.getLogger(__name__)

async def analyze_message_7243():
    """分析消息7243的原始内容"""
    
    # 获取Telegram客户端配置
    try:
        # 从项目配置中获取API配置
        from app.services.config_manager import ConfigManager
        config_manager = ConfigManager()
        
        api_id = await config_manager.get_config('telegram.api_id')
        api_hash = await config_manager.get_config('telegram.api_hash')
        session_string = await config_manager.get_config('telegram.session')
        
        if not api_id or not api_hash or not session_string:
            logger.error("❌ Telegram API配置不完整")
            return
            
    except Exception as e:
        logger.error(f"❌ 获取配置失败: {e}")
        return
    
    client = None
    try:
        # 创建客户端
        client = TelegramClient('analyze_session', int(api_id), api_hash)
        
        # 从session字符串启动
        await client.start(
            phone=lambda: "",  # 空函数，使用session_string
        )
        
        # 使用session字符串
        if session_string:
            await client.session.save()
        
        logger.info("✅ Telegram客户端连接成功")
        
        # 获取指定频道的指定消息
        channel_username = "feilvbingi"  # @feilvbingi
        message_id = 7243
        
        logger.info(f"🔍 正在获取频道 @{channel_username} 的消息 {message_id}")
        
        # 获取频道实体
        try:
            channel_entity = await client.get_entity(f"@{channel_username}")
            logger.info(f"✅ 频道获取成功: {channel_entity.title}")
        except Exception as e:
            logger.error(f"❌ 获取频道失败: {e}")
            return
        
        # 获取指定消息
        try:
            messages = await client.get_messages(channel_entity, ids=[message_id])
            if not messages or not messages[0]:
                logger.error(f"❌ 未找到消息 {message_id}")
                return
            
            message = messages[0]
            logger.info(f"✅ 消息获取成功")
            
        except Exception as e:
            logger.error(f"❌ 获取消息失败: {e}")
            return
        
        # 分析消息的各种文本属性
        analysis_result = {
            "message_id": message.id,
            "date": message.date.isoformat() if message.date else None,
            "from_id": str(message.from_id) if message.from_id else None,
            "peer_id": str(message.peer_id) if message.peer_id else None,
            "media_type": message.media.__class__.__name__ if message.media else None,
            "text_analysis": {}
        }
        
        # 详细分析各种文本属性
        text_attrs = {
            'text': getattr(message, 'text', None),
            'raw_text': getattr(message, 'raw_text', None), 
            'message': getattr(message, 'message', None),
            'caption': getattr(message, 'caption', None) if message.media else None
        }
        
        logger.info("📝 消息文本属性分析:")
        logger.info("=" * 60)
        
        for attr_name, attr_value in text_attrs.items():
            if attr_value is not None:
                analysis_result["text_analysis"][attr_name] = {
                    "length": len(attr_value),
                    "content": attr_value,
                    "contains_asterisks": "*" in attr_value,
                    "asterisk_count": attr_value.count("*"),
                    "asterisk_positions": [i for i, char in enumerate(attr_value) if char == "*"]
                }
                
                logger.info(f"{attr_name.upper()}:")
                logger.info(f"  长度: {len(attr_value)} 字符")
                logger.info(f"  包含星号: {'是' if '*' in attr_value else '否'}")
                if "*" in attr_value:
                    logger.info(f"  星号数量: {attr_value.count('*')}")
                    logger.info(f"  星号位置: {[i for i, char in enumerate(attr_value) if char == '*']}")
                logger.info(f"  内容: {repr(attr_value)}")
                logger.info(f"  显示: {attr_value}")
                logger.info("-" * 40)
            else:
                analysis_result["text_analysis"][attr_name] = None
                logger.info(f"{attr_name.upper()}: None")
        
        # 分析实体信息
        if hasattr(message, 'entities') and message.entities:
            analysis_result["entities"] = []
            logger.info(f"📌 消息实体分析 (共{len(message.entities)}个):")
            logger.info("=" * 60)
            
            for i, entity in enumerate(message.entities):
                entity_info = {
                    "index": i,
                    "type": entity.__class__.__name__,
                    "offset": getattr(entity, 'offset', None),
                    "length": getattr(entity, 'length', None),
                    "url": getattr(entity, 'url', None)
                }
                
                # 提取实体对应的文本
                if message.text and entity_info['offset'] is not None and entity_info['length']:
                    start = entity_info['offset']
                    end = start + entity_info['length']
                    entity_text = message.text[start:end]
                    entity_info['extracted_text'] = entity_text
                    
                    logger.info(f"实体 {i}:")
                    logger.info(f"  类型: {entity_info['type']}")
                    logger.info(f"  偏移: {entity_info['offset']}")
                    logger.info(f"  长度: {entity_info['length']}")
                    logger.info(f"  文本: {repr(entity_text)}")
                    if entity_info['url']:
                        logger.info(f"  URL: {entity_info['url']}")
                    logger.info("-" * 30)
                
                analysis_result["entities"].append(entity_info)
        else:
            analysis_result["entities"] = []
            logger.info("📌 消息无实体")
        
        # 重点检查可疑的星号位置
        logger.info("🔍 星号位置详细分析:")
        logger.info("=" * 60)
        
        if message.text and "*" in message.text:
            text = message.text
            asterisk_positions = [i for i, char in enumerate(text) if char == "*"]
            
            for pos in asterisk_positions:
                # 获取星号前后的上下文
                start = max(0, pos - 10)
                end = min(len(text), pos + 11)
                context = text[start:end]
                
                logger.info(f"位置 {pos}: ...{context}...")
                logger.info(f"  前一个字符: {repr(text[pos-1]) if pos > 0 else 'N/A'}")
                logger.info(f"  后一个字符: {repr(text[pos+1]) if pos < len(text)-1 else 'N/A'}")
                
                # 检查是否在实体范围内
                if hasattr(message, 'entities') and message.entities:
                    for entity in message.entities:
                        if hasattr(entity, 'offset') and hasattr(entity, 'length'):
                            entity_start = entity.offset
                            entity_end = entity_start + entity.length
                            if entity_start <= pos < entity_end:
                                logger.info(f"  ⚠️  位于实体内: {entity.__class__.__name__} ({entity_start}-{entity_end})")
                                break
                    else:
                        logger.info(f"  ✅ 不在任何实体范围内")
                logger.info("-" * 30)
        
        # 保存分析结果到文件
        output_file = Path("message_7243_analysis.json")
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(analysis_result, f, ensure_ascii=False, indent=2)
        
        logger.info("=" * 60)
        logger.info(f"✅ 分析完成！结果已保存到: {output_file}")
        logger.info(f"📊 总结:")
        logger.info(f"  - 消息ID: {message.id}")
        logger.info(f"  - 消息时间: {message.date}")
        logger.info(f"  - 有文本属性: {len([k for k, v in text_attrs.items() if v])}")
        logger.info(f"  - 实体数量: {len(message.entities) if message.entities else 0}")
        logger.info(f"  - 包含星号: {'是' if any('*' in str(v) for v in text_attrs.values() if v) else '否'}")
        
        # 特别提醒
        if message.text and "*" in message.text:
            logger.warning("⚠️  消息.text属性中确实包含星号！")
            logger.warning("   这可能是原始消息本身就有星号，或者是Telethon处理时产生的")
        
        if message.raw_text and "*" in message.raw_text:
            logger.warning("⚠️  消息.raw_text属性中也包含星号！")
        
        return analysis_result
        
    except Exception as e:
        logger.error(f"❌ 分析过程中出错: {e}")
        return None
        
    finally:
        if client:
            await client.disconnect()
            logger.info("🔌 客户端已断开连接")

async def main():
    """主函数"""
    logger.info("🚀 开始分析消息 https://t.me/feilvbingi/7243")
    
    try:
        result = await analyze_message_7243()
        if result:
            logger.info("✅ 分析任务完成")
        else:
            logger.error("❌ 分析任务失败")
    except Exception as e:
        logger.error(f"❌ 主函数执行失败: {e}")

if __name__ == "__main__":
    # 确保在项目根目录下运行
    project_root = Path(__file__).parent
    os.chdir(project_root)
    
    # 添加项目路径到Python路径
    import sys
    sys.path.insert(0, str(project_root))
    
    # 运行分析
    asyncio.run(main())