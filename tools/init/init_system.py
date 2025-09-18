#!/usr/bin/env python3
"""
系统初始化工具 - 统一的存储和管理员初始化
合并了存储系统初始化和管理员管理功能
"""
import asyncio
import os
import json
import logging
import getpass
import bcrypt
from pathlib import Path
from datetime import datetime
import sys

# 动态路径检测，避免硬编码
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.url_config import url_config
from app.storage.redis_manager import redis_manager
from app.storage.json_store import init_json_stores, get_json_user_store
from app.services.config_manager import config_manager
from app.core.path_config import PathConfig

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class SystemInitializer:
    """系统初始化器"""

    def __init__(self):
        self.initialized_components = []

    async def init_default_configs(self):
        """初始化默认配置"""

        DEFAULT_CONFIGS = {


            # 过滤配置
            "filter.enabled": {
                "value": "true",
                "config_type": "boolean",
                "description": "启用内容过滤",
                "category": "filter"
            },
            "filter.tail_filter": {
                "value": "true",
                "config_type": "boolean",
                "description": "启用尾部过滤",
                "category": "filter"
            },
            "filter.separator": {
                "value": "true",
                "config_type": "boolean",
                "description": "启用分隔符过滤",
                "category": "filter"
            },
            "filter.markdown": {
                "value": "true",
                "config_type": "boolean",
                "description": "启用Markdown格式过滤",
                "category": "filter"
            },
            "filter.ad_detector": {
                "value": "true",
                "config_type": "boolean",
                "description": "启用广告检测器",
                "category": "filter"
            },

            # 审核配置
            "review.auto_forward_delay": {
                "value": "1800",
                "config_type": "integer",
                "description": "自动转发延时（秒）",
                "category": "review"
            },
            "review.require_approval": {
                "value": "true",
                "config_type": "boolean",
                "description": "需要人工审核",
                "category": "review"
            },
            "review.auto_reject_ads": {
                "value": "true",
                "config_type": "boolean",
                "description": "自动拒绝广告消息",
                "category": "review"
            },
            "review.auto_forward_enabled": {
                "value": "false",
                "config_type": "boolean",
                "description": "启用自动转发",
                "category": "review"
            },
            "review.auto_forward_after_collect": {
                "value": "false",
                "config_type": "boolean",
                "description": "采集消息后自动转发到审核群",
                "category": "review"
            },

            # 采集配置
            "collection.enabled": {
                "value": "true",
                "config_type": "boolean",
                "description": "启用消息采集",
                "category": "collection"
            },
            "collection.max_messages_per_batch": {
                "value": "50",
                "config_type": "integer",
                "description": "每批最大消息数",
                "category": "collection"
            },

            # 调度配置
            "scheduler.enabled": {
                "value": "true",
                "config_type": "boolean",
                "description": "启用消息调度服务（自动转发、清理）",
                "category": "scheduler"
            },
            "scheduler.data_cleanup_interval_hours": {
                "value": "24",
                "config_type": "string",
                "description": "数据清理时间间隔（小时）",
                "category": "scheduler"
            },

            # 系统配置
            "system.log_level": {
                "value": "INFO",
                "config_type": "string",
                "description": "日志级别",
                "category": "system"
            },

            # 存储配置
            "storage.delete_single_messages": {
                "value": "true",
                "config_type": "boolean",
                "description": "组合消息保存后删除单独消息（性能优化，可回滚）",
                "category": "storage"
            },

            # 目标配置
            "target.signature": {
                "value": "🔔 订阅📡东南亚曝光台\\n🔗  t.me/dny9527\\n☎️ 投稿曝料：@stan0505",
                "config_type": "string",
                "description": "频道落款内容（支持多行，用\\\\n分隔）",
                "category": "target"
            },
            "target.channel_link": {
                "value": "@bigeventsinsea",
                "config_type": "string",
                "description": "目标频道链接（用户配置）",
                "category": "target"
            },

            # 审核群配置
            "review.group_link": {
                "value": "https://t.me/+TfGC_XoQ5gllZWY1",
                "config_type": "string",
                "description": "审核群链接（用户配置）",
                "category": "review"
            },

            # Telegram API配置
            "telegram.api_id": {
                "value": "24382238",
                "config_type": "string",
                "description": "Telegram API ID（双Session共用）",
                "category": "telegram"
            },
            "telegram.api_hash": {
                "value": "a926790195b42a472477e7709a74fc24",
                "config_type": "string",
                "description": "Telegram API Hash（双Session共用）",
                "category": "telegram"
            },
            "telegram.sender_session": {
                "value": "",
                "config_type": "string",
                "description": "Telegram Sender Session",
                "category": "telegram"
            },
            "telegram.listener_session": {
                "value": "",
                "config_type": "string",
                "description": "Telegram Listener Session",
                "category": "telegram"
            }
        }

        updated_count = 0
        for key, config in DEFAULT_CONFIGS.items():
            try:
                # 检查是否已存在
                existing = await config_manager.get_config(key)
                if existing is None:
                    success = await config_manager.set_config(
                        key,
                        config["value"],
                        config["description"],
                        config["config_type"]
                    )
                    if success:
                        updated_count += 1
                        logger.debug(f"初始化配置: {key}")
            except Exception as e:
                logger.error(f"初始化配置失败 {key}: {e}")

        if updated_count > 0:
            logger.info(f"✅ 初始化了 {updated_count} 个默认配置")
        else:
            logger.info("ℹ️  配置已存在，跳过初始化")

        self.initialized_components.append(f"配置({updated_count}个)")
        return updated_count

    def init_default_permissions(self):
        """初始化默认权限数据（JSON文件）"""

        PERMISSION_DEFINITIONS = [
            # 消息管理
            {"name": "messages.view", "module": "messages", "action": "view", "description": "查看消息"},
            {"name": "messages.approve", "module": "messages", "action": "approve", "description": "批准消息"},
            {"name": "messages.reject", "module": "messages", "action": "reject", "description": "拒绝消息"},
            {"name": "messages.edit", "module": "messages", "action": "edit", "description": "编辑消息"},
            {"name": "messages.delete", "module": "messages", "action": "delete", "description": "删除消息"},

            # 配置管理
            {"name": "config.view", "module": "config", "action": "view", "description": "查看配置"},
            {"name": "config.edit", "module": "config", "action": "edit", "description": "修改配置"},

            # 频道管理
            {"name": "channels.view", "module": "channels", "action": "view", "description": "查看频道"},
            {"name": "channels.add", "module": "channels", "action": "add", "description": "添加频道"},
            {"name": "channels.edit", "module": "channels", "action": "edit", "description": "编辑频道"},
            {"name": "channels.delete", "module": "channels", "action": "delete", "description": "删除频道"},

            # 训练管理
            {"name": "training.view", "module": "training", "action": "view", "description": "查看训练数据"},
            {"name": "training.submit", "module": "training", "action": "submit", "description": "提交训练数据"},
            {"name": "training.mark_ad", "module": "training", "action": "mark_ad", "description": "标记为广告"},
            {"name": "training.mark_tail", "module": "training", "action": "mark_tail", "description": "标记尾部内容"},
            {"name": "training.manage", "module": "training", "action": "manage", "description": "管理训练数据"},

            # 过滤管理
            {"name": "filter.view", "module": "filter", "action": "view", "description": "查看过滤规则"},
            {"name": "filter.add_keyword", "module": "filter", "action": "add_keyword", "description": "添加过滤关键词"},
            {"name": "filter.execute", "module": "filter", "action": "execute", "description": "执行过滤操作"},
            {"name": "filter.manage", "module": "filter", "action": "manage", "description": "管理过滤规则"},

            # 系统管理
            {"name": "system.view_status", "module": "system", "action": "view_status", "description": "查看系统状态"},
            {"name": "system.view_logs", "module": "system", "action": "view_logs", "description": "查看系统日志"},
            {"name": "system.restart", "module": "system", "action": "restart", "description": "重启系统"},

            # 管理员管理
            {"name": "admin.manage_users", "module": "admin", "action": "manage_users", "description": "管理用户"},
            {"name": "admin.manage_permissions", "module": "admin", "action": "manage_permissions", "description": "管理权限"},
        ]

        permissions_file = PathConfig.PERMISSIONS_CONFIG_FILE
        permissions_file.parent.mkdir(parents=True, exist_ok=True)

        if permissions_file.exists():
            logger.info("ℹ️  权限文件已存在，跳过初始化")
            return 0

        try:
            permissions_data = {
                "permissions": PERMISSION_DEFINITIONS,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }

            with open(permissions_file, 'w', encoding='utf-8') as f:
                json.dump(permissions_data, f, ensure_ascii=False, indent=2)

            logger.info(f"✅ 初始化 {len(PERMISSION_DEFINITIONS)} 个权限项")
            self.initialized_components.append(f"权限({len(PERMISSION_DEFINITIONS)}个)")
            return len(PERMISSION_DEFINITIONS)

        except Exception as e:
            logger.error(f"初始化权限文件失败: {e}")
            return 0

    def init_directory_structure(self):
        """初始化目录结构"""

        # 使用PathConfig进行统一路径管理
        PathConfig.ensure_directories()

        # 额外创建静态文件目录
        try:
            static_dir = Path("static")
            static_dir.mkdir(exist_ok=True)
            logger.info("✅ 目录结构初始化完成")
            self.initialized_components.append("目录结构")
            return 1
        except Exception as e:
            logger.error(f"创建静态目录失败: {e}")
            return 0

    def init_default_data_files(self):
        """初始化默认数据文件"""

        DATA_FILES = {
            str(PathConfig.TAIL_FILTER_SAMPLES_FILE): {
                "samples": [],
                "created_at": datetime.now().isoformat(),
                "total_count": 0
            },
            str(PathConfig.AD_KEYWORDS_FILE): {
                "keywords": [],
                "created_at": datetime.now().isoformat(),
                "total_count": 0
            },
            str(PathConfig.SEPARATOR_PATTERNS_FILE): {
                "patterns": [],
                "created_at": datetime.now().isoformat(),
                "total_count": 0
            }
        }

        created_count = 0
        for file_path, default_content in DATA_FILES.items():
            file_obj = Path(file_path)
            file_obj.parent.mkdir(parents=True, exist_ok=True)

            if not file_obj.exists():
                try:
                    with open(file_obj, 'w', encoding='utf-8') as f:
                        json.dump(default_content, f, ensure_ascii=False, indent=2)
                    created_count += 1
                    logger.debug(f"创建数据文件: {file_path}")
                except Exception as e:
                    logger.error(f"创建数据文件失败 {file_path}: {e}")

        if created_count > 0:
            logger.info(f"✅ 创建了 {created_count} 个数据文件")
            self.initialized_components.append(f"数据文件({created_count}个)")
        else:
            logger.info("ℹ️  数据文件已存在")

        return created_count

    async def initialize_storage_system(self):
        """初始化存储系统"""
        logger.info("🚀 正在初始化 Telegram 消息审核系统存储层...")

        # 1. 创建目录结构
        logger.info("📁 初始化目录结构...")
        self.init_directory_structure()

        # 2. 初始化JSON存储
        logger.info("📄 初始化JSON存储...")
        json_success = init_json_stores()
        if json_success:
            logger.info("✅ JSON存储初始化完成")
            self.initialized_components.append("JSON存储")
        else:
            logger.error("❌ JSON存储初始化失败")
            return False

        # 3. 初始化Redis存储
        logger.info("🔴 初始化Redis存储...")
        redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
        redis_success = redis_manager.is_healthy()
        if redis_success:
            logger.info("✅ Redis存储初始化完成")
            self.initialized_components.append("Redis存储")
        else:
            logger.error("❌ Redis存储初始化失败")
            return False

        # 4. 初始化默认数据文件
        logger.info("📊 初始化默认数据文件...")
        self.init_default_data_files()

        # 5. 初始化权限数据
        logger.info("🔐 初始化权限数据...")
        self.init_default_permissions()

        # 6. 初始化默认配置
        logger.info("⚙️  初始化默认配置...")
        try:
            config_count = await self.init_default_configs()
            logger.info("✅ 默认配置初始化完成")
        except Exception as e:
            logger.error(f"❌ 默认配置初始化失败: {e}")
            return False

        logger.info("\n🎉 存储系统初始化完成！")
        logger.info(f"📋 已初始化组件: {', '.join(self.initialized_components)}")
        logger.info("\n📋 下一步操作：")
        logger.info("1. 运行 python3 tools/init/init_system.py --create-admin 创建超级管理员")
        logger.info("2. 启动系统: ./dev.sh 或 ./start.sh")
        logger.info(f"3. 访问 {url_config.get_auth_url()} 完成Telegram认证")
        logger.info(f"4. 访问 {url_config.get_config_url()} 配置频道")
        logger.info(f"5. 访问 {url_config.base_url} 开始使用系统")

        return True

    async def check_storage_status(self):
        """检查存储系统状态"""
        logger.info("🔍 检查存储系统状态...")

        # 检查Redis连接
        try:
            redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
            if redis_manager.is_healthy():
                logger.info("✅ Redis连接正常")

                total_messages = len(redis_manager.get_all_messages(limit=1000))
                pending_messages = len(redis_manager.get_messages_by_status('pending', 100))

                logger.info(f"📊 Redis消息统计: 总计 {total_messages} 条，待审核 {pending_messages} 条")
            else:
                logger.error("❌ Redis连接失败")
        except Exception as e:
            logger.error(f"❌ Redis检查失败: {e}")

        # 检查JSON配置
        try:
            if init_json_stores():
                logger.info("✅ JSON存储正常")

                config_count = await config_manager.get_all_configs()
                logger.info(f"📋 配置项数量: {len(config_count)}")
            else:
                logger.error("❌ JSON存储失败")
        except Exception as e:
            logger.error(f"❌ JSON配置检查失败: {e}")

        # 检查数据文件
        data_files = [
            str(PathConfig.TAIL_FILTER_SAMPLES_FILE),
            str(PathConfig.AD_KEYWORDS_FILE),
            str(PathConfig.SEPARATOR_PATTERNS_FILE),
            str(PathConfig.PERMISSIONS_CONFIG_FILE)
        ]

        existing_files = 0
        for file_path in data_files:
            if Path(file_path).exists():
                existing_files += 1

        logger.info(f"📄 数据文件: {existing_files}/{len(data_files)} 个存在")

        logger.info("✅ 存储系统状态检查完成")

    async def load_permissions(self):
        """加载权限定义"""
        permissions_file = PathConfig.PERMISSIONS_CONFIG_FILE
        if not permissions_file.exists():
            logger.warning("❌ 权限文件不存在，请先运行 --init 初始化系统")
            return []

        try:
            with open(permissions_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('permissions', [])
        except Exception as e:
            logger.error(f"❌ 读取权限文件失败: {e}")
            return []

    async def create_super_admin(self):
        """创建超级管理员账号"""
        print("🔐 创建超级管理员账号")
        print("-" * 40)

        # 初始化JSON存储
        if not init_json_stores():
            print("❌ JSON存储初始化失败")
            return False

        user_store = get_json_user_store()

        # 检查是否已存在超级管理员
        all_users = user_store.get_all_users()
        existing_super = None
        for user in all_users:
            if user.get('is_super_admin'):
                existing_super = user
                break

        if existing_super:
            print("⚠️  系统已存在超级管理员账号！")
            print(f"   现有超级管理员: {existing_super.get('username')}")
            try:
                confirm = input("是否要创建新的超级管理员？(yes/no): ").lower()
            except EOFError:
                confirm = 'no'
                print("非交互环境，取消创建")

            if confirm != 'yes':
                print("已取消创建")
                return False

        # 获取用户输入
        username = None
        while True:
            try:
                username = input("请输入用户名: ").strip()
            except EOFError:
                # 非交互环境，使用默认用户名
                username = "admin"
                print(f"非交互环境，使用默认用户名: {username}")

            if not username:
                print("❌ 用户名不能为空")
                continue

            # 检查用户名是否已存在
            if user_store.get_user_by_username(username):
                print(f"❌ 用户名 '{username}' 已存在")
                # 在非交互环境中，添加随机后缀
                try:
                    input("test")  # 测试是否交互环境
                except EOFError:
                    import random
                    username = f"{username}_{random.randint(1000, 9999)}"
                    print(f"自动调整用户名为: {username}")
                    break
                continue
            break

        # 获取密码
        password = None
        while True:
            try:
                password = getpass.getpass("请输入密码 (至少6位): ")
            except EOFError:
                # 非交互环境，使用默认密码
                password = "admin123"
                print("非交互环境，使用默认密码: admin123")

            if len(password) < 6:
                print("❌ 密码长度至少6位")
                try:
                    getpass.getpass("test")  # 测试是否交互环境
                except EOFError:
                    password = "admin123"  # 使用更长的默认密码
                    break
                continue

            # 确认密码
            try:
                password_confirm = getpass.getpass("请再次输入密码: ")
                if password != password_confirm:
                    print("❌ 两次输入的密码不一致")
                    continue
            except EOFError:
                # 非交互环境，跳过确认
                pass
            break

        # 加载权限信息
        permissions = await self.load_permissions()
        if not permissions:
            print("⚠️  未找到权限定义，管理员将不具备任何权限")

        # 创建管理员用户
        try:
            password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

            admin_data = {
                "username": username,
                "password_hash": password_hash,
                "is_super_admin": True,
                "is_active": True,
                "permissions": [perm['name'] for perm in permissions],  # 分配所有权限
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "last_login": None,
                "login_count": 0
            }

            user_id = user_store.create_user(admin_data)

            if user_id:
                print("\n✅ 超级管理员创建成功！")
                print(f"👤 用户名: {username}")
                print(f"🆔 用户ID: {user_id}")
                print(f"🔑 权限: 所有权限 ({len(permissions)} 项)")
                print(f"📅 创建时间: {admin_data['created_at']}")
                print("\n现在可以使用此账号登录系统了")
                print("\n登录地址:")
                print(f"  {url_config.get_login_url()}")

                return True
            else:
                print("❌ 创建管理员账号失败")
                return False

        except Exception as e:
            print(f"❌ 创建管理员时出错: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def list_admins(self):
        """列出所有管理员账号"""
        print("👥 系统管理员列表")
        print("-" * 50)

        if not init_json_stores():
            print("❌ JSON存储初始化失败")
            return

        user_store = get_json_user_store()
        all_users = user_store.get_all_users()

        if not all_users:
            print("⚠️  系统中没有管理员账号")
            return

        admin_count = 0
        for user in all_users:
            if user.get('is_super_admin') or user.get('permissions'):
                admin_count += 1
                status = "🟢 活跃" if user.get('is_active', True) else "🔴 禁用"
                admin_type = "🔑 超级管理员" if user.get('is_super_admin') else "👤 普通管理员"

                print(f"{admin_count}. {user.get('username')} - {admin_type} - {status}")
                print(f"   ID: {user.get('id')}")
                print(f"   权限数: {len(user.get('permissions', []))}")
                print(f"   创建时间: {user.get('created_at', '未知')}")
                print(f"   最后登录: {user.get('last_login', '未登录')}")
                print()

        if admin_count == 0:
            print("⚠️  系统中没有管理员账号")
        else:
            print(f"📊 总计: {admin_count} 个管理员账号")

    async def reset_admin_password(self):
        """重置管理员密码"""
        print("🔄 重置管理员密码")
        print("-" * 40)

        if not init_json_stores():
            print("❌ JSON存储初始化失败")
            return

        user_store = get_json_user_store()
        all_users = user_store.get_all_users()

        if not all_users:
            print("⚠️  系统中没有用户")
            return

        # 显示用户列表
        admin_users = [user for user in all_users if user.get('is_super_admin') or user.get('permissions')]

        if not admin_users:
            print("⚠️  系统中没有管理员账号")
            return

        print("请选择要重置密码的管理员:")
        for i, user in enumerate(admin_users, 1):
            admin_type = "🔑 超级管理员" if user.get('is_super_admin') else "👤 普通管理员"
            print(f"{i}. {user.get('username')} - {admin_type}")

        try:
            choice = input("请输入序号: ").strip()
            choice_idx = int(choice) - 1

            if choice_idx < 0 or choice_idx >= len(admin_users):
                print("❌ 无效的选择")
                return

            selected_user = admin_users[choice_idx]

            # 获取新密码
            new_password = getpass.getpass("请输入新密码 (至少6位): ")
            if len(new_password) < 6:
                print("❌ 密码长度至少6位")
                return

            # 更新密码
            password_hash = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

            user_data = selected_user.copy()
            user_data['password_hash'] = password_hash
            user_data['updated_at'] = datetime.now().isoformat()

            success = user_store.update_user(selected_user['id'], user_data)

            if success:
                print(f"\n✅ 用户 '{selected_user['username']}' 的密码已重置")
            else:
                print("❌ 密码重置失败")

        except (ValueError, EOFError):
            print("❌ 操作已取消")
        except Exception as e:
            print(f"❌ 重置密码时出错: {e}")


async def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description='系统初始化工具 - 统一的存储和管理员管理')
    parser.add_argument('--init', action='store_true', help='初始化存储系统')
    parser.add_argument('--check', action='store_true', help='检查存储状态')
    parser.add_argument('--create-admin', action='store_true', help='创建超级管理员')
    parser.add_argument('--list-admins', action='store_true', help='列出所有管理员')
    parser.add_argument('--reset-password', action='store_true', help='重置管理员密码')

    args = parser.parse_args()

    initializer = SystemInitializer()

    if args.check:
        await initializer.check_storage_status()
    elif args.create_admin:
        success = await initializer.create_super_admin()
        if not success:
            sys.exit(1)
    elif args.list_admins:
        await initializer.list_admins()
    elif args.reset_password:
        await initializer.reset_admin_password()
    elif args.init or len(sys.argv) == 1:  # 默认行为
        success = await initializer.initialize_storage_system()
        if not success:
            sys.exit(1)
    else:
        parser.print_help()


if __name__ == "__main__":
    asyncio.run(main())