#!/usr/bin/env python3
"""
系统管理脚本
"""
import asyncio
import argparse
import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import AsyncSessionLocal, Message, Channel, FilterRule, SystemConfig
from app.services.config_manager import config_manager
from sqlalchemy import select, func

async def show_stats():
    """显示系统统计信息"""
    async with AsyncSessionLocal() as db:
        # 消息统计
        total_messages = await db.execute(select(func.count(Message.id)))
        pending_messages = await db.execute(
            select(func.count(Message.id)).where(Message.status == "pending")
        )
        approved_messages = await db.execute(
            select(func.count(Message.id)).where(Message.status == "approved")
        )
        ad_messages = await db.execute(
            select(func.count(Message.id)).where(Message.is_ad == True)
        )
        
        print("📊 系统统计信息")
        print("=" * 40)
        print(f"总消息数: {total_messages.scalar()}")
        print(f"待审核: {pending_messages.scalar()}")
        print(f"已批准: {approved_messages.scalar()}")
        print(f"广告消息: {ad_messages.scalar()}")
        
        # 频道统计
        channels = await db.execute(select(Channel))
        print(f"\n配置频道数: {len(channels.scalars().all())}")
        
        # 过滤规则统计
        rules = await db.execute(select(FilterRule))
        print(f"过滤规则数: {len(rules.scalars().all())}")

async def cleanup_old_messages(days=30):
    """清理旧消息"""
    from datetime import datetime, timedelta
    
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    
    async with AsyncSessionLocal() as db:
        # 删除指定天数前的已处理消息
        result = await db.execute(
            select(Message).where(
                Message.created_at < cutoff_date,
                Message.status.in_(["approved", "rejected", "auto_forwarded"])
            )
        )
        old_messages = result.scalars().all()
        
        for message in old_messages:
            await db.delete(message)
        
        await db.commit()
        print(f"✅ 已清理 {len(old_messages)} 条 {days} 天前的消息")

async def add_source_channel(channel_id, channel_name):
    """添加源频道"""
    async with AsyncSessionLocal() as db:
        channel = Channel(
            channel_id=channel_id,
            channel_name=channel_name,
            channel_type="source",
            is_active=True
        )
        db.add(channel)
        await db.commit()
        print(f"✅ 已添加源频道: {channel_name} ({channel_id})")

async def list_channels():
    """列出所有频道"""
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Channel))
        channels = result.scalars().all()
        
        print("📋 频道列表")
        print("=" * 60)
        for channel in channels:
            status = "✅" if channel.is_active else "❌"
            print(f"{status} {channel.channel_name} ({channel.channel_id}) - {channel.channel_type}")

async def add_filter_rule(rule_type, pattern, action="flag"):
    """添加过滤规则"""
    async with AsyncSessionLocal() as db:
        rule = FilterRule(
            rule_type=rule_type,
            pattern=pattern,
            action=action,
            is_active=True
        )
        db.add(rule)
        await db.commit()
        print(f"✅ 已添加过滤规则: {rule_type} - {pattern}")

async def list_configs():
    """列出所有配置"""
    try:
        configs = await config_manager.get_all_configs()
        
        print("⚙️ 系统配置列表")
        print("=" * 80)
        
        # 按分类组织配置
        categories = {}
        for key, config in configs.items():
            category = key.split('.')[0] if '.' in key else 'other'
            if category not in categories:
                categories[category] = []
            categories[category].append((key, config))
        
        for category, items in sorted(categories.items()):
            print(f"\n📂 {category.upper()}")
            print("-" * 40)
            for key, config in items:
                value_str = str(config['value'])
                if len(value_str) > 50:
                    value_str = value_str[:47] + "..."
                print(f"  {key:<30} = {value_str}")
                if config['description']:
                    print(f"  {'':<30}   📝 {config['description']}")
                
    except Exception as e:
        print(f"❌ 获取配置列表失败: {e}")

async def get_config_value(key):
    """获取配置值"""
    try:
        value = await config_manager.get_config(key)
        if value is None:
            print(f"❌ 配置项 '{key}' 不存在")
            return
        
        print(f"⚙️ 配置项: {key}")
        print(f"📄 值: {value}")
        
        # 获取详细信息
        all_configs = await config_manager.get_all_configs()
        if key in all_configs:
            config_info = all_configs[key]
            print(f"📝 描述: {config_info.get('description', '无描述')}")
            print(f"🏷️ 类型: {config_info.get('config_type', 'unknown')}")
            print(f"🕒 更新时间: {config_info.get('updated_at', 'unknown')}")
            
    except Exception as e:
        print(f"❌ 获取配置失败: {e}")

