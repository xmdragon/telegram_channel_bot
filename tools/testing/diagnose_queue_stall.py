#!/usr/bin/env python3
"""
Linus式队列停滞诊断工具 - 快速定位问题根源
遵循"先找到问题，再谈优化"的实用主义原则
"""
import os
import sys
import asyncio
import logging
from pathlib import Path
from datetime import datetime, timedelta

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

class QueueStallDiagnoser:
    """队列停滞诊断器"""
    
    def __init__(self):
        self.findings = []
        
    async def diagnose(self):
        """诊断队列停滞问题"""
        logger.info("🔍 开始队列停滞诊断...")
        
        try:
            await self._init_storage()
            from app.services.message_queue import get_message_queue
            self.queue = get_message_queue()
            
            # 执行诊断步骤
            checks = [
                ("检查队列基础状态", self._check_queue_basic_status),
                ("分析消息流向", self._analyze_message_flow),
                ("检查工作进程状态", self._check_worker_status),
                ("验证队列操作", self._test_queue_operations),
                ("诊断停滞原因", self._diagnose_stall_cause)
            ]
            
            for name, check_func in checks:
                logger.info(f"▶️ {name}...")
                try:
                    result = await check_func()
                    if result.get('issues'):
                        self.findings.extend(result['issues'])
                    if result.get('info'):
                        logger.info(f"ℹ️ {result['info']}")
                except Exception as e:
                    logger.error(f"❌ {name}失败: {e}")
                    self.findings.append({
                        'type': 'diagnostic_error',
                        'description': f"{name}过程中出错: {str(e)}",
                        'severity': 'high'
                    })
            
            # 生成诊断报告
            await self._generate_diagnosis_report()
            return True
            
        except Exception as e:
            logger.error(f"❌ 诊断失败: {e}")
            return False
    
    async def _init_storage(self):
        """初始化存储层"""
        from app.storage.redis_store import init_redis_stores
        from app.storage.json_store import init_json_stores
        
        if not redis_manager.is_healthy():
            raise RuntimeError("Redis存储层初始化失败")
        if not init_json_stores():
            raise RuntimeError("JSON存储层初始化失败")
    
    async def _check_queue_basic_status(self):
        """检查队列基础状态"""
        status = await self.queue.get_queue_status()
        result = {'issues': [], 'info': None}
        
        # 检查各项指标
        raw_length = status['raw_queue_length']
        failed_length = status['failed_queue_length']
        stats = status['stats']
        
        if raw_length > 3000:
            result['issues'].append({
                'type': 'queue_backlog',
                'description': f'队列积压严重: {raw_length}条消息',
                'severity': 'high',
                'impact': '处理延迟，系统性能下降'
            })
        
        if failed_length > 5:
            result['issues'].append({
                'type': 'failed_messages',
                'description': f'失败消息较多: {failed_length}条',
                'severity': 'medium',
                'impact': '消息丢失风险'
            })
        
        if status['health'] == 'degraded':
            result['issues'].append({
                'type': 'health_degraded',
                'description': '系统健康状态降级',
                'severity': 'high',
                'impact': '整体性能受影响'
            })
        
        result['info'] = f"队列状态: 待处理{raw_length}, 失败{failed_length}, 健康度{status['health']}"
        return result
    
    async def _analyze_message_flow(self):
        """分析消息流向"""
        status = await self.queue.get_queue_status()
        stats = status['stats']
        
        result = {'issues': [], 'info': None}
        
        total_enqueued = stats['total_enqueued']
        dequeued = stats['dequeued']
        completed = stats['completed']
        
        # 计算处理差距
        dequeue_gap = total_enqueued - dequeued
        completion_gap = dequeued - completed
        
        if dequeue_gap > 1000:
            result['issues'].append({
                'type': 'dequeue_bottleneck',
                'description': f'出队速度跟不上入队: 差距{dequeue_gap}条',
                'severity': 'high',
                'impact': '消息处理器可能停滞或处理速度不足'
            })
        
        if completion_gap > 500:
            result['issues'].append({
                'type': 'completion_bottleneck', 
                'description': f'消息完成标记滞后: 差距{completion_gap}条',
                'severity': 'medium',
                'impact': '处理统计不准确，可能有进程崩溃'
            })
        
        # 计算完成率
        completion_rate = (completed / total_enqueued * 100) if total_enqueued > 0 else 0
        
        result['info'] = f"消息流向: 入队{total_enqueued} -> 出队{dequeued} -> 完成{completed} (完成率{completion_rate:.1f}%)"
        return result
    
    async def _check_worker_status(self):
        """检查工作进程状态"""
        result = {'issues': [], 'info': None}
        
        # 检查Redis中的工作进程状态
        try:
            # 获取所有正在处理的worker key
            worker_keys = self.queue.redis.keys(self.queue.QUEUE_KEYS['processing'].format('*'))
            active_workers = len(worker_keys)
            
            if active_workers == 0:
                result['issues'].append({
                    'type': 'no_active_workers',
                    'description': '没有发现活跃的工作进程',
                    'severity': 'critical',
                    'impact': '消息无法被处理'
                })
            elif active_workers < 3:
                result['issues'].append({
                    'type': 'insufficient_workers',
                    'description': f'活跃工作进程过少: {active_workers}个',
                    'severity': 'medium',
                    'impact': '处理能力不足'
                })
            
            # 检查工作进程是否有超时的
            current_time = datetime.now()
            stuck_workers = 0
            
            for worker_key in worker_keys:
                ttl = self.queue.redis.ttl(worker_key)
                if ttl < 60:  # 如果TTL小于60秒，可能是即将超时的任务
                    stuck_workers += 1
            
            if stuck_workers > 0:
                result['issues'].append({
                    'type': 'stuck_workers',
                    'description': f'{stuck_workers}个工作进程可能卡住',
                    'severity': 'high',
                    'impact': '处理效率降低'
                })
            
            result['info'] = f"工作进程状态: 活跃{active_workers}个, 疑似卡住{stuck_workers}个"
            return result
            
        except Exception as e:
            result['issues'].append({
                'type': 'worker_check_failed',
                'description': f'无法检查工作进程状态: {str(e)}',
                'severity': 'medium',
                'impact': '诊断信息不完整'
            })
            return result
    
    async def _test_queue_operations(self):
        """验证队列操作"""
        result = {'issues': [], 'info': None}
        
        try:
            from app.services.message_queue import CollectedMessage
            
            # 创建测试消息
            test_msg = CollectedMessage(
                channel_id="-1001111111111",
                message_id=999999,
                content="队列诊断测试消息",
                media_type="text"
            )
            
            # 测试入队
            enqueue_success = await self.queue.enqueue_message(test_msg)
            if not enqueue_success:
                result['issues'].append({
                    'type': 'enqueue_failed',
                    'description': '测试消息入队失败',
                    'severity': 'critical',
                    'impact': '队列入队功能异常'
                })
                return result
            
            # 测试出队
            dequeued = await self.queue.dequeue_message("diagnose-test", timeout=2)
            if dequeued:
                # 标记完成
                await self.queue.mark_completed("diagnose-test", dequeued)
                result['info'] = "队列操作测试: 入队✅, 出队✅, 标记完成✅"
            else:
                result['issues'].append({
                    'type': 'dequeue_failed', 
                    'description': '测试消息出队超时',
                    'severity': 'high',
                    'impact': '队列出队功能异常或处理器未运行'
                })
            
        except Exception as e:
            result['issues'].append({
                'type': 'queue_test_error',
                'description': f'队列操作测试出错: {str(e)}',
                'severity': 'high',
                'impact': '队列功能可能异常'
            })
        
        return result
    
    async def _diagnose_stall_cause(self):
        """诊断停滞根本原因"""
        result = {'issues': [], 'info': None}
        
        # 基于前面的发现，推断停滞原因
        issue_types = [finding['type'] for finding in self.findings]
        
        if 'no_active_workers' in issue_types:
            result['issues'].append({
                'type': 'root_cause',
                'description': '根本原因: 消息处理器进程未运行或已停滞',
                'severity': 'critical',
                'impact': '需要重启消息处理器',
                'solution': '# 队列处理功能已整合到services模块 --workers 10'
            })
        elif 'dequeue_failed' in issue_types and 'queue_backlog' in issue_types:
            result['issues'].append({
                'type': 'root_cause', 
                'description': '根本原因: 处理器运行但无法从队列获取消息',
                'severity': 'high',
                'impact': '可能是Redis连接问题或队列机制故障',
                'solution': '检查Redis连接，重启处理器'
            })
        elif 'queue_backlog' in issue_types and 'insufficient_workers' in issue_types:
            result['issues'].append({
                'type': 'root_cause',
                'description': '根本原因: 工作进程数量不足以应对当前负载',
                'severity': 'high', 
                'impact': '需要增加工作进程数量',
                'solution': '增加工作进程: # 队列处理功能已整合到services模块 --workers 15'
            })
        
        return result
    
    async def _generate_diagnosis_report(self):
        """生成诊断报告"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = f"tools/testing/queue_stall_diagnosis_{timestamp}.txt"
        
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(f"队列停滞诊断报告\n")
            f.write(f"诊断时间: {datetime.now().isoformat()}\n")
            f.write("=" * 50 + "\n\n")
            
            if not self.findings:
                f.write("✅ 未发现明显问题\n")
            else:
                # 按严重程度分组
                critical = [f for f in self.findings if f['severity'] == 'critical']
                high = [f for f in self.findings if f['severity'] == 'high']
                medium = [f for f in self.findings if f['severity'] == 'medium']
                
                if critical:
                    f.write("🚨 紧急问题:\n")
                    for issue in critical:
                        f.write(f"  - {issue['description']}\n")
                        if 'solution' in issue:
                            f.write(f"    解决方案: {issue['solution']}\n")
                        f.write(f"    影响: {issue['impact']}\n\n")
                
                if high:
                    f.write("⚠️ 高优先级问题:\n")
                    for issue in high:
                        f.write(f"  - {issue['description']}\n")
                        if 'solution' in issue:
                            f.write(f"    解决方案: {issue['solution']}\n")
                        f.write(f"    影响: {issue['impact']}\n\n")
                
                if medium:
                    f.write("ℹ️ 中等优先级问题:\n")
                    for issue in medium:
                        f.write(f"  - {issue['description']}\n")
                        f.write(f"    影响: {issue['impact']}\n\n")
        
        logger.info(f"📋 诊断报告已生成: {report_path}")
        
        # 输出关键发现
        critical_issues = [f for f in self.findings if f['severity'] == 'critical']
        if critical_issues:
            logger.warning("🚨 发现紧急问题:")
            for issue in critical_issues:
                logger.warning(f"  - {issue['description']}")
                if 'solution' in issue:
                    logger.info(f"  解决方案: {issue['solution']}")

async def main():
    """主函数"""
    diagnoser = QueueStallDiagnoser()
    success = await diagnoser.diagnose()
    
    if success:
        logger.info("🎉 诊断完成")
        return 0
    else:
        logger.error("❌ 诊断失败")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)