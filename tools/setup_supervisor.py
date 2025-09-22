#!/usr/bin/env python3
"""
Supervisor配置生成和安装工具
用于生成Supervisor配置文件并安装到系统
"""
import sys
import os
import subprocess
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.supervisor_config import SupervisorConfig
from app.core.path_config import PathConfig

def check_supervisor_installed():
    """检查Supervisor是否已安装"""
    try:
        result = subprocess.run(['which', 'supervisorctl'], capture_output=True, text=True)
        return result.returncode == 0
    except:
        return False

def generate_config():
    """生成配置文件"""
    print("📝 生成Supervisor配置...")

    # 生成配置内容
    config_content = SupervisorConfig.generate_supervisor_conf()

    # 确保本地配置目录存在
    local_conf_path = SupervisorConfig.get_local_conf_path()
    local_conf_path.parent.mkdir(parents=True, exist_ok=True)

    # 保存到本地
    local_conf_path.write_text(config_content)
    print(f"✅ 配置已生成: {local_conf_path}")

    # 显示配置内容摘要
    print("\n📋 配置摘要:")
    print(f"  - 管理端口: {SupervisorConfig.SUPERVISOR_HOST}:{SupervisorConfig.SUPERVISOR_PORT}")
    print(f"  - 用户名: {SupervisorConfig.SUPERVISOR_USER}")
    print(f"  - 服务组: telegram")
    print(f"  - 包含服务:")
    for short_name, full_name in SupervisorConfig.SERVICE_MAPPING.items():
        info = SupervisorConfig.SERVICE_INFO.get(short_name, {})
        print(f"    - {full_name}: {info.get('description', '无描述')}")

    return config_content

def install_config(config_content=None):
    """安装配置到系统"""
    if not check_supervisor_installed():
        print("❌ Supervisor未安装")
        print("请先运行: sudo apt-get install supervisor")
        return False

    if config_content is None:
        config_content = generate_config()

    # 获取目标路径
    target_path = SupervisorConfig.get_supervisor_conf_path()
    print(f"\n📝 安装配置到: {target_path}")

    # 检查目标目录是否存在
    if not target_path.parent.exists():
        print(f"❌ 目标目录不存在: {target_path.parent}")
        print("请检查Supervisor安装是否正确")
        return False

    # 写入配置文件（需要sudo权限）
    try:
        # 先写入临时文件
        temp_file = Path('/tmp/telegram_bot_supervisor.conf')
        temp_file.write_text(config_content)

        # 使用sudo复制到目标位置
        cmd = f"sudo cp {temp_file} {target_path}"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

        if result.returncode != 0:
            print(f"❌ 安装失败: {result.stderr}")
            return False

        print("✅ 配置文件已安装")

        # 设置正确的权限
        subprocess.run(f"sudo chmod 644 {target_path}", shell=True)

        # 删除临时文件
        temp_file.unlink()

    except Exception as e:
        print(f"❌ 安装配置时出错: {e}")
        return False

    # 重载Supervisor配置
    print("\n🔄 重载Supervisor配置...")
    try:
        # reread - 读取新配置
        result = subprocess.run("sudo supervisorctl reread", shell=True, capture_output=True, text=True)
        print(f"  重读配置: {result.stdout.strip()}")

        # update - 更新配置
        result = subprocess.run("sudo supervisorctl update", shell=True, capture_output=True, text=True)
        print(f"  更新配置: {result.stdout.strip()}")

        print("✅ Supervisor配置已重载")
        return True

    except Exception as e:
        print(f"❌ 重载配置失败: {e}")
        return False

def check_services_status():
    """检查服务状态"""
    print("\n📊 检查服务状态...")
    try:
        result = subprocess.run("sudo supervisorctl status telegram:*", shell=True, capture_output=True, text=True)
        if result.stdout:
            print(result.stdout)
        else:
            print("暂无服务状态信息")
    except Exception as e:
        print(f"❌ 检查状态失败: {e}")

def start_services():
    """启动所有服务"""
    print("\n🚀 启动所有服务...")
    try:
        result = subprocess.run("sudo supervisorctl start telegram:*", shell=True, capture_output=True, text=True)
        print(result.stdout.strip() if result.stdout else "✅ 服务启动命令已执行")
        return result.returncode == 0
    except Exception as e:
        print(f"❌ 启动服务失败: {e}")
        return False

def uninstall_config():
    """卸载配置"""
    print("🗑️ 卸载Supervisor配置...")

    target_path = SupervisorConfig.get_supervisor_conf_path()

    # 先停止服务
    print("  停止服务...")
    subprocess.run("sudo supervisorctl stop telegram:*", shell=True)

    # 删除配置文件
    if target_path.exists():
        try:
            subprocess.run(f"sudo rm {target_path}", shell=True)
            print(f"  ✅ 已删除: {target_path}")
        except:
            print(f"  ❌ 删除失败: {target_path}")

    # 重载配置
    subprocess.run("sudo supervisorctl reread", shell=True)
    subprocess.run("sudo supervisorctl update", shell=True)

    print("✅ 配置已卸载")

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Supervisor配置管理工具")
    parser.add_argument('--generate', action='store_true', help='仅生成配置文件')
    parser.add_argument('--install', action='store_true', help='生成并安装配置到系统')
    parser.add_argument('--start', action='store_true', help='安装配置并启动服务')
    parser.add_argument('--status', action='store_true', help='检查服务状态')
    parser.add_argument('--uninstall', action='store_true', help='卸载配置')

    args = parser.parse_args()

    # 确保必要的目录存在
    PathConfig.ensure_directories()

    if args.uninstall:
        uninstall_config()
    elif args.status:
        check_services_status()
    elif args.start:
        # 安装并启动
        config_content = generate_config()
        if install_config(config_content):
            start_services()
            check_services_status()
    elif args.install:
        # 仅安装
        install_config()
        check_services_status()
    else:
        # 默认只生成
        generate_config()
        print("\n💡 提示:")
        print("  - 使用 --install 安装到系统")
        print("  - 使用 --start 安装并启动服务")
        print("  - 使用 --status 查看服务状态")

if __name__ == "__main__":
    main()