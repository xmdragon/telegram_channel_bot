#!/usr/bin/env python3
"""
彻底修复visual_hash存储格式问题
将所有Python dict格式的visual_hash转换为JSON格式
"""
import redis
import json
import ast
import logging

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def fix_visual_hash_storage():
    """彻底修复visual_hash存储格式"""
    try:
        # 连接Redis
        r = redis.from_url("redis://localhost:6379", decode_responses=True)
        
        # 扫描所有消息key
        message_keys = []
        for key in r.scan_iter(match="message:-*:*"):
                message_keys.append(key)
        
        logger.info(f"找到 {len(message_keys)} 个消息")
        
        fixed_count = 0
        error_count = 0
        
        for key in message_keys:
            try:
                # 获取visual_hash字段
                visual_hash = r.hget(key, 'visual_hash')
                
                if not visual_hash:
                    continue
                
                # 检查是否已经是JSON格式
                try:
                    json.loads(visual_hash)
                    # 已经是JSON格式，跳过
                    continue
                except json.JSONDecodeError:
                    pass
                
                # 尝试解析Python dict格式
                try:
                    # 使用ast.literal_eval安全解析Python字面量
                    parsed_data = ast.literal_eval(visual_hash)
                    
                    # 转换为JSON格式
                    json_visual_hash = json.dumps(parsed_data, ensure_ascii=False)
                    
                    # 更新Redis中的数据
                    r.hset(key, 'visual_hash', json_visual_hash)
                    
                    logger.info(f"修复 {key}: Python dict -> JSON")
                    fixed_count += 1
                    
                except (ValueError, SyntaxError) as e:
                    logger.warning(f"无法解析 {key} 的visual_hash: {e}")
                    logger.warning(f"数据内容: {visual_hash[:100]}...")
                    error_count += 1
                    
            except Exception as e:
                logger.error(f"处理 {key} 时出错: {e}")
                error_count += 1
        
        logger.info(f"修复完成: 成功修复 {fixed_count} 个, 错误 {error_count} 个")
        return fixed_count, error_count
        
    except Exception as e:
        logger.error(f"修复失败: {e}")
        return 0, 1

def test_visual_hash_parsing():
    """测试visual_hash解析"""
    try:
        r = redis.from_url("redis://localhost:6379", decode_responses=True)
        
        # 找一个有visual_hash的消息测试
        for key in r.scan_iter(match="message:-*:*"):
                visual_hash = r.hget(key, 'visual_hash')
                if visual_hash:
                    logger.info(f"测试消息: {key}")
                    logger.info(f"visual_hash类型: {type(visual_hash)}")
                    logger.info(f"visual_hash内容: {visual_hash[:100]}...")
                    
                    try:
                        parsed = json.loads(visual_hash)
                        logger.info("✅ JSON解析成功")
                        logger.info(f"解析结果类型: {type(parsed)}")
                        return key, True
                    except json.JSONDecodeError as e:
                        logger.error(f"❌ JSON解析失败: {e}")
                        return key, False
        
        logger.warning("没有找到包含visual_hash的消息")
        return None, None
        
    except Exception as e:
        logger.error(f"测试失败: {e}")
        return None, False

if __name__ == "__main__":
    print("🔧 开始修复visual_hash存储格式问题...")
    
    # 先测试当前状态
    print("\n📊 测试当前visual_hash解析状态...")
    test_key, test_result = test_visual_hash_parsing()
    
    if test_result is False:
        print("❌ 发现格式问题，开始修复...")
        # 执行修复
        fixed, errors = fix_visual_hash_storage()
        print(f"✅ 修复完成: 成功 {fixed} 个, 错误 {errors} 个")
        
        # 再次测试
        print("\n🔍 验证修复结果...")
        test_key, test_result = test_visual_hash_parsing()
        
        if test_result:
            print("✅ 修复成功！所有visual_hash现在都是JSON格式")
        else:
            print("❌ 修复后仍有问题")
    elif test_result is True:
        print("✅ visual_hash格式正常，无需修复")
    else:
        print("⚠️  没有找到visual_hash数据进行测试")