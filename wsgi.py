"""
WSGI入口文件，用于生产环境部署
支持 Gunicorn, Waitress, uWSGI 等 WSGI 服务器

端口配置：固定使用5000端口，不占用其他端口（8000、8203、8206等）
"""
from app import create_app

app = create_app()

if __name__ == '__main__':
    # 开发环境直接运行
    # 启用线程模式以支持并发请求，特别是跨网络请求
    # 固定使用5000端口，确保不占用其他应用端口
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)

