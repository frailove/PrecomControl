# 网络安全审查报告

> PrecomControl 系统安全审计清单 - 针对网络安全审查要求

## 🔴 严重安全问题（必须修复）

### 1. 硬编码敏感信息

**问题**：`config.py` 中硬编码了数据库密码

```python
# config.py:6
'password': 'Gcc$873209',  # ❌ 硬编码密码
```

**风险**：
- 代码泄露会导致数据库被直接访问
- Git 历史中可能永久保存密码
- 违反安全最佳实践

**修复方案**：
- ✅ 已支持环境变量（`DB_PASSWORD`），但需要确保生产环境使用
- 从代码中完全移除硬编码密码
- 使用密钥管理服务（如 Windows Credential Manager、Azure Key Vault）

**优先级**：🔴 **P0 - 立即修复**

---

### 2. 缺少 CSRF 保护

**问题**：所有表单和 API 端点都没有 CSRF Token 验证

**风险**：
- 攻击者可以伪造请求，执行未授权操作
- 用户可能在不知情的情况下被诱导执行危险操作

**修复方案**：
```python
# 安装 Flask-WTF
pip install Flask-WTF

# app.py 中添加
from flask_wtf.csrf import CSRFProtect
csrf = CSRFProtect(app)

# 所有表单中添加 CSRF Token
<form method="POST">
    {{ csrf_token() }}
    ...
</form>

# API 请求中添加 CSRF Token（通过 Header）
X-CSRFToken: <token>
```

**优先级**：🔴 **P0 - 立即修复**

---

### 3. SQL 注入风险（部分）

**问题**：部分 SQL 查询使用了 f-string 拼接，虽然参数化，但仍有风险

```python
# routes/test_package_routes.py:373
f"SELECT DISTINCT Block FROM Faclist WHERE {' AND '.join(clauses)} AND Block IS NOT NULL"
```

**风险**：
- 如果 `clauses` 列表中的值未正确转义，可能导致 SQL 注入

**修复方案**：
- ✅ 大部分查询已使用参数化查询（`%s`），这是正确的
- 需要确保所有动态 WHERE 条件都使用参数化查询
- 避免使用 f-string 直接拼接 SQL

**优先级**：🟡 **P1 - 高优先级**

---

### 4. 文件上传安全不足

**问题**：
1. 仅检查文件扩展名，未验证文件内容（MIME 类型）
2. 未限制文件大小（虽然有 `MAX_CONTENT_LENGTH`，但未针对单个文件）
3. 未检查文件是否为恶意文件（如 ZIP 炸弹、宏病毒）

**风险**：
- 攻击者可以上传恶意文件（如 `.exe` 伪装成 `.pdf`）
- 可能导致服务器资源耗尽
- 可能执行恶意代码

**修复方案**：
```python
import magic  # python-magic
from werkzeug.utils import secure_filename

def validate_file(file):
    # 1. 检查扩展名
    if not allowed_file(file.filename):
        return False, "不允许的文件类型"
    
    # 2. 检查 MIME 类型
    file.seek(0)
    mime_type = magic.from_buffer(file.read(1024), mime=True)
    allowed_mimes = {
        'application/pdf',
        'image/png', 'image/jpeg',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        # ...
    }
    if mime_type not in allowed_mimes:
        return False, "文件内容与扩展名不匹配"
    
    # 3. 检查文件大小（单个文件）
    file.seek(0, 2)  # 移动到文件末尾
    size = file.tell()
    if size > 50 * 1024 * 1024:  # 50MB
        return False, "文件过大"
    file.seek(0)
    
    # 4. 扫描恶意内容（可选，使用 ClamAV 等）
    # ...
    
    return True, None
```

**优先级**：🟡 **P1 - 高优先级**

---

## 🟡 中等问题（建议修复）

### 5. 错误信息泄露

**问题**：部分错误处理可能泄露敏感信息

```python
# routes/backup_routes.py:1643
return jsonify({'error': str(exc)}), 500  # ❌ 可能泄露堆栈信息
```

**风险**：
- 泄露系统路径、数据库结构、内部逻辑
- 帮助攻击者了解系统架构

