#!/usr/bin/env python3
"""
JSON文件验证和修复工具
防止JSON格式错误再次发生
"""
import json
import logging
import sys
from pathlib import Path
from typing import List, Optional

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class JSONValidator:
    """JSON文件验证和修复工具"""
    
    def __init__(self):
        self.data_dir = Path("data/config")
        self.critical_files = [
            "channels.json",
            "system.json", 
            "admins.json"
        ]
    
    def validate_file(self, file_path: Path) -> bool:
        """验证单个JSON文件"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                json.load(f)
            logger.info(f"✅ {file_path.name} 格式正确")
            return True
        except json.JSONDecodeError as e:
            logger.error(f"❌ {file_path.name} 格式错误: {e}")
            return False
        except FileNotFoundError:
            logger.warning(f"⚠️ 文件不存在: {file_path}")
            return False
    
    def fix_trailing_commas(self, file_path: Path) -> bool:
        """修复JSON文件中的trailing comma"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 移除对象内最后一个属性后的逗号
            import re
            fixed_content = re.sub(r',(\s*})', r'\1', content)
            fixed_content = re.sub(r',(\s*])', r'\1', fixed_content)
            
            # 验证修复后的JSON
            data = json.loads(fixed_content)
            
            # 重新格式化并保存
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"✅ {file_path.name} 已修复并重新格式化")
            return True
            
        except Exception as e:
            logger.error(f"❌ 修复 {file_path.name} 失败: {e}")
            return False
    
    def validate_all(self) -> bool:
        """验证所有关键JSON文件"""
        all_valid = True
        
        for filename in self.critical_files:
            file_path = self.data_dir / filename
            if not self.validate_file(file_path):
                all_valid = False
                # 尝试修复
                logger.info(f"🔧 尝试修复 {filename}...")
                if self.fix_trailing_commas(file_path):
                    # 再次验证
                    if self.validate_file(file_path):
                        logger.info(f"✅ {filename} 修复成功")
                    else:
                        logger.error(f"❌ {filename} 修复失败")
                        all_valid = False
        
        return all_valid
    
    def backup_files(self) -> List[Path]:
        """备份所有JSON配置文件"""
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = Path(f"data/backups/json_backup_{timestamp}")
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        backed_up = []
        for filename in self.critical_files:
            source = self.data_dir / filename
            if source.exists():
                target = backup_dir / filename
                import shutil
                shutil.copy2(source, target)
                backed_up.append(target)
                logger.info(f"📦 已备份: {filename} -> {target}")
        
        return backed_up

def main():
    """主函数"""
    validator = JSONValidator()
    
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "validate":
            success = validator.validate_all()
            sys.exit(0 if success else 1)
            
        elif command == "backup":
            backups = validator.backup_files()
            print(f"已备份 {len(backups)} 个文件")
            
        elif command == "fix":
            # 先备份
            validator.backup_files()
            # 然后验证和修复
            success = validator.validate_all()
            sys.exit(0 if success else 1)
            
        else:
            print("用法: python3 json_validator.py [validate|backup|fix]")
            sys.exit(1)
    else:
        # 默认执行验证
        success = validator.validate_all()
        sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()