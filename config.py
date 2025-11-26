# 数据库配置（通过环境变量读取，避免硬编码敏感信息）
import os
from datetime import timedelta

DB_CONFIG = {
    # 为了兼容现有部署，host/database/user/port 提供默认值；密码必须从环境变量读取
    'host': os.environ.get('DB_HOST', '10.78.44.17'),
    'database': os.environ.get('DB_NAME', 'PRECOMCONTROL'),
    'user': os.environ.get('DB_USER', 'root'),
    # 严禁在代码中硬编码真实密码：生产/测试环境必须设置 DB_PASSWORD 环境变量
    'password': os.environ.get('DB_PASSWORD'),
    'port': int(os.environ.get('DB_PORT', 3306)),
}

# Flask配置
class FlaskConfig:
    # 安全：从环境变量读取密钥，如果没有则使用默认值（生产环境必须修改）
    SECRET_KEY = os.environ.get('FLASK_SECRET_KEY', 'your-secret-key-change-this-in-production')
    
    # 生产环境配置
    DEBUG = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'  # 默认关闭调试模式
    TESTING = False
    
    # 文件上传限制
    MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100MB 最大上传文件大小
    
    # 会话配置
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = os.environ.get('FLASK_HTTPS', 'False').lower() == 'true'  # HTTPS时启用
    
    # 性能优化
    JSONIFY_PRETTYPRINT_REGULAR = False  # 生产环境不需要美化JSON输出
    JSON_SORT_KEYS = False  # 不排序JSON键，提高性能