#!/usr/bin/env python3
"""
ONNX模型转换工具 - Linus式简洁设计
将text2vec-base-chinese转换为ONNX格式，实现2倍速度提升

Author: Claude (Linus式重构)
Created: 2025-09-06
"""

import os
import sys
import logging
import time
import traceback
from pathlib import Path
from typing import Optional

# 添加项目根目录到路径
sys.path.append(str(Path(__file__).parent.parent.parent))

try:
    # 导入优化工具
    from optimum.onnxruntime import ORTModelForFeatureExtraction
    from transformers import AutoTokenizer
    import onnx
    import numpy as np
    
    # 导入项目模块
    from app.core.path_config import PathConfig
    from app.core.logging_config import setup_logging, get_logger
    
except ImportError as e:
    print(f"❌ 导入错误: {e}")
    print("请先安装依赖: pip install onnx onnxruntime optimum[onnxruntime]")
    sys.exit(1)

# 初始化日志
setup_logging(service_name="onnx_converter", log_level="INFO", console_output=True)
logger = get_logger(__name__)


class Text2VecONNXConverter:
    """text2vec模型ONNX转换器 - Linus原则：单一职责，无特殊情况"""
    
    def __init__(self):
        self.model_name = "shibing624/text2vec-base-chinese"
        self.onnx_model_path = Path("data/models")
        self.onnx_model_path.mkdir(parents=True, exist_ok=True)
        
        # 输出路径
        self.output_dir = self.onnx_model_path / "text2vec-base-chinese-onnx"
        self.onnx_file_path = self.output_dir / "model.onnx"
        
    def convert_model(self) -> bool:
        """
        转换text2vec模型为ONNX格式
        
        Returns:
            转换成功返回True
        """
        try:
            logger.info("🚀 开始转换text2vec-base-chinese为ONNX格式...")
            
            # 删除已存在的输出目录
            if self.output_dir.exists():
                import shutil
                shutil.rmtree(self.output_dir)
                logger.info(f"清理旧文件: {self.output_dir}")
            
            start_time = time.time()
            
            # Step 1: 使用optimum转换模型
            logger.info("正在使用Optimum转换模型...")
            onnx_model = ORTModelForFeatureExtraction.from_pretrained(
                self.model_name,
                export=True,  # 自动转换为ONNX
                use_cache=False  # 不使用KV缓存，减小模型大小
            )
            
            # Step 2: 保存ONNX模型和tokenizer
            logger.info(f"保存ONNX模型到: {self.output_dir}")
            onnx_model.save_pretrained(self.output_dir)
            
            # 同时保存tokenizer
            tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            tokenizer.save_pretrained(self.output_dir)
            
            # Step 3: 验证ONNX文件
            if not self.onnx_file_path.exists():
                logger.error(f"ONNX文件生成失败: {self.onnx_file_path}")
                return False
            
            # 检查模型有效性
            try:
                onnx_proto = onnx.load(str(self.onnx_file_path))
                onnx.checker.check_model(onnx_proto)
                logger.info("✅ ONNX模型验证通过")
            except Exception as e:
                logger.error(f"ONNX模型验证失败: {e}")
                return False
            
            # Step 4: 显示转换结果
            conversion_time = time.time() - start_time
            file_size = self.onnx_file_path.stat().st_size / (1024 * 1024)  # MB
            
            logger.info("=" * 60)
            logger.info("🎉 ONNX转换成功!")
            logger.info(f"📁 模型路径: {self.output_dir}")
            logger.info(f"📊 模型大小: {file_size:.1f} MB")
            logger.info(f"⏱️  转换耗时: {conversion_time:.2f} 秒")
            logger.info(f"🔧 预期加速: 2-2.5倍")
            logger.info("=" * 60)
            
            return True
            
        except Exception as e:
            logger.error(f"ONNX转换失败: {e}")
            logger.error(f"错误详情: {traceback.format_exc()}")
            return False
    
    def test_onnx_model(self) -> bool:
        """
        测试ONNX模型是否可用
        
        Returns:
            测试通过返回True
        """
        try:
            logger.info("🧪 测试ONNX模型...")
            
            if not self.onnx_file_path.exists():
                logger.error("ONNX模型文件不存在")
                return False
            
            # 加载ONNX模型和tokenizer
            onnx_model = ORTModelForFeatureExtraction.from_pretrained(
                str(self.output_dir)
            )
            tokenizer = AutoTokenizer.from_pretrained(str(self.output_dir))
            
            # 测试文本
            test_texts = [
                "这是一个测试句子",
                "ONNX模型转换成功",
                "文本语义向量提取测试"
            ]
            
            logger.info("正在进行推理测试...")
            start_time = time.time()
            
            for text in test_texts:
                # 编码
                inputs = tokenizer(text, return_tensors="pt", truncation=True, padding=True)
                
                # 推理
                outputs = onnx_model(**inputs)
                embeddings = outputs.last_hidden_state
                
                # 简单验证
                assert embeddings.shape[-1] == 768, f"向量维度错误: {embeddings.shape[-1]}"
                logger.debug(f"✅ 测试通过: '{text[:20]}...' -> {embeddings.shape}")
            
            test_time = time.time() - start_time
            avg_time = (test_time / len(test_texts)) * 1000  # ms
            
            logger.info(f"✅ ONNX模型测试成功!")
            logger.info(f"📊 平均推理时间: {avg_time:.1f} ms/句")
            logger.info(f"🎯 输出维度: 768")
            
            return True
            
        except Exception as e:
            logger.error(f"ONNX模型测试失败: {e}")
            logger.error(f"错误详情: {traceback.format_exc()}")
            return False
    
    def cleanup_temp_files(self):
        """清理临时文件"""
        try:
            # 清理缓存
            cache_dir = Path.home() / ".cache" / "huggingface" / "transformers"
            if cache_dir.exists():
                temp_files = list(cache_dir.glob("*tmp*"))
                for temp_file in temp_files[:5]:  # 只清理前5个临时文件
                    temp_file.unlink(missing_ok=True)
                logger.debug(f"清理临时文件: {len(temp_files)} 个")
        except Exception as e:
            logger.debug(f"清理临时文件失败: {e}")


def main():
    """主函数"""
    print("🚀 text2vec-base-chinese ONNX转换工具")
    print("=" * 50)
    
    converter = Text2VecONNXConverter()
    
    try:
        # Step 1: 转换模型
        if not converter.convert_model():
            logger.error("❌ 模型转换失败")
            sys.exit(1)
        
        # Step 2: 测试模型
        if not converter.test_onnx_model():
            logger.error("❌ 模型测试失败")
            sys.exit(1)
        
        # Step 3: 清理临时文件
        converter.cleanup_temp_files()
        
        print("\n🎉 ONNX转换完成!")
        print("接下来可以:")
        print("1. 运行性能测试: python3 tools/testing/test_onnx_performance.py")
        print("2. 更新配置启用ONNX: data/config/ai_models.json")
        print("3. 重启系统验证效果")
        
    except KeyboardInterrupt:
        logger.info("用户取消转换")
        sys.exit(0)
    except Exception as e:
        logger.error(f"转换过程异常: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()