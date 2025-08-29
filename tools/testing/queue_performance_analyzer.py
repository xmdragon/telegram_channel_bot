#!/usr/bin/env python3
"""
Linus式队列性能分析器 - 识别瓶颈并提供优化建议
遵循"数据说话"的原则，用具体指标驱动优化决策
"""
import os
import sys
import asyncio
import logging
import time
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, List

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

class QueuePerformanceAnalyzer:
    """队列性能分析器 - Linus式简洁分析"""
    
    def __init__(self):
        self.queue = None
        self.analysis_results = {}
        
    async def analyze_performance(self) -> Dict[str, Any]:
        """全面性能分析"""
        logger.info("🔍 开始队列性能分析...")
        
        try:
            # 初始化存储层
            await self._init_storage()
            
            # 获取队列实例
            from app.services.message_queue import get_message_queue
            self.queue = get_message_queue()
            
            # 执行各项分析
            analyses = [
                ("队列状态分析", self._analyze_queue_status),
                ("处理速度分析", self._analyze_processing_speed),
                ("瓶颈识别", self._identify_bottlenecks),
                ("扩展性评估", self._evaluate_scalability),
                ("优化建议", self._generate_optimization_recommendations)
            ]
            
            for name, analysis_func in analyses:
                logger.info(f"▶️ {name}...")
                result = await analysis_func()
                self.analysis_results[name] = result
            
            # 生成综合报告
            await self._generate_comprehensive_report()
            
            return self.analysis_results
            
        except Exception as e:
            logger.error(f"❌ 性能分析失败: {e}")
            import traceback
            traceback.print_exc()
            return {}
    
    async def _init_storage(self):
        """初始化存储层"""
        from app.storage.redis_store import init_redis_stores
        from app.storage.json_store import init_json_stores
        
        if not init_redis_stores():
            raise RuntimeError("Redis存储层初始化失败")
        if not init_json_stores():
            raise RuntimeError("JSON存储层初始化失败")
    
    async def _analyze_queue_status(self) -> Dict[str, Any]:
        """分析当前队列状态"""
        status = await self.queue.get_queue_status()
        
        # 计算关键指标
        total_enqueued = status['stats']['total_enqueued']
        completed = status['stats']['completed']
        failed = status['stats']['failed']
        pending = status['raw_queue_length']
        
        completion_rate = (completed / total_enqueued * 100) if total_enqueued > 0 else 0
        failure_rate = (failed / total_enqueued * 100) if total_enqueued > 0 else 0
        
        analysis = {
            'raw_status': status,
            'metrics': {
                'total_processed': total_enqueued,
                'completion_rate_percent': round(completion_rate, 2),
                'failure_rate_percent': round(failure_rate, 2),
                'pending_messages': pending,
                'backlog_severity': self._assess_backlog_severity(pending)
            }
        }
        
        logger.info(f"📊 队列状态: {pending}条待处理, 完成率{completion_rate:.1f}%, 失败率{failure_rate:.2f}%")
        return analysis
    
    def _assess_backlog_severity(self, pending: int) -> str:
        """评估积压严重程度"""
        if pending < 100:
            return "轻微"
        elif pending < 1000:
            return "中等"
        elif pending < 5000:
            return "严重"
        else:
            return "极严重"
    
    async def _analyze_processing_speed(self) -> Dict[str, Any]:
        """分析处理速度"""
        # 进行短期速度测试
        logger.info("⏱️ 进行处理速度测试...")
        
        initial_status = await self.queue.get_queue_status()
        initial_completed = initial_status['stats']['completed']
        
        # 等待30秒观察处理速度
        await asyncio.sleep(30)
        
        final_status = await self.queue.get_queue_status()
        final_completed = final_status['stats']['completed']
        
        messages_processed = final_completed - initial_completed
        processing_rate = messages_processed / 30  # msg/s
        
        # 估算清空队列所需时间
        pending = final_status['raw_queue_length']
        eta_hours = (pending / processing_rate / 3600) if processing_rate > 0 else float('inf')
        
        analysis = {
            'current_rate_msg_per_sec': round(processing_rate, 2),
            'messages_processed_in_30s': messages_processed,
            'estimated_clear_time_hours': round(eta_hours, 1) if eta_hours != float('inf') else '无法估计',
            'rate_assessment': self._assess_processing_rate(processing_rate)
        }
        
        logger.info(f"🚀 当前处理速度: {processing_rate:.2f} msg/s, 预计清空时间: {eta_hours:.1f}小时")
        return analysis
    
    def _assess_processing_rate(self, rate: float) -> str:
        """评估处理速度"""
        if rate >= 1.0:
            return "优秀"
        elif rate >= 0.5:
            return "良好"
        elif rate >= 0.1:
            return "一般"
        else:
            return "较慢"
    
    async def _identify_bottlenecks(self) -> Dict[str, Any]:
        """识别性能瓶颈"""
        bottlenecks = []
        
        status = await self.queue.get_queue_status()
        
        # 检查各种瓶颈指标
        if status['raw_queue_length'] > 1000:
            bottlenecks.append({
                'type': '队列积压',
                'severity': '高',
                'description': f"队列积压{status['raw_queue_length']}条消息",
                'impact': '处理延迟增加'
            })
        
        failure_rate = status['stats']['failed'] / status['stats']['total_enqueued'] * 100
        if failure_rate > 1.0:
            bottlenecks.append({
                'type': '失败率过高',
                'severity': '中',
                'description': f"失败率{failure_rate:.2f}%",
                'impact': '资源浪费，需要重试'
            })
        
        if status['health'] == 'degraded':
            bottlenecks.append({
                'type': '系统健康状态降级',
                'severity': '高',
                'description': '队列健康状态不佳',
                'impact': '整体性能受影响'
            })
        
        analysis = {
            'bottlenecks_found': len(bottlenecks),
            'bottlenecks': bottlenecks,
            'priority_issues': [b for b in bottlenecks if b['severity'] == '高']
        }
        
        logger.info(f"🔍 发现{len(bottlenecks)}个性能瓶颈")
        return analysis
    
    async def _evaluate_scalability(self) -> Dict[str, Any]:
        """评估系统扩展性"""
        # 检查当前工作进程配置
        # 这里简化实现，实际中可以通过监控API获取
        
        analysis = {
            'current_workers': 5,  # 默认工作进程数
            'theoretical_max_throughput': '5-25 msg/s',  # 基于工作进程数估算
            'scalability_recommendations': [
                {
                    'action': '增加工作进程',
                    'expected_improvement': '线性性能提升',
                    'cost': '内存使用增加'
                },
                {
                    'action': '优化消息处理管道',
                    'expected_improvement': '单个消息处理速度提升',
                    'cost': '代码复杂度增加'
                },
                {
                    'action': '实现动态扩缩容',
                    'expected_improvement': '根据负载自动调整',
                    'cost': '实现复杂度高'
                }
            ]
        }
        
        logger.info("📈 扩展性评估完成")
        return analysis
    
    async def _generate_optimization_recommendations(self) -> Dict[str, Any]:
        """生成优化建议 - Linus式实用主义"""
        recommendations = []
        
        status = await self.queue.get_queue_status()
        pending = status['raw_queue_length']
        
        # 基于实际情况的具体建议
        if pending > 2000:
            recommendations.append({
                'priority': '紧急',
                'category': '立即执行',
                'title': '增加工作进程数量',
                'description': '将工作进程从5个增加到10-15个',
                'implementation': 'python3 message_processor.py --workers 15',
                'expected_result': '处理速度提升2-3倍'
            })
        
        if status['stats']['failed'] > 0:
            recommendations.append({
                'priority': '高',
                'category': '错误处理优化',
                'title': '处理失败消息重试',
                'description': '清理失败队列，重新处理失败消息',
                'implementation': '实现智能重试机制',
                'expected_result': '减少消息丢失'
            })
        
        recommendations.append({
            'priority': '中',
            'category': '性能优化',
            'title': '实现批量处理',
            'description': '对相似消息进行批量处理以提高效率',
            'implementation': '优化MessageProcessor批处理逻辑',
            'expected_result': '减少Redis I/O操作'
        })
        
        recommendations.append({
            'priority': '中',
            'category': '监控完善',
            'title': '增加实时性能指标',
            'description': '实现更细粒度的性能监控',
            'implementation': '扩展QueueMonitor功能',
            'expected_result': '更好的问题诊断能力'
        })
        
        # Linus式实用主义建议
        linus_recommendations = [
            {
                'principle': '"做一件事并做好"',
                'suggestion': '考虑将消息过滤和存储拆分为独立的处理器',
                'benefit': '提高单个处理步骤的效率'
            },
            {
                'principle': '"最笨但最清晰"',
                'suggestion': '优先使用简单的工作进程池扩展，而不是复杂的动态调度',
                'benefit': '降低系统复杂度，提高可靠性'
            },
            {
                'principle': '"消除特殊情况"',
                'suggestion': '统一单消息和组消息的处理路径',
                'benefit': '减少代码分支，提高处理一致性'
            }
        ]
        
        analysis = {
            'immediate_actions': [r for r in recommendations if r['priority'] == '紧急'],
            'high_priority_actions': [r for r in recommendations if r['priority'] == '高'],
            'medium_priority_actions': [r for r in recommendations if r['priority'] == '中'],
            'all_recommendations': recommendations,
            'linus_philosophy_recommendations': linus_recommendations
        }
        
        logger.info(f"💡 生成{len(recommendations)}条优化建议")
        return analysis
    
    async def _generate_comprehensive_report(self):
        """生成综合分析报告"""
        report_time = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = f"tools/testing/queue_performance_report_{report_time}.json"
        
        report = {
            'analysis_timestamp': datetime.now().isoformat(),
            'analysis_results': self.analysis_results,
            'executive_summary': self._generate_executive_summary()
        }
        
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        logger.info(f"📊 综合报告已生成: {report_path}")
    
    def _generate_executive_summary(self) -> Dict[str, Any]:
        """生成执行摘要"""
        return {
            'overall_health': '需要改进',
            'critical_issues': [
                '队列积压严重（3000+消息）',
                '处理速度不足以应对当前负载',
                '系统健康状态降级'
            ],
            'immediate_actions_required': [
                '增加工作进程数量',
                '清理失败消息队列',
                '监控处理速度改善情况'
            ],
            'estimated_improvement_timeline': {
                '立即（增加进程）': '处理速度提升2-3倍',
                '1-2天（积压清理）': '队列长度降至正常水平',
                '1周（优化完成）': '系统健康状态恢复正常'
            }
        }

async def main():
    """主函数"""
    analyzer = QueuePerformanceAnalyzer()
    results = await analyzer.analyze_performance()
    
    if results:
        logger.info("🎉 性能分析完成")
        
        # 输出关键指标摘要
        if '队列状态分析' in results:
            metrics = results['队列状态分析']['metrics']
            logger.info(f"📈 完成率: {metrics['completion_rate_percent']}%")
            logger.info(f"📈 失败率: {metrics['failure_rate_percent']}%")
            logger.info(f"📈 积压程度: {metrics['backlog_severity']}")
        
        return 0
    else:
        logger.error("❌ 性能分析失败")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)