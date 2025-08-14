#!/usr/bin/env python3
"""
测试消息过滤bug - 验证训练样本误删正文内容的问题
"""

# 模拟消息7842的内容
original_content = """#国内资讯**

马云为了保命，已上交全部个人财产给国家**

截正2025年8月10日**，蚂蚁集团已完成"解除马云先生控制权"，**集团表示是创始人马云自愿放弃的。

**马云把全部家产上交国家堪称时代楷模 ，**像马云这样主动把全部身家上交国家求饶一条狗命的企业家，马云不是第一个，也不会是最后一个。**第一批把全部身家上交国家保命的是王健林和赵本山**

📣**  **订阅👑👑👑👑👑👑**频道  ↓
****🔗**** **t.me/+8rnBOqnrjxM3M2Y1
✅**投稿澄清爆料**：** **@dny228"""

# 模拟训练样本中的尾部文本
tail_sample = "上交国家保命的是王健林和赵本山**\n\n📣**  **订阅👑👑👑👑👑👑**频道  ↓"

# 模拟 _apply_trained_tail_filters 的错误逻辑
def buggy_filter(content, tail_text):
    """模拟有bug的过滤逻辑"""
    if tail_text in content:
        # 找到最后一次出现的位置
        match_start = content.rfind(tail_text)
        if match_start != -1:
            # 错误地删除从这里开始的所有内容
            filtered = content[:match_start].rstrip()
            return filtered
    return content

# 测试
print("原始内容长度:", len(original_content))
print("\n原始内容前100字符:")
print(original_content[:100])
print("\n原始内容后100字符:")
print(original_content[-100:])

filtered = buggy_filter(original_content, tail_sample)
print("\n过滤后内容长度:", len(filtered))
print("\n过滤后内容:")
print(filtered)

print("\n被删除的内容:")
print(original_content[len(filtered):])

print("\n结论:")
print(f"删除了 {len(original_content) - len(filtered)} 个字符")
print(f"删除了 {(len(original_content) - len(filtered)) / len(original_content) * 100:.1f}% 的内容")
