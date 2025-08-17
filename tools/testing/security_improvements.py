#!/usr/bin/env python3
"""
安全改进建议实施脚本
基于安全评估报告的具体改进措施
"""

import json
import logging
from datetime import datetime
from typing import Dict, List

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SecurityImprovements:
    """安全改进建议类"""
    
    def __init__(self):
        self.improvements = {
            "high_priority": [
                {
                    "id": "SEC-001", 
                    "title": "实施API速率限制",
                    "description": "防范暴力破解攻击",
                    "implementation": self.implement_rate_limiting,
                    "estimated_effort": "2小时"
                },
                {
                    "id": "SEC-002",
                    "title": "缩短令牌有效期", 
                    "description": "从24小时缩短到4小时",
                    "implementation": self.optimize_token_lifetime,
                    "estimated_effort": "30分钟"
                }
            ],
            "medium_priority": [
                {
                    "id": "SEC-003",
                    "title": "增强密码策略",
                    "description": "添加密码复杂度要求",
                    "implementation": self.enhance_password_policy,
                    "estimated_effort": "1小时"
                },
                {
                    "id": "SEC-004", 
                    "title": "会话并发控制",
                    "description": "限制同时在线会话数",
                    "implementation": self.implement_session_control,
                    "estimated_effort": "2小时"
                }
            ],
            "low_priority": [
                {
                    "id": "SEC-005",
                    "title": "升级密码哈希算法",
                    "description": "从SHA-256升级到bcrypt",
                    "implementation": self.upgrade_password_hashing,
                    "estimated_effort": "4小时"
                },
                {
                    "id": "SEC-006",
                    "title": "添加安全头信息", 
                    "description": "实施HSTS、CSP等安全头",
                    "implementation": self.add_security_headers,
                    "estimated_effort": "1小时"
                }
            ]
        }
    
    def implement_rate_limiting(self):
        """实施API速率限制"""
        logger.info("🚦 实施API速率限制...")
        
        # 生成速率限制代码示例
        rate_limit_code = '''
# 1. 安装依赖
# pip install slowapi

# 2. 在web_server.py中添加
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# 3. 初始化限制器
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# 4. 在登录路由中应用限制
@limiter.limit("5/minute")  # 每分钟最多5次尝试
@router.post("/login")
async def login(request: Request, login_req: LoginRequest):
    # 现有登录代码
    pass

# 5. 高级配置
@limiter.limit("10/minute", key_func=lambda request: request.client.host)
@limiter.limit("100/hour", key_func=lambda request: request.client.host)
'''
        
        print("📋 API速率限制实施代码:")
        print(rate_limit_code)
        
        return {
            "status": "ready_to_implement",
            "code_sample": rate_limit_code,
            "next_steps": [
                "安装slowapi依赖",
                "修改web_server.py",
                "在admin_auth.py中添加限制装饰器",
                "测试限制功能",
                "配置Redis存储(可选)"
            ]
        }
    
    def optimize_token_lifetime(self):
        """优化令牌生命周期"""
        logger.info("⏰ 优化令牌生命周期...")
        
        config_update = '''
# 在app/services/auth_service.py中修改
class AuthService:
    def __init__(self):
        # 从24小时缩短到4小时
        self.default_session_expire = 4 * 3600  # 4小时
        # 或者更激进的2小时
        # self.default_session_expire = 2 * 3600  # 2小时

# 可选：实施令牌刷新机制
@router.post("/refresh-token")
async def refresh_token(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """刷新令牌"""
    if not credentials:
        raise HTTPException(status_code=401, detail="未登录")
    
    auth = get_auth()
    new_token = await auth.refresh_token(credentials.credentials)
    
    if new_token:
        return {"success": True, "token": new_token}
    else:
        raise HTTPException(status_code=401, detail="令牌刷新失败")
'''
        
        print("📋 令牌生命周期优化代码:")
        print(config_update)
        
        return {
            "status": "ready_to_implement", 
            "configuration": {
                "current_lifetime": "24小时",
                "recommended_lifetime": "4小时",
                "with_refresh": "2小时 + 刷新机制"
            },
            "code_sample": config_update
        }
    
    def enhance_password_policy(self):
        """增强密码策略"""
        logger.info("🔐 增强密码策略...")
        
        password_policy_code = '''
# 在app/services/auth_service.py中添加
import re

class PasswordPolicy:
    """密码策略验证"""
    
    @staticmethod
    def validate_password(password: str) -> Dict[str, Any]:
        """验证密码强度"""
        errors = []
        
        # 长度检查
        if len(password) < 8:
            errors.append("密码长度至少8位")
        
        # 复杂度检查
        if not re.search(r'[A-Z]', password):
            errors.append("密码必须包含大写字母")
        
        if not re.search(r'[a-z]', password):
            errors.append("密码必须包含小写字母")
        
        if not re.search(r'\\d', password):
            errors.append("密码必须包含数字")
        
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            errors.append("密码必须包含特殊字符")
        
        # 常见密码检查
        common_passwords = ['password', '123456', 'admin123', 'qwerty']
        if password.lower() in common_passwords:
            errors.append("不能使用常见密码")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "strength": "强" if len(errors) == 0 else "弱"
        }

# 在创建用户和修改密码时使用
async def create_user(self, username: str, password: str, is_super_admin: bool = False):
    # 密码策略验证
    policy_result = PasswordPolicy.validate_password(password)
    if not policy_result["valid"]:
        raise ValueError(f"密码不符合安全策略: {', '.join(policy_result['errors'])}")
    
    # 现有创建用户代码
    pass
'''
        
        print("📋 密码策略增强代码:")
        print(password_policy_code)
        
        return {
            "status": "ready_to_implement",
            "policy_requirements": {
                "minimum_length": 8,
                "required_characters": ["大写字母", "小写字母", "数字", "特殊字符"],
                "forbidden": ["常见密码", "用户名相同"]
            },
            "code_sample": password_policy_code
        }
    
    def implement_session_control(self):
        """实施会话并发控制"""
        logger.info("👥 实施会话并发控制...")
        
        session_control_code = '''
# 在app/services/auth_service.py中修改
class AuthService:
    def __init__(self):
        self.max_concurrent_sessions = 3  # 最大并发会话数
    
    async def login(self, username: str, password: str, **kwargs):
        # 现有登录验证代码...
        
        # 检查并发会话数
        active_sessions = await self.get_user_active_sessions(admin_id)
        if len(active_sessions) >= self.max_concurrent_sessions:
            # 删除最老的会话
            oldest_session = min(active_sessions, key=lambda s: s['login_time'])
            await self.logout(oldest_session['token'])
            logger.info(f"因达到最大并发数，清理用户 {username} 的最老会话")
        
        # 继续现有登录流程
        pass
    
    async def get_user_active_sessions(self, admin_id: int) -> List[Dict]:
        """获取用户的活跃会话"""
        active_tokens = self.session_store.get_active_sessions()
        user_sessions = []
        
        for token in active_tokens:
            session_data = self.session_store.get_session(token)
            if session_data and session_data.get('admin_id') == admin_id:
                user_sessions.append({
                    'token': token,
                    'login_time': session_data.get('login_time'),
                    'ip_address': session_data.get('ip_address')
                })
        
        return user_sessions
'''
        
        print("📋 会话并发控制代码:")
        print(session_control_code)
        
        return {
            "status": "ready_to_implement",
            "configuration": {
                "max_sessions_per_user": 3,
                "cleanup_strategy": "删除最老会话",
                "notification": "可选择通知用户"
            },
            "code_sample": session_control_code
        }
    
    def upgrade_password_hashing(self):
        """升级密码哈希算法"""
        logger.info("🔒 升级密码哈希算法...")
        
        bcrypt_upgrade_code = '''
# 1. 安装依赖
# pip install bcrypt

# 2. 在app/services/auth_service.py中修改
import bcrypt

class AuthService:
    def hash_password(self, password: str) -> str:
        """使用bcrypt哈希密码"""
        salt = bcrypt.gensalt(rounds=12)  # 12轮加盐
        return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
    
    def verify_password(self, password: str, hashed_password: str) -> bool:
        """验证密码"""
        # 兼容旧的SHA-256哈希
        if len(hashed_password) == 64:  # SHA-256长度
            import hashlib
            return hashlib.sha256(password.encode()).hexdigest() == hashed_password
        
        # 新的bcrypt验证
        return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))

# 3. 数据迁移脚本
async def migrate_password_hashes():
    """迁移现有密码哈希"""
    admin_store = get_json_admin_store()
    admins_data = admin_store._load_json(admin_store.ADMIN_FILE)
    
    for admin_id, admin_data in admins_data.items():
        old_hash = admin_data.get('password_hash', '')
        if len(old_hash) == 64:  # 识别SHA-256哈希
            print(f"管理员 {admin_data['username']} 需要在下次登录时重新设置密码")
            # 标记需要密码重置
            admin_data['requires_password_reset'] = True
    
    admin_store._save_json(admin_store.ADMIN_FILE, admins_data)
'''
        
        print("📋 密码哈希算法升级代码:")
        print(bcrypt_upgrade_code)
        
        return {
            "status": "requires_planning",
            "migration_strategy": "渐进式迁移",
            "steps": [
                "安装bcrypt依赖",
                "修改哈希和验证函数",
                "实施向后兼容",
                "强制用户在下次登录时重置密码",
                "逐步淘汰SHA-256哈希"
            ],
            "code_sample": bcrypt_upgrade_code
        }
    
    def add_security_headers(self):
        """添加安全头信息"""
        logger.info("🛡️ 添加安全头信息...")
        
        security_headers_code = '''
# 在web_server.py中添加安全头中间件
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware

# 添加安全头中间件
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    
    # HSTS (HTTP Strict Transport Security)
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    
    # Content Security Policy
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "connect-src 'self' ws: wss:;"
    )
    
    # X-Frame-Options (防止点击劫持)
    response.headers["X-Frame-Options"] = "DENY"
    
    # X-Content-Type-Options
    response.headers["X-Content-Type-Options"] = "nosniff"
    
    # X-XSS-Protection
    response.headers["X-XSS-Protection"] = "1; mode=block"
    
    # Referrer Policy
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    
    # Permissions Policy
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    
    return response

# 生产环境添加HTTPS重定向
if settings.environment == "production":
    app.add_middleware(HTTPSRedirectMiddleware)

# 信任主机中间件
app.add_middleware(
    TrustedHostMiddleware, 
    allowed_hosts=["localhost", "127.0.0.1", "yourdomain.com"]
)
'''
        
        print("📋 安全头信息代码:")
        print(security_headers_code)
        
        return {
            "status": "ready_to_implement",
            "headers": {
                "HSTS": "强制HTTPS",
                "CSP": "内容安全策略", 
                "X-Frame-Options": "防点击劫持",
                "X-Content-Type-Options": "防MIME嗅探",
                "Referrer-Policy": "引用策略"
            },
            "code_sample": security_headers_code
        }
    
    def generate_implementation_plan(self):
        """生成实施计划"""
        print("\n" + "="*80)
        print("🔒 安全改进实施计划")
        print("="*80)
        
        total_effort = 0
        
        for priority, items in self.improvements.items():
            print(f"\n📌 {priority.upper().replace('_', ' ')} 优先级改进:")
            print("-" * 50)
            
            for item in items:
                effort_hours = float(item["estimated_effort"].split("小时")[0]) if "小时" in item["estimated_effort"] else 0.5
                total_effort += effort_hours
                
                print(f"🎯 {item['id']}: {item['title']}")
                print(f"   描述: {item['description']}")
                print(f"   预估工作量: {item['estimated_effort']}")
                print(f"   实施建议: 调用 {item['implementation'].__name__}()")
                print()
        
        print(f"📊 总预估工作量: {total_effort} 小时")
        print(f"🗓️ 建议完成时间: {int(total_effort / 8) + 1} 个工作日")
        
        return {
            "total_effort_hours": total_effort,
            "estimated_days": int(total_effort / 8) + 1,
            "priority_order": ["high_priority", "medium_priority", "low_priority"]
        }
    
    def run_implementation_wizard(self):
        """运行实施向导"""
        print("🧙‍♂️ 安全改进实施向导")
        print("="*50)
        
        print("\n选择要实施的改进项目:")
        print("1. API速率限制 (高优先级)")
        print("2. 令牌生命周期优化 (高优先级)")
        print("3. 密码策略增强 (中优先级)")
        print("4. 会话并发控制 (中优先级)")
        print("5. 密码哈希升级 (低优先级)")
        print("6. 安全头信息 (低优先级)")
        print("7. 生成完整实施计划")
        print("0. 退出")
        
        try:
            choice = input("\n请输入选项 (0-7): ").strip()
            
            if choice == "1":
                return self.implement_rate_limiting()
            elif choice == "2":
                return self.optimize_token_lifetime()
            elif choice == "3":
                return self.enhance_password_policy()
            elif choice == "4":
                return self.implement_session_control()
            elif choice == "5":
                return self.upgrade_password_hashing()
            elif choice == "6":
                return self.add_security_headers()
            elif choice == "7":
                return self.generate_implementation_plan()
            elif choice == "0":
                print("👋 退出向导")
                return None
            else:
                print("❌ 无效选项")
                return None
                
        except KeyboardInterrupt:
            print("\n👋 用户取消操作")
            return None


def main():
    """主函数"""
    print("🛡️ Telegram消息处理系统 - 安全改进建议")
    print("基于安全评估报告的具体实施指导")
    print("="*60)
    
    security_improver = SecurityImprovements()
    
    # 显示改进计划
    security_improver.generate_implementation_plan()
    
    # 运行交互式向导
    print("\n" + "="*60)
    while True:
        result = security_improver.run_implementation_wizard()
        if result is None:
            break
        
        input("\n按Enter键继续...")
    
    print("\n✅ 安全改进建议生成完成！")
    print("📄 详细安全评估报告: tools/testing/security_assessment_report.md")


if __name__ == "__main__":
    main()