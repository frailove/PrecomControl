# 维护脚本说明

## 焊接记录文件自动同步

### 功能说明

自动从源文件夹同步最新的焊接记录 Excel 文件到项目目录，替换旧的 `WeldingDB_*.xlsx` 文件。

**工作流程：**
1. **文件同步阶段**：查找最新文件夹 → 复制 Excel 文件并重命名为 `WeldingDB_*.xlsx`
2. **数据同步流水线阶段**（使用 `-AutoImport` 时）：备份 → 导入 → 同步 → 聚合 → 清理

### 脚本文件

- **`sync_welding_files.ps1`** - 主同步脚本
- **`setup_welding_sync_task.ps1`** - 定时任务设置脚本

---

## 使用方法

### 方法一：手动运行（前台）

```powershell
# 基本运行
.\scripts\maintenance\sync_welding_files.ps1

# 详细输出模式
.\scripts\maintenance\sync_welding_files.ps1 -ShowVerbose

# 测试模式（不实际复制文件）
.\scripts\maintenance\sync_welding_files.ps1 -Test

# 同步后自动运行数据同步流水线（备份、导入、同步、聚合、清理）
.\scripts\maintenance\sync_welding_files.ps1 -AutoImport
```

### 方法二：手动运行（后台）

```powershell
# 后台运行，不显示窗口
Start-Process powershell.exe -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"C:\Projects\PrecomControl\scripts\maintenance\sync_welding_files.ps1`"" -WindowStyle Hidden

# 后台运行，显示窗口（用于调试）
Start-Process powershell.exe -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"C:\Projects\PrecomControl\scripts\maintenance\sync_welding_files.ps1`" -ShowVerbose"
```

### 方法三：设置定时任务（自动运行）

#### 1. 设置加密的数据库密码（推荐，避免每次输入）

**定时任务运行时无法交互式输入密码，建议预先设置加密密码：**

```powershell
# 设置加密密码（使用 Windows DPAPI 加密，只有当前用户可以解密）
.\scripts\maintenance\set_db_password.ps1

# 查看是否已设置（不显示密码值）
.\scripts\maintenance\set_db_password.ps1 -Show

# 删除加密密码文件
.\scripts\maintenance\set_db_password.ps1 -Remove
```

**安全说明：**
- 密码使用 Windows DPAPI（Data Protection API）加密存储
- 只有当前用户或机器可以解密，不会明文存储
- 加密文件存储在 `config\db_password.encrypted`
- 如果修改了数据库密码，需要重新运行此脚本更新

#### 2. 创建定时任务（每天凌晨 2:00）

```powershell
# 以管理员身份运行
.\scripts\maintenance\setup_welding_sync_task.ps1

# 自定义运行时间（例如：每天凌晨 3:00）
.\scripts\maintenance\setup_welding_sync_task.ps1 -Time "03:00"
```

#### 3. 管理定时任务

```powershell
# 查看任务详细信息（包括运行时间、下次运行时间等）
.\scripts\maintenance\view_sync_task.ps1

# 修改运行时间（例如：改为每天凌晨 2:00）
.\scripts\maintenance\view_sync_task.ps1 -Time "02:00"

# 查看任务状态（简单信息）
Get-ScheduledTask -TaskName "PrecomControl_WeldingSync"

# 手动运行任务
Start-ScheduledTask -TaskName "PrecomControl_WeldingSync"

# 查看任务历史
Get-ScheduledTaskInfo -TaskName "PrecomControl_WeldingSync"

# 删除任务
.\scripts\maintenance\setup_welding_sync_task.ps1 -Remove
```

---

## 工作流程详解

### 文件同步阶段

1. **查找最新文件夹**
   - 在源路径 `Z:\16-无损检测资料 NDT （заявка и заключение НК и РК）\12 焊接记录查询 журнал сварочных работ` 下
   - 查找最新创建的文件夹（按创建时间排序）

2. **查找 Excel 文件**
   - 在最新文件夹中查找所有 `.xlsx` 文件

3. **删除旧文件**
   - 删除目标路径中的旧 `WeldingDB_*.xlsx` 文件（不备份）

4. **复制并重命名新文件**
   - 将新文件复制到 `C:\Projects\PrecomControl\nordinfo\`
   - 自动重命名为 `WeldingDB_1.xlsx`, `WeldingDB_2.xlsx`, `WeldingDB_3.xlsx` 等

### 数据同步流水线阶段（使用 `-AutoImport` 时）

在文件同步成功后，自动运行 `data_sync_pipeline.py`，执行以下步骤：

1. **[1/5] 创建导入前备份**
   - 自动创建数据库备份，确保数据安全

2. **[2/5] 导入最新 WeldingList 数据**
   - 从 `WeldingDB_*.xlsx` 文件导入焊接记录到数据库

3. **[3/5] 同步主数据**
   - 同步试压包、系统、子系统等主数据

4. **[4/5] 刷新所有聚合表**
   - 刷新 JointSummary、NDEPWHTStatus、ISODrawingList、SystemWeldingSummary、SubsystemWeldingSummary 等聚合表

5. **[5/5] 执行数据清理**
   - 清理孤立记录、软删除记录、日志和旧备份

---

## 日志

同步操作的日志保存在：
```
C:\Projects\PrecomControl\logs\welding_sync.log
```

### 查看日志

```powershell
# 查看最后 50 行
Get-Content C:\Projects\PrecomControl\logs\welding_sync.log -Tail 50

