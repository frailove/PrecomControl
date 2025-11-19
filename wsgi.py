"""
WSGI入口文件，用于生产环境部署
支持 Gunicorn, Waitress, uWSGI 等 WSGI 服务器
"""
from app import create_app

app = create_app()

if __name__ == '__main__':
    # 开发环境直接运行
    app.run(host='0.0.0.0', port=5000, debug=False)

