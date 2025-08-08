#!/usr/bin/env python3
"""
配置导入脚本 - 从JSON文件导入系统配置
支持增量导入和覆盖模式
"""

import asyncio
import json
from datetime import datetime
from sqlalchemy import select, delete
from app.core.database import AsyncSessionLocal, SystemConfig, AdKeyword, Channel, FilterRule
import sys
import argparse

async def import_configs(filename, mode='merge'):
    """
    导入配置数据
    
    Args:
        filename: 配置文件路径
        mode: 导入模式 - 'merge'(合并,默认) 或 'replace'(替换)
    """
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"❌ 文件不存在: {filename}")
        return False
    except json.JSONDecodeError as e:
        print(f"❌ JSON解析错误: {e}")
        return False
    
    async with AsyncSessionLocal() as session:
        stats = {
            "system_configs": {"added": 0, "updated": 0, "skipped": 0},
            "ad_keywords": {"added": 0, "updated": 0, "skipped": 0},
            "channels": {"added": 0, "updated": 0, "skipped": 0},
            "filter_rules": {"added": 0, "updated": 0, "skipped": 0}
        }
        
        print(f"开始导入配置 (模式: {mode})...")
        print(f"导入文件: {filename}")
        print(f"导出时间: {data.get('export_time', '未知')}")
        print(f"版本: {data.get('version', '未知')}\n")
        
        # 导入系统配置
        if 'system_configs' in data:
            print("正在导入系统配置...")
            
            if mode == 'replace':
                # 替换模式：先删除所有非session配置
                await session.execute(
                    delete(SystemConfig).where(SystemConfig.key != 'telegram.session')
                )
            
            for config_data in data['system_configs']:
                # 跳过session配置
                if config_data['key'] == 'telegram.session':
                    stats["system_configs"]["skipped"] += 1
                    continue
                
                # 查找现有配置
                query = select(SystemConfig).where(SystemConfig.key == config_data['key'])
                result = await session.execute(query)
                existing = result.scalar_one_or_none()
                
                if existing:
                    # 更新现有配置
                    existing.value = config_data['value']
                    existing.description = config_data.get('description')
                    existing.config_type = config_data.get('config_type')
                    existing.is_active = config_data.get('is_active', True)
                    existing.updated_at = datetime.utcnow()
                    stats["system_configs"]["updated"] += 1
                else:
                    # 创建新配置
                    new_config = SystemConfig(
                        key=config_data['key'],
                        value=config_data['value'],
                        description=config_data.get('description'),
                        config_type=config_data.get('config_type'),
                        is_active=config_data.get('is_active', True)
                    )
                    session.add(new_config)
                    stats["system_configs"]["added"] += 1
            
            await session.commit()
            print(f"  系统配置: 添加 {stats['system_configs']['added']}, "
                  f"更新 {stats['system_configs']['updated']}, "
                  f"跳过 {stats['system_configs']['skipped']}")
        
        # 导入广告关键词
        if 'ad_keywords' in data:
            print("正在导入广告关键词...")
            
            if mode == 'replace':
                # 替换模式：先删除所有关键词
                await session.execute(delete(AdKeyword))
            
            for keyword_data in data['ad_keywords']:
                # 查找现有关键词
                query = select(AdKeyword).where(
                    AdKeyword.keyword == keyword_data['keyword'],
                    AdKeyword.keyword_type == keyword_data['keyword_type']
                )
                result = await session.execute(query)
                existing = result.scalar_one_or_none()
                
                if existing:
                    # 更新现有关键词
                    existing.description = keyword_data.get('description')
                    existing.is_active = keyword_data.get('is_active', True)
                    existing.updated_at = datetime.utcnow()
                    stats["ad_keywords"]["updated"] += 1
                else:
                    # 创建新关键词
                    new_keyword = AdKeyword(
                        keyword=keyword_data['keyword'],
                        keyword_type=keyword_data['keyword_type'],
                        description=keyword_data.get('description'),
                        is_active=keyword_data.get('is_active', True)
                    )
                    session.add(new_keyword)
                    stats["ad_keywords"]["added"] += 1
            
            await session.commit()
            print(f"  广告关键词: 添加 {stats['ad_keywords']['added']}, "
                  f"更新 {stats['ad_keywords']['updated']}")
        
        # 导入频道配置
        if 'channels' in data:
            print("正在导入频道配置...")
            
            if mode == 'replace':
                # 替换模式：先删除所有频道
                await session.execute(delete(Channel))
            
            for channel_data in data['channels']:
                # 查找现有频道（按名称）
                query = select(Channel).where(
                    Channel.channel_name == channel_data['channel_name']
                )
                result = await session.execute(query)
                existing = result.scalar_one_or_none()
                
                if existing:
                    # 更新现有频道
                    existing.channel_id = channel_data.get('channel_id')
                    existing.channel_title = channel_data.get('channel_title')
                    existing.channel_type = channel_data.get('channel_type')
                    existing.is_active = channel_data.get('is_active', True)
                    existing.config = channel_data.get('config')
                    existing.description = channel_data.get('description')
                    existing.updated_at = datetime.utcnow()
                    stats["channels"]["updated"] += 1
                else:
                    # 创建新频道
                    new_channel = Channel(
                        channel_id=channel_data.get('channel_id'),
                        channel_name=channel_data['channel_name'],
                        channel_title=channel_data.get('channel_title'),
                        channel_type=channel_data.get('channel_type'),
                        is_active=channel_data.get('is_active', True),
                        config=channel_data.get('config'),
                        description=channel_data.get('description')
                    )
                    session.add(new_channel)
                    stats["channels"]["added"] += 1
            
            await session.commit()
            print(f"  频道配置: 添加 {stats['channels']['added']}, "
                  f"更新 {stats['channels']['updated']}")
        
        # 导入过滤规则
        if 'filter_rules' in data:
            print("正在导入过滤规则...")
            
            if mode == 'replace':
                # 替换模式：先删除所有规则
                await session.execute(delete(FilterRule))
            
            for rule_data in data['filter_rules']:
                # 查找现有规则
                query = select(FilterRule).where(
                    FilterRule.rule_type == rule_data['rule_type'],
                    FilterRule.pattern == rule_data['pattern']
                )
                result = await session.execute(query)
                existing = result.scalar_one_or_none()
                
                if existing:
                    # 更新现有规则
                    existing.action = rule_data.get('action')
                    existing.is_active = rule_data.get('is_active', True)
                    stats["filter_rules"]["updated"] += 1
                else:
                    # 创建新规则
                    new_rule = FilterRule(
                        rule_type=rule_data['rule_type'],
                        pattern=rule_data['pattern'],
                        action=rule_data.get('action'),
                        is_active=rule_data.get('is_active', True)
                    )
                    session.add(new_rule)
                    stats["filter_rules"]["added"] += 1
            
            await session.commit()
            print(f"  过滤规则: 添加 {stats['filter_rules']['added']}, "
                  f"更新 {stats['filter_rules']['updated']}")
        
        print(f"\n✅ 配置导入完成!")
        return True

async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='导入系统配置')
    parser.add_argument('filename', help='配置文件路径')
    parser.add_argument('--mode', choices=['merge', 'replace'], default='merge',
                        help='导入模式: merge(合并,默认) 或 replace(替换)')
    
    args = parser.parse_args()
    
    try:
        success = await import_configs(args.filename, args.mode)
        if not success:
            sys.exit(1)
    except Exception as e:
        print(f"❌ 导入失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())