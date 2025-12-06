"""
Gunicorn 配置文件
用于生产环境部署，支持50-80并发

端口配置：固定使用5000端口，不占用其他端口（8000、8203、8206等）
"""
import multiprocessing

# 服务器配置
# 固定使用5000端口，确保不占用其他应用端口
bind = "0.0.0.0:5000"
backlog = 2048

# 工作进程配置
# 推荐：CPU核心数 * 2 + 1
workers = multiprocessing.cpu_count() * 2 + 1
# 如果CPU核心数较少，可以手动设置
# workers = 8  # 支持50-80并发

# 工作模式
worker_class = "sync"  # 同步工作模式，适合I/O密集型应用
worker_connections = 1000

# 超时设置
timeout = 120  # 请求超时时间（秒）
keepalive = 5  # Keep-Alive连接保持时间（秒）

# 日志配置
accesslog = "logs/gunicorn_access.log"
errorlog = "logs/gunicorn_error.log"
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# 进程名称
proc_name = "precom_control"

# 性能优化
preload_app = True  # 预加载应用，减少内存占用
max_requests = 1000  # 每个工作进程处理的最大请求数，防止内存泄漏
max_requests_jitter = 50  # 随机抖动，避免所有进程同时重启

# 安全
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190

