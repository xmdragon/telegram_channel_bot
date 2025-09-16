# Gunicorn配置文件 - 生产级部署
# "正确的工具做正确的事" - Gunicorn管理进程，uvicorn处理异步

import multiprocessing
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 获取端口配置
WEB_PORT = int(os.getenv("WEB_PORT", "8008"))

# 进程管理
bind = f"0.0.0.0:{WEB_PORT}"
workers = int(os.getenv("WORKERS", multiprocessing.cpu_count()))
worker_class = "uvicorn.workers.UvicornWorker"
worker_connections = 1000

# 超时配置 - 保守但实用的值
timeout = 300           # 请求处理超时（5分钟，应对大量消息处理）
graceful_timeout = 30   # 优雅关闭超时
keepalive = 5          # HTTP keep-alive

# 进程重启策略
max_requests = 1000         # 处理1000个请求后重启worker，防止内存泄露
max_requests_jitter = 50    # 随机化重启时间，避免同时重启

# 预处理和热重载
preload_app = True      # 预加载应用，节省内存
reload = False          # 生产环境禁用热重载

# 日志配置 - 明确命名
accesslog = "./logs/gunicorn_access.log"    # HTTP访问日志
errorlog = "./logs/gunicorn_error.log"      # 只记录ERROR级别日志
loglevel = "error"                          # 只记录错误级别

# 安全配置
limit_request_line = 4096       # 限制请求行大小
limit_request_fields = 100      # 限制请求头字段数量
limit_request_field_size = 8192 # 限制请求头字段大小

# 进程名称
proc_name = "telegram-bot-gunicorn"

# 用户和组（生产环境可配置）
# user = "www-data"
# group = "www-data"

def when_ready(server):
    """服务器就绪回调"""
    server.log.info("🚀 Gunicorn生产服务器已就绪")

def worker_int(worker):
    """Worker接收到SIGINT信号"""
    worker.log.info(f"Worker {worker.pid} 接收到中断信号")

def post_fork(server, worker):
    """Worker fork后的钩子，添加延迟避免同时初始化"""
    import time
    import os
    
    try:
        pid = os.getpid()
        worker_age = getattr(worker, 'age', 0)
        delay = (worker_age % 4) * 0.5  # 0, 0.5, 1.0, 1.5秒延迟
        
        if delay > 0:
            server.log.info(f"🕐 Worker {pid} 延迟 {delay:.1f}秒启动，错开初始化")
            time.sleep(delay)
        else:
            server.log.info(f"🚀 Worker {pid} 立即启动（首个worker）")
            
    except Exception as e:
        server.log.error(f"Worker {pid} post_fork错误: {e}")

def on_exit(server):
    """服务器退出回调"""
    server.log.info("🛑 Gunicorn服务器正在关闭")