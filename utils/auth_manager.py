import json
import secrets
import string
from datetime import datetime, timedelta
from typing import List, Optional

from werkzeug.security import generate_password_hash, check_password_hash

from database import create_connection, ensure_user_management_tables

MAX_FAILED_ATTEMPTS = 5
LOCK_DURATION_MINUTES = 15
SENSITIVE_PAYLOAD_KEYS = {
    'password',
    'pwd',
    'pass',
    'new_password',
    'newpassword',
    'confirm_password',
    'confirmpassword',
    'old_password',
    'oldpassword',
    'token',
    'access_token',
    'refresh_token',
    'api_key',
    'apikey'
}
SENSITIVE_PAYLOAD_KEYS = {k.lower() for k in SENSITIVE_PAYLOAD_KEYS}

DEFAULT_PERMISSIONS = [
    {
        'code': 'user.view',
        'module': 'User',
        'name': '查看用户',
        'description': '查看系统用户清单'
    },
    {
        'code': 'user.manage',
        'module': 'User',
        'name': '管理用户',
        'description': '新增、编辑、重置用户'
    },
    {
        'code': 'role.view',
        'module': 'Role',
        'name': '查看角色',
        'description': '查看角色与权限'
    },
    {
        'code': 'role.manage',
        'module': 'Role',
        'name': '管理角色',
        'description': '创建、编辑角色及权限'
    },
    {
        'code': 'audit.view',
        'module': 'Audit',
        'name': '查看日志',
        'description': '查看关键操作日志'
    }
]

DEFAULT_ROLES = [
    {
        'name': '系统管理员',
        'description': '拥有全部系统权限，可配置用户/角色/日志',
        'is_system': 1,
        'permissions': [perm['code'] for perm in DEFAULT_PERMISSIONS]
    },
    {
        'name': '审阅者',
        'description': '可查看用户、角色、操作日志',
        'is_system': 1,
        'permissions': ['user.view', 'role.view', 'audit.view']
    }
]

DEFAULT_ADMIN = {
    'username': 'admin',
    'full_name': '系统管理员',
    'password': 'Admin@123',
    'email': None,
    'phone': None,
    'is_super_admin': True
}


