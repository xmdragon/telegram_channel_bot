"""
管理员系统管理API
只保留实际使用的功能
"""
from fastapi import APIRouter
import logging

router = APIRouter()
logger = logging.getLogger(__name__)