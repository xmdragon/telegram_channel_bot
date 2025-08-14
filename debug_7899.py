import sys
sys.path.append('/Users/eric/workspace/telegram_channel_bot')

from app.services.intelligent_tail_filter import intelligent_tail_filter

content = """暑假即将结束，迪拜国际机场将迎来返程高峰 

迪拜国际机场（DXB）已进入暑期收官繁忙期的筹备阶段，预计8月13日至25日期间将迎送超360万人次旅客，主要因假期收尾学生开学。

据预测，每日平均旅客流量将达28万人次，其中8月15日（周五）预计将迎来单日客流峰值，突破29万人次。

此次开学季客流高峰紧随2025年上半年创纪录业绩而来。同期迪拜接待国际过夜游客达988万人次，较去年增长6%；迪拜国际机场处理旅客超4600万人次，进一步巩固其全球最繁忙客运机场的地位。

迪拜机场正与航空公司、监管机构及商业合作伙伴等机场生态系统成员协同联动，全力保障高峰期旅客出行体验顺畅。

🛎失联导航：@Wdubai
✅订阅频道：@dubai0
🙋‍♂️便民信息：
【[迪拜互助群](https://t.me/+PquyxdGQsXEwZjUx)】【[TG中文包](tg://setlanguage?lang=classic-zh-cn)】【[签证查询](https://smartservices.icp.gov.ae/echannels/web/client/default.html?from=timeline&isappinstalled=0#/fileValidity)】"""

lines = content.split('\n')
print(f"总行数: {len(lines)}")

# 测试尾部（从空行后的第一行"🛎失联导航：@Wdubai"开始）
tail_start = 6  # 第7行（索引6）是空行后的第一行
tail_content = '\n'.join(lines[tail_start:])
print(f"\n尾部内容（从第{tail_start+1}行开始）:")
print(f"长度: {len(tail_content)}")
print(f"内容预览: {tail_content[:100]}...")

# 测试is_tail判定
is_tail_result = intelligent_tail_filter.is_tail(tail_content)
print(f"\nis_tail判定: {is_tail_result}")

# 提取特征
features = intelligent_tail_filter.feature_extractor.extract_features(tail_content)
print(f"\n特征:")
for key, value in features.items():
    if value > 0:
        print(f"  {key}: {value}")

# 计算特征得分
score = intelligent_tail_filter._calculate_feature_score(features)
print(f"\n特征得分: {score:.3f}")

# 测试filter_message
print("\n" + "="*50)
print("测试filter_message:")
filtered, has_tail, tail_part = intelligent_tail_filter.filter_message(content)
print(f"has_tail: {has_tail}")
print(f"过滤后长度: {len(filtered)}")
print(f"过滤后内容结尾:")
print(filtered[-100:] if len(filtered) > 100 else filtered)