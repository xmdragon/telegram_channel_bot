#!/usr/bin/env python3
"""
安全JSON编辑工具
防止手动编辑JSON时产生格式错误
"""
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SafeJSONEditor:
    """安全的JSON编辑器"""
    
    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        if not self.file_path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")
    
    def load(self) -> Dict[str, Any]:
        """安全加载JSON文件"""
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            logger.error(f"JSON格式错误: {e}")
            raise
    
    def save(self, data: Dict[str, Any], backup: bool = True) -> bool:
        """安全保存JSON文件"""
        try:
            # 1. 备份原文件
            if backup:
                backup_path = self.file_path.with_suffix('.json.bak')
                import shutil
                shutil.copy2(self.file_path, backup_path)
                logger.info(f"已备份到: {backup_path}")
            
            # 2. 验证数据可序列化
            test_json = json.dumps(data, ensure_ascii=False, indent=2)
            
            # 3. 写入临时文件
            temp_path = self.file_path.with_suffix('.json.tmp')
            with open(temp_path, 'w', encoding='utf-8') as f:
                f.write(test_json)
            
            # 4. 验证临时文件
            with open(temp_path, 'r', encoding='utf-8') as f:
                json.load(f)
            
            # 5. 原子性替换
            temp_path.replace(self.file_path)
            logger.info(f"✅ 文件已安全保存: {self.file_path}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 保存失败: {e}")
            # 清理临时文件
            if 'temp_path' in locals() and temp_path.exists():
                temp_path.unlink()
            return False
    
    def remove_field(self, field_name: str) -> bool:
        """安全删除字段"""
        try:
            data = self.load()
            if field_name in data:
                del data[field_name]
                logger.info(f"已删除字段: {field_name}")
                return self.save(data)
            else:
                logger.warning(f"字段不存在: {field_name}")
                return True
        except Exception as e:
            logger.error(f"删除字段失败: {e}")
            return False
    
    def remove_nested_field(self, path: str) -> bool:
        """安全删除嵌套字段 (例如: 'channels.channel_1.last_collected_message_id')"""
        try:
            data = self.load()
            
            # 解析路径
            parts = path.split('.')
            current = data
            
            # 遍历到父对象
            for part in parts[:-1]:
                if part in current and isinstance(current[part], dict):
                    current = current[part]
                else:
                    logger.warning(f"路径不存在: {path}")
                    return True
            
            # 删除最后的字段
            final_key = parts[-1]
            if final_key in current:
                del current[final_key]
                logger.info(f"已删除嵌套字段: {path}")
                return self.save(data)
            else:
                logger.warning(f"字段不存在: {path}")
                return True
                
        except Exception as e:
            logger.error(f"删除嵌套字段失败: {e}")
            return False
    
    def batch_remove_field_from_objects(self, parent_key: str, field_name: str) -> bool:
        """批量删除对象中的字段"""
        try:
            data = self.load()
            
            if parent_key not in data:
                logger.warning(f"父键不存在: {parent_key}")
                return True
            
            parent_obj = data[parent_key]
            if not isinstance(parent_obj, dict):
                logger.error(f"父对象不是字典类型: {parent_key}")
                return False
            
            removed_count = 0
            for obj_key, obj_value in parent_obj.items():
                if isinstance(obj_value, dict) and field_name in obj_value:
                    del obj_value[field_name]
                    removed_count += 1
                    logger.debug(f"从 {obj_key} 删除字段: {field_name}")
            
            if removed_count > 0:
                logger.info(f"已从 {removed_count} 个对象中删除字段: {field_name}")
                return self.save(data)
            else:
                logger.info(f"未找到需要删除的字段: {field_name}")
                return True
                
        except Exception as e:
            logger.error(f"批量删除字段失败: {e}")
            return False

def main():
    """主函数"""
    if len(sys.argv) < 3:
        print("用法:")
        print("  python3 safe_json_edit.py <file.json> remove_field <field_name>")
        print("  python3 safe_json_edit.py <file.json> remove_nested <path>")
        print("  python3 safe_json_edit.py <file.json> batch_remove <parent_key> <field_name>")
        sys.exit(1)
    
    file_path = sys.argv[1]
    command = sys.argv[2]
    
    try:
        editor = SafeJSONEditor(file_path)
        
        if command == "remove_field" and len(sys.argv) >= 4:
            field_name = sys.argv[3]
            success = editor.remove_field(field_name)
            
        elif command == "remove_nested" and len(sys.argv) >= 4:
            path = sys.argv[3]
            success = editor.remove_nested_field(path)
            
        elif command == "batch_remove" and len(sys.argv) >= 5:
            parent_key = sys.argv[3]
            field_name = sys.argv[4]
            success = editor.batch_remove_field_from_objects(parent_key, field_name)
            
        else:
            print("无效的命令或参数")
            sys.exit(1)
        
        sys.exit(0 if success else 1)
        
    except Exception as e:
        logger.error(f"操作失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()