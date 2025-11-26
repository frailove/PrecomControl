from flask import Blueprint, request, render_template, jsonify, redirect, url_for, send_file, current_app
from database import create_connection, ensure_precom_tables
from models.system import SystemModel
from models.subsystem import SubsystemModel
from werkzeug.utils import secure_filename
from datetime import datetime
from io import BytesIO
import os
import re
import pandas as pd


precom_bp = Blueprint('precom', __name__)

PRECOM_UPLOAD_FOLDER = 'uploads/precom_tasks'
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'xlsx', 'xls', 'doc', 'docx', 'zip'}

from importlib import import_module

try:
    # 通过动态导入避免静态检查器对可选依赖报错
    magic = import_module("magic")  # type: ignore[assignment]
except ImportError:
    magic = None

TASK_TYPE_LABELS = {
    'Manhole': '人孔检查',
    'MotorSolo': '电机单试',
    'SkidInstall': '仪表台件安装',
    'LoopTest': '回路测试',
    'Alignment': '动设备最终对中',
    'MRT': 'MRT 机械联动测试',
    'FunctionTest': 'Function Test',
}


def _allowed_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def _validate_precom_upload_file(file) -> tuple[bool, str | None]:
    """验证预试车附件上传文件的扩展名、MIME 和大小。"""
    if not file or not file.filename:
        return False, "未选择文件"

    if not _allowed_file(file.filename):
        return False, "不允许的文件类型"

    max_size_bytes = 50 * 1024 * 1024
    try:
        pos = file.stream.tell()
        file.stream.seek(0, os.SEEK_END)
        size = file.stream.tell()
        file.stream.seek(pos)
    except Exception:
        size = None
    if size is not None and size > max_size_bytes:
        return False, "单个文件大小不能超过 50MB"

    if magic is not None:
        try:
            pos = file.stream.tell()
            sample = file.stream.read(2048)
            file.stream.seek(pos)
            mime_type = magic.from_buffer(sample, mime=True)
        except Exception:
            mime_type = None

        if mime_type:
            allowed_mimes = {
                'application/pdf',
                'image/png',
                'image/jpeg',
                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                'application/vnd.ms-excel',
                'application/msword',
                'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                'application/zip',
            }
            if mime_type not in allowed_mimes:
                return False, "文件内容与扩展名不匹配或类型不受支持"

    return True, None


def _ensure_upload_folder(task_id: int) -> str:
    folder = os.path.join(PRECOM_UPLOAD_FOLDER, str(task_id))
    os.makedirs(folder, exist_ok=True)
    return folder


def _task_status(row) -> str:
    total = int(row.get('QuantityTotal') or 0)
    done = int(row.get('QuantityDone') or 0)
    if total <= 0:
        return '未开始'
    if done <= 0:
        return '未开始'
    if done < total:
        return '进行中'
    return '已完成'


@precom_bp.route('/precom/tasks')
def precom_task_list():
    task_type = (request.args.get('task_type') or '').strip() or None
    system_code = (request.args.get('system_code') or '').strip() or None
    subsystem_code = (request.args.get('subsystem_code') or '').strip() or None
    block = (request.args.get('block') or '').strip() or None
    status_filter = (request.args.get('status') or '').strip() or None

    systems = SystemModel.get_all_systems()
    subsystems = SubsystemModel.get_all_subsystems() if not system_code else SubsystemModel.get_subsystems_by_system(system_code)

    page_title = TASK_TYPE_LABELS.get(task_type, '预试车任务管理')

    conn = create_connection()
    tasks = []
    if conn:
        try:
            cur = conn.cursor(dictionary=True)
            clauses = []
            params = []
            if task_type:
                clauses.append("TaskType = %s")
                params.append(task_type)
            if system_code:
                clauses.append("SystemCode = %s")
                params.append(system_code)
            if subsystem_code:
                clauses.append("SubSystemCode = %s")
                params.append(subsystem_code)
            if block:
                clauses.append("PositionBlock = %s")
                params.append(block)
            where_sql = " AND ".join(clauses) if clauses else "1=1"
            cur.execute(
                f"""
                SELECT TaskID, TaskType, SystemCode, SubSystemCode, DrawingNumber,
                       TagNumber, PointTag, Description, PositionBlock,
                       QuantityTotal, QuantityDone, PlannedDate, ActualDate, PerformedBy, TestType
                FROM PrecomTask
                WHERE {where_sql}
                ORDER BY SubSystemCode, TaskType, TagNumber, PointTag
                """,
                tuple(params),
            )
            rows = cur.fetchall()
            for row in rows:
                row['Status'] = _task_status(row)
                if status_filter and row['Status'] != status_filter:
                    continue
                tasks.append(row)
        finally:
            conn.close()

    return render_template(
        'precom_task_list.html',
        tasks=tasks,
        systems=systems,
        subsystems=subsystems,
        filter_task_type=task_type or '',
        filter_system=system_code or '',
        filter_subsystem=subsystem_code or '',
        filter_block=block or '',
        filter_status=status_filter or '',
        page_title=page_title,
        new_task_url=url_for('precom.precom_task_new', task_type=task_type) if task_type else url_for('precom.precom_task_new'),
    )


