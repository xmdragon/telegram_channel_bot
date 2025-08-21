#!/usr/bin/env python3
"""
AI模型预下载工具
解决sentence-transformers每次启动重复下载问题

使用方法：
python3 tools/maintenance/preload_ai_models.py
"""
import sys
import os
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

def preload_models():
    """预下载所有AI模型"""
    print("🚀 开始预下载AI模型...")
    
    try:
        from app.services.model_cache_manager import ModelCacheManager
        
        # 初始化缓存管理器
        cache_manager = ModelCacheManager()
        
        # 预下载默认模型  
        print(f"📥 下载默认模型...")
        
        model = cache_manager.get_model()  # 使用配置中的默认模型
        
        if model:
            # 获取模型配置信息
            config = cache_manager._load_config()
            default_model = config.get('default_model', 'nano')
            model_config = config.get('models', {}).get(default_model, {})
            model_name = model_config.get('name', 'unknown')
            
            print(f"✅ 模型下载完成: {model_name}")
            print(f"📁 缓存位置: {cache_manager.cache_dir}")
            
            # 验证模型工作
            test_text = "这是一个测试文本"
            embeddings = model.encode(test_text)
            print(f"🧪 模型测试成功，向量维度: {len(embeddings)}")
            
            return True
        else:
            print(f"❌ 模型下载失败")
            return False
            
    except Exception as e:
        print(f"❌ 预下载失败: {e}")
        return False

def check_model_status():
    """检查模型缓存状态"""
    print("🔍 检查模型缓存状态...")
    
    try:
        from app.services.model_cache_manager import ModelCacheManager
        
        cache_manager = ModelCacheManager()
        cache_dir = cache_manager.cache_dir
        
        print(f"📁 缓存目录: {cache_dir}")
        
        if cache_dir.exists():
            cached_files = list(cache_dir.rglob("*"))
            if cached_files:
                print(f"📦 发现 {len(cached_files)} 个缓存文件")
                for file in sorted(cached_files)[:10]:  # 显示前10个
                    if file.is_file():
                        size_mb = file.stat().st_size / (1024*1024)
                        print(f"   - {file.name}: {size_mb:.1f}MB")
            else:
                print("📭 缓存目录为空")
        else:
            print("❌ 缓存目录不存在")
            
    except Exception as e:
        print(f"❌ 检查失败: {e}")

def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="AI模型预下载工具")
    parser.add_argument("--check", action="store_true", help="检查模型缓存状态")
    parser.add_argument("--download", action="store_true", help="预下载模型")
    
    args = parser.parse_args()
    
    if args.check:
        check_model_status()
    elif args.download:
        success = preload_models()
        sys.exit(0 if success else 1)
    else:
        # 默认：检查状态，如果没有缓存则下载
        print("🔧 AI模型管理工具")
        print("================")
        
        check_model_status()
        print()
        
        # 询问是否下载
        try:
            response = input("是否立即下载模型？(y/N): ").strip().lower()
            if response in ['y', 'yes', '是']:
                success = preload_models()
                if success:
                    print("\n🎉 模型预下载完成！现在启动系统将使用本地缓存。")
                else:
                    print("\n❌ 预下载失败，请检查网络连接。")
            else:
                print("跳过下载，系统启动时将从网络下载模型。")
        except KeyboardInterrupt:
            print("\n操作取消")

if __name__ == "__main__":
    main()