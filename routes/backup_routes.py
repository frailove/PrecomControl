"""
备份与同步管理路由
提供备份、同步、恢复的Web界面和API
"""
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash, current_app
from datetime import datetime
import sys
import os

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import create_connection
from utils.backup_manager import BackupManager
from utils.sync_manager import SyncManager
from utils.data_cleaner import DataCleaner
from utils.restore_manager import RestoreManager
from utils.auth_decorators import login_required, permission_required
import os
import sys
from werkzeug.utils import secure_filename

# 创建Blueprint
backup_bp = Blueprint('backup', __name__, url_prefix='/backup')


@backup_bp.route('/')
@login_required
@permission_required('backup.manage')
def index():
    """备份与同步管理主页"""
    manager = BackupManager()
    last_backup_time = None
    try:
        backups = manager.get_backup_list(limit=1)
        if backups:
            last_backup_time = backups[0]['BackupTime'].strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        pass

    sync_last_time = None
    try:
        conn = create_connection()
        cur = conn.cursor()
        cur.execute("SELECT SyncTime FROM SyncLog ORDER BY SyncTime DESC LIMIT 1")
        row = cur.fetchone()
        if row and row[0]:
            sync_last_time = row[0].strftime('%Y-%m-%d %H:%M:%S')
        cur.close()
        conn.close()
    except Exception:
        pass

    return render_template(
        'backup/index.html',
        active_page='backup',
        backups_last_time=last_backup_time,
        sync_last_time=sync_last_time
    )


@backup_bp.route('/list')
@login_required
@permission_required('backup.manage')
def backup_list():
    """备份列表页面"""
    try:
        manager = BackupManager()
        backups = manager.get_backup_list(limit=50)
        return render_template('backup/list.html', backups=backups, active_page='backup')
    except Exception as e:
        flash(f'加载备份列表失败: {str(e)}', 'error')
        return redirect(url_for('backup.index'))


@backup_bp.route('/sync-logs')
@login_required
@permission_required('backup.manage')
def sync_logs():
    """同步日志页面"""
    try:
        conn = create_connection()
        cur = conn.cursor(buffered=True, dictionary=True)
        
        cur.execute("""
            SELECT 
                SyncID, SyncTime, SyncType, RecordsAdded, RecordsUpdated,
                RecordsDeleted, RecordsSkipped, Status, Duration
            FROM SyncLog
            ORDER BY SyncTime DESC
            LIMIT 50
        """)
        logs = cur.fetchall()
        
        cur.close()
        conn.close()
        
        return render_template('backup/sync_logs.html', logs=logs, active_page='backup')
    except Exception as e:
        flash(f'加载同步日志失败: {str(e)}', 'error')
        return redirect(url_for('backup.index'))


@backup_bp.route('/statistics')
@login_required
@permission_required('backup.manage')
def statistics():
    """数据统计页面"""
    try:
        cleaner = DataCleaner()
        stats = cleaner.get_cleanup_statistics()
        return render_template('backup/statistics.html', stats=stats, active_page='backup')
    except Exception as e:
        flash(f'加载统计信息失败: {str(e)}', 'error')
        return redirect(url_for('backup.index'))


# ==================== API接口 ====================

@backup_bp.route('/api/create-backup', methods=['POST'])
@login_required
@permission_required('backup.manage')
def api_create_backup():
    """API: 创建备份"""
    try:
        data = request.get_json() or {}
        description = data.get('description', '手动备份')
        
        manager = BackupManager()
        backup_id = manager.create_full_backup(
            trigger='MANUAL',
            description=description,
            backup_by='USER'
        )
        
        return jsonify({
            'success': True,
            'backup_id': backup_id,
            'message': f'备份创建成功，备份ID: {backup_id}'
        })
    except Exception as e:
        current_app.logger.error(f"创建备份失败: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'message': '备份失败，请稍后重试'
        }), 500


