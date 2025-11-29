# -*- coding: utf-8 -*-
"""
从 WeldingList 聚合生成 JointSummary、NDEPWHTStatus、ISODrawingList
"""
import sys
import os
from decimal import Decimal

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import create_connection, ensure_welding_summary_tables
from utils.ndt_compliance_checker import parse_nde_grade

PIPELINE_SYSTEM_SHARE_THRESHOLD = float(os.getenv("PIPELINE_SYSTEM_SHARE_THRESHOLD", 0.5))

def refresh_joint_summary(test_package_id):
    """
    从 WeldingList 聚合生成 JointSummary 数据
    """
    conn = create_connection()
    if not conn:
        return False
    
    try:
        cur = conn.cursor(dictionary=True)
        
        # 1. 统计焊口数量和DIN
        cur.execute("""
            SELECT 
                COUNT(*) as TotalJoints,
                COALESCE(SUM(Size), 0) as TotalDIN,
                COUNT(CASE WHEN Status = '已完成' OR Status = 'Completed' THEN 1 END) as CompletedJoints,
                COALESCE(SUM(CASE WHEN Status = '已完成' OR Status = 'Completed' THEN Size ELSE 0 END), 0) as CompletedDIN
            FROM WeldingList
            WHERE TestPackageID = %s
        """, (test_package_id,))
        
        result = cur.fetchone()
        if not result:
            return False
        
        total_joints = result['TotalJoints']
        completed_joints = result['CompletedJoints']
        remaining_joints = total_joints - completed_joints
        
        total_din = float(result['TotalDIN'])
        completed_din = float(result['CompletedDIN'])
        remaining_din = total_din - completed_din
        
        # 2. 插入或更新 JointSummary
        cur.execute("""
            INSERT INTO JointSummary (
                TestPackageID, TotalJoints, CompletedJoints, RemainingJoints,
                TotalDIN, CompletedDIN, RemainingDIN
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                TotalJoints = VALUES(TotalJoints),
                CompletedJoints = VALUES(CompletedJoints),
                RemainingJoints = VALUES(RemainingJoints),
                TotalDIN = VALUES(TotalDIN),
                CompletedDIN = VALUES(CompletedDIN),
                RemainingDIN = VALUES(RemainingDIN),
                updated_at = CURRENT_TIMESTAMP
        """, (test_package_id, total_joints, completed_joints, remaining_joints,
              total_din, completed_din, remaining_din))
        
        conn.commit()
        return True
        
    except Exception as e:
        print(f"刷新JointSummary失败: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


def refresh_nde_pwht_status(test_package_id):
    """
    从 WeldingList 聚合生成 NDEPWHTStatus 数据（基于NDT符合性检查）
    
    重要逻辑：
    1. 检查是否所有焊口都完成焊接
    2. 如果有未完成焊接的焊口 → Total和Remaining设为NULL（显示N/A），只显示Completed
    3. 如果全部完成焊接 → 根据NDEGrade计算Total和Remaining
    """
    conn = create_connection()
    if not conn:
        return False
    
    try:
        cur = conn.cursor(dictionary=True)
        
        # 1. 检查是否所有焊口都完成焊接
        cur.execute("""
            SELECT 
                COUNT(*) as total_welds,
                SUM(CASE WHEN WeldDate IS NOT NULL OR Status = '已完成' OR Status = 'Completed' THEN 1 ELSE 0 END) as welded_count
            FROM WeldingList
            WHERE TestPackageID = %s
        """, (test_package_id,))
        
        weld_summary = cur.fetchone()
        total_welds = weld_summary['total_welds']
        welded_count = weld_summary['welded_count']
        all_welds_completed = (total_welds == welded_count and total_welds > 0)
        
        # 2. 查询已完成焊接的焊口的检测统计（按管线和焊工分组）
        cur.execute("""
            SELECT 
                wl.PipelineNumber,
                wl.WelderRoot,
                COUNT(*) as total_welds,
                SUM(CASE WHEN wl.VTResult IS NOT NULL AND wl.VTResult != '' THEN 1 ELSE 0 END) as VT_count,
                SUM(CASE WHEN wl.RTResult IS NOT NULL AND wl.RTResult != '' THEN 1 ELSE 0 END) as RT_count,
                SUM(CASE WHEN wl.PTResult IS NOT NULL AND wl.PTResult != '' THEN 1 ELSE 0 END) as PT_count,
                SUM(CASE WHEN wl.UTResult IS NOT NULL AND wl.UTResult != '' THEN 1 ELSE 0 END) as UT_count,
                SUM(CASE WHEN wl.MTResult IS NOT NULL AND wl.MTResult != '' THEN 1 ELSE 0 END) as MT_count,
                SUM(CASE WHEN wl.PMIResult IS NOT NULL AND wl.PMIResult != '' THEN 1 ELSE 0 END) as PMI_count,
                SUM(CASE WHEN wl.FTResult IS NOT NULL AND wl.FTResult != '' THEN 1 ELSE 0 END) as FT_count,
                SUM(CASE WHEN wl.HTResult IS NOT NULL AND wl.HTResult != '' THEN 1 ELSE 0 END) as HT_count,
                SUM(CASE WHEN wl.PWHTResult IS NOT NULL AND wl.PWHTResult != '' THEN 1 ELSE 0 END) as PWHT_count,
                ll.NDEGrade
            FROM WeldingList wl
            LEFT JOIN LineList ll ON wl.PipelineNumber = ll.LineID
            WHERE wl.TestPackageID = %s
              AND (wl.WeldDate IS NOT NULL OR wl.Status = '已完成' OR wl.Status = 'Completed')
            GROUP BY wl.PipelineNumber, wl.WelderRoot, ll.NDEGrade
        """, (test_package_id,))
        
        all_stats = cur.fetchall()
        
        # 使用字典累计各类检测的统计
        
        test_types = ['VT', 'RT', 'PT', 'UT', 'MT', 'PMI', 'FT', 'HT', 'PWHT']
        
        # 初始化统计数据
        stats = {}
        for t in test_types:
            stats[f'{t}_Completed'] = 0  # 已完成数始终计算
            if all_welds_completed:
                # 所有焊口都完成焊接 → 可以计算Total和Remaining
                stats[f'{t}_Total'] = 0
                stats[f'{t}_Remaining'] = 0
            else:
                # 有未完成焊接的焊口 → Total和Remaining设为NULL
                stats[f'{t}_Total'] = None
                stats[f'{t}_Remaining'] = None
        
        # 3. 累计各类检测的统计
        for stat in all_stats:
            nde_requirements = parse_nde_grade(stat.get('NDEGrade'))
            total_welds = stat['total_welds']
            
            for test_type in test_types:
                # 累计已完成数
                completed_count = stat.get(f'{test_type}_count', 0)
                stats[f'{test_type}_Completed'] += completed_count
                
                # 如果所有焊口都完成，计算Total
                if all_welds_completed and nde_requirements.get(test_type, 0) > 0:
                    required_count = int(total_welds * nde_requirements[test_type] / 100)
                    stats[f'{test_type}_Total'] += required_count
        
        # 4. 计算剩余数（只有全部完成时）
        if all_welds_completed:
            for test_type in test_types:
                total = stats[f'{test_type}_Total'] or 0
                completed = stats[f'{test_type}_Completed'] or 0
                stats[f'{test_type}_Remaining'] = total - completed
        
        # 插入或更新 NDEPWHTStatus
        cur.execute("""
            INSERT INTO NDEPWHTStatus (
                TestPackageID,
                VT_Total, VT_Completed, VT_Remaining,
                RT_Total, RT_Completed, RT_Remaining,
                PT_Total, PT_Completed, PT_Remaining,
                HT_Total, HT_Completed, HT_Remaining,
                PWHT_Total, PWHT_Completed, PWHT_Remaining,
                PMI_Total, PMI_Completed, PMI_Remaining,
                UT_Total, UT_Completed, UT_Remaining,
                MT_Total, MT_Completed, MT_Remaining,
                FT_Total, FT_Completed, FT_Remaining
            ) VALUES (
                %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s
            )
            ON DUPLICATE KEY UPDATE
                VT_Total = VALUES(VT_Total), VT_Completed = VALUES(VT_Completed), VT_Remaining = VALUES(VT_Remaining),
                RT_Total = VALUES(RT_Total), RT_Completed = VALUES(RT_Completed), RT_Remaining = VALUES(RT_Remaining),
                PT_Total = VALUES(PT_Total), PT_Completed = VALUES(PT_Completed), PT_Remaining = VALUES(PT_Remaining),
                HT_Total = VALUES(HT_Total), HT_Completed = VALUES(HT_Completed), HT_Remaining = VALUES(HT_Remaining),
                PWHT_Total = VALUES(PWHT_Total), PWHT_Completed = VALUES(PWHT_Completed), PWHT_Remaining = VALUES(PWHT_Remaining),
                PMI_Total = VALUES(PMI_Total), PMI_Completed = VALUES(PMI_Completed), PMI_Remaining = VALUES(PMI_Remaining),
                UT_Total = VALUES(UT_Total), UT_Completed = VALUES(UT_Completed), UT_Remaining = VALUES(UT_Remaining),
                MT_Total = VALUES(MT_Total), MT_Completed = VALUES(MT_Completed), MT_Remaining = VALUES(MT_Remaining),
                FT_Total = VALUES(FT_Total), FT_Completed = VALUES(FT_Completed), FT_Remaining = VALUES(FT_Remaining),
                updated_at = CURRENT_TIMESTAMP
        """, (
            test_package_id,
            stats['VT_Total'], stats['VT_Completed'], stats['VT_Remaining'],
            stats['RT_Total'], stats['RT_Completed'], stats['RT_Remaining'],
            stats['PT_Total'], stats['PT_Completed'], stats['PT_Remaining'],
            stats['HT_Total'], stats['HT_Completed'], stats['HT_Remaining'],
            stats['PWHT_Total'], stats['PWHT_Completed'], stats['PWHT_Remaining'],
            stats['PMI_Total'], stats['PMI_Completed'], stats['PMI_Remaining'],
            stats['UT_Total'], stats['UT_Completed'], stats['UT_Remaining'],
            stats['MT_Total'], stats['MT_Completed'], stats['MT_Remaining'],
            stats['FT_Total'], stats['FT_Completed'], stats['FT_Remaining']
        ))
        
        conn.commit()
        return True
        
    except Exception as e:
        print(f"刷新NDEPWHTStatus失败: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


def refresh_iso_drawing_list(test_package_id):
    """
    从 WeldingList 提取唯一的 ISO 图纸编号到 ISODrawingList
    注意：只提取 DrawingNumber 字段包含 'ISO' 的记录
    """
    conn = create_connection()
    if not conn:
        return False
    
    try:
        cur = conn.cursor(dictionary=True)
        
        # 1. 删除旧数据
        cur.execute("DELETE FROM ISODrawingList WHERE TestPackageID = %s", (test_package_id,))
        
        # 2. 从 WeldingList 提取唯一的 ISO 图纸编号（只提取包含'ISO'的）
        cur.execute("""
            SELECT DISTINCT DrawingNumber, RevNo
            FROM WeldingList
            WHERE TestPackageID = %s 
              AND DrawingNumber IS NOT NULL 
              AND DrawingNumber != ''
              AND UPPER(DrawingNumber) LIKE '%ISO%'
            ORDER BY DrawingNumber, RevNo
        """, (test_package_id,))
        
        drawings = cur.fetchall()
        
        # 3. 插入到 ISODrawingList
        for drawing in drawings:
            iso_no = drawing['DrawingNumber']
            rev_no = drawing['RevNo'] if drawing['RevNo'] else None
            
            cur.execute("""
                INSERT INTO ISODrawingList (TestPackageID, ISODrawingNo, RevNo)
                VALUES (%s, %s, %s)
            """, (test_package_id, iso_no, rev_no))
        
        conn.commit()
        return True
        
    except Exception as e:
        print(f"刷新ISODrawingList失败: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


def refresh_all_aggregated_data(test_package_id):
    """
    刷新指定试压包的所有聚合数据
    """
    success = True
    success &= refresh_joint_summary(test_package_id)
    success &= refresh_nde_pwht_status(test_package_id)
    success &= refresh_iso_drawing_list(test_package_id)
    return success


def refresh_all_packages_aggregated_data(test_package_ids=None, verbose=True):
    """
    批量刷新聚合数据。若 test_package_ids 为 None，则全量重建三张聚合表；否则退化为逐个刷新。
    """
    if test_package_ids:
        total = len(test_package_ids)
        success = 0
        failed = 0
        for idx, tp_id in enumerate(test_package_ids, start=1):
            result = refresh_all_aggregated_data(tp_id)
            if result:
                success += 1
            else:
                failed += 1
            if verbose and total:
                print(f"  -> [{idx}/{total}] 刷新试压包 {tp_id} {'成功' if result else '失败'}")
        # 同步刷新系统 / 子系统汇总（增量模式简单起见，直接全表重建）
        refresh_system_and_subsystem_summaries(verbose=verbose)
        return {'mode': 'partial', 'total': total, 'success': success, 'failed': failed}
    
    joint_rows = refresh_joint_summary_bulk()
    nde_rows = refresh_nde_pwht_status_bulk()
    iso_rows = refresh_iso_drawing_list_bulk()
    alert_rows = refresh_test_package_preparation_alerts()
    sys_rows, subsys_rows = refresh_system_and_subsystem_summaries(verbose=verbose)
    block_sys_rows, block_subsys_rows = refresh_block_summaries(verbose=verbose)
    if verbose:
        print(f"JointSummary refreshed rows: {joint_rows}")
        print(f"NDEPWHTStatus refreshed rows: {nde_rows}")
        print(f"ISODrawingList refreshed rows: {iso_rows}")
        print(f"Preparation alerts refreshed rows: {alert_rows}")
        print(f"SystemWeldingSummary refreshed rows: {sys_rows}")
        print(f"SubsystemWeldingSummary refreshed rows: {subsys_rows}")
        print(f"BlockSystemSummary refreshed rows: {block_sys_rows}")
        print(f"BlockSubsystemSummary refreshed rows: {block_subsys_rows}")
    return {
        'mode': 'full',
        'joint_rows': joint_rows,
        'nde_rows': nde_rows,
        'iso_rows': iso_rows,
        'alert_rows': alert_rows,
        'system_rows': sys_rows,
        'subsystem_rows': subsys_rows,
        'block_system_rows': block_sys_rows,
        'block_subsystem_rows': block_subsys_rows
    }


def refresh_block_summaries(verbose=True):
    """
    基于 WeldingList / HydroTestPackageList，按 Block 预聚合系统 / 子系统级统计，
    用于 Faclist 过滤时的高速查询：
    - BlockSystemSummary:  (Block, SystemCode)
    - BlockSubsystemSummary: (Block, SystemCode, SubSystemCode)
    """
    # 复用 ensure_welding_summary_tables 中的建表逻辑
    ensure_welding_summary_tables()
    conn = create_connection()
    if not conn:
        return 0, 0

    try:
        cur = conn.cursor()

        # ---------- BlockSystemSummary ----------
        cur.execute("TRUNCATE TABLE BlockSystemSummary")
        cur.execute(
            """
            INSERT INTO BlockSystemSummary (
                Block,
                SystemCode,
                TotalDIN,
                CompletedDIN,
                TotalPackages,
                TestedPackages
            )
            SELECT
                CASE
                    -- 如果 Block 格式是 B-C-A（例如：00051-00-5100），转换为 A-B-C（例如：5100-00051-00）
                    WHEN (LENGTH(wl.Block) - LENGTH(REPLACE(wl.Block, '-', ''))) = 2 THEN
                        CONCAT(
                            SUBSTRING_INDEX(wl.Block, '-', -1),  -- A: 最后一段
                            '-',
                            SUBSTRING_INDEX(wl.Block, '-', 1),    -- B: 第一段
                            '-',
                            SUBSTRING_INDEX(SUBSTRING_INDEX(wl.Block, '-', 2), '-', -1)  -- C: 第二段
                        )
                    ELSE
                        wl.Block  -- 如果格式不是 B-C-A，保持原样
                END AS Block,
                wl.SystemCode,
                COALESCE(SUM(wl.Size), 0) AS TotalDIN,
                COALESCE(SUM(CASE WHEN wl.WeldDate IS NOT NULL THEN wl.Size ELSE 0 END), 0) AS CompletedDIN,
                COUNT(DISTINCT wl.TestPackageID) AS TotalPackages,
                COUNT(
                    DISTINCT CASE
                        WHEN h.ActualDate IS NOT NULL THEN wl.TestPackageID
                        ELSE NULL
                    END
                ) AS TestedPackages
            FROM WeldingList wl
            LEFT JOIN HydroTestPackageList h
                ON wl.TestPackageID = h.TestPackageID
            WHERE wl.Block IS NOT NULL
              AND TRIM(wl.Block) <> ''
              AND wl.SystemCode IS NOT NULL
              AND TRIM(wl.SystemCode) <> ''
            GROUP BY Block, wl.SystemCode
            """
        )
        block_sys_rows = cur.rowcount or 0

        # ---------- BlockSubsystemSummary ----------
        cur.execute("TRUNCATE TABLE BlockSubsystemSummary")
        cur.execute(
            """
            INSERT INTO BlockSubsystemSummary (
                Block,
                SystemCode,
                SubSystemCode,
                TotalDIN,
                CompletedDIN,
                TotalPackages,
                TestedPackages
            )
            SELECT
                CASE
                    -- 如果 Block 格式是 B-C-A（例如：00051-00-5100），转换为 A-B-C（例如：5100-00051-00）
                    WHEN (LENGTH(wl.Block) - LENGTH(REPLACE(wl.Block, '-', ''))) = 2 THEN
                        CONCAT(
                            SUBSTRING_INDEX(wl.Block, '-', -1),  -- A: 最后一段
                            '-',
                            SUBSTRING_INDEX(wl.Block, '-', 1),    -- B: 第一段
                            '-',
                            SUBSTRING_INDEX(SUBSTRING_INDEX(wl.Block, '-', 2), '-', -1)  -- C: 第二段
                        )
                    ELSE
                        wl.Block  -- 如果格式不是 B-C-A，保持原样
                END AS Block,
                wl.SystemCode,
                wl.SubSystemCode,
                COALESCE(SUM(wl.Size), 0) AS TotalDIN,
                COALESCE(SUM(CASE WHEN wl.WeldDate IS NOT NULL THEN wl.Size ELSE 0 END), 0) AS CompletedDIN,
                COUNT(DISTINCT wl.TestPackageID) AS TotalPackages,
                COUNT(
                    DISTINCT CASE
                        WHEN h.ActualDate IS NOT NULL THEN wl.TestPackageID
                        ELSE NULL
                    END
                ) AS TestedPackages
            FROM WeldingList wl
            LEFT JOIN HydroTestPackageList h
                ON wl.TestPackageID = h.TestPackageID
            WHERE wl.Block IS NOT NULL
              AND TRIM(wl.Block) <> ''
              AND wl.SubSystemCode IS NOT NULL
              AND TRIM(wl.SubSystemCode) <> ''
            GROUP BY Block, wl.SystemCode, wl.SubSystemCode
            """
        )
        block_subsys_rows = cur.rowcount or 0

        conn.commit()
        if verbose:
            print(f"[AGG] BlockSystemSummary refreshed: {block_sys_rows} rows")
            print(f"[AGG] BlockSubsystemSummary refreshed: {block_subsys_rows} rows")
        return block_sys_rows, block_subsys_rows
    except Exception as exc:
        print(f"刷新 BlockSystem/BlockSubsystem 汇总失败: {exc}")
        conn.rollback()
        return 0, 0
    finally:
        conn.close()


def refresh_system_and_subsystem_summaries(verbose=True):
    """
    从 WeldingList / HydroTestPackageList 生成系统 / 子系统级别的汇总表：
    - TotalDIN / CompletedDIN
    - TotalPackages / TestedPackages
    """
    ensure_welding_summary_tables()
    conn = create_connection()
    if not conn:
        return 0, 0

    try:
        cur = conn.cursor()

        # ---------- SystemWeldingSummary ----------
        cur.execute("TRUNCATE TABLE SystemWeldingSummary")
        cur.execute(
            """
            INSERT INTO SystemWeldingSummary (
                SystemCode,
                TotalDIN,
                CompletedDIN,
                TotalPackages,
                TestedPackages
            )
            SELECT
                s.SystemCode,
                COALESCE(w.total_din, 0) AS TotalDIN,
                COALESCE(w.completed_din, 0) AS CompletedDIN,
                COALESCE(p.total_packages, 0) AS TotalPackages,
                COALESCE(p.tested_packages, 0) AS TestedPackages
            FROM SystemList s
            LEFT JOIN (
                SELECT
                    SystemCode,
                    COALESCE(SUM(Size), 0) AS total_din,
                    COALESCE(SUM(CASE WHEN WeldDate IS NOT NULL THEN Size ELSE 0 END), 0) AS completed_din
                FROM WeldingList
                WHERE SystemCode IS NOT NULL AND TRIM(SystemCode) <> ''
                GROUP BY SystemCode
            ) w ON w.SystemCode = s.SystemCode
            LEFT JOIN (
                SELECT
                    SystemCode,
                    COUNT(DISTINCT TestPackageID) AS total_packages,
                    COUNT(DISTINCT CASE WHEN ActualDate IS NOT NULL THEN TestPackageID END) AS tested_packages
                FROM HydroTestPackageList
                WHERE SystemCode IS NOT NULL AND TRIM(SystemCode) <> ''
                GROUP BY SystemCode
            ) p ON p.SystemCode = s.SystemCode
            """
        )
        sys_rows = cur.rowcount or 0

        # ---------- SubsystemWeldingSummary ----------
        cur.execute("TRUNCATE TABLE SubsystemWeldingSummary")
        cur.execute(
            """
            INSERT INTO SubsystemWeldingSummary (
                SystemCode,
                SubSystemCode,
                TotalDIN,
                CompletedDIN,
                TotalPackages,
                TestedPackages
            )
            SELECT
                sub.SystemCode,
                sub.SubSystemCode,
                COALESCE(w.total_din, 0) AS TotalDIN,
                COALESCE(w.completed_din, 0) AS CompletedDIN,
                COALESCE(p.total_packages, 0) AS TotalPackages,
                COALESCE(p.tested_packages, 0) AS TestedPackages
            FROM SubsystemList sub
            LEFT JOIN (
                SELECT
                    SubSystemCode,
                    COALESCE(SUM(Size), 0) AS total_din,
                    COALESCE(SUM(CASE WHEN WeldDate IS NOT NULL THEN Size ELSE 0 END), 0) AS completed_din
                FROM WeldingList
                WHERE SubSystemCode IS NOT NULL AND TRIM(SubSystemCode) <> ''
                GROUP BY SubSystemCode
            ) w ON w.SubSystemCode = sub.SubSystemCode
            LEFT JOIN (
                SELECT
                    SubSystemCode,
                    COUNT(DISTINCT TestPackageID) AS total_packages,
                    COUNT(DISTINCT CASE WHEN ActualDate IS NOT NULL THEN TestPackageID END) AS tested_packages
                FROM HydroTestPackageList
                WHERE SubSystemCode IS NOT NULL AND TRIM(SubSystemCode) <> ''
                GROUP BY SubSystemCode
            ) p ON p.SubSystemCode = sub.SubSystemCode
            """
        )
        subsys_rows = cur.rowcount or 0

        conn.commit()
        if verbose:
            print(f"[AGG] SystemWeldingSummary refreshed: {sys_rows} rows")
            print(f"[AGG] SubsystemWeldingSummary refreshed: {subsys_rows} rows")
        return sys_rows, subsys_rows
    except Exception as exc:
        print(f"刷新 System/Subsystem 汇总失败: {exc}")
        conn.rollback()
        return 0, 0
    finally:
        conn.close()


def refresh_joint_summary_bulk():
    conn = create_connection()
    if not conn:
        return 0
    try:
        cur = conn.cursor()
        cur.execute("TRUNCATE TABLE JointSummary")
        cur.execute("""
            INSERT INTO JointSummary (
                TestPackageID, TotalJoints, CompletedJoints, RemainingJoints,
                TotalDIN, CompletedDIN, RemainingDIN
            )
            SELECT 
                TestPackageID,
                COUNT(*) AS TotalJoints,
                SUM(CASE WHEN Status = '已完成' OR Status = 'Completed' OR WeldDate IS NOT NULL THEN 1 ELSE 0 END) AS CompletedJoints,
                COUNT(*) - SUM(CASE WHEN Status = '已完成' OR Status = 'Completed' OR WeldDate IS NOT NULL THEN 1 ELSE 0 END) AS RemainingJoints,
                COALESCE(SUM(Size), 0) AS TotalDIN,
                COALESCE(SUM(CASE WHEN Status = '已完成' OR Status = 'Completed' OR WeldDate IS NOT NULL THEN Size ELSE 0 END), 0) AS CompletedDIN,
                COALESCE(SUM(Size), 0) - COALESCE(SUM(CASE WHEN Status = '已完成' OR Status = 'Completed' OR WeldDate IS NOT NULL THEN Size ELSE 0 END), 0) AS RemainingDIN
            FROM WeldingList
            WHERE TestPackageID IS NOT NULL AND TestPackageID <> ''
            GROUP BY TestPackageID
        """)
        conn.commit()
        return cur.rowcount or 0
    finally:
        conn.close()


def refresh_iso_drawing_list_bulk():
    conn = create_connection()
    if not conn:
        return 0
    try:
        cur = conn.cursor()
        cur.execute("TRUNCATE TABLE ISODrawingList")
        cur.execute("""
            INSERT INTO ISODrawingList (TestPackageID, ISODrawingNo, RevNo)
            SELECT DISTINCT
                TestPackageID,
                DrawingNumber,
                RevNo
            FROM WeldingList
            WHERE TestPackageID IS NOT NULL
              AND TestPackageID <> ''
              AND DrawingNumber IS NOT NULL
              AND DrawingNumber <> ''
              AND UPPER(DrawingNumber) LIKE '%ISO%'
        """)
        conn.commit()
        return cur.rowcount or 0
    finally:
        conn.close()


def refresh_nde_pwht_status_bulk():
    conn = create_connection()
    if not conn:
        return 0
    try:
        cur = conn.cursor(dictionary=True)
        # 完焊统计
        cur.execute("""
            SELECT 
                TestPackageID,
                COUNT(*) AS total_welds,
                SUM(CASE WHEN WeldDate IS NOT NULL OR Status = '已完成' OR Status = 'Completed' THEN 1 ELSE 0 END) AS welded_count
            FROM WeldingList
            WHERE TestPackageID IS NOT NULL AND TestPackageID <> ''
            GROUP BY TestPackageID
        """)
        completion = {}
        for row in cur.fetchall():
            completion[row['TestPackageID']] = row
        
        # 管线 / 焊工检测情况（仅统计已完成焊口）
        cur.execute("""
            SELECT 
                wl.TestPackageID,
                wl.PipelineNumber,
                wl.WelderRoot,
                COUNT(*) AS total_welds,
                SUM(CASE WHEN wl.VTResult IS NOT NULL AND wl.VTResult <> '' THEN 1 ELSE 0 END) AS VT_count,
                SUM(CASE WHEN wl.RTResult IS NOT NULL AND wl.RTResult <> '' THEN 1 ELSE 0 END) AS RT_count,
                SUM(CASE WHEN wl.PTResult IS NOT NULL AND wl.PTResult <> '' THEN 1 ELSE 0 END) AS PT_count,
                SUM(CASE WHEN wl.UTResult IS NOT NULL AND wl.UTResult <> '' THEN 1 ELSE 0 END) AS UT_count,
                SUM(CASE WHEN wl.MTResult IS NOT NULL AND wl.MTResult <> '' THEN 1 ELSE 0 END) AS MT_count,
                SUM(CASE WHEN wl.PMIResult IS NOT NULL AND wl.PMIResult <> '' THEN 1 ELSE 0 END) AS PMI_count,
                SUM(CASE WHEN wl.FTResult IS NOT NULL AND wl.FTResult <> '' THEN 1 ELSE 0 END) AS FT_count,
                SUM(CASE WHEN wl.HTResult IS NOT NULL AND wl.HTResult <> '' THEN 1 ELSE 0 END) AS HT_count,
                SUM(CASE WHEN wl.PWHTResult IS NOT NULL AND wl.PWHTResult <> '' THEN 1 ELSE 0 END) AS PWHT_count,
                ll.NDEGrade
            FROM WeldingList wl
            LEFT JOIN LineList ll ON wl.PipelineNumber = ll.LineID
            WHERE wl.TestPackageID IS NOT NULL AND wl.TestPackageID <> ''
              AND (wl.WeldDate IS NOT NULL OR wl.Status = '已完成' OR wl.Status = 'Completed')
            GROUP BY wl.TestPackageID, wl.PipelineNumber, wl.WelderRoot, ll.NDEGrade
        """)
        test_types = ['VT', 'RT', 'PT', 'UT', 'MT', 'PMI', 'FT', 'HT', 'PWHT']
        stats_by_package = {}

        def init_stats(all_completed):
            base = {}
            for t in test_types:
                base[t] = {
                    'Completed': 0,
                    'Total': 0 if all_completed else None,
                    'Remaining': 0 if all_completed else None
                }
            base['all_completed'] = all_completed
            return base

        for row in cur.fetchall():
            test_package_id = row['TestPackageID']
            if not test_package_id:
                continue
            package_summary = completion.get(test_package_id, {'total_welds': 0, 'welded_count': 0})
            all_completed = package_summary['total_welds'] == package_summary['welded_count'] and package_summary['total_welds'] > 0
            pkg_stats = stats_by_package.setdefault(test_package_id, init_stats(all_completed))
            nde_requirements = parse_nde_grade(row.get('NDEGrade'))
            total_welds = row['total_welds'] or 0
            for test_type in test_types:
                completed_count = row.get(f'{test_type}_count') or 0
                pkg_stats[test_type]['Completed'] += completed_count
                if pkg_stats[test_type]['Total'] is not None and nde_requirements.get(test_type, 0) > 0:
                    required = int(total_welds * nde_requirements[test_type] / 100)
                    pkg_stats[test_type]['Total'] += required

        # 生成最终记录
        records = []
        for test_package_id, summary in completion.items():
            pkg_stats = stats_by_package.get(test_package_id)
            if not pkg_stats:
                pkg_stats = init_stats(
                    summary['total_welds'] == summary['welded_count'] and summary['total_welds'] > 0
                )
            for test_type in test_types:
                if pkg_stats[test_type]['Total'] is not None:
                    pkg_stats[test_type]['Remaining'] = pkg_stats[test_type]['Total'] - pkg_stats[test_type]['Completed']
            records.append((
                test_package_id,
                pkg_stats['VT']['Total'], pkg_stats['VT']['Completed'], pkg_stats['VT']['Remaining'],
                pkg_stats['RT']['Total'], pkg_stats['RT']['Completed'], pkg_stats['RT']['Remaining'],
                pkg_stats['PT']['Total'], pkg_stats['PT']['Completed'], pkg_stats['PT']['Remaining'],
                pkg_stats['HT']['Total'], pkg_stats['HT']['Completed'], pkg_stats['HT']['Remaining'],
                pkg_stats['PWHT']['Total'], pkg_stats['PWHT']['Completed'], pkg_stats['PWHT']['Remaining'],
                pkg_stats['PMI']['Total'], pkg_stats['PMI']['Completed'], pkg_stats['PMI']['Remaining'],
                pkg_stats['UT']['Total'], pkg_stats['UT']['Completed'], pkg_stats['UT']['Remaining'],
                pkg_stats['MT']['Total'], pkg_stats['MT']['Completed'], pkg_stats['MT']['Remaining'],
                pkg_stats['FT']['Total'], pkg_stats['FT']['Completed'], pkg_stats['FT']['Remaining']
            ))

        cur.execute("TRUNCATE TABLE NDEPWHTStatus")
        if records:
            expected_len = 1 + len(test_types) * 3
            columns = ['TestPackageID']
            placeholders = ['%s']
            for t in test_types:
                columns.extend([f"{t}_Total", f"{t}_Completed", f"{t}_Remaining"])
                placeholders.extend(['%s', '%s', '%s'])
            insert_sql = f"""
                INSERT INTO NDEPWHTStatus (
                    {', '.join(columns)}
                ) VALUES (
                    {', '.join(placeholders)}
                )
            """
            adjusted_records = []
            for rec in records:
                if len(rec) == expected_len:
                    adjusted_records.append(rec)
                elif len(rec) > expected_len:
                    adjusted_records.append(rec[:expected_len])
                else:
                    padding = [None] * (expected_len - len(rec))
                    adjusted_records.append(tuple(list(rec) + padding))
            cur.executemany(insert_sql, adjusted_records)
        conn.commit()
        return len(records)
    finally:
        conn.close()


def refresh_test_package_preparation_alerts(system_share_threshold=None):
    threshold = system_share_threshold or PIPELINE_SYSTEM_SHARE_THRESHOLD
    conn = create_connection()
    if not conn:
        return 0
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS TestPackagePreparationAlert (
                AlertID INT AUTO_INCREMENT PRIMARY KEY,
                SystemCode VARCHAR(50) NOT NULL,
                PipelineNumber VARCHAR(100) NOT NULL,
                TotalDIN DECIMAL(18,4) NOT NULL DEFAULT 0,
                CompletedDIN DECIMAL(18,4) NOT NULL DEFAULT 0,
                CompletionRate DECIMAL(5,4) NOT NULL DEFAULT 0,
                SystemDINShare DECIMAL(5,4) NOT NULL DEFAULT 0,
                ThresholdMet TINYINT(1) NOT NULL DEFAULT 0,
                CreatedAt DATETIME DEFAULT CURRENT_TIMESTAMP,
                Status VARCHAR(20) DEFAULT 'PENDING',
                Remarks VARCHAR(255),
                INDEX idx_alert_system (SystemCode),
                INDEX idx_alert_status (Status)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)
        cur.execute("TRUNCATE TABLE TestPackagePreparationAlert")
        base_pipeline_stats = """
            SELECT
                SystemCode,
                PipelineNumber,
                COALESCE(SUM(Size), 0) AS total_din,
                COALESCE(SUM(CASE WHEN WeldDate IS NOT NULL OR Status = '已完成' OR Status = 'Completed'
                                  THEN Size ELSE 0 END), 0) AS completed_din
            FROM WeldingList
            WHERE SystemCode IS NOT NULL AND TRIM(SystemCode) <> ''
              AND PipelineNumber IS NOT NULL AND TRIM(PipelineNumber) <> ''
              AND IsDeleted = FALSE
            GROUP BY SystemCode, PipelineNumber
        """
        query = f"""
            INSERT INTO TestPackagePreparationAlert (
                SystemCode,
                PipelineNumber,
                TotalDIN,
                CompletedDIN,
                CompletionRate,
                SystemDINShare,
                ThresholdMet
            )
            SELECT
                cp.SystemCode,
                cp.PipelineNumber,
                cp.total_din,
                cp.completed_din,
                CASE WHEN cp.total_din > 0 THEN cp.completed_din / cp.total_din ELSE 0 END AS completion_rate,
                CASE WHEN ss.system_total_din > 0 THEN ss.system_completed_din / ss.system_total_din ELSE 0 END AS system_share,
                CASE WHEN ss.system_total_din > 0 AND ss.system_completed_din / ss.system_total_din >= %s THEN 1 ELSE 0 END AS threshold_met
            FROM (
                SELECT
                    bs.SystemCode,
                    bs.PipelineNumber,
                    bs.total_din,
                    bs.completed_din,
                    CASE WHEN bs.total_din > 0 AND bs.completed_din >= bs.total_din THEN 1 ELSE 0 END AS is_completed
                FROM (
                    {base_pipeline_stats}
                ) bs
            ) cp
            JOIN (
                SELECT
                    bs2.SystemCode,
                    SUM(bs2.total_din) AS system_total_din,
                    SUM(CASE WHEN bs2.total_din > 0 AND bs2.completed_din >= bs2.total_din THEN bs2.total_din ELSE 0 END) AS system_completed_din
                FROM (
                    {base_pipeline_stats}
                ) bs2
                GROUP BY bs2.SystemCode
            ) ss ON ss.SystemCode = cp.SystemCode
            WHERE cp.is_completed = 1
              AND ss.system_total_din > 0
              AND ss.system_completed_din / ss.system_total_din >= %s
        """
        cur.execute(query, (threshold, threshold))
        conn.commit()
        return cur.rowcount or 0
    finally:
        conn.close()


if __name__ == '__main__':
    print("Refreshing aggregated data for all test packages...")
    stats = refresh_all_packages_aggregated_data()
    if stats.get('mode') == 'full':
        print(f"JointSummary rows: {stats['joint_rows']}")
        print(f"NDEPWHTStatus rows: {stats['nde_rows']}")
        print(f"ISODrawingList rows: {stats['iso_rows']}")
        print(f"Preparation alerts rows: {stats.get('alert_rows', 0)}")
    else:
        print(f"Total: {stats['total']}, Success: {stats['success']}, Failed: {stats['failed']}")