def generate_random_password(length: int = 12) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*?"
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def bootstrap_user_management():
    """确保权限/角色/默认管理员存在"""
    ensure_user_management_tables()
    conn = create_connection()
    if not conn:
        return False
    try:
        cur = conn.cursor(dictionary=True)
        # 权限
        for perm in DEFAULT_PERMISSIONS:
            cur.execute(
                """
                INSERT INTO Permission (PermissionCode, ModuleName, DisplayName, Description)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    ModuleName = VALUES(ModuleName),
                    DisplayName = VALUES(DisplayName),
                    Description = VALUES(Description)
                """,
                (perm['code'], perm['module'], perm['name'], perm['description'])
            )

        # 角色及权限
        for role in DEFAULT_ROLES:
            cur.execute("SELECT RoleID FROM Role WHERE RoleName = %s", (role['name'],))
            row = cur.fetchone()
            if row:
                role_id = row['RoleID']
            else:
                cur.execute(
                    """
                    INSERT INTO Role (RoleName, Description, IsSystemRole, CreatedBy)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (role['name'], role['description'], role['is_system'], 'system')
                )
                role_id = cur.lastrowid
            # 角色权限
            cur.execute("DELETE FROM RolePermission WHERE RoleID = %s", (role_id,))
            if role['permissions']:
                cur.execute(
                    "SELECT PermissionID, PermissionCode FROM Permission"
                )
                perm_map = {p['PermissionCode']: p['PermissionID'] for p in cur.fetchall()}
                values = [
                    (role_id, perm_map[code])
                    for code in role['permissions']
                    if code in perm_map
                ]
                if values:
                    cur.executemany(
                        "INSERT INTO RolePermission (RoleID, PermissionID) VALUES (%s, %s)",
                        values
                    )

        # 默认管理员
        cur.execute("SELECT UserID FROM UserAccount WHERE Username = %s", (DEFAULT_ADMIN['username'],))
        row = cur.fetchone()
        if not row:
            cur.execute(
                """
                INSERT INTO UserAccount
                (Username, FullName, Email, Phone, PasswordHash, IsActive, IsSuperAdmin, CreatedBy)
                VALUES (%s, %s, %s, %s, %s, 1, %s, %s)
                """,
                (
                    DEFAULT_ADMIN['username'],
                    DEFAULT_ADMIN['full_name'],
                    DEFAULT_ADMIN['email'],
                    DEFAULT_ADMIN['phone'],
                    generate_password_hash(DEFAULT_ADMIN['password']),
                    1 if DEFAULT_ADMIN['is_super_admin'] else 0,
                    'system'
                )
            )
            admin_user_id = cur.lastrowid
            # 赋予系统管理员角色
            cur.execute("SELECT RoleID FROM Role WHERE RoleName = %s", ('系统管理员',))
            role_row = cur.fetchone()
            if role_row:
                cur.execute(
                    "INSERT INTO UserRole (UserID, RoleID) VALUES (%s, %s)",
                    (admin_user_id, role_row['RoleID'])
                )
        conn.commit()
        # 在角色和用户创建后初始化模块权限
        bootstrap_module_permissions()
        return True
    finally:
        conn.close()


def get_user_by_username(username: str):
    conn = create_connection()
    if not conn:
        return None
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM UserAccount WHERE Username = %s", (username,))
        return cur.fetchone()
    finally:
        conn.close()


def get_user_by_id(user_id: int):
    conn = create_connection()
    if not conn:
        return None
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM UserAccount WHERE UserID = %s", (user_id,))
        return cur.fetchone()
    finally:
        conn.close()


def authenticate_user(username: str, password: str, client_ip: Optional[str] = None):
    conn = create_connection()
    if not conn:
        return None, '数据库连接失败'
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM UserAccount WHERE Username = %s", (username,))
        user = cur.fetchone()
        if not user:

            return None, '账号或密码错误'
        if not user['IsActive']:
            return None, '账号已被禁用'
        locked_until = user.get('LockedUntil')
        if locked_until and locked_until > datetime.utcnow():
            remain = int((locked_until - datetime.utcnow()).total_seconds() // 60) + 1
            return None, f'账号已锁定，请 {remain} 分钟后重试'
        if not check_password_hash(user['PasswordHash'], password):
            failed = (user['FailedLoginAttempts'] or 0) + 1
            lock_until = None
            if failed >= MAX_FAILED_ATTEMPTS:
                lock_until = datetime.utcnow() + timedelta(minutes=LOCK_DURATION_MINUTES)
                failed = 0
            cur.execute(
                """
                UPDATE UserAccount
                SET FailedLoginAttempts = %s, LockedUntil = %s
                WHERE UserID = %s
                """,
                (failed, lock_until, user['UserID'])
            )
            conn.commit()
            return None, '账号或密码错误'
        cur.execute(
            """
            UPDATE UserAccount
            SET FailedLoginAttempts = 0,
                LockedUntil = NULL,
                LastLoginAt = %s,
                LastLoginIP = %s
            WHERE UserID = %s
            """,
            (datetime.utcnow(), client_ip, user['UserID'])
        )
        conn.commit()
        return user, None
    finally:
        conn.close()


def get_permissions_for_user(user_id: int, is_super_admin: bool = False) -> List[str]:
    if is_super_admin:
        conn = create_connection()
        if not conn:
            return []
        try:
            cur = conn.cursor()
            cur.execute("SELECT PermissionCode FROM Permission")
            return [row[0] for row in cur.fetchall()]
        finally:
            conn.close()
    conn = create_connection()
    if not conn:
        return []
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT DISTINCT p.PermissionCode
            FROM UserRole ur
            JOIN RolePermission rp ON ur.RoleID = rp.RoleID
            JOIN Permission p ON rp.PermissionID = p.PermissionID
            WHERE ur.UserID = %s
            """,
            (user_id,)
        )
        return [row[0] for row in cur.fetchall()]
    finally:
        conn.close()


