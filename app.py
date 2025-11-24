import os
from flask import Flask, session, redirect, url_for, request, g
from config import FlaskConfig
from routes.system_routes import system_bp
from routes.subsystem_routes import subsystem_bp
from routes.test_package_routes import test_package_bp
from routes.backup_routes import backup_bp
from routes.precom_routes import precom_bp
from routes.auth_routes import auth_bp
from database import ensure_user_management_tables, ensure_precom_tables
from utils.auth_manager import bootstrap_user_management
from utils.auth_decorators import has_permission
# from routes.test_package_routes_new_ui import test_package_new_ui_bp  # 新UI路由
# from routes.system_routes_new_ui import system_new_ui_bp  # 系统管理新UI
# from routes.subsystem_routes_new_ui import subsystem_new_ui_bp  # 子系统管理新UI


def create_app():
    """创建Flask应用"""
    app = Flask(__name__)
    app.config.from_object(FlaskConfig)
    
    # 初始化数据库连接池（生产环境）
    from database import init_connection_pool
    init_connection_pool()
    
    # 初始化数据库表
    ensure_user_management_tables()
    ensure_precom_tables()
    bootstrap_user_management()
    
    # 配置日志（生产环境）
    import logging
    from logging.handlers import RotatingFileHandler
    if not app.debug:
        os.makedirs('logs', exist_ok=True)
        file_handler = RotatingFileHandler(
            'logs/app.log', 
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=10
        )
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        ))
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)
        app.logger.setLevel(logging.INFO)
        app.logger.info('应用启动')
        
        # 配置数据库模块的日志记录器，使其也记录到同一个日志文件
        db_logger = logging.getLogger('database')
        db_logger.setLevel(logging.INFO)
        db_logger.addHandler(file_handler)
        db_logger.propagate = False  # 避免重复记录
    
    # 注册蓝图
    app.register_blueprint(auth_bp)
    app.register_blueprint(system_bp)
    app.register_blueprint(subsystem_bp)
    app.register_blueprint(test_package_bp)
    app.register_blueprint(precom_bp)
    app.register_blueprint(backup_bp)  # 备份管理路由

    PUBLIC_ENDPOINTS = {'auth.login', 'static', 'index'}
    # 不需要模块权限检查的端点（账户管理、个人信息等）
    NO_MODULE_CHECK_ENDPOINTS = {'auth.', 'admin.users', 'profile'}

    @app.before_request
    def enforce_login():
        endpoint = request.endpoint
        if not endpoint:
            return
        if endpoint in PUBLIC_ENDPOINTS or endpoint.startswith('static'):
            return
        if not session.get('user'):
            return redirect(url_for('auth.login', next=request.path))
        g.current_user = session.get('user')
        
        # 检查模块访问权限
        from utils.auth_decorators import get_module_code_by_path, has_module_access
        # 跳过不需要模块检查的端点
        if any(endpoint.startswith(prefix) for prefix in NO_MODULE_CHECK_ENDPOINTS):
            return
        
        # 跳过API路由（API路由有自己的权限检查）
        if request.path.startswith('/api/'):
            return
        
        module_code = get_module_code_by_path(request.path)
        if module_code and not has_module_access(module_code):
            # 用户没有访问该模块的权限
            from flask import render_template
            return render_template('errors/403_module.html', 
                                 module_code=module_code,
                                 path=request.path), 403

    @app.context_processor
    def inject_user():
        return {
            'current_user': session.get('user'),
            'has_permission': has_permission
        }
    
    # 错误处理（生产环境）
    @app.errorhandler(404)
    def not_found(error):
        from flask import render_template
        return render_template('errors/404.html'), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        from flask import render_template
        app.logger.error(f'服务器错误: {error}', exc_info=True)
        return render_template('errors/500.html'), 500
    
    # 健康检查端点（用于负载均衡和监控）
    @app.route('/health')
    def health_check():
        from database import create_connection
        try:
            conn = create_connection()
            if conn:
                conn.close()
                return {'status': 'healthy', 'database': 'connected'}, 200
            else:
                return {'status': 'unhealthy', 'database': 'disconnected'}, 503
        except Exception as e:
            app.logger.error(f'健康检查失败: {e}')
            return {'status': 'unhealthy', 'error': str(e)}, 503
    
    # 首页（工业化风格）
    @app.route('/')
    def index():
        from flask import render_template
        from utils.auth_manager import get_user_accessible_modules, get_all_modules
        from database import create_connection
        
        user = session.get('user')
        accessible_modules = []
        all_modules_map = {}
        
        if user:
            # 获取用户可访问的模块代码
            accessible_modules = get_user_accessible_modules(
                user['id'], 
                bool(user.get('is_super_admin', False))
            )
            # 获取所有模块信息用于显示
            all_modules = get_all_modules()
            all_modules_map = {m['ModuleCode']: m for m in all_modules}
        
        return render_template(
            'index_industrial.html',
            accessible_modules=accessible_modules,
            all_modules_map=all_modules_map
        )
    
    # 旧首页（备份）
    @app.route('/index_old')
    def index_old():
        return '''
        <!DOCTYPE html>
        <html>
            <head>
                <title>预试车管理系统</title>
                <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
                <style>
                    body { background-color: #f8f9fa; }
                    .hero { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 80px 0; }
                    .feature-card { transition: transform 0.3s; }
                    .feature-card:hover { transform: translateY(-5px); }
                </style>
            </head>
            <body>
                <nav class="navbar navbar-expand-lg navbar-dark bg-dark">
                    <div class="container">
                        <a class="navbar-brand" href="/">🚀 预试车管理系统</a>
                        <div class="navbar-nav">
                            <a class="nav-link" href="/">首页</a>
                            <a class="nav-link" href="/systems">系统管理</a>
                            <a class="nav-link" href="/subsystems">子系统管理</a>
                            <a class="nav-link" href="/test_packages">试压包管理</a>
                            <a class="nav-link" href="/backup">备份管理</a>
                        </div>
                    </div>
                </nav>
                
                <div class="hero text-center">
                    <div class="container">
                        <h1 class="display-4">🚀 预试车管理系统</h1>
                        <p class="lead">完整的预试车管理系统 - 系统、子系统、试压包一体化管理</p>
                        <a href="/systems" class="btn btn-light btn-lg mt-3">开始使用</a>
                    </div>
                </div>
                
                <div class="container mt-5">
                    <div class="row">
                        <div class="col-md-3 mb-4">
                            <div class="card feature-card shadow">
                                <div class="card-body text-center">
                                    <h3>🔧</h3>
                                    <h5 class="card-title">系统管理</h5>
                                    <p class="card-text">管理系统基本信息</p>
                                    <a href="/systems" class="btn btn-primary">进入</a>
                                </div>
                            </div>
                        </div>
                        <div class="col-md-3 mb-4">
                            <div class="card feature-card shadow">
                                <div class="card-body text-center">
                                    <h3>⚙️</h3>
                                    <h5 class="card-title">子系统管理</h5>
                                    <p class="card-text">管理子系统信息</p>
                                    <a href="/subsystems" class="btn btn-primary">进入</a>
                                </div>
                            </div>
                        </div>
                        <div class="col-md-3 mb-4">
                            <div class="card feature-card shadow">
                                <div class="card-body text-center">
                                    <h3>📦</h3>
                                    <h5 class="card-title">试压包管理</h5>
                                    <p class="card-text">管理水压测试包</p>
                                    <a href="/test_packages" class="btn btn-primary">进入</a>
                                </div>
                            </div>
                        </div>
                        <div class="col-md-3 mb-4">
                            <div class="card feature-card shadow">
                                <div class="card-body text-center">
                                    <h3>💾</h3>
                                    <h5 class="card-title">备份管理</h5>
                                    <p class="card-text">数据备份与同步</p>
                                    <a href="/backup" class="btn btn-primary">进入</a>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <div class="alert alert-info mt-4">
                        <strong>调试信息:</strong> 应用运行正常！
                    </div>
                </div>
                
                <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
            </body>
        </html>
        '''
    
    return app

