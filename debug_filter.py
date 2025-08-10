#!/usr/bin/env python3
"""
调试尾部过滤逻辑
"""
import asyncio
import logging
from app.services.ai_filter import ai_filter

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

async def debug_filter():
    """调试过滤逻辑"""
    
    # 加载AI模式
    ai_filter.load_patterns("data/ai_filter_patterns.json")
    
    channel_id = "-1002495270592"  # @yyds518899
    
    # 完整消息内容
    content = """#曝光山东威海人  #杨庆磊

事件：偷公司客户
姓名：杨庆磊
外号：张良
护照号：EJI567I57
 国内脏款支付宝：13465590102
山东威海人
   
此子快40岁的人了，在国内娶不到老婆，因他父亲癌症去世，他妈妈在日本打杂，所以他在公司不允许搞小菲的情况下在公司楼梯间和小菲做爱，搞了一个生了四个孩子的小菲(目前这个小菲又被他搞大肚子快生了)

自打进公司开始就到处施以小恩试图拉拢人心，没事的时候喜欢看三国演义，擅长离间计，攻心计，提前半年开始预谋如何偷公司资源，如果早生几十年绝对的汉奸。

在他申请离职的时候寄出工作手机，但他却说手机少了2部，在他的工作电脑的谷歌翻译器里找到了他和他菲律宾女人的聊天翻译记录。

菲律宾同行见到此人慎用



👍亚太新闻频道👍 https://t.me/yyds518899

🔞亚太色情吃瓜 🔞 ：https://t.me/saisaissssss168168

便民服务中文包 https://t.me/setlanguage/classic-zh-cn"""

    logger.info("=" * 60)
    logger.info("🔍 调试尾部过滤")
    logger.info("=" * 60)
    
    # 手动执行过滤逻辑
    lines = content.split('\n')
    logger.info(f"消息总行数: {len(lines)}")
    
    # 逐行测试
    logger.info("\n逐行测试相似度:")
    for i in range(len(lines) - 1, max(0, len(lines) - 10), -1):
        test_tail = '\n'.join(lines[i:])
        is_tail, score = ai_filter.is_channel_tail(channel_id, test_tail)
        logger.info(f"  从第{i}行到结尾 (共{len(lines)-i}行): 相似度={score:.3f}, 匹配={'✅' if is_tail else '❌'}")
        if is_tail and score > 0.8:
            logger.info(f"    -> 应该从第{i}行开始过滤")
            break
    
    # 测试filter_channel_tail函数
    logger.info("\n测试filter_channel_tail函数:")
    filtered = ai_filter.filter_channel_tail(channel_id, content)
    logger.info(f"  原始长度: {len(content)}")
    logger.info(f"  过滤后长度: {len(filtered)}")
    logger.info(f"  删除字符数: {len(content) - len(filtered)}")
    
    if len(filtered) < len(content):
        logger.info(f"\n✅ 过滤成功!")
        logger.info(f"被删除的内容:")
        removed = content[len(filtered):]
        logger.info("-" * 40)
        logger.info(removed)
        logger.info("-" * 40)
    else:
        logger.info(f"\n❌ 过滤失败!")
        
        # 检查阈值设置
        pattern = ai_filter.channel_patterns.get(channel_id)
        if pattern:
            logger.info(f"\n当前模式设置:")
            logger.info(f"  阈值: {pattern['threshold']}")
            logger.info(f"  样本数: {pattern.get('sample_count', 0)}")
            
            # 测试不同的尾部
            test_tails = [
                "👍亚太新闻频道👍 https://t.me/yyds518899",
                """👍亚太新闻频道👍 https://t.me/yyds518899

🔞亚太色情吃瓜 🔞 ：https://t.me/saisaissssss168168""",
                """👍亚太新闻频道👍 https://t.me/yyds518899

🔞亚太色情吃瓜 🔞 ：https://t.me/saisaissssss168168

便民服务中文包 https://t.me/setlanguage/classic-zh-cn"""
            ]
            
            logger.info(f"\n测试不同长度的尾部:")
            for tail in test_tails:
                is_tail, score = ai_filter.is_channel_tail(channel_id, tail)
                logger.info(f"  {len(tail)}字符: 相似度={score:.3f} {'✅' if is_tail else '❌'}")

asyncio.run(debug_filter())