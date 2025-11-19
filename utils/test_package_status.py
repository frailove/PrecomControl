# -*- coding: utf-8 -*-
"""
试压包状态分类系统
根据焊口完成情况、检测完成情况、资料完善情况等判断试压包的当前状态
"""
from database import create_connection

class TestPackageStatus:
    """试压包状态枚举"""
    CONSTRUCTION_INCOMPLETE = 1  # 施工未完成
    CONSTRUCTION_COMPLETE = 2    # 现场施工已完成，具备试压包资料准备条件
    DOCUMENT_READY = 3           # 试压包资料准备已完成，等待反馈现场试压结果
    TEST_COMPLETE = 4            # 试压已完成
    
    STATUS_NAMES = {
        1: '施工未完成',
        2: '现场施工已完成',
        3: '资料准备完成',
        4: '试压已完成'
    }
    
    STATUS_COLORS = {
        1: 'secondary',  # 灰色
        2: 'warning',    # 黄色
        3: 'info',       # 蓝色
        4: 'success'     # 绿色
    }
    
    STATUS_DESCRIPTIONS = {
        1: '焊口或检测未完成',
        2: '具备试压包资料准备条件',
        3: '等待反馈现场试压结果',
        4: '试压已完成'
    }


def calculate_test_package_status(test_package_id):
    """
    计算试压包的当前状态
    
    返回: {
        'status': int (1-4),
        'status_name': str,
        'status_color': str,
        'status_description': str,
        'details': dict  # 详细检查结果
    }
    """
    conn = create_connection()
    if not conn:
        return None
    
    try:
        cur = conn.cursor(dictionary=True)
        
        # 获取试压包基础信息
        cur.execute("""
            SELECT TestPackageID, Status, ActualDate,
                   SystemCode, SubSystemCode, Description,
                   PipeMaterial, TestType, TestMedium,
                   DesignPressure, TestPressure
            FROM HydroTestPackageList
            WHERE TestPackageID = %s
        """, (test_package_id,))
        test_package = cur.fetchone()
        
        if not test_package:
            return None
        
        details = {}
        
        # 1. 检查焊口完成情况
        cur.execute("""
            SELECT TotalJoints, CompletedJoints, RemainingJoints
            FROM JointSummary
            WHERE TestPackageID = %s
        """, (test_package_id,))
        joint_summary = cur.fetchone()
        
        joints_complete = False
        if joint_summary:
            total = joint_summary['TotalJoints'] or 0
            completed = joint_summary['CompletedJoints'] or 0
            details['joints'] = {
                'total': total,
                'completed': completed,
                'percentage': round(completed / total * 100, 1) if total > 0 else 0
            }
            joints_complete = (total > 0 and completed == total)
        else:
            details['joints'] = {'total': 0, 'completed': 0, 'percentage': 0}
            joints_complete = False
        
        # 2. 检查检测完成情况（所有Required测试都完成）
        cur.execute("""
            SELECT VT_Total, VT_Completed, VT_Remaining,
                   RT_Total, RT_Completed, RT_Remaining,
                   PT_Total, PT_Completed, PT_Remaining,
                   UT_Total, UT_Completed, UT_Remaining,
                   MT_Total, MT_Completed, MT_Remaining,
                   PMI_Total, PMI_Completed, PMI_Remaining
            FROM NDEPWHTStatus
            WHERE TestPackageID = %s
        """, (test_package_id,))
        nde_status = cur.fetchone()
        
        tests_complete = False
        if nde_status:
            # 检查所有有要求的测试是否都完成
            all_tests_done = True
            test_types = ['VT', 'RT', 'PT', 'UT', 'MT', 'PMI']
            for test_type in test_types:
                total = nde_status[f'{test_type}_Total'] or 0
                completed = nde_status[f'{test_type}_Completed'] or 0
                if total > 0 and completed < total:
                    all_tests_done = False
                    break
            tests_complete = all_tests_done
            details['tests_complete'] = tests_complete
        else:
            tests_complete = False
            details['tests_complete'] = False
        
        # 如果焊口或检测未完成，返回状态1
        if not joints_complete or not tests_complete:
            return {
                'status': TestPackageStatus.CONSTRUCTION_INCOMPLETE,
                'status_name': TestPackageStatus.STATUS_NAMES[1],
                'status_color': TestPackageStatus.STATUS_COLORS[1],
                'status_description': TestPackageStatus.STATUS_DESCRIPTIONS[1],
                'details': details
            }
        
        # 3. 检查基础信息是否完善
        basic_info_complete = all([
            test_package.get('SystemCode'),
            test_package.get('SubSystemCode'),
            test_package.get('Description'),
            test_package.get('TestType'),
            test_package.get('DesignPressure'),
            test_package.get('TestPressure')
        ])
        details['basic_info_complete'] = basic_info_complete
        
        # 4. 检查图纸清单（P&ID + ISO）
        cur.execute("""
            SELECT COUNT(*) as pid_count FROM PIDList WHERE TestPackageID = %s
        """, (test_package_id,))
        pid_count = cur.fetchone()['pid_count']
        
        cur.execute("""
            SELECT COUNT(*) as iso_count FROM ISODrawingList WHERE TestPackageID = %s
        """, (test_package_id,))
        iso_count = cur.fetchone()['iso_count']
        
        drawings_complete = (pid_count > 0 or iso_count > 0)
        details['drawings'] = {'pid_count': pid_count, 'iso_count': iso_count}
        
        # 5. 检查必需附件（3/4/5/7/9/10/11）
        required_modules = [
            'PID_Drawings',           # 3
            'ISO_Drawings',           # 4
            'Welding_Documents',      # 5
            'NDE_Reports',            # 7
            'Material_Certificates',  # 9
            'Calibration_Certificates', # 10
            'Test_Procedure'          # 11
        ]
        
        attachments_status = {}
        for module in required_modules:
            cur.execute("""
                SELECT COUNT(*) as count
                FROM TestPackageAttachments
                WHERE TestPackageID = %s AND ModuleName = %s
            """, (test_package_id, module))
            count = cur.fetchone()['count']
            attachments_status[module] = count > 0
        
        attachments_complete = all(attachments_status.values())
        details['attachments'] = attachments_status
        
        # 6. 检查Punch List（没有未整改的）
        cur.execute("""
            SELECT COUNT(*) as unresolved_count
            FROM PunchList
            WHERE TestPackageID = %s AND Rectified = 'N'
        """, (test_package_id,))
        unresolved_punch = cur.fetchone()['unresolved_count']
        
        punch_complete = (unresolved_punch == 0)
        details['punch'] = {'unresolved': unresolved_punch}
        
        # 判断是否达到状态3的条件
        document_ready = (
            basic_info_complete and
            drawings_complete and
            attachments_complete and
            details['joints']['percentage'] == 100 and
            punch_complete
        )
        
        # 如果资料未准备好，返回状态2
        if not document_ready:
            return {
                'status': TestPackageStatus.CONSTRUCTION_COMPLETE,
                'status_name': TestPackageStatus.STATUS_NAMES[2],
                'status_color': TestPackageStatus.STATUS_COLORS[2],
                'status_description': TestPackageStatus.STATUS_DESCRIPTIONS[2],
                'details': details
            }
        
        # 7. 检查是否已完成试压（Status = 'Completed' 且有ActualDate）
        test_complete = (
            test_package.get('Status') == 'Completed' and
            test_package.get('ActualDate') is not None
        )
        
        if test_complete:
            return {
                'status': TestPackageStatus.TEST_COMPLETE,
                'status_name': TestPackageStatus.STATUS_NAMES[4],
                'status_color': TestPackageStatus.STATUS_COLORS[4],
                'status_description': TestPackageStatus.STATUS_DESCRIPTIONS[4],
                'details': details
            }
        else:
            return {
                'status': TestPackageStatus.DOCUMENT_READY,
                'status_name': TestPackageStatus.STATUS_NAMES[3],
                'status_color': TestPackageStatus.STATUS_COLORS[3],
                'status_description': TestPackageStatus.STATUS_DESCRIPTIONS[3],
                'details': details
            }
    
    finally:
        conn.close()