@precom_bp.route('/precom/manhole')
def precom_manhole_entry():
    return redirect(url_for('precom.precom_task_list', task_type='Manhole'))


@precom_bp.route('/precom/motor_solo')
def precom_motor_solo_entry():
    return redirect(url_for('precom.precom_task_list', task_type='MotorSolo'))


@precom_bp.route('/precom/skid_install')
def precom_skid_install_entry():
    return redirect(url_for('precom.precom_task_list', task_type='SkidInstall'))


@precom_bp.route('/precom/loop_test')
def precom_loop_test_entry():
    return redirect(url_for('precom.precom_task_list', task_type='LoopTest'))


@precom_bp.route('/precom/alignment')
def precom_alignment_entry():
    return redirect(url_for('precom.precom_task_list', task_type='Alignment'))


@precom_bp.route('/precom/mrt')
def precom_mrt_entry():
    return redirect(url_for('precom.precom_task_list', task_type='MRT'))


@precom_bp.route('/precom/function_test')
def precom_function_test_entry():
    return redirect(url_for('precom.precom_task_list', task_type='FunctionTest'))


@precom_bp.route('/precom/tasks/new', methods=['GET', 'POST'])
def precom_task_new():
    task_type = (request.args.get('task_type') or '').strip() or 'Manhole'
    systems = SystemModel.get_all_systems()
    subsystems = []
    if request.method == 'POST':
        system_code = request.form.get('SystemCode') or None
        subsystem_code = request.form.get('SubSystemCode') or None
        if system_code:
            subsystems = SubsystemModel.get_subsystems_by_system(system_code)
        data = {
            'TaskType': task_type,
            'SystemCode': system_code,
            'SubSystemCode': subsystem_code,
            'DrawingNumber': _join_drawing_numbers_from_request(),
            'TagNumber': request.form.get('TagNumber') or None,
            'PointTag': request.form.get('PointTag') or None,
            'Description': request.form.get('Description') or None,
            'PositionBlock': _join_position_blocks_from_request(),
            'QuantityTotal': int(request.form.get('QuantityTotal') or 1),
            'QuantityDone': int(request.form.get('QuantityDone') or 0),
            'PlannedDate': request.form.get('PlannedDate') or None,
            'ActualDate': request.form.get('ActualDate') or None,
            'PerformedBy': request.form.get('PerformedBy') or None,
            'TestType': request.form.get('TestType') or None,
            # 施工进度汇总字段（预留，可选）
            'ProgressID': request.form.get('ProgressID') or None,
            'Discipline': request.form.get('Discipline') or None,
            'WorkPackage': request.form.get('WorkPackage') or None,
            'KeyQuantityTotal': int(request.form.get('KeyQuantityTotal') or 0),
            'KeyQuantityDone': int(request.form.get('KeyQuantityDone') or 0),
            'KeyProgressPercent': (
                float(request.form.get('KeyProgressPercent') or 0)
                if request.form.get('KeyProgressPercent')
                else None
            ),
        }
        activities = _parse_activity_rows_from_request()
        conn = create_connection()
        if not conn:
            return "数据库连接失败", 500
        try:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO PrecomTask (
                    TaskType, SystemCode, SubSystemCode, DrawingNumber,
                    TagNumber, PointTag, Description, PositionBlock,
                    QuantityTotal, QuantityDone, PlannedDate, ActualDate,
                    PerformedBy, TestType,
                    ProgressID, Discipline, WorkPackage,
                    KeyQuantityTotal, KeyQuantityDone, KeyProgressPercent
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    data['TaskType'],
                    data['SystemCode'],
                    data['SubSystemCode'],
                    data['DrawingNumber'],
                    data['TagNumber'],
                    data['PointTag'],
                    data['Description'],
                    data['PositionBlock'],
                    data['QuantityTotal'],
                    data['QuantityDone'],
                    data['PlannedDate'],
                    data['ActualDate'],
                    data['PerformedBy'],
                    data['TestType'],
                    data['ProgressID'],
                    data['Discipline'],
                    data['WorkPackage'],
                    data['KeyQuantityTotal'],
                    data['KeyQuantityDone'],
                    data['KeyProgressPercent'],
                ),
            )
            task_id = cur.lastrowid
            _save_task_activities(conn, task_id, activities)
            conn.commit()
            return redirect(url_for('precom.precom_task_edit', task_id=task_id))
        finally:
            conn.close()
    else:
        system_code = request.args.get('system_code') or None
        if system_code:
            subsystems = SubsystemModel.get_subsystems_by_system(system_code)

    return render_template(
        'precom_task_edit.html',
        task=None,
        task_type=task_type,
        systems=systems,
        subsystems=subsystems,
        block_rows=_split_position_blocks(None),
        drawing_rows=_split_drawing_numbers(None),
        activities=[],
    )


