"""
启动时的关键配置检查服务
确保所有关键配置都正确设置和解析
"""
import logging
from typing import Dict, List, Optional
from app.services.config_manager import ConfigManager
from app.services.channel_id_resolver import channel_id_resolver
from app.services.channel_manager import channel_manager
from app.core.database import AsyncSessionLocal, Channel
from sqlalchemy import select

logger = logging.getLogger(__name__)

class StartupChecker:
    """启动检查器"""
    
    def __init__(self):
        self.config_manager = ConfigManager()
        self.errors = []
        self.warnings = []
        self.resolved_items = []
        
    async def check_and_resolve_all_channels(self, client=None) -> Dict:
        """
        检查并解析所有频道ID（源频道、目标频道、审核群）
        返回检查结果
        """
        logger.info("=" * 60)
        logger.info("🚀 开始启动配置检查...")
        logger.info("=" * 60)
        
        # 如果提供了客户端，临时设置到auth_manager
        original_client = None
        if client:
            from app.telegram.auth import auth_manager
            original_client = auth_manager.client
            auth_manager.client = client
        
        results = {
            'success': True,
            'source_channels': [],
            'target_channel': None,
            'review_group': None,
            'errors': [],
            'warnings': [],
            'resolved': []
        }
        
        try:
            # 1. 检查并解析源频道
            logger.info("\n📡 检查源频道配置...")
            source_results = await self._check_source_channels()
            results['source_channels'] = source_results['channels']
            results['errors'].extend(source_results['errors'])
            results['warnings'].extend(source_results['warnings'])
            results['resolved'].extend(source_results['resolved'])
            
            # 2. 检查并解析目标频道
            logger.info("\n🎯 检查目标频道配置...")
            target_result = await self._check_target_channel()
            results['target_channel'] = target_result['channel_id']
            if target_result['error']:
                results['errors'].append(target_result['error'])
            if target_result['warning']:
                results['warnings'].append(target_result['warning'])
            if target_result['resolved']:
                results['resolved'].append(target_result['resolved'])
            
            # 3. 检查并解析审核群
            logger.info("\n👥 检查审核群配置...")
            review_result = await self._check_review_group()
            results['review_group'] = review_result['group_id']
            if review_result['error']:
                results['errors'].append(review_result['error'])
            if review_result['warning']:
                results['warnings'].append(review_result['warning'])
            if review_result['resolved']:
                results['resolved'].append(review_result['resolved'])
            
            # 4. 检查Telegram认证
            logger.info("\n🔐 检查Telegram认证...")
            auth_result = await self._check_telegram_auth()
            if auth_result['error']:
                results['errors'].append(auth_result['error'])
            if auth_result['warning']:
                results['warnings'].append(auth_result['warning'])
            
            # 5. 汇总结果
            if results['errors']:
                results['success'] = False
                logger.error("\n❌ 启动检查发现严重错误:")
                for error in results['errors']:
                    logger.error(f"  - {error}")
            
            if results['warnings']:
                logger.warning("\n⚠️ 启动检查发现警告:")
                for warning in results['warnings']:
                    logger.warning(f"  - {warning}")
            
            if results['resolved']:
                logger.info("\n✅ 成功解析的项目:")
                for item in results['resolved']:
                    logger.info(f"  - {item}")
            
            if results['success']:
                logger.info("\n✅ 启动检查完成，所有关键配置正常")
            else:
                logger.error("\n❌ 启动检查失败，请修复错误后重试")
            
            logger.info("=" * 60)
            
            return results
            
        except Exception as e:
            logger.error(f"启动检查过程出错: {e}")
            results['success'] = False
            results['errors'].append(f"检查过程异常: {str(e)}")
            return results
        finally:
            # 恢复原始客户端
            if client and original_client is not None:
                from app.telegram.auth import auth_manager
                auth_manager.client = original_client
    
    async def _check_source_channels(self) -> Dict:
        """检查源频道配置"""
        result = {
            'channels': [],
            'errors': [],
            'warnings': [],
            'resolved': []
        }
        
        try:
            # 获取所有活跃源频道
            async with AsyncSessionLocal() as db:
                query_result = await db.execute(
                    select(Channel).where(
                        Channel.channel_type == "source",
                        Channel.is_active == True
                    )
                )
                channels = query_result.scalars().all()
                
                if not channels:
                    result['errors'].append("未配置任何源频道")
                    return result
                
                for channel in channels:
                    if not channel.channel_id or channel.channel_id.strip() == '':
                        # 需要解析ID
                        logger.info(f"  - 频道 {channel.channel_name} 需要解析ID...")
                        resolved_id = await channel_id_resolver.resolve_and_update_channel(channel.channel_name)
                        
                        if resolved_id:
                            result['channels'].append(resolved_id)
                            result['resolved'].append(f"源频道 {channel.channel_name} -> {resolved_id}")
                            logger.info(f"    ✅ 解析成功: {resolved_id}")
                        else:
                            result['warnings'].append(f"源频道 {channel.channel_name} ID解析失败")
                            logger.warning(f"    ❌ 解析失败")
                    else:
                        # 已有ID，验证格式
                        channel_id = channel.channel_id
                        if not channel_id.startswith('-100'):
                            result['warnings'].append(f"源频道 {channel.channel_name} 的ID格式可能不正确: {channel_id}")
                        result['channels'].append(channel_id)
                        logger.info(f"  - 频道 {channel.channel_name}: {channel_id} (已配置)")
                
                logger.info(f"  共找到 {len(result['channels'])} 个活跃源频道")
                
        except Exception as e:
            result['errors'].append(f"检查源频道失败: {str(e)}")
            
        return result
    
    async def _check_target_channel(self) -> Dict:
        """检查目标频道配置"""
        result = {
            'channel_id': None,
            'error': None,
            'warning': None,
            'resolved': None
        }
        
        try:
            # 获取目标频道配置
            target_channel = await self.config_manager.get_config('channels.target_channel_id')
            target_channel_name = await self.config_manager.get_config('channels.target_channel_name')
            
            if not target_channel:
                if target_channel_name:
                    # 有频道名但没有ID，尝试解析
                    logger.info(f"  - 目标频道 {target_channel_name} 需要解析ID...")
                    resolved_id = await channel_id_resolver.resolve_channel_id(target_channel_name)
                    
                    if resolved_id:
                        # 保存解析的ID
                        await self.config_manager.set_config('channels.target_channel_id', resolved_id)
                        result['channel_id'] = resolved_id
                        result['resolved'] = f"目标频道 {target_channel_name} -> {resolved_id}"
                        logger.info(f"    ✅ 解析成功: {resolved_id}")
                    else:
                        result['error'] = f"目标频道 {target_channel_name} ID解析失败"
                        logger.error(f"    ❌ 解析失败")
                else:
                    result['error'] = "未配置目标频道"
                    logger.error("  - 未配置目标频道")
            else:
                # 检查是否为用户名而非ID
                if target_channel.startswith('@') or not target_channel.startswith('-100'):
                    # 这是用户名或格式不正确的ID，需要解析
                    logger.info(f"  - 目标频道 {target_channel} 需要解析ID...")
                    resolved_id = await channel_id_resolver.resolve_channel_id(target_channel)
                    
                    if resolved_id:
                        # 保存解析的ID，同时保存原始名称
                        await self.config_manager.set_config('channels.target_channel_id', resolved_id)
                        if target_channel.startswith('@'):
                            await self.config_manager.set_config('channels.target_channel_name', target_channel)
                        result['channel_id'] = resolved_id
                        result['resolved'] = f"目标频道 {target_channel} -> {resolved_id}"
                        logger.info(f"    ✅ 解析成功: {resolved_id}")
                    else:
                        result['error'] = f"目标频道 {target_channel} ID解析失败"
                        logger.error(f"    ❌ 解析失败")
                else:
                    # 已经是正确格式的ID
                    result['channel_id'] = target_channel
                    logger.info(f"  - 目标频道: {target_channel} (已配置)")
                
        except Exception as e:
            result['error'] = f"检查目标频道失败: {str(e)}"
            
        return result
    
    async def _check_review_group(self) -> Dict:
        """检查审核群配置"""
        result = {
            'group_id': None,
            'error': None,
            'warning': None,
            'resolved': None
        }
        
        try:
            # 获取审核群配置
            review_group = await self.config_manager.get_config('channels.review_group_id')
            review_group_name = await self.config_manager.get_config('channels.review_group_name')
            
            if not review_group:
                if review_group_name:
                    # 有群名但没有ID，尝试解析
                    logger.info(f"  - 审核群 {review_group_name} 需要解析ID...")
                    resolved_id = await channel_id_resolver.resolve_channel_id(review_group_name)
                    
                    if resolved_id:
                        # 保存解析的ID
                        await self.config_manager.set_config('channels.review_group_id', resolved_id)
                        result['group_id'] = resolved_id
                        result['resolved'] = f"审核群 {review_group_name} -> {resolved_id}"
                        logger.info(f"    ✅ 解析成功: {resolved_id}")
                    else:
                        result['warning'] = f"审核群 {review_group_name} ID解析失败"
                        logger.warning(f"    ❌ 解析失败")
                else:
                    result['warning'] = "未配置审核群（将直接转发到目标频道）"
                    logger.warning("  - 未配置审核群")
            else:
                # 检查是否为用户名而非ID
                if review_group.startswith('@') or not review_group.startswith('-100'):
                    # 这是用户名或格式不正确的ID，需要解析
                    logger.info(f"  - 审核群 {review_group} 需要解析ID...")
                    resolved_id = await channel_id_resolver.resolve_channel_id(review_group)
                    
                    if resolved_id:
                        # 保存解析的ID，同时保存原始名称
                        await self.config_manager.set_config('channels.review_group_id', resolved_id)
                        if review_group.startswith('@'):
                            await self.config_manager.set_config('channels.review_group_name', review_group)
                        result['group_id'] = resolved_id
                        result['resolved'] = f"审核群 {review_group} -> {resolved_id}"
                        logger.info(f"    ✅ 解析成功: {resolved_id}")
                    else:
                        result['warning'] = f"审核群 {review_group} ID解析失败"
                        logger.warning(f"    ❌ 解析失败")
                else:
                    # 已经是正确格式的ID
                    result['group_id'] = review_group
                    logger.info(f"  - 审核群: {review_group} (已配置)")
                
        except Exception as e:
            result['error'] = f"检查审核群失败: {str(e)}"
            
        return result
    
    async def _check_telegram_auth(self) -> Dict:
        """检查Telegram认证"""
        result = {
            'authenticated': False,
            'error': None,
            'warning': None
        }
        
        try:
            # 检查API凭据
            api_id = await self.config_manager.get_config('telegram.api_id')
            api_hash = await self.config_manager.get_config('telegram.api_hash')
            session = await self.config_manager.get_config('telegram.session')
            
            if not api_id or not api_hash:
                result['error'] = "缺少Telegram API凭据"
                logger.error("  - 缺少API ID或API Hash")
            elif not session:
                result['warning'] = "未完成Telegram认证，请访问 /auth.html 进行认证"
                logger.warning("  - 未找到会话信息")
            else:
                result['authenticated'] = True
                logger.info("  - Telegram认证状态: ✅ 已认证")
                
        except Exception as e:
            result['error'] = f"检查Telegram认证失败: {str(e)}"
            
        return result

# 创建全局实例
startup_checker = StartupChecker()