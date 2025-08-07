"""
关键词管理API
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from typing import List, Optional
from pydantic import BaseModel

from app.core.database import get_db, AdKeyword

router = APIRouter()

class KeywordCreate(BaseModel):
    keyword: str
    keyword_type: str  # text 或 line
    description: Optional[str] = None

class KeywordUpdate(BaseModel):
    keyword: Optional[str] = None
    keyword_type: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None

class KeywordResponse(BaseModel):
    id: int
    keyword: str
    keyword_type: str
    description: Optional[str]
    is_active: bool
    
    class Config:
        from_attributes = True

@router.get("/", response_model=List[KeywordResponse])
async def get_keywords(
    keyword_type: Optional[str] = None,
    is_active: Optional[bool] = None,
    db: AsyncSession = Depends(get_db)
):
    """获取关键词列表"""
    query = select(AdKeyword)
    
    # 添加过滤条件
    if keyword_type:
        query = query.where(AdKeyword.keyword_type == keyword_type)
    if is_active is not None:
        query = query.where(AdKeyword.is_active == is_active)
    
    # 按创建时间倒序排列
    query = query.order_by(AdKeyword.created_at.desc())
    
    result = await db.execute(query)
    keywords = result.scalars().all()
    
    return keywords

@router.post("/", response_model=KeywordResponse)
async def create_keyword(
    keyword_data: KeywordCreate,
    db: AsyncSession = Depends(get_db)
):
    """创建新关键词"""
    # 检查关键词类型是否有效
    if keyword_data.keyword_type not in ["text", "line"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="关键词类型必须是 'text' 或 'line'"
        )
    
    # 检查关键词是否已存在
    existing_query = select(AdKeyword).where(
        AdKeyword.keyword == keyword_data.keyword,
        AdKeyword.keyword_type == keyword_data.keyword_type
    )
    result = await db.execute(existing_query)
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该关键词已存在"
        )
    
    # 创建新关键词
    keyword = AdKeyword(
        keyword=keyword_data.keyword,
        keyword_type=keyword_data.keyword_type,
        description=keyword_data.description
    )
    
    db.add(keyword)
    await db.commit()
    await db.refresh(keyword)
    
    return keyword

@router.put("/{keyword_id}", response_model=KeywordResponse)
async def update_keyword(
    keyword_id: int,
    keyword_data: KeywordUpdate,
    db: AsyncSession = Depends(get_db)
):
    """更新关键词"""
    # 查找关键词
    query = select(AdKeyword).where(AdKeyword.id == keyword_id)
    result = await db.execute(query)
    keyword = result.scalar_one_or_none()
    
    if not keyword:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="关键词不存在"
        )
    
    # 检查关键词类型是否有效
    if keyword_data.keyword_type and keyword_data.keyword_type not in ["text", "line"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="关键词类型必须是 'text' 或 'line'"
        )
    
    # 更新字段
    update_data = keyword_data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(keyword, field, value)
    
    await db.commit()
    await db.refresh(keyword)
    
    return keyword

@router.delete("/{keyword_id}")
async def delete_keyword(
    keyword_id: int,
    db: AsyncSession = Depends(get_db)
):
    """删除关键词"""
    # 查找关键词
    query = select(AdKeyword).where(AdKeyword.id == keyword_id)
    result = await db.execute(query)
    keyword = result.scalar_one_or_none()
    
    if not keyword:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="关键词不存在"
        )
    
    # 删除关键词
    await db.delete(keyword)
    await db.commit()
    
    return {"message": "关键词删除成功"}

@router.post("/batch")
async def batch_create_keywords(
    keywords_data: List[KeywordCreate],
    db: AsyncSession = Depends(get_db)
):
    """批量创建关键词"""
    created_keywords = []
    
    for keyword_data in keywords_data:
        # 检查关键词类型是否有效
        if keyword_data.keyword_type not in ["text", "line"]:
            continue
            
        # 检查关键词是否已存在
        existing_query = select(AdKeyword).where(
            AdKeyword.keyword == keyword_data.keyword,
            AdKeyword.keyword_type == keyword_data.keyword_type
        )
        result = await db.execute(existing_query)
        if result.scalar_one_or_none():
            continue
        
        # 创建新关键词
        keyword = AdKeyword(
            keyword=keyword_data.keyword,
            keyword_type=keyword_data.keyword_type,
            description=keyword_data.description
        )
        
        db.add(keyword)
        created_keywords.append(keyword)
    
    await db.commit()
    
    return {
        "message": f"成功创建 {len(created_keywords)} 个关键词",
        "created_count": len(created_keywords)
    }

@router.delete("/batch")
async def batch_delete_keywords(
    keyword_ids: List[int],
    db: AsyncSession = Depends(get_db)
):
    """批量删除关键词"""
    # 删除指定的关键词
    delete_query = delete(AdKeyword).where(AdKeyword.id.in_(keyword_ids))
    result = await db.execute(delete_query)
    
    await db.commit()
    
    return {
        "message": f"成功删除 {result.rowcount} 个关键词",
        "deleted_count": result.rowcount
    }