@precom_bp.route('/precom/tasks/<int:task_id>/edit', methods=['GET', 'POST'])
def precom_task_edit(task_id: int):
    conn = create_connection()
    if not conn:
        return "数据库连接失败", 500
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM PrecomTask WHERE TaskID = %s", (task_id,))
        task = cur.fetchone()
        if not task:
            return "未找到任务", 404

        systems = SystemModel.get_all_systems()
        subsystems = SubsystemModel.get_subsystems_by_system(task.get('SystemCode')) if task.get('SystemCode') else []

        if request.method == 'POST':
            data = {
                'SystemCode': request.form.get('SystemCode') or None,
                'SubSystemCode': request.form.get('SubSystemCode') or None,
                'DrawingNumber': _join_drawing_numbers_from_request(),
                'TagNumber': request.form.get('TagNumber') or None,
                'PointTag': request.form.get('PointTag') or None,
                'Description': request.form.get('Description') or None,
                'PositionBlock': _join_position_blocks_from_request(),
                'QuantityTotal': int(request.form.get('QuantityTotal') or 1),
                'QuantityDone': int(request.form.get('QuantityDone') or 0),
                'PlannedDate': request.form.get('PlannedDate') or None,
                'ActualDate': request.form.get('ActualDate') or None,
                'PerformedBy': request.form.get('PerformedBy') or None,
                'TestType': request.form.get('TestType') or None,
                # 施工进度汇总字段（预留，可选）
                'ProgressID': request.form.get('ProgressID') or None,
                'Discipline': request.form.get('Discipline') or None,
                'WorkPackage': request.form.get('WorkPackage') or None,
                'KeyQuantityTotal': int(request.form.get('KeyQuantityTotal') or 0),
                'KeyQuantityDone': int(request.form.get('KeyQuantityDone') or 0),
                'KeyProgressPercent': (
                    float(request.form.get('KeyProgressPercent') or 0)
                    if request.form.get('KeyProgressPercent')
                    else None
                ),
            }
            activities = _parse_activity_rows_from_request()
            cur_update = conn.cursor()
            cur_update.execute(
                """
                UPDATE PrecomTask
                SET SystemCode=%s, SubSystemCode=%s, DrawingNumber=%s,
                    TagNumber=%s, PointTag=%s, Description=%s, PositionBlock=%s,
                    QuantityTotal=%s, QuantityDone=%s, PlannedDate=%s, ActualDate=%s,
                    PerformedBy=%s, TestType=%s,
                    ProgressID=%s, Discipline=%s, WorkPackage=%s,
                    KeyQuantityTotal=%s, KeyQuantityDone=%s, KeyProgressPercent=%s
                WHERE TaskID=%s
                """,
                (
                    data['SystemCode'],
                    data['SubSystemCode'],
                    data['DrawingNumber'],
                    data['TagNumber'],
                    data['PointTag'],
                    data['Description'],
                    data['PositionBlock'],
                    data['QuantityTotal'],
                    data['QuantityDone'],
                    data['PlannedDate'],
                    data['ActualDate'],
                    data['PerformedBy'],
                    data['TestType'],
                    data['ProgressID'],
                    data['Discipline'],
                    data['WorkPackage'],
                    data['KeyQuantityTotal'],
                    data['KeyQuantityDone'],
                    data['KeyProgressPercent'],
                    task_id,
                ),
            )
            _save_task_activities(conn, task_id, activities)
            conn.commit()
            return redirect(url_for('precom.precom_task_edit', task_id=task_id))

        # 加载附件和Punch简要信息用于页面展示
        cur.execute(
            """
            SELECT AttachmentID, FileName, FileSize, UploadedBy, UploadedAt, ModuleName
            FROM PrecomTaskAttachment
            WHERE TaskID = %s
            ORDER BY UploadedAt DESC
            """,
            (task_id,),
        )
        attachments = cur.fetchall()

        cur.execute(
            """
            SELECT ID, PunchNo, RefNo, SheetNo, RevNo, Description, Category, Cause,
                   IssuedBy, Rectified, RectifiedDate, Verified, VerifiedDate
            FROM PrecomTaskPunch
            WHERE TaskID = %s
            ORDER BY ID
            """,
            (task_id,),
        )
        punches = cur.fetchall()

        # 加载施工活动明细
        cur.execute(
            """
            SELECT ID, ActID, Block, ActDescription, Scope, Discipline,
                   WorkPackage, WeightFactor, ManHours, Subproject
            FROM PrecomTaskActivity
            WHERE TaskID = %s
            ORDER BY ID
            """,
            (task_id,),
        )
        activities = cur.fetchall()

        return render_template(
            'precom_task_edit.html',
            task=task,
            task_type=task.get('TaskType'),
            systems=systems,
            subsystems=subsystems,
            attachments=attachments,
            punches=punches,
            activities=activities,
            block_rows=_split_position_blocks(task.get('PositionBlock')),
            drawing_rows=_split_drawing_numbers(task.get('DrawingNumber')),
        )
    finally:
        conn.close()


