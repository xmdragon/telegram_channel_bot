"""
启动时的关键配置检查服务
确保所有关键配置都正确设置和解析
"""
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
from app.services.config_manager import config_manager
from app.services.channel_id_resolver import channel_id_resolver
from app.services.channel_manager import channel_manager
from app.storage.json_store import get_json_channel_store
from app.storage.redis_manager import redis_manager
from app.utils.timezone import get_current_time

logger = logging.getLogger(__name__)

class StartupChecker:
    """启动检查器"""
    
    def __init__(self):
        self.config_manager = config_manager
        self.errors = []
        self.warnings = []
        self.resolved_items = []
        self.critical_json_files = [
            "data/config/channels.json",
            "data/config/system.json", 
            "data/config/admins.json"
        ]
        
    async def check_and_resolve_all_channels(self, client=None) -> Dict:
        """
        检查并解析所有频道ID（源频道、目标频道、审核群）
        返回检查结果
        """
        logger.info("=" * 60)
        logger.info("🚀 开始启动配置检查...")
        logger.info("=" * 60)
        
        # 首先检查JSON文件完整性
        json_check = self._check_json_integrity()
        if not json_check['success']:
            results['success'] = False
            results['errors'].extend(json_check['errors'])
            return results
        
        # 客户端直接传递给需要的方法，不再使用全局auth_manager
        
        results = {
            'success': True,
            'source_channels': [],
            'target_channel': None,
            'errors': [],
            'warnings': [],
            'resolved': [],
            'duplicates_removed': []  # 新增：记录删除的重复项
        }
        
        try:
            # 1. 检查并解析源频道
            logger.info("\n📡 检查源频道配置...")
            source_results = await self._check_source_channels()
            results['source_channels'] = source_results['channels']
            results['errors'].extend(source_results['errors'])
            results['warnings'].extend(source_results['warnings'])
            results['resolved'].extend(source_results['resolved'])
            results['duplicates_removed'].extend(source_results.get('duplicates_removed', []))
            
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

            # 3. 检查Telegram认证
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
            # 清理工作（不再需要恢复客户端）
            pass
    
    async def _check_source_channels(self) -> Dict:
        """检查源频道配置"""
        result = {
            'channels': [],
            'errors': [],
            'warnings': [],
            'resolved': [],
            'duplicates_removed': []  # 新增：记录删除的重复项
        }
        
        try:
            # 获取目标频道配置，用于过滤
            target_channel_id = await self.config_manager.get_config('target.channel_id')
            target_channel = await self.config_manager.get_config('target.channel_link')
            
            # 从 JSON 存储获取所有活跃源频道
            channel_store = get_json_channel_store()
            channels = channel_store.get_all_channels()
                
            if not channels:
                result['errors'].append("未配置任何源频道")
                return result
            
            # 步骤1: 检测并删除重复的频道（基于channel_id）
            seen_ids = {}  # 记录已见过的channel_id
            channels_to_process = []  # 处理后的频道列表
            
            for channel in channels:
                channel_id = channel.get('channel_id', '')
                channel_name = channel.get('channel_name', '')
                
                if channel_id and channel_id.startswith('-100'):  # 有效的频道ID
                    if channel_id in seen_ids:
                        # 发现重复，删除当前项
                        existing = seen_ids[channel_id]
                        logger.warning(f"发现重复频道ID {channel_id}: {existing.get('channel_name')} vs {channel_name}")
                        
                        # 删除重复的频道记录
                        success = channel_store.delete_channel(channel_name)
                        if success:
                            result['duplicates_removed'].append(f"{channel_name} (重复ID: {channel_id})")
                            logger.info(f"已删除重复频道: {channel_name}")
                        continue
                    else:
                        seen_ids[channel_id] = channel
                        channels_to_process.append(channel)
                else:
                    # 没有有效ID的频道，暂时保留
                    channels_to_process.append(channel)
            
            # 如果有删除的重复项，记录到警告
            if result['duplicates_removed']:
                result['warnings'].append(f"已删除 {len(result['duplicates_removed'])} 个重复频道")
            
            # 继续处理剩余的频道
            for channel in channels_to_process:
                    
                channel_name = channel.get('channel_name', '')
                channel_id = channel.get('channel_id', '')
                
                # 跳过目标频道（如果错误地出现在源频道列表中）
                if channel_id == target_channel_id or channel_name == target_channel:
                    logger.warning(f"发现目标频道错误地存在于源频道列表中，跳过处理: {channel_name} ({channel_id})")
                    result['warnings'].append(f"目标频道 {channel_name} 错误地标记为源频道，已跳过")
                    continue
                
                if not channel_id or channel_id.strip() == '':
                    # 需要解析ID
                    logger.info(f"  - 频道 {channel_name} 需要解析ID...")
                    resolved_id = await self._resolve_and_save_channel_id(channel_name)
                        
                    if resolved_id:
                        # 检查解析后是否产生重复
                        if resolved_id in seen_ids:
                            existing = seen_ids[resolved_id]
                            logger.warning(f"解析后发现重复ID {resolved_id}: {existing.get('channel_name')} vs {channel_name}")
                            # 删除当前频道，保留已存在的
                            channel_store.delete_channel(channel_name)
                            result['duplicates_removed'].append(f"{channel_name} (解析后重复: {resolved_id})")
                            result['warnings'].append(f"频道 {channel_name} 解析后与 {existing.get('channel_name')} 重复，已删除")
                        else:
                            # 更新频道信息并检查名称变化
                            await self._update_channel_info(channel, resolved_id, result)
                            seen_ids[resolved_id] = channel
                            result['channels'].append(resolved_id)
                            result['resolved'].append(f"源频道 {channel_name} -> {resolved_id}")
                            logger.info(f"    ✅ 解析成功: {resolved_id}")
                    else:
                        result['warnings'].append(f"源频道 {channel_name} ID解析失败")
                        logger.warning(f"    ❌ 解析失败")
                else:
                    # 已有ID，检查是否需要解析
                    if channel_id.startswith('@'):
                        # 是用户名，需要解析
                        logger.info(f"  - 频道 {channel_name} (@用户名) 需要解析ID...")
                        resolved_id = await self._resolve_and_save_channel_id(channel_name)
                            
                        if resolved_id:
                            # 检查解析后是否产生重复
                            if resolved_id in seen_ids:
                                existing = seen_ids[resolved_id]
                                logger.warning(f"解析后发现重复ID {resolved_id}: {existing.get('channel_name')} vs {channel_name}")
                                channel_store.delete_channel(channel_name)
                                result['duplicates_removed'].append(f"{channel_name} (解析后重复: {resolved_id})")
                                result['warnings'].append(f"频道 {channel_name} 解析后与 {existing.get('channel_name')} 重复，已删除")
                            else:
                                await self._update_channel_info(channel, resolved_id, result)
                                seen_ids[resolved_id] = channel
                                result['channels'].append(resolved_id)
                                result['resolved'].append(f"源频道 {channel_name} -> {resolved_id}")
                                logger.info(f"    ✅ 解析成功: {resolved_id}")
                        else:
                            result['warnings'].append(f"源频道 {channel_name} ID解析失败")
                            logger.warning(f"    ❌ 解析失败")
                    elif not channel_id.startswith('-100'):
                        # ID格式可能不正确，尝试解析
                        logger.info(f"  - 频道 {channel_name} (ID格式异常) 需要解析...")
                        resolved_id = await self._resolve_and_save_channel_id(channel_name)
                            
                        if resolved_id:
                            # 检查解析后是否产生重复
                            if resolved_id in seen_ids:
                                existing = seen_ids[resolved_id]
                                logger.warning(f"解析后发现重复ID {resolved_id}: {existing.get('channel_name')} vs {channel_name}")
                                channel_store.delete_channel(channel_name)
                                result['duplicates_removed'].append(f"{channel_name} (解析后重复: {resolved_id})")
                                result['warnings'].append(f"频道 {channel_name} 解析后与 {existing.get('channel_name')} 重复，已删除")
                            else:
                                await self._update_channel_info(channel, resolved_id, result)
                                seen_ids[resolved_id] = channel
                                result['channels'].append(resolved_id)
                                result['resolved'].append(f"源频道 {channel_name} -> {resolved_id}")
                                logger.info(f"    ✅ 解析成功: {resolved_id}")
                        else:
                            # 解析失败，仍然使用原ID但给出警告
                            result['warnings'].append(f"源频道 {channel_name} 的ID格式可能不正确: {channel_id}")
                            result['channels'].append(channel_id)
                            logger.warning(f"    ⚠️ ID格式异常但解析失败，继续使用: {channel_id}")
                    else:
                        # 格式正确的ID
                        result['channels'].append(channel_id)
                        logger.info(f"  - 频道 {channel_name}: {channel_id} (已配置)")
                
            logger.info(f"  共找到 {len(result['channels'])} 个活跃源频道")
                
        except Exception as e:
            result['errors'].append(f"检查源频道失败: {str(e)}")
            
        return result
    
    async def _update_channel_info(self, channel: Dict, resolved_id: str, result: Dict) -> None:
        """更新频道信息并检查名称变化"""
        try:
            # 使用双Session系统获取客户端
            from app.telegram.dual_session_manager import dual_session_manager
            client = await dual_session_manager.get_listener_client()
            
            if not client:
                return
            
            # 获取频道最新信息
            try:
                entity = await client.get_entity(int(resolved_id))
                current_username = f"@{entity.username}" if hasattr(entity, 'username') and entity.username else None
                current_title = entity.title if hasattr(entity, 'title') else None
                
                old_name = channel.get('channel_name', '')
                
                # 检查用户名是否变化
                if current_username and current_username != old_name:
                    logger.info(f"检测到频道名称变化: {old_name} -> {current_username}")
                    result['warnings'].append(f"频道名称已更改: {old_name} -> {current_username}")
                    channel['channel_name'] = current_username
                
                # 更新频道标题
                if current_title:
                    channel['channel_title'] = current_title
                
                # 更新频道ID
                channel['channel_id'] = resolved_id
                channel['updated_at'] = get_current_time().isoformat()
                
                # 保存更新
                channel_store = get_json_channel_store()
                channel_store.update_channel(channel)
                
            except Exception as e:
                logger.debug(f"获取频道详细信息失败: {e}")
                # 即使获取详细信息失败，也要更新ID
                channel['channel_id'] = resolved_id
                channel_store = get_json_channel_store()
                channel_store.update_channel(channel)
                
        except Exception as e:
            logger.error(f"更新频道信息失败: {e}")
    
    async def _resolve_and_save_channel_id(self, channel_name: str, channel_type: str = 'source') -> Optional[str]:
        """解析并保存频道ID到JSON存储（仅用于源频道）"""
        try:
            # 检查是否为目标频道（目标频道不应该被添加到频道列表中）
            target_channel_id = await self.config_manager.get_config('target.channel_id')
            target_channel = await self.config_manager.get_config('target.channel_link')
            
            # 使用频道ID解析器解析
            resolved_id = await channel_id_resolver.resolve_channel_id(channel_name)
            
            if resolved_id:
                # 如果解析的ID与目标频道相同，不应该添加到频道列表中
                if resolved_id == target_channel_id or channel_name == target_channel:
                    logger.warning(f"跳过添加目标频道到源频道列表: {channel_name} -> {resolved_id}")
                    return resolved_id
                
                # 保存到JSON存储（仅非目标频道）
                channel_store = get_json_channel_store()
                
                # 更新频道配置
                channel_data = channel_store.get_channel(channel_name)
                if channel_data:
                    channel_data['channel_id'] = resolved_id
                    channel_store.save_channel(channel_name, channel_data)
                else:
                    # 创建新的频道记录，使用add_channel方法确保一致的键格式
                    new_channel = {
                        'channel_name': channel_name,
                        'channel_id': resolved_id,
                        'channel_type': channel_type,
                        'is_active': True
                    }
                    # 使用add_channel方法以确保一致的键格式和重复检查
                    channel_store.add_channel(new_channel)
                
                return resolved_id
            
            return None
            
        except Exception as e:
            logger.error(f"解析并保存频道ID失败 {channel_name}: {e}")
            return None
    
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
            target_channel_id = await self.config_manager.get_config('target.channel_id')
            target_channel = await self.config_manager.get_config('target.channel_link')
            
            if not target_channel_id:
                if target_channel:
                    # 有频道名但没有ID，尝试解析
                    logger.info(f"  - 目标频道 {target_channel} 需要解析ID...")
                    resolved_id = await channel_id_resolver.resolve_channel_id(target_channel)
                    
                    if resolved_id:
                        # 保存解析的ID
                        await self.config_manager.set_config('target.channel_id', resolved_id)
                        result['channel_id'] = resolved_id
                        result['resolved'] = f"目标频道 {target_channel} -> {resolved_id}"
                        logger.info(f"    ✅ 解析成功: {resolved_id}")
                    else:
                        result['error'] = f"目标频道 {target_channel} ID解析失败"
                        logger.error(f"    ❌ 解析失败")
                else:
                    result['error'] = "未配置目标频道"
                    logger.error("  - 未配置目标频道")
            else:
                # 🔧 优化：如果已有有效ID，无需重新解析
                if target_channel_id.startswith('-100'):
                    # 已有有效的频道ID，直接使用
                    result['channel_id'] = target_channel_id
                    result['status'] = f"目标频道ID已缓存: {target_channel_id}"
                    logger.info(f"    ✅ 使用已缓存ID: {target_channel_id}")
                else:
                    # ID格式不正确，需要解析
                    logger.info(f"  - 目标频道 {target_channel} 需要解析ID...")
                    resolved_id = await channel_id_resolver.resolve_channel_id(target_channel)
                    
                    if resolved_id:
                        # 保存解析的ID，同时保存原始名称
                        await self.config_manager.set_config('target.channel_id', resolved_id)
                        if target_channel.startswith('@'):
                            await self.config_manager.set_config('target.channel_link', target_channel)
                        result['channel_id'] = resolved_id
                        result['resolved'] = f"目标频道 {target_channel} -> {resolved_id}"
                        logger.info(f"    ✅ 解析成功: {resolved_id}")
                    else:
                        result['error'] = f"目标频道 {target_channel} ID解析失败"
                        logger.error(f"    ❌ 解析失败")
                
        except Exception as e:
            result['error'] = f"检查目标频道失败: {str(e)}"
            
        return result
    
    
    async def _check_telegram_auth(self) -> Dict:
        """检查Telegram双Session认证和存储系统状态"""
        result = {
            'authenticated': False,
            'error': None,
            'warning': None
        }
        
        try:
            # 检查共用API凭据
            api_id = await self.config_manager.get_config('telegram.api_id')
            api_hash = await self.config_manager.get_config('telegram.api_hash')
            
            # 检查双Session配置
            listener_session = await self.config_manager.get_config('telegram.listener_session')
            sender_session = await self.config_manager.get_config('telegram.sender_session')
            
            if not api_id or not api_hash:
                result['error'] = "缺少Telegram API凭据"
                logger.error("  - 缺少API ID或API Hash")
            elif not listener_session and not sender_session:
                result['warning'] = "未完成Telegram认证，请访问 /telegram-auth.html 进行认证"
                logger.warning("  - 未找到任何会话信息（listener和sender都未配置）")
            elif not listener_session:
                result['warning'] = "监听Session未配置，消息采集功能不可用"
                logger.warning("  - 未找到listener会话信息")
            elif not sender_session:
                result['warning'] = "发送Session未配置，部分功能可能受限"
                logger.warning("  - 未找到sender会话信息")
            else:
                result['authenticated'] = True
                logger.info("  - Telegram认证状态: ✅ 双Session已认证")
            
            # 检查存储系统状态
            await self._check_storage_system()
                
        except Exception as e:
            result['error'] = f"检查Telegram认证失败: {str(e)}"
            
        return result
    
    async def _check_storage_system(self) -> Dict:
        """检查存储系统状态"""
        result = {
            'redis_available': False,
            'json_available': False,
            'errors': [],
            'warnings': []
        }
        
        try:
            # 检查 Redis 连接
            try:
                redis_store = redis_manager
                redis_manager.client.ping()
                result['redis_available'] = True
                logger.info("  - Redis存储: ✅ 连接正常")
            except Exception as e:
                result['errors'].append(f"Redis连接失败: {str(e)}")
                logger.error(f"  - Redis存储: ❌ 连接失败 - {e}")
            
            # 检查 JSON 存储
            try:
                channel_store = get_json_channel_store()
                # 尝试读取配置文件
                channel_store.get_all_channels()
                result['json_available'] = True
                logger.info("  - JSON存储: ✅ 文件系统正常")
            except Exception as e:
                result['errors'].append(f"JSON存储失败: {str(e)}")
                logger.error(f"  - JSON存储: ❌ 文件系统错误 - {e}")
            
            return result
            
        except Exception as e:
            logger.error(f"检查存储系统失败: {e}")
            result['errors'].append(f"存储系统检查失败: {str(e)}")
            return result

    def _check_json_integrity(self) -> Dict:
        """检查关键JSON文件的完整性"""
        result = {
            'success': True,
            'errors': [],
            'warnings': []
        }
        
        logger.info("📋 检查JSON文件完整性...")
        
        for file_path in self.critical_json_files:
            path = Path(file_path)
            
            if not path.exists():
                error = f"关键配置文件不存在: {file_path}"
                result['errors'].append(error)
                result['success'] = False
                logger.error(f"  - ❌ {error}")
                continue
            
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    json.load(f)
                logger.info(f"  - ✅ {path.name} 格式正确")
                
            except json.JSONDecodeError as e:
                error = f"{path.name} JSON格式错误: {e}"
                result['errors'].append(error)
                result['success'] = False
                logger.error(f"  - ❌ {error}")
                
                # 尝试自动修复
                logger.info(f"  - 🔧 尝试自动修复 {path.name}...")
                if self._try_fix_json_file(path):
                    logger.info(f"  - ✅ {path.name} 自动修复成功")
                    result['warnings'].append(f"{path.name} 已自动修复")
                    result['success'] = True  # 修复后继续
                else:
                    logger.error(f"  - ❌ {path.name} 自动修复失败")
                    
            except Exception as e:
                error = f"读取 {path.name} 失败: {e}"
                result['errors'].append(error)
                result['success'] = False
                logger.error(f"  - ❌ {error}")
        
        return result
    
    def _try_fix_json_file(self, file_path: Path) -> bool:
        """尝试修复JSON文件的常见格式错误"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 修复trailing comma
            import re
            fixed_content = re.sub(r',(\s*})', r'\1', content)
            fixed_content = re.sub(r',(\s*])', r'\1', fixed_content)
            
            # 验证修复后的JSON
            data = json.loads(fixed_content)
            
            # 备份原文件
            backup_path = file_path.with_suffix('.json.bak')
            import shutil
            shutil.copy2(file_path, backup_path)
            
            # 保存修复后的文件
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"  - 📦 已备份原文件到: {backup_path}")
            return True
            
        except Exception as e:
            logger.error(f"  - 修复失败: {e}")
            return False

# 创建全局实例
startup_checker = StartupChecker()