@backup_bp.route('/api/sync', methods=['POST'])
@login_required
@permission_required('backup.manage')
def api_sync():
    """API: 执行同步（仅主数据同步）"""
    try:
        data = request.get_json() or {}
        backup_id = data.get('backup_id')
        
        manager = SyncManager()
        sync_id = manager.sync_after_welding_import(backup_id=backup_id)
        
        return jsonify({
            'success': True,
            'sync_id': sync_id,
            'message': f'同步完成，同步ID: {sync_id}'
        })
    except Exception as e:
        current_app.logger.error(f"数据同步失败: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'message': '同步失败，请稍后重试'
        }), 500


@backup_bp.route('/api/run-pipeline', methods=['POST'])
@login_required
@permission_required('backup.manage')
def api_run_pipeline():
    """API: 运行完整的数据同步流水线"""
    try:
        # 导入数据同步流水线模块
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from maintenance.data_sync_pipeline import run_data_sync_pipeline
        
        # 获取参数
        data = request.form.to_dict() if request.form else (request.get_json() or {})
        
        # 处理Excel文件上传
        excel_path = None
        if 'excel_file' in request.files:
            file = request.files['excel_file']
            if file and file.filename:
                # 保存上传的文件
                upload_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'uploads', 'temp')
                os.makedirs(upload_dir, exist_ok=True)
                filename = secure_filename(file.filename)
                excel_path = os.path.join(upload_dir, filename)
                file.save(excel_path)
        else:
            # 使用默认路径或参数中的路径（目录会自动查找所有 WeldingDB_*.xlsx 文件）
            excel_path = data.get('excel_path', '').strip() if data.get('excel_path') else ''
            if not excel_path:
                # 如果为空，使用默认的 nordinfo 目录
                project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                excel_path = os.path.join(project_root, 'nordinfo')
            # 确保是字符串类型
            excel_path = str(excel_path)
        
        # 获取其他参数
        trigger = data.get('trigger', 'MANUAL')
        description = data.get('description', f'Web界面触发 - {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
        skip_backup = data.get('skip_backup', 'false').lower() == 'true'
        skip_cleanup = data.get('skip_cleanup', 'false').lower() == 'true'
        cleanup_keep_days = int(data.get('cleanup_keep_days', 90))
        cleanup_permanent_delete = data.get('cleanup_permanent_delete', 'false').lower() == 'true'
        verbose_import = data.get('verbose_import', 'false').lower() == 'true'
        
        # 运行流水线
        summary = run_data_sync_pipeline(
            excel_path=excel_path,
            trigger=trigger,
            description=description,
            skip_backup=skip_backup,
            skip_cleanup=skip_cleanup,
            cleanup_keep_days=cleanup_keep_days,
            cleanup_permanent_delete=cleanup_permanent_delete,
            verbose_import=verbose_import
        )
        
        return jsonify({
            'success': True,
            'message': '数据同步流水线执行完成',
            'summary': summary
        })
    except FileNotFoundError as e:
        current_app.logger.warning(f"流水线执行失败，文件未找到: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'message': '文件未找到，请检查上传或配置的路径'
        }), 400
    except Exception as e:
        import traceback
        current_app.logger.error(f"数据同步流水线执行失败: {e}\n{traceback.format_exc()}", exc_info=False)
        return jsonify({
            'success': False,
            'message': '流水线执行失败，请联系管理员查看服务器日志'
        }), 500


@backup_bp.route('/api/restore/<int:backup_id>', methods=['POST'])
@login_required
@permission_required('backup.manage')
def api_restore(backup_id):
    """API: 恢复备份"""
    try:
        data = request.get_json() or {}
        tables = data.get('tables')  # 可选，指定要恢复的表
        preview = data.get('preview', True)  # 默认预览模式
        
        manager = RestoreManager()
        
        if preview:
            # 预览模式
            backup = manager.backup_manager.get_backup_details(backup_id)
            return jsonify({
                'success': True,
                'preview': True,
                'backup': {
                    'backup_id': backup_id,
                    'backup_time': backup['BackupTime'].strftime('%Y-%m-%d %H:%M:%S'),
                    'welding_count': backup['WeldingListCount'],
                    'package_count': backup['TestPackageCount'],
                    'system_count': backup['SystemCount'],
                    'subsystem_count': backup['SubsystemCount']
                },
                'message': '预览模式：显示将要恢复的内容'
            })
        else:
            # 实际恢复
            success = manager.restore_by_backup_id(backup_id, tables=tables, preview=False)
            
            if success:
                return jsonify({
                    'success': True,
                    'message': f'数据恢复成功（备份ID: {backup_id}）'
                })
            else:
                return jsonify({
                    'success': False,
                    'message': '数据恢复失败'
                }), 500
    except Exception as e:
        current_app.logger.error(f"数据恢复失败: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'message': '恢复失败，请稍后重试或联系管理员'
        }), 500


