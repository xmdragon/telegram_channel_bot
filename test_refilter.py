import requests
import json

# 登录获取token
login_url = "http://localhost:8000/api/admin/login"
login_data = {"username": "admin", "password": "admin123"}
login_resp = requests.post(login_url, json=login_data)

if login_resp.status_code != 200:
    print("尝试其他密码...")
    login_data = {"username": "admin", "password": "admin888"}
    login_resp = requests.post(login_url, json=login_data)

if login_resp.status_code != 200:
    print(f"登录失败: {login_resp.text}")
    exit(1)

token = login_resp.json().get("access_token")
print(f"登录成功，获取token")

headers = {"Authorization": f"Bearer {token}"}

# 测试重新过滤消息7891
print("\n" + "=" * 50)
print("重新过滤消息7891...")
refilter_url = "http://localhost:8000/api/messages/7891/refilter"
response = requests.post(refilter_url, headers=headers)

if response.status_code == 200:
    result = response.json()
    print(f"过滤成功:")
    print(f"  原始长度: {result.get('original_length')} 字符")
    print(f"  过滤后长度: {result.get('filtered_length')} 字符")
    print(f"  减少: {result.get('reduction')} 字符")
else:
    print(f"过滤失败: {response.text}")

# 验证过滤结果
print("\n" + "=" * 50)
print("验证过滤结果...")
get_url = "http://localhost:8000/api/messages/7891"
response = requests.get(get_url, headers=headers)

if response.status_code == 200:
    message = response.json()["message"]
    print(f"原始内容长度: {len(message['content']) if message['content'] else 0}")
    print(f"过滤内容长度: {len(message['filtered_content']) if message['filtered_content'] else 0}")
    print(f"\n过滤后内容:")
    print(message['filtered_content'][:200] if message['filtered_content'] else "无")
else:
    print(f"获取消息失败: {response.text}")
