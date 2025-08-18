#!/usr/bin/env python3
"""
SentenceTransformer初始化追踪器
精确定位哪些模块在初始化SentenceTransformer
"""
import sys
import os
import traceback
from typing import List, Dict

# 添加项目根目录到路径
sys.path.append('.')

# 设置AI禁用环境
os.environ['AI_ENABLED'] = 'false'
os.environ['ENVIRONMENT'] = 'development'

class SentenceTransformerTracer:
    """SentenceTransformer初始化追踪器"""
    
    def __init__(self):
        self.init_count = 0
        self.init_traces: List[Dict] = []
        self.original_init = None
    
    def patch_sentence_transformer(self):
        """猴子补丁SentenceTransformer.__init__"""
        try:
            # 延迟导入以避免立即触发
            import sentence_transformers
            
            # 保存原始__init__
            self.original_init = sentence_transformers.SentenceTransformer.__init__
            
            def traced_init(self_st, *args, **kwargs):
                self.init_count += 1
                
                # 获取调用栈
                stack = traceback.extract_stack()
                
                # 过滤出项目相关的调用栈
                project_stack = []
                for frame in stack:
                    if '/workspace/telegram_channel_bot/' in frame.filename:
                        project_stack.append({
                            'filename': frame.filename.split('/workspace/telegram_channel_bot/')[-1],
                            'line': frame.lineno,
                            'function': frame.name,
                            'code': frame.line
                        })
                
                trace_info = {
                    'count': self.init_count,
                    'args': str(args)[:100],
                    'kwargs': str(kwargs)[:100],
                    'stack': project_stack[-10:]  # 最近10层调用
                }
                
                self.init_traces.append(trace_info)
                
                print(f"\\n🔍 SentenceTransformer初始化 #{self.init_count}")
                print(f"参数: {trace_info['args']}")
                print("调用栈:")
                for i, frame in enumerate(project_stack[-5:], 1):  # 显示最近5层
                    print(f"  {i}. {frame['filename']}:{frame['line']} in {frame['function']}()")
                    if frame['code']:
                        print(f"     {frame['code'].strip()}")
                
                # 调用原始初始化
                return self.original_init(self_st, *args, **kwargs)
            
            # 应用补丁
            sentence_transformers.SentenceTransformer.__init__ = traced_init
            print("✅ SentenceTransformer追踪补丁已安装")
            
        except ImportError:
            print("⚠️ sentence_transformers未安装，无法追踪")
        except Exception as e:
            print(f"❌ 安装追踪补丁失败: {e}")
    
    def get_summary(self) -> Dict:
        """获取追踪汇总"""
        return {
            'total_count': self.init_count,
            'traces': self.init_traces
        }

def main():
    """主函数"""
    print("🔍 开始追踪SentenceTransformer初始化...")
    print("=" * 60)
    
    # 创建追踪器
    tracer = SentenceTransformerTracer()
    
    # 安装追踪补丁
    tracer.patch_sentence_transformer()
    
    # 导入可能触发SentenceTransformer的模块
    print("\\n📦 开始导入messages_crud模块...")
    
    try:
        # 这应该触发所有的SentenceTransformer初始化
        from app.api.messages_crud import router
        print("✅ messages_crud导入完成")
        
    except Exception as e:
        print(f"❌ 导入失败: {e}")
        traceback.print_exc()
    
    # 输出追踪结果
    summary = tracer.get_summary()
    
    print("\\n" + "=" * 60)
    print(f"📊 追踪结果汇总")
    print("=" * 60)
    print(f"SentenceTransformer初始化总次数: {summary['total_count']}")
    
    if summary['total_count'] == 0:
        print("🎉 没有检测到SentenceTransformer初始化！")
        return
    
    # 分析每个初始化的来源
    print("\\n📍 各初始化详细来源:")
    for i, trace in enumerate(summary['traces'], 1):
        print(f"\\n初始化 #{i}:")
        
        # 找出最可能的源头模块
        if trace['stack']:
            source_file = trace['stack'][-1]['filename']
            source_func = trace['stack'][-1]['function']
            print(f"  源头: {source_file} -> {source_func}()")
            
            # 显示完整调用链
            print("  调用链:")
            for j, frame in enumerate(trace['stack']):
                indent = "    " + "  " * j
                print(f"{indent}{frame['filename']}:{frame['line']} in {frame['function']}()")
        
        # 参数信息
        if trace['args'] or trace['kwargs']:
            print(f"  参数: {trace['args']}")
    
    # 给出优化建议
    print("\\n" + "=" * 60)
    print("🛠️ 优化建议")
    print("=" * 60)
    
    unique_sources = set()
    for trace in summary['traces']:
        if trace['stack']:
            source = trace['stack'][-1]['filename']
            unique_sources.add(source)
    
    for source in unique_sources:
        print(f"• 检查 {source} 中的SentenceTransformer使用")
        print(f"  建议: 添加AI配置开关或实现懒加载")

if __name__ == "__main__":
    main()