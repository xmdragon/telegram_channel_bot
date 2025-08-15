import requests
import json

# 模拟提交尾部训练数据
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

print("提交完整3行尾部数据...")
print(f"尾部内容行数: {len(data1['tailPart'].split(chr(10)))}")
print(f"尾部内容: {repr(data1['tailPart'][:50])}...")

response = requests.post(url, json=data1)
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

print("提交单行尾部数据...")
print(f"尾部内容行数: {len(data2['tailPart'].split(chr(10)))}")
print(f"尾部内容: {repr(data2['tailPart'])}")

response = requests.post(url, json=data2)
print(f"响应: {response.json()}")