@precom_bp.route('/precom/tasks/<int:task_id>/delete', methods=['POST'])
def precom_task_delete(task_id: int):
    conn = create_connection()
    if not conn:
        return jsonify({'error': '数据库连接失败'}), 500
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM PrecomTask WHERE TaskID = %s", (task_id,))
        conn.commit()
        return jsonify({'success': True})
    finally:
        conn.close()


@precom_bp.route('/api/precom/tasks/<int:task_id>/attachments', methods=['GET'])
def precom_attachments(task_id: int):
    conn = create_connection()
    if not conn:
        return jsonify([])
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT AttachmentID, FileName, FileSize, UploadedBy, UploadedAt, ModuleName
            FROM PrecomTaskAttachment
            WHERE TaskID = %s
            ORDER BY UploadedAt DESC
            """,
            (task_id,),
        )
        rows = cur.fetchall()
        for row in rows:
            if row.get('UploadedAt'):
                row['UploadedAt'] = row['UploadedAt'].strftime('%Y-%m-%d %H:%M:%S')
        return jsonify(rows)
    finally:
        conn.close()


@precom_bp.route('/api/faclist/blocks')
def api_faclist_blocks():
    """返回 Faclist 中所有唯一 Block，用于预试车任务 Block 下拉多选。"""
    conn = create_connection()
    if not conn:
        return jsonify([])
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT DISTINCT Block
            FROM Faclist
            WHERE Block IS NOT NULL AND Block <> ''
            ORDER BY Block
            """
        )
        rows = cur.fetchall()
        blocks = [row[0] for row in rows if row and row[0]]
        return jsonify(blocks)
    finally:
        conn.close()


