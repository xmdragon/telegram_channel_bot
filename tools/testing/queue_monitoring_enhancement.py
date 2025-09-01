#!/usr/bin/env python3
"""
队列监控增强工具 - Linus式实用监控
添加关键性能指标监控，遵循"测量你能改善的"原则
"""
import os
import sys
import asyncio
import logging
import json
import time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, List

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

class QueueMonitoringEnhancer:
    """队列监控增强器 - 添加实用指标"""
    
    def __init__(self):
        self.queue = None
        self.metrics_history = []
        
    async def setup_enhanced_monitoring(self):
        """设置增强监控"""
        logger.info("🔧 设置增强队列监控...")
        
        try:
            await self._init_storage()
            from app.services.message_queue import get_message_queue
            self.queue = get_message_queue()
            
            # 创建监控任务
            monitoring_tasks = [
                ("实时性能监控", self._real_time_performance_monitor),
                ("端到端延迟监控", self._end_to_end_latency_monitor),
                ("工作进程健康监控", self._worker_health_monitor),
                ("队列容量预警", self._queue_capacity_alerting)
            ]
            
            logger.info(f"启动 {len(monitoring_tasks)} 个监控任务...")
            
            # 并发运行所有监控任务
            tasks = []
            for name, monitor_func in monitoring_tasks:
                logger.info(f"▶️ 启动 {name}")
                task = asyncio.create_task(monitor_func())
                tasks.append(task)
            
            # 运行监控循环
            await asyncio.gather(*tasks, return_exceptions=True)
            
        except Exception as e:
            logger.error(f"❌ 监控设置失败: {e}")
            return False
        
        return True
    
    async def _init_storage(self):
        """初始化存储层"""
        from app.storage.redis_store import init_redis_stores
        from app.storage.json_store import init_json_stores
        
        if not redis_manager.is_healthy():
            raise RuntimeError("Redis存储层初始化失败")
        if not init_json_stores():
            raise RuntimeError("JSON存储层初始化失败")
    
    async def _real_time_performance_monitor(self):
        """实时性能监控"""
        logger.info("📊 启动实时性能监控...")
        
        last_stats = None
        monitor_interval = 10  # 10秒间隔
        
        while True:
            try:
                current_stats = await self.queue.get_queue_status()
                timestamp = datetime.now()
                
                if last_stats:
                    # 计算增量指标
                    delta_enqueued = current_stats['stats']['total_enqueued'] - last_stats['stats']['total_enqueued']
                    delta_completed = current_stats['stats']['completed'] - last_stats['stats']['completed']
                    delta_failed = current_stats['stats']['failed'] - last_stats['stats']['failed']
                    
                    # 计算速率
                    enqueue_rate = delta_enqueued / monitor_interval
                    completion_rate = delta_completed / monitor_interval
                    failure_rate = delta_failed / monitor_interval
                    
                    # 计算队列变化
                    queue_length_change = current_stats['raw_queue_length'] - last_stats['raw_queue_length']
                    
                    # 记录指标
                    metrics = {
                        'timestamp': timestamp.isoformat(),
                        'enqueue_rate_msg_per_sec': round(enqueue_rate, 2),
                        'completion_rate_msg_per_sec': round(completion_rate, 2),
                        'failure_rate_msg_per_sec': round(failure_rate, 3),
                        'queue_length': current_stats['raw_queue_length'],
                        'queue_length_change': queue_length_change,
                        'health_status': current_stats['health']
                    }
                    
                    # 保存指标历史
                    self.metrics_history.append(metrics)
                    # 只保留最近1小时的数据
                    if len(self.metrics_history) > 360:  # 1小时的数据点
                        self.metrics_history.pop(0)
                    
                    # 输出关键指标
                    if completion_rate > 0 or enqueue_rate > 0 or queue_length_change != 0:
                        logger.info(f"📈 性能指标: 入队{enqueue_rate:.1f}/s, 完成{completion_rate:.1f}/s, "
                                  f"队列{current_stats['raw_queue_length']}({queue_length_change:+d})")
                    
                    # 检查异常情况
                    await self._check_performance_alerts(metrics)
                
                last_stats = current_stats
                await asyncio.sleep(monitor_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"实时性能监控异常: {e}")
                await asyncio.sleep(monitor_interval)
    
    async def _check_performance_alerts(self, metrics: Dict[str, Any]):
        """检查性能告警"""
        # 队列增长过快告警
        if metrics['queue_length_change'] > 50:
            logger.warning(f"⚠️ 队列积压快速增长: +{metrics['queue_length_change']}条")
        
        # 处理速度过慢告警
        if metrics['completion_rate_msg_per_sec'] < 0.5 and metrics['queue_length'] > 1000:
            logger.warning(f"⚠️ 处理速度过慢: {metrics['completion_rate_msg_per_sec']:.2f} msg/s，队列积压{metrics['queue_length']}条")
        
        # 失败率告警
        if metrics['failure_rate_msg_per_sec'] > 0.1:
            logger.warning(f"⚠️ 失败率过高: {metrics['failure_rate_msg_per_sec']:.3f} failures/s")
    
    async def _end_to_end_latency_monitor(self):
        """端到端延迟监控"""
        logger.info("⏱️ 启动端到端延迟监控...")
        
        from app.services.message_queue import CollectedMessage
        
        while True:
            try:
                # 发送测试消息测量延迟
                start_time = datetime.now()
                
                test_msg = CollectedMessage(
                    channel_id="-1001111111112",  # 测试频道
                    message_id=int(time.time()),  # 使用时间戳作为唯一ID
                    content=f"延迟测试消息 - {start_time.isoformat()}",
                    media_type="text"
                )
                
                # 入队
                enqueue_success = await self.queue.enqueue_message(test_msg)
                enqueue_time = datetime.now()
                
                if enqueue_success:
                    # 尝试立即出队（测试处理延迟）
                    dequeued = await self.queue.dequeue_message("latency-test", timeout=5)
                    dequeue_time = datetime.now()
                    
                    if dequeued:
                        # 标记完成
                        await self.queue.mark_completed("latency-test", dequeued)
                        complete_time = datetime.now()
                        
                        # 计算各阶段延迟
                        enqueue_latency = (enqueue_time - start_time).total_seconds() * 1000
                        dequeue_latency = (dequeue_time - enqueue_time).total_seconds() * 1000
                        total_latency = (complete_time - start_time).total_seconds() * 1000
                        
                        # 记录延迟指标
                        if total_latency > 100:  # 只记录显著延迟
                            logger.info(f"⏱️ 端到端延迟: 总计{total_latency:.1f}ms "
                                      f"(入队{enqueue_latency:.1f}ms + 出队{dequeue_latency:.1f}ms)")
                        
                        # 延迟告警
                        if total_latency > 1000:  # 1秒告警
                            logger.warning(f"⚠️ 端到端延迟过高: {total_latency:.1f}ms")
                
                # 每60秒测试一次
                await asyncio.sleep(60)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"延迟监控异常: {e}")
                await asyncio.sleep(60)
    
    async def _worker_health_monitor(self):
        """工作进程健康监控"""
        logger.info("👥 启动工作进程健康监控...")
        
        while True:
            try:
                # 获取工作进程状态
                worker_keys = self.queue.redis.keys(self.queue.QUEUE_KEYS['processing'].format('*'))
                active_workers = len(worker_keys)
                
                # 检查工作进程TTL
                stuck_workers = 0
                expiring_workers = 0
                
                for worker_key in worker_keys:
                    ttl = self.queue.redis.ttl(worker_key)
                    if ttl < 0:  # 无TTL，可能卡住
                        stuck_workers += 1
                    elif ttl < 60:  # TTL小于60秒，即将过期
                        expiring_workers += 1
                
                # 健康状态评估
                if active_workers == 0:
                    logger.warning("🚨 没有活跃的工作进程！")
                elif active_workers < 5:
                    logger.warning(f"⚠️ 工作进程数量较少: {active_workers}个")
                elif stuck_workers > 0:
                    logger.warning(f"⚠️ {stuck_workers}个工作进程可能卡住")
                elif expiring_workers > active_workers * 0.5:
                    logger.warning(f"⚠️ {expiring_workers}个工作进程即将过期")
                else:
                    # 健康状态良好，降低日志频率
                    if datetime.now().minute % 5 == 0:  # 每5分钟报告一次正常状态
                        logger.info(f"✅ 工作进程健康: {active_workers}个活跃")
                
                await asyncio.sleep(30)  # 30秒检查一次
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"工作进程监控异常: {e}")
                await asyncio.sleep(30)
    
    async def _queue_capacity_alerting(self):
        """队列容量预警"""
        logger.info("📏 启动队列容量预警...")
        
        # 容量阈值
        WARNING_THRESHOLD = 2000
        CRITICAL_THRESHOLD = 5000
        EMERGENCY_THRESHOLD = 10000
        
        last_alert_time = {}
        alert_cooldown = 300  # 5分钟冷却期
        
        while True:
            try:
                status = await self.queue.get_queue_status()
                queue_length = status['raw_queue_length']
                current_time = datetime.now()
                
                # 确定告警级别
                alert_level = None
                if queue_length >= EMERGENCY_THRESHOLD:
                    alert_level = "EMERGENCY"
                elif queue_length >= CRITICAL_THRESHOLD:
                    alert_level = "CRITICAL"
                elif queue_length >= WARNING_THRESHOLD:
                    alert_level = "WARNING"
                
                # 发送告警（考虑冷却期）
                if alert_level:
                    last_alert = last_alert_time.get(alert_level, datetime.min)
                    if (current_time - last_alert).total_seconds() > alert_cooldown:
                        if alert_level == "EMERGENCY":
                            logger.error(f"🚨 紧急告警: 队列长度 {queue_length} 超过紧急阈值 {EMERGENCY_THRESHOLD}")
                        elif alert_level == "CRITICAL":
                            logger.error(f"🔥 严重告警: 队列长度 {queue_length} 超过严重阈值 {CRITICAL_THRESHOLD}")
                        elif alert_level == "WARNING":
                            logger.warning(f"⚠️ 容量告警: 队列长度 {queue_length} 超过警告阈值 {WARNING_THRESHOLD}")
                        
                        last_alert_time[alert_level] = current_time
                        
                        # 提供建议
                        if queue_length > 5000:
                            logger.info("💡 建议: 增加工作进程数量或检查处理瓶颈")
                
                await asyncio.sleep(60)  # 1分钟检查一次
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"容量预警异常: {e}")
                await asyncio.sleep(60)
    
    async def generate_monitoring_report(self):
        """生成监控报告"""
        if not self.metrics_history:
            logger.warning("无监控数据，无法生成报告")
            return
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = f"tools/testing/monitoring_report_{timestamp}.json"
        
        # 计算统计指标
        completion_rates = [m['completion_rate_msg_per_sec'] for m in self.metrics_history]
        queue_lengths = [m['queue_length'] for m in self.metrics_history]
        
        report = {
            'report_timestamp': datetime.now().isoformat(),
            'monitoring_duration_minutes': len(self.metrics_history) * 10 / 60,
            'metrics_summary': {
                'avg_completion_rate': sum(completion_rates) / len(completion_rates),
                'max_completion_rate': max(completion_rates),
                'min_queue_length': min(queue_lengths),
                'max_queue_length': max(queue_lengths),
                'avg_queue_length': sum(queue_lengths) / len(queue_lengths)
            },
            'raw_metrics': self.metrics_history[-100:]  # 最近100个数据点
        }
        
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        logger.info(f"📋 监控报告已生成: {report_path}")

async def main():
    """主函数 - 运行增强监控"""
    enhancer = QueueMonitoringEnhancer()
    
    try:
        logger.info("🚀 启动队列监控增强...")
        
        # 运行监控任务
        monitoring_task = asyncio.create_task(enhancer.setup_enhanced_monitoring())
        
        # 等待监控运行（或手动停止）
        await asyncio.wait_for(monitoring_task, timeout=300)  # 5分钟测试
        
    except asyncio.TimeoutError:
        logger.info("⏰ 监控测试完成（5分钟）")
    except KeyboardInterrupt:
        logger.info("⏹️ 用户停止监控")
    finally:
        # 生成报告
        await enhancer.generate_monitoring_report()
        logger.info("🎉 监控增强测试完成")

if __name__ == "__main__":
    asyncio.run(main())