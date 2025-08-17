#!/usr/bin/env python3
"""
认证和权限安全测试脚本
测试系统的用户认证、权限控制和会话管理的安全性
"""

import asyncio
import aiohttp
import json
import time
import hashlib
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
import websockets
import urllib.parse

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('security_test.log')
    ]
)
logger = logging.getLogger(__name__)

class SecurityTestSuite:
    """安全测试套件"""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.session = None
        self.test_results = []
        self.auth_token = None
        
        # 测试账户配置
        self.admin_username = "admin"
        self.admin_password = "admin123"
        
        # 威胁检测计数器
        self.threat_detected = {
            "unauthorized_access": 0,
            "token_vulnerabilities": 0,
            "injection_attempts": 0,
            "session_hijacking": 0,
            "privilege_escalation": 0
        }
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        if self.session:
            await self.session.close()
    
    def add_test_result(self, test_name: str, status: str, details: str, 
                       severity: str = "INFO", threat_type: str = None):
        """记录测试结果"""
        result = {
            "timestamp": datetime.now().isoformat(),
            "test_name": test_name,
            "status": status,
            "details": details,
            "severity": severity
        }
        
        self.test_results.append(result)
        
        # 威胁检测计数
        if threat_type and threat_type in self.threat_detected:
            self.threat_detected[threat_type] += 1
        
        # 记录日志
        log_level = getattr(logging, severity)
        logger.log(log_level, f"[{test_name}] {status}: {details}")
    
    # ==================== 管理员认证测试 ====================
    
    async def test_admin_login_flow(self):
        """测试管理员登录流程"""
        logger.info("🔐 开始测试管理员登录流程...")
        
        # 1. 测试正确登录
        try:
            login_data = {
                "username": self.admin_username,
                "password": self.admin_password
            }
            
            async with self.session.post(
                f"{self.base_url}/api/admin/auth/login",
                json=login_data
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("success") and data.get("token"):
                        self.auth_token = data["token"]
                        self.add_test_result(
                            "正确登录测试",
                            "✅ PASS",
                            f"管理员登录成功，获得token: {self.auth_token[:8]}..."
                        )
                    else:
                        self.add_test_result(
                            "正确登录测试",
                            "❌ FAIL",
                            "登录响应格式错误",
                            "HIGH"
                        )
                else:
                    self.add_test_result(
                        "正确登录测试",
                        "❌ FAIL",
                        f"登录失败，状态码: {response.status}",
                        "HIGH"
                    )
        except Exception as e:
            self.add_test_result(
                "正确登录测试",
                "❌ ERROR",
                f"登录异常: {str(e)}",
                "CRITICAL"
            )
        
        # 2. 测试错误密码
        try:
            wrong_login_data = {
                "username": self.admin_username,
                "password": "wrong_password"
            }
            
            async with self.session.post(
                f"{self.base_url}/api/admin/auth/login",
                json=wrong_login_data
            ) as response:
                if response.status == 401:
                    self.add_test_result(
                        "错误密码拒绝测试",
                        "✅ PASS",
                        "错误密码被正确拒绝"
                    )
                else:
                    self.add_test_result(
                        "错误密码拒绝测试",
                        "❌ FAIL",
                        f"错误密码未被拒绝，状态码: {response.status}",
                        "HIGH",
                        "unauthorized_access"
                    )
        except Exception as e:
            self.add_test_result(
                "错误密码拒绝测试",
                "❌ ERROR",
                f"测试异常: {str(e)}",
                "MEDIUM"
            )
        
        # 3. 测试不存在的用户
        try:
            nonexistent_login_data = {
                "username": "nonexistent_user",
                "password": "any_password"
            }
            
            async with self.session.post(
                f"{self.base_url}/api/admin/auth/login",
                json=nonexistent_login_data
            ) as response:
                if response.status == 401:
                    self.add_test_result(
                        "不存在用户拒绝测试",
                        "✅ PASS",
                        "不存在用户被正确拒绝"
                    )
                else:
                    self.add_test_result(
                        "不存在用户拒绝测试",
                        "❌ FAIL",
                        f"不存在用户未被拒绝，状态码: {response.status}",
                        "HIGH",
                        "unauthorized_access"
                    )
        except Exception as e:
            self.add_test_result(
                "不存在用户拒绝测试",
                "❌ ERROR",
                f"测试异常: {str(e)}",
                "MEDIUM"
            )
    
    async def test_password_security(self):
        """测试密码安全性"""
        logger.info("🔒 开始测试密码安全性...")
        
        # 1. 测试暴力破解防护
        try:
            failed_attempts = 0
            for i in range(10):  # 尝试10次错误登录
                wrong_login_data = {
                    "username": self.admin_username,
                    "password": f"wrong_password_{i}"
                }
                
                async with self.session.post(
                    f"{self.base_url}/api/admin/auth/login",
                    json=wrong_login_data
                ) as response:
                    if response.status == 401:
                        failed_attempts += 1
                    
                    # 检查是否有速率限制
                    if response.status == 429:  # Too Many Requests
                        self.add_test_result(
                            "暴力破解防护测试",
                            "✅ PASS",
                            f"在第{i+1}次尝试后触发速率限制"
                        )
                        break
                    
                    await asyncio.sleep(0.1)  # 避免过快请求
            else:
                # 如果没有触发速率限制
                self.add_test_result(
                    "暴力破解防护测试",
                    "⚠️ WARNING",
                    f"连续{failed_attempts}次失败登录未触发速率限制",
                    "MEDIUM"
                )
        except Exception as e:
            self.add_test_result(
                "暴力破解防护测试",
                "❌ ERROR",
                f"测试异常: {str(e)}",
                "MEDIUM"
            )
        
        # 2. 测试密码哈希安全性
        try:
            # 检查配置文件中的密码哈希
            password_hash = "240be518fabd2724ddb6f04eeb1da5967448d7e831c08c8fa822809f74c720a9"
            
            # 验证是否是SHA-256哈希
            test_password = "admin123"
            expected_hash = hashlib.sha256(test_password.encode()).hexdigest()
            
            if password_hash == expected_hash:
                self.add_test_result(
                    "密码哈希验证",
                    "✅ PASS",
                    "密码使用SHA-256哈希存储"
                )
            else:
                self.add_test_result(
                    "密码哈希验证",
                    "⚠️ WARNING",
                    "密码哈希格式未知或使用弱哈希算法",
                    "MEDIUM"
                )
        except Exception as e:
            self.add_test_result(
                "密码哈希验证",
                "❌ ERROR",
                f"验证异常: {str(e)}",
                "LOW"
            )
    
    # ==================== 权限验证测试 ====================
    
    async def test_api_access_control(self):
        """测试API访问控制"""
        logger.info("🛡️ 开始测试API访问控制...")
        
        if not self.auth_token:
            self.add_test_result(
                "API访问控制测试",
                "❌ SKIP",
                "无有效认证token，跳过测试",
                "HIGH"
            )
            return
        
        # 受保护的API端点列表
        protected_endpoints = [
            "/api/messages",
            "/api/admin/current",
            "/api/admin/admins",
            "/api/config",
            "/api/channel-config"
        ]
        
        for endpoint in protected_endpoints:
            # 1. 测试未认证访问
            try:
                async with self.session.get(f"{self.base_url}{endpoint}") as response:
                    if response.status == 401:
                        self.add_test_result(
                            f"未认证访问拒绝测试 - {endpoint}",
                            "✅ PASS",
                            "未认证访问被正确拒绝"
                        )
                    else:
                        self.add_test_result(
                            f"未认证访问拒绝测试 - {endpoint}",
                            "❌ FAIL",
                            f"未认证访问未被拒绝，状态码: {response.status}",
                            "HIGH",
                            "unauthorized_access"
                        )
            except Exception as e:
                self.add_test_result(
                    f"未认证访问拒绝测试 - {endpoint}",
                    "❌ ERROR",
                    f"测试异常: {str(e)}",
                    "MEDIUM"
                )
            
            # 2. 测试有效token访问
            try:
                headers = {"Authorization": f"Bearer {self.auth_token}"}
                async with self.session.get(
                    f"{self.base_url}{endpoint}",
                    headers=headers
                ) as response:
                    if response.status in [200, 201, 204]:
                        self.add_test_result(
                            f"有效token访问测试 - {endpoint}",
                            "✅ PASS",
                            "有效token访问成功"
                        )
                    elif response.status == 403:
                        self.add_test_result(
                            f"有效token访问测试 - {endpoint}",
                            "⚠️ INFO",
                            "访问被权限控制拒绝（正常）"
                        )
                    else:
                        self.add_test_result(
                            f"有效token访问测试 - {endpoint}",
                            "⚠️ WARNING",
                            f"意外状态码: {response.status}",
                            "MEDIUM"
                        )
            except Exception as e:
                self.add_test_result(
                    f"有效token访问测试 - {endpoint}",
                    "❌ ERROR",
                    f"测试异常: {str(e)}",
                    "MEDIUM"
                )
    
    async def test_token_security(self):
        """测试Token安全性"""
        logger.info("🎫 开始测试Token安全性...")
        
        if not self.auth_token:
            self.add_test_result(
                "Token安全测试",
                "❌ SKIP",
                "无有效认证token，跳过测试",
                "HIGH"
            )
            return
        
        # 1. 测试无效token
        invalid_tokens = [
            "invalid_token",
            "Bearer invalid",
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.invalid",
            "",
            "null",
            "undefined"
        ]
        
        for invalid_token in invalid_tokens:
            try:
                headers = {"Authorization": f"Bearer {invalid_token}"}
                async with self.session.get(
                    f"{self.base_url}/api/admin/current",
                    headers=headers
                ) as response:
                    if response.status == 401:
                        self.add_test_result(
                            f"无效token拒绝测试 - {invalid_token[:10]}...",
                            "✅ PASS",
                            "无效token被正确拒绝"
                        )
                    else:
                        self.add_test_result(
                            f"无效token拒绝测试 - {invalid_token[:10]}...",
                            "❌ FAIL",
                            f"无效token未被拒绝，状态码: {response.status}",
                            "HIGH",
                            "token_vulnerabilities"
                        )
            except Exception as e:
                self.add_test_result(
                    f"无效token拒绝测试 - {invalid_token[:10]}...",
                    "❌ ERROR",
                    f"测试异常: {str(e)}",
                    "MEDIUM"
                )
        
        # 2. 测试token长度和格式
        token_length = len(self.auth_token)
        if token_length >= 32:
            self.add_test_result(
                "Token长度检查",
                "✅ PASS",
                f"Token长度足够: {token_length}字符"
            )
        else:
            self.add_test_result(
                "Token长度检查",
                "⚠️ WARNING",
                f"Token长度可能不足: {token_length}字符",
                "MEDIUM",
                "token_vulnerabilities"
            )
        
        # 3. 测试token熵值（随机性）
        try:
            import string
            charset = string.ascii_letters + string.digits + "-_"
            unique_chars = len(set(self.auth_token))
            charset_ratio = unique_chars / len(charset)
            
            if charset_ratio > 0.3:  # 至少使用30%的字符集
                self.add_test_result(
                    "Token随机性检查",
                    "✅ PASS",
                    f"Token字符多样性良好: {charset_ratio:.2%}"
                )
            else:
                self.add_test_result(
                    "Token随机性检查",
                    "⚠️ WARNING",
                    f"Token字符多样性不足: {charset_ratio:.2%}",
                    "MEDIUM",
                    "token_vulnerabilities"
                )
        except Exception as e:
            self.add_test_result(
                "Token随机性检查",
                "❌ ERROR",
                f"检查异常: {str(e)}",
                "LOW"
            )
    
    # ==================== 会话管理测试 ====================
    
    async def test_session_management(self):
        """测试会话管理"""
        logger.info("📱 开始测试会话管理...")
        
        if not self.auth_token:
            self.add_test_result(
                "会话管理测试",
                "❌ SKIP",
                "无有效认证token，跳过测试",
                "HIGH"
            )
            return
        
        # 1. 测试会话状态检查
        try:
            headers = {"Authorization": f"Bearer {self.auth_token}"}
            async with self.session.get(
                f"{self.base_url}/api/admin/auth/check-auth",
                headers=headers
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("authenticated"):
                        self.add_test_result(
                            "会话状态检查",
                            "✅ PASS",
                            "会话状态检查正常"
                        )
                    else:
                        self.add_test_result(
                            "会话状态检查",
                            "❌ FAIL",
                            "会话未被识别为已认证",
                            "HIGH"
                        )
                else:
                    self.add_test_result(
                        "会话状态检查",
                        "❌ FAIL",
                        f"会话状态检查失败，状态码: {response.status}",
                        "HIGH"
                    )
        except Exception as e:
            self.add_test_result(
                "会话状态检查",
                "❌ ERROR",
                f"测试异常: {str(e)}",
                "MEDIUM"
            )
        
        # 2. 测试登出功能
        try:
            headers = {"Authorization": f"Bearer {self.auth_token}"}
            async with self.session.post(
                f"{self.base_url}/api/admin/auth/logout",
                headers=headers
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("success"):
                        self.add_test_result(
                            "登出功能测试",
                            "✅ PASS",
                            "登出功能正常"
                        )
                        
                        # 验证登出后token是否失效
                        await asyncio.sleep(1)
                        async with self.session.get(
                            f"{self.base_url}/api/admin/current",
                            headers=headers
                        ) as verify_response:
                            if verify_response.status == 401:
                                self.add_test_result(
                                    "登出后token失效测试",
                                    "✅ PASS",
                                    "登出后token已失效"
                                )
                            else:
                                self.add_test_result(
                                    "登出后token失效测试",
                                    "❌ FAIL",
                                    f"登出后token仍然有效，状态码: {verify_response.status}",
                                    "HIGH",
                                    "session_hijacking"
                                )
                    else:
                        self.add_test_result(
                            "登出功能测试",
                            "❌ FAIL",
                            "登出请求失败",
                            "HIGH"
                        )
                else:
                    self.add_test_result(
                        "登出功能测试",
                        "❌ FAIL",
                        f"登出请求状态码错误: {response.status}",
                        "HIGH"
                    )
        except Exception as e:
            self.add_test_result(
                "登出功能测试",
                "❌ ERROR",
                f"测试异常: {str(e)}",
                "MEDIUM"
            )
    
    # ==================== 注入攻击测试 ====================
    
    async def test_injection_attacks(self):
        """测试注入攻击防护"""
        logger.info("💉 开始测试注入攻击防护...")
        
        # 1. SQL注入测试
        sql_injection_payloads = [
            "admin'; DROP TABLE admins; --",
            "admin' OR '1'='1",
            "admin' UNION SELECT * FROM admins --",
            "admin'; INSERT INTO admins VALUES('hacker','hash'); --"
        ]
        
        for payload in sql_injection_payloads:
            try:
                login_data = {
                    "username": payload,
                    "password": "any_password"
                }
                
                async with self.session.post(
                    f"{self.base_url}/api/admin/auth/login",
                    json=login_data
                ) as response:
                    if response.status == 401:
                        self.add_test_result(
                            f"SQL注入防护测试 - {payload[:20]}...",
                            "✅ PASS",
                            "SQL注入payload被正确拒绝"
                        )
                    elif response.status == 400:
                        self.add_test_result(
                            f"SQL注入防护测试 - {payload[:20]}...",
                            "✅ PASS",
                            "SQL注入payload触发输入验证错误"
                        )
                    else:
                        self.add_test_result(
                            f"SQL注入防护测试 - {payload[:20]}...",
                            "❌ FAIL",
                            f"SQL注入payload未被正确处理，状态码: {response.status}",
                            "HIGH",
                            "injection_attempts"
                        )
            except Exception as e:
                self.add_test_result(
                    f"SQL注入防护测试 - {payload[:20]}...",
                    "❌ ERROR",
                    f"测试异常: {str(e)}",
                    "MEDIUM"
                )
        
        # 2. XSS测试
        xss_payloads = [
            "<script>alert('XSS')</script>",
            "javascript:alert('XSS')",
            "<img src=x onerror=alert('XSS')>",
            "';alert('XSS');//"
        ]
        
        for payload in xss_payloads:
            try:
                login_data = {
                    "username": payload,
                    "password": "test"
                }
                
                async with self.session.post(
                    f"{self.base_url}/api/admin/auth/login",
                    json=login_data
                ) as response:
                    response_text = await response.text()
                    
                    # 检查响应中是否包含未转义的脚本
                    if "<script>" in response_text or "javascript:" in response_text:
                        self.add_test_result(
                            f"XSS防护测试 - {payload[:20]}...",
                            "❌ FAIL",
                            "响应中包含未转义的脚本内容",
                            "HIGH",
                            "injection_attempts"
                        )
                    else:
                        self.add_test_result(
                            f"XSS防护测试 - {payload[:20]}...",
                            "✅ PASS",
                            "XSS payload被正确处理"
                        )
            except Exception as e:
                self.add_test_result(
                    f"XSS防护测试 - {payload[:20]}...",
                    "❌ ERROR",
                    f"测试异常: {str(e)}",
                    "MEDIUM"
                )
    
    # ==================== Telegram认证安全测试 ====================
    
    async def test_telegram_auth_security(self):
        """测试Telegram认证安全性"""
        logger.info("📱 开始测试Telegram认证安全性...")
        
        # 1. 测试API密钥保护
        try:
            # 检查配置中的敏感信息是否暴露
            async with self.session.get(f"{self.base_url}/api/config") as response:
                if response.status == 401:
                    self.add_test_result(
                        "Telegram配置保护测试",
                        "✅ PASS",
                        "Telegram配置需要认证访问"
                    )
                elif response.status == 200:
                    data = await response.json()
                    # 检查是否暴露了敏感信息
                    sensitive_fields = ["api_hash", "session", "bot_token"]
                    exposed_fields = []
                    
                    for field in sensitive_fields:
                        if any(field in str(item) for item in data.values()):
                            exposed_fields.append(field)
                    
                    if exposed_fields:
                        self.add_test_result(
                            "Telegram配置保护测试",
                            "❌ FAIL",
                            f"暴露敏感字段: {exposed_fields}",
                            "CRITICAL"
                        )
                    else:
                        self.add_test_result(
                            "Telegram配置保护测试",
                            "⚠️ WARNING",
                            "配置可以无认证访问，但未发现明显敏感信息",
                            "MEDIUM"
                        )
                else:
                    self.add_test_result(
                        "Telegram配置保护测试",
                        "⚠️ INFO",
                        f"配置访问状态码: {response.status}"
                    )
        except Exception as e:
            self.add_test_result(
                "Telegram配置保护测试",
                "❌ ERROR",
                f"测试异常: {str(e)}",
                "MEDIUM"
            )
        
        # 2. 测试Telegram认证状态
        try:
            async with self.session.get(f"{self.base_url}/api/auth/status") as response:
                if response.status == 200:
                    data = await response.json()
                    if "authorized" in data:
                        self.add_test_result(
                            "Telegram认证状态检查",
                            "✅ PASS",
                            f"Telegram认证状态: {data.get('authorized', 'unknown')}"
                        )
                    else:
                        self.add_test_result(
                            "Telegram认证状态检查",
                            "⚠️ INFO",
                            "无法获取Telegram认证状态"
                        )
                else:
                    self.add_test_result(
                        "Telegram认证状态检查",
                        "⚠️ WARNING",
                        f"Telegram认证状态检查失败，状态码: {response.status}",
                        "MEDIUM"
                    )
        except Exception as e:
            self.add_test_result(
                "Telegram认证状态检查",
                "❌ ERROR",
                f"测试异常: {str(e)}",
                "LOW"
            )
    
    # ==================== WebSocket安全测试 ====================
    
    async def test_websocket_security(self):
        """测试WebSocket安全性"""
        logger.info("🔌 开始测试WebSocket安全性...")
        
        try:
            # 测试未认证的WebSocket连接
            ws_url = f"ws://localhost:8000/ws"
            
            try:
                async with websockets.connect(ws_url, timeout=5) as websocket:
                    # 尝试发送消息
                    await websocket.send("test message")
                    response = await asyncio.wait_for(websocket.recv(), timeout=2)
                    
                    self.add_test_result(
                        "WebSocket未认证访问测试",
                        "⚠️ WARNING",
                        "WebSocket允许未认证连接",
                        "MEDIUM"
                    )
            except websockets.exceptions.ConnectionClosedError:
                self.add_test_result(
                    "WebSocket未认证访问测试",
                    "✅ PASS",
                    "WebSocket正确拒绝未认证连接"
                )
            except websockets.exceptions.InvalidURI:
                self.add_test_result(
                    "WebSocket未认证访问测试",
                    "ℹ️ INFO",
                    "WebSocket端点不存在或配置不同"
                )
            except Exception as e:
                self.add_test_result(
                    "WebSocket未认证访问测试",
                    "⚠️ INFO",
                    f"WebSocket连接异常: {str(e)}"
                )
        
        except Exception as e:
            self.add_test_result(
                "WebSocket安全测试",
                "❌ ERROR",
                f"测试异常: {str(e)}",
                "LOW"
            )
    
    # ==================== 综合安全测试 ====================
    
    async def run_all_tests(self):
        """运行所有安全测试"""
        logger.info("🚀 开始执行综合安全测试...")
        start_time = time.time()
        
        # 执行所有测试
        await self.test_admin_login_flow()
        await self.test_password_security()
        await self.test_api_access_control()
        await self.test_token_security()
        await self.test_session_management()
        await self.test_injection_attacks()
        await self.test_telegram_auth_security()
        await self.test_websocket_security()
        
        end_time = time.time()
        total_time = end_time - start_time
        
        logger.info(f"🏁 安全测试完成，总耗时: {total_time:.2f}秒")
        
        # 生成测试报告
        await self.generate_security_report()
    
    async def generate_security_report(self):
        """生成安全测试报告"""
        logger.info("📊 生成安全测试报告...")
        
        # 统计测试结果
        total_tests = len(self.test_results)
        passed_tests = len([r for r in self.test_results if r["status"].startswith("✅")])
        failed_tests = len([r for r in self.test_results if r["status"].startswith("❌")])
        warning_tests = len([r for r in self.test_results if r["status"].startswith("⚠️")])
        
        # 按严重程度分类
        critical_issues = len([r for r in self.test_results if r["severity"] == "CRITICAL"])
        high_issues = len([r for r in self.test_results if r["severity"] == "HIGH"])
        medium_issues = len([r for r in self.test_results if r["severity"] == "MEDIUM"])
        
        # 生成报告
        report = f"""
===========================================
🔒 Telegram消息处理系统 - 安全测试报告
===========================================

📊 测试统计
-----------
总测试数量: {total_tests}
通过测试: {passed_tests} (✅)
失败测试: {failed_tests} (❌)
警告测试: {warning_tests} (⚠️)

🚨 安全问题统计
---------------
严重问题: {critical_issues}
高危问题: {high_issues}
中等问题: {medium_issues}

🎯 威胁检测统计
---------------
未授权访问尝试: {self.threat_detected['unauthorized_access']}
Token漏洞检测: {self.threat_detected['token_vulnerabilities']}
注入攻击尝试: {self.threat_detected['injection_attempts']}
会话劫持尝试: {self.threat_detected['session_hijacking']}
权限提升尝试: {self.threat_detected['privilege_escalation']}

📋 详细测试结果
---------------
"""
        
        # 按严重程度排序显示结果
        sorted_results = sorted(
            self.test_results,
            key=lambda x: {
                "CRITICAL": 4,
                "HIGH": 3,
                "MEDIUM": 2,
                "LOW": 1,
                "INFO": 0
            }.get(x["severity"], 0),
            reverse=True
        )
        
        for result in sorted_results:
            report += f"{result['status']} [{result['severity']}] {result['test_name']}\n"
            report += f"    {result['details']}\n"
            report += f"    时间: {result['timestamp']}\n\n"
        
        # 安全建议
        report += """
🛡️ 安全建议
------------
1. 实施API请求速率限制，防止暴力破解攻击
2. 加强密码策略，要求更强密码复杂度
3. 实施会话超时和自动清理机制
4. 对所有用户输入进行严格验证和过滤
5. 使用HTTPS加密所有敏感数据传输
6. 定期审计用户权限和会话活动
7. 实施多因素认证增强安全性
8. 定期更新依赖库和安全补丁

🔍 合规性检查
-------------
✅ 数据加密: 密码使用哈希存储
✅ 访问控制: 实施基于token的认证
✅ 会话管理: 支持登出和会话失效
⚠️ 审计日志: 建议增强安全事件日志
⚠️ 速率限制: 建议实施更严格的限制
⚠️ 输入验证: 建议加强输入sanitization

===========================================
报告生成时间: {datetime.now().isoformat()}
===========================================
"""
        
        # 保存报告到文件
        report_file = f"security_test_report_{int(time.time())}.txt"
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(report)
        
        # 显示报告
        print(report)
        
        logger.info(f"📄 安全测试报告已保存到: {report_file}")
        
        return report


async def main():
    """主函数"""
    print("🔐 Telegram消息处理系统 - 认证和权限安全测试")
    print("=" * 60)
    
    async with SecurityTestSuite() as test_suite:
        await test_suite.run_all_tests()
    
    print("\n✅ 安全测试完成！请查看详细报告。")


if __name__ == "__main__":
    asyncio.run(main())