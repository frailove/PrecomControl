"""
统一数据同步流水线脚本
步骤：备份 -> 焊口导入 -> 主数据同步 -> 聚合刷新 -> 数据清理
"""
import argparse
import json
import os
from datetime import datetime

from database import create_welding_table
from welding_importer import WeldingDataImporter
from utils.backup_manager import create_backup
from utils.sync_manager import sync_after_import
from utils.refresh_aggregated_data import refresh_all_packages_aggregated_data
from utils.data_cleaner import DataCleaner


def run_data_sync_pipeline(
    excel_path,
    trigger='SCHEDULED',
    description=None,
    skip_backup=False,
    skip_cleanup=False,
    cleanup_keep_days=90,
    cleanup_permanent_delete=False,
    verbose_import=False
):
    """
    运行完整的数据同步流水线
    """
    summary = {
        'excel_path': excel_path,
        'trigger': trigger,
        'started_at': datetime.now().isoformat(timespec='seconds')
    }
    
    if not os.path.exists(excel_path):
        raise FileNotFoundError(f"找不到焊接数据源文件: {excel_path}")
    
    print("\n" + "=" * 70)
    print("数据同步流水线启动")
    print("=" * 70)
    
    backup_id = None
    if skip_backup:
        print("\n[1/5] 跳过备份步骤（按参数配置）")
    else:
        print("\n[1/5] 创建导入前备份...")
        backup_id = create_backup(
            trigger=trigger or 'SCHEDULED',
            description=description or f'自动备份 - {datetime.now():%Y-%m-%d %H:%M:%S}'
        )
        summary['backup_id'] = backup_id
    
    print("\n[2/5] 导入最新 WeldingList 数据...")
    create_welding_table()
    importer = WeldingDataImporter(excel_path, verbose=verbose_import)
    if not importer.import_to_database():
        raise RuntimeError("导入WeldingList失败，终止后续步骤。")
    summary['imported_rows'] = len(importer.df) if importer.df is not None else 0
    
    print("\n[3/5] 同步主数据（试压包 / 系统 / 子系统）...")
    sync_id = sync_after_import(backup_id=backup_id)
    summary['sync_id'] = sync_id
    
    print("\n[4/5] 刷新所有聚合表（JointSummary / NDEPWHTStatus / ISODrawingList）...")
    agg_stats = refresh_all_packages_aggregated_data(verbose=True)
    summary['aggregation'] = agg_stats
    
    if skip_cleanup:
        print("\n[5/5] 跳过清理步骤（按参数配置）")
    else:
        print("\n[5/5] 执行数据清理（孤立记录 / 软删除 / 日志 / 旧备份）...")
        cleaner = DataCleaner()
        cleaner.clean_all(days_to_keep=cleanup_keep_days, permanent_delete=cleanup_permanent_delete)
        summary['cleanup'] = {
            'days_to_keep': cleanup_keep_days,
            'permanent_delete': cleanup_permanent_delete
        }
    
    summary['finished_at'] = datetime.now().isoformat(timespec='seconds')
    print("\n" + "=" * 70)
    print("数据同步流水线完成")
    print("=" * 70)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    
    return summary


def parse_args():
    parser = argparse.ArgumentParser(description="运行数据同步与备份流水线")
    parser.add_argument(
        '--excel',
        default=r"C:\Projects\PrecomControl\nordinfo\WeldingDB_2.xlsx",
        help='WeldingList 数据Excel路径'
    )
    parser.add_argument('--trigger', default='SCHEDULED', help='备份触发来源描述')
    parser.add_argument('--description', help='备份描述')
    parser.add_argument('--skip-backup', action='store_true', help='跳过备份步骤')
    parser.add_argument('--skip-cleanup', action='store_true', help='跳过数据清理步骤')
    parser.add_argument('--cleanup-keep-days', type=int, default=90, help='清理时保留软删除记录的天数')
    parser.add_argument('--cleanup-permanent-delete', action='store_true', help='清理软删除记录时直接真删除')
    parser.add_argument('--verbose-import', action='store_true', help='导入时打印详细列映射信息')
    return parser.parse_args()


if __name__ == '__main__':
    args = parse_args()
    run_data_sync_pipeline(
        excel_path=args.excel,
        trigger=args.trigger,
        description=args.description,
        skip_backup=args.skip_backup,
        skip_cleanup=args.skip_cleanup,
        cleanup_keep_days=args.cleanup_keep_days,
        cleanup_permanent_delete=args.cleanup_permanent_delete,
        verbose_import=args.verbose_import
    )

