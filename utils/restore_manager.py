"""
数据恢复管理模块
提供时间点恢复、选择性恢复、恢复预览等高级功能
"""
import os
import sys
from datetime import datetime

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import create_connection
from utils.backup_manager import BackupManager


class RestoreManager:
    """数据恢复管理器"""
    
    def __init__(self):
        self.backup_manager = BackupManager()
    
    def restore_to_time_point(self, target_time, tables=None, preview=False):
        """
        恢复到指定时间点
        
        Args:
            target_time: 目标时间（datetime对象或字符串 'YYYY-MM-DD HH:MM:SS'）
            tables: 要恢复的表列表（None表示所有表）
            preview: 是否仅预览（不实际执行）
            
        Returns:
            bool: 恢复是否成功
        """
        # 转换时间格式
        if isinstance(target_time, str):
            target_time = datetime.strptime(target_time, '%Y-%m-%d %H:%M:%S')
        
        print(f"\n{'='*60}")
        print(f"恢复到时间点: {target_time}")
        print(f"{'='*60}")
        
        # 1. 查找最接近的备份
        backup = self._find_closest_backup(target_time)
        
        if not backup:
            print(f"\n错误: 未找到在 {target_time} 之前的备份")
            return False
        
        backup_id = backup['BackupID']
        backup_time = backup['BackupTime']
        
        print(f"\n找到最接近的备份:")
        print(f"  备份ID: {backup_id}")
        print(f"  备份时间: {backup_time}")
        print(f"  时间差: {target_time - backup_time}")
        
        if preview:
            print(f"\n预览模式：以下是将要恢复的内容")
            print(f"  WeldingList: {backup['WeldingListCount']} 条记录")
            print(f"  HydroTestPackageList: {backup['TestPackageCount']} 条记录")
            print(f"  SystemList: {backup['SystemCount']} 条记录")
            print(f"  SubsystemList: {backup['SubsystemCount']} 条记录")
            print(f"\n提示: 要实际执行恢复，请设置 preview=False")
            return True
        
        # 2. 执行恢复
        print(f"\n开始恢复...")
        return self.backup_manager.restore_from_backup(backup_id, tables=tables)
    
    def restore_by_backup_id(self, backup_id, tables=None, preview=False):
        """
        从指定备份ID恢复
        
        Args:
            backup_id: 备份ID
            tables: 要恢复的表列表
            preview: 是否仅预览
            
        Returns:
            bool: 恢复是否成功
        """
        backup = self.backup_manager.get_backup_details(backup_id)
        
        if not backup:
            print(f"错误: 备份 {backup_id} 不存在")
            return False
        
        print(f"\n{'='*60}")
        print(f"从备份恢复: {backup_id}")
        print(f"备份时间: {backup['BackupTime']}")
        print(f"{'='*60}")
        
        if preview:
            print(f"\n预览模式：以下是将要恢复的内容")
            print(f"  WeldingList: {backup['WeldingListCount']} 条记录")
            print(f"  HydroTestPackageList: {backup['TestPackageCount']} 条记录")
            print(f"  SystemList: {backup['SystemCount']} 条记录")
            print(f"  SubsystemList: {backup['SubsystemCount']} 条记录")
            print(f"\n提示: 要实际执行恢复，请设置 preview=False")
            return True
        
        return self.backup_manager.restore_from_backup(backup_id, tables=tables)
    
    def compare_with_backup(self, backup_id):
        """
        比较当前数据与备份数据的差异
        
        Args:
            backup_id: 备份ID
            
        Returns:
            dict: 差异统计
        """
        conn = create_connection()
        cur = conn.cursor(buffered=True, dictionary=True)
        
        try:
            backup = self.backup_manager.get_backup_details(backup_id)
            
            if not backup:
                print(f"错误: 备份 {backup_id} 不存在")
                return None
            
            print(f"\n{'='*60}")
            print(f"比较当前数据与备份 {backup_id}")
            print(f"备份时间: {backup['BackupTime']}")
            print(f"{'='*60}\n")
            
            differences = {}
            
            # 比较记录数
            tables_to_compare = [
                ('WeldingList', 'WeldingListCount'),
                ('HydroTestPackageList', 'TestPackageCount'),
                ('SystemList', 'SystemCount'),
                ('SubsystemList', 'SubsystemCount')
            ]
            
            for table_name, backup_field in tables_to_compare:
                # 当前记录数
                cur.execute(f"SELECT COUNT(*) as count FROM {table_name} WHERE IsDeleted = FALSE")
                current_count = cur.fetchone()['count']
                
                # 备份记录数
                backup_count = backup.get(backup_field, 0)
                
                # 差异
                diff = current_count - backup_count
                diff_percent = (diff / backup_count * 100) if backup_count > 0 else 0
                
                differences[table_name] = {
                    'current': current_count,
                    'backup': backup_count,
                    'difference': diff,
                    'diff_percent': diff_percent
                }
                
                # 显示差异
                sign = '+' if diff > 0 else ''
                print(f"{table_name:<30}: {current_count:>6} (备份: {backup_count:>6}, 差异: {sign}{diff:>6}, {sign}{diff_percent:>6.1f}%)")
            
            print(f"\n{'='*60}\n")
            
            return differences
            
        finally:
            cur.close()
            conn.close()
    
    def list_available_backups(self, limit=20):
        """
        列出可用的备份
        
        Args:
            limit: 显示数量限制
            
        Returns:
            list: 备份列表
        """
        return self.backup_manager.get_backup_list(limit=limit)
    
    def _find_closest_backup(self, target_time):
        """
        查找最接近目标时间的备份（且备份时间早于目标时间）
        
        Args:
            target_time: 目标时间
            
        Returns:
            dict: 备份记录
        """
        conn = create_connection()
        cur = conn.cursor(buffered=True, dictionary=True)
        
        try:
            cur.execute("""
                SELECT * FROM DataBackup
                WHERE BackupTime <= %s
                  AND Status = 'COMPLETED'
                ORDER BY BackupTime DESC
                LIMIT 1
            """, (target_time,))
            
            return cur.fetchone()
            
        finally:
            cur.close()
            conn.close()
    
    def create_restore_point(self, description=None):
        """
        创建还原点（实际上是创建一个备份）
        
        Args:
            description: 还原点描述
            
        Returns:
            backup_id: 备份ID
        """
        print(f"\n创建还原点...")
        
        if not description:
            description = f"还原点 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        backup_id = self.backup_manager.create_full_backup(
            trigger='MANUAL',
            description=description,
            backup_by='USER'
        )
        
        print(f"还原点已创建，备份ID: {backup_id}")
        
        return backup_id
    
    def restore_deleted_data(self, table_name, record_id):
        """
        恢复被软删除的数据
        
        Args:
            table_name: 表名
            record_id: 记录ID
            
        Returns:
            bool: 恢复是否成功
        """
        from utils.sync_manager import SyncManager
        sync_manager = SyncManager()
        return sync_manager.restore_deleted_record(table_name, record_id)


def restore_to_time(target_time, tables=None, preview=True):
    """便捷函数：恢复到时间点"""
    manager = RestoreManager()
    return manager.restore_to_time_point(target_time, tables=tables, preview=preview)


def restore_backup(backup_id, tables=None, preview=True):
    """便捷函数：从备份恢复"""
    manager = RestoreManager()
    return manager.restore_by_backup_id(backup_id, tables=tables, preview=preview)


def compare_backup(backup_id):
    """便捷函数：比较与备份的差异"""
    manager = RestoreManager()
    return manager.compare_with_backup(backup_id)


def create_restore_point(description=None):
    """便捷函数：创建还原点"""
    manager = RestoreManager()
    return manager.create_restore_point(description=description)


if __name__ == '__main__':
    # 测试恢复功能
    print("数据恢复工具测试\n")
    
    manager = RestoreManager()
    
    # 1. 列出可用备份
    print("可用备份列表:")
    from utils.backup_manager import list_backups
    list_backups(limit=10)
    
    # 2. 比较与最新备份的差异
    backups = manager.list_available_backups(limit=1)
    if backups:
        latest_backup_id = backups[0]['BackupID']
        print(f"\n比较与最新备份的差异:")
        compare_backup(latest_backup_id)

