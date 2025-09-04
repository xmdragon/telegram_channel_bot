#!/usr/bin/env python3
"""
Colima健康检查和自动恢复脚本
用于监控Colima状态并在崩溃时自动重启
"""

import subprocess
import time
import logging
import sys
import os
from datetime import datetime
from pathlib import Path

# 配置日志
log_dir = Path(__file__).parent.parent.parent / "logs"
log_dir.mkdir(exist_ok=True)
log_file = log_dir / "colima_health.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

class ColimaHealthChecker:
    """Colima健康检查器"""
    
    def __init__(self, check_interval=30, max_restart_attempts=3):
        """
        初始化健康检查器
        
        Args:
            check_interval: 检查间隔（秒）
            max_restart_attempts: 最大重启尝试次数
        """
        self.check_interval = check_interval
        self.max_restart_attempts = max_restart_attempts
        self.restart_count = 0
        self.last_restart_time = None
        
    def check_colima_status(self):
        """检查Colima运行状态"""
        try:
            result = subprocess.run(
                ['colima', 'status'],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            # 合并stdout和stderr的输出进行检查
            combined_output = result.stdout + result.stderr
            
            # 检查输出中是否包含运行状态（不区分大小写）
            if 'running' in combined_output.lower():
                return True
            else:
                logger.warning(f"Colima状态异常: {combined_output[:100]}")
                return False
                
        except subprocess.TimeoutExpired:
            logger.error("Colima状态检查超时")
            return False
        except FileNotFoundError:
            logger.error("找不到colima命令，请确保已安装")
            return False
        except Exception as e:
            logger.error(f"检查Colima状态时出错: {e}")
            return False
    
    def check_docker_status(self):
        """检查Docker是否可用"""
        try:
            result = subprocess.run(
                ['docker', 'ps'],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0
        except:
            return False
    
    def restart_colima(self):
        """重启Colima"""
        if self.restart_count >= self.max_restart_attempts:
            # 重置计数器（如果距离上次重启超过1小时）
            if self.last_restart_time:
                time_since_last = time.time() - self.last_restart_time
                if time_since_last > 3600:  # 1小时
                    self.restart_count = 0
                    logger.info("重置重启计数器（距离上次重启超过1小时）")
                else:
                    logger.error(f"已达到最大重启次数 {self.max_restart_attempts}")
                    return False
        
        try:
            logger.info(f"开始重启Colima (尝试 {self.restart_count + 1}/{self.max_restart_attempts})")
            
            # 停止Colima
            subprocess.run(['colima', 'stop'], timeout=30, capture_output=True)
            time.sleep(5)
            
            # 启动Colima
            result = subprocess.run(
                ['colima', 'start'],
                capture_output=True,
                text=True,
                timeout=120
            )
            
            if result.returncode == 0:
                logger.info("Colima重启成功")
                self.restart_count += 1
                self.last_restart_time = time.time()
                
                # 等待Docker完全就绪
                time.sleep(10)
                
                # 验证Docker是否正常工作
                if self.check_docker_status():
                    logger.info("Docker服务已就绪")
                    
                    # 重启项目容器
                    self.restart_project_containers()
                    return True
                else:
                    logger.warning("Docker服务未就绪")
                    return False
            else:
                logger.error(f"Colima重启失败: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            logger.error("Colima重启超时")
            return False
        except Exception as e:
            logger.error(f"重启Colima时出错: {e}")
            return False
    
    def restart_project_containers(self):
        """重启项目容器"""
        try:
            project_dir = Path(__file__).parent.parent.parent
            
            # 切换到项目目录
            os.chdir(project_dir)
            
            # 重启docker-compose服务
            logger.info("重启项目容器...")
            result = subprocess.run(
                ['docker', 'compose', 'restart'],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                logger.info("项目容器重启成功")
            else:
                logger.warning(f"项目容器重启失败: {result.stderr}")
                
        except Exception as e:
            logger.error(f"重启项目容器时出错: {e}")
    
    def clean_temp_files(self):
        """清理临时文件（减少文件监听负担）"""
        try:
            temp_media_dir = Path(__file__).parent.parent.parent / "temp_media"
            if temp_media_dir.exists():
                # 获取文件数量
                file_count = len(list(temp_media_dir.glob("*")))
                
                if file_count > 100:  # 超过100个文件时清理
                    logger.info(f"清理临时媒体文件（当前: {file_count}个）")
                    
                    # 删除超过1小时的文件
                    current_time = time.time()
                    deleted_count = 0
                    
                    for file_path in temp_media_dir.glob("*"):
                        if file_path.is_file():
                            file_age = current_time - file_path.stat().st_mtime
                            if file_age > 3600:  # 1小时
                                file_path.unlink()
                                deleted_count += 1
                    
                    if deleted_count > 0:
                        logger.info(f"已清理 {deleted_count} 个旧临时文件")
                        
        except Exception as e:
            logger.error(f"清理临时文件时出错: {e}")
    
    def run(self):
        """运行健康检查循环"""
        logger.info("Colima健康检查器启动")
        logger.info(f"检查间隔: {self.check_interval}秒")
        logger.info(f"最大重启次数: {self.max_restart_attempts}")
        
        consecutive_failures = 0
        
        while True:
            try:
                # 检查Colima状态
                if self.check_colima_status():
                    # 进一步检查Docker状态
                    if self.check_docker_status():
                        if consecutive_failures > 0:
                            logger.info("服务已恢复正常")
                        consecutive_failures = 0
                        
                        # 每10个周期输出一次状态
                        if not hasattr(self, '_check_count'):
                            self._check_count = 0
                        self._check_count += 1
                        if self._check_count % 10 == 0:
                            logger.info(f"系统运行正常 (已检查{self._check_count}次)")
                        
                        # 定期清理临时文件
                        if time.time() % 3600 < self.check_interval:
                            self.clean_temp_files()
                    else:
                        consecutive_failures += 1
                        logger.warning(f"Docker不可用 (连续失败: {consecutive_failures})")
                        
                        if consecutive_failures >= 2:
                            logger.info("尝试重启Colima...")
                            if self.restart_colima():
                                consecutive_failures = 0
                else:
                    consecutive_failures += 1
                    logger.warning(f"Colima未运行 (连续失败: {consecutive_failures})")
                    
                    if consecutive_failures >= 2:
                        logger.info("尝试启动Colima...")
                        if self.restart_colima():
                            consecutive_failures = 0
                
                # 等待下次检查
                time.sleep(self.check_interval)
                
            except KeyboardInterrupt:
                logger.info("收到停止信号，退出健康检查")
                break
            except Exception as e:
                logger.error(f"健康检查循环出错: {e}")
                time.sleep(self.check_interval)

def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Colima健康检查和自动恢复")
    parser.add_argument(
        '--interval',
        type=int,
        default=30,
        help='检查间隔（秒），默认30秒'
    )
    parser.add_argument(
        '--max-restarts',
        type=int,
        default=3,
        help='最大重启次数，默认3次'
    )
    parser.add_argument(
        '--daemon',
        action='store_true',
        help='以守护进程方式运行'
    )
    
    args = parser.parse_args()
    
    if args.daemon:
        # 创建守护进程
        try:
            pid = os.fork()
            if pid > 0:
                print(f"健康检查器已在后台运行 (PID: {pid})")
                sys.exit(0)
        except OSError as e:
            logger.error(f"无法创建守护进程: {e}")
            sys.exit(1)
    
    # 创建并运行健康检查器
    checker = ColimaHealthChecker(
        check_interval=args.interval,
        max_restart_attempts=args.max_restarts
    )
    checker.run()

if __name__ == "__main__":
    main()