def get_status_summary_by_system(system_code=None, subsystem_code=None):
    """
    获取系统或子系统的试压包状态汇总
    
    返回: {
        'total': int,
        'status_1': int,  # 施工未完成
        'status_2': int,  # 现场施工已完成
        'status_3': int,  # 资料准备完成
        'status_4': int   # 试压已完成
    }
    """
    conn = create_connection()
    if not conn:
        return None
    
    try:
        cur = conn.cursor(dictionary=True)
        
        # 构建查询条件
        where_clause = "WHERE 1=1"
        params = []
        
        if system_code:
            where_clause += " AND SystemCode = %s"
            params.append(system_code)
        
        if subsystem_code:
            where_clause += " AND SubSystemCode = %s"
            params.append(subsystem_code)
        
        # 获取所有试压包
        cur.execute(f"""
            SELECT TestPackageID
            FROM HydroTestPackageList
            {where_clause}
        """, params)
        
        test_packages = cur.fetchall()
        
        summary = {
            'total': len(test_packages),
            'status_1': 0,
            'status_2': 0,
            'status_3': 0,
            'status_4': 0
        }
        
        # 计算每个试压包的状态
        for tp in test_packages:
            status_info = calculate_test_package_status(tp['TestPackageID'])
            if status_info:
                status = status_info['status']
                summary[f'status_{status}'] += 1
        
        return summary
    
    finally:
        conn.close()

