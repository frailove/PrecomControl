"""导出功能模块 - 用于导出系统、子系统、试压包数据到Excel"""
import pandas as pd
from io import BytesIO
from flask import Response
from database import create_connection


def export_systems_to_excel(filtered_systems, stats_by_system, selected_columns=None):
    """导出系统数据到Excel
    selected_columns: 用户选择的列列表，如果为None则导出所有列
    """
    # 定义所有可导出的列
    all_columns = {
        '系统代码': 'system_code',
        '英文描述': 'description_eng',
        '类型': 'type',
        'DIN总量': 'total_din',
        'DIN完成量': 'completed_din',
        '测试包完成/总量': 'test_packages',
        '焊接进度': 'welding_progress',
        '测试进度': 'test_progress',
        '优先级': 'priority',
        '更新时间': 'update_date'
    }
    
    # 如果没有指定列，使用所有列
    if selected_columns is None:
        selected_columns = list(all_columns.keys())
    
    # 确保至少选择一列
    if not selected_columns:
        selected_columns = list(all_columns.keys())
    
    # 构建数据
    data = []
    for system in filtered_systems:
        sys_code = str(system['SystemCode']).strip()
        stats = stats_by_system.get(sys_code, {})
        if not stats:
            for key, value in stats_by_system.items():
                if str(key).strip().upper() == sys_code.upper():
                    stats = value
                    break
        
        total_din = stats.get('total_din', 0)
        completed_din = stats.get('completed_din', 0)
        welding_progress = stats.get('welding_progress', 0.0)
        total_packages = stats.get('total_packages', 0)
        tested_packages = stats.get('tested_packages', 0)
        test_progress = stats.get('test_progress', 0.0)
        
        row_data = {}
        if '系统代码' in selected_columns:
            row_data['系统代码'] = sys_code
        if '英文描述' in selected_columns:
            row_data['英文描述'] = system['SystemDescriptionENG']
        if '类型' in selected_columns:
            row_data['类型'] = system['ProcessOrNonProcess']
        if 'DIN总量' in selected_columns:
            row_data['DIN总量'] = f"{total_din:.1f}"
        if 'DIN完成量' in selected_columns:
            row_data['DIN完成量'] = f"{completed_din:.1f}"
        if '测试包完成/总量' in selected_columns:
            row_data['测试包完成/总量'] = f"{tested_packages} / {total_packages}"
        if '焊接进度' in selected_columns:
            row_data['焊接进度'] = f"{welding_progress*100:.1f}%"
        if '测试进度' in selected_columns:
            row_data['测试进度'] = f"{test_progress*100:.1f}%"
        if '优先级' in selected_columns:
            row_data['优先级'] = system['Priority']
        if '更新时间' in selected_columns:
            row_data['更新时间'] = system['updateDate'].strftime('%Y-%m-%d %H:%M') if system['updateDate'] else '未知'
        
        data.append(row_data)
    
    # 按照用户选择的顺序排列列
    ordered_columns = [col for col in selected_columns if col in all_columns]
    df = pd.DataFrame(data, columns=ordered_columns)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='系统数据')
    output.seek(0)
    
    return Response(
        output.getvalue(),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': 'attachment; filename=systems_export.xlsx'}
    )


def export_subsystems_to_excel(filtered_subsystems, stats_by_subsystem, selected_columns=None):
    """导出子系统数据到Excel
    selected_columns: 用户选择的列列表，如果为None则导出所有列
    """
    # 定义所有可导出的列
    all_columns = {
        '子系统代码': 'subsystem_code',
        '系统代码': 'system_code',
        '系统描述': 'system_description',
        '英文描述': 'description_eng',
        '俄文描述': 'description_rus',
        '类型': 'type',
        'DIN总量': 'total_din',
        'DIN完成量': 'completed_din',
        '测试包完成/总量': 'test_packages',
        '焊接进度': 'welding_progress',
        '测试进度': 'test_progress',
        '优先级': 'priority'
    }
    
    # 如果没有指定列，使用所有列
    if selected_columns is None:
        selected_columns = list(all_columns.keys())
    
    # 确保至少选择一列
    if not selected_columns:
        selected_columns = list(all_columns.keys())
    
    # 构建数据
    data = []
    for subsystem in filtered_subsystems:
        sub_code = str(subsystem['SubSystemCode']).strip()
        stats = stats_by_subsystem.get(sub_code, {})
        if not stats:
            for key, value in stats_by_subsystem.items():
                if str(key).strip().upper() == sub_code.upper():
                    stats = value
                    break
        
        total_din = stats.get('total_din', 0)
        completed_din = stats.get('completed_din', 0)
        welding_progress = stats.get('welding_progress', 0.0)
        total_packages = stats.get('total_packages', 0)
        tested_packages = stats.get('tested_packages', 0)
        test_progress = stats.get('test_progress', 0.0)
        
        row_data = {}
        if '子系统代码' in selected_columns:
            row_data['子系统代码'] = sub_code
        if '系统代码' in selected_columns:
            row_data['系统代码'] = subsystem['SystemCode']
        if '系统描述' in selected_columns:
            row_data['系统描述'] = subsystem['SystemDescription'] or 'N/A'
        if '英文描述' in selected_columns:
            row_data['英文描述'] = subsystem['SubSystemDescriptionENG']
        if '俄文描述' in selected_columns:
            row_data['俄文描述'] = subsystem['SubSystemDescriptionRUS'] or ''
        if '类型' in selected_columns:
            row_data['类型'] = subsystem['ProcessOrNonProcess']
        if 'DIN总量' in selected_columns:
            row_data['DIN总量'] = f"{total_din:.1f}"
        if 'DIN完成量' in selected_columns:
            row_data['DIN完成量'] = f"{completed_din:.1f}"
        if '测试包完成/总量' in selected_columns:
            row_data['测试包完成/总量'] = f"{tested_packages} / {total_packages}"
        if '焊接进度' in selected_columns:
            row_data['焊接进度'] = f"{welding_progress*100:.1f}%"
        if '测试进度' in selected_columns:
            row_data['测试进度'] = f"{test_progress*100:.1f}%"
        if '优先级' in selected_columns:
            row_data['优先级'] = subsystem['Priority']
        
        data.append(row_data)
    
    # 按照用户选择的顺序排列列
    ordered_columns = [col for col in selected_columns if col in all_columns]
    df = pd.DataFrame(data, columns=ordered_columns)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='子系统数据')
    output.seek(0)
    
    return Response(
        output.getvalue(),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': 'attachment; filename=subsystems_export.xlsx'}
    )