def get_all_users():
    conn = create_connection()
    if not conn:
        return []
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT
                u.UserID,
                u.Username,
                u.FullName,
                u.Email,
                u.Phone,
                u.IsActive,
                u.IsSuperAdmin,
                u.LastLoginAt,
                GROUP_CONCAT(r.RoleName ORDER BY r.RoleName SEPARATOR ', ') AS RoleNames,
                GROUP_CONCAT(r.RoleID ORDER BY r.RoleID SEPARATOR ',') AS RoleIDs
            FROM UserAccount u
            LEFT JOIN UserRole ur ON u.UserID = ur.UserID
            LEFT JOIN Role r ON ur.RoleID = r.RoleID
            GROUP BY u.UserID
            ORDER BY u.IsSuperAdmin DESC, u.Username
            """
        )
        rows = cur.fetchall()
        for row in rows:
            if row['RoleIDs']:
                row['RoleIDs'] = [int(rid) for rid in row['RoleIDs'].split(',') if rid]
            else:
                row['RoleIDs'] = []
            if row['LastLoginAt']:
                row['LastLoginAt'] = row['LastLoginAt'].strftime('%Y-%m-%d %H:%M')
        return rows
    finally:
        conn.close()


def get_all_roles():
    conn = create_connection()
    if not conn:
        return []
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT
                r.RoleID,
                r.RoleName,
                r.Description,
                r.IsSystemRole,
                GROUP_CONCAT(p.PermissionCode ORDER BY p.PermissionCode) AS PermissionCodes
            FROM Role r
            LEFT JOIN RolePermission rp ON r.RoleID = rp.RoleID
            LEFT JOIN Permission p ON rp.PermissionID = p.PermissionID
            GROUP BY r.RoleID
            ORDER BY r.RoleName
            """
        )
        roles = cur.fetchall()
        for role in roles:
            if role['PermissionCodes']:
                role['PermissionCodes'] = role['PermissionCodes'].split(',')
            else:
                role['PermissionCodes'] = []
        return roles
    finally:
        conn.close()


def get_all_permissions():
    conn = create_connection()
    if not conn:
        return []
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT PermissionID, PermissionCode, ModuleName, DisplayName, Description FROM Permission ORDER BY ModuleName, PermissionCode"
        )
        return cur.fetchall()
    finally:
        conn.close()


def create_user(username: str, password: str, full_name: Optional[str], email: Optional[str],
                phone: Optional[str], is_active: bool, is_super_admin: bool, created_by: str) -> int:
    conn = create_connection()
    if not conn:
        raise RuntimeError("数据库连接失败")
    try:
        ok, msg = validate_password_strength(password)
        if not ok:
            raise ValueError(msg)

        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO UserAccount
            (Username, FullName, Email, Phone, PasswordHash, IsActive, IsSuperAdmin, CreatedBy)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                username,
                full_name,
                email,
                phone,
                generate_password_hash(password),
                1 if is_active else 0,
                1 if is_super_admin else 0,
                created_by
            )
        )
        user_id = cur.lastrowid
        conn.commit()
        return user_id
    finally:
        conn.close()


def update_user(user_id: int, full_name: Optional[str], email: Optional[str], phone: Optional[str],
                is_active: bool, is_super_admin: bool, updated_by: str):
    conn = create_connection()
    if not conn:
        raise RuntimeError("数据库连接失败")
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE UserAccount
            SET FullName = %s,
                Email = %s,
                Phone = %s,
                IsActive = %s,
                IsSuperAdmin = %s,
                UpdatedBy = %s,
                UpdatedAt = %s
            WHERE UserID = %s
            """,
            (
                full_name,
                email,
                phone,
                1 if is_active else 0,
                1 if is_super_admin else 0,
                updated_by,
                datetime.utcnow(),
                user_id
            )
        )
        conn.commit()
    finally:
        conn.close()


def update_profile(user_id: int, full_name: Optional[str], email: Optional[str], phone: Optional[str]):
    conn = create_connection()
    if not conn:
        raise RuntimeError("数据库连接失败")
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE UserAccount
            SET FullName = %s,
                Email = %s,
                Phone = %s,
                UpdatedAt = %s
            WHERE UserID = %s
            """,
            (full_name, email, phone, datetime.utcnow(), user_id)
        )
        conn.commit()
    finally:
        conn.close()


