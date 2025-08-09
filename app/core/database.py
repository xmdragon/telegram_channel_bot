"""
数据库配置和模型
"""
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, Boolean, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from datetime import datetime
import asyncio

from .config import settings

# 创建异步数据库引擎 - 仅支持PostgreSQL
engine = create_async_engine(settings.DATABASE_URL, echo=False)

AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

Base = declarative_base()

class Message(Base):
    """消息模型"""
    __tablename__ = "messages"
    
    id = Column(Integer, primary_key=True, index=True)
    source_channel = Column(String, nullable=False)  # 源频道
    message_id = Column(Integer, nullable=False)  # 原消息ID
    content = Column(Text)  # 消息内容
    media_type = Column(String)  # 媒体类型
    media_url = Column(String)  # 媒体URL
    
    # 消息组合相关
    grouped_id = Column(String)  # Telegram的grouped_id，用于标识组合消息
    is_combined = Column(Boolean, default=False)  # 是否为组合消息的主消息
    combined_messages = Column(JSON)  # 存储组合消息的所有内容和媒体
    media_group = Column(JSON)  # 存储媒体组信息
    
    # 审核相关
    review_message_id = Column(Integer)  # 审核群消息ID
    status = Column(String, default="pending")  # pending/approved/rejected/auto_forwarded
    reviewed_by = Column(String)  # 审核人
    review_time = Column(DateTime)  # 审核时间
    
    # 转发相关
    target_message_id = Column(Integer)  # 目标频道消息ID
    forwarded_time = Column(DateTime)  # 转发时间
    
    # 过滤和处理
    is_ad = Column(Boolean, default=False)  # 是否为广告
    filtered_content = Column(Text)  # 过滤后内容
    
    # 媒体哈希用于检测重复
    media_hash = Column(String, index=True)  # 媒体文件的哈希值
    combined_media_hash = Column(String, index=True)  # 组合媒体的哈希值
    visual_hash = Column(Text)  # 视觉感知哈希（包含phash、dhash等多种哈希）
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Channel(Base):
    """频道配置模型"""
    __tablename__ = "channels"
    
    id = Column(Integer, primary_key=True, index=True)
    channel_id = Column(String, unique=True, nullable=True)  # 允许为空，等待Telethon获取
    channel_name = Column(String, unique=True, nullable=False)  # 频道名称唯一
    channel_title = Column(String)  # 频道标题
    channel_type = Column(String)  # source/review/target
    is_active = Column(Boolean, default=True)
    config = Column(JSON)  # 频道特定配置
    description = Column(String)  # 频道描述
    last_collected_message_id = Column(Integer, nullable=True)  # 最后采集的消息ID
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class FilterRule(Base):
    """过滤规则模型"""
    __tablename__ = "filter_rules"
    
    id = Column(Integer, primary_key=True, index=True)
    rule_type = Column(String)  # keyword/regex/ml
    pattern = Column(String)
    action = Column(String)  # block/flag/replace
    is_active = Column(Boolean, default=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)

class SystemConfig(Base):
    """系统配置模型"""
    __tablename__ = "system_configs"
    
    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, nullable=False, index=True)
    value = Column(Text)  # JSON格式存储
    description = Column(String)
    config_type = Column(String)  # string/integer/boolean/json/list
    is_active = Column(Boolean, default=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class AdKeyword(Base):
    """广告关键词模型"""
    __tablename__ = "ad_keywords"
    
    id = Column(Integer, primary_key=True, index=True)
    keyword = Column(String, nullable=False, index=True)  # 关键词
    keyword_type = Column(String, nullable=False)  # text(文中关键词) 或 line(行过滤关键词)
    description = Column(String)  # 关键词描述
    is_active = Column(Boolean, default=True)  # 是否启用
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

async def init_db():
    """初始化数据库"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_db():
    """获取数据库会话"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()