@precom_bp.route('/api/precom/tasks/<int:task_id>/attachments', methods=['POST'])
def precom_upload_attachment(task_id: int):
    if 'files' not in request.files:
        return jsonify({'error': '未选择文件'}), 400
    files = request.files.getlist('files')
    if not files:
        return jsonify({'error': '未选择文件'}), 400

    conn = create_connection()
    if not conn:
        return jsonify({'error': '数据库连接失败'}), 500
    try:
        folder = _ensure_upload_folder(task_id)
        cur = conn.cursor()
        uploaded = []
        for file in files:
            ok, err = _validate_precom_upload_file(file)
            if not ok:
                current_app.logger.warning(f"预试车附件校验失败: {err} (filename={file.filename})")
                continue
            original = secure_filename(file.filename)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{timestamp}_{original}"
            file_path = os.path.join(folder, filename)
            file.save(file_path)
            file_size = os.path.getsize(file_path)
            cur.execute(
                """
                INSERT INTO PrecomTaskAttachment (TaskID, FileName, FilePath, FileSize, UploadedBy)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (task_id, original, file_path, file_size, 'web'),
            )
            uploaded.append({'id': cur.lastrowid, 'filename': original, 'size': file_size})
        conn.commit()
        return jsonify({'success': True, 'files': uploaded})
    except Exception as exc:
        conn.rollback()
        current_app.logger.error(f"上传预试车附件失败: {exc}", exc_info=True)
        return jsonify({'error': '服务器内部错误，请稍后重试'}), 500
    finally:
        conn.close()


@precom_bp.route('/api/precom/tasks/<int:task_id>/punch_list', methods=['GET'])
def precom_punch_list(task_id: int):
    conn = create_connection()
    if not conn:
        return jsonify([])
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT ID, PunchNo, RefNo, Description, Category, Cause,
                   IssuedBy, Rectified, RectifiedDate, Verified, VerifiedDate
            FROM PrecomTaskPunch
            WHERE TaskID = %s
            ORDER BY ID
            """,
            (task_id,),
        )
        rows = cur.fetchall()
        for row in rows:
            for key in ('RectifiedDate', 'VerifiedDate'):
                if row.get(key):
                    row[key] = row[key].strftime('%Y-%m-%d %H:%M:%S')
        return jsonify(rows)
    finally:
        conn.close()