**修复方案**：
```python
# 生产环境统一错误处理
@app.errorhandler(Exception)
def handle_exception(e):
    if app.debug:
        return jsonify({'error': str(e)}), 500
    else:
        app.logger.error(f'Internal error: {e}', exc_info=True)
        return jsonify({'error': '服务器内部错误，请稍后重试'}), 500
```

**优先级**：🟡 **P2 - 中优先级**

---

### 6. 会话安全配置

**问题**：会话配置需要加强

**当前配置**（`config.py`）：
```python
SESSION_COOKIE_HTTPONLY = True  # ✅ 已启用
SESSION_COOKIE_SAMESITE = 'Lax'  # ✅ 已启用
SESSION_COOKIE_SECURE = os.environ.get('FLASK_HTTPS', 'False').lower() == 'true'  # ⚠️ 需要确保生产环境为 True
```

**修复方案**：
- 确保生产环境 `FLASK_HTTPS=True`
- 考虑缩短会话超时时间（当前 8 小时可能过长）
- 添加会话固定攻击防护（登录时重新生成 session ID）

**优先级**：🟡 **P2 - 中优先级**

---

### 7. 密码策略不足

**问题**：
- 密码最小长度仅 8 位（`utils/auth_manager.py:474`）
- 未强制要求复杂密码（大小写、数字、特殊字符）
- 未实现密码历史记录（防止重复使用旧密码）

**修复方案**：
```python
def validate_password_strength(password: str) -> tuple[bool, str]:
    """验证密码强度"""
    if len(password) < 12:  # 提高最小长度
        return False, "密码长度至少 12 位"
    
    has_upper = any(c.isupper() for c in password)
    has_lower = any(c.islower() for c in password)
    has_digit = any(c.isdigit() for c in password)
    has_special = any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in password)
    
    if not (has_upper and has_lower and has_digit and has_special):
        return False, "密码必须包含大小写字母、数字和特殊字符"
    
    # 检查常见弱密码
    weak_passwords = ['Password123!', 'Admin@123', ...]
    if password in weak_passwords:
        return False, "密码过于简单，请使用更复杂的密码"
    
    return True, ""
```

**优先级**：🟡 **P2 - 中优先级**

---

### 8. 缺少速率限制（Rate Limiting）

**问题**：未对 API 端点实施速率限制

**风险**：
- 暴力破解攻击（登录、密码重置）
- DDoS 攻击
- 资源耗尽

**修复方案**：
```python
# 安装 Flask-Limiter
pip install Flask-Limiter

# app.py
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

# 对敏感端点添加更严格的限制
@auth_bp.route('/login', methods=['POST'])
@limiter.limit("5 per minute")  # 登录尝试限制
def login():
    ...
```

**优先级**：🟡 **P2 - 中优先级**

---

### 9. 依赖包安全

**问题**：`requirements.txt` 中的包可能存在已知漏洞

**当前版本**：
```
Flask==2.3.3
mysql-connector-python==8.1.0
pandas==1.5.3
openpyxl==3.0.10
```

**修复方案**：
```bash
# 安装安全扫描工具
pip install safety

# 扫描已知漏洞
safety check -r requirements.txt

# 定期更新依赖包
pip install --upgrade Flask mysql-connector-python pandas openpyxl
```

**优先级**：🟡 **P2 - 中优先级**

---

### 10. 日志安全

**问题**：
- ✅ 已实现敏感数据脱敏（`utils/auth_manager.py`）
- ⚠️ 但日志可能包含其他敏感信息（IP、用户行为等）

**修复方案**：
- 确保日志文件权限正确（仅管理员可读）
- 定期轮转和归档日志
- 避免在日志中记录完整请求体（仅记录必要信息）

**优先级**：🟢 **P3 - 低优先级**

---

## 🟢 建议改进（最佳实践）

### 11. 添加安全响应头

**问题**：缺少安全相关的 HTTP 响应头

**修复方案**：
```python
@app.after_request
def set_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    response.headers['Content-Security-Policy'] = "default-src 'self'"
    return response
```

**优先级**：🟢 **P3 - 低优先级**

---

### 12. 输入验证和清理

