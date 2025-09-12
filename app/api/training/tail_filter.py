"""
尾部过滤管理模块 - 尾部过滤样本的CRUD和去重功能
"""
from fastapi import APIRouter, HTTPException
from datetime import datetime
from typing import List, Dict, Any
import logging
import hashlib
import re

from .base import (
    TailFilterSample, load_tail_filter_samples, save_tail_filter_samples,
    generate_sample_id, validate_sample_data, calculate_statistics,
    handle_api_error, validate_pagination_params,
    paginate_data
)
from app.core.route_config import ROUTES

logger = logging.getLogger(__name__)
router = APIRouter(tags=["training-tail-filter"])

def extract_promotional_content(text: str) -> str:
    """
    从尾部文本中提取推广内容
    专门针对尾部推广模式进行提取
    """
    if not text:
        return ""
    
    # 推广关键词模式
    promo_patterns = [
        '📣', '订阅', '频道', '@', '💬', '商务', '对接', '联系', '😍', '投稿', '澄清', '爆料',
        '🔗', 't.me', 'https://', '☎️', '免费', '♾', '🔔', '👌', '➡️', '点击', '加入',
        '———', '——', '━━', '═══', '▬▬'
    ]
    
    lines = text.split('\n')
    promo_lines = []
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # 检查是否包含推广关键词
        if any(pattern in line for pattern in promo_patterns):
            promo_lines.append(line)
        # 或者很短且包含特殊字符（可能是分隔符）
        elif len(line) < 20 and any(char in line for char in ['━', '═', '─', '▬', '-', '=', '*']):
            promo_lines.append(line)
    
    return '\n'.join(promo_lines)

def is_separator_line(text: str) -> bool:
    """
    检查是否为分隔符行
    """
    if not text:
        return False
    
    # 移除空格后检查
    clean_text = text.replace(' ', '')
    
    # 检查是否全部是分隔符字符
    separator_chars = set('—━═─▬-=*~_|+#')
    text_chars = set(clean_text)
    
    # 如果全部是分隔符字符，或者长度小于等于20且主要是分隔符
    if text_chars.issubset(separator_chars):
        return True
    
    # 检查是否是重复的分隔符模式
    if len(clean_text) >= 3:
        # 检查是否是重复字符（如"———"、"==="等）
        if len(set(clean_text)) <= 2 and any(char in separator_chars for char in clean_text):
            return True
    
    return False

def remove_emojis(text: str) -> str:
    """
    移除文本中的emoji，保留文字内容
    """
    if not text:
        return ""
    
    # 简化但有效的emoji移除正则表达式
    emoji_pattern = re.compile(
        r'[\U0001F600-\U0001F64F]|'  # 表情符号
        r'[\U0001F300-\U0001F5FF]|'  # 杂项符号和象形文字  
        r'[\U0001F680-\U0001F6FF]|'  # 交通和地图符号
        r'[\U0001F1E0-\U0001F1FF]|'  # 国旗
        r'[\U0001F900-\U0001F9FF]|'  # 补充符号和象形文字
        r'[\U00002600-\U000027BF]|'  # 杂项符号和装饰符号
        r'[\U0000FE00-\U0000FE0F]'   # 变化选择器
    )
    
    # 移除emoji
    text_only = emoji_pattern.sub(' ', text)
    
    # 清理多余空格
    text_only = re.sub(r'\s+', ' ', text_only).strip()
    
    return text_only

def extract_regex_rules_from_tail(tail_part: str) -> List[str]:
    """
    从尾部内容中提取正则表达式规则
    按行分析，专注文字内容，忽略emoji变化和分隔符
    
    Args:
        tail_part: 尾部推广内容
        
    Returns:
        正则表达式规则列表
    """
    if not tail_part or not tail_part.strip():
        return []
    
    lines = tail_part.split('\n')
    rules = []
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # 检查是否为纯分隔符行
        if is_separator_line(line):
            continue
        
        # 移除emoji，专注文字内容  
        text_only = remove_emojis(line)
        
        if not text_only:
            continue
        
        # 再次检查清理后是否变成分隔符
        if is_separator_line(text_only):
            continue
        
        # 生成正则表达式规则
        rule = generate_line_regex(text_only)
        if rule and len(rule.strip()) > 3:  # 避免过短的规则
            rules.append(rule)
    
    return rules

