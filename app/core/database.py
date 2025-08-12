"""
数据库配置和模型
"""
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, Boolean, JSON, Index, func, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from datetime import datetime
from app.utils.timezone import get_current_time
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
    filter_reason = Column(String)  # 过滤/拒绝原因
    
    # 媒体哈希用于检测重复
    media_hash = Column(String, index=True)  # 媒体文件的哈希值
    combined_media_hash = Column(String, index=True)  # 组合媒体的哈希值
    visual_hash = Column(Text)  # 视觉感知哈希（包含phash、dhash等多种哈希）
    
    # OCR相关字段
    ocr_text = Column(Text)  # OCR提取的文字内容（JSON格式存储文字列表）
    qr_codes = Column(Text)  # 二维码信息（JSON格式存储二维码数据）
    ocr_ad_score = Column(Integer, default=0)  # OCR检测的广告分数（0-100）
    ocr_processed = Column(Boolean, default=False)  # 是否已进行OCR处理
    
    created_at = Column(DateTime, default=get_current_time)
    updated_at = Column(DateTime, default=get_current_time, onupdate=get_current_time)
    
    # 添加唯一约束防止重复消息
    __table_args__ = (
        Index('idx_unique_message', 'source_channel', 'message_id', unique=True),
        Index('idx_media_hash', 'media_hash'),
        Index('idx_combined_media_hash', 'combined_media_hash'),
    )

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
    
    created_at = Column(DateTime, default=get_current_time)
    updated_at = Column(DateTime, default=get_current_time, onupdate=get_current_time)


class SystemConfig(Base):
    """系统配置模型"""
    __tablename__ = "system_configs"
    
    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, nullable=False, index=True)
    value = Column(Text)  # JSON格式存储
    description = Column(String)
    config_type = Column(String)  # string/integer/boolean/json/list
    is_active = Column(Boolean, default=True)
    
    created_at = Column(DateTime, default=get_current_time)
    updated_at = Column(DateTime, default=get_current_time, onupdate=get_current_time)


class AITrainingSample(Base):
    """AI训练样本模型"""
    __tablename__ = "ai_training_samples"
    
    id = Column(Integer, primary_key=True, index=True)
    channel_id = Column(String, nullable=False, index=True)  # 频道ID
    channel_name = Column(String)  # 频道名称
    original_message = Column(Text, nullable=False)  # 原始消息
    tail_content = Column(Text, nullable=False)  # 尾部推广内容
    is_applied = Column(Boolean, default=False)  # 是否已应用到模型
    created_by = Column(String, default='manual')  # 创建者
    created_at = Column(DateTime(timezone=True), server_default=func.now())  # 创建时间
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())  # 更新时间


class Admin(Base):
    """管理员模型"""
    __tablename__ = "admins"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    is_super_admin = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    last_login = Column(DateTime)
    created_at = Column(DateTime, default=get_current_time)
    updated_at = Column(DateTime, default=get_current_time, onupdate=get_current_time)
    
    # 关系 - 明确指定foreign_keys避免歧义
    permissions = relationship("AdminPermission", 
                             foreign_keys="[AdminPermission.admin_id]",
                             back_populates="admin", 
                             cascade="all, delete-orphan")
    sessions = relationship("AdminSession", back_populates="admin", cascade="all, delete-orphan")


class Permission(Base):
    """权限模型"""
    __tablename__ = "permissions"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)  # 如: messages.view
    module = Column(String, nullable=False)  # 模块名: messages, config, etc
    action = Column(String, nullable=False)  # 操作: view, edit, delete, etc
    description = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # 关系
    admin_permissions = relationship("AdminPermission", back_populates="permission", cascade="all, delete-orphan")


class AdminPermission(Base):
    """管理员权限关联表"""
    __tablename__ = "admin_permissions"
    
    id = Column(Integer, primary_key=True, index=True)
    admin_id = Column(Integer, ForeignKey("admins.id", ondelete="CASCADE"), nullable=False)
    permission_id = Column(Integer, ForeignKey("permissions.id", ondelete="CASCADE"), nullable=False)
    granted_by = Column(Integer, ForeignKey("admins.id"))  # 授权人
    granted_at = Column(DateTime, default=datetime.utcnow)
    
    # 关系 - 明确指定foreign_keys
    admin = relationship("Admin", foreign_keys=[admin_id], back_populates="permissions", overlaps="granter")
    permission = relationship("Permission", back_populates="admin_permissions")
    granter = relationship("Admin", foreign_keys=[granted_by])  # 授权人关系，单独定义
    
    # 唯一约束
    __table_args__ = (
        Index('idx_unique_admin_permission', 'admin_id', 'permission_id', unique=True),
    )


class AdminSession(Base):
    """管理员会话模型"""
    __tablename__ = "admin_sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    admin_id = Column(Integer, ForeignKey("admins.id", ondelete="CASCADE"), nullable=False)
    token = Column(String, unique=True, nullable=False, index=True)
    ip_address = Column(String)
    user_agent = Column(String)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    last_activity = Column(DateTime, default=datetime.utcnow)
    
    # 关系
    admin = relationship("Admin", back_populates="sessions")

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