def validate_password_strength(password: str) -> tuple[bool, str]:
    """验证密码强度，返回 (是否通过, 错误消息)"""
    if len(password or '') < 12:
        return False, "密码长度至少 12 位"

    has_upper = any(c.isupper() for c in password)
    has_lower = any(c.islower() for c in password)
    has_digit = any(c.isdigit() for c in password)
    has_special = any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?/" for c in password)

    if not (has_upper and has_lower and has_digit and has_special):
        return False, "密码必须包含大小写字母、数字和特殊字符"

    weak_passwords = {
        "Password123!",
        "Admin@123",
        "Qwer1234!",
        "Test1234!",
    }
    if password in weak_passwords:
        return False, "密码过于简单，请使用更复杂的密码"

    return True, ""


def change_password(user_id: int, current_password: str, new_password: str):
    conn = create_connection()
    if not conn:
        raise RuntimeError("数据库连接失败")
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT PasswordHash FROM UserAccount WHERE UserID = %s", (user_id,))
        row = cur.fetchone()
        if not row or not check_password_hash(row['PasswordHash'], current_password):
            return False, '当前密码不正确'

        ok, msg = validate_password_strength(new_password)
        if not ok:
            return False, msg
        cur.execute(
            """
            UPDATE UserAccount
            SET PasswordHash = %s,
                UpdatedAt = %s
            WHERE UserID = %s
            """,
            (generate_password_hash(new_password), datetime.utcnow(), user_id)
        )
        conn.commit()
        return True, None
    finally:
        conn.close()


def set_user_roles(user_id: int, role_ids: List[int]):
    conn = create_connection()
    if not conn:
        raise RuntimeError("数据库连接失败")
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM UserRole WHERE UserID = %s", (user_id,))
        values = [(user_id, rid) for rid in role_ids]
        if values:
            cur.executemany(
                "INSERT INTO UserRole (UserID, RoleID) VALUES (%s, %s)",
                values
            )
        conn.commit()
    finally:
        conn.close()


def reset_user_password(user_id: int, new_password: str, updated_by: str):
    conn = create_connection()
    if not conn:
        raise RuntimeError("数据库连接失败")
    try:
        ok, msg = validate_password_strength(new_password)
        if not ok:
            raise ValueError(msg)

        cur = conn.cursor()
        cur.execute(
            """
            UPDATE UserAccount
            SET PasswordHash = %s,
                UpdatedBy = %s,
                UpdatedAt = %s
            WHERE UserID = %s
            """,
            (generate_password_hash(new_password), updated_by, datetime.utcnow(), user_id)
        )
        conn.commit()
    finally:
        conn.close()


def create_role(role_name: str, description: Optional[str], permission_codes: List[str], created_by: str) -> int:
    conn = create_connection()
    if not conn:
        raise RuntimeError("数据库连接失败")
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "INSERT INTO Role (RoleName, Description, IsSystemRole, CreatedBy) VALUES (%s, %s, 0, %s)",
            (role_name, description, created_by)
        )
        role_id = cur.lastrowid
        _set_role_permissions(cur, role_id, permission_codes)
        conn.commit()
        return role_id
    finally:
        conn.close()


