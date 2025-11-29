"""
WSGI入口文件，用于生产环境部署
支持 Gunicorn, Waitress, uWSGI 等 WSGI 服务器
"""
from app import create_app

app = create_app()

if __name__ == '__main__':
    # 开发环境直接运行
    # 启用线程模式以支持并发请求，特别是跨网络请求
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)

