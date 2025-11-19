from functools import wraps

from flask import session, redirect, url_for, request, abort, g, jsonify


def current_user():
    return session.get('user')


def has_permission(code: str) -> bool:
    user = session.get('user')
    if not user:
        return False
    if user.get('is_super_admin'):
        return True
    permissions = session.get('permissions') or []
    return code in permissions


def login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not session.get('user'):
            return redirect(url_for('auth.login', next=request.path))
        g.current_user = session.get('user')
        return func(*args, **kwargs)
    return wrapper


def _expects_json():
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return True
    if request.path.startswith('/api/'):
        return True
    if request.is_json:
        return True
    accept = request.accept_mimetypes
    return accept['application/json'] >= accept['text/html']


def permission_required(code):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not session.get('user'):
                if _expects_json():
                    return jsonify({'success': False, 'message': '未登录'}), 401
                return redirect(url_for('auth.login', next=request.path))
            if not has_permission(code):
                if _expects_json():
                    return jsonify({'success': False, 'message': '权限不足'}), 403
                abort(403)
            return func(*args, **kwargs)
        return wrapper
    return decorator


def has_module_access(module_code: str) -> bool:
    """检查用户是否有访问指定模块的权限"""
    user = session.get('user')
    if not user:
        return False
    if user.get('is_super_admin'):
        return True
    from utils.auth_manager import get_user_accessible_modules
    accessible_modules = get_user_accessible_modules(user['id'], False)
    return module_code in accessible_modules


def get_module_code_by_path(path: str) -> str:
    """根据URL路径获取对应的模块代码"""
    # 跳过API路由和静态资源
    if path.startswith('/api/') or path.startswith('/static/'):
        return None
    
    # URL路径到模块代码的映射
    path_module_map = {
        '/systems': 'systems',
        '/subsystems': 'subsystems',
        '/test_packages': 'test_packages',
        '/backup': 'backup',
        '/precom/manhole': 'precom_manhole',
        '/precom/motor_solo': 'precom_motor_solo',
        '/precom/skid_install': 'precom_skid_install',
        '/precom/loop_test': 'precom_loop_test',
        '/precom/alignment': 'precom_alignment',
        '/precom/mrt': 'precom_mrt',
        '/precom/function_test': 'precom_function_test',
    }
    
    # 精确匹配
    if path in path_module_map:
        return path_module_map[path]
    
    # 前缀匹配（用于子路由，如 /test_packages/edit/xxx）
    for route_path, module_code in path_module_map.items():
        if path.startswith(route_path + '/') or path == route_path:
            return module_code
    
    # 预试车任务的其他路由（如编辑、API等）
    if path.startswith('/precom/'):
        # 尝试从路径中提取任务类型
        parts = path.split('/')
        if len(parts) >= 3:
            task_type = parts[2]
            task_type_map = {
                'manhole': 'precom_manhole',
                'motor_solo': 'precom_motor_solo',
                'skid_install': 'precom_skid_install',
                'loop_test': 'precom_loop_test',
                'alignment': 'precom_alignment',
                'mrt': 'precom_mrt',
                'function_test': 'precom_function_test',
                'tasks': None,  # /precom/tasks 需要根据查询参数或数据库判断
            }
            if task_type in task_type_map:
                if task_type_map[task_type] is None:
                    # /precom/tasks 相关路由，需要从查询参数或数据库获取task_type
                    from flask import request
                    # 先尝试从查询参数获取
                    task_type_param = request.args.get('task_type', '').strip()
                    if not task_type_param and request.method == 'POST':
                        # POST请求尝试从表单获取
                        task_type_param = request.form.get('TaskType', '').strip()
                    
                    if task_type_param:
                        task_type_param_map = {
                            'Manhole': 'precom_manhole',
                            'MotorSolo': 'precom_motor_solo',
                            'SkidInstall': 'precom_skid_install',
                            'LoopTest': 'precom_loop_test',
                            'Alignment': 'precom_alignment',
                            'MRT': 'precom_mrt',
                            'FunctionTest': 'precom_function_test',
                        }
                        module_code = task_type_param_map.get(task_type_param)
                        if module_code:
                            return module_code
                    
                    # 如果路径包含task_id，尝试从数据库获取
                    if '/tasks/' in path and len(parts) >= 4:
                        try:
                            task_id = int(parts[3])
                            from database import create_connection
                            conn = create_connection()
                            if conn:
                                try:
                                    cur = conn.cursor(dictionary=True)
                                    cur.execute(
                                        "SELECT TaskType FROM PrecomTask WHERE TaskID = %s",
                                        (task_id,)
                                    )
                                    row = cur.fetchone()
                                    if row and row.get('TaskType'):
                                        task_type_from_db = row['TaskType']
                                        task_type_param_map = {
                                            'Manhole': 'precom_manhole',
                                            'MotorSolo': 'precom_motor_solo',
                                            'SkidInstall': 'precom_skid_install',
                                            'LoopTest': 'precom_loop_test',
                                            'Alignment': 'precom_alignment',
                                            'MRT': 'precom_mrt',
                                            'FunctionTest': 'precom_function_test',
                                        }
                                        return task_type_param_map.get(task_type_from_db)
                                finally:
                                    conn.close()
                        except (ValueError, IndexError):
                            pass
                    
                    # 如果无法确定，返回None（不进行权限检查，由具体路由处理）
                    return None
                else:
                    return task_type_map[task_type]
    
    return None


