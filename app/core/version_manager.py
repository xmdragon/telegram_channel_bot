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
    
    def __init__(self, version_file: str = "data/config/frontend_version.txt"):
        """
        初始化版本管理器
        
        Args:
            version_file: 版本号存储文件路径
        """
        self.version_file = Path(version_file)
        self.version_file.parent.mkdir(parents=True, exist_ok=True)
        self._current_version: Optional[str] = None
    
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
        保存版本号到文件
        
        Args:
            version: 要保存的版本号
        """
        try:
            self.version_file.write_text(version.strip(), encoding='utf-8')
            self._current_version = version
            logger.info(f"版本号已保存到 {self.version_file}: {version}")
        except Exception as e:
            logger.error(f"保存版本号失败: {e}")
            # 如果保存失败，仍然使用内存中的版本
            self._current_version = version
    
    def load_version(self) -> Optional[str]:
        """
        从文件加载版本号
        
        Returns:
            str: 加载的版本号，如果文件不存在则返回None
        """
        try:
            if self.version_file.exists():
                version = self.version_file.read_text(encoding='utf-8').strip()
                logger.info(f"从文件加载版本号: {version}")
                return version
        except Exception as e:
            logger.warning(f"加载版本号失败: {e}")
        return None
    
    def get_current_version(self) -> str:
        """
        获取当前版本号
        
        Returns:
            str: 当前版本号
        """
        if self._current_version is None:
            # 尝试从文件加载
            self._current_version = self.load_version()
            
            # 如果文件不存在或加载失败，生成新版本号
            if self._current_version is None:
                self._current_version = self.generate_version()
                self.save_version(self._current_version)
        
        return self._current_version
    
    def refresh_version(self) -> str:
        """
        刷新版本号（生成新的版本号）
        
        Returns:
            str: 新的版本号
        """
        new_version = self.generate_version()
        self.save_version(new_version)
        logger.info(f"版本号已刷新: {self._current_version} -> {new_version}")
        return new_version
    
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