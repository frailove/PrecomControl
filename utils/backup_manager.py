"""
数据备份管理模块
提供全量备份、增量备份、备份恢复等功能
"""
import os
import sys
import json
from datetime import datetime, timedelta

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import create_connection

class BackupManager:
    """数据备份管理器"""
    
    # 需要备份的表
    BACKUP_TABLES = [
        # 'WeldingList'  # 外部来源数据，体量巨大且可随时重新导入，这里不再备份
        'HydroTestPackageList',
        'SystemList',
        'SubsystemList',
        'LineList',
        'JointSummary',
        'NDEPWHTStatus',
        'ISODrawingList'
        # 'AttachmentList',  # 待创建
        # 'PunchListItem'     # 待创建
    ]
    
    def __init__(self, backup_dir='backups'):
        """
        初始化备份管理器
        
        Args:
            backup_dir: 备份文件存储目录
        """
        self.backup_dir = backup_dir
        if not os.path.exists(backup_dir):
            os.makedirs(backup_dir)
    
    def create_full_backup(self, trigger='MANUAL', description=None, backup_by='SYSTEM'):
        """
        创建全量备份
        
        Args:
            trigger: 触发原因 (SCHEDULED, PRE_IMPORT, MANUAL)
            description: 备份描述
            backup_by: 备份执行者
            
        Returns:
            backup_id: 备份ID
        """
        conn = create_connection()
        cur = conn.cursor(buffered=True, dictionary=True)
        
        try:
            print(f"\n{'='*60}")
            print(f"开始全量备份 [{trigger}]")
            print(f"{'='*60}")
            
            # 1. 创建备份记录
            backup_time = datetime.now()
            backup_time_str = backup_time.strftime('%Y%m%d_%H%M%S')
            
            cur.execute("""
                INSERT INTO DataBackup 
                (BackupType, BackupTrigger, BackupTime, BackupBy, Status, Description)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, ('FULL', trigger, backup_time, backup_by, 'RUNNING', description))
            conn.commit()
            
            backup_id = cur.lastrowid
            print(f"\n备份ID: {backup_id}")
            
            # 2. 备份每个表
            backup_files = {}
            total_size = 0
            table_counts = {}
            
            for table_name in self.BACKUP_TABLES:
                print(f"\n备份表: {table_name}...", end='')
                
                try:
                    # 查询表数据
                    cur.execute(f"SELECT * FROM {table_name}")
                    rows = cur.fetchall()
                    
                    if rows:
                        # 保存为JSON文件
                        backup_file = os.path.join(
                            self.backup_dir,
                            f'backup_{backup_id}_{table_name}_{backup_time_str}.json'
                        )
                        
                        with open(backup_file, 'w', encoding='utf-8') as f:
                            json.dump(rows, f, ensure_ascii=False, indent=2, default=str)
                        
                        file_size = os.path.getsize(backup_file)
                        total_size += file_size
                        
                        backup_files[table_name] = backup_file
                        table_counts[table_name] = len(rows)
                        
                        print(f" {len(rows)} 条记录, {file_size/1024:.2f} KB")
                    else:
                        print(f" 表为空")
                        table_counts[table_name] = 0
                        
                except Exception as e:
                    print(f" 失败: {e}")
                    table_counts[table_name] = 0
            
            # 3. 更新备份记录
            backup_file_path_json = json.dumps(backup_files, ensure_ascii=False)
            
            cur.execute("""
                UPDATE DataBackup SET
                    Status = 'COMPLETED',
                    BackupFilePath = %s,
                    BackupSize = %s,
                    WeldingListCount = %s,
                    TestPackageCount = %s,
                    SystemCount = %s,
                    SubsystemCount = %s
                WHERE BackupID = %s
            """, (
                backup_file_path_json,
                total_size,
                table_counts.get('WeldingList', 0),
                table_counts.get('HydroTestPackageList', 0),
                table_counts.get('SystemList', 0),
                table_counts.get('SubsystemList', 0),
                backup_id
            ))
            conn.commit()
            
            print(f"\n{'='*60}")
            print(f"全量备份完成！")
            print(f"备份ID: {backup_id}")
            print(f"备份文件总大小: {total_size/1024/1024:.2f} MB")
            print(f"备份时间: {backup_time}")
            print(f"{'='*60}\n")
            
            return backup_id
            
        except Exception as e:
            # 备份失败，更新状态
            try:
                cur.execute("""
                    UPDATE DataBackup SET
                        Status = 'FAILED',
                        ErrorMessage = %s
                    WHERE BackupID = %s
                """, (str(e), backup_id))
                conn.commit()
            except:
                pass
            
            print(f"\n备份失败: {e}")
            raise
            
        finally:
            cur.close()
            conn.close()
    
    def create_incremental_backup(self, since_backup_id=None, since_time=None):
        """
        创建增量备份（仅备份变更的数据）
        
        Args:
            since_backup_id: 自从哪个备份ID之后的变更
            since_time: 自从哪个时间点之后的变更
            
        Returns:
            backup_id: 备份ID
        """
        # 增量备份的实现（可选，暂时使用全量备份）
        print("增量备份功能开发中，当前使用全量备份代替...")
        return self.create_full_backup(trigger='SCHEDULED', description='增量备份（全量）')
    
    def get_backup_list(self, limit=20):
        """
        获取备份列表
        
        Args:
            limit: 返回记录数限制
            
        Returns:
            list: 备份记录列表
        """
        conn = create_connection()
        cur = conn.cursor(buffered=True, dictionary=True)
        
        try:
            cur.execute("""
                SELECT 
                    BackupID, BackupType, BackupTrigger, BackupTime, BackupBy,
                    WeldingListCount, TestPackageCount, SystemCount, SubsystemCount,
                    BackupSize, Status, ErrorMessage, Description
                FROM DataBackup
                ORDER BY BackupTime DESC
                LIMIT %s
            """, (limit,))
            
            backups = cur.fetchall()
            return backups
            
        finally:
            cur.close()
            conn.close()
    
    def get_backup_details(self, backup_id):
        """
        获取备份详情
        
        Args:
            backup_id: 备份ID
            
        Returns:
            dict: 备份详情
        """
        conn = create_connection()
        cur = conn.cursor(buffered=True, dictionary=True)
        
        try:
            cur.execute("""
                SELECT * FROM DataBackup WHERE BackupID = %s
            """, (backup_id,))
            
            backup = cur.fetchone()
            
            if backup and backup.get('BackupFilePath'):
                # 解析备份文件路径
                try:
                    backup['BackupFiles'] = json.loads(backup['BackupFilePath'])
                except:
                    backup['BackupFiles'] = {}
            
            return backup
            
        finally:
            cur.close()
            conn.close()
    
    def delete_old_backups(self, keep_days=30, keep_count=10):
        """
        删除旧备份（保留策略）
        
        Args:
            keep_days: 保留最近N天的备份
            keep_count: 至少保留最近N个备份
        """
        conn = create_connection()
        cur = conn.cursor(buffered=True, dictionary=True)
        
        try:
            print(f"\n清理旧备份（保留最近{keep_days}天或最近{keep_count}个）...")
            
            # 1. 获取所有备份
            cur.execute("""
                SELECT BackupID, BackupTime, BackupFilePath
                FROM DataBackup
                ORDER BY BackupTime DESC
            """)
            backups = cur.fetchall()
            
            if len(backups) <= keep_count:
                print("备份数量未超过保留阈值，无需清理")
                return
            
            # 2. 确定要删除的备份
            cutoff_time = datetime.now() - timedelta(days=keep_days)
            backups_to_delete = []
            
            for idx, backup in enumerate(backups):
                # 跳过最近的 keep_count 个备份
                if idx < keep_count:
                    continue
                
                # 删除超过 keep_days 的备份
                if backup['BackupTime'] < cutoff_time:
                    backups_to_delete.append(backup)
            
            if not backups_to_delete:
                print("没有需要清理的旧备份")
                return
            
            # 3. 删除备份文件和数据库记录
            deleted_count = 0
            for backup in backups_to_delete:
                try:
                    # 删除备份文件
                    if backup.get('BackupFilePath'):
                        backup_files = json.loads(backup['BackupFilePath'])
                        for table_name, file_path in backup_files.items():
                            if os.path.exists(file_path):
                                os.remove(file_path)
                                print(f"  删除文件: {os.path.basename(file_path)}")
                    
                    # 删除数据库记录
                    cur.execute("DELETE FROM DataBackup WHERE BackupID = %s", (backup['BackupID'],))
                    conn.commit()
                    
                    deleted_count += 1
                    
                except Exception as e:
                    print(f"  删除备份 {backup['BackupID']} 失败: {e}")
            
            print(f"\n已删除 {deleted_count} 个旧备份")
            
        finally:
            cur.close()
            conn.close()
    
    def restore_from_backup(self, backup_id, tables=None):
        """
        从备份恢复数据
        
        Args:
            backup_id: 备份ID
            tables: 要恢复的表列表（None表示恢复所有表）
            
        Returns:
            bool: 恢复是否成功
        """
        conn = create_connection()
        cur = conn.cursor(buffered=True, dictionary=True)
        
        try:
            print(f"\n{'='*60}")
            print(f"从备份 {backup_id} 恢复数据")
            print(f"{'='*60}")
            
            # 1. 获取备份信息
            backup = self.get_backup_details(backup_id)
            
            if not backup:
                print(f"错误: 备份 {backup_id} 不存在")
                return False
            
            if backup['Status'] != 'COMPLETED':
                print(f"错误: 备份状态为 {backup['Status']}，无法恢复")
                return False
            
            backup_files = backup.get('BackupFiles', {})
            
            if not backup_files:
                print("错误: 备份文件信息不存在")
                return False
            
            # 2. 确定要恢复的表
            tables_to_restore = tables if tables else list(backup_files.keys())
            
            # 3. 恢复每个表
            restored_count = 0
            for table_name in tables_to_restore:
                if table_name not in backup_files:
                    print(f"\n跳过 {table_name}: 备份中不存在")
                    continue
                
                backup_file = backup_files[table_name]
                
                if not os.path.exists(backup_file):
                    print(f"\n跳过 {table_name}: 备份文件不存在")
                    continue
                
                print(f"\n恢复表: {table_name}...", end='')
                
                try:
                    # 读取备份数据
                    with open(backup_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    if not data:
                        print(" 备份为空")
                        continue
                    
                    # 清空当前表数据（谨慎操作！）
                    cur.execute(f"TRUNCATE TABLE {table_name}")
                    conn.commit()
                    
                    # 插入备份数据
                    columns = list(data[0].keys())
                    placeholders = ', '.join(['%s'] * len(columns))
                    insert_sql = f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders})"
                    
                    for row in data:
                        values = [row.get(col) for col in columns]
                        cur.execute(insert_sql, values)
                    
                    conn.commit()
                    
                    print(f" 恢复 {len(data)} 条记录")
                    restored_count += 1
                    
                except Exception as e:
                    print(f" 失败: {e}")
                    conn.rollback()
            
            print(f"\n{'='*60}")
            print(f"数据恢复完成！")
            print(f"已恢复 {restored_count} 个表")
            print(f"{'='*60}\n")
            
            return True
            
        except Exception as e:
            print(f"\n恢复失败: {e}")
            conn.rollback()
            return False
            
        finally:
            cur.close()
            conn.close()


def create_backup(trigger='MANUAL', description=None):
    """便捷函数：创建备份"""
    manager = BackupManager()
    return manager.create_full_backup(trigger=trigger, description=description)


def list_backups(limit=20):
    """便捷函数：列出备份"""
    manager = BackupManager()
    backups = manager.get_backup_list(limit=limit)
    
    if backups:
        print(f"\n{'='*80}")
        print(f"备份列表（最近 {len(backups)} 个）")
        print(f"{'='*80}")
        print(f"{'ID':<8} {'时间':<20} {'类型':<12} {'触发':<15} {'状态':<10} {'大小':<12}")
        print(f"{'-'*80}")
        
        for backup in backups:
            backup_id = backup['BackupID']
            backup_time = backup['BackupTime'].strftime('%Y-%m-%d %H:%M:%S')
            backup_type = backup['BackupType']
            trigger = backup['BackupTrigger']
            status = backup['Status']
            size_mb = backup['BackupSize'] / 1024 / 1024 if backup['BackupSize'] else 0
            
            print(f"{backup_id:<8} {backup_time:<20} {backup_type:<12} {trigger:<15} {status:<10} {size_mb:.2f} MB")
        
        print(f"{'='*80}\n")
    else:
        print("\n暂无备份记录\n")
    
    return backups


def restore_backup(backup_id):
    """便捷函数：恢复备份"""
    manager = BackupManager()
    return manager.restore_from_backup(backup_id)


if __name__ == '__main__':
    # 测试备份功能
    print("测试备份管理器...")
    
    # 创建备份
    backup_id = create_backup(trigger='MANUAL', description='测试备份')
    
    # 列出备份
    list_backups()