def generate_line_regex(text: str) -> str:
    """
    为单行文本生成正则表达式
    
    Args:
        text: 单行文本（已移除emoji）
        
    Returns:
        正则表达式字符串
    """
    if not text:
        return ""
    
    # 检查是否包含Telegram链接
    if 't.me/' in text:
        # t.me/+abc123 → t\.me/\+[a-zA-Z0-9_]+
        # t.me/channel → t\.me/[a-zA-Z0-9_]+
        # 先转义特殊字符
        escaped = re.escape(text)
        # 然后替换Telegram链接部分为通配模式
        if '\+' in escaped:  # 注意：re.escape后+变成\+
            pattern = re.sub(r't\\\.me/\\\+[a-zA-Z0-9_]+', r't\\.me/\\+[a-zA-Z0-9_]+', escaped)
        else:
            pattern = re.sub(r't\\\.me/[a-zA-Z0-9_]+', r't\\.me/[a-zA-Z0-9_]+', escaped)
        # 处理空格
        pattern = re.sub(r'\\\ +', r'\\s*', pattern)
        return pattern
    
    # 检查是否包含@用户名
    elif '@' in text:
        # 投稿澄清爆料： @tx188 → 投稿澄清爆料：\s*@\w+
        escaped = re.escape(text)
        # 替换@用户名为通配模式
        pattern = re.sub(r'@[a-zA-Z0-9_]+', r'@\\w+', escaped)
        # 处理空格
        pattern = re.sub(r'\\\ +', r'\\s*', pattern)
        return pattern
    
    # 检查是否包含https链接
    elif 'https://' in text or 'http://' in text:
        # https://example.com → https?://[^\s]+
        escaped = re.escape(text)
        # 替换URL为通配模式
        pattern = re.sub(r'https?://[^\\\s]+', r'https?://[^\\s]+', escaped)
        # 处理空格
        pattern = re.sub(r'\\\ +', r'\\s*', pattern)
        return pattern
    
    # 纯文字内容，直接转义特殊字符
    else:
        return escape_regex_special_chars(text)

def escape_regex_special_chars(text: str) -> str:
    """
    转义正则表达式特殊字符
    注意：只需要单层转义，JSON会自动处理转义
    
    Args:
        text: 原始文本
        
    Returns:
        转义后的文本
    """
    # 使用re.escape自动转义所有特殊字符
    escaped = re.escape(text)
    
    # 处理空格变化（可能有多个空格或制表符）
    escaped = re.sub(r'\\\s+', r'\\s*', escaped)
    
    return escaped

def calculate_text_similarity(text1: str, text2: str) -> float:
    """
    计算两个文本的相似度
    专门针对尾部推广内容优化的相似度算法
    """
    if not text1 or not text2:
        return 0.0
    
    if text1 == text2:
        return 1.0
    
    # 提取推广内容进行比较
    promo1 = extract_promotional_content(text1)
    promo2 = extract_promotional_content(text2)
    
    # 如果提取到推广内容，优先比较推广内容
    if promo1 and promo2:
        if promo1 == promo2:
            return 1.0
        # 对推广内容计算相似度
        text1, text2 = promo1, promo2
    
    # 生成字符级n-gram
    def get_char_ngrams(text: str, n: int = 3) -> set:
        text = text.replace(' ', '').replace('\n', '')
        if len(text) < n:
            return {text}
        return {text[i:i+n] for i in range(len(text) - n + 1)}
    
    # 生成词级特征
    def get_word_features(text: str) -> set:
        import re
        # 提取中文词、英文词、@用户名、链接等
        words = set()
        # 中文词（2-3字词组）
        chinese_chars = re.findall(r'[\u4e00-\u9fff]+', text)
        for word in chinese_chars:
            if len(word) >= 2:
                for i in range(len(word) - 1):
                    words.add(word[i:i+2])
        
        # @用户名、链接、特殊词汇
        special_tokens = re.findall(r'@\w+|https?://\S+|t\.me/\S+|[📣💬😍🔗☎️♾🔔👌➡️📱]+', text)
        words.update(special_tokens)
        
        return words
    
    # 组合字符n-gram和词级特征
    features1 = get_char_ngrams(text1) | get_word_features(text1)
    features2 = get_char_ngrams(text2) | get_word_features(text2)
    
    if not features1 or not features2:
        return 0.0
    
    # Jaccard相似度
    intersection = len(features1 & features2)
    union = len(features1 | features2)
    
    return intersection / union if union > 0 else 0.0

