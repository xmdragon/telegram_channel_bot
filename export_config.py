#!/usr/bin/env python3
"""
配置导出脚本 - 导出系统配置到JSON文件
支持Redis和JSON存储系统
排除敏感的session信息
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from app.services.config_manager import config_manager
from app.storage.json_store import get_json_config_store
from app.storage.redis_store import init_redis_stores, get_redis_store
import sys
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def export_configs():
    """导出所有配置数据"""
    try:
        # 初始化存储系统
        init_redis_stores()
        json_store = get_json_config_store()
        
        export_data = {
            "export_time": datetime.now().isoformat(),
            "version": "2.0",
            "storage_type": "redis_json",
            "system_configs": [],
            "channels": [],
            "training_data": {},
            "filter_patterns": {},
            "permissions": []
        }
        
        # 导出系统配置（从JSON存储）
        print("正在导出系统配置...")
        try:
            all_configs = await config_manager.get_all_configs()
            
            for key, config in all_configs.items():
                # 排除敏感信息
                if key == 'telegram.session':
                    continue
                    
                export_data["system_configs"].append({
                    "key": key,
                    "value": config.get('value'),
                    "description": config.get('description', ''),
                    "config_type": config.get('config_type', 'string'),
                    "is_active": config.get('is_active', True),
                    "created_at": config.get('created_at'),
                    "updated_at": config.get('updated_at')
                })
            
            print(f"  导出了 {len(export_data['system_configs'])} 个系统配置项")
        except Exception as e:
            logger.warning(f"导出系统配置失败: {e}")
        
        # 导出训练数据
        print("正在导出训练数据...")
        training_files = {
            'ad_training_data': 'data/training/ad/json/ad_training_data.json',
            'tail_filter_samples': 'data/training/tail/tail_filter_samples.json',
            'ocr_samples': 'data/training/other/ocr_samples.json',
            'feedback_learning': 'data/training/other/feedback_learning.json',
            'manual_training_data': 'data/training/other/manual_training_data.json'
        }
        
        for data_key, file_path in training_files.items():
            try:
                path = Path(file_path)
                if path.exists():
                    with open(path, 'r', encoding='utf-8') as f:
                        export_data['training_data'][data_key] = json.load(f)
                    print(f"  导出训练数据: {data_key}")
            except Exception as e:
                logger.warning(f"导出训练数据 {data_key} 失败: {e}")
        
        # 导出过滤模式
        print("正在导出过滤模式...")
        filter_files = {
            'ai_filter_patterns': 'data/training/other/ai_filter_patterns.json',
            'learned_patterns': 'data/training/other/learned_patterns.json',
            'separator_patterns': 'data/training/tail/separator_patterns.json'
        }
        
        for pattern_key, file_path in filter_files.items():
            try:
                path = Path(file_path)
                if path.exists():
                    with open(path, 'r', encoding='utf-8') as f:
                        export_data['filter_patterns'][pattern_key] = json.load(f)
                    print(f"  导出过滤模式: {pattern_key}")
            except Exception as e:
                logger.warning(f"导出过滤模式 {pattern_key} 失败: {e}")
        
        # 保存到文件
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"config_export_{timestamp}.json"
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)
        
        print(f"\n✅ 配置已成功导出到: {filename}")
        print(f"总计导出:")
        print(f"  - 系统配置: {len(export_data['system_configs'])} 项")
        print(f"  - 训练数据文件: {len(export_data['training_data'])} 个")
        print(f"  - 过滤模式文件: {len(export_data['filter_patterns'])} 个")
        print(f"  - 权限配置: {len(export_data['permissions'])} 项")
        
        # 统计训练数据总量
        total_training_items = 0
        for data_key, data_content in export_data['training_data'].items():
            if isinstance(data_content, dict):
                if 'samples' in data_content:
                    total_training_items += len(data_content['samples'])
                elif 'training_data' in data_content:
                    total_training_items += len(data_content['training_data'])
                elif isinstance(data_content, list):
                    total_training_items += len(data_content)
        
        print(f"  - 训练样本总数: {total_training_items} 条")
        
        return filename
        
    except Exception as e:
        logger.error(f"导出配置失败: {e}")
        raise

async def main():
    """主函数"""
    try:
        await export_configs()
    except Exception as e:
        print(f"❌ 导出失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())