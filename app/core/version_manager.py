"""
版本号管理模块
用于生成和管理前端资源的版本号，防止缓存问题
"""
import time
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)

class VersionManager:
    """版本号管理器"""
    
    def __init__(self):
        """
        初始化版本管理器
        使用system.json统一配置管理
        """
        self._current_version: Optional[str] = None
        self._config_manager = None
    
    def _get_config_manager(self):
        """获取配置管理器实例"""
        if self._config_manager is None:
            try:
                from app.services.config_manager import get_config_manager
                self._config_manager = get_config_manager()
            except Exception as e:
                logger.error(f"获取配置管理器失败: {e}")
        return self._config_manager
    
    def generate_version(self) -> str:
        """
        生成新的版本号（基于时间戳）
        
        Returns:
            str: 新生成的版本号
        """
        version = str(int(time.time()))
        logger.info(f"生成新版本号: {version}")
        return version
    
    def save_version(self, version: str) -> None:
        """
        保存版本号到system.json配置
        
        Args:
            version: 要保存的版本号
        """
        try:
            config_manager = self._get_config_manager()
            if config_manager:
                # 更新auto_version字段
                config_manager.set_config('system.auto_version', version, config_type='string', 
                                        description='系统自动生成的版本号')
                self._current_version = None  # 重置缓存，强制重新获取
                logger.info(f"版本号已保存到system.json: {version}")
            else:
                # 如果配置管理器不可用，仍然使用内存中的版本
                self._current_version = version
                logger.warning(f"配置管理器不可用，使用内存版本号: {version}")
        except Exception as e:
            logger.error(f"保存版本号失败: {e}")
            # 如果保存失败，仍然使用内存中的版本
            self._current_version = version
    
    def load_version(self) -> Optional[str]:
        """
        从system.json加载版本号
        优先级：手动设置的version > 自动生成的auto_version
        
        Returns:
            str: 加载的版本号，如果都不存在则返回None
        """
        try:
            config_manager = self._get_config_manager()
            if config_manager:
                # 优先使用手动设置的version
                manual_version = config_manager.get_config('system.version')
                if manual_version and manual_version.strip():
                    logger.info(f"使用手动设置的版本号: {manual_version}")
                    return manual_version.strip()
                
                # 如果没有手动设置，使用auto_version
                auto_version = config_manager.get_config('system.auto_version')
                if auto_version and auto_version.strip():
                    logger.info(f"使用自动生成的版本号: {auto_version}")
                    return auto_version.strip()
        except Exception as e:
            logger.warning(f"从配置加载版本号失败: {e}")
        return None
    
    def get_current_version(self) -> str:
        """
        获取当前版本号
        优先级：手动设置的version > 自动生成的auto_version > 新生成版本号
        
        Returns:
            str: 当前版本号
        """
        if self._current_version is None:
            # 尝试从配置加载
            self._current_version = self.load_version()
            
            # 如果配置中都不存在，生成新版本号
            if self._current_version is None:
                self._current_version = self.generate_version()
                self.save_version(self._current_version)
        
        return self._current_version
    
    def refresh_version(self) -> str:
        """
        刷新版本号（生成新的版本号并保存到auto_version）
        
        Returns:
            str: 新的版本号
        """
        old_version = self._current_version
        new_version = self.generate_version()
        self.save_version(new_version)
        logger.info(f"版本号已刷新: {old_version} -> {new_version}")
        return new_version
    
    def set_manual_version(self, version: str) -> bool:
        """
        设置手动版本号（保存到system.version）
        
        Args:
            version: 手动设置的版本号
            
        Returns:
            bool: 设置是否成功
        """
        try:
            config_manager = self._get_config_manager()
            if config_manager:
                config_manager.set_config('system.version', version.strip(), config_type='string', 
                                        description='手动设置的前端资源版本号')
                self._current_version = None  # 重置缓存，强制重新获取
                logger.info(f"手动版本号已设置: {version}")
                return True
            else:
                logger.error("配置管理器不可用，无法设置手动版本号")
                return False
        except Exception as e:
            logger.error(f"设置手动版本号失败: {e}")
            return False
    
    def clear_manual_version(self) -> bool:
        """
        清除手动设置的版本号（删除system.version配置项）
        
        Returns:
            bool: 清除是否成功
        """
        try:
            config_manager = self._get_config_manager()
            if config_manager:
                config_manager.delete_config('system.version')
                self._current_version = None  # 重置缓存，强制重新获取
                logger.info("手动版本号已清除，将使用自动生成的版本号")
                return True
            else:
                logger.error("配置管理器不可用，无法清除手动版本号")
                return False
        except Exception as e:
            logger.error(f"清除手动版本号失败: {e}")
            return False
    
    def update_html_files(self, html_dir: str = "static") -> int:
        """
        更新所有HTML文件中的版本号
        
        Args:
            html_dir: HTML文件目录
            
        Returns:
            int: 更新的文件数量
        """
        import re
        import os
        
        current_version = self.get_current_version()
        html_dir_path = Path(html_dir)
        
        if not html_dir_path.exists():
            logger.warning(f"HTML目录不存在: {html_dir_path}")
            return 0
        
        updated_count = 0
        version_pattern = re.compile(r'\?v=\d+')
        new_version_param = f'?v={current_version}'
        
        for html_file in html_dir_path.glob('*.html'):
            try:
                # 读取文件内容
                content = html_file.read_text(encoding='utf-8')
                
                # 替换版本号
                new_content = version_pattern.sub(new_version_param, content)
                
                # 如果有变化，写回文件
                if new_content != content:
                    html_file.write_text(new_content, encoding='utf-8')
                    updated_count += 1
                    logger.debug(f"已更新HTML文件版本号: {html_file.name}")
                
            except Exception as e:
                logger.error(f"更新HTML文件失败 {html_file}: {e}")
        
        if updated_count > 0:
            logger.info(f"已更新 {updated_count} 个HTML文件的版本号为: {current_version}")
        
        return updated_count

# 全局版本管理器实例
version_manager = VersionManager()

def get_version_manager() -> VersionManager:
    """获取全局版本管理器实例"""
    return version_manager

def get_frontend_version() -> str:
    """获取前端资源版本号"""
    return version_manager.get_current_version()