#!/usr/bin/env python3
"""
Docker 环境测试脚本
"""
import os
import sys
import subprocess
import time
import urllib.request
import urllib.error
from pathlib import Path

def run_command(command, check=True):
    """运行命令"""
    print(f"🔄 执行: {command}")
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    
    if result.stdout:
        print(f"📤 输出: {result.stdout}")
    
    if result.stderr:
        print(f"⚠️  错误: {result.stderr}")
    
    if check and result.returncode != 0:
        print(f"❌ 命令失败: {command}")
        return False
    
    return True

def test_docker_environment():
    """测试 Docker 环境"""
    print("🧪 测试 Docker 环境")
    print("=" * 50)
    
    # 检查 Docker 是否安装
    print("\n1️⃣ 检查 Docker 安装...")
    if not run_command("docker --version", check=False):
        print("❌ Docker 未安装或未在 PATH 中")
        return False
    print("✅ Docker 已安装")
    
    # 检查 Docker Compose 是否安装
    print("\n2️⃣ 检查 Docker Compose...")
    if not run_command("docker compose version", check=False):
        print("❌ Docker Compose 未安装")
        return False
    print("✅ Docker Compose 已安装")
    
    # 检查项目文件
    print("\n3️⃣ 检查项目文件...")
    required_files = [
        "Dockerfile",
        "docker-compose.yml",
        "requirements.txt",
        "main.py"
    ]
    
    for file in required_files:
        if not Path(file).exists():
            print(f"❌ 缺少文件: {file}")
            return False
    print("✅ 项目文件完整")
    
    # 构建镜像
    print("\n4️⃣ 构建 Docker 镜像...")
    if not run_command("docker compose build"):
        print("❌ 镜像构建失败")
        return False
    print("✅ 镜像构建成功")
    
    # 启动服务
    print("\n5️⃣ 启动服务...")
    if not run_command("docker compose up -d"):
        print("❌ 服务启动失败")
        return False
    print("✅ 服务启动成功")
    
    # 等待服务启动
    print("\n6️⃣ 等待服务启动...")
    time.sleep(10)
    
    # 检查服务状态
    print("\n7️⃣ 检查服务状态...")
    if not run_command("docker compose ps"):
        print("❌ 服务状态检查失败")
        return False
    
    # 测试 API 连接
    print("\n8️⃣ 测试 API 连接...")
    try:
        with urllib.request.urlopen("http://localhost:8000/status", timeout=10) as response:
            if response.getcode() == 200:
                print("✅ API 连接成功")
            else:
                print(f"⚠️  API 响应异常: {response.getcode()}")
    except Exception as e:
        print(f"❌ API 连接失败: {e}")
        return False
    
    # 检查日志
    print("\n9️⃣ 检查应用日志...")
    if not run_command("docker compose logs app | tail -10"):
        print("⚠️  无法查看日志")
    
    print("\n🎉 Docker 环境测试完成!")
    print("\n📝 下一步:")
    print("1. 访问 http://localhost:8000/status 检查系统状态")
    print("2. 访问 http://localhost:8000/auth 进行 Telegram 登录")
    print("3. 配置频道设置")
    print("4. 开始使用系统")
    
    return True

def cleanup():
    """清理测试环境"""
    print("\n🧹 清理测试环境...")
    run_command("docker compose down", check=False)
    print("✅ 清理完成")

def main():
    """主函数"""
    try:
        success = test_docker_environment()
        
        if success:
            print("\n✅ Docker 环境测试通过!")
                    print("\n💡 提示:")
        print("- 使用 'docker compose logs -f app' 查看实时日志")
        print("- 使用 'docker compose down' 停止服务")
        print("- 使用 'docker compose up -d' 重新启动服务")
        else:
            print("\n❌ Docker 环境测试失败!")
            cleanup()
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n\n❌ 测试已取消")
        cleanup()
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        cleanup()
        sys.exit(1)

if __name__ == "__main__":
    main() 