def update_role(role_id: int, description: Optional[str], permission_codes: List[str], updated_by: str):
    conn = create_connection()
    if not conn:
        raise RuntimeError("数据库连接失败")
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            UPDATE Role
            SET Description = %s,
                UpdatedBy = %s,
                UpdatedAt = %s
            WHERE RoleID = %s
            """,
            (description, updated_by, datetime.utcnow(), role_id)
        )
        _set_role_permissions(cur, role_id, permission_codes)
        conn.commit()
    finally:
        conn.close()


def _set_role_permissions(cur, role_id: int, permission_codes: List[str]):
    cur.execute("DELETE FROM RolePermission WHERE RoleID = %s", (role_id,))
    if not permission_codes:
        return
    cur.execute("SELECT PermissionID, PermissionCode FROM Permission")
    perm_map = {row['PermissionCode']: row['PermissionID'] for row in cur.fetchall()}
    values = [
        (role_id, perm_map[code])
        for code in permission_codes
        if code in perm_map
    ]
    if values:
        cur.executemany(
            "INSERT INTO RolePermission (RoleID, PermissionID) VALUES (%s, %s)",
            values
        )


def _sanitize_payload(data):
    """移除/掩码敏感字段，防止在审计日志中泄露密码等信息。"""
    if data is None:
        return None

    if isinstance(data, dict):
        sanitized = {}
        for key, value in data.items():
            if key is None:
                sanitized[key] = _sanitize_payload(value)
                continue
            if key.lower() in SENSITIVE_PAYLOAD_KEYS:
                sanitized[key] = '***'
            else:
                sanitized[key] = _sanitize_payload(value)
        return sanitized

    if isinstance(data, list):
        return [_sanitize_payload(item) for item in data]

    # 其他类型（字符串/数字等）原样返回
    return data


def record_audit(action_code: str, action_name: str, user: Optional[dict], request=None,
                 target_type: Optional[str] = None, target_id: Optional[str] = None,
                 remark: Optional[str] = None):
    conn = create_connection()
    if not conn:
        return
    try:
        cur = conn.cursor()
        payload = None
        if request:
            payload_obj = None
            if request.is_json:
                try:
                    payload_obj = request.get_json(silent=True)
                except Exception:
                    payload_obj = None
            elif request.form:
                payload_obj = request.form.to_dict(flat=True)

            if payload_obj is not None:
                try:
                    sanitized = _sanitize_payload(payload_obj)
                    payload = json.dumps(sanitized, ensure_ascii=False)
                except Exception:
                    payload = None
        cur.execute(
            """
            INSERT INTO AuditLog
            (UserID, UsernameSnapshot, ActionCode, ActionName, TargetType, TargetID,
             RequestMethod, RequestPath, RequestPayload, ClientIP, UserAgent, Remark)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                user.get('id') if user else None,
                user.get('username') if user else None,
                action_code,
                action_name,
                target_type,
                target_id,
                request.method if request else None,
                request.path if request else None,
                payload,
                request.remote_addr if request else None,
                request.user_agent.string if request and request.user_agent else None,
                remark
            )
        )
        conn.commit()
    finally:
        conn.close()


def get_audit_logs(limit: int = 200, action_code: Optional[str] = None, keyword: Optional[str] = None):
    conn = create_connection()
    if not conn:
        return []
    try:
        cur = conn.cursor(dictionary=True)
        query = """
            SELECT
                a.AuditID,
                a.ActionCode,
                a.ActionName,
                a.TargetType,
                a.TargetID,
                a.RequestMethod,
                a.RequestPath,
                a.ClientIP,
                a.UsernameSnapshot,
                a.CreatedAt,
                a.Remark
            FROM AuditLog a
        """
        clauses = []
        params = []
        if action_code:
            clauses.append("a.ActionCode = %s")
            params.append(action_code)
        if keyword:
            clauses.append("(a.UsernameSnapshot LIKE %s OR a.ActionName LIKE %s OR a.TargetID LIKE %s)")
            like = f"%{keyword}%"
            params.extend([like, like, like])
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY a.AuditID DESC LIMIT %s"
        params.append(limit)
        cur.execute(query, tuple(params))
        rows = cur.fetchall()
        for row in rows:
            if row['CreatedAt']:
                row['CreatedAt'] = row['CreatedAt'].strftime('%Y-%m-%d %H:%M:%S')
        return rows
    finally:
        conn.close()


