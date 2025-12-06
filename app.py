"""
PrecomControl 主应用文件

端口配置说明：
- 本应用固定使用5000端口
- 不会占用其他端口（8000、8203、8206等）
- 所有启动配置均使用5000端口
"""
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


def compile_translations_if_needed():
    """编译翻译文件（如果 babel 可用）"""
    try:
        import os
        from babel.messages.mofile import write_mo
        from babel.messages.pofile import read_po
        
        languages = ['en_US', 'ru_RU', 'zh_CN']
        translations_dir = 'translations'
        
        for lang in languages:
            po_file = os.path.join(translations_dir, lang, 'LC_MESSAGES', 'messages.po')
            mo_file = os.path.join(translations_dir, lang, 'LC_MESSAGES', 'messages.mo')
            
            if os.path.exists(po_file):
                # 检查 .mo 文件是否存在或是否过期
                if not os.path.exists(mo_file) or os.path.getmtime(po_file) > os.path.getmtime(mo_file):
                    print(f'[翻译] 编译 {lang} 翻译文件...')
                    try:
                        with open(po_file, 'rb') as f:
                            catalog = read_po(f)
                        with open(mo_file, 'wb') as f:
                            write_mo(f, catalog)
                        print(f'[翻译] ✓ 成功编译 {lang}')
                    except Exception as e:
                        print(f'[翻译] ✗ 编译 {lang} 失败: {e}')
    except ImportError:
        print('[翻译] Babel 未安装，跳过翻译编译')
    except Exception as e:
        print(f'[翻译] 编译翻译文件时出错: {e}')