def export_test_packages_to_excel(packages, selected_columns=None):
    """导出试压包数据到Excel
    selected_columns: 用户选择的列列表，如果为None则导出所有列
    """
    # 定义所有可导出的列
    all_columns = {
        '试压包ID': 'test_package_id',
        '系统代码': 'system_code',
        '子系统代码': 'subsystem_code',
        '描述': 'description',
        '计划日期': 'planned_date',
        '实际日期': 'actual_date',
        '压力': 'pressure',
        '测试时长': 'test_duration',
        'DIN总量': 'total_din',
        'DIN完成量': 'completed_din',
        '焊接进度': 'welding_progress',
        '焊口总量': 'total_welds',
        '检测通过量': 'tests_passed',
        '检测通过比': 'test_pass_ratio'
    }
    
    # 如果没有指定列，使用所有列
    if selected_columns is None:
        selected_columns = list(all_columns.keys())
    
    # 确保至少选择一列
    if not selected_columns:
        selected_columns = list(all_columns.keys())
    
    # 构建数据
    data = []
    test_icons = {
        'vt_pass': 'VT', 'rt_pass': 'RT', 'ut_pass': 'UT',
        'pt_pass': 'PT', 'mt_pass': 'MT', 'pmi_pass': 'PMI', 'ft_pass': 'FT'
    }
    
    for p in packages:
        total_din = p.get('total_din', 0)
        completed_din = p.get('completed_din', 0)
        progress_pct = f"{p['progress']*100:.1f}%" if total_din > 0 else '0%'
        tests_passed_count = p.get('tests_passed_count', 0)
        total_welds = p.get('total', 0)
        # 计算检测通过比
        test_pass_ratio = (tests_passed_count / total_welds * 100) if total_welds > 0 else 0
        test_pass_ratio_pct = f"{test_pass_ratio:.1f}%"
        
        row_data = {}
        if '试压包ID' in selected_columns:
            row_data['试压包ID'] = p['TestPackageID']
        if '系统代码' in selected_columns:
            row_data['系统代码'] = p.get('SystemCode') or 'N/A'
        if '子系统代码' in selected_columns:
            row_data['子系统代码'] = p.get('SubSystemCode') or 'N/A'
        if '描述' in selected_columns:
            row_data['描述'] = p.get('Description') or ''
        if '计划日期' in selected_columns:
            row_data['计划日期'] = p.get('PlannedDate') or '未计划'
        if '实际日期' in selected_columns:
            row_data['实际日期'] = p.get('ActualDate') or '未完成'
        if '压力' in selected_columns:
            row_data['压力'] = p.get('Pressure') or 'N/A'
        if '测试时长' in selected_columns:
            row_data['测试时长'] = p.get('TestDuration') or 'N/A'
        if 'DIN总量' in selected_columns:
            row_data['DIN总量'] = f"{total_din:.1f}"
        if 'DIN完成量' in selected_columns:
            row_data['DIN完成量'] = f"{completed_din:.1f}"
        if '焊接进度' in selected_columns:
            row_data['焊接进度'] = progress_pct
        if '焊口总量' in selected_columns:
            row_data['焊口总量'] = total_welds
        if '检测通过量' in selected_columns:
            row_data['检测通过量'] = tests_passed_count
        if '检测通过比' in selected_columns:
            row_data['检测通过比'] = test_pass_ratio_pct
        
        data.append(row_data)
    
    # 按照用户选择的顺序排列列
    ordered_columns = [col for col in selected_columns if col in all_columns]
    df = pd.DataFrame(data, columns=ordered_columns)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='试压包数据')
    output.seek(0)
    
    return Response(
        output.getvalue(),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': 'attachment; filename=test_packages_export.xlsx'}
    )

