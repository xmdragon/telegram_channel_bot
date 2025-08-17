#!/usr/bin/env python3
"""
前端页面链接功能测试脚本
模拟用户行为测试所有前端页面的链接和导航功能
"""

import asyncio
import aiohttp
import json
import re
import time
from urllib.parse import urljoin, urlparse
from dataclasses import dataclass
from typing import List, Dict, Set, Optional
from bs4 import BeautifulSoup
import logging

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class TestResult:
    """测试结果数据类"""
    url: str
    status_code: int
    response_time: float
    success: bool
    error_message: str = ""
    links_found: List[str] = None
    js_files: List[str] = None
    css_files: List[str] = None

    def __post_init__(self):
        if self.links_found is None:
            self.links_found = []
        if self.js_files is None:
            self.js_files = []
        if self.css_files is None:
            self.css_files = []

class FrontendLinkTester:
    """前端页面链接测试器"""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.session = None
        self.test_results: List[TestResult] = []
        self.visited_urls: Set[str] = set()
        
        # 测试页面列表（根据CLAUDE.md更新后的文件名）
        self.test_pages = [
            "login.html",
            "index.html", 
            "config.html",
            "ad-training-manager.html",
            "admin-manage.html",
            "media-manager.html",
            "tail-filter-manager.html",
            "threshold-dashboard.html",
            "auth.html",
            "logs.html",
            "status.html",
            "train.html"
        ]
        
        # 重命名页面映射（用于检测旧链接）
        self.renamed_pages = {
            "dashboard.html": "threshold-dashboard.html",
            "training.html": "ad-training-manager.html",
            "admin.html": "admin-manage.html",
            "media.html": "media-manager.html",
            "tail-filter.html": "tail-filter-manager.html"
        }

    async def __aenter__(self):
        """异步上下文管理器入口"""
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            connector=aiohttp.TCPConnector(limit=10)
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        if self.session:
            await self.session.close()

    async def fetch_page(self, url: str) -> TestResult:
        """获取页面并分析"""
        start_time = time.time()
        
        try:
            async with self.session.get(url) as response:
                response_time = time.time() - start_time
                content = await response.text()
                
                result = TestResult(
                    url=url,
                    status_code=response.status,
                    response_time=response_time,
                    success=response.status == 200
                )
                
                if response.status == 200:
                    # 解析HTML内容
                    soup = BeautifulSoup(content, 'html.parser')
                    
                    # 提取链接
                    links = []
                    for a_tag in soup.find_all('a', href=True):
                        href = a_tag['href']
                        if not href.startswith(('http://', 'https://', 'mailto:', 'tel:')):
                            links.append(href)
                    
                    # 提取JavaScript文件
                    js_files = []
                    for script_tag in soup.find_all('script', src=True):
                        js_files.append(script_tag['src'])
                    
                    # 提取CSS文件
                    css_files = []
                    for link_tag in soup.find_all('link', {'rel': 'stylesheet', 'href': True}):
                        css_files.append(link_tag['href'])
                    
                    result.links_found = links
                    result.js_files = js_files
                    result.css_files = css_files
                    
                else:
                    result.error_message = f"HTTP {response.status}"
                    
        except Exception as e:
            response_time = time.time() - start_time
            result = TestResult(
                url=url,
                status_code=0,
                response_time=response_time,
                success=False,
                error_message=str(e)
            )
            
        return result

    async def test_basic_connectivity(self) -> Dict[str, TestResult]:
        """测试基础连通性"""
        logger.info("🔍 开始基础连通性测试...")
        
        connectivity_results = {}
        
        for page in self.test_pages:
            url = urljoin(f"{self.base_url}/static/", page)
            logger.info(f"测试页面: {page}")
            
            result = await self.fetch_page(url)
            connectivity_results[page] = result
            self.test_results.append(result)
            
            if result.success:
                logger.info(f"  ✅ {page} - {result.status_code} ({result.response_time:.3f}s)")
            else:
                logger.error(f"  ❌ {page} - {result.error_message}")
        
        return connectivity_results

    async def test_resources(self, page_results: Dict[str, TestResult]) -> Dict[str, List[TestResult]]:
        """测试资源文件加载（JS/CSS）"""
        logger.info("🎨 开始资源文件测试...")
        
        resource_results = {}
        
        for page, page_result in page_results.items():
            if not page_result.success:
                continue
                
            page_resource_results = []
            
            # 测试CSS文件
            for css_file in page_result.css_files:
                css_url = urljoin(f"{self.base_url}/static/", css_file)
                result = await self.fetch_page(css_url)
                page_resource_results.append(result)
                
                if result.success:
                    logger.info(f"  ✅ CSS: {css_file}")
                else:
                    logger.error(f"  ❌ CSS: {css_file} - {result.error_message}")
            
            # 测试JS文件
            for js_file in page_result.js_files:
                js_url = urljoin(f"{self.base_url}/static/", js_file)
                result = await self.fetch_page(js_url)
                page_resource_results.append(result)
                
                if result.success:
                    logger.info(f"  ✅ JS: {js_file}")
                else:
                    logger.error(f"  ❌ JS: {js_file} - {result.error_message}")
            
            resource_results[page] = page_resource_results
        
        return resource_results

    async def test_navigation_links(self, page_results: Dict[str, TestResult]) -> Dict[str, Dict]:
        """测试导航链接"""
        logger.info("🧭 开始导航链接测试...")
        
        navigation_results = {}
        
        for page, page_result in page_results.items():
            if not page_result.success:
                continue
            
            page_nav_results = {
                'internal_links': [],
                'broken_links': [],
                'renamed_page_references': []
            }
            
            for link in page_result.links_found:
                # 跳过JavaScript链接和外部链接
                if link.startswith(('javascript:', '#', 'mailto:', 'tel:')):
                    continue
                
                # 检查是否是重命名页面的旧链接
                for old_name, new_name in self.renamed_pages.items():
                    if old_name in link:
                        page_nav_results['renamed_page_references'].append({
                            'link': link,
                            'old_name': old_name,
                            'new_name': new_name
                        })
                
                # 测试内部链接
                if link.startswith('./') or not link.startswith(('http://', 'https://')):
                    # 构建完整URL
                    if link.startswith('./'):
                        link_url = urljoin(f"{self.base_url}/static/", link[2:])
                    else:
                        link_url = urljoin(f"{self.base_url}/static/", link)
                    
                    # 避免重复测试
                    if link_url not in self.visited_urls:
                        self.visited_urls.add(link_url)
                        result = await self.fetch_page(link_url)
                        
                        if result.success:
                            page_nav_results['internal_links'].append({
                                'link': link,
                                'url': link_url,
                                'status': 'success'
                            })
                        else:
                            page_nav_results['broken_links'].append({
                                'link': link,
                                'url': link_url,
                                'error': result.error_message
                            })
                            logger.error(f"  ❌ 断链: {link} -> {result.error_message}")
            
            navigation_results[page] = page_nav_results
        
        return navigation_results

    async def test_api_endpoints(self) -> Dict[str, TestResult]:
        """测试API端点可访问性"""
        logger.info("🔌 开始API端点测试...")
        
        # 常用的API端点
        api_endpoints = [
            "/api/health",
            "/api/messages",
            "/api/config/system",
            "/api/admin/auth/check-auth"
        ]
        
        api_results = {}
        
        for endpoint in api_endpoints:
            url = urljoin(self.base_url, endpoint)
            result = await self.fetch_page(url)
            api_results[endpoint] = result
            
            if result.success:
                logger.info(f"  ✅ API: {endpoint}")
            else:
                logger.info(f"  ⚠️ API: {endpoint} - {result.error_message} (可能需要认证)")
        
        return api_results

    def generate_report(self, connectivity_results, resource_results, navigation_results, api_results) -> str:
        """生成测试报告"""
        report = []
        report.append("=" * 80)
        report.append("🧪 前端页面链接功能测试报告")
        report.append("=" * 80)
        report.append(f"测试时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        report.append(f"基础URL: {self.base_url}")
        report.append("")
        
        # 1. 基础连通性测试结果
        report.append("📊 1. 基础连通性测试结果")
        report.append("-" * 50)
        
        success_count = 0
        total_count = len(connectivity_results)
        
        for page, result in connectivity_results.items():
            status_icon = "✅" if result.success else "❌"
            report.append(f"{status_icon} {page:25} | {result.status_code:3} | {result.response_time:.3f}s")
            if result.success:
                success_count += 1
            if not result.success:
                report.append(f"    错误: {result.error_message}")
        
        report.append(f"\n成功率: {success_count}/{total_count} ({success_count/total_count*100:.1f}%)")
        
        # 2. 资源文件测试结果
        report.append("\n🎨 2. 资源文件测试结果")
        report.append("-" * 50)
        
        total_resources = 0
        successful_resources = 0
        
        for page, resources in resource_results.items():
            if resources:
                report.append(f"\n📄 {page}:")
                for resource in resources:
                    total_resources += 1
                    resource_name = resource.url.split('/')[-1]
                    status_icon = "✅" if resource.success else "❌"
                    report.append(f"  {status_icon} {resource_name}")
                    if resource.success:
                        successful_resources += 1
        
        if total_resources > 0:
            report.append(f"\n资源加载成功率: {successful_resources}/{total_resources} ({successful_resources/total_resources*100:.1f}%)")
        
        # 3. 导航链接测试结果
        report.append("\n🧭 3. 导航链接测试结果")
        report.append("-" * 50)
        
        total_broken_links = 0
        total_renamed_references = 0
        
        for page, nav_result in navigation_results.items():
            if nav_result['broken_links'] or nav_result['renamed_page_references']:
                report.append(f"\n📄 {page}:")
                
                # 断链
                if nav_result['broken_links']:
                    report.append("  ❌ 断链:")
                    for broken in nav_result['broken_links']:
                        report.append(f"    • {broken['link']} -> {broken['error']}")
                        total_broken_links += 1
                
                # 重命名页面引用
                if nav_result['renamed_page_references']:
                    report.append("  ⚠️ 旧页面名称引用:")
                    for ref in nav_result['renamed_page_references']:
                        report.append(f"    • {ref['link']} (应更新为 {ref['new_name']})")
                        total_renamed_references += 1
                
                # 成功链接
                if nav_result['internal_links']:
                    report.append(f"  ✅ 正常链接: {len(nav_result['internal_links'])}个")
        
        if total_broken_links == 0 and total_renamed_references == 0:
            report.append("✅ 所有导航链接正常，无断链或旧引用")
        
        # 4. API端点测试结果
        report.append("\n🔌 4. API端点测试结果")
        report.append("-" * 50)
        
        for endpoint, result in api_results.items():
            status_icon = "✅" if result.success else "⚠️"
            report.append(f"{status_icon} {endpoint:30} | {result.status_code}")
        
        # 5. 重构后的页面验证
        report.append("\n🔄 5. 重构后的页面验证")
        report.append("-" * 50)
        
        renamed_pages_status = []
        for old_name, new_name in self.renamed_pages.items():
            old_result = connectivity_results.get(old_name)
            new_result = connectivity_results.get(new_name)
            
            if old_result:
                renamed_pages_status.append(f"❌ {old_name} 仍然存在 (应该已删除)")
            if new_result and new_result.success:
                renamed_pages_status.append(f"✅ {new_name} 正常访问")
            elif new_name in self.test_pages:
                renamed_pages_status.append(f"❌ {new_name} 无法访问")
        
        if renamed_pages_status:
            report.extend(renamed_pages_status)
        else:
            report.append("✅ 所有重命名页面正常")
        
        # 6. 总结和建议
        report.append("\n📋 6. 测试总结和建议")
        report.append("-" * 50)
        
        issues = []
        
        if total_broken_links > 0:
            issues.append(f"发现 {total_broken_links} 个断链需要修复")
        
        if total_renamed_references > 0:
            issues.append(f"发现 {total_renamed_references} 个旧页面名称引用需要更新")
        
        if success_count < total_count:
            failed_pages = [page for page, result in connectivity_results.items() if not result.success]
            issues.append(f"以下页面无法访问: {', '.join(failed_pages)}")
        
        if successful_resources < total_resources:
            issues.append(f"部分资源文件加载失败")
        
        if issues:
            report.append("⚠️ 发现的问题:")
            for issue in issues:
                report.append(f"  • {issue}")
        else:
            report.append("✅ 所有测试通过，系统状态良好")
        
        report.append("\n" + "=" * 80)
        
        return "\n".join(report)

async def main():
    """主函数"""
    async with FrontendLinkTester() as tester:
        # 1. 基础连通性测试
        connectivity_results = await tester.test_basic_connectivity()
        
        # 2. 资源文件测试
        resource_results = await tester.test_resources(connectivity_results)
        
        # 3. 导航链接测试
        navigation_results = await tester.test_navigation_links(connectivity_results)
        
        # 4. API端点测试
        api_results = await tester.test_api_endpoints()
        
        # 5. 生成报告
        report = tester.generate_report(
            connectivity_results, 
            resource_results, 
            navigation_results, 
            api_results
        )
        
        print(report)
        
        # 保存报告到文件
        report_file = f"frontend_test_report_{int(time.time())}.txt"
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(report)
        
        print(f"\n📄 测试报告已保存到: {report_file}")

if __name__ == "__main__":
    asyncio.run(main())