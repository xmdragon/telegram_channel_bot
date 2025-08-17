#!/usr/bin/env python3
"""
简化的训练API测试脚本 - 直接测试核心端点
绕过健康检查，直接验证功能端点
"""

import requests
import json
import time
from datetime import datetime

def test_training_api():
    """
    测试训练相关的核心API端点
    """
    base_url = "http://localhost:8000"
    
    # 核心训练API端点
    endpoints = [
        {
            "name": "训练统计",
            "url": "/api/training-db/stats",
            "method": "GET"
        },
        {
            "name": "广告样本列表", 
            "url": "/api/training-db/ad-samples",
            "method": "GET"
        },
        {
            "name": "频道列表",
            "url": "/api/training-db/channels", 
            "method": "GET"
        },
        {
            "name": "训练历史",
            "url": "/api/training-db/history",
            "method": "GET"
        },
        {
            "name": "尾部过滤统计",
            "url": "/api/training-db/tail-filter-statistics",
            "method": "GET"
        }
    ]
    
    results = []
    print(f"开始测试训练API端点... {datetime.now()}")
    print("="*60)
    
    for endpoint in endpoints:
        try:
            start_time = time.time()
            
            response = requests.get(
                f"{base_url}{endpoint['url']}",
                timeout=10
            )
            
            response_time = time.time() - start_time
            
            result = {
                "name": endpoint["name"],
                "url": endpoint["url"],
                "status_code": response.status_code,
                "response_time": f"{response_time:.3f}s",
                "success": response.status_code == 200
            }
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    result["data_type"] = type(data).__name__
                    if isinstance(data, list):
                        result["data_count"] = len(data)
                    elif isinstance(data, dict):
                        result["data_keys"] = len(data.keys())
                    print(f"✅ {endpoint['name']}: {response.status_code} ({response_time:.3f}s)")
                except:
                    result["data_type"] = "non-json"
                    print(f"✅ {endpoint['name']}: {response.status_code} ({response_time:.3f}s) - 非JSON响应")
            else:
                print(f"❌ {endpoint['name']}: {response.status_code} ({response_time:.3f}s)")
                result["error"] = response.text[:200]
                
            results.append(result)
            
        except requests.exceptions.ConnectionError:
            print(f"❌ {endpoint['name']}: 连接失败")
            results.append({
                "name": endpoint["name"],
                "url": endpoint["url"],
                "error": "连接失败",
                "success": False
            })
        except Exception as e:
            print(f"❌ {endpoint['name']}: 异常 - {e}")
            results.append({
                "name": endpoint["name"], 
                "url": endpoint["url"],
                "error": str(e),
                "success": False
            })
    
    # 统计结果
    total_tests = len(results)
    successful_tests = sum(1 for r in results if r.get("success", False))
    failed_tests = total_tests - successful_tests
    
    print("\n" + "="*60)
    print(f"测试完成 - 总计: {total_tests}, 成功: {successful_tests}, 失败: {failed_tests}")
    print(f"成功率: {(successful_tests/total_tests*100):.1f}%")
    
    # 保存详细结果
    with open("tools/testing/simple_api_test_results.json", "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total": total_tests,
                "successful": successful_tests,
                "failed": failed_tests,
                "success_rate": successful_tests/total_tests*100
            },
            "results": results
        }, f, indent=2, ensure_ascii=False)
    
    print(f"\n详细结果已保存到: tools/testing/simple_api_test_results.json")
    return results

if __name__ == "__main__":
    test_training_api()
