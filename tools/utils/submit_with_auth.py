import requests
import json

# 先获取登录token
login_url = "http://localhost:8000/api/admin/login"
login_data = {"username": "admin", "password": "admin888"}
login_resp = requests.post(login_url, json=login_data)
token = login_resp.json().get("access_token")

if not token:
    print("登录失败")
    exit(1)

headers = {"Authorization": f"Bearer {token}"}

# 测试提交尾部训练数据
url = "http://localhost:8000/api/training/tail-filter-samples"

# 测试1：提交完整的3行尾部
data1 = {
    "content": """**#柬泰冲突****：奥斯玛的也在撤退了！

**👌订阅频道：@miandianDs
👌投稿爆料： @QianQian106
👌海外交友； @tmiandianKs""",
    "tailPart": """**👌订阅频道：@miandianDs
👌投稿爆料： @QianQian106
👌海外交友； @tmiandianKs""",
    "message_id": 7891
}

print("=" * 50)
print("测试1: 提交完整3行尾部数据")
print(f"尾部内容行数: {len(data1['tailPart'].splitlines())}")
print(f"尾部内容长度: {len(data1['tailPart'])} 字符")
print(f"尾部内容预览:\n{data1['tailPart']}")
print("-" * 30)

response = requests.post(url, json=data1, headers=headers)
print(f"响应: {response.json()}\n")

# 测试2：只提交最后一行
data2 = {
    "content": """**#柬泰冲突****：奥斯玛的也在撤退了！

**👌订阅频道：@miandianDs
👌投稿爆料： @QianQian106
👌海外交友； @tmiandianKs""",
    "tailPart": "👌海外交友； @tmiandianKs",
    "message_id": 7892
}

print("=" * 50)
print("测试2: 提交单行尾部数据")
print(f"尾部内容行数: {len(data2['tailPart'].splitlines())}")
print(f"尾部内容长度: {len(data2['tailPart'])} 字符")
print(f"尾部内容: {data2['tailPart']}")
print("-" * 30)

response = requests.post(url, json=data2, headers=headers)
print(f"响应: {response.json()}")
