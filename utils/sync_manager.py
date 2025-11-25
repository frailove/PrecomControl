"""
智能同步管理模块
处理WeldingList刷新后的数据同步，包括软删除、变更检测、级联处理
"""
import os
import sys
import json
from datetime import datetime

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import create_connection


class SyncManager:
    """智能同步管理器"""
    
    def __init__(self):
        pass
    
    def sync_after_welding_import(self, backup_id=None):
        """
        WeldingList导入后的智能同步
        
        Args:
            backup_id: 关联的备份ID
            
        Returns:
            sync_id: 同步ID
        """
        conn = create_connection()
        cur = conn.cursor(buffered=True, dictionary=True)
        
        try:
            # 确保表结构已更新（放宽列长度，避免同步时溢出）
            self._ensure_table_schema(cur, conn)
            
            print(f"\n{'='*60}")
            print(f"开始智能同步...")
            print(f"{'='*60}")
            
            start_time = datetime.now()
            
            # 1. 创建同步日志
            cur.execute("""
                INSERT INTO SyncLog 
                (SyncType, BackupID, StartTime, Status)
                VALUES (%s, %s, %s, %s)
            """, ('WELDING_IMPORT', backup_id, start_time, 'RUNNING'))
            conn.commit()
            
            sync_id = cur.lastrowid
            print(f"\n同步ID: {sync_id}")
            
            stats = {
                'added': 0,
                'updated': 0,
                'deleted': 0,
                'skipped': 0
            }
            
            # 2. 同步 TestPackages（从WeldingList提取唯一的TestPackageID）
            print(f"\n[1/3] 同步试压包数据...")
            test_package_stats = self._sync_test_packages(cur, conn, sync_id)
            for key in stats:
                stats[key] += test_package_stats.get(key, 0)
            
            # 3. 同步 Systems（从WeldingList提取唯一的SystemCode）
            print(f"\n[2/3] 同步系统数据...")
            system_stats = self._sync_systems(cur, conn, sync_id)
            for key in stats:
                stats[key] += system_stats.get(key, 0)
            
            # 4. 同步 Subsystems（从WeldingList提取唯一的SubSystemCode）
            print(f"\n[3/3] 同步子系统数据...")
            subsystem_stats = self._sync_subsystems(cur, conn, sync_id)
            for key in stats:
                stats[key] += subsystem_stats.get(key, 0)
            
            # 5. 更新同步日志
            end_time = datetime.now()
            duration = int((end_time - start_time).total_seconds())
            
            details = {
                'test_packages': test_package_stats,
                'systems': system_stats,
                'subsystems': subsystem_stats
            }
            
            cur.execute("""
                UPDATE SyncLog SET
                    Status = 'COMPLETED',
                    RecordsAdded = %s,
                    RecordsUpdated = %s,
                    RecordsDeleted = %s,
                    RecordsSkipped = %s,
                    DetailsJSON = %s,
                    EndTime = %s,
                    Duration = %s
                WHERE SyncID = %s
            """, (
                stats['added'],
                stats['updated'],
                stats['deleted'],
                stats['skipped'],
                json.dumps(details, ensure_ascii=False),
                end_time,
                duration,
                sync_id
            ))
            conn.commit()
            
            print(f"\n{'='*60}")
            print(f"智能同步完成！")
            print(f"同步ID: {sync_id}")
            print(f"新增: {stats['added']}, 更新: {stats['updated']}, 删除: {stats['deleted']}, 跳过: {stats['skipped']}")
            print(f"耗时: {duration} 秒")
            print(f"{'='*60}\n")
            
            return sync_id
            
        except Exception as e:
            # 同步失败，更新状态
            try:
                cur.execute("""
                    UPDATE SyncLog SET
                        Status = 'FAILED',
                        ErrorMessage = %s,
                        EndTime = %s
                    WHERE SyncID = %s
                """, (str(e), datetime.now(), sync_id))
                conn.commit()
            except:
                pass
            
            print(f"\n同步失败: {e}")
            raise
            
        finally:
            cur.close()
            conn.close()
    
    def _sync_test_packages(self, cur, conn, sync_id):
        """
        同步试压包数据
        
        策略：
        1. 从WeldingList提取所有唯一的TestPackageID
        2. 对于WeldingList中存在但HydroTestPackageList中不存在的，新增记录
        3. 对于HydroTestPackageList中存在但WeldingList中不存在的，软删除（标记IsDeleted=TRUE）
        4. 保护手动修改过的记录（IsManuallyModified=TRUE）
        """
        stats = {'added': 0, 'updated': 0, 'deleted': 0, 'skipped': 0}
        now = datetime.now()
        
        base_select = """
            SELECT
                TRIM(wl.TestPackageID) AS TestPackageID,
                MAX(TRIM(wl.SystemCode)) AS SystemCode,
                MAX(TRIM(wl.SubSystemCode)) AS SubSystemCode,
                COALESCE(NULLIF(TRIM(wl.TestPackageID), ''), 'AUTO_SYNC') AS Description
            FROM WeldingList wl
            WHERE wl.TestPackageID IS NOT NULL
              AND TRIM(wl.TestPackageID) <> ''
              AND wl.IsDeleted = FALSE
            GROUP BY TRIM(wl.TestPackageID)
        """

        # 仅插入新增记录
        insert_sql = f"""
            INSERT INTO HydroTestPackageList
                (TestPackageID, SystemCode, SubSystemCode, Description, DataSource, LastSyncTime, IsDeleted, DeletedTime)
            SELECT
                src.TestPackageID,
                src.SystemCode,
                src.SubSystemCode,
                src.Description,
                'WELDING_LIST' AS DataSource,
                %s AS LastSyncTime,
                FALSE AS IsDeleted,
                NULL AS DeletedTime
            FROM ({base_select}) src
            WHERE NOT EXISTS (
                SELECT 1 FROM HydroTestPackageList h WHERE h.TestPackageID = src.TestPackageID
            )
        """
        cur.execute(insert_sql, (now,))
        conn.commit()
        stats['added'] = cur.rowcount or 0
        if stats['added']:
            print(f"  + 新增试压包: {stats['added']} 条")

        # 更新已存在的记录
        update_sql = f"""
            UPDATE HydroTestPackageList h
            JOIN ({base_select}) src ON src.TestPackageID = h.TestPackageID
            SET h.SystemCode = src.SystemCode,
                h.SubSystemCode = src.SubSystemCode,
                h.Description = src.Description,
                h.DataSource = 'WELDING_LIST',
                h.LastSyncTime = %s,
                h.IsDeleted = FALSE,
                h.DeletedTime = NULL
        """
        cur.execute(update_sql, (now,))
        conn.commit()
        stats['updated'] = cur.rowcount or 0
        if stats['updated']:
            print(f"  ~ 更新试压包: {stats['updated']} 条")
        
        # 软删除
        cur.execute("""
            UPDATE HydroTestPackageList h
            LEFT JOIN (
                SELECT DISTINCT TestPackageID
                FROM WeldingList
                WHERE TestPackageID IS NOT NULL
                  AND TestPackageID <> ''
                  AND IsDeleted = FALSE
            ) wl ON wl.TestPackageID = h.TestPackageID
            SET h.IsDeleted = TRUE,
                h.DeletedTime = %s,
                h.LastSyncTime = %s
            WHERE wl.TestPackageID IS NULL
              AND h.IsDeleted = FALSE
              AND (h.IsManuallyModified IS NULL OR h.IsManuallyModified = FALSE)
        """, (now, now))
        conn.commit()
        stats['deleted'] = cur.rowcount or 0
        if stats['deleted']:
            print(f"  - 软删除试压包: {stats['deleted']} 条")
        
        return stats
    
    def _sync_systems(self, cur, conn, sync_id):
        """同步系统数据"""
        stats = {'added': 0, 'updated': 0, 'deleted': 0, 'skipped': 0}
        now = datetime.now()
        
        cur.execute("""
            INSERT INTO SystemList (
                SystemCode,
                SystemDescriptionENG,
                SystemDescriptionRUS,
                ProcessOrNonProcess,
                Priority,
                Remarks,
                DataSource,
                LastSyncTime,
                created_by,
                last_updated_by
            )
            SELECT
                src.SystemCode,
                src.SystemCode AS SystemDescriptionENG,
                NULL,
                'Process',
                0,
                '',
                'WELDING_LIST',
                %s,
                'sync',
                'sync'
            FROM (
                SELECT DISTINCT TRIM(wl.SystemCode) AS SystemCode
                FROM WeldingList wl
                WHERE wl.SystemCode IS NOT NULL
                  AND TRIM(wl.SystemCode) <> ''
                  AND wl.IsDeleted = FALSE
            ) src
            ON DUPLICATE KEY UPDATE
                SystemDescriptionENG = IF(SystemList.IsManuallyModified = TRUE, SystemList.SystemDescriptionENG, VALUES(SystemDescriptionENG)),
                ProcessOrNonProcess = IF(SystemList.IsManuallyModified = TRUE, SystemList.ProcessOrNonProcess, VALUES(ProcessOrNonProcess)),
                Priority = IF(SystemList.IsManuallyModified = TRUE, SystemList.Priority, VALUES(Priority)),
                Remarks = IF(SystemList.IsManuallyModified = TRUE, SystemList.Remarks, VALUES(Remarks)),
                DataSource = 'WELDING_LIST',
                LastSyncTime = VALUES(LastSyncTime),
                IsDeleted = FALSE,
                DeletedTime = NULL,
                last_updated_by = 'sync'
        """, (now,))
        conn.commit()
        stats['added'] = cur.rowcount or 0
        if stats['added']:
            print(f"  + 新增系统: {stats['added']} 条")
        
        cur.execute("""
            UPDATE SystemList s
            LEFT JOIN (
                SELECT DISTINCT SystemCode
                FROM WeldingList
                WHERE SystemCode IS NOT NULL
                  AND SystemCode <> ''
                  AND IsDeleted = FALSE
            ) wl ON wl.SystemCode = s.SystemCode
            SET s.IsDeleted = TRUE,
                s.DeletedTime = %s,
                s.LastSyncTime = %s
            WHERE wl.SystemCode IS NULL
              AND s.IsDeleted = FALSE
              AND (s.IsManuallyModified IS NULL OR s.IsManuallyModified = FALSE)
        """, (now, now))
        conn.commit()
        stats['deleted'] = cur.rowcount or 0
        if stats['deleted']:
            print(f"  - 软删除系统: {stats['deleted']} 条")
        
        return stats
    
    def _ensure_table_schema(self, cur, conn):
        """确保表结构已更新（放宽列长度，避免同步时溢出）"""
        from mysql.connector import Error
        def _get_column_type(col):
            if not col:
                return ''
            if isinstance(col, dict):
                return str(col.get('Type', '') or '')
            if isinstance(col, (list, tuple)) and len(col) > 1:
                return str(col[1] or '')
            return str(col)

        import re
        
        try:
            # 检查并更新 SystemList.SystemCode
            cur.execute("SHOW COLUMNS FROM SystemList LIKE 'SystemCode'")
            col = cur.fetchone()
            col_type = _get_column_type(col)
            print(f"[DEBUG] SystemList.SystemCode 当前类型: {col_type}")
            
            if col_type and 'varchar' in col_type.lower():
                match = re.search(r'varchar\((\d+)\)', col_type.lower())
                if match:
                    current_len = int(match.group(1))
                    print(f"[DEBUG] SystemList.SystemCode 当前长度: {current_len}")
                    if current_len < 512:
                        print(f"[DEBUG] 执行 ALTER TABLE 更新 SystemList.SystemCode: {current_len} -> 512")
                        cur.execute("ALTER TABLE SystemList MODIFY COLUMN SystemCode VARCHAR(512) NOT NULL")
                        conn.commit()
                        print(f"[DEBUG] SystemList.SystemCode 更新完成")
        except Error as e:
            print(f"[ERROR] 更新 SystemList.SystemCode 失败: {e}")

        try:
            # 检查并更新 SubsystemList.SubSystemCode（最关键，因为报错在这里）
            cur.execute("SHOW COLUMNS FROM SubsystemList LIKE 'SubSystemCode'")
            col = cur.fetchone()
            col_type = _get_column_type(col)
            print(f"[DEBUG] SubsystemList.SubSystemCode 当前类型: {col_type}")
            
            if col_type and 'varchar' in col_type.lower():
                match = re.search(r'varchar\((\d+)\)', col_type.lower())
                if match:
                    current_len = int(match.group(1))
                    print(f"[DEBUG] SubsystemList.SubSystemCode 当前长度: {current_len}")
                    if current_len < 512:
                        print(f"[DEBUG] 执行 ALTER TABLE 更新 SubsystemList.SubSystemCode: {current_len} -> 512")
                        cur.execute("ALTER TABLE SubsystemList MODIFY COLUMN SubSystemCode VARCHAR(512) NOT NULL")
                        conn.commit()
                        # 再次查询确认
                        cur.execute("SHOW COLUMNS FROM SubsystemList LIKE 'SubSystemCode'")
                        col_after = cur.fetchone()
                        col_type_after = _get_column_type(col_after)
                        print(f"[DEBUG] 更新后 SubsystemList.SubSystemCode 类型: {col_type_after}")
                    else:
                        print(f"[DEBUG] SubsystemList.SubSystemCode 长度已足够: {current_len}")
                else:
                    print(f"[WARN] 无法解析 SubsystemList.SubSystemCode 类型: {col_type}")
        except Error as e:
            print(f"[ERROR] 更新 SubsystemList.SubSystemCode 失败: {e}")

        try:
            # 检查并更新 SubsystemList.SystemCode
            cur.execute("SHOW COLUMNS FROM SubsystemList LIKE 'SystemCode'")
            col = cur.fetchone()
            col_type = _get_column_type(col)
            print(f"[DEBUG] SubsystemList.SystemCode 当前类型: {col_type}")
            
            if col_type and 'varchar' in col_type.lower():
                match = re.search(r'varchar\((\d+)\)', col_type.lower())
                if match:
                    current_len = int(match.group(1))
                    print(f"[DEBUG] SubsystemList.SystemCode 当前长度: {current_len}")
                    if current_len < 512:
                        print(f"[DEBUG] 执行 ALTER TABLE 更新 SubsystemList.SystemCode: {current_len} -> 512")
                        cur.execute("ALTER TABLE SubsystemList MODIFY COLUMN SystemCode VARCHAR(512) NOT NULL")
                        conn.commit()
                        print(f"[DEBUG] SubsystemList.SystemCode 更新完成")
        except Error as e:
            if getattr(e, 'errno', None) == 1832:
                print("[INFO] 跳过 SubsystemList.SystemCode 长度调整：该列存在外键约束（SubsystemList_ibfk_1），如需放宽请在数据库中手动处理。")
            else:
                print(f"[ERROR] 更新 SubsystemList.SystemCode 失败: {e}")

        # 注意：不再尝试修改 HydroTestPackageList 的列，因为：
        # 1. SystemCode 和 SubSystemCode 有外键约束，修改需要先删除外键
        # 2. 修改列信息不是长期需求，应该通过数据库管理工具手动处理
    
    def _sync_subsystems(self, cur, conn, sync_id):
        """同步子系统数据"""
        stats = {'added': 0, 'updated': 0, 'deleted': 0, 'skipped': 0}
        now = datetime.now()
        
        # 调试：先查询所有要插入的 SubSystemCode，找出超长的值
        cur.execute("""
            SELECT DISTINCT
                TRIM(wl.SubSystemCode) AS SubSystemCode,
                TRIM(wl.SystemCode) AS SystemCode,
                LENGTH(TRIM(wl.SubSystemCode)) AS SubSystemCodeLen,
                LENGTH(TRIM(wl.SystemCode)) AS SystemCodeLen
            FROM WeldingList wl
            WHERE wl.SubSystemCode IS NOT NULL
              AND TRIM(wl.SubSystemCode) <> ''
              AND wl.IsDeleted = FALSE
            ORDER BY LENGTH(TRIM(wl.SubSystemCode)) DESC
            LIMIT 20
        """)
        long_codes = cur.fetchall()
        if long_codes:
            print("\n[DEBUG] 最长的 SubSystemCode 值（前20个）：")
            for idx, row in enumerate(long_codes, 1):
                sub_code = row.get('SubSystemCode', '') if isinstance(row, dict) else (row[0] if isinstance(row, (list, tuple)) else '')
                sub_len = row.get('SubSystemCodeLen', 0) if isinstance(row, dict) else (row[2] if isinstance(row, (list, tuple)) and len(row) > 2 else 0)
                sys_code = row.get('SystemCode', '') if isinstance(row, dict) else (row[1] if isinstance(row, (list, tuple)) and len(row) > 1 else '')
                print(f"  [{idx}] SubSystemCode长度={sub_len}, 值='{sub_code[:100]}...' (SystemCode='{sys_code}')")
                if sub_len > 512:
                    print(f"      ⚠️  超过512字符限制！")
        
        cur.execute("""
            INSERT INTO SubsystemList (
                SubSystemCode,
                SystemCode,
                SubSystemDescriptionENG,
                SubSystemDescriptionRUS,
                ProcessOrNonProcess,
                Priority,
                Remarks,
                DataSource,
                LastSyncTime,
                created_by,
                last_updated_by
            )
            SELECT
                src.SubSystemCode,
                src.SystemCode,
                src.SubSystemCode,
                NULL,
                'Process',
                0,
                '',
                'WELDING_LIST',
                %s,
                'sync',
                'sync'
            FROM (
                SELECT DISTINCT
                    TRIM(wl.SubSystemCode) AS SubSystemCode,
                    TRIM(wl.SystemCode) AS SystemCode
                FROM WeldingList wl
                WHERE wl.SubSystemCode IS NOT NULL
                  AND TRIM(wl.SubSystemCode) <> ''
                  AND wl.IsDeleted = FALSE
            ) src
            ON DUPLICATE KEY UPDATE
                SubSystemDescriptionENG = IF(SubsystemList.IsManuallyModified = TRUE, SubsystemList.SubSystemDescriptionENG, VALUES(SubSystemDescriptionENG)),
                ProcessOrNonProcess = IF(SubsystemList.IsManuallyModified = TRUE, SubsystemList.ProcessOrNonProcess, VALUES(ProcessOrNonProcess)),
                Priority = IF(SubsystemList.IsManuallyModified = TRUE, SubsystemList.Priority, VALUES(Priority)),
                Remarks = IF(SubsystemList.IsManuallyModified = TRUE, SubsystemList.Remarks, VALUES(Remarks)),
                DataSource = 'WELDING_LIST',
                LastSyncTime = VALUES(LastSyncTime),
                IsDeleted = FALSE,
                DeletedTime = NULL,
                last_updated_by = 'sync'
        """, (now,))
        conn.commit()
        stats['added'] = cur.rowcount or 0
        if stats['added']:
            print(f"  + 新增子系统: {stats['added']} 条")
        
        cur.execute("""
            UPDATE SubsystemList s
            LEFT JOIN (
                SELECT DISTINCT SubSystemCode
                FROM WeldingList
                WHERE SubSystemCode IS NOT NULL
                  AND SubSystemCode <> ''
                  AND IsDeleted = FALSE
            ) wl ON wl.SubSystemCode = s.SubSystemCode
            SET s.IsDeleted = TRUE,
                s.DeletedTime = %s,
                s.LastSyncTime = %s
            WHERE wl.SubSystemCode IS NULL
              AND s.IsDeleted = FALSE
              AND (s.IsManuallyModified IS NULL OR s.IsManuallyModified = FALSE)
        """, (now, now))
        conn.commit()
        stats['deleted'] = cur.rowcount or 0
        if stats['deleted']:
            print(f"  - 软删除子系统: {stats['deleted']} 条")
        
        return stats
    
    def _log_change(self, cur, conn, sync_id, table_name, record_id, 
                   change_type, field_name, old_value, new_value):
        """记录变更日志"""
        try:
            cur.execute("""
                INSERT INTO ChangeLog
                (SyncID, TableName, RecordID, ChangeType, FieldName, OldValue, NewValue, ChangeSource)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (sync_id, table_name, record_id, change_type, field_name, 
                 str(old_value) if old_value else None,
                 str(new_value) if new_value else None,
                 'SYNC'))
            conn.commit()
        except Exception as e:
            print(f"  记录变更日志失败: {e}")
    
    def restore_deleted_record(self, table_name, record_id):
        """
        恢复被软删除的记录
        
        Args:
            table_name: 表名
            record_id: 记录ID
        """
        conn = create_connection()
        cur = conn.cursor(buffered=True)
        
        try:
            id_field = {
                'HydroTestPackageList': 'TestPackageID',
                'SystemList': 'SystemCode',
                'SubsystemList': 'SubSystemCode'
            }.get(table_name)
            
            if not id_field:
                print(f"不支持的表: {table_name}")
                return False
            
            cur.execute(f"""
                UPDATE {table_name} SET
                    IsDeleted = FALSE,
                    DeletedTime = NULL,
                    LastSyncTime = %s,
                    IsManuallyModified = TRUE
                WHERE {id_field} = %s AND IsDeleted = TRUE
            """, (datetime.now(), record_id))
            conn.commit()
            
            print(f"已恢复 {table_name} 中的记录: {record_id}")
            return True
            
        except Exception as e:
            print(f"恢复记录失败: {e}")
            return False
            
        finally:
            cur.close()
            conn.close()


def sync_after_import(backup_id=None):
    """便捷函数：执行同步"""
    manager = SyncManager()
    return manager.sync_after_welding_import(backup_id=backup_id)


if __name__ == '__main__':
    # 测试同步功能
    print("测试智能同步管理器...")
    sync_id = sync_after_import()
    print(f"\n同步完成，SyncID: {sync_id}")