@backup_bp.route('/api/clean-data', methods=['POST'])
@login_required
@permission_required('backup.manage')
def api_clean_data():
    """API: 清理数据"""
    try:
        data = request.get_json() or {}
        days_to_keep = data.get('days_to_keep', 90)
        permanent_delete = data.get('permanent_delete', False)
        
        cleaner = DataCleaner()
        cleaner.clean_all(days_to_keep=days_to_keep, permanent_delete=permanent_delete)
        
        return jsonify({
            'success': True,
            'message': '数据清理完成'
        })
    except Exception as e:
        current_app.logger.error(f"数据清理失败: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'message': '清理失败，请稍后重试'
        }), 500


@backup_bp.route('/api/backup/<int:backup_id>')
@login_required
@permission_required('backup.manage')
def api_backup_detail(backup_id):
    """API: 获取备份详情"""
    try:
        manager = BackupManager()
        backup = manager.get_backup_details(backup_id)
        
        if not backup:
            return jsonify({
                'success': False,
                'message': '备份不存在'
            }), 404
        
        # 转换datetime为字符串
        backup_data = {
            'backup_id': backup['BackupID'],
            'backup_type': backup['BackupType'],
            'backup_trigger': backup['BackupTrigger'],
            'backup_time': backup['BackupTime'].strftime('%Y-%m-%d %H:%M:%S'),
            'backup_by': backup['BackupBy'],
            'welding_count': backup['WeldingListCount'],
            'package_count': backup['TestPackageCount'],
            'system_count': backup['SystemCount'],
            'subsystem_count': backup['SubsystemCount'],
            'backup_size': backup['BackupSize'],
            'status': backup['Status'],
            'description': backup.get('Description')
        }
        
        return jsonify({
            'success': True,
            'backup': backup_data
        })
    except Exception as e:
        current_app.logger.error(f"获取备份详情失败: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'message': '获取备份详情失败，请稍后重试'
        }), 500


@backup_bp.route('/api/sync/<int:sync_id>')
@login_required
@permission_required('backup.manage')
def api_sync_detail(sync_id):
    """API: 获取同步详情"""
    try:
        from database import create_connection
        conn = create_connection()
        cur = conn.cursor(buffered=True, dictionary=True)
        
        cur.execute("""
            SELECT * FROM SyncLog WHERE SyncID = %s
        """, (sync_id,))
        sync = cur.fetchone()
        
        cur.close()
        conn.close()
        
        if not sync:
            return jsonify({
                'success': False,
                'message': '同步记录不存在'
            }), 404
        
        # 转换datetime为字符串
        sync_data = {
            'sync_id': sync['SyncID'],
            'sync_time': sync['SyncTime'].strftime('%Y-%m-%d %H:%M:%S'),
            'sync_type': sync['SyncType'],
            'records_added': sync['RecordsAdded'],
            'records_updated': sync['RecordsUpdated'],
            'records_deleted': sync['RecordsDeleted'],
            'records_skipped': sync['RecordsSkipped'],
            'status': sync['Status'],
            'duration': sync.get('Duration'),
            'details': sync.get('DetailsJSON')
        }
        
        return jsonify({
            'success': True,
            'sync': sync_data
        })
    except Exception as e:
        current_app.logger.error(f"获取同步详情失败: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'message': '获取同步详情失败，请稍后重试'
        }), 500