if __name__ == '__main__':
    """
    开发环境直接运行
    生产环境请使用 WSGI 服务器（Gunicorn/Waitress）
    运行方式：
    - Windows: python start_production.bat 或 waitress-serve --listen=0.0.0.0:5000 wsgi:app
    - Linux: bash start_production.sh 或 gunicorn -c gunicorn_config.py wsgi:app
    """
    import os
    
    app = create_app()
    
    # 检查是否存在SSL证书
    cert_file = 'cert.pem'
    key_file = 'key.pem'
    
    # 开发环境配置
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    
    if os.path.exists(cert_file) and os.path.exists(key_file):
        # Use HTTPS
        print("=" * 60)
        print("Flask Application Starting (HTTPS Mode - Development)")
        print("=" * 60)
        print("Local access:  https://localhost:5000")
        print("Network access: https://0.0.0.0:5000")
        print("SSL certificate loaded")
        print("\n注意: 这是开发模式，生产环境请使用 WSGI 服务器")
        print("      Windows: python start_production.bat")
        print("      Linux: bash start_production.sh")
        print("=" * 60 + "\n")
        
        app.run(
            debug=debug_mode, 
            host='0.0.0.0', 
            port=5000,
            ssl_context=(cert_file, key_file),
            threaded=True,
            use_reloader=debug_mode
        )
    else:
        # Use HTTP
        print("=" * 60)
        print("Flask Application Starting (HTTP Mode - Development)")
        print("=" * 60)
        print("Local access:  http://localhost:5000")
        print("Network access: http://0.0.0.0:5000")
        print("\n注意: 这是开发模式，生产环境请使用 WSGI 服务器")
        print("      Windows: python start_production.bat")
        print("      Linux: bash start_production.sh")
        print("=" * 60 + "\n")
        
        app.run(debug=debug_mode, host='0.0.0.0', port=5000, threaded=True)