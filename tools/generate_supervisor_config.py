#!/usr/bin/env python3
"""
生成Supervisor配置文件
自动检测虚拟环境和路径
"""
import sys
import os
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.supervisor_config import SupervisorConfig


def main():
    """生成Supervisor配置文件"""
    try:
        print("🔧 正在生成Supervisor配置文件...")

        # 生成配置
        conf = SupervisorConfig.generate_supervisor_conf()

        # 写入文件
        config_path = Path(__file__).parent.parent / 'config' / 'supervisord.conf'
        config_path.parent.mkdir(exist_ok=True)

        with open(config_path, 'w') as f:
            f.write(conf)

        print(f"✅ 配置文件已生成: {config_path}")

        # 显示关键信息
        import re
        matches = re.findall(r'command=([^\s]+python3?)', conf)
        if matches:
            print(f"📍 使用的Python: {matches[0]}")

        # 检查虚拟环境
        root_dir = Path(__file__).parent.parent.resolve()
        venv_dir = root_dir / 'venv'
        venv_alt_dir = root_dir / '.venv'

        if venv_dir.exists():
            print(f"🐍 检测到虚拟环境: {venv_dir}")
        elif venv_alt_dir.exists():
            print(f"🐍 检测到虚拟环境: {venv_alt_dir}")
        else:
            print("⚠️  未检测到虚拟环境，使用系统Python")

        print(f"📂 项目路径: {root_dir}")

        return True

    except Exception as e:
        print(f"❌ 生成配置失败: {e}")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)