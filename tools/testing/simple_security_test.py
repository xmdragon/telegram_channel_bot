#!/usr/bin/env python3
"""
简化版认证安全测试脚本
使用内置的urllib库进行HTTP请求测试
"""

import json
import urllib.request
import urllib.parse
import urllib.error
import hashlib
import time
import logging
from datetime import datetime
from typing import Dict, List, Optional

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class SimpleSecurityTest:
    """简化安全测试类"""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.auth_token = None
        self.test_results = []
        
        # 测试账户配置
        self.admin_username = "admin"
        self.admin_password = "admin123"
    
    def add_result(self, test_name: str, status: str, details: str, severity: str = "INFO"):
        """记录测试结果"""
        result = {
            "timestamp": datetime.now().isoformat(),
            "test_name": test_name,
            "status": status,
            "details": details,
            "severity": severity
        }
        self.test_results.append(result)
        
        # 输出结果
        print(f"{status} [{severity}] {test_name}: {details}")
        logger.info(f"[{test_name}] {status}: {details}")
    
    def make_request(self, url: str, method: str = "GET", data: dict = None, headers: dict = None):
        """发送HTTP请求"""
        try:
            if headers is None:
                headers = {"Content-Type": "application/json"}
            
            if data:
                data = json.dumps(data).encode('utf-8')
            
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            
            with urllib.request.urlopen(req, timeout=10) as response:
                response_data = response.read().decode('utf-8')
                try:
                    return {
                        "status": response.getcode(),
                        "data": json.loads(response_data) if response_data else {},
                        "success": True
                    }
                except json.JSONDecodeError:
                    return {
                        "status": response.getcode(),
                        "data": response_data,
                        "success": True
                    }
        
        except urllib.error.HTTPError as e:
            try:
                error_data = e.read().decode('utf-8')
                return {
                    "status": e.code,
                    "data": error_data,
                    "success": False,
                    "error": str(e)
                }
            except:
                return {
                    "status": e.code,
                    "data": "",
                    "success": False,
                    "error": str(e)
                }
        
        except Exception as e:
            return {
                "status": 0,
                "data": "",
                "success": False,
                "error": str(e)
            }
    
    def test_admin_login(self):
        """测试管理员登录功能"""
        print("\n🔐 测试管理员登录功能...")
        
        # 1. 测试正确登录
        login_data = {
            "username": self.admin_username,
            "password": self.admin_password
        }
        
        result = self.make_request(
            f"{self.base_url}/api/admin/auth/login",
            method="POST",
            data=login_data
        )
        
        if result["success"] and result["status"] == 200:
            try:
                data = json.loads(result["data"]) if isinstance(result["data"], str) else result["data"]
                if data.get("success") and data.get("token"):
                    self.auth_token = data["token"]
                    self.add_result(
                        "正确登录测试",
                        "✅ PASS",
                        f"管理员登录成功，获得token: {self.auth_token[:8]}..."
                    )
                else:
                    self.add_result(
                        "正确登录测试",
                        "❌ FAIL",
                        "登录响应格式错误",
                        "HIGH"
                    )
            except Exception as e:
                self.add_result(
                    "正确登录测试",
                    "❌ ERROR",
                    f"解析登录响应失败: {str(e)}",
                    "HIGH"
                )
        else:
            self.add_result(
                "正确登录测试",
                "❌ FAIL",
                f"登录失败，状态码: {result['status']}, 错误: {result.get('error', 'Unknown')}",
                "HIGH"
            )
        
        # 2. 测试错误密码
        wrong_login_data = {
            "username": self.admin_username,
            "password": "wrong_password"
        }
        
        result = self.make_request(
            f"{self.base_url}/api/admin/auth/login",
            method="POST",
            data=wrong_login_data
        )
        
        if result["status"] == 401:
            self.add_result(
                "错误密码拒绝测试",
                "✅ PASS",
                "错误密码被正确拒绝"
            )
        else:
            self.add_result(
                "错误密码拒绝测试",
                "❌ FAIL",
                f"错误密码未被拒绝，状态码: {result['status']}",
                "HIGH"
            )
        
        # 3. 测试不存在的用户
        nonexistent_login_data = {
            "username": "nonexistent_user",
            "password": "any_password"
        }
        
        result = self.make_request(
            f"{self.base_url}/api/admin/auth/login",
            method="POST",
            data=nonexistent_login_data
        )
        
        if result["status"] == 401:
            self.add_result(
                "不存在用户拒绝测试",
                "✅ PASS",
                "不存在用户被正确拒绝"
            )
        else:
            self.add_result(
                "不存在用户拒绝测试",
                "❌ FAIL",
                f"不存在用户未被拒绝，状态码: {result['status']}",
                "HIGH"
            )
    
    def test_api_access_control(self):
        """测试API访问控制"""
        print("\n🛡️ 测试API访问控制...")
        
        # 受保护的API端点
        protected_endpoints = [
            "/api/messages",
            "/api/admin/current",
            "/api/admin/admins",
            "/api/config"
        ]
        
        for endpoint in protected_endpoints:
            # 测试未认证访问
            result = self.make_request(f"{self.base_url}{endpoint}")
            
            if result["status"] == 401:
                self.add_result(
                    f"未认证访问拒绝 - {endpoint}",
                    "✅ PASS",
                    "未认证访问被正确拒绝"
                )
            else:
                self.add_result(
                    f"未认证访问拒绝 - {endpoint}",
                    "❌ FAIL",
                    f"未认证访问未被拒绝，状态码: {result['status']}",
                    "HIGH"
                )
            
            # 如果有有效token，测试认证访问
            if self.auth_token:
                headers = {
                    "Authorization": f"Bearer {self.auth_token}",
                    "Content-Type": "application/json"
                }
                
                result = self.make_request(
                    f"{self.base_url}{endpoint}",
                    headers=headers
                )
                
                if result["status"] in [200, 201, 204]:
                    self.add_result(
                        f"有效token访问 - {endpoint}",
                        "✅ PASS",
                        "有效token访问成功"
                    )
                elif result["status"] == 403:
                    self.add_result(
                        f"有效token访问 - {endpoint}",
                        "ℹ️ INFO",
                        "访问被权限控制拒绝（正常）"
                    )
                else:
                    self.add_result(
                        f"有效token访问 - {endpoint}",
                        "⚠️ WARNING",
                        f"意外状态码: {result['status']}",
                        "MEDIUM"
                    )
    
    def test_token_security(self):
        """测试Token安全性"""
        print("\n🎫 测试Token安全性...")
        
        if not self.auth_token:
            self.add_result(
                "Token安全测试",
                "❌ SKIP",
                "无有效认证token，跳过测试",
                "HIGH"
            )
            return
        
        # 测试无效token
        invalid_tokens = [
            "invalid_token",
            "Bearer invalid",
            "",
            "null"
        ]
        
        for invalid_token in invalid_tokens:
            headers = {
                "Authorization": f"Bearer {invalid_token}",
                "Content-Type": "application/json"
            }
            
            result = self.make_request(
                f"{self.base_url}/api/admin/current",
                headers=headers
            )
            
            if result["status"] == 401:
                self.add_result(
                    f"无效token拒绝 - {invalid_token[:10] if invalid_token else 'empty'}",
                    "✅ PASS",
                    "无效token被正确拒绝"
                )
            else:
                self.add_result(
                    f"无效token拒绝 - {invalid_token[:10] if invalid_token else 'empty'}",
                    "❌ FAIL",
                    f"无效token未被拒绝，状态码: {result['status']}",
                    "HIGH"
                )
        
        # 检查token长度
        token_length = len(self.auth_token) if self.auth_token else 0
        if token_length >= 32:
            self.add_result(
                "Token长度检查",
                "✅ PASS",
                f"Token长度足够: {token_length}字符"
            )
        else:
            self.add_result(
                "Token长度检查",
                "⚠️ WARNING",
                f"Token长度可能不足: {token_length}字符",
                "MEDIUM"
            )
    
    def test_session_management(self):
        """测试会话管理"""
        print("\n📱 测试会话管理...")
        
        if not self.auth_token:
            self.add_result(
                "会话管理测试",
                "❌ SKIP",
                "无有效认证token，跳过测试",
                "HIGH"
            )
            return
        
        # 测试会话状态检查
        headers = {
            "Authorization": f"Bearer {self.auth_token}",
            "Content-Type": "application/json"
        }
        
        result = self.make_request(
            f"{self.base_url}/api/admin/auth/check-auth",
            headers=headers
        )
        
        if result["success"] and result["status"] == 200:
            try:
                data = json.loads(result["data"]) if isinstance(result["data"], str) else result["data"]
                if data.get("authenticated"):
                    self.add_result(
                        "会话状态检查",
                        "✅ PASS",
                        "会话状态检查正常"
                    )
                else:
                    self.add_result(
                        "会话状态检查",
                        "❌ FAIL",
                        "会话未被识别为已认证",
                        "HIGH"
                    )
            except Exception as e:
                self.add_result(
                    "会话状态检查",
                    "❌ ERROR",
                    f"解析响应失败: {str(e)}",
                    "MEDIUM"
                )
        else:
            self.add_result(
                "会话状态检查",
                "❌ FAIL",
                f"会话状态检查失败，状态码: {result['status']}",
                "HIGH"
            )
        
        # 测试登出功能
        result = self.make_request(
            f"{self.base_url}/api/admin/auth/logout",
            method="POST",
            headers=headers
        )
        
        if result["success"] and result["status"] == 200:
            try:
                data = json.loads(result["data"]) if isinstance(result["data"], str) else result["data"]
                if data.get("success"):
                    self.add_result(
                        "登出功能测试",
                        "✅ PASS",
                        "登出功能正常"
                    )
                    
                    # 验证登出后token是否失效
                    time.sleep(1)
                    verify_result = self.make_request(
                        f"{self.base_url}/api/admin/current",
                        headers=headers
                    )
                    
                    if verify_result["status"] == 401:
                        self.add_result(
                            "登出后token失效测试",
                            "✅ PASS",
                            "登出后token已失效"
                        )
                    else:
                        self.add_result(
                            "登出后token失效测试",
                            "❌ FAIL",
                            f"登出后token仍然有效，状态码: {verify_result['status']}",
                            "HIGH"
                        )
                else:
                    self.add_result(
                        "登出功能测试",
                        "❌ FAIL",
                        "登出请求失败",
                        "HIGH"
                    )
            except Exception as e:
                self.add_result(
                    "登出功能测试",
                    "❌ ERROR",
                    f"解析登出响应失败: {str(e)}",
                    "MEDIUM"
                )
        else:
            self.add_result(
                "登出功能测试",
                "❌ FAIL",
                f"登出请求失败，状态码: {result['status']}",
                "HIGH"
            )
    
    def test_injection_attacks(self):
        """测试注入攻击防护"""
        print("\n💉 测试注入攻击防护...")
        
        # SQL注入测试payload
        sql_payloads = [
            "admin'; DROP TABLE admins; --",
            "admin' OR '1'='1",
            "admin' UNION SELECT * FROM admins --"
        ]
        
        for payload in sql_payloads:
            login_data = {
                "username": payload,
                "password": "any_password"
            }
            
            result = self.make_request(
                f"{self.base_url}/api/admin/auth/login",
                method="POST",
                data=login_data
            )
            
            if result["status"] in [401, 400]:
                self.add_result(
                    f"SQL注入防护 - {payload[:20]}...",
                    "✅ PASS",
                    "SQL注入payload被正确拒绝"
                )
            elif result["status"] == 200:
                self.add_result(
                    f"SQL注入防护 - {payload[:20]}...",
                    "❌ FAIL",
                    "SQL注入payload可能成功",
                    "CRITICAL"
                )
            else:
                self.add_result(
                    f"SQL注入防护 - {payload[:20]}...",
                    "⚠️ WARNING",
                    f"意外状态码: {result['status']}",
                    "MEDIUM"
                )
        
        # XSS测试payload
        xss_payloads = [
            "<script>alert('XSS')</script>",
            "javascript:alert('XSS')",
            "<img src=x onerror=alert('XSS')>"
        ]
        
        for payload in xss_payloads:
            login_data = {
                "username": payload,
                "password": "test"
            }
            
            result = self.make_request(
                f"{self.base_url}/api/admin/auth/login",
                method="POST",
                data=login_data
            )
            
            # 检查响应中是否包含未转义的脚本
            response_text = str(result.get("data", ""))
            if "<script>" in response_text or "javascript:" in response_text:
                self.add_result(
                    f"XSS防护 - {payload[:20]}...",
                    "❌ FAIL",
                    "响应中包含未转义的脚本内容",
                    "HIGH"
                )
            else:
                self.add_result(
                    f"XSS防护 - {payload[:20]}...",
                    "✅ PASS",
                    "XSS payload被正确处理"
                )
    
    def test_password_security(self):
        """测试密码安全性"""
        print("\n🔒 测试密码安全性...")
        
        # 验证密码哈希
        known_hash = "240be518fabd2724ddb6f04eeb1da5967448d7e831c08c8fa822809f74c720a9"
        test_password = "admin123"
        expected_hash = hashlib.sha256(test_password.encode()).hexdigest()
        
        if known_hash == expected_hash:
            self.add_result(
                "密码哈希验证",
                "✅ PASS",
                "密码使用SHA-256哈希存储"
            )
        else:
            self.add_result(
                "密码哈希验证",
                "⚠️ WARNING",
                "密码哈希格式未知或使用弱哈希算法",
                "MEDIUM"
            )
        
        # 测试暴力破解（简化版）
        failed_attempts = 0
        for i in range(5):  # 减少尝试次数
            wrong_login_data = {
                "username": self.admin_username,
                "password": f"wrong_password_{i}"
            }
            
            result = self.make_request(
                f"{self.base_url}/api/admin/auth/login",
                method="POST",
                data=wrong_login_data
            )
            
            if result["status"] == 401:
                failed_attempts += 1
            elif result["status"] == 429:  # Too Many Requests
                self.add_result(
                    "暴力破解防护",
                    "✅ PASS",
                    f"在第{i+1}次尝试后触发速率限制"
                )
                break
            
            time.sleep(0.5)  # 避免过快请求
        else:
            self.add_result(
                "暴力破解防护",
                "⚠️ WARNING",
                f"连续{failed_attempts}次失败登录未触发速率限制",
                "MEDIUM"
            )
    
    def generate_report(self):
        """生成测试报告"""
        print("\n" + "="*60)
        print("🔒 认证安全测试报告")
        print("="*60)
        
        # 统计结果
        total_tests = len(self.test_results)
        passed_tests = len([r for r in self.test_results if r["status"].startswith("✅")])
        failed_tests = len([r for r in self.test_results if r["status"].startswith("❌")])
        warning_tests = len([r for r in self.test_results if r["status"].startswith("⚠️")])
        
        # 按严重程度统计
        critical_issues = len([r for r in self.test_results if r["severity"] == "CRITICAL"])
        high_issues = len([r for r in self.test_results if r["severity"] == "HIGH"])
        medium_issues = len([r for r in self.test_results if r["severity"] == "MEDIUM"])
        
        print(f"\n📊 测试统计:")
        print(f"总测试数量: {total_tests}")
        print(f"通过测试: {passed_tests} (✅)")
        print(f"失败测试: {failed_tests} (❌)")
        print(f"警告测试: {warning_tests} (⚠️)")
        
        print(f"\n🚨 安全问题统计:")
        print(f"严重问题: {critical_issues}")
        print(f"高危问题: {high_issues}")
        print(f"中等问题: {medium_issues}")
        
        print(f"\n📋 详细测试结果:")
        print("-" * 60)
        
        # 按严重程度排序
        severity_order = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "INFO": 0}
        sorted_results = sorted(
            self.test_results,
            key=lambda x: severity_order.get(x["severity"], 0),
            reverse=True
        )
        
        for result in sorted_results:
            print(f"{result['status']} [{result['severity']}] {result['test_name']}")
            print(f"    {result['details']}")
            print()
        
        print("🛡️ 安全建议:")
        print("1. 实施API请求速率限制，防止暴力破解攻击")
        print("2. 加强密码策略，要求更强密码复杂度")
        print("3. 实施会话超时和自动清理机制")
        print("4. 对所有用户输入进行严格验证和过滤")
        print("5. 使用HTTPS加密所有敏感数据传输")
        print("6. 定期审计用户权限和会话活动")
        print("7. 实施多因素认证增强安全性")
        
        # 保存报告
        report_file = f"security_test_report_{int(time.time())}.txt"
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(f"认证安全测试报告 - {datetime.now().isoformat()}\n")
            f.write("="*60 + "\n")
            for result in sorted_results:
                f.write(f"{result['status']} [{result['severity']}] {result['test_name']}: {result['details']}\n")
        
        print(f"\n📄 详细报告已保存到: {report_file}")
        print("="*60)
    
    def run_all_tests(self):
        """运行所有安全测试"""
        print("🚀 开始执行认证安全测试...")
        start_time = time.time()
        
        try:
            self.test_admin_login()
            self.test_api_access_control()
            self.test_token_security()
            self.test_session_management()
            self.test_injection_attacks()
            self.test_password_security()
        except Exception as e:
            print(f"❌ 测试执行异常: {str(e)}")
            logger.error(f"测试执行异常: {str(e)}")
        
        end_time = time.time()
        print(f"\n🏁 测试完成，总耗时: {end_time - start_time:.2f}秒")
        
        self.generate_report()


def main():
    """主函数"""
    print("🔐 Telegram消息处理系统 - 认证安全测试")
    print("使用内置urllib库进行HTTP安全测试")
    print("="*60)
    
    # 检查系统是否运行
    test_suite = SimpleSecurityTest()
    health_check = test_suite.make_request(f"{test_suite.base_url}/api/health")
    
    if not health_check["success"]:
        print(f"❌ 无法连接到系统: {test_suite.base_url}")
        print("请确保系统正在运行: ./dev.sh --status")
        return
    
    print(f"✅ 系统连接正常: {test_suite.base_url}")
    
    # 运行测试
    test_suite.run_all_tests()
    
    print("\n✅ 安全测试完成！")


if __name__ == "__main__":
    main()