# UI一致性优化指南

## 🎯 目标
确保切换语言后，UI布局保持一致，不会因为文本长度变化而错位。

## 📐 已实施的优化措施

### 1. **导航栏链接固定**
```css
.top-navbar .nav-link {
    white-space: nowrap;      /* 不换行 */
    min-width: fit-content;   /* 最小宽度适应内容 */
}
```

### 2. **下拉菜单固定宽度**
```css
.top-navbar .dropdown-item {
    white-space: nowrap;      /* 不换行 */
    min-width: 200px;         /* 最小宽度200px */
}
```

### 3. **按钮固定规则**
```css
.btn {
    white-space: nowrap;      /* 文字不换行 */
    min-width: fit-content;   /* 适应内容 */
}

.btn-sm {
    min-width: auto;          /* 小按钮更紧凑 */
}
```

### 4. **表格列标题**
```css
table th {
    white-space: nowrap;          /* 不换行 */
    overflow: hidden;             /* 超出隐藏 */
    text-overflow: ellipsis;      /* 显示省略号 */
}
```

### 5. **表单标签**
```css
.form-label {
    white-space: nowrap;          /* 不换行 */
    min-width: fit-content;       /* 适应内容 */
}
```

## 🔤 翻译文本长度控制建议

### 导航菜单（尽量简短）
```
中文 → 英文缩写（如需要）
系统管理 → Systems (不要用 System Management)
备份 → Backup (不要用 Backup Management)
```

### 按钮文字（使用动词）
```
新增关键工程量 → Add Quantity (简化)
返回列表 → Back (简化)
下载导入模板 → Template (简化)
```

### 表格列标题（使用缩写）
```
已完成数量 → Completed (不要 Completed Quantity)
测试计划时间 → Planned (不要 Planned Test Date)
```

## 🛠️ 如果UI仍有问题的解决方案

### 方案A：为不同语言设置不同的CSS
```html
<body class="lang-{{ get_locale() }}">
```

```css
/* 英文时调整间距 */
.lang-en_US .btn {
    padding: 0.625rem 1.2rem;
}

/* 俄文时使用更小字号 */
.lang-ru_RU .nav-link {
    font-size: 0.85rem;
}
```

### 方案B：使用缩写 + Tooltip
```html
<button title="{{ _('新增关键工程量') }}">
    <i class="bi bi-plus-circle"></i>
    {{ _('新增') }}
</button>
```

### 方案C：响应式文本
```css
/* 大屏幕显示完整文本，小屏幕显示缩写 */
.btn .full-text { display: inline; }
.btn .short-text { display: none; }

@media (max-width: 1200px) {
    .btn .full-text { display: none; }
    .btn .short-text { display: inline; }
}
```

## 📊 测试不同语言的布局

测试时注意检查：
- [ ] 导航栏是否对齐
- [ ] 按钮是否大小一致
- [ ] 表格列宽是否稳定
- [ ] 下拉菜单是否整齐
- [ ] 表单布局是否一致

## 💡 最佳实践

1. **保持文本简洁**：UI文本越短越好
2. **使用图标**：减少对文字的依赖
3. **固定宽度**：关键元素使用固定或最小宽度
4. **测试所有语言**：每次修改都要测三种语言
5. **优先考虑俄语**：俄语通常最长，以俄语为基准设计宽度