**问题**：部分用户输入未充分验证

**修复方案**：
- 对所有用户输入进行验证（长度、格式、类型）
- 使用白名单而非黑名单
- 对输出进行 HTML 转义（Jinja2 默认已转义，但需要确认）

**优先级**：🟢 **P3 - 低优先级**

---

### 13. 审计日志增强

**问题**：
- ✅ 已有审计日志功能
- ⚠️ 可以增加更多安全相关事件记录（登录失败、权限拒绝等）

**修复方案**：
- 记录所有认证事件（成功/失败）
- 记录所有权限检查失败
- 记录敏感操作（密码修改、用户创建等）

**优先级**：🟢 **P3 - 低优先级**

---

### 14. 数据库连接安全

**问题**：
- ✅ 已使用连接池
- ⚠️ 建议使用 SSL 连接数据库（如果数据库支持）

**修复方案**：
```python
DB_CONFIG = {
    'host': os.environ.get('DB_HOST'),
    'database': os.environ.get('DB_NAME'),
    'user': os.environ.get('DB_USER'),
    'password': os.environ.get('DB_PASSWORD'),
    'port': int(os.environ.get('DB_PORT', 3306)),
    'ssl_disabled': False,  # 启用 SSL
    'ssl_ca': '/path/to/ca.pem',  # 可选
    'ssl_cert': '/path/to/client-cert.pem',  # 可选
    'ssl_key': '/path/to/client-key.pem'  # 可选
}
```

**优先级**：🟢 **P3 - 低优先级**

---

## 📋 修复优先级总结

| 优先级 | 问题 | 预计工作量 | 风险等级 |
|--------|------|-----------|----------|
| 🔴 P0 | 1. 硬编码密码移除 | 1小时 | 严重 |
| 🔴 P0 | 2. CSRF 保护 | 4-6小时 | 严重 |
| 🟡 P1 | 3. SQL 注入风险 | 2-3小时 | 高 |
| 🟡 P1 | 4. 文件上传安全 | 4-6小时 | 高 |
| 🟡 P2 | 5. 错误信息泄露 | 2小时 | 中 |
| 🟡 P2 | 6. 会话安全 | 1小时 | 中 |
| 🟡 P2 | 7. 密码策略 | 3-4小时 | 中 |
| 🟡 P2 | 8. 速率限制 | 2-3小时 | 中 |
| 🟡 P2 | 9. 依赖包更新 | 1小时 | 中 |
| 🟢 P3 | 10-14. 其他改进 | 8-10小时 | 低 |

**总计预计工作量**：28-40 小时

---

## ✅ 已实现的安全措施

1. ✅ 密码哈希存储（使用 `werkzeug.security`）
2. ✅ 敏感数据脱敏（审计日志）
3. ✅ 参数化 SQL 查询（大部分）
4. ✅ 文件上传使用 `secure_filename`
5. ✅ 会话 Cookie HttpOnly 和 SameSite
6. ✅ 用户认证和授权
7. ✅ 审计日志记录
8. ✅ 错误页面自定义（404、500）

---

## 🚀 快速修复清单

### 立即执行（P0）

1. **移除硬编码密码**
   ```bash
   # 1. 从 config.py 中删除硬编码密码
   # 2. 设置环境变量
   export DB_PASSWORD='your-secure-password'
   export FLASK_SECRET_KEY='your-secret-key'
   ```

2. **添加 CSRF 保护**
   ```bash
   pip install Flask-WTF
   # 然后按照上面的修复方案实施
   ```

### 本周内完成（P1）

3. **修复 SQL 注入风险**
4. **加强文件上传验证**

### 本月内完成（P2）

5. **错误处理改进**
6. **密码策略加强**
7. **添加速率限制**
8. **更新依赖包**

---

## 📚 参考资源

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [Flask Security Best Practices](https://flask.palletsprojects.com/en/2.3.x/security/)
- [OWASP Cheat Sheet Series](https://cheatsheetseries.owasp.org/)

---

**报告生成时间**：2024年
**审计人员**：AI Assistant
**下次审计建议**：修复 P0 和 P1 问题后，进行渗透测试

