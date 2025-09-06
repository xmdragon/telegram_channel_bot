import requests
import json
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))

from app.core.url_config import url_config

# 模拟提交尾部训练数据
url = url_config.get_api_url("training/tail-filter-samples")

# 为消息7911添加完整的尾部训练
data = {
    "content": """#网友投稿    #百乐门这超速抓人

天下公寓大路过来这里抓摩托超速的，玛德，老子上次就因为开摩托超速罚款，后面一直慢慢的开，这次我开的很慢，结果还是被抓罚款。到现在才看到亚太的坑比，就是想要搞钱吃

☎️投稿商务曝光☎️  ：@A166688899

👍亚太新闻频道👍 https://t.me/yyds518899

🔞亚太色情吃瓜 🔞 ：https://t.me/saisaissssss168168

便民服务中文包 https://t.me/setlanguage/classic-zh-cn""",
    "tailPart": """☎️投稿商务曝光☎️  ：@A166688899

👍亚太新闻频道👍 https://t.me/yyds518899

🔞亚太色情吃瓜 🔞 ：https://t.me/saisaissssss168168

便民服务中文包 https://t.me/setlanguage/classic-zh-cn""",
    "message_id": 7911
}

print("提交尾部训练数据...")
print(f"尾部内容行数: {len(data['tailPart'].splitlines())}")
print(f"尾部内容长度: {len(data['tailPart'])} 字符")

# 使用简单的方式提交（不需要认证的测试）
response = requests.post(url, json=data)
print(f"响应状态: {response.status_code}")
print(f"响应内容: {response.text[:200]}")