@router.get(ROUTES.training.tail_filter_statistics)
async def get_tail_filter_statistics():
    """获取尾部过滤统计信息"""
    try:
        samples = load_tail_filter_samples()
        
        # 计算统计数据
        total_samples = len(samples)
        valid_samples = len([s for s in samples if s.get('tail_part')])
        samples_with_separator = len([s for s in samples if s.get('tail_part', '') and any(
            char in s.get('tail_part', '') for char in ['━', '═', '─', '▬', '-', '=', '*', '🔔', '🔗', '☎️', '♾', '😀', '⚡', '📱', '📣', '👌']
        )])
        
        # 计算今日新增
        today = datetime.now().date()
        today_added = 0
        for sample in samples:
            created_at = sample.get('created_at', '')
            if created_at:
                try:
                    sample_date = datetime.fromisoformat(created_at).date()
                    if sample_date == today:
                        today_added += 1
                except:
                    pass
        
        return {
            "success": True,
            "total_samples": total_samples,
            "valid_samples": valid_samples,
            "samples_with_separator": samples_with_separator,
            "today_added": today_added
        }
    except Exception as e:
        logger.error(f"获取尾部过滤统计失败: {e}")
        return {
            "success": False,
            "total_samples": 0,
            "valid_samples": 0,
            "samples_with_separator": 0,
            "today_added": 0
        }

@router.get(ROUTES.training.tail_filter_history)
async def get_tail_filter_history(limit: int = 20):
    """获取尾部过滤历史记录"""
    try:
        from .base import load_training_data  # 引用基础训练数据
        samples = load_training_data()
        
        # 获取最近N条记录，按创建时间排序
        sorted_samples = sorted(
            samples, 
            key=lambda x: x.get('created_at', ''), 
            reverse=True
        )[:limit]
        
        history = []
        for sample in sorted_samples:
            history.append({
                "id": sample.get('id', ''),
                "channel_id": sample.get('channel_id', ''),
                "channel_name": sample.get('channel_name', '未知频道'),
                "tail_length": len(sample.get('tail_content', '')),
                "created_at": sample.get('created_at')
            })
        
        return {"success": True, "history": history}
    except Exception as e:
        logger.error(f"获取尾部过滤历史失败: {e}")
        return {"success": False, "history": []}

@router.get(ROUTES.training.tail_filter_samples)
async def get_tail_filter_samples(page: int = 1, page_size: int = 20):
    """获取尾部过滤训练样本列表"""
    try:
        samples = load_tail_filter_samples()
        
        # 格式化样本数据以匹配前端期望的格式
        formatted_samples = []
        for sample in samples:
            # 原始数据格式兼容处理
            content = sample.get('content', sample.get('original_message', ''))
            tail_content = sample.get('tail_part', '')
            
            # 统一使用tail_part字段
            formatted_samples.append({
                "id": sample.get('id', ''),
                "content": content,
                "tail_part": tail_content,  # 统一使用tail_part字段
                "separator": sample.get('separator', ''),
                "normal_part": sample.get('normal_part', ''),
                "created_at": sample.get('created_at', ''),
                "channel_id": sample.get('channel_id', 'unknown'),
                "channel_name": sample.get('channel_name', '历史数据'),
                "is_applied": sample.get('is_applied', True)  # 历史数据默认已应用
            })
        
        # 应用分页
        page, page_size = validate_pagination_params(page, page_size)
        paginated_result = paginate_data(formatted_samples, page, page_size)
        
        return {
            "success": True,
            "samples": paginated_result['items'],
            "total": paginated_result['total'],
            "page": paginated_result['page'],
            "page_size": paginated_result['page_size'],
            "total_pages": paginated_result['total_pages']
        }
    except Exception as e:
        logger.error(f"获取尾部过滤训练样本失败: {e}")
        return {
            "success": False,
            "samples": [],
            "total": 0,
            "page": page,
            "page_size": page_size,
            "total_pages": 0
        }

