"""
数据清理模块
处理孤立记录清理、历史数据归档、日志清理等
"""
import os
import sys
from datetime import datetime, timedelta

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import create_connection


class DataCleaner:
    """数据清理器"""
    
    def __init__(self):
        pass
    
    def clean_all(self, days_to_keep=90, permanent_delete=False):
        """
        执行完整清理流程
        
        Args:
            days_to_keep: 保留最近N天的软删除记录
            permanent_delete: 是否永久删除（真删除）
        """
        print(f"\n{'='*60}")
        print(f"开始数据清理...")
        print(f"{'='*60}")
        
        # 1. 清理孤立记录
        print(f"\n[1/4] 清理孤立记录...")
        self.clean_orphaned_records()
        
        # 2. 清理旧的软删除记录
        print(f"\n[2/4] 清理旧的软删除记录（保留 {days_to_keep} 天）...")
        self.clean_old_deleted_records(days_to_keep, permanent_delete)
        
        # 3. 清理旧的同步日志
        print(f"\n[3/4] 清理旧的同步日志（保留 {days_to_keep} 天）...")
        self.clean_old_logs(days_to_keep)
        
        # 4. 清理旧的备份
        print(f"\n[4/4] 清理旧的备份文件（保留 30 天）...")
        from utils.backup_manager import BackupManager
        backup_manager = BackupManager()
        backup_manager.delete_old_backups(keep_days=30, keep_count=10)
        
        print(f"\n{'='*60}")
        print(f"数据清理完成！")
        print(f"{'='*60}\n")
    
    def clean_orphaned_records(self):
        """
        清理孤立记录
        
        孤立记录定义：
        1. JointSummary中的试压包在HydroTestPackageList中不存在或已删除
        2. NDEPWHTStatus中的试压包在HydroTestPackageList中不存在或已删除
        3. ISODrawingList中的试压包在HydroTestPackageList中不存在或已删除
        """
        conn = create_connection()
        cur = conn.cursor(buffered=True, dictionary=True)
        
        try:
            total_cleaned = 0
            
            # 1. 清理孤立的 JointSummary 记录
            cur.execute("""
                DELETE js FROM JointSummary js
                LEFT JOIN HydroTestPackageList hp 
                    ON js.TestPackageID = hp.TestPackageID AND hp.IsDeleted = FALSE
                WHERE hp.TestPackageID IS NULL
            """)
            conn.commit()
            count = cur.rowcount
            total_cleaned += count
            print(f"  清理 JointSummary 孤立记录: {count} 条")
            
            # 2. 清理孤立的 NDEPWHTStatus 记录
            cur.execute("""
                DELETE nde FROM NDEPWHTStatus nde
                LEFT JOIN HydroTestPackageList hp 
                    ON nde.TestPackageID = hp.TestPackageID AND hp.IsDeleted = FALSE
                WHERE hp.TestPackageID IS NULL
            """)
            conn.commit()
            count = cur.rowcount
            total_cleaned += count
            print(f"  清理 NDEPWHTStatus 孤立记录: {count} 条")
            
            # 3. 清理孤立的 ISODrawingList 记录
            cur.execute("""
                DELETE iso FROM ISODrawingList iso
                LEFT JOIN HydroTestPackageList hp 
                    ON iso.TestPackageID = hp.TestPackageID AND hp.IsDeleted = FALSE
                WHERE hp.TestPackageID IS NULL
            """)
            conn.commit()
            count = cur.rowcount
            total_cleaned += count
            print(f"  清理 ISODrawingList 孤立记录: {count} 条")
            
            print(f"\n  总计清理孤立记录: {total_cleaned} 条")
            
        except Exception as e:
            print(f"  清理孤立记录失败: {e}")
            conn.rollback()
            
        finally:
            cur.close()
            conn.close()
    
    def clean_old_deleted_records(self, days_to_keep=90, permanent_delete=False):
        """
        清理旧的软删除记录
        
        Args:
            days_to_keep: 保留最近N天的软删除记录
            permanent_delete: 是否永久删除（True）还是仅统计（False）
        """
        conn = create_connection()
        cur = conn.cursor(buffered=True, dictionary=True)
        
        try:
            cutoff_date = datetime.now() - timedelta(days=days_to_keep)
            total_cleaned = 0
            
            tables = [
                ('WeldingList', 'WeldID'),
                ('HydroTestPackageList', 'TestPackageID'),
                ('SystemList', 'SystemCode'),
                ('SubsystemList', 'SubSystemCode')
            ]
            
            for table_name, id_field in tables:
                if permanent_delete:
                    # 真删除
                    cur.execute(f"""
                        DELETE FROM {table_name}
                        WHERE IsDeleted = TRUE 
                          AND DeletedTime < %s
                    """, (cutoff_date,))
                    conn.commit()
                    count = cur.rowcount
                    print(f"  永久删除 {table_name}: {count} 条记录")
                else:
                    # 仅统计
                    cur.execute(f"""
                        SELECT COUNT(*) as count
                        FROM {table_name}
                        WHERE IsDeleted = TRUE 
                          AND DeletedTime < %s
                    """, (cutoff_date,))
                    result = cur.fetchone()
                    count = result['count'] if result else 0
                    print(f"  {table_name} 可清理记录: {count} 条")
                
                total_cleaned += count
            
            if permanent_delete:
                print(f"\n  总计永久删除: {total_cleaned} 条")
            else:
                print(f"\n  总计可清理: {total_cleaned} 条（当前仅统计，未实际删除）")
                print(f"  提示：要永久删除这些记录，请调用 clean_old_deleted_records(permanent_delete=True)")
            
        except Exception as e:
            print(f"  清理软删除记录失败: {e}")
            conn.rollback()
            
        finally:
            cur.close()
            conn.close()
    
    def clean_old_logs(self, days_to_keep=90):
        """
        清理旧的同步日志和变更日志
        
        Args:
            days_to_keep: 保留最近N天的日志
        """
        conn = create_connection()
        cur = conn.cursor(buffered=True, dictionary=True)
        
        try:
            cutoff_date = datetime.now() - timedelta(days=days_to_keep)
            total_cleaned = 0
            
            # 1. 清理旧的变更日志
            cur.execute("""
                DELETE FROM ChangeLog
                WHERE ChangeTime < %s
            """, (cutoff_date,))
            conn.commit()
            count = cur.rowcount
            total_cleaned += count
            print(f"  清理 ChangeLog: {count} 条")
            
            # 2. 清理旧的同步日志（保留成功的，删除失败的旧记录）
            cur.execute("""
                DELETE FROM SyncLog
                WHERE SyncTime < %s AND Status = 'FAILED'
            """, (cutoff_date,))
            conn.commit()
            count = cur.rowcount
            total_cleaned += count
            print(f"  清理 SyncLog（失败的）: {count} 条")
            
            print(f"\n  总计清理日志: {total_cleaned} 条")
            
        except Exception as e:
            print(f"  清理日志失败: {e}")
            conn.rollback()
            
        finally:
            cur.close()
            conn.close()
    
    def vacuum_database(self):
        """
        优化数据库（MySQL）
        
        注意：MySQL使用OPTIMIZE TABLE来回收空间
        """
        conn = create_connection()
        cur = conn.cursor(buffered=True)
        
        try:
            print(f"\n{'='*60}")
            print(f"优化数据库...")
            print(f"{'='*60}\n")
            
            tables = [
                'WeldingList',
                'HydroTestPackageList',
                'SystemList',
                'SubsystemList',
                'JointSummary',
                'NDEPWHTStatus',
                'ISODrawingList',
                'ChangeLog',
                'SyncLog',
                'DataBackup'
            ]
            
            for table_name in tables:
                print(f"  优化表: {table_name}...", end='')
                try:
                    cur.execute(f"OPTIMIZE TABLE {table_name}")
                    conn.commit()
                    print(" 完成")
                except Exception as e:
                    print(f" 失败: {e}")
            
            print(f"\n{'='*60}")
            print(f"数据库优化完成！")
            print(f"{'='*60}\n")
            
        except Exception as e:
            print(f"\n数据库优化失败: {e}")
            
        finally:
            cur.close()
            conn.close()
    
    def get_cleanup_statistics(self):
        """
        获取清理统计信息
        
        Returns:
            dict: 统计信息
        """
        conn = create_connection()
        cur = conn.cursor(buffered=True, dictionary=True)
        
        try:
            stats = {}
            
            # 1. 软删除记录统计
            tables = [
                ('WeldingList', 'WeldID'),
                ('HydroTestPackageList', 'TestPackageID'),
                ('SystemList', 'SystemCode'),
                ('SubsystemList', 'SubSystemCode')
            ]
            
            stats['deleted_records'] = {}
            for table_name, id_field in tables:
                cur.execute(f"""
                    SELECT 
                        COUNT(*) as total,
                        COUNT(CASE WHEN IsDeleted = TRUE THEN 1 END) as deleted
                    FROM {table_name}
                """)
                result = cur.fetchone()
                stats['deleted_records'][table_name] = result
            
            # 2. 孤立记录统计
            stats['orphaned_records'] = {}
            
            # JointSummary孤立记录
            cur.execute("""
                SELECT COUNT(*) as count
                FROM JointSummary js
                LEFT JOIN HydroTestPackageList hp 
                    ON js.TestPackageID = hp.TestPackageID AND hp.IsDeleted = FALSE
                WHERE hp.TestPackageID IS NULL
            """)
            stats['orphaned_records']['JointSummary'] = cur.fetchone()['count']
            
            # NDEPWHTStatus孤立记录
            cur.execute("""
                SELECT COUNT(*) as count
                FROM NDEPWHTStatus nde
                LEFT JOIN HydroTestPackageList hp 
                    ON nde.TestPackageID = hp.TestPackageID AND hp.IsDeleted = FALSE
                WHERE hp.TestPackageID IS NULL
            """)
            stats['orphaned_records']['NDEPWHTStatus'] = cur.fetchone()['count']
            
            # ISODrawingList孤立记录
            cur.execute("""
                SELECT COUNT(*) as count
                FROM ISODrawingList iso
                LEFT JOIN HydroTestPackageList hp 
                    ON iso.TestPackageID = hp.TestPackageID AND hp.IsDeleted = FALSE
                WHERE hp.TestPackageID IS NULL
            """)
            stats['orphaned_records']['ISODrawingList'] = cur.fetchone()['count']
            
            # 3. 日志统计
            cur.execute("SELECT COUNT(*) as count FROM SyncLog")
            stats['sync_log_count'] = cur.fetchone()['count']
            
            cur.execute("SELECT COUNT(*) as count FROM ChangeLog")
            stats['change_log_count'] = cur.fetchone()['count']
            
            cur.execute("SELECT COUNT(*) as count FROM DataBackup")
            stats['backup_count'] = cur.fetchone()['count']
            
            return stats
            
        finally:
            cur.close()
            conn.close()


