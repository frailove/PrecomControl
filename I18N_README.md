# 国际化(i18n)使用指南

## 📚 快速开始

### 1. 初始化（首次运行）

```bash
# Windows
init_i18n.bat

# Linux/Mac
./init_i18n.sh
```

这将：
- 安装Flask-Babel
- 创建translations目录
- 提取所有需要翻译的文本
- 初始化英语和俄语翻译文件

### 2. 翻译文本

编辑翻译文件：
- `translations/en_US/LC_MESSAGES/messages.po` (英语)
- `translations/ru_RU/LC_MESSAGES/messages.po` (俄语)

### 3. 编译翻译

```bash
# Windows
compile_i18n.bat

# Linux/Mac
./compile_i18n.sh
```

### 4. 更新翻译（代码修改后）

```bash
# Windows
update_i18n.bat

# Linux/Mac
./update_i18n.sh
```

## 🔧 在代码中标记需要翻译的文本

### Python后端

```python
from flask_babel import gettext as _

# 简单文本
flash(_('保存成功'), 'success')

# 带变量的文本
message = _('找到 %(count)d 条记录', count=total)
```

### Jinja2模板

```html
<!-- 简单文本 -->
<h1>{{ _('系统管理') }}</h1>

<!-- 按钮 -->
<button>{{ _('保存') }}</button>

<!-- 带变量 -->
<p>{{ _('共 %(total)s 条记录', total=count) }}</p>
```

### JavaScript

```javascript
// 通过后端注入翻译对象（推荐）
const messages = {{ get_flashed_messages()|tojson }};

// 或在HTML中定义
<script>
    const i18n = {
        save: "{{ _('保存') }}",
        cancel: "{{ _('取消') }}"
    };
    alert(i18n.save);
</script>
```

## 📝 翻译文件格式

```po
# 注释
msgid "保存成功"
msgstr "Save successful"

# 带变量
msgid "找到 %(count)d 条记录"
msgstr "Found %(count)d records"
```

## 🌍 支持的语言

| 代码 | 语言 | 状态 |
|------|------|------|
| zh_CN | 简体中文 | ✅ 默认 |
| en_US | English | 🚧 进行中 |
| ru_RU | Русский | 🚧 进行中 |

## 🎯 语言切换

用户可以通过导航栏右上角的语言选择器切换语言。
语言偏好保存在cookie中，有效期1年。

## 📊 翻译进度跟踪

```bash
# 查看翻译进度
pybabel stats translations/en_US/LC_MESSAGES/messages.po
pybabel stats translations/ru_RU/LC_MESSAGES/messages.po
```

## 🛠️ 常用命令

```bash
# 提取新的翻译文本
pybabel extract -F babel.cfg -k _l -o messages.pot .

# 更新所有语言
pybabel update -i messages.pot -d translations

# 编译所有语言
pybabel compile -d translations

# 编译特定语言
pybabel compile -d translations -l en_US
```

## ⚠️ 注意事项

1. **不翻译**：用户输入的内容、数据库数据
2. **需要翻译**：UI标签、按钮、提示消息、错误信息
3. **保持变量名**：翻译时保持 `%(variable)s` 不变
4. **测试**：每次更新翻译后要测试三种语言
5. **编译**：修改.po文件后必须编译才能生效

## 🔍 调试

```python
# 在app.py中查看当前语言
from flask_babel import get_locale
print(f"当前语言: {get_locale()}")

# 强制刷新翻译缓存
app.config['BABEL_TRANSLATION_DIRECTORIES'] = 'translations'
```

## 📖 更多资源

- [Flask-Babel文档](https://python-babel.github.io/flask-babel/)
- [Babel文档](http://babel.pocoo.org/)
- [Poedit编辑器](https://poedit.net/) - 推荐的.po文件编辑工具