def get_user_accessible_modules(user_id: int, is_super_admin: bool = False) -> List[str]:
    """获取用户可访问的模块代码列表"""
    if is_super_admin:
        conn = create_connection()
        if not conn:
            return []
        try:
            cur = conn.cursor()
            cur.execute("SELECT ModuleCode FROM ModulePermission WHERE IsActive = 1 ORDER BY DisplayOrder")
            return [row[0] for row in cur.fetchall()]
        finally:
            conn.close()
    
    conn = create_connection()
    if not conn:
        return []
    try:
        cur = conn.cursor()
        # 从用户直接权限和角色权限中获取
        cur.execute("""
            SELECT DISTINCT m.ModuleCode, m.DisplayOrder
            FROM ModulePermission m
            WHERE m.IsActive = 1
              AND (
                  EXISTS (
                      SELECT 1 FROM UserModulePermission ump
                      WHERE ump.UserID = %s AND ump.ModuleID = m.ModuleID
                  )
                  OR EXISTS (
                      SELECT 1 FROM UserRole ur
                      JOIN RoleModulePermission rmp ON ur.RoleID = rmp.RoleID
                      WHERE ur.UserID = %s AND rmp.ModuleID = m.ModuleID
                  )
              )
            ORDER BY m.DisplayOrder
        """, (user_id, user_id))
        return [row[0] for row in cur.fetchall()]
    finally:
        conn.close()


