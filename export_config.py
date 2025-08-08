#!/usr/bin/env python3
"""
配置导出脚本 - 导出系统配置到JSON文件
排除敏感的session信息
"""

import asyncio
import json
from datetime import datetime
from sqlalchemy import select
from app.core.database import AsyncSessionLocal, SystemConfig, AdKeyword, Channel, FilterRule
import sys

async def export_configs():
    """导出所有配置数据"""
    async with AsyncSessionLocal() as session:
        export_data = {
            "export_time": datetime.now().isoformat(),
            "version": "1.0",
            "system_configs": [],
            "ad_keywords": [],
            "channels": [],
            "filter_rules": []
        }
        
        # 导出系统配置（排除session）
        print("正在导出系统配置...")
        query = select(SystemConfig).where(
            SystemConfig.key != 'telegram.session',
            SystemConfig.is_active == True
        )
        result = await session.execute(query)
        configs = result.scalars().all()
        
        for config in configs:
            export_data["system_configs"].append({
                "key": config.key,
                "value": config.value,
                "description": config.description,
                "config_type": config.config_type,
                "is_active": config.is_active
            })
        print(f"  导出了 {len(configs)} 个系统配置项")
        
        # 导出广告关键词
        print("正在导出广告关键词...")
        query = select(AdKeyword).where(AdKeyword.is_active == True)
        result = await session.execute(query)
        keywords = result.scalars().all()
        
        for keyword in keywords:
            export_data["ad_keywords"].append({
                "keyword": keyword.keyword,
                "keyword_type": keyword.keyword_type,
                "description": keyword.description,
                "is_active": keyword.is_active
            })
        print(f"  导出了 {len(keywords)} 个广告关键词")
        
        # 导出频道配置
        print("正在导出频道配置...")
        query = select(Channel).where(Channel.is_active == True)
        result = await session.execute(query)
        channels = result.scalars().all()
        
        for channel in channels:
            export_data["channels"].append({
                "channel_id": channel.channel_id,
                "channel_name": channel.channel_name,
                "channel_title": channel.channel_title,
                "channel_type": channel.channel_type,
                "is_active": channel.is_active,
                "config": channel.config,
                "description": channel.description
            })
        print(f"  导出了 {len(channels)} 个频道配置")
        
        # 导出过滤规则（如果有）
        print("正在导出过滤规则...")
        query = select(FilterRule).where(FilterRule.is_active == True)
        result = await session.execute(query)
        rules = result.scalars().all()
        
        for rule in rules:
            export_data["filter_rules"].append({
                "rule_type": rule.rule_type,
                "pattern": rule.pattern,
                "action": rule.action,
                "is_active": rule.is_active
            })
        print(f"  导出了 {len(rules)} 个过滤规则")
        
        # 保存到文件
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"config_export_{timestamp}.json"
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)
        
        print(f"\n✅ 配置已成功导出到: {filename}")
        print(f"总计导出:")
        print(f"  - 系统配置: {len(export_data['system_configs'])} 项")
        print(f"  - 广告关键词: {len(export_data['ad_keywords'])} 项")
        print(f"  - 频道配置: {len(export_data['channels'])} 项")
        print(f"  - 过滤规则: {len(export_data['filter_rules'])} 项")
        
        return filename

async def main():
    """主函数"""
    try:
        await export_configs()
    except Exception as e:
        print(f"❌ 导出失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())