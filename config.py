# 数据库配置
DB_CONFIG = {
    'host': '10.78.44.17',
    'database': 'PRECOMCONTROL',
    'user': 'root',
    'password': 'Gcc$873209',
    'port': 3306
}

# Flask配置
from datetime import timedelta


import os

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