@router.post(ROUTES.training.tail_filter_samples)
async def add_tail_filter_sample(request: dict):
    """添加尾部过滤训练样本"""
    try:
        # 提取参数
        content = request.get("content", "")
        separator = request.get("separator", "")
        normal_part = request.get("normalPart", "")
        tail_part = request.get("tailPart", "")
        message_id = request.get("message_id")
        
        logger.info(f"收到尾部过滤训练样本: 内容长度={len(content)}, 尾部长度={len(tail_part)}")
        
        if not content or not tail_part:
            return {"success": False, "message": "内容和尾部内容不能为空"}
        
        samples = load_tail_filter_samples()
        
        # 生成新的ID
        new_id = max([s.get('id', 0) for s in samples], default=0) + 1
        
        # 生成正则规则
        regex_rules = extract_regex_rules_from_tail(tail_part)
        
        # 创建新样本（只保留核心字段）
        new_sample = {
            "id": new_id,
            "tail_part": tail_part,
            "rules": regex_rules,
            "created_at": datetime.now().isoformat()
        }
        
        # 计算哈希用于重复检查（但不保存到样本）
        content_hash = hashlib.md5(content.encode()).hexdigest()
        
        # 检查重复
        existing_sample = None
        for sample in samples:
            # 兼容旧格式的哈希检查
            existing_hash = sample.get('content_hash')
            if not existing_hash and sample.get('content'):
                # 为历史数据生成哈希
                existing_hash = hashlib.md5(sample.get('content', '').encode()).hexdigest()
            # 或者直接比较tail_part
            if existing_hash == content_hash or sample.get('tail_part') == tail_part:
                existing_sample = sample
                break
        
        if existing_sample:
            # 样本已存在，但仍然返回成功，只是不添加重复样本
            logger.info(f"尾部过滤训练样本已存在，跳过添加: {existing_sample.get('id')}")
            sample_id = existing_sample.get('id')
        else:
            # 添加新样本
            samples.append(new_sample)
            if not save_tail_filter_samples(samples):
                raise HTTPException(status_code=500, detail="保存样本失败")
            sample_id = new_id
            logger.info(f"新尾部过滤训练样本已保存: {sample_id}，生成了 {len(regex_rules)} 个正则规则")
        
        # 如果有message_id，直接使用用户编辑的内容更新filtered_content
        if message_id and normal_part:
            try:
                # 使用Redis管理器 - Linus式简洁
                from app.storage.redis_manager import redis_manager
                if not redis_manager.is_healthy():
                    logger.error("Redis不可用，无法更新消息")
                    return {"success": True, "message": "训练样本已提交，但Redis连接失败，请手动刷新页面", "id": sample_id}
                
                # 解析消息ID
                if ':' in message_id:
                    channel_id, msg_id = message_id.split(':', 1)
                    
                    # 直接更新filtered_content为用户编辑的内容
                    update_data = {"filtered_content": normal_part}
                    success = redis_manager.update_message(channel_id, int(msg_id), update_data)
                    
                    if success:
                        logger.info(f"成功更新消息的filtered_content: {message_id}")
                        if existing_sample:
                            return {"success": True, "message": "训练样本已存在，消息内容已更新", "id": sample_id}
                        else:
                            return {"success": True, "message": "训练样本已提交并自动应用到消息", "id": sample_id}
                    else:
                        logger.warning(f"更新消息内容失败: {message_id}")
                        if existing_sample:
                            return {"success": True, "message": "训练样本已存在，但内容更新失败，请手动刷新页面", "id": sample_id}
                        else:
                            return {"success": True, "message": "训练样本已提交，但内容更新失败，请手动刷新页面", "id": sample_id}
            except Exception as update_error:
                logger.error(f"更新消息内容失败: {update_error}")
                if existing_sample:
                    return {"success": True, "message": "训练样本已存在，但内容更新失败，请手动刷新页面", "id": sample_id}
                else:
                    return {"success": True, "message": "训练样本已提交，但内容更新失败，请手动刷新页面", "id": sample_id}
        
        # 返回成功，提供适当的消息
        if existing_sample:
            logger.info(f"尾部过滤训练样本已存在: ID={sample_id}")
            return {"success": True, "message": "训练样本已存在，数据保存成功", "id": sample_id}
        else:
            logger.info(f"成功添加尾部过滤训练样本: ID={sample_id}")
            return {"success": True, "message": "训练样本已提交", "id": sample_id}
            
    except Exception as e:
        raise handle_api_error(e, "添加尾部过滤训练样本")