async def set_config_value(key, value, config_type="string", description=""):
    """设置配置值"""
    try:
        import json
        
        # 根据类型转换值
        if config_type == "integer":
            value = int(value)
        elif config_type == "boolean":
            value = value.lower() in ('true', '1', 'yes', 'on')
        elif config_type == "list" or config_type == "json":
            value = json.loads(value)
        
        success = await config_manager.set_config(key, value, description, config_type)
        
        if success:
            print(f"✅ 配置设置成功: {key} = {value}")
        else:
            print(f"❌ 配置设置失败: {key}")
            
    except ValueError as e:
        print(f"❌ 值格式错误: {e}")
    except json.JSONDecodeError as e:
        print(f"❌ JSON格式错误: {e}")
    except Exception as e:
        print(f"❌ 设置配置失败: {e}")

async def delete_config_value(key):
    """删除配置"""
    try:
        success = await config_manager.delete_config(key)
        
        if success:
            print(f"✅ 配置删除成功: {key}")
        else:
            print(f"❌ 配置项不存在: {key}")
            
    except Exception as e:
        print(f"❌ 删除配置失败: {e}")

async def reset_default_configs():
    """重置为默认配置"""
    try:
        from app.services.config_manager import DEFAULT_CONFIGS
        
        print("⚠️ 正在重置所有配置为默认值...")
        
        success_count = 0
        for key, config_info in DEFAULT_CONFIGS.items():
            success = await config_manager.set_config(
                key=key,
                value=config_info["value"],
                description=config_info["description"],
                config_type=config_info["config_type"]
            )
            if success:
                success_count += 1
                print(f"  ✅ {key}")
            else:
                print(f"  ❌ {key}")
        
        print(f"\n🎉 成功重置 {success_count} 个配置项")
        
    except Exception as e:
        print(f"❌ 重置配置失败: {e}")

async def main():
    parser = argparse.ArgumentParser(description="Telegram消息系统管理工具")
    subparsers = parser.add_subparsers(dest='command', help='可用命令')
    
    # 统计命令
    subparsers.add_parser('stats', help='显示系统统计信息')
    
    # 清理命令
    cleanup_parser = subparsers.add_parser('cleanup', help='清理旧消息')
    cleanup_parser.add_argument('--days', type=int, default=30, help='清理多少天前的消息')
    
    # 添加频道命令
    add_channel_parser = subparsers.add_parser('add-channel', help='添加源频道')
    add_channel_parser.add_argument('channel_id', help='频道ID')
    add_channel_parser.add_argument('channel_name', help='频道名称')
    
    # 列出频道命令
    subparsers.add_parser('list-channels', help='列出所有频道')
    
    # 添加过滤规则命令
    add_rule_parser = subparsers.add_parser('add-rule', help='添加过滤规则')
    add_rule_parser.add_argument('rule_type', choices=['keyword', 'regex'], help='规则类型')
    add_rule_parser.add_argument('pattern', help='匹配模式')
    add_rule_parser.add_argument('--action', default='flag', help='执行动作')
    
    # 配置管理命令
    config_parser = subparsers.add_parser('config', help='配置管理')
    config_subparsers = config_parser.add_subparsers(dest='config_action', help='配置操作')
    
    # 列出配置
    config_subparsers.add_parser('list', help='列出所有配置')
    
    # 获取配置
    get_config_parser = config_subparsers.add_parser('get', help='获取配置值')
    get_config_parser.add_argument('key', help='配置键名')
    
    # 设置配置
    set_config_parser = config_subparsers.add_parser('set', help='设置配置值')
    set_config_parser.add_argument('key', help='配置键名')
    set_config_parser.add_argument('value', help='配置值')
    set_config_parser.add_argument('--type', default='string', choices=['string', 'integer', 'boolean', 'list', 'json'], help='配置类型')
    set_config_parser.add_argument('--description', default='', help='配置描述')
    
    # 删除配置
    del_config_parser = config_subparsers.add_parser('delete', help='删除配置')
    del_config_parser.add_argument('key', help='配置键名')
    
    # 重置配置
    config_subparsers.add_parser('reset', help='重置为默认配置')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    try:
        if args.command == 'stats':
            await show_stats()
        elif args.command == 'cleanup':
            await cleanup_old_messages(args.days)
        elif args.command == 'add-channel':
            await add_source_channel(args.channel_id, args.channel_name)
        elif args.command == 'list-channels':
            await list_channels()
        elif args.command == 'add-rule':
            await add_filter_rule(args.rule_type, args.pattern, args.action)
        elif args.command == 'config':
            if args.config_action == 'list':
                await list_configs()
            elif args.config_action == 'get':
                await get_config_value(args.key)
            elif args.config_action == 'set':
                await set_config_value(args.key, args.value, args.type, args.description)
            elif args.config_action == 'delete':
                await delete_config_value(args.key)
            elif args.config_action == 'reset':
                await reset_default_configs()
            else:
                config_parser.print_help()
    except Exception as e:
        print(f"❌ 执行失败: {e}")

if __name__ == "__main__":
    asyncio.run(main())