@precom_bp.route('/api/precom/tasks/<int:task_id>/punch_list', methods=['POST'])
def precom_add_punch(task_id: int):
    data = request.json or {}
    description = (data.get('Description') or '').strip()
    if not description:
        return jsonify({'error': 'Description 为必填项。'}), 400

    conn = create_connection()
    if not conn:
        return jsonify({'error': '数据库连接失败'}), 500
    try:
        cur = conn.cursor()
        rectified_flag = 'Y' if str(data.get('Rectified') or '').upper() == 'Y' else 'N'
        rectified_date = datetime.now() if rectified_flag == 'Y' else None
        verified_flag = 'Y' if str(data.get('Verified') or '').upper() == 'Y' else 'N'
        verified_date = datetime.now() if verified_flag == 'Y' else None

        cur.execute(
            """
            INSERT INTO PrecomTaskPunch (
                TaskID, PunchNo, RefNo, SheetNo, RevNo, Description, Category, Cause,
                IssuedBy, Rectified, RectifiedDate, Verified, VerifiedDate
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                task_id,
                data.get('PunchNo'),
                data.get('RefNo'),
                data.get('SheetNo'),
                data.get('RevNo'),
                description,
                data.get('Category'),
                data.get('Cause'),
                data.get('IssuedBy'),
                rectified_flag,
                rectified_date,
                verified_flag,
                verified_date,
            ),
        )
        conn.commit()
        return jsonify({'success': True, 'id': cur.lastrowid})
    except Exception as exc:
        conn.rollback()
        current_app.logger.error(f"新增预试车 Punch 失败: {exc}", exc_info=True)
        return jsonify({'error': '服务器内部错误，请稍后重试'}), 500
    finally:
        conn.close()


@precom_bp.route('/api/precom/tasks/<int:task_id>/punch_list/<int:punch_id>', methods=['DELETE'])
def precom_delete_punch(task_id: int, punch_id: int):
    conn = create_connection()
    if not conn:
        return jsonify({'error': '数据库连接失败'}), 500
    try:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM PrecomTaskPunch WHERE ID = %s AND TaskID = %s",
            (punch_id, task_id),
        )
        conn.commit()
        return jsonify({'success': True})
    finally:
        conn.close()


@precom_bp.route('/precom/tasks/<int:task_id>/punch/import/template')
def precom_punch_template(task_id: int):
    # 简单模板：PunchNo, RefNo, Description, Category, Cause, IssuedBy
    columns = ['PunchNo', 'RefNo', 'SheetNo', 'RevNo', 'Description', 'Category', 'Cause', 'IssuedBy']
    df = pd.DataFrame(columns=columns)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='PunchList', index=False)
    output.seek(0)
    filename = f"PrecomTask_{task_id}_PunchTemplate.xlsx"
    return send_file(
        output,
        as_attachment=True,
        download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )


@precom_bp.route('/api/precom/tasks/<int:task_id>/punch_list/import', methods=['POST'])
def precom_import_punch(task_id: int):
    upload = request.files.get('file')
    if not upload or upload.filename == '':
        return jsonify({'success': False, 'message': '请上传需要导入的 Excel 文件'}), 400

    file_bytes = upload.read()
    try:
        excel = pd.ExcelFile(BytesIO(file_bytes))
    except Exception as exc:
        return jsonify({'success': False, 'message': f'读取文件失败: {exc}'}), 400

    sheet_name = next((name for name in excel.sheet_names if 'punch' in name.lower()), excel.sheet_names[0])
    df = excel.parse(sheet_name)
    if df.empty:
        return jsonify({'success': False, 'message': 'Excel 内容为空'}), 400

    required_columns = ['Description']
    missing = [col for col in required_columns if col not in df.columns]
    if missing:
        return jsonify({'success': False, 'message': f"缺少必要字段: {', '.join(missing)}"}), 400

    records = []
    for idx, row in df.iterrows():
        desc = str(row.get('Description') or '').strip()
        if not desc:
            continue
        records.append(
            (
                task_id,
                str(row.get('PunchNo') or '').strip() or None,
                str(row.get('RefNo') or '').strip() or None,
                str(row.get('SheetNo') or '').strip() or None,
                str(row.get('RevNo') or '').strip() or None,
                desc,
                str(row.get('Category') or '').strip() or None,
                str(row.get('Cause') or '').strip() or None,
                str(row.get('IssuedBy') or '').strip() or None,
            )
        )

    if not records:
        return jsonify({'success': False, 'message': '没有可以导入的记录'}), 400

    conn = create_connection()
    if not conn:
        return jsonify({'success': False, 'message': '数据库连接失败'}), 500

    try:
        cur = conn.cursor()
        cur.executemany(
            """
            INSERT INTO PrecomTaskPunch (
                TaskID, PunchNo, RefNo, SheetNo, RevNo, Description, Category, Cause,
                IssuedBy, Rectified, RectifiedDate, Verified, VerifiedDate
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'N', NULL, 'N', NULL)
            """,
            records,
        )
        conn.commit()
        return jsonify({'success': True, 'inserted': cur.rowcount})
    except Exception as exc:
        conn.rollback()
        return jsonify({'success': False, 'message': f'导入失败: {exc}'}), 500
    finally:
        conn.close()


def _parse_activity_rows_from_request():
    """从表单中解析施工活动行数据，返回字典列表"""
    act_ids = request.form.getlist('ActivityActID')
    blocks = request.form.getlist('ActivityBlock')
    descriptions = request.form.getlist('ActivityDescription')
    scopes = request.form.getlist('ActivityScope')
    disciplines = request.form.getlist('ActivityDiscipline')
    work_packages = request.form.getlist('ActivityWorkPackage')
    weight_factors = request.form.getlist('ActivityWeightFactor')
    man_hours_list = request.form.getlist('ActivityManHours')
    subprojects = request.form.getlist('ActivitySubproject')

    activities = []
    row_count = max(
        len(act_ids),
        len(blocks),
        len(descriptions),
        len(scopes),
        len(disciplines),
        len(work_packages),
        len(weight_factors),
        len(man_hours_list),
        len(subprojects),
    )
    for idx in range(row_count):
        act_id = (act_ids[idx].strip() if idx < len(act_ids) and act_ids[idx] else '')
        block = (blocks[idx].strip() if idx < len(blocks) and blocks[idx] else '')
        desc = (descriptions[idx].strip() if idx < len(descriptions) and descriptions[idx] else '')
        scope = (scopes[idx].strip() if idx < len(scopes) and scopes[idx] else '')
        disc = (disciplines[idx].strip() if idx < len(disciplines) and disciplines[idx] else '')
        wp = (work_packages[idx].strip() if idx < len(work_packages) and work_packages[idx] else '')
        wf_raw = weight_factors[idx].strip() if idx < len(weight_factors) and weight_factors[idx] else ''
        mh_raw = man_hours_list[idx].strip() if idx < len(man_hours_list) and man_hours_list[idx] else ''
        subprj = (subprojects[idx].strip() if idx < len(subprojects) and subprojects[idx] else '')

        # 如果整行都是空，则跳过
        if not any([act_id, block, desc, scope, disc, wp, wf_raw, mh_raw, subprj]):
            continue

        try:
            wf = float(wf_raw) if wf_raw else None
        except ValueError:
            wf = None
        try:
            mh = float(mh_raw) if mh_raw else None
        except ValueError:
            mh = None

        activities.append(
            {
                'ActID': act_id or None,
                'Block': block or None,
                'ActDescription': desc or None,
                'Scope': scope or None,
                'Discipline': disc or None,
                'WorkPackage': wp or None,
                'WeightFactor': wf,
                'ManHours': mh,
                'Subproject': subprj or None,
            }
        )
    return activities


def _save_task_activities(conn, task_id: int, activities):
    """将施工活动明细保存到 PrecomTaskActivity 表，先清空后重新插入"""
    cur = conn.cursor()
    # 先删除原有记录
    cur.execute("DELETE FROM PrecomTaskActivity WHERE TaskID = %s", (task_id,))
    if not activities:
        return
    insert_sql = """
        INSERT INTO PrecomTaskActivity (
            TaskID, ActID, Block, ActDescription, Scope,
            Discipline, WorkPackage, WeightFactor, ManHours, Subproject
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    values = [
        (
            task_id,
            act['ActID'],
            act['Block'],
            act['ActDescription'],
            act['Scope'],
            act['Discipline'],
            act['WorkPackage'],
            act['WeightFactor'],
            act['ManHours'],
            act['Subproject'],
        )
        for act in activities
    ]
    cur.executemany(insert_sql, values)


def _sanitize_list(values):
    return [v.strip() for v in values if v and v.strip()]


def _join_position_blocks_from_request():
    blocks = _sanitize_list(request.form.getlist('PositionBlocks'))
    return ';'.join(blocks) if blocks else None


def _join_drawing_numbers_from_request():
    numbers = _sanitize_list(request.form.getlist('DrawingNumbers'))
    if numbers:
        return '\n'.join(numbers)
    fallback = request.form.get('DrawingNumber')
    if fallback and fallback.strip():
        return fallback.strip()
    return None


def _split_position_blocks(value):
    if not value:
        return ['']
    parts = [p.strip() for p in re.split(r'[;\n,]', value) if p.strip()]
    return parts or ['']


def _split_drawing_numbers(value):
    if not value:
        return ['']
    parts = [p.strip() for p in re.split(r'[\n;]+', value) if p.strip()]
    return parts or ['']


@precom_bp.route('/precom/tasks/export', methods=['GET'])
def precom_export_tasks():
    task_type = (request.args.get('task_type') or '').strip() or None
    conn = create_connection()
    if not conn:
        return "数据库连接失败", 500
    try:
        cur = conn.cursor(dictionary=True)
        clauses = []
        params = []
        if task_type:
            clauses.append("TaskType = %s")
            params.append(task_type)
        where_sql = " AND ".join(clauses) if clauses else "1=1"
        cur.execute(
            f"""
            SELECT TaskID, TaskType, SystemCode, SubSystemCode, DrawingNumber,
                   TagNumber, PointTag, Description, PositionBlock,
                   QuantityTotal, QuantityDone, PlannedDate, ActualDate,
                   PerformedBy, TestType
            FROM PrecomTask
            WHERE {where_sql}
            ORDER BY SubSystemCode, TaskType, TagNumber, PointTag
            """,
            tuple(params),
        )
        rows = cur.fetchall()
    finally:
        conn.close()

    if not rows:
        rows = []
    df = pd.DataFrame(rows)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='PrecomTasks', index=False)
    output.seek(0)
    type_part = task_type or 'ALL'
    filename = f"PrecomTasks_{type_part}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return send_file(
        output,
        as_attachment=True,
        download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )


