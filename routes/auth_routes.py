from flask import Blueprint, render_template, request, redirect, url_for, session, jsonify, flash

from utils.auth_manager import (
    authenticate_user,
    change_password,
    create_role,
    create_user,
    generate_random_password,
    get_all_modules,
    get_all_permissions,
    get_all_roles,
    get_all_users,
    get_audit_logs,
    get_permissions_for_user,
    get_role_modules,
    get_user_by_id,
    get_user_modules,
    record_audit,
    reset_user_password,
    set_role_modules,
    set_user_modules,
    set_user_roles,
    update_profile,
    update_role,
    update_user
)
from utils.auth_decorators import login_required, permission_required, has_permission

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('user') and request.method == 'GET':
        next_url = request.args.get('next') or url_for('system.systems')
        return redirect(next_url)
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        if not username or not password:
            flash('请输入用户名和密码', 'danger')
            return render_template('auth/login.html')
        user, error = authenticate_user(username, password, client_ip=request.remote_addr)
        if error:
            flash(error, 'danger')
            return render_template('auth/login.html', username=username)
        permissions = get_permissions_for_user(user['UserID'], bool(user['IsSuperAdmin']))
        session['user'] = {
            'id': user['UserID'],
            'username': user['Username'],
            'full_name': user.get('FullName'),
            'is_super_admin': bool(user['IsSuperAdmin'])
        }
        session['permissions'] = permissions
        session.permanent = True
        record_audit('LOGIN', '用户登录', session['user'], request)
        next_url = request.args.get('next') or url_for('system.systems')
        return redirect(next_url)
    return render_template('auth/login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    user = session.get('user')
    record_audit('LOGOUT', '用户退出', user, request)
    session.clear()
    return redirect(url_for('auth.login'))


@auth_bp.route('/admin/users')
@login_required
@permission_required('user.view')
def admin_users_page():
    if session.get('user') and not has_permission('user.manage'):
        return redirect(url_for('auth.profile'))
    users = get_all_users()
    roles = get_all_roles()
    permissions = get_all_permissions()
    modules = get_all_modules()
    audit_logs = get_audit_logs(limit=50)
    audit_action_codes = sorted({log['ActionCode'] for log in audit_logs if log.get('ActionCode')})
    return render_template(
        'admin/user_management.html',
        active_page='admin_users',
        users=users,
        roles=roles,
        permissions=permissions,
        modules=modules,
        audit_logs=audit_logs,
        audit_action_codes=audit_action_codes,
        can_manage_users=has_permission('user.manage'),
        can_manage_roles=has_permission('role.manage')
    )


@auth_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    user = session.get('user')
    latest_user = get_user_by_id(user['id'])
    info_success = None
    info_error = None
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip() or None
        email = request.form.get('email', '').strip() or None
        phone = request.form.get('phone', '').strip() or None
        try:
            update_profile(user['id'], full_name, email, phone)
            record_audit('PROFILE_UPDATE', '更新个人信息', user, request)
            session['user']['full_name'] = full_name
            latest_user = get_user_by_id(user['id'])
            info_success = '个人信息已更新'
        except Exception as exc:
            # 安全：避免在错误消息中泄露敏感信息
            error_msg = str(exc)
            if any(keyword in error_msg.lower() for keyword in ['password', 'pwd', 'pass']):
                info_error = '更新失败，请检查输入参数'
            else:
                info_error = error_msg
    return render_template('auth/profile.html', profile=latest_user, active_page='profile', info_success=info_success, info_error=info_error)


@auth_bp.route('/profile/password', methods=['POST'])
@login_required
def change_password_api():
    user = session.get('user')
    data = request.form
    current_password = data.get('current_password') or ''
    new_password = data.get('new_password') or ''
    confirm_password = data.get('confirm_password') or ''
    latest_user = get_user_by_id(user['id'])
    if new_password != confirm_password:
        return render_template('auth/profile.html', error='两次输入的新密码不一致', profile=latest_user, active_page='profile')
    success, err = change_password(user['id'], current_password, new_password)
    if not success:
        return render_template('auth/profile.html', error=err, profile=latest_user, active_page='profile')
    record_audit('PROFILE_RESET_PW', '修改个人密码', user, request)
    return render_template('auth/profile.html', success='密码已更新', profile=latest_user, active_page='profile')


@auth_bp.route('/api/admin/users', methods=['GET'])
@login_required
@permission_required('user.view')
def api_users():
    return jsonify({'success': True, 'data': get_all_users()})


@auth_bp.route('/api/admin/users', methods=['POST'])
@login_required
@permission_required('user.manage')
def api_create_user():
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or generate_random_password()
    full_name = data.get('full_name')
    email = data.get('email')
    phone = data.get('phone')
    is_active = data.get('is_active', True)
    is_super_admin = data.get('is_super_admin', False)
    role_ids = data.get('role_ids') or []
    if not username:
        return jsonify({'success': False, 'message': '用户名不能为空'}), 400
    try:
        user_id = create_user(
            username=username,
            password=password,
            full_name=full_name,
            email=email,
            phone=phone,
            is_active=bool(is_active),
            is_super_admin=bool(is_super_admin),
            created_by=session['user']['username']
        )
        set_user_roles(user_id, role_ids)
        record_audit('USER_CREATE', '创建用户', session['user'], request, 'UserAccount', str(user_id))
        # 安全：只在响应中返回临时密码（仅限管理员创建用户时），不记录到审计日志
        return jsonify({'success': True, 'user_id': user_id, 'temp_password': password})
    except Exception as exc:
        # 安全：异常信息中可能包含敏感信息，只返回通用错误消息
        error_msg = str(exc)
        # 过滤可能包含密码的异常信息
        if any(keyword in error_msg.lower() for keyword in ['password', 'pwd', 'pass']):
            error_msg = '操作失败，请检查输入参数'
        return jsonify({'success': False, 'message': error_msg}), 500


@auth_bp.route('/api/admin/users/<int:user_id>', methods=['PUT'])
@login_required
@permission_required('user.manage')
def api_update_user(user_id):
    import logging
    import traceback
    from flask import jsonify, request as flask_request
    logger = logging.getLogger('routes.auth_routes')
    
    # 记录请求信息
    client_ip = flask_request.remote_addr
    user_agent = flask_request.headers.get('User-Agent', 'Unknown')
    logger.info(f'[API] 收到更新用户 {user_id} 请求，客户端IP: {client_ip}, User-Agent: {user_agent[:50]}')
    
    try:
        data = request.get_json(silent=True) or {}
        logger.info(f'[API] 更新用户 {user_id}: 开始处理请求, 数据: {list(data.keys())}')
        
        # 先更新用户基本信息
        try:
            update_user(
                user_id=user_id,
                full_name=data.get('full_name'),
                email=data.get('email'),
                phone=data.get('phone'),
                is_active=bool(data.get('is_active', True)),
                is_super_admin=bool(data.get('is_super_admin', False)),
                updated_by=session['user']['username']
            )
            logger.info(f'[API] 更新用户 {user_id}: 基本信息更新成功')
        except Exception as e:
            logger.error(f'[API] 更新用户 {user_id} 基本信息失败: {e}')
            logger.error(f'[API] 错误堆栈: {traceback.format_exc()}')
            raise
        
        # 再设置角色
        try:
            set_user_roles(user_id, data.get('role_ids') or [])
            logger.info(f'[API] 更新用户 {user_id}: 角色设置成功')
        except Exception as e:
            logger.error(f'[API] 设置用户 {user_id} 角色失败: {e}')
            logger.error(f'[API] 错误堆栈: {traceback.format_exc()}')
            raise
        
        # 记录审计日志
        try:
            record_audit('USER_UPDATE', '修改用户', session['user'], request, 'UserAccount', str(user_id))
        except Exception as e:
            logger.warning(f'[API] 记录审计日志失败: {e}')
            # 审计日志失败不影响主流程
        
        logger.info(f'[API] 更新用户 {user_id}: 完成，客户端IP: {client_ip}')
        
        # 确保响应正确发送，避免连接重置
        response = jsonify({'success': True})
        response_data = response.get_data()
        response.headers['Connection'] = 'close'  # 明确关闭连接
        response.headers['Content-Length'] = str(len(response_data))
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        logger.info(f'[API] 准备返回响应，大小: {len(response_data)} 字节，客户端IP: {client_ip}')
        return response
        
    except Exception as exc:
        logger.error(f'[API] 更新用户 {user_id} 失败: {exc}')
        logger.error(f'[API] 错误堆栈: {traceback.format_exc()}')
        
        # 安全：异常信息中可能包含敏感信息，只返回通用错误消息
        error_msg = str(exc)
        if any(keyword in error_msg.lower() for keyword in ['password', 'pwd', 'pass']):
            error_msg = '操作失败，请检查输入参数'
        elif '数据库连接失败' in error_msg or 'connection' in error_msg.lower():
            error_msg = '数据库连接失败，请稍后重试'
        elif 'timeout' in error_msg.lower():
            error_msg = '请求超时，请稍后重试'
        
        # 确保返回 JSON 响应，避免连接被重置
        try:
            return jsonify({'success': False, 'message': error_msg}), 500
        except Exception as e:
            logger.error(f'[API] 返回错误响应失败: {e}')
            # 最后的保障：返回简单的文本响应
            from flask import Response
            return Response(
                f'{{"success": false, "message": "{error_msg}"}}',
                status=500,
                mimetype='application/json'
            )


@auth_bp.route('/api/admin/users/<int:user_id>/reset_password', methods=['POST'])
@login_required
@permission_required('user.manage')
def api_reset_password(user_id):
    import logging
    import traceback
    from flask import jsonify, Response
    logger = logging.getLogger('routes.auth_routes')
    
    client_ip = request.remote_addr
    logger.info(f'[API] 收到重置用户 {user_id} 密码请求，客户端IP: {client_ip}')
    
    data = request.get_json(silent=True) or {}
    new_password = data.get('password') or generate_random_password()
    try:
        reset_user_password(user_id, new_password, session['user']['username'])
        record_audit('USER_RESET_PW', '重置用户密码', session['user'], request, 'UserAccount', str(user_id))
        # 安全：只在响应中返回新密码（仅限管理员重置密码时），不记录到审计日志
        response = jsonify({'success': True, 'new_password': new_password})
        response_data = response.get_data()
        response.headers['Connection'] = 'close'
        response.headers['Content-Length'] = str(len(response_data))
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        logger.info(f'[API] 重置用户 {user_id} 密码成功，客户端IP: {client_ip}')
        return response
    except Exception as exc:
        logger.error(f'[API] 重置用户 {user_id} 密码失败: {exc}')
        logger.error(f'[API] 错误堆栈: {traceback.format_exc()}')
        # 安全：异常信息中可能包含敏感信息，只返回通用错误消息
        error_msg = str(exc)
        # 过滤可能包含密码的异常信息
        if any(keyword in error_msg.lower() for keyword in ['password', 'pwd', 'pass']):
            error_msg = '操作失败，请检查输入参数'
        elif '数据库连接失败' in error_msg or 'connection' in error_msg.lower():
            error_msg = '数据库连接失败，请稍后重试'
        elif 'timeout' in error_msg.lower():
            error_msg = '请求超时，请稍后重试'
        
        # 确保返回 JSON 响应，避免连接被重置
        try:
            response = jsonify({'success': False, 'message': error_msg})
            response_data = response.get_data()
            response.headers['Connection'] = 'close'
            response.headers['Content-Length'] = str(len(response_data))
            response.headers['Content-Type'] = 'application/json; charset=utf-8'
            return response, 500
        except Exception as e:
            logger.error(f'[API] 返回错误响应失败: {e}')
            return Response(
                f'{{"success": false, "message": "{error_msg}"}}',
                status=500,
                mimetype='application/json',
                headers={'Connection': 'close', 'Content-Type': 'application/json; charset=utf-8'}
            )


@auth_bp.route('/api/admin/roles', methods=['GET'])
@login_required
@permission_required('role.view')
def api_roles():
    return jsonify({'success': True, 'data': get_all_roles()})


@auth_bp.route('/api/admin/roles', methods=['POST'])
@login_required
@permission_required('role.manage')
def api_create_role():
    data = request.get_json() or {}
    name = (data.get('role_name') or '').strip()
    if not name:
        return jsonify({'success': False, 'message': '角色名称不能为空'}), 400
    try:
        role_id = create_role(
            role_name=name,
            description=data.get('description'),
            permission_codes=data.get('permission_codes') or [],
            created_by=session['user']['username']
        )
        record_audit('ROLE_CREATE', '创建角色', session['user'], request, 'Role', str(role_id))
        return jsonify({'success': True, 'role_id': role_id})
    except Exception as exc:
        error_msg = str(exc)
        if any(keyword in error_msg.lower() for keyword in ['password', 'pwd', 'pass']):
            error_msg = '操作失败，请检查输入参数'
        return jsonify({'success': False, 'message': error_msg}), 500


@auth_bp.route('/api/admin/roles/<int:role_id>', methods=['PUT'])
@login_required
@permission_required('role.manage')
def api_update_role(role_id):
    data = request.get_json() or {}
    try:
        update_role(
            role_id=role_id,
            description=data.get('description'),
            permission_codes=data.get('permission_codes') or [],
            updated_by=session['user']['username']
        )
        record_audit('ROLE_UPDATE', '修改角色', session['user'], request, 'Role', str(role_id))
        return jsonify({'success': True})
    except Exception as exc:
        error_msg = str(exc)
        if any(keyword in error_msg.lower() for keyword in ['password', 'pwd', 'pass']):
            error_msg = '操作失败，请检查输入参数'
        return jsonify({'success': False, 'message': error_msg}), 500


@auth_bp.route('/api/admin/permissions', methods=['GET'])
@login_required
@permission_required('role.view')
def api_permissions():
    return jsonify({'success': True, 'data': get_all_permissions()})


@auth_bp.route('/api/admin/audit_logs', methods=['GET'])
@login_required
@permission_required('audit.view')
def api_audit_logs():
    action_code = request.args.get('action')
    keyword = request.args.get('keyword')
    limit = min(int(request.args.get('limit', 200)), 500)
    logs = get_audit_logs(limit=limit, action_code=action_code or None, keyword=keyword or None)
    return jsonify({'success': True, 'data': logs})


@auth_bp.route('/api/admin/users/<int:user_id>/modules', methods=['GET'])
@login_required
@permission_required('user.view')
def api_get_user_modules(user_id):
    module_ids = get_user_modules(user_id)
    return jsonify({'success': True, 'module_ids': module_ids})


@auth_bp.route('/api/admin/users/<int:user_id>/modules', methods=['PUT'])
@login_required
@permission_required('user.manage')
def api_set_user_modules(user_id):
    import logging
    import traceback
    from flask import jsonify, Response, request as flask_request
    logger = logging.getLogger('routes.auth_routes')
    
    # 记录请求信息
    client_ip = flask_request.remote_addr
    logger.info(f'[API] 收到设置用户 {user_id} 模块权限请求，客户端IP: {client_ip}')
    
    try:
        data = request.get_json() or {}
        module_ids = data.get('module_ids') or []
        logger.info(f'[API] 设置用户 {user_id} 模块权限: {module_ids}')
        
        set_user_modules(user_id, [int(mid) for mid in module_ids])
        logger.info(f'[API] 设置用户 {user_id} 模块权限: 成功')
        
        try:
            record_audit('USER_UPDATE_MODULES', '设置用户模块权限', session['user'], request, 'UserAccount', str(user_id))
        except Exception as e:
            logger.warning(f'[API] 记录审计日志失败: {e}')
            # 审计日志失败不影响主流程
        
        # 确保响应正确发送，避免连接重置
        response = jsonify({'success': True})
        response_data = response.get_data()
        response.headers['Connection'] = 'close'  # 明确关闭连接
        response.headers['Content-Length'] = str(len(response_data))
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        logger.info(f'[API] 准备返回响应，大小: {len(response_data)} 字节，客户端IP: {client_ip}')
        return response
        
    except Exception as exc:
        logger.error(f'[API] 设置用户 {user_id} 模块权限失败: {exc}')
        logger.error(f'[API] 错误堆栈: {traceback.format_exc()}')
        
        error_msg = str(exc)
        if any(keyword in error_msg.lower() for keyword in ['password', 'pwd', 'pass']):
            error_msg = '操作失败，请检查输入参数'
        elif '数据库连接失败' in error_msg or 'connection' in error_msg.lower():
            error_msg = '数据库连接失败，请稍后重试'
        elif 'timeout' in error_msg.lower():
            error_msg = '请求超时，请稍后重试'
        
        # 确保返回 JSON 响应，避免连接被重置
        try:
            response = jsonify({'success': False, 'message': error_msg})
            response_data = response.get_data()
            response.headers['Connection'] = 'close'
            response.headers['Content-Length'] = str(len(response_data))
            response.headers['Content-Type'] = 'application/json; charset=utf-8'
            return response, 500
        except Exception as e:
            logger.error(f'[API] 返回错误响应失败: {e}')
            # 最后的保障：返回简单的文本响应
            return Response(
                f'{{"success": false, "message": "{error_msg}"}}',
                status=500,
                mimetype='application/json',
                headers={'Connection': 'close', 'Content-Type': 'application/json; charset=utf-8'}
            )


@auth_bp.route('/api/admin/roles/<int:role_id>/modules', methods=['GET'])
@login_required
@permission_required('role.view')
def api_get_role_modules(role_id):
    module_ids = get_role_modules(role_id)
    return jsonify({'success': True, 'module_ids': module_ids})


@auth_bp.route('/api/admin/roles/<int:role_id>/modules', methods=['PUT'])
@login_required
@permission_required('role.manage')
def api_set_role_modules(role_id):
    data = request.get_json() or {}
    module_ids = data.get('module_ids') or []
    try:
        set_role_modules(role_id, [int(mid) for mid in module_ids])
        record_audit('ROLE_UPDATE_MODULES', '设置角色模块权限', session['user'], request, 'Role', str(role_id))
        return jsonify({'success': True})
    except Exception as exc:
        error_msg = str(exc)
        if any(keyword in error_msg.lower() for keyword in ['password', 'pwd', 'pass']):
            error_msg = '操作失败，请检查输入参数'
        return jsonify({'success': False, 'message': error_msg}), 500


@auth_bp.route('/api/admin/modules', methods=['GET'])
@login_required
@permission_required('user.view')
def api_modules():
    return jsonify({'success': True, 'data': get_all_modules()})


@auth_bp.app_context_processor
def inject_helpers():
    return {
        'has_permission': has_permission
    }


