#!/usr/bin/env python3
"""
测试多个训练样本片段连续匹配导致的内容破坏
"""

original = """#国内资讯**

马云为了保命，已上交全部个人财产给国家**

截正2025年8月10日**，蚂蚁集团已完成"解除马云先生控制权"，**集团表示是创始人马云自愿放弃的。

**马云把全部家产上交国家堪称时代楷模 ，**像马云这样主动把全部身家上交国家求饶一条狗命的企业家，马云不是第一个，也不会是最后一个。**第一批把全部身家上交国家保命的是王健林和赵本山**

📣**  **订阅👑👑👑👑👑👑**频道  ↓
****🔗**** **t.me/+8rnBOqnrjxM3M2Y1
✅**投稿澄清爆料**：** **@dny228"""

# 可能的训练样本片段
samples = [
    "马云为了保命",  # 可能的片段1
    "月",  # 可能的片段2（来自其他样本）
    "蚂蚁",  # 可能的片段3
    "t.me/+",  # 可能的片段4
    "订阅",  # 可能的片段5
    "上交国家保命的是王健林和赵本山**\n\n📣**  **订阅"  # 长片段
]

def simulate_buggy_filter(content, samples):
    """模拟多个样本片段的错误匹配"""
    result = content
    for sample in samples:
        if sample in result:
            # 这里的逻辑可能更复杂，可能会删除包含这个片段的整个部分
            parts = result.split(sample)
            if len(parts) > 1:
                # 可能的错误逻辑：删除片段及其周围的一些内容
                print(f"匹配到片段: '{sample}'")
                # 简单模拟：删除片段本身
                result = result.replace(sample, "", 1)  # 只替换第一次出现
    return result

filtered = simulate_buggy_filter(original, samples)
print("\n过滤后:")
print(filtered[:200])
print("\n这解释了为什么会有多处片段被删除！")