@router.get(ROUTES.training.tail_filter_samples_by_id)
async def get_tail_filter_sample_by_id(sample_id: int):
    """获取单个尾部过滤训练样本"""
    try:
        samples = load_tail_filter_samples()
        
        # 查找指定ID的样本
        for sample in samples:
            if sample.get('id') == sample_id:
                return {
                    "success": True,
                    "sample": {
                        "id": sample.get('id'),
                        "tail_part": sample.get('tail_part', ''),
                        "original_message": sample.get('content', ''),  # 支持旧字段名
                        "created_at": sample.get('created_at', ''),
                        "updated_at": sample.get('updated_at', ''),
                        "channel_id": sample.get('channel_id', ''),
                        "channel_name": sample.get('channel_name', '')
                    }
                }
        
        # 样本不存在
        raise HTTPException(status_code=404, detail="训练样本不存在")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取尾部过滤训练样本失败: {e}")
        raise HTTPException(status_code=500, detail="获取训练样本失败")

@router.put(ROUTES.training.tail_filter_samples_by_id)
async def update_tail_filter_sample(sample_id: int, request: dict):
    """更新尾部过滤训练样本"""
    try:
        # 验证参数 - 支持新旧字段名
        tail_content = request.get('tail_content') or request.get('tail_part', '')
        tail_content = tail_content.strip()
        
        if not tail_content:
            return {"success": False, "message": "尾部内容不能为空"}
        
        # 加载样本
        samples = load_tail_filter_samples()
        
        # 查找样本并更新
        sample_found = False
        for sample in samples:
            if sample.get('id') == sample_id:
                # 更新样本数据 - 直接存储到tail_part
                sample['tail_part'] = tail_content
                sample['updated_at'] = datetime.now().isoformat()
                # 清除旧的tail_content字段（如果存在）
                if 'tail_content' in sample:
                    del sample['tail_content']
                sample_found = True
                break
        
        if not sample_found:
            return {"success": False, "message": "样本不存在"}
        
        # 保存更新后的数据
        if not save_tail_filter_samples(samples):
            raise HTTPException(status_code=500, detail="保存数据失败")
        
        
        logger.info(f"成功更新尾部过滤样本: {sample_id}")
        return {"success": True, "message": "样本已更新"}
        
    except Exception as e:
        logger.error(f"更新尾部过滤样本失败: {e}")
        return {"success": False, "message": str(e)}

@router.delete(ROUTES.training.tail_filter_samples_by_id)
async def delete_tail_filter_sample(sample_id: int):
    """删除尾部过滤训练样本"""
    try:
        samples = load_tail_filter_samples()
        
        # 查找并删除样本
        original_count = len(samples)
        sample_to_delete = None
        for sample in samples:
            if sample.get('id') == sample_id:
                sample_to_delete = sample
                break
        
        if not sample_to_delete:
            return {"success": False, "message": "训练样本不存在"}
        
        samples = [s for s in samples if s.get('id') != sample_id]
        
        # 保存更新后的数据
        if not save_tail_filter_samples(samples):
            raise HTTPException(status_code=500, detail="保存数据失败")
        
        
        return {"success": True, "message": "删除成功"}
    except Exception as e:
        raise handle_api_error(e, "删除尾部过滤训练样本")

@router.post(ROUTES.training.tail_filter_rebuild_vectors)
async def rebuild_tail_vectors():
    """重建正则规则索引（替代ONNX向量）"""
    try:
        logger.info("开始重建正则规则索引...")
        
        samples = load_tail_filter_samples()
        updated_count = 0
        
        # 为缺少rules字段的样本生成正则规则
        for sample in samples:
            if 'rules' not in sample or not sample.get('rules'):
                tail_part = sample.get('tail_part', '')
                if tail_part:
                    sample['rules'] = extract_regex_rules_from_tail(tail_part)
                    updated_count += 1
        
        # 保存更新后的数据
        if updated_count > 0:
            save_tail_filter_samples(samples)
        
        result = {
            "success": True,
            "message": "正则规则重建成功",
            "sample_count": len(samples),
            "updated_count": updated_count,
            "model_type": "Regex_Rules"
        }
        
        logger.info(f"正则规则重建成功: {result}")
        return result
        
    except Exception as e:
        logger.error(f"重建正则规则索引时发生错误: {e}")
        return {
            "success": False,
            "message": f"重建失败: {str(e)}",
            "sample_count": 0,
            "updated_count": 0,
            "model_type": "Error"
        }