@precom_bp.route('/precom/tasks/import', methods=['POST'])
def precom_import_tasks():
    task_type = (request.args.get('task_type') or '').strip() or None
    upload = request.files.get('file')
    if not upload or upload.filename == '':
        return jsonify({'success': False, 'message': '请上传需要导入的 Excel 文件'}), 400

    file_bytes = upload.read()
    try:
        excel = pd.ExcelFile(BytesIO(file_bytes))
    except Exception as exc:
        return jsonify({'success': False, 'message': f'读取文件失败: {exc}'}), 400

    sheet_name = excel.sheet_names[0]
    df = excel.parse(sheet_name)
    if df.empty:
        return jsonify({'success': False, 'message': 'Excel 内容为空'}), 400

    required_columns = ['SubSystemCode', 'Description']
    missing = [col for col in required_columns if col not in df.columns]
    if missing:
        return jsonify({'success': False, 'message': f"缺少必要字段: {', '.join(missing)}"}), 400

    records = []
    for _, row in df.iterrows():
        subsystem = str(row.get('SubSystemCode') or '').strip()
        description = str(row.get('Description') or '').strip()
        if not subsystem or not description:
            continue
        records.append(
            (
                task_type or str(row.get('TaskType') or '').strip() or 'Manhole',
                str(row.get('SystemCode') or '').strip() or None,
                subsystem,
                str(row.get('DrawingNumber') or '').strip() or None,
                str(row.get('TagNumber') or '').strip() or None,
                str(row.get('PointTag') or '').strip() or None,
                description,
                str(row.get('PositionBlock') or '').strip() or None,
                int(row.get('QuantityTotal') or 1),
                int(row.get('QuantityDone') or 0),
                row.get('PlannedDate') if pd.notna(row.get('PlannedDate')) else None,
                row.get('ActualDate') if pd.notna(row.get('ActualDate')) else None,
                str(row.get('PerformedBy') or '').strip() or None,
                str(row.get('TestType') or '').strip() or None,
            )
        )

    if not records:
        return jsonify({'success': False, 'message': '没有可以导入的记录'}), 400

    conn = create_connection()
    if not conn:
        return jsonify({'success': False, 'message': '数据库连接失败'}), 500

    try:
        cur = conn.cursor()
        cur.executemany(
            """
            INSERT INTO PrecomTask (
                TaskType, SystemCode, SubSystemCode, DrawingNumber,
                TagNumber, PointTag, Description, PositionBlock,
                QuantityTotal, QuantityDone, PlannedDate, ActualDate,
                PerformedBy, TestType
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            records,
        )
        conn.commit()
        return jsonify({'success': True, 'inserted': cur.rowcount})
    except Exception as exc:
        conn.rollback()
        return jsonify({'success': False, 'message': f'导入失败: {exc}'}), 500
    finally:
        conn.close()


@precom_bp.route('/precom/tasks/<int:task_id>/export', methods=['GET'])
def precom_export_single_task(task_id: int):
    conn = create_connection()
    if not conn:
        return "数据库连接失败", 500
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM PrecomTask WHERE TaskID = %s", (task_id,))
        task = cur.fetchone()
        if not task:
            return "未找到任务", 404

        cur.execute(
            """
            SELECT FileName, FilePath
            FROM PrecomTaskAttachment
            WHERE TaskID = %s
            """,
            (task_id,),
        )
        attachments = cur.fetchall()
    finally:
        conn.close()

    # 构建任务 Excel
    df = pd.DataFrame([task])
    excel_buffer = BytesIO()
    with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Task', index=False)
    excel_buffer.seek(0)

    # 打包为 ZIP（Excel + 附件）
    import zipfile

    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"PrecomTask_{task_id}.xlsx", excel_buffer.read())
        for att in attachments or []:
            path = att.get('FilePath')
            name = att.get('FileName') or os.path.basename(path or '')
            if path and os.path.exists(path):
                zf.write(path, arcname=f"attachments/{name}")
    zip_buffer.seek(0)

    filename = f"PrecomTask_{task_id}_with_attachments.zip"
    return send_file(
        zip_buffer,
        as_attachment=True,
        download_name=filename,
        mimetype='application/zip',
    )