def create_app():
    """创建Flask应用"""
    app = Flask(__name__)
    app.config.from_object(FlaskConfig)
    
    # 编译翻译文件（如果需要）
    compile_translations_if_needed()
    
    # 国际化配置
    from flask_babel import Babel
    
    app.config['BABEL_DEFAULT_LOCALE'] = 'zh_CN'
    app.config['BABEL_TRANSLATION_DIRECTORIES'] = 'translations'
    app.config['LANGUAGES'] = {
        'zh_CN': '中文',
        'en_US': 'English',
        'ru_RU': 'Русский'
    }
    
    def get_locale():
        # 1. 优先从URL参数读取
        lang = request.args.get('lang')
        if lang in app.config['LANGUAGES']:
            return lang
        # 2. 从cookie读取
        lang = request.cookies.get('language')
        if lang in app.config['LANGUAGES']:
            return lang
        # 3. 从用户设置读取（如果已登录）
        if session.get('user'):
            lang = session.get('user', {}).get('language')
            if lang in app.config['LANGUAGES']:
                return lang
        # 4. 默认中文
        return 'zh_CN'
    
    babel = Babel(app, locale_selector=get_locale)
    
    # CSRF 保护（安全关键）
    from flask_wtf.csrf import CSRFProtect, generate_csrf, CSRFError
    csrf = CSRFProtect(app)
    
    # 确保模板中可以访问 csrf_token 函数
    @app.context_processor
    def inject_csrf_token():
        return {'csrf_token': generate_csrf}
    
    # 添加 CSRF 错误处理
    @app.errorhandler(CSRFError)
    def handle_csrf_error(e):
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f'[CSRF] CSRF 验证失败: {e.description}, 路径: {request.path}, 方法: {request.method}')
        from flask import jsonify
        # 如果是 API 请求，返回 JSON 错误
        if request.path.startswith('/api/'):
            return jsonify({'success': False, 'message': 'CSRF 验证失败，请刷新页面后重试'}), 400
        # 否则返回 HTML 错误页面
        from flask import render_template
        return render_template('errors/400_csrf.html', error=e), 400
    
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
    import sys
    
    # 确保 logs 目录存在
    os.makedirs('logs', exist_ok=True)
    
    # 文件日志处理器
    file_handler = RotatingFileHandler(
        'logs/app.log', 
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=10,
        encoding='utf-8'  # 支持中文
    )
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    file_handler.setLevel(logging.INFO)
    
    # 控制台日志处理器（用于调试）
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    ))
    console_handler.setLevel(logging.INFO)
    
    # 配置根日志记录器
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    
    # 配置应用日志记录器
    app.logger.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)
    app.logger.addHandler(console_handler)
    app.logger.info('应用启动')
    
    # 配置数据库模块的日志记录器
    db_logger = logging.getLogger('database')
    db_logger.setLevel(logging.INFO)
    db_logger.addHandler(file_handler)
    db_logger.addHandler(console_handler)
    db_logger.propagate = False  # 避免重复记录
    
    # 配置路由模块的日志记录器
    routes_logger = logging.getLogger('routes')
    routes_logger.setLevel(logging.INFO)
    routes_logger.addHandler(file_handler)
    routes_logger.addHandler(console_handler)
    routes_logger.propagate = False
    
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
        from flask_babel import get_locale as babel_get_locale
        return {
            'current_user': session.get('user'),
            'has_permission': has_permission,
            'get_locale': babel_get_locale,
            'available_languages': app.config['LANGUAGES']
        }
    
    # 添加响应头，确保跨网络请求正常工作
    @app.after_request
    def after_request(response):
        # 对于 API 请求，添加必要的响应头
        if request.path.startswith('/api/'):
            # 确保响应完整传输
            if 'Content-Length' not in response.headers:
                response.headers['Content-Length'] = str(len(response.get_data()))
            # 对于 PUT/POST/DELETE 请求，明确关闭连接
            if request.method in ['PUT', 'POST', 'DELETE', 'PATCH']:
                response.headers['Connection'] = 'close'
        return response
    
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
    
    # 安全相关 HTTP 响应头（最佳实践）
    @app.after_request
    def set_security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        # 仅在 HTTPS 场景下启用 HSTS，避免本地开发调试受影响
        if request.is_secure:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        return response

    # 语言切换路由
    @app.route('/debug/language')
    def debug_language():
        """调试语言设置"""
        from flask_babel import get_locale as babel_get_locale
        
        current_locale = str(babel_get_locale())
        url_lang = request.args.get('lang', '无')
        cookie_lang = request.cookies.get('language', '无')
        session_lang = session.get('user', {}).get('language', '无') if session.get('user') else '未登录'
        
        html = f'''
        <html>
        <head>
            <title>语言调试</title>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: Arial; padding: 20px; background: #f5f5f5; }}
                .info {{ background: white; padding: 20px; border-radius: 8px; margin: 10px 0; }}
                table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
                th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
                th {{ background-color: #4CAF50; color: white; }}
                .btn {{ display: inline-block; padding: 10px 20px; margin: 5px; background: #2196F3; color: white; text-decoration: none; border-radius: 4px; }}
                .btn:hover {{ background: #0b7dda; }}
                .clear {{ background: #f44336; }}
                .clear:hover {{ background: #da190b; }}
            </style>
        </head>
        <body>
            <h1>🔍 语言设置调试信息</h1>
            
            <div class="info">
                <h2>当前状态</h2>
                <table>
                    <tr><th>项目</th><th>值</th></tr>
                    <tr><td><strong>当前语言 (Babel)</strong></td><td><strong style="color: red; font-size: 1.2em;">{current_locale}</strong></td></tr>
                    <tr><td>URL参数 (lang)</td><td>{url_lang}</td></tr>
                    <tr><td>Cookie (language)</td><td>{cookie_lang}</td></tr>
                    <tr><td>Session用户语言</td><td>{session_lang}</td></tr>
                    <tr><td>是否登录</td><td>{'是' if session.get('user') else '否'}</td></tr>
                </table>
            </div>
            
            <div class="info">
                <h2>测试操作</h2>
                <a href="/set_language/zh_CN" class="btn">设置为中文 🇨🇳</a>
                <a href="/set_language/en_US" class="btn">设置为英语 🇺🇸</a>
                <a href="/set_language/ru_RU" class="btn">设置为俄语 🇷🇺</a>
                <br><br>
                <a href="/debug/clear_language" class="btn clear">清除Language Cookie</a>
                <a href="/debug/clear_session" class="btn clear">清除Session</a>
                <a href="/debug/language" class="btn">刷新</a>
                <br><br>
                <a href="/" class="btn" style="background: #607D8B;">返回首页</a>
            </div>
            
            <div class="info">
                <h2>优先级说明</h2>
                <ol>
                    <li>URL参数 (lang) - 最高优先级</li>
                    <li>Cookie (language) - 第二优先级</li>
                    <li>Session用户语言 - 第三优先级</li>
                    <li>默认语言 (zh_CN) - 最低优先级</li>
                </ol>
            </div>
        </body>
        </html>
        '''
        return html
    
    @app.route('/debug/clear_language')
    def debug_clear_language():
        """清除语言cookie"""
        from flask import make_response
        response = make_response(redirect('/debug/language'))
        response.set_cookie('language', '', expires=0, path='/')
        return response
    
    @app.route('/debug/clear_session')
    def debug_clear_session():
        """清除session中的语言设置"""
        from flask import make_response
        if session.get('user'):
            session['user'].pop('language', None)
        response = make_response(redirect('/debug/language'))
        return response
    
    @app.route('/set_language/<language>')
    def set_language(language):
        from flask import make_response
        if language not in app.config['LANGUAGES']:
            language = 'zh_CN'
        
        response = make_response(redirect(request.referrer or url_for('index')))
        # 设置cookie，有效期1年，确保路径为根路径
        response.set_cookie('language', language, max_age=365*24*60*60, path='/')
        
        # 如果用户已登录，保存语言偏好到session
        if session.get('user'):
            session['user']['language'] = language
        
        # 调试信息
        print(f'[语言切换] 切换到: {language}')
        print(f'[语言切换] Cookie已设置: language={language}')
        
        return response
    
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
    - Windows: .\start.ps1 -Mode production 或 python -m waitress --listen=0.0.0.0:5000 wsgi:app
    - Linux: gunicorn -c gunicorn_config.py wsgi:app
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
        print("      Windows: .\\start.ps1 -Mode production")
        print("      Linux: gunicorn -c gunicorn_config.py wsgi:app")
        print("=" * 60 + "\n")
        
        # 固定使用5000端口，确保不占用其他应用端口（8000、8203、8206等）
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
        print("      Windows: .\\start.ps1 -Mode production")
        print("      Linux: gunicorn -c gunicorn_config.py wsgi:app")
        print("=" * 60 + "\n")
        
        # 固定使用5000端口，确保不占用其他应用端口（8000、8203、8206等）
        app.run(debug=debug_mode, host='0.0.0.0', port=5000, threaded=True)