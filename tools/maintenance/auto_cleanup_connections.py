#!/usr/bin/env python3
"""
自动清理 CLOSE-WAIT 连接的监控脚本
当 CLOSE-WAIT 连接数量过多时自动重启 web 服务
"""

import subprocess
import time
import os
import sys
import logging
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/connection_cleanup.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def count_close_wait_connections(port=8008):
    """统计指定端口的 CLOSE-WAIT 连接数"""
    try:
        result = subprocess.run(
            ['ss', '-ant'],
            capture_output=True,
            text=True,
            check=True
        )

        lines = result.stdout.split('\n')
        close_wait_count = 0

        for line in lines:
            if f'{port}' in line and 'CLOSE-WAIT' in line:
                close_wait_count += 1

        return close_wait_count
    except subprocess.CalledProcessError as e:
        logger.error(f"检查连接状态失败: {e}")
        return 0

def check_service_health(port=8008):
    """检查服务健康状态"""
    try:
        result = subprocess.run(
            ['curl', '-f', '--max-time', '3', f'http://localhost:{port}/api/health'],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False

def restart_web_service():
    """重启 web 服务"""
    logger.info("🔄 检测到服务异常，正在重启...")

    try:
        # 停止服务
        subprocess.run(['./stop.sh'], check=True, capture_output=True)
        time.sleep(3)

        # 启动服务
        subprocess.Popen(['./dev.sh', 'web'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(5)

        # 验证启动
        if check_service_health():
            logger.info("✅ 服务重启成功")
            return True
        else:
            logger.error("❌ 服务重启失败")
            return False

    except subprocess.CalledProcessError as e:
        logger.error(f"重启服务失败: {e}")
        return False

def main():
    """主监控循环"""
    logger.info("🚀 启动连接清理监控服务...")

    # 配置参数
    CHECK_INTERVAL = 30  # 检查间隔（秒）
    MAX_CLOSE_WAIT = 5   # 最大允许的 CLOSE-WAIT 连接数
    MAX_UNHEALTHY_COUNT = 3  # 连续不健康次数阈值

    unhealthy_count = 0

    try:
        while True:
            close_wait_count = count_close_wait_connections()
            is_healthy = check_service_health()

            logger.debug(f"CLOSE-WAIT 连接数: {close_wait_count}, 服务健康: {is_healthy}")

            # 检查是否需要重启
            should_restart = False
            restart_reason = ""

            if close_wait_count > MAX_CLOSE_WAIT:
                should_restart = True
                restart_reason = f"CLOSE-WAIT 连接过多 ({close_wait_count} > {MAX_CLOSE_WAIT})"

            if not is_healthy:
                unhealthy_count += 1
                if unhealthy_count >= MAX_UNHEALTHY_COUNT:
                    should_restart = True
                    restart_reason = f"服务连续 {unhealthy_count} 次健康检查失败"
            else:
                unhealthy_count = 0

            # 执行重启
            if should_restart:
                logger.warning(f"⚠️ {restart_reason}")
                if restart_web_service():
                    unhealthy_count = 0
                    time.sleep(10)  # 重启后等待更长时间
                else:
                    logger.error("重启失败，等待下次检查...")

            time.sleep(CHECK_INTERVAL)

    except KeyboardInterrupt:
        logger.info("🛑 监控服务已停止")
    except Exception as e:
        logger.error(f"监控服务异常: {e}")

if __name__ == "__main__":
    # 确保在项目根目录运行
    os.chdir(Path(__file__).parent.parent.parent)
    main()