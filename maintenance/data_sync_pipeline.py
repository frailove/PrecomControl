"""
统一数据同步流水线脚本
步骤：备份 -> 焊口导入 -> 主数据同步 -> 聚合刷新 -> 数据清理
"""
import argparse
import json
import os
import sys
from datetime import datetime

# 确保可以从项目根目录导入 database / utils / welding_importer 等模块
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

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
    
    # excel_path 可以是文件、目录或通配符，resolve_welding_files 会处理
    # 如果为空，使用默认的 nordinfo 目录
    if not excel_path:
        # 获取项目根目录
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(current_dir)
        excel_path = os.path.join(project_root, 'nordinfo')
    
    # 确保 excel_path 是字符串类型
    excel_path = str(excel_path)
    
    # 这里只检查路径是否存在（文件或目录）
    if not os.path.exists(excel_path):
        raise FileNotFoundError(f"找不到焊接数据源路径: {excel_path}")
    
    # 强制刷新输出，确保实时显示
    import sys
    sys.stdout.flush()
    
    print("\n" + "=" * 70)
    print("数据同步流水线启动")
    print("=" * 70)
    sys.stdout.flush()
    
    backup_id = None
    if skip_backup:
        print("\n[1/5] 跳过备份步骤（按参数配置）")
        sys.stdout.flush()
    else:
        print("\n[1/5] 创建导入前备份...")
        sys.stdout.flush()
        backup_id = create_backup(
            trigger=trigger or 'SCHEDULED',
            description=description or f'自动备份 - {datetime.now():%Y-%m-%d %H:%M:%S}'
        )
        summary['backup_id'] = backup_id
        sys.stdout.flush()
    
    print("\n[2/5] 导入最新 WeldingList 数据...")
    sys.stdout.flush()
    # create_welding_table() 会确保 Block 字段存在（如果不存在则添加）
    create_welding_table()
    # 导入时会自动从 DrawingNumber 提取 Block 字段并填充
    importer = WeldingDataImporter(excel_path, verbose=verbose_import)
    if not importer.import_to_database():
        raise RuntimeError("导入WeldingList失败，终止后续步骤。")
    summary['imported_rows'] = len(importer.df) if importer.df is not None else 0
    sys.stdout.flush()
    
    print("\n[3/5] 同步主数据（试压包 / 系统 / 子系统）...")
    sys.stdout.flush()
    sync_id = sync_after_import(backup_id=backup_id)
    summary['sync_id'] = sync_id
    sys.stdout.flush()
    
    print("\n[4/5] 刷新所有聚合表（JointSummary / NDEPWHTStatus / ISODrawingList / SystemWeldingSummary / SubsystemWeldingSummary）...")
    sys.stdout.flush()
    agg_stats = refresh_all_packages_aggregated_data(verbose=True)
    summary['aggregation'] = agg_stats
    sys.stdout.flush()
    
    if skip_cleanup:
        print("\n[5/5] 跳过清理步骤（按参数配置）")
        sys.stdout.flush()
    else:
        print("\n[5/5] 执行数据清理（孤立记录 / 软删除 / 日志 / 旧备份）...")
        sys.stdout.flush()
        cleaner = DataCleaner()
        cleaner.clean_all(days_to_keep=cleanup_keep_days, permanent_delete=cleanup_permanent_delete)
        summary['cleanup'] = {
            'days_to_keep': cleanup_keep_days,
            'permanent_delete': cleanup_permanent_delete
        }
        sys.stdout.flush()
    
    summary['finished_at'] = datetime.now().isoformat(timespec='seconds')
    print("\n" + "=" * 70)
    print("数据同步流水线完成")
    print("=" * 70)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    sys.stdout.flush()
    
    return summary


def parse_args():
    parser = argparse.ArgumentParser(description="运行数据同步与备份流水线")
    parser.add_argument(
        '--excel',
        default=r"C:\Projects\PrecomControl\nordinfo",
        help='WeldingList 数据Excel路径或目录（目录会自动查找所有 WeldingDB_*.xlsx 文件）'
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