# 查看今天的日志
Get-Content C:\Projects\PrecomControl\logs\welding_sync.log | Select-String "$(Get-Date -Format 'yyyy-MM-dd')"

# 实时查看日志（类似 tail -f）
Get-Content C:\Projects\PrecomControl\logs\welding_sync.log -Wait -Tail 20
```

---

## 配置

### 修改源路径和目标路径

编辑 `sync_welding_files.ps1` 文件，修改以下变量：

```powershell
$SourceBasePath = "Z:\16-无损检测资料 NDT （заявка и заключение НК и РК）\12 焊接记录查询 журнал сварочных работ"
$TargetPath = "C:\Projects\PrecomControl\nordinfo"
$FilePattern = "WeldingDB_*.xlsx"
```

### 修改定时任务运行时间

编辑 `setup_welding_sync_task.ps1` 文件，或运行时指定：

```powershell
.\setup_welding_sync_task.ps1 -Time "02:00"  # 凌晨 2:00
.\setup_welding_sync_task.ps1 -Time "03:30"  # 凌晨 3:30
```

---

## 故障排查

### 问题：源路径不存在

**错误信息**：`错误: 源路径不存在`

**解决方法**：
1. 检查网络驱动器 Z: 是否已映射
2. 检查路径是否正确
3. 确认有访问权限

### 问题：无法访问文件夹

**错误信息**：`错误: 无法访问源路径`

**解决方法**：
1. 检查文件夹权限
2. 确认网络连接正常
3. 尝试手动访问该路径

### 问题：文件复制失败

**错误信息**：`✗ 复制失败`

**解决方法**：
1. 检查目标路径权限
2. 确认目标文件未被其他程序占用
3. 检查磁盘空间

### 问题：定时任务不运行

**解决方法**：
1. 检查任务状态：`Get-ScheduledTask -TaskName "PrecomControl_WeldingSync"`
2. 查看任务历史：`Get-ScheduledTaskInfo -TaskName "PrecomControl_WeldingSync"`
3. 手动运行测试：`Start-ScheduledTask -TaskName "PrecomControl_WeldingSync"`
4. 检查日志文件查看错误信息

---

## 注意事项

1. **权限要求**
   - 手动运行：需要访问源路径和目标路径的权限
   - 定时任务：建议以管理员身份创建，或使用有足够权限的用户账户

2. **网络驱动器**
   - 如果源路径在网络驱动器上，确保定时任务运行时网络驱动器已映射
   - 或者使用 UNC 路径（如：`\\server\share\path`）

3. **文件占用**
   - 同步时确保目标文件未被其他程序（如 Excel）打开
   - 建议在非工作时间运行

4. **数据同步流水线**
   - 使用 `-AutoImport` 参数时，会自动运行完整的数据同步流水线
   - 需要虚拟环境和数据库密码（如果未设置 `DB_PASSWORD` 环境变量，会提示输入）
   - 流水线包括：备份、导入、同步、聚合、清理五个步骤

---

## 示例输出

```
[2025-12-06 14:30:00] [INFO] ========================================
[2025-12-06 14:30:00] [INFO] 开始同步焊接记录文件
[2025-12-06 14:30:00] [INFO] ========================================
[2025-12-06 14:30:00] [SUCCESS] ✓ 源路径检查通过: Z:\16-无损检测资料 NDT...
[2025-12-06 14:30:00] [SUCCESS] ✓ 目标路径检查通过: C:\Projects\PrecomControl\nordinfo
[2025-12-06 14:30:01] [SUCCESS] ✓ 找到最新文件夹: 2025-12-05
[2025-12-06 14:30:01] [SUCCESS] ✓ 找到 4 个 Excel 文件
[2025-12-06 14:30:02] [SUCCESS] ✓ 旧文件处理完成
[2025-12-06 14:30:03] [SUCCESS]   ✓ 已复制并重命名: ecu.xlsx -> WeldingDB_1.xlsx (1250.5 KB)
[2025-12-06 14:30:03] [SUCCESS]   ✓ 已复制并重命名: pel.xlsx -> WeldingDB_2.xlsx (980.2 KB)
[2025-12-06 14:30:03] [SUCCESS] 同步完成！成功复制 4 个文件
[2025-12-06 14:30:03] [INFO] ========================================
[2025-12-06 14:30:03] [INFO] 开始执行数据同步流水线
[2025-12-06 14:30:03] [INFO]   步骤：备份 → 导入 → 同步 → 聚合 → 清理
[2025-12-06 14:30:03] [INFO] ========================================
[2025-12-06 14:30:05] [INFO] [1/5] 创建导入前备份...
[2025-12-06 14:30:10] [INFO] [2/5] 导入最新 WeldingList 数据...
[2025-12-06 14:30:15] [INFO] [3/5] 同步主数据...
[2025-12-06 14:30:20] [INFO] [4/5] 刷新所有聚合表...
[2025-12-06 14:30:25] [INFO] [5/5] 执行数据清理...
[2025-12-06 14:30:30] [SUCCESS] ✓ 数据同步流水线完成！
```