def get_all_modules():
    """获取所有模块"""
    conn = create_connection()
    if not conn:
        return []
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT ModuleID, ModuleCode, ModuleName, DisplayName, Description, 
                   IconClass, RoutePath, DisplayOrder, IsActive
            FROM ModulePermission
            ORDER BY DisplayOrder, ModuleName
        """)
        return cur.fetchall()
    finally:
        conn.close()


def get_user_modules(user_id: int):
    """获取用户拥有的模块ID列表"""
    conn = create_connection()
    if not conn:
        return []
    try:
        cur = conn.cursor()
        cur.execute("SELECT ModuleID FROM UserModulePermission WHERE UserID = %s", (user_id,))
        return [row[0] for row in cur.fetchall()]
    finally:
        conn.close()


def get_role_modules(role_id: int):
    """获取角色拥有的模块ID列表"""
    conn = create_connection()
    if not conn:
        return []
    try:
        cur = conn.cursor()
        cur.execute("SELECT ModuleID FROM RoleModulePermission WHERE RoleID = %s", (role_id,))
        return [row[0] for row in cur.fetchall()]
    finally:
        conn.close()


def set_user_modules(user_id: int, module_ids: List[int]):
    """设置用户的模块权限"""
    conn = create_connection()
    if not conn:
        raise RuntimeError("数据库连接失败")
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM UserModulePermission WHERE UserID = %s", (user_id,))
        values = [(user_id, mid) for mid in module_ids]
        if values:
            cur.executemany(
                "INSERT INTO UserModulePermission (UserID, ModuleID) VALUES (%s, %s)",
                values
            )
        conn.commit()
    finally:
        conn.close()


def set_role_modules(role_id: int, module_ids: List[int]):
    """设置角色的模块权限"""
    conn = create_connection()
    if not conn:
        raise RuntimeError("数据库连接失败")
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM RoleModulePermission WHERE RoleID = %s", (role_id,))
        values = [(role_id, mid) for mid in module_ids]
        if values:
            cur.executemany(
                "INSERT INTO RoleModulePermission (RoleID, ModuleID) VALUES (%s, %s)",
                values
            )
        conn.commit()
    finally:
        conn.close()


def bootstrap_module_permissions():
    """初始化默认模块权限"""
    conn = create_connection()
    if not conn:
        return False
    try:
        cur = conn.cursor(dictionary=True)
        modules = [
            {'code': 'systems', 'name': '系统管理', 'display': '系统管理', 'desc': '管理工艺和非工艺系统基本信息', 
             'icon': 'bi-diagram-3-fill', 'route': '/systems', 'order': 1},
            {'code': 'subsystems', 'name': '子系统管理', 'display': '子系统管理', 'desc': '管理子系统信息和配置',
             'icon': 'bi-bezier2', 'route': '/subsystems', 'order': 2},
            {'code': 'test_packages', 'name': '试压包管理', 'display': '试压包管理', 'desc': '管理试压包、焊口、检测数据',
             'icon': 'bi-box-seam-fill', 'route': '/test_packages', 'order': 3},
            {'code': 'backup', 'name': '备份管理', 'display': '备份管理', 'desc': '数据备份、同步和恢复',
             'icon': 'bi-database-fill', 'route': '/backup', 'order': 4},
            {'code': 'precom_manhole', 'name': '人孔检查', 'display': '人孔检查', 'desc': '按设备/子系统管理人孔开启与复位检查任务',
             'icon': 'bi-door-open', 'route': '/precom/manhole', 'order': 5},
            {'code': 'precom_motor_solo', 'name': '电机单试', 'display': '电机单试', 'desc': '电机 Solo Run 计划、执行与记录管理',
             'icon': 'bi-lightning-charge-fill', 'route': '/precom/motor_solo', 'order': 6},
            {'code': 'precom_skid_install', 'name': '台件安装', 'display': '台件安装', 'desc': '仪表台件清单与安装完成情况追踪',
             'icon': 'bi-hdd-network', 'route': '/precom/skid_install', 'order': 7},
            {'code': 'precom_loop_test', 'name': '回路测试', 'display': '回路测试', 'desc': '回路点位测试计划、执行与结果记录',
             'icon': 'bi-activity', 'route': '/precom/loop_test', 'order': 8},
            {'code': 'precom_alignment', 'name': '最终对中', 'display': '最终对中', 'desc': '动设备最终对中任务与记录管理',
             'icon': 'bi-arrow-repeat', 'route': '/precom/alignment', 'order': 9},
            {'code': 'precom_mrt', 'name': 'MRT 联动测试', 'display': 'MRT 联动测试', 'desc': '机械联动测试计划与执行情况跟踪',
             'icon': 'bi-diagram-3', 'route': '/precom/mrt', 'order': 10},
            {'code': 'precom_function_test', 'name': 'Function Test', 'display': 'Function Test', 'desc': '功能测试任务及尾项管理',
             'icon': 'bi-check2-square', 'route': '/precom/function_test', 'order': 11},
        ]
        
        for module in modules:
            cur.execute("""
                INSERT INTO ModulePermission (ModuleCode, ModuleName, DisplayName, Description, IconClass, RoutePath, DisplayOrder)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    ModuleName = VALUES(ModuleName),
                    DisplayName = VALUES(DisplayName),
                    Description = VALUES(Description),
                    IconClass = VALUES(IconClass),
                    RoutePath = VALUES(RoutePath),
                    DisplayOrder = VALUES(DisplayOrder),
                    IsActive = 1
            """, (
                module['code'], module['name'], module['display'], module['desc'],
                module['icon'], module['route'], module['order']
            ))
        
        # 给系统管理员角色分配所有模块权限
        cur.execute("SELECT RoleID FROM Role WHERE RoleName = %s", ('系统管理员',))
        admin_role = cur.fetchone()
        if admin_role:
            admin_role_id = admin_role['RoleID']
            cur.execute("SELECT ModuleID FROM ModulePermission")
            all_module_ids = [row['ModuleID'] for row in cur.fetchall()]
            if all_module_ids:
                cur.execute("DELETE FROM RoleModulePermission WHERE RoleID = %s", (admin_role_id,))
                values = [(admin_role_id, mid) for mid in all_module_ids]
                cur.executemany(
                    "INSERT INTO RoleModulePermission (RoleID, ModuleID) VALUES (%s, %s)",
                    values
                )
        
        conn.commit()
        return True
    finally:
        conn.close()