def print_cleanup_stats():
    """打印清理统计信息"""
    cleaner = DataCleaner()
    stats = cleaner.get_cleanup_statistics()
    
    print(f"\n{'='*60}")
    print(f"数据清理统计信息")
    print(f"{'='*60}\n")
    
    print("1. 软删除记录统计：")
    for table_name, data in stats['deleted_records'].items():
        total = data['total']
        deleted = data['deleted']
        percent = (deleted / total * 100) if total > 0 else 0
        print(f"   {table_name:<30}: {deleted:>6}/{total:<6} ({percent:.1f}%)")
    
    print("\n2. 孤立记录统计：")
    for table_name, count in stats['orphaned_records'].items():
        print(f"   {table_name:<30}: {count:>6} 条")
    
    print("\n3. 日志统计：")
    print(f"   SyncLog（同步日志）             : {stats['sync_log_count']:>6} 条")
    print(f"   ChangeLog（变更日志）           : {stats['change_log_count']:>6} 条")
    print(f"   DataBackup（备份记录）          : {stats['backup_count']:>6} 条")
    
    print(f"\n{'='*60}\n")


def clean_all_data(days_to_keep=90, permanent_delete=False):
    """便捷函数：执行完整清理"""
    cleaner = DataCleaner()
    cleaner.clean_all(days_to_keep=days_to_keep, permanent_delete=permanent_delete)


if __name__ == '__main__':
    # 测试清理功能
    print("数据清理工具\n")
    
    # 1. 显示统计信息
    print_cleanup_stats()
    
    # 2. 执行清理（不永久删除）
    clean_all_data(days_to_keep=90, permanent_delete=False)

