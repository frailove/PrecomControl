from flask import Blueprint, render_template, jsonify, request
from database import create_connection
from utils.auth_decorators import login_required
from datetime import datetime, timedelta
from collections import defaultdict
from math import ceil
import json

# 导入Faclist筛选器函数
from routes.system_routes import get_faclist_filter_options, resolve_system_codes_by_blocks

# 创建蓝图
dashboard_bp = Blueprint('dashboard', __name__)

# 模块类型定义
MODULE_TYPES = {
    'overview': {'name': '总览', 'icon': 'bi-speedometer2'},
    'test': {'name': '试压包', 'icon': 'bi-box-seam-fill'},
    'flushing': {'name': '吹扫', 'icon': 'bi-droplet-fill'},
    'reinstatement': {'name': '复位', 'icon': 'bi-arrow-repeat'},
    'precom_manhole': {'name': '人孔检查', 'icon': 'bi-door-open'},
    'precom_motor_solo': {'name': '电机单试', 'icon': 'bi-lightning-charge-fill'},
    'precom_skid_install': {'name': '台件安装', 'icon': 'bi-hdd-network'},
    'precom_loop_test': {'name': '回路测试', 'icon': 'bi-activity'},
    'precom_alignment': {'name': '最终对中', 'icon': 'bi-arrow-repeat'},
    'precom_mrt': {'name': 'MRT联动测试', 'icon': 'bi-diagram-3'},
    'precom_function_test': {'name': 'Function Test', 'icon': 'bi-check2-square'}
}


def get_test_package_stats(level='system', system_code=None, subsystem_code=None, matched_blocks=None, allowed_system_codes=None):
    """获取试压包统计（基于ActualDate）"""
    conn = create_connection()
    if not conn:
        return []
    
    try:
        cur = conn.cursor(dictionary=True)
        if level == 'system':
            where_clauses = ["s.IsDeleted = FALSE"]
            params = []
            
            if system_code:
                where_clauses.append("s.SystemCode = %s")
                params.append(system_code)
            if allowed_system_codes is not None:
                if len(allowed_system_codes) == 0:
                    return []
                placeholders = ','.join(['%s'] * len(allowed_system_codes))
                where_clauses.append(f"s.SystemCode IN ({placeholders})")
                params.extend(allowed_system_codes)
            
            if matched_blocks:
                block_placeholders = ','.join(['%s'] * len(matched_blocks))
                block_params = tuple(matched_blocks)
                # 构建尾项统计的 WHERE 条件（使用相同的 block 筛选）
                punch_where = f"""
                    EXISTS (
                        SELECT 1 FROM WeldingList wl
                        WHERE wl.TestPackageID = h.TestPackageID
                        AND wl.Block IN ({block_placeholders})
                    )
                """
                sql = f"""
                    SELECT DISTINCT
                        s.SystemCode,
                        s.SystemDescriptionENG,
                        s.ProcessOrNonProcess,
                        COALESCE(SUM(bss.TotalPackages), 0) AS TotalPackages,
                        COALESCE(SUM(bss.TestedPackages), 0) AS TestedPackages,
                        COALESCE(SUM(bss.TotalDIN), 0) AS TotalDIN,
                        COALESCE(SUM(bss.CompletedDIN), 0) AS CompletedDIN,
                        CASE 
                            WHEN SUM(bss.TotalPackages) > 0 THEN (SUM(bss.TestedPackages) / SUM(bss.TotalPackages)) * 100
                            ELSE 0
                        END AS Progress,
                        -- 尾项统计（需要考虑Faclist筛选）
                        COALESCE((SELECT COUNT(*) FROM PunchList pl 
                            WHERE pl.TestPackageID IN 
                                (SELECT h.TestPackageID FROM HydroTestPackageList h 
                                 WHERE h.SystemCode = s.SystemCode AND h.IsDeleted = FALSE
                                 AND {punch_where})
                            AND (pl.Deleted IS NULL OR pl.Deleted != 'Y')
                        ), 0) AS PunchTotal,
                        COALESCE((SELECT COUNT(*) FROM PunchList pl 
                            WHERE pl.TestPackageID IN 
                                (SELECT h.TestPackageID FROM HydroTestPackageList h 
                                 WHERE h.SystemCode = s.SystemCode AND h.IsDeleted = FALSE
                                 AND {punch_where})
                            AND pl.Rectified = 'Y' AND (pl.Deleted IS NULL OR pl.Deleted != 'Y')
                        ), 0) AS PunchRectified,
                        COALESCE((SELECT COUNT(*) FROM PunchList pl 
                            WHERE pl.TestPackageID IN 
                                (SELECT h.TestPackageID FROM HydroTestPackageList h 
                                 WHERE h.SystemCode = s.SystemCode AND h.IsDeleted = FALSE
                                 AND {punch_where})
                            AND pl.Verified = 'Y' AND (pl.Deleted IS NULL OR pl.Deleted != 'Y')
                        ), 0) AS PunchVerified
                    FROM SystemList s
                    LEFT JOIN BlockSystemSummary bss ON bss.SystemCode = s.SystemCode 
                        AND bss.Block IN ({block_placeholders})
                    WHERE {' AND '.join(where_clauses)}
                    GROUP BY s.SystemCode, s.SystemDescriptionENG, s.ProcessOrNonProcess
                    ORDER BY s.SystemCode
                """
                # 参数顺序：where_clauses 参数 + bss.Block 参数 + 3个尾项统计的 punch_where 参数（每个都需要 block_params）
                cur.execute(sql, tuple(params) + block_params + block_params + block_params + block_params)
            else:
                sql = f"""
                    SELECT 
                        s.SystemCode,
                        s.SystemDescriptionENG,
                        s.ProcessOrNonProcess,
                        COALESCE(sws.TotalPackages, 0) AS TotalPackages,
                        COALESCE(sws.TestedPackages, 0) AS TestedPackages,
                        COALESCE(sws.TotalDIN, 0) AS TotalDIN,
                        COALESCE(sws.CompletedDIN, 0) AS CompletedDIN,
                        CASE 
                            WHEN sws.TotalPackages > 0 THEN (sws.TestedPackages / sws.TotalPackages) * 100
                            ELSE 0
                        END AS Progress,
                        -- 尾项统计
                        COALESCE((SELECT COUNT(*) FROM PunchList pl 
                            WHERE pl.TestPackageID IN 
                                (SELECT h.TestPackageID FROM HydroTestPackageList h 
                                 WHERE h.SystemCode = s.SystemCode AND h.IsDeleted = FALSE)
                            AND (pl.Deleted IS NULL OR pl.Deleted != 'Y')
                        ), 0) AS PunchTotal,
                        COALESCE((SELECT COUNT(*) FROM PunchList pl 
                            WHERE pl.TestPackageID IN 
                                (SELECT h.TestPackageID FROM HydroTestPackageList h 
                                 WHERE h.SystemCode = s.SystemCode AND h.IsDeleted = FALSE)
                            AND pl.Rectified = 'Y' AND (pl.Deleted IS NULL OR pl.Deleted != 'Y')
                        ), 0) AS PunchRectified,
                        COALESCE((SELECT COUNT(*) FROM PunchList pl 
                            WHERE pl.TestPackageID IN 
                                (SELECT h.TestPackageID FROM HydroTestPackageList h 
                                 WHERE h.SystemCode = s.SystemCode AND h.IsDeleted = FALSE)
                            AND pl.Verified = 'Y' AND (pl.Deleted IS NULL OR pl.Deleted != 'Y')
                        ), 0) AS PunchVerified
                    FROM SystemList s
                    LEFT JOIN SystemWeldingSummary sws ON sws.SystemCode = s.SystemCode
                    WHERE {' AND '.join(where_clauses)}
                    ORDER BY s.SystemCode
                """
                cur.execute(sql, tuple(params))
        else:  # subsystem
            where_clauses = ["sub.IsDeleted = FALSE"]
            params = []
            
            if system_code:
                where_clauses.append("sub.SystemCode = %s")
                params.append(system_code)
            if subsystem_code:
                where_clauses.append("sub.SubSystemCode = %s")
                params.append(subsystem_code)
            if allowed_system_codes is not None:
                if len(allowed_system_codes) == 0:
                    return []
                placeholders = ','.join(['%s'] * len(allowed_system_codes))
                where_clauses.append(f"sub.SystemCode IN ({placeholders})")
                params.extend(allowed_system_codes)
            
            if matched_blocks:
                block_placeholders = ','.join(['%s'] * len(matched_blocks))
                sql = f"""
                    SELECT DISTINCT
                        sub.SubSystemCode,
                        sub.SystemCode,
                        sub.SubSystemDescriptionENG,
                        sub.ProcessOrNonProcess,
                        COALESCE(SUM(bss.TotalPackages), 0) AS TotalPackages,
                        COALESCE(SUM(bss.TestedPackages), 0) AS TestedPackages,
                        COALESCE(SUM(sws.TotalDIN), 0) AS TotalDIN,
                        COALESCE(SUM(sws.CompletedDIN), 0) AS CompletedDIN,
                        CASE 
                            WHEN SUM(bss.TotalPackages) > 0 THEN (SUM(bss.TestedPackages) / SUM(bss.TotalPackages)) * 100
                            ELSE 0
                        END AS Progress,
                        -- 尾项统计
                        COALESCE((SELECT COUNT(*) FROM PunchList pl 
                            WHERE pl.TestPackageID IN 
                                (SELECT h.TestPackageID FROM HydroTestPackageList h 
                                 WHERE h.SubSystemCode = sub.SubSystemCode AND h.IsDeleted = FALSE)
                            AND (pl.Deleted IS NULL OR pl.Deleted != 'Y')
                        ), 0) AS PunchTotal,
                        COALESCE((SELECT COUNT(*) FROM PunchList pl 
                            WHERE pl.TestPackageID IN 
                                (SELECT h.TestPackageID FROM HydroTestPackageList h 
                                 WHERE h.SubSystemCode = sub.SubSystemCode AND h.IsDeleted = FALSE)
                            AND pl.Rectified = 'Y' AND (pl.Deleted IS NULL OR pl.Deleted != 'Y')
                        ), 0) AS PunchRectified,
                        COALESCE((SELECT COUNT(*) FROM PunchList pl 
                            WHERE pl.TestPackageID IN 
                                (SELECT h.TestPackageID FROM HydroTestPackageList h 
                                 WHERE h.SubSystemCode = sub.SubSystemCode AND h.IsDeleted = FALSE)
                            AND pl.Verified = 'Y' AND (pl.Deleted IS NULL OR pl.Deleted != 'Y')
                        ), 0) AS PunchVerified
                    FROM SubsystemList sub
                    LEFT JOIN BlockSystemSummary bss ON bss.SystemCode = sub.SystemCode 
                        AND bss.Block IN ({block_placeholders})
                    LEFT JOIN SubsystemWeldingSummary sws ON sws.SubSystemCode = sub.SubSystemCode
                    WHERE {' AND '.join(where_clauses)}
                    GROUP BY sub.SubSystemCode, sub.SystemCode, sub.SubSystemDescriptionENG, sub.ProcessOrNonProcess
                    ORDER BY sub.SystemCode, sub.SubSystemCode
                """
                cur.execute(sql, tuple(params) + tuple(matched_blocks))
            else:
                sql = f"""
                    SELECT 
                        sub.SubSystemCode,
                        sub.SystemCode,
                        sub.SubSystemDescriptionENG,
                        sub.ProcessOrNonProcess,
                        COALESCE(sws.TotalPackages, 0) AS TotalPackages,
                        COALESCE(sws.TestedPackages, 0) AS TestedPackages,
                        COALESCE(sws.TotalDIN, 0) AS TotalDIN,
                        COALESCE(sws.CompletedDIN, 0) AS CompletedDIN,
                        CASE 
                            WHEN sws.TotalPackages > 0 THEN (sws.TestedPackages / sws.TotalPackages) * 100
                            ELSE 0
                        END AS Progress,
                        -- 尾项统计
                        COALESCE((SELECT COUNT(*) FROM PunchList pl 
                            WHERE pl.TestPackageID IN 
                                (SELECT h.TestPackageID FROM HydroTestPackageList h 
                                 WHERE h.SubSystemCode = sub.SubSystemCode AND h.IsDeleted = FALSE)
                            AND (pl.Deleted IS NULL OR pl.Deleted != 'Y')
                        ), 0) AS PunchTotal,
                        COALESCE((SELECT COUNT(*) FROM PunchList pl 
                            WHERE pl.TestPackageID IN 
                                (SELECT h.TestPackageID FROM HydroTestPackageList h 
                                 WHERE h.SubSystemCode = sub.SubSystemCode AND h.IsDeleted = FALSE)
                            AND pl.Rectified = 'Y' AND (pl.Deleted IS NULL OR pl.Deleted != 'Y')
                        ), 0) AS PunchRectified,
                        COALESCE((SELECT COUNT(*) FROM PunchList pl 
                            WHERE pl.TestPackageID IN 
                                (SELECT h.TestPackageID FROM HydroTestPackageList h 
                                 WHERE h.SubSystemCode = sub.SubSystemCode AND h.IsDeleted = FALSE)
                            AND pl.Verified = 'Y' AND (pl.Deleted IS NULL OR pl.Deleted != 'Y')
                        ), 0) AS PunchVerified
                    FROM SubsystemList sub
                    LEFT JOIN SubsystemWeldingSummary sws ON sws.SubSystemCode = sub.SubSystemCode
                    WHERE {' AND '.join(where_clauses)}
                    ORDER BY sub.SystemCode, sub.SubSystemCode
                """
                cur.execute(sql, tuple(params))
        return cur.fetchall()
    finally:
        conn.close()


def get_flushing_stats(level='system', system_code=None, subsystem_code=None, matched_blocks=None, allowed_system_codes=None):
    """获取吹扫统计（基于FlushingActualDate或附件）"""
    conn = create_connection()
    if not conn:
        return []
    
    try:
        cur = conn.cursor(dictionary=True)
        # 检查字段是否存在
        cur.execute("SHOW COLUMNS FROM HydroTestPackageList LIKE 'FlushingActualDate'")
        has_flushing_date = cur.fetchone() is not None
        
        if has_flushing_date:
            flush_condition = "(h.FlushingActualDate IS NOT NULL OR tpa.ID IS NOT NULL)"
        else:
            flush_condition = "tpa.ID IS NOT NULL"
        
        where_clauses = []
        params = []
        
        if level == 'system':
            where_clauses.append("s.IsDeleted = FALSE")
            if system_code:
                where_clauses.append("s.SystemCode = %s")
                params.append(system_code)
            if allowed_system_codes is not None:
                if len(allowed_system_codes) == 0:
                    return []
                placeholders = ','.join(['%s'] * len(allowed_system_codes))
                where_clauses.append(f"s.SystemCode IN ({placeholders})")
                params.extend(allowed_system_codes)
            
            sql = """
                SELECT 
                    s.SystemCode,
                    s.SystemDescriptionENG,
                    s.ProcessOrNonProcess,
                    COUNT(DISTINCT h.TestPackageID) AS TotalPackages,
                    COUNT(DISTINCT CASE WHEN """ + flush_condition + """ THEN h.TestPackageID END) AS CompletedPackages,
                    COALESCE(sws.TotalDIN, 0) AS TotalDIN,
                    COALESCE(sws.CompletedDIN, 0) AS CompletedDIN,
                    CASE 
                        WHEN COUNT(DISTINCT h.TestPackageID) > 0 
                        THEN (COUNT(DISTINCT CASE WHEN """ + flush_condition + """ THEN h.TestPackageID END) / COUNT(DISTINCT h.TestPackageID)) * 100
                        ELSE 0
                    END AS Progress,
                    -- 尾项统计
                    COALESCE((SELECT COUNT(*) FROM PunchList pl 
                        WHERE pl.TestPackageID IN 
                            (SELECT h2.TestPackageID FROM HydroTestPackageList h2 
                             WHERE h2.SystemCode = s.SystemCode AND h2.IsDeleted = FALSE)
                        AND (pl.Deleted IS NULL OR pl.Deleted != 'Y')
                    ), 0) AS PunchTotal,
                    COALESCE((SELECT COUNT(*) FROM PunchList pl 
                        WHERE pl.TestPackageID IN 
                            (SELECT h2.TestPackageID FROM HydroTestPackageList h2 
                             WHERE h2.SystemCode = s.SystemCode AND h2.IsDeleted = FALSE)
                        AND pl.Rectified = 'Y' AND (pl.Deleted IS NULL OR pl.Deleted != 'Y')
                    ), 0) AS PunchRectified,
                    COALESCE((SELECT COUNT(*) FROM PunchList pl 
                        WHERE pl.TestPackageID IN 
                            (SELECT h2.TestPackageID FROM HydroTestPackageList h2 
                             WHERE h2.SystemCode = s.SystemCode AND h2.IsDeleted = FALSE)
                        AND pl.Verified = 'Y' AND (pl.Deleted IS NULL OR pl.Deleted != 'Y')
                    ), 0) AS PunchVerified
                FROM SystemList s
                LEFT JOIN HydroTestPackageList h ON h.SystemCode = s.SystemCode AND h.IsDeleted = FALSE
                LEFT JOIN TestPackageAttachments tpa ON tpa.TestPackageID = h.TestPackageID 
                    AND tpa.ModuleName = 'Flushing_Certificate'
                LEFT JOIN SystemWeldingSummary sws ON sws.SystemCode = s.SystemCode
                WHERE """ + " AND ".join(where_clauses) + """
                GROUP BY s.SystemCode, s.SystemDescriptionENG, s.ProcessOrNonProcess, sws.TotalDIN, sws.CompletedDIN
                ORDER BY s.SystemCode
            """
            cur.execute(sql, tuple(params))
        else:  # subsystem
            where_clauses.append("sub.IsDeleted = FALSE")
            if system_code:
                where_clauses.append("sub.SystemCode = %s")
                params.append(system_code)
            if subsystem_code:
                where_clauses.append("sub.SubSystemCode = %s")
                params.append(subsystem_code)
            if allowed_system_codes is not None:
                if len(allowed_system_codes) == 0:
                    return []
                placeholders = ','.join(['%s'] * len(allowed_system_codes))
                where_clauses.append(f"sub.SystemCode IN ({placeholders})")
                params.extend(allowed_system_codes)
            
            sql = """
                SELECT 
                    sub.SubSystemCode,
                    sub.SystemCode,
                    sub.SubSystemDescriptionENG,
                    sub.ProcessOrNonProcess,
                    COUNT(DISTINCT h.TestPackageID) AS TotalPackages,
                    COUNT(DISTINCT CASE WHEN """ + flush_condition + """ THEN h.TestPackageID END) AS CompletedPackages,
                    COALESCE(sws.TotalDIN, 0) AS TotalDIN,
                    COALESCE(sws.CompletedDIN, 0) AS CompletedDIN,
                    CASE 
                        WHEN COUNT(DISTINCT h.TestPackageID) > 0 
                        THEN (COUNT(DISTINCT CASE WHEN """ + flush_condition + """ THEN h.TestPackageID END) / COUNT(DISTINCT h.TestPackageID)) * 100
                        ELSE 0
                    END AS Progress,
                    -- 尾项统计
                    COALESCE((SELECT COUNT(*) FROM PunchList pl 
                        WHERE pl.TestPackageID IN 
                            (SELECT h2.TestPackageID FROM HydroTestPackageList h2 
                             WHERE h2.SubSystemCode = sub.SubSystemCode AND h2.IsDeleted = FALSE)
                        AND (pl.Deleted IS NULL OR pl.Deleted != 'Y')
                    ), 0) AS PunchTotal,
                    COALESCE((SELECT COUNT(*) FROM PunchList pl 
                        WHERE pl.TestPackageID IN 
                            (SELECT h2.TestPackageID FROM HydroTestPackageList h2 
                             WHERE h2.SubSystemCode = sub.SubSystemCode AND h2.IsDeleted = FALSE)
                        AND pl.Rectified = 'Y' AND (pl.Deleted IS NULL OR pl.Deleted != 'Y')
                    ), 0) AS PunchRectified,
                    COALESCE((SELECT COUNT(*) FROM PunchList pl 
                        WHERE pl.TestPackageID IN 
                            (SELECT h2.TestPackageID FROM HydroTestPackageList h2 
                             WHERE h2.SubSystemCode = sub.SubSystemCode AND h2.IsDeleted = FALSE)
                        AND pl.Verified = 'Y' AND (pl.Deleted IS NULL OR pl.Deleted != 'Y')
                    ), 0) AS PunchVerified
                FROM SubsystemList sub
                LEFT JOIN HydroTestPackageList h ON h.SubSystemCode = sub.SubSystemCode AND h.IsDeleted = FALSE
                LEFT JOIN TestPackageAttachments tpa ON tpa.TestPackageID = h.TestPackageID 
                    AND tpa.ModuleName = 'Flushing_Certificate'
                LEFT JOIN SubsystemWeldingSummary sws ON sws.SubSystemCode = sub.SubSystemCode
                WHERE """ + " AND ".join(where_clauses) + """
                GROUP BY sub.SubSystemCode, sub.SystemCode, sub.SubSystemDescriptionENG, sub.ProcessOrNonProcess, sws.TotalDIN, sws.CompletedDIN
                ORDER BY sub.SystemCode, sub.SubSystemCode
            """
            cur.execute(sql, tuple(params))
        return cur.fetchall()
    finally:
        conn.close()


def get_reinstatement_stats(level='system', system_code=None, subsystem_code=None, matched_blocks=None, allowed_system_codes=None):
    """获取复位统计（基于ReinstatementActualDate或附件）"""
    conn = create_connection()
    if not conn:
        return []
    
    try:
        cur = conn.cursor(dictionary=True)
        # 检查字段是否存在
        cur.execute("SHOW COLUMNS FROM HydroTestPackageList LIKE 'ReinstatementActualDate'")
        has_reinst_date = cur.fetchone() is not None
        
        if has_reinst_date:
            reinst_condition = "(h.ReinstatementActualDate IS NOT NULL OR tpa.ID IS NOT NULL)"
        else:
            reinst_condition = "tpa.ID IS NOT NULL"
        
        where_clauses = []
        params = []
        
        if level == 'system':
            where_clauses.append("s.IsDeleted = FALSE")
            if system_code:
                where_clauses.append("s.SystemCode = %s")
                params.append(system_code)
            if allowed_system_codes is not None:
                if len(allowed_system_codes) == 0:
                    return []
                placeholders = ','.join(['%s'] * len(allowed_system_codes))
                where_clauses.append(f"s.SystemCode IN ({placeholders})")
                params.extend(allowed_system_codes)
            
            sql = """
                SELECT 
                    s.SystemCode,
                    s.SystemDescriptionENG,
                    s.ProcessOrNonProcess,
                    COUNT(DISTINCT h.TestPackageID) AS TotalPackages,
                    COUNT(DISTINCT CASE WHEN """ + reinst_condition + """ THEN h.TestPackageID END) AS CompletedPackages,
                    COALESCE(sws.TotalDIN, 0) AS TotalDIN,
                    COALESCE(sws.CompletedDIN, 0) AS CompletedDIN,
                    CASE 
                        WHEN COUNT(DISTINCT h.TestPackageID) > 0 
                        THEN (COUNT(DISTINCT CASE WHEN """ + reinst_condition + """ THEN h.TestPackageID END) / COUNT(DISTINCT h.TestPackageID)) * 100
                        ELSE 0
                    END AS Progress,
                    -- 尾项统计
                    COALESCE((SELECT COUNT(*) FROM PunchList pl 
                        WHERE pl.TestPackageID IN 
                            (SELECT h2.TestPackageID FROM HydroTestPackageList h2 
                             WHERE h2.SystemCode = s.SystemCode AND h2.IsDeleted = FALSE)
                        AND (pl.Deleted IS NULL OR pl.Deleted != 'Y')
                    ), 0) AS PunchTotal,
                    COALESCE((SELECT COUNT(*) FROM PunchList pl 
                        WHERE pl.TestPackageID IN 
                            (SELECT h2.TestPackageID FROM HydroTestPackageList h2 
                             WHERE h2.SystemCode = s.SystemCode AND h2.IsDeleted = FALSE)
                        AND pl.Rectified = 'Y' AND (pl.Deleted IS NULL OR pl.Deleted != 'Y')
                    ), 0) AS PunchRectified,
                    COALESCE((SELECT COUNT(*) FROM PunchList pl 
                        WHERE pl.TestPackageID IN 
                            (SELECT h2.TestPackageID FROM HydroTestPackageList h2 
                             WHERE h2.SystemCode = s.SystemCode AND h2.IsDeleted = FALSE)
                        AND pl.Verified = 'Y' AND (pl.Deleted IS NULL OR pl.Deleted != 'Y')
                    ), 0) AS PunchVerified
                FROM SystemList s
                LEFT JOIN HydroTestPackageList h ON h.SystemCode = s.SystemCode AND h.IsDeleted = FALSE
                LEFT JOIN TestPackageAttachments tpa ON tpa.TestPackageID = h.TestPackageID 
                    AND tpa.ModuleName = 'Reinstatement_Check_List'
                LEFT JOIN SystemWeldingSummary sws ON sws.SystemCode = s.SystemCode
                WHERE """ + " AND ".join(where_clauses) + """
                GROUP BY s.SystemCode, s.SystemDescriptionENG, s.ProcessOrNonProcess, sws.TotalDIN, sws.CompletedDIN
                ORDER BY s.SystemCode
            """
            cur.execute(sql, tuple(params))
        else:  # subsystem
            where_clauses.append("sub.IsDeleted = FALSE")
            if system_code:
                where_clauses.append("sub.SystemCode = %s")
                params.append(system_code)
            if subsystem_code:
                where_clauses.append("sub.SubSystemCode = %s")
                params.append(subsystem_code)
            if allowed_system_codes is not None:
                if len(allowed_system_codes) == 0:
                    return []
                placeholders = ','.join(['%s'] * len(allowed_system_codes))
                where_clauses.append(f"sub.SystemCode IN ({placeholders})")
                params.extend(allowed_system_codes)
            
            sql = """
                SELECT 
                    sub.SubSystemCode,
                    sub.SystemCode,
                    sub.SubSystemDescriptionENG,
                    sub.ProcessOrNonProcess,
                    COUNT(DISTINCT h.TestPackageID) AS TotalPackages,
                    COUNT(DISTINCT CASE WHEN """ + reinst_condition + """ THEN h.TestPackageID END) AS CompletedPackages,
                    COALESCE(sws.TotalDIN, 0) AS TotalDIN,
                    COALESCE(sws.CompletedDIN, 0) AS CompletedDIN,
                    CASE 
                        WHEN COUNT(DISTINCT h.TestPackageID) > 0 
                        THEN (COUNT(DISTINCT CASE WHEN """ + reinst_condition + """ THEN h.TestPackageID END) / COUNT(DISTINCT h.TestPackageID)) * 100
                        ELSE 0
                    END AS Progress,
                    -- 尾项统计
                    COALESCE((SELECT COUNT(*) FROM PunchList pl 
                        WHERE pl.TestPackageID IN 
                            (SELECT h2.TestPackageID FROM HydroTestPackageList h2 
                             WHERE h2.SubSystemCode = sub.SubSystemCode AND h2.IsDeleted = FALSE)
                        AND (pl.Deleted IS NULL OR pl.Deleted != 'Y')
                    ), 0) AS PunchTotal,
                    COALESCE((SELECT COUNT(*) FROM PunchList pl 
                        WHERE pl.TestPackageID IN 
                            (SELECT h2.TestPackageID FROM HydroTestPackageList h2 
                             WHERE h2.SubSystemCode = sub.SubSystemCode AND h2.IsDeleted = FALSE)
                        AND pl.Rectified = 'Y' AND (pl.Deleted IS NULL OR pl.Deleted != 'Y')
                    ), 0) AS PunchRectified,
                    COALESCE((SELECT COUNT(*) FROM PunchList pl 
                        WHERE pl.TestPackageID IN 
                            (SELECT h2.TestPackageID FROM HydroTestPackageList h2 
                             WHERE h2.SubSystemCode = sub.SubSystemCode AND h2.IsDeleted = FALSE)
                        AND pl.Verified = 'Y' AND (pl.Deleted IS NULL OR pl.Deleted != 'Y')
                    ), 0) AS PunchVerified
                FROM SubsystemList sub
                LEFT JOIN HydroTestPackageList h ON h.SubSystemCode = sub.SubSystemCode AND h.IsDeleted = FALSE
                LEFT JOIN TestPackageAttachments tpa ON tpa.TestPackageID = h.TestPackageID 
                    AND tpa.ModuleName = 'Reinstatement_Check_List'
                LEFT JOIN SubsystemWeldingSummary sws ON sws.SubSystemCode = sub.SubSystemCode
                WHERE """ + " AND ".join(where_clauses) + """
                GROUP BY sub.SubSystemCode, sub.SystemCode, sub.SubSystemDescriptionENG, sub.ProcessOrNonProcess, sws.TotalDIN, sws.CompletedDIN
                ORDER BY sub.SystemCode, sub.SubSystemCode
            """
            cur.execute(sql, tuple(params))
        return cur.fetchall()
    finally:
        conn.close()


def get_overview_stats(level='system', system_code=None, subsystem_code=None, matched_blocks=None, allowed_system_codes=None):
    """获取总览统计（包含试压包、吹扫、复位和所有预试车任务）"""
    conn = create_connection()
    if not conn:
        return []
    
    try:
        cur = conn.cursor(dictionary=True)
        # 检查字段是否存在，如果不存在则使用附件判断
        cur.execute("SHOW COLUMNS FROM HydroTestPackageList LIKE 'FlushingActualDate'")
        has_flushing_date = cur.fetchone() is not None
        cur.execute("SHOW COLUMNS FROM HydroTestPackageList LIKE 'ReinstatementActualDate'")
        has_reinst_date = cur.fetchone() is not None
        
        if has_flushing_date and has_reinst_date:
            flush_condition = "(h.FlushingActualDate IS NOT NULL OR tpa_flush.ID IS NOT NULL)"
            reinst_condition = "(h.ReinstatementActualDate IS NOT NULL OR tpa_reinst.ID IS NOT NULL)"
        else:
            flush_condition = "tpa_flush.ID IS NOT NULL"
            reinst_condition = "tpa_reinst.ID IS NOT NULL"
        
        # 构建WHERE条件
        where_clauses = ["s.IsDeleted = FALSE"]
        params = []
        
        if system_code:
            where_clauses.append("s.SystemCode = %s")
            params.append(system_code)
        
        if allowed_system_codes is not None:
            if len(allowed_system_codes) == 0:
                return []
            placeholders = ','.join(['%s'] * len(allowed_system_codes))
            where_clauses.append(f"s.SystemCode IN ({placeholders})")
            params.extend(allowed_system_codes)
        
        if level == 'system':
            # 系统级别：统计试压包、吹扫、复位和所有预试车任务
            # 确保包含所有系统（即使没有试压包或预试车任务）
            sql = """
                SELECT 
                    s.SystemCode,
                    s.SystemDescriptionENG,
                    s.ProcessOrNonProcess,
                    -- 试压包相关
                    COALESCE(COUNT(DISTINCT h.TestPackageID), 0) AS TotalPackages,
                    COALESCE(COUNT(DISTINCT CASE WHEN h.ActualDate IS NOT NULL THEN h.TestPackageID END), 0) AS TestedPackages,
                    COALESCE(COUNT(DISTINCT CASE WHEN """ + flush_condition + """ THEN h.TestPackageID END), 0) AS FlushedPackages,
                    COALESCE(COUNT(DISTINCT CASE WHEN """ + reinst_condition + """ THEN h.TestPackageID END), 0) AS ReinstatedPackages,
                    -- 预试车任务统计
                    COALESCE(SUM(CASE WHEN pt.TaskType = 'Manhole' THEN pt.QuantityTotal ELSE 0 END), 0) AS ManholeTotal,
                    COALESCE(SUM(CASE WHEN pt.TaskType = 'Manhole' THEN pt.QuantityDone ELSE 0 END), 0) AS ManholeDone,
                    COALESCE(SUM(CASE WHEN pt.TaskType = 'MotorSolo' THEN pt.QuantityTotal ELSE 0 END), 0) AS MotorSoloTotal,
                    COALESCE(SUM(CASE WHEN pt.TaskType = 'MotorSolo' THEN pt.QuantityDone ELSE 0 END), 0) AS MotorSoloDone,
                    COALESCE(SUM(CASE WHEN pt.TaskType = 'SkidInstall' THEN pt.QuantityTotal ELSE 0 END), 0) AS SkidInstallTotal,
                    COALESCE(SUM(CASE WHEN pt.TaskType = 'SkidInstall' THEN pt.QuantityDone ELSE 0 END), 0) AS SkidInstallDone,
                    COALESCE(SUM(CASE WHEN pt.TaskType = 'LoopTest' THEN pt.QuantityTotal ELSE 0 END), 0) AS LoopTestTotal,
                    COALESCE(SUM(CASE WHEN pt.TaskType = 'LoopTest' THEN pt.QuantityDone ELSE 0 END), 0) AS LoopTestDone,
                    COALESCE(SUM(CASE WHEN pt.TaskType = 'Alignment' THEN pt.QuantityTotal ELSE 0 END), 0) AS AlignmentTotal,
                    COALESCE(SUM(CASE WHEN pt.TaskType = 'Alignment' THEN pt.QuantityDone ELSE 0 END), 0) AS AlignmentDone,
                    COALESCE(SUM(CASE WHEN pt.TaskType = 'MRT' THEN pt.QuantityTotal ELSE 0 END), 0) AS MRTTotal,
                    COALESCE(SUM(CASE WHEN pt.TaskType = 'MRT' THEN pt.QuantityDone ELSE 0 END), 0) AS MRTDone,
                    COALESCE(SUM(CASE WHEN pt.TaskType = 'FunctionTest' THEN pt.QuantityTotal ELSE 0 END), 0) AS FunctionTestTotal,
                    COALESCE(SUM(CASE WHEN pt.TaskType = 'FunctionTest' THEN pt.QuantityDone ELSE 0 END), 0) AS FunctionTestDone,
                    -- 尾项统计（试压包尾项 + 预试车任务尾项）
                    COALESCE((SELECT COUNT(*) FROM PunchList pl2 WHERE pl2.TestPackageID IN 
                        (SELECT h2.TestPackageID FROM HydroTestPackageList h2 WHERE h2.SystemCode = s.SystemCode AND h2.IsDeleted = FALSE)
                    ), 0) + 
                    COALESCE((SELECT COUNT(*) FROM PrecomTaskPunch ptp2 
                     INNER JOIN PrecomTask pt2 ON ptp2.TaskID = pt2.TaskID 
                     WHERE pt2.SystemCode = s.SystemCode AND (ptp2.Deleted IS NULL OR ptp2.Deleted = 'N')
                    ), 0) AS PunchTotal,
                    COALESCE((SELECT COUNT(*) FROM PunchList pl2 WHERE pl2.TestPackageID IN 
                        (SELECT h2.TestPackageID FROM HydroTestPackageList h2 WHERE h2.SystemCode = s.SystemCode AND h2.IsDeleted = FALSE)
                     AND pl2.Rectified = 'Y'
                    ), 0) + 
                    COALESCE((SELECT COUNT(*) FROM PrecomTaskPunch ptp2 
                     INNER JOIN PrecomTask pt2 ON ptp2.TaskID = pt2.TaskID 
                     WHERE pt2.SystemCode = s.SystemCode AND ptp2.Rectified = 'Y' AND (ptp2.Deleted IS NULL OR ptp2.Deleted = 'N')
                    ), 0) AS PunchRectified,
                    COALESCE((SELECT COUNT(*) FROM PunchList pl2 WHERE pl2.TestPackageID IN 
                        (SELECT h2.TestPackageID FROM HydroTestPackageList h2 WHERE h2.SystemCode = s.SystemCode AND h2.IsDeleted = FALSE)
                     AND pl2.Verified = 'Y'
                    ), 0) + 
                    COALESCE((SELECT COUNT(*) FROM PrecomTaskPunch ptp2 
                     INNER JOIN PrecomTask pt2 ON ptp2.TaskID = pt2.TaskID 
                     WHERE pt2.SystemCode = s.SystemCode AND ptp2.Verified = 'Y' AND (ptp2.Deleted IS NULL OR ptp2.Deleted = 'N')
                    ), 0) AS PunchVerified
                FROM SystemList s
                LEFT JOIN HydroTestPackageList h ON h.SystemCode = s.SystemCode AND h.IsDeleted = FALSE
                LEFT JOIN TestPackageAttachments tpa_flush ON tpa_flush.TestPackageID = h.TestPackageID 
                    AND tpa_flush.ModuleName = 'Flushing_Certificate'
                LEFT JOIN TestPackageAttachments tpa_reinst ON tpa_reinst.TestPackageID = h.TestPackageID 
                    AND tpa_reinst.ModuleName = 'Reinstatement_Check_List'
                LEFT JOIN PrecomTask pt ON pt.SystemCode = s.SystemCode
                WHERE """ + " AND ".join(where_clauses) + """
                GROUP BY s.SystemCode, s.SystemDescriptionENG, s.ProcessOrNonProcess
                ORDER BY s.SystemCode
            """
            cur.execute(sql, tuple(params))
        else:  # subsystem
            where_clauses = ["sub.IsDeleted = FALSE"]
            params = []
            
            if system_code:
                where_clauses.append("sub.SystemCode = %s")
                params.append(system_code)
            if subsystem_code:
                where_clauses.append("sub.SubSystemCode = %s")
                params.append(subsystem_code)
            if allowed_system_codes is not None:
                if len(allowed_system_codes) == 0:
                    return []
                placeholders = ','.join(['%s'] * len(allowed_system_codes))
                where_clauses.append(f"sub.SystemCode IN ({placeholders})")
                params.extend(allowed_system_codes)
            
            sql = """
                SELECT 
                    sub.SubSystemCode,
                    sub.SystemCode,
                    sub.SubSystemDescriptionENG,
                    sub.ProcessOrNonProcess,
                    -- 试压包相关
                    COUNT(DISTINCT h.TestPackageID) AS TotalPackages,
                    COUNT(DISTINCT CASE WHEN h.ActualDate IS NOT NULL THEN h.TestPackageID END) AS TestedPackages,
                    COUNT(DISTINCT CASE WHEN """ + flush_condition + """ THEN h.TestPackageID END) AS FlushedPackages,
                    COUNT(DISTINCT CASE WHEN """ + reinst_condition + """ THEN h.TestPackageID END) AS ReinstatedPackages,
                    -- 预试车任务统计
                    COALESCE(SUM(CASE WHEN pt.TaskType = 'Manhole' THEN pt.QuantityTotal ELSE 0 END), 0) AS ManholeTotal,
                    COALESCE(SUM(CASE WHEN pt.TaskType = 'Manhole' THEN pt.QuantityDone ELSE 0 END), 0) AS ManholeDone,
                    COALESCE(SUM(CASE WHEN pt.TaskType = 'MotorSolo' THEN pt.QuantityTotal ELSE 0 END), 0) AS MotorSoloTotal,
                    COALESCE(SUM(CASE WHEN pt.TaskType = 'MotorSolo' THEN pt.QuantityDone ELSE 0 END), 0) AS MotorSoloDone,
                    COALESCE(SUM(CASE WHEN pt.TaskType = 'SkidInstall' THEN pt.QuantityTotal ELSE 0 END), 0) AS SkidInstallTotal,
                    COALESCE(SUM(CASE WHEN pt.TaskType = 'SkidInstall' THEN pt.QuantityDone ELSE 0 END), 0) AS SkidInstallDone,
                    COALESCE(SUM(CASE WHEN pt.TaskType = 'LoopTest' THEN pt.QuantityTotal ELSE 0 END), 0) AS LoopTestTotal,
                    COALESCE(SUM(CASE WHEN pt.TaskType = 'LoopTest' THEN pt.QuantityDone ELSE 0 END), 0) AS LoopTestDone,
                    COALESCE(SUM(CASE WHEN pt.TaskType = 'Alignment' THEN pt.QuantityTotal ELSE 0 END), 0) AS AlignmentTotal,
                    COALESCE(SUM(CASE WHEN pt.TaskType = 'Alignment' THEN pt.QuantityDone ELSE 0 END), 0) AS AlignmentDone,
                    COALESCE(SUM(CASE WHEN pt.TaskType = 'MRT' THEN pt.QuantityTotal ELSE 0 END), 0) AS MRTTotal,
                    COALESCE(SUM(CASE WHEN pt.TaskType = 'MRT' THEN pt.QuantityDone ELSE 0 END), 0) AS MRTDone,
                    COALESCE(SUM(CASE WHEN pt.TaskType = 'FunctionTest' THEN pt.QuantityTotal ELSE 0 END), 0) AS FunctionTestTotal,
                    COALESCE(SUM(CASE WHEN pt.TaskType = 'FunctionTest' THEN pt.QuantityDone ELSE 0 END), 0) AS FunctionTestDone,
                    -- 尾项统计（试压包尾项 + 预试车任务尾项）
                    (SELECT COALESCE(COUNT(*), 0) FROM PunchList pl2 WHERE pl2.TestPackageID IN 
                        (SELECT h2.TestPackageID FROM HydroTestPackageList h2 WHERE h2.SubSystemCode = sub.SubSystemCode AND h2.IsDeleted = FALSE)
                    ) + 
                    (SELECT COALESCE(COUNT(*), 0) FROM PrecomTaskPunch ptp2 
                     INNER JOIN PrecomTask pt2 ON ptp2.TaskID = pt2.TaskID 
                     WHERE pt2.SubSystemCode = sub.SubSystemCode AND (ptp2.Deleted IS NULL OR ptp2.Deleted = 'N')
                    ) AS PunchTotal,
                    (SELECT COALESCE(COUNT(*), 0) FROM PunchList pl2 WHERE pl2.TestPackageID IN 
                        (SELECT h2.TestPackageID FROM HydroTestPackageList h2 WHERE h2.SubSystemCode = sub.SubSystemCode AND h2.IsDeleted = FALSE)
                     AND pl2.Rectified = 'Y'
                    ) + 
                    (SELECT COALESCE(COUNT(*), 0) FROM PrecomTaskPunch ptp2 
                     INNER JOIN PrecomTask pt2 ON ptp2.TaskID = pt2.TaskID 
                     WHERE pt2.SubSystemCode = sub.SubSystemCode AND ptp2.Rectified = 'Y' AND (ptp2.Deleted IS NULL OR ptp2.Deleted = 'N')
                    ) AS PunchRectified,
                    (SELECT COALESCE(COUNT(*), 0) FROM PunchList pl2 WHERE pl2.TestPackageID IN 
                        (SELECT h2.TestPackageID FROM HydroTestPackageList h2 WHERE h2.SubSystemCode = sub.SubSystemCode AND h2.IsDeleted = FALSE)
                     AND pl2.Verified = 'Y'
                    ) + 
                    (SELECT COALESCE(COUNT(*), 0) FROM PrecomTaskPunch ptp2 
                     INNER JOIN PrecomTask pt2 ON ptp2.TaskID = pt2.TaskID 
                     WHERE pt2.SubSystemCode = sub.SubSystemCode AND ptp2.Verified = 'Y' AND (ptp2.Deleted IS NULL OR ptp2.Deleted = 'N')
                    ) AS PunchVerified
                FROM SubsystemList sub
                LEFT JOIN HydroTestPackageList h ON h.SubSystemCode = sub.SubSystemCode AND h.IsDeleted = FALSE
                LEFT JOIN TestPackageAttachments tpa_flush ON tpa_flush.TestPackageID = h.TestPackageID 
                    AND tpa_flush.ModuleName = 'Flushing_Certificate'
                LEFT JOIN TestPackageAttachments tpa_reinst ON tpa_reinst.TestPackageID = h.TestPackageID 
                    AND tpa_reinst.ModuleName = 'Reinstatement_Check_List'
                LEFT JOIN PrecomTask pt ON pt.SubSystemCode = sub.SubSystemCode
                WHERE """ + " AND ".join(where_clauses) + """
                GROUP BY sub.SubSystemCode, sub.SystemCode, sub.SubSystemDescriptionENG, sub.ProcessOrNonProcess
                ORDER BY sub.SystemCode, sub.SubSystemCode
            """
            cur.execute(sql, tuple(params))
        
        results = cur.fetchall()
        # 计算进度百分比
        for row in results:
            # 试压包进度
            total_packages = row.get('TotalPackages', 0) or 0
            if total_packages > 0:
                row['TestProgress'] = round((row.get('TestedPackages', 0) or 0) / total_packages * 100, 1)
                row['FlushProgress'] = round((row.get('FlushedPackages', 0) or 0) / total_packages * 100, 1)
                row['ReinstProgress'] = round((row.get('ReinstatedPackages', 0) or 0) / total_packages * 100, 1)
            else:
                row['TestProgress'] = 0
                row['FlushProgress'] = 0
                row['ReinstProgress'] = 0
            
            # 确保试压包数量字段有默认值
            row['TotalPackages'] = total_packages
            row['TestedPackages'] = row.get('TestedPackages', 0) or 0
            row['FlushedPackages'] = row.get('FlushedPackages', 0) or 0
            row['ReinstatedPackages'] = row.get('ReinstatedPackages', 0) or 0
            
            # 预试车任务进度
            task_types = ['Manhole', 'MotorSolo', 'SkidInstall', 'LoopTest', 'Alignment', 'MRT', 'FunctionTest']
            for task_type in task_types:
                total = row.get(f'{task_type}Total', 0) or 0
                done = row.get(f'{task_type}Done', 0) or 0
                if total > 0:
                    row[f'{task_type}Progress'] = round((done / total) * 100, 1)
                else:
                    row[f'{task_type}Progress'] = 0
                # 确保字段有默认值
                row[f'{task_type}Total'] = total
                row[f'{task_type}Done'] = done
            
            # 尾项统计默认值
            row['PunchTotal'] = row.get('PunchTotal', 0) or 0
            row['PunchRectified'] = row.get('PunchRectified', 0) or 0
            row['PunchVerified'] = row.get('PunchVerified', 0) or 0
        
        return results
    finally:
        conn.close()


def get_planned_vs_actual_data(module_type='test', period='month'):
    """获取计划vs实际完成情况数据（按年/季度/月）"""
    conn = create_connection()
    if not conn:
        return {'labels': [], 'planned': [], 'actual': [], 'cumulative_planned': [], 'cumulative_actual': []}
    
    try:
        cur = conn.cursor(dictionary=True)
        
        # 根据period参数构建日期格式和分组
        if period == 'year':
            date_group = 'YEAR(h.PlannedDate)'
            date_group_actual = 'YEAR(h.ActualDate)'
        elif period == 'quarter':
            date_group = "CONCAT(YEAR(h.PlannedDate), '-Q', QUARTER(h.PlannedDate))"
            date_group_actual = "CONCAT(YEAR(h.ActualDate), '-Q', QUARTER(h.ActualDate))"
        else:  # month
            date_group = "DATE_FORMAT(h.PlannedDate, '%Y-%m')"
            date_group_actual = "DATE_FORMAT(h.ActualDate, '%Y-%m')"
        
        if module_type == 'test':
            # 试压包：基于ActualDate
            planned_sql = f"""
                SELECT 
                    {date_group} AS period,
                    COUNT(DISTINCT h.TestPackageID) AS planned_count
                FROM HydroTestPackageList h
                INNER JOIN WeldingList wl ON wl.TestPackageID = h.TestPackageID
                WHERE h.PlannedDate IS NOT NULL
                  AND h.IsDeleted = FALSE
                  AND wl.IsDeleted = FALSE
                GROUP BY {date_group}
                ORDER BY period
            """
            actual_sql = f"""
                SELECT 
                    {date_group_actual} AS period,
                    COUNT(DISTINCT h.TestPackageID) AS actual_count
                FROM HydroTestPackageList h
                INNER JOIN WeldingList wl ON wl.TestPackageID = h.TestPackageID
                WHERE h.ActualDate IS NOT NULL
                  AND h.IsDeleted = FALSE
                  AND wl.IsDeleted = FALSE
                GROUP BY {date_group_actual}
                ORDER BY period
            """
        elif module_type == 'flushing':
            # 吹扫：基于FlushingPlannedDate和FlushingActualDate或附件上传时间
            if period == 'year':
                date_group_flush_planned = 'YEAR(h.FlushingPlannedDate)'
                date_group_flush_actual = 'YEAR(h.FlushingActualDate)'
                date_group_upload = 'YEAR(tpa.UploadedAt)'
            elif period == 'quarter':
                date_group_flush_planned = "CONCAT(YEAR(h.FlushingPlannedDate), '-Q', QUARTER(h.FlushingPlannedDate))"
                date_group_flush_actual = "CONCAT(YEAR(h.FlushingActualDate), '-Q', QUARTER(h.FlushingActualDate))"
                date_group_upload = "CONCAT(YEAR(tpa.UploadedAt), '-Q', QUARTER(tpa.UploadedAt))"
            else:  # month
                date_group_flush_planned = "DATE_FORMAT(h.FlushingPlannedDate, '%Y-%m')"
                date_group_flush_actual = "DATE_FORMAT(h.FlushingActualDate, '%Y-%m')"
                date_group_upload = "DATE_FORMAT(tpa.UploadedAt, '%Y-%m')"
            
            planned_sql = f"""
                SELECT 
                    {date_group_flush_planned} AS period,
                    COUNT(DISTINCT h.TestPackageID) AS planned_count
                FROM HydroTestPackageList h
                INNER JOIN WeldingList wl ON wl.TestPackageID = h.TestPackageID
                WHERE h.FlushingPlannedDate IS NOT NULL
                  AND h.IsDeleted = FALSE
                  AND wl.IsDeleted = FALSE
                GROUP BY {date_group_flush_planned}
                ORDER BY period
            """
            actual_sql = f"""
                SELECT 
                    COALESCE({date_group_flush_actual}, {date_group_upload}) AS period,
                    COUNT(DISTINCT h.TestPackageID) AS actual_count
                FROM HydroTestPackageList h
                INNER JOIN WeldingList wl ON wl.TestPackageID = h.TestPackageID
                LEFT JOIN TestPackageAttachments tpa ON tpa.TestPackageID = h.TestPackageID
                    AND tpa.ModuleName = 'Flushing_Certificate'
                WHERE (h.FlushingActualDate IS NOT NULL OR tpa.ID IS NOT NULL)
                  AND h.IsDeleted = FALSE
                  AND wl.IsDeleted = FALSE
                GROUP BY COALESCE({date_group_flush_actual}, {date_group_upload})
                ORDER BY period
            """
        elif module_type == 'reinstatement':
            # 复位：基于ReinstatementPlannedDate和ReinstatementActualDate或附件上传时间
            if period == 'year':
                date_group_reinst_planned = 'YEAR(h.ReinstatementPlannedDate)'
                date_group_reinst_actual = 'YEAR(h.ReinstatementActualDate)'
                date_group_upload = 'YEAR(tpa.UploadedAt)'
            elif period == 'quarter':
                date_group_reinst_planned = "CONCAT(YEAR(h.ReinstatementPlannedDate), '-Q', QUARTER(h.ReinstatementPlannedDate))"
                date_group_reinst_actual = "CONCAT(YEAR(h.ReinstatementActualDate), '-Q', QUARTER(h.ReinstatementActualDate))"
                date_group_upload = "CONCAT(YEAR(tpa.UploadedAt), '-Q', QUARTER(tpa.UploadedAt))"
            else:  # month
                date_group_reinst_planned = "DATE_FORMAT(h.ReinstatementPlannedDate, '%Y-%m')"
                date_group_reinst_actual = "DATE_FORMAT(h.ReinstatementActualDate, '%Y-%m')"
                date_group_upload = "DATE_FORMAT(tpa.UploadedAt, '%Y-%m')"
            
            planned_sql = f"""
                SELECT 
                    {date_group_reinst_planned} AS period,
                    COUNT(DISTINCT h.TestPackageID) AS planned_count
                FROM HydroTestPackageList h
                INNER JOIN WeldingList wl ON wl.TestPackageID = h.TestPackageID
                WHERE h.ReinstatementPlannedDate IS NOT NULL
                  AND h.IsDeleted = FALSE
                  AND wl.IsDeleted = FALSE
                GROUP BY {date_group_reinst_planned}
                ORDER BY period
            """
            actual_sql = f"""
                SELECT 
                    COALESCE({date_group_reinst_actual}, {date_group_upload}) AS period,
                    COUNT(DISTINCT h.TestPackageID) AS actual_count
                FROM HydroTestPackageList h
                INNER JOIN WeldingList wl ON wl.TestPackageID = h.TestPackageID
                LEFT JOIN TestPackageAttachments tpa ON tpa.TestPackageID = h.TestPackageID
                    AND tpa.ModuleName = 'Reinstatement_Check_List'
                WHERE (h.ReinstatementActualDate IS NOT NULL OR tpa.ID IS NOT NULL)
                  AND h.IsDeleted = FALSE
                  AND wl.IsDeleted = FALSE
                GROUP BY COALESCE({date_group_reinst_actual}, {date_group_upload})
                ORDER BY period
            """
        else:  # overview
            # 总览：使用试压包数据
            planned_sql = f"""
                SELECT 
                    {date_group} AS period,
                    COUNT(DISTINCT h.TestPackageID) AS planned_count
                FROM HydroTestPackageList h
                INNER JOIN WeldingList wl ON wl.TestPackageID = h.TestPackageID
                WHERE h.PlannedDate IS NOT NULL
                  AND h.IsDeleted = FALSE
                  AND wl.IsDeleted = FALSE
                GROUP BY {date_group}
                ORDER BY period
            """
            actual_sql = f"""
                SELECT 
                    {date_group_actual} AS period,
                    COUNT(DISTINCT h.TestPackageID) AS actual_count
                FROM HydroTestPackageList h
                INNER JOIN WeldingList wl ON wl.TestPackageID = h.TestPackageID
                WHERE h.ActualDate IS NOT NULL
                  AND h.IsDeleted = FALSE
                  AND wl.IsDeleted = FALSE
                GROUP BY {date_group_actual}
                ORDER BY period
            """
        
        cur.execute(planned_sql)
        planned_data = {row['period']: row['planned_count'] for row in cur.fetchall()}
        
        cur.execute(actual_sql)
        actual_data = {row['period']: row['actual_count'] for row in cur.fetchall()}
        
        # 合并所有期间
        all_periods = sorted(set(list(planned_data.keys()) + list(actual_data.keys())))
        
        labels = []
        planned = []
        actual = []
        cumulative_planned = 0
        cumulative_actual = 0
        cumulative_planned_list = []
        cumulative_actual_list = []
        
        for period_val in all_periods:
            labels.append(str(period_val))
            planned.append(planned_data.get(period_val, 0))
            actual.append(actual_data.get(period_val, 0))
            cumulative_planned += planned_data.get(period_val, 0)
            cumulative_actual += actual_data.get(period_val, 0)
            cumulative_planned_list.append(cumulative_planned)
            cumulative_actual_list.append(cumulative_actual)
        
        return {
            'labels': labels,
            'planned': planned,
            'actual': actual,
            'cumulative_planned': cumulative_planned_list,
            'cumulative_actual': cumulative_actual_list
        }
    finally:
        conn.close()


@dashboard_bp.route('/dashboard')
@login_required
def dashboard():
    """仪表板主页面"""
    # 确保数据库字段存在
    from database import ensure_hydro_columns
    ensure_hydro_columns()
    
    module_type = request.args.get('module', 'overview')
    level = request.args.get('level', 'system')
    system_code = request.args.get('system_code', '').strip() or None
    subsystem_code = request.args.get('subsystem_code', '').strip() or None
    page = int(request.args.get('page', 1))
    per_page = 20
    
    # Faclist筛选器参数
    fac_filters = {
        'subproject_code': (request.args.get('subproject_code') or '').strip() or None,
        'train': (request.args.get('train') or '').strip() or None,
        'unit': (request.args.get('unit') or '').strip() or None,
        'simpleblk': (request.args.get('simpleblk') or '').strip() or None,
        'mainblock': (request.args.get('mainblock') or '').strip() or None,
        'block': (request.args.get('block') or '').strip() or None,
        'bccquarter': (request.args.get('bccquarter') or '').strip() or None
    }
    
    if module_type not in MODULE_TYPES:
        module_type = 'overview'
    
    # 导入模型
    from models.system import SystemModel
    from models.subsystem import SubsystemModel
    
    # 初始化Faclist筛选相关变量
    matched_blocks = None
    allowed_system_codes = None
    has_faclist_filters = any(fac_filters.values())
    
    # 处理Faclist筛选：获取匹配的Block和系统代码
    if has_faclist_filters:
        conn = create_connection()
        if conn:
            try:
                cur = conn.cursor(dictionary=True)
                clauses = []
                params = []
                if fac_filters['subproject_code']:
                    clauses.append("SubProjectCode = %s")
                    params.append(fac_filters['subproject_code'])
                if fac_filters['train']:
                    clauses.append("Train = %s")
                    params.append(fac_filters['train'])
                if fac_filters['unit']:
                    clauses.append("Unit = %s")
                    params.append(fac_filters['unit'])
                if fac_filters['simpleblk']:
                    clauses.append("SimpleBLK = %s")
                    params.append(fac_filters['simpleblk'])
                if fac_filters['mainblock']:
                    clauses.append("MainBlock = %s")
                    params.append(fac_filters['mainblock'])
                if fac_filters['block']:
                    clauses.append("Block = %s")
                    params.append(fac_filters['block'])
                if fac_filters['bccquarter']:
                    clauses.append("BCCQuarter = %s")
                    params.append(fac_filters['bccquarter'])
                
                if clauses:
                    where_clause = " AND ".join(clauses)
                    cur.execute(
                        f"""
                        SELECT DISTINCT Block
                        FROM Faclist
                        WHERE {where_clause}
                          AND Block IS NOT NULL
                          AND Block <> ''
                        """,
                        tuple(params)
                    )
                    matched_blocks = [row['Block'] for row in cur.fetchall() if row.get('Block')]
                    if matched_blocks:
                        allowed_system_codes = resolve_system_codes_by_blocks(cur, matched_blocks)
                    else:
                        allowed_system_codes = []
            finally:
                conn.close()
    
    # 获取系统和子系统列表用于筛选（应用Faclist筛选）
    if allowed_system_codes is not None:
        all_systems = SystemModel.get_all_systems()
        # SystemModel 返回字典列表，使用字典方式访问
        systems = [s for s in all_systems if s.get('SystemCode') in allowed_system_codes] if len(allowed_system_codes) > 0 else []
    else:
        systems = SystemModel.get_all_systems()
    
    if allowed_system_codes is not None:
        all_subsystems = SubsystemModel.get_subsystems_by_system(system_code) if system_code else SubsystemModel.get_all_subsystems()
        # SubsystemModel 也返回字典列表，使用字典方式访问
        subsystems = [s for s in all_subsystems if s.get('SystemCode') in allowed_system_codes] if len(allowed_system_codes) > 0 else []
    else:
        subsystems = SubsystemModel.get_subsystems_by_system(system_code) if system_code else SubsystemModel.get_all_subsystems()
    
    # 获取Faclist筛选选项
    faclist_options = get_faclist_filter_options(
        filter_subproject=fac_filters['subproject_code'],
        filter_train=fac_filters['train'],
        filter_unit=fac_filters['unit'],
        filter_simpleblk=fac_filters['simpleblk'],
        filter_mainblock=fac_filters['mainblock'],
        filter_block=fac_filters['block'],
        filter_bccquarter=fac_filters['bccquarter']
    )
    
    # 根据模块类型获取统计数据（带筛选）
    if module_type == 'overview':
        all_stats = get_overview_stats(level, system_code, subsystem_code, matched_blocks, allowed_system_codes)
        # 计算汇总统计
        total_count = len(all_stats)
        completed_count = sum(1 for item in all_stats if (
            (item.get('TestProgress', 0) or 0) >= 100 and 
            (item.get('FlushProgress', 0) or 0) >= 100 and 
            (item.get('ReinstProgress', 0) or 0) >= 100 and
            all((item.get(f'{task}Progress', 0) or 0) >= 100 for task in ['Manhole', 'MotorSolo', 'SkidInstall', 'LoopTest', 'Alignment', 'MRT', 'FunctionTest'])
        ))
        in_progress_count = sum(1 for item in all_stats if 
            any([
                (item.get('TestProgress', 0) or 0) > 0 and (item.get('TestProgress', 0) or 0) < 100,
                (item.get('FlushProgress', 0) or 0) > 0 and (item.get('FlushProgress', 0) or 0) < 100,
                (item.get('ReinstProgress', 0) or 0) > 0 and (item.get('ReinstProgress', 0) or 0) < 100,
                (item.get('ManholeProgress', 0) or 0) > 0 and (item.get('ManholeProgress', 0) or 0) < 100,
                (item.get('MotorSoloProgress', 0) or 0) > 0 and (item.get('MotorSoloProgress', 0) or 0) < 100,
                (item.get('SkidInstallProgress', 0) or 0) > 0 and (item.get('SkidInstallProgress', 0) or 0) < 100,
                (item.get('LoopTestProgress', 0) or 0) > 0 and (item.get('LoopTestProgress', 0) or 0) < 100,
                (item.get('AlignmentProgress', 0) or 0) > 0 and (item.get('AlignmentProgress', 0) or 0) < 100,
                (item.get('MRTProgress', 0) or 0) > 0 and (item.get('MRTProgress', 0) or 0) < 100,
                (item.get('FunctionTestProgress', 0) or 0) > 0 and (item.get('FunctionTestProgress', 0) or 0) < 100
            ]))
        # 分页
        total_pages = max(1, ceil(total_count / per_page))
        page = max(1, min(page, total_pages))
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        stats = all_stats[start_idx:end_idx]
        total_packages = sum(item.get('TotalPackages', 0) or 0 for item in all_stats)
        completed_packages = sum(item.get('TestedPackages', 0) or 0 for item in all_stats)
        overall_progress = (completed_packages / total_packages * 100) if total_packages > 0 else 0
    elif module_type == 'test':
        all_stats = get_test_package_stats(level, system_code, subsystem_code, matched_blocks, allowed_system_codes)
        total_count = len(all_stats)
        completed_count = sum(1 for item in all_stats if (item.get('Progress', 0) or 0) >= 100)
        in_progress_count = sum(1 for item in all_stats if 0 < (item.get('Progress', 0) or 0) < 100)
        total_pages = max(1, ceil(total_count / per_page))
        page = max(1, min(page, total_pages))
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        stats = all_stats[start_idx:end_idx]
        total_packages = sum(item.get('TotalPackages', 0) or 0 for item in all_stats)
        completed_packages = sum(item.get('TestedPackages', 0) or 0 for item in all_stats)
        overall_progress = (completed_packages / total_packages * 100) if total_packages > 0 else 0
        # 试压包模块：卡片展示焊接数据（不需要card变量，直接使用welding变量）
        card_total_packages = 0
        card_completed_packages = 0
        card_progress = 0
        # 计算焊接量统计（考虑Faclist筛选条件和系统筛选）
        if matched_blocks:
            # 有Faclist筛选：从BlockSystemSummary/BlockSubsystemSummary计算（所有符合筛选条件的数据）
            conn = create_connection()
            if conn:
                try:
                    cur = conn.cursor(dictionary=True)
                    block_placeholders = ','.join(['%s'] * len(matched_blocks))
                    if level == 'system':
                        # 使用allowed_system_codes获取所有符合筛选条件的系统代码
                        if allowed_system_codes and len(allowed_system_codes) > 0:
                            code_placeholders = ','.join(['%s'] * len(allowed_system_codes))
                            cur.execute(f"""
                                SELECT 
                                    COALESCE(SUM(TotalDIN), 0) AS total_din,
                                    COALESCE(SUM(CompletedDIN), 0) AS completed_din
                                FROM BlockSystemSummary
                                WHERE SystemCode IN ({code_placeholders})
                                  AND Block IN ({block_placeholders})
                            """, tuple(allowed_system_codes) + tuple(matched_blocks))
                        else:
                            cur.execute("SELECT 0 AS total_din, 0 AS completed_din")
                    else:
                        # 子系统级别：需要先获取符合筛选条件的子系统代码
                        if allowed_system_codes and len(allowed_system_codes) > 0:
                            # 获取所有符合筛选条件的子系统代码
                            code_placeholders = ','.join(['%s'] * len(allowed_system_codes))
                            cur.execute(f"""
                                SELECT DISTINCT SubSystemCode
                                FROM SubsystemList
                                WHERE SystemCode IN ({code_placeholders})
                                  AND IsDeleted = FALSE
                            """, tuple(allowed_system_codes))
                            subsystem_codes = [row['SubSystemCode'] for row in cur.fetchall() if row.get('SubSystemCode')]
                            if subsystem_codes:
                                sub_code_placeholders = ','.join(['%s'] * len(subsystem_codes))
                                cur.execute(f"""
                                    SELECT 
                                        COALESCE(SUM(TotalDIN), 0) AS total_din,
                                        COALESCE(SUM(CompletedDIN), 0) AS completed_din
                                    FROM BlockSubsystemSummary
                                    WHERE SubSystemCode IN ({sub_code_placeholders})
                                      AND Block IN ({block_placeholders})
                                """, tuple(subsystem_codes) + tuple(matched_blocks))
                            else:
                                cur.execute("SELECT 0 AS total_din, 0 AS completed_din")
                        else:
                            cur.execute("SELECT 0 AS total_din, 0 AS completed_din")
                    row = cur.fetchone() or {}
                    total_welding_din = float(row.get('total_din', 0) or 0)
                    completed_welding_din = float(row.get('completed_din', 0) or 0)
                finally:
                    conn.close()
            else:
                total_welding_din = 0
                completed_welding_din = 0
        elif system_code:
            # 无Faclist筛选但有系统筛选：直接从SystemWeldingSummary/SubsystemWeldingSummary查询
            conn = create_connection()
            if conn:
                try:
                    cur = conn.cursor(dictionary=True)
                    if level == 'system':
                        # 系统级别：直接从SystemWeldingSummary查询
                        cur.execute("""
                            SELECT 
                                COALESCE(TotalDIN, 0) AS total_din,
                                COALESCE(CompletedDIN, 0) AS completed_din
                            FROM SystemWeldingSummary
                            WHERE SystemCode = %s
                        """, (system_code,))
                    else:
                        # 子系统级别：如果有subsystem_code，查询该子系统；否则查询该系统下所有子系统
                        if subsystem_code:
                            cur.execute("""
                                SELECT 
                                    COALESCE(TotalDIN, 0) AS total_din,
                                    COALESCE(CompletedDIN, 0) AS completed_din
                                FROM SubsystemWeldingSummary
                                WHERE SubSystemCode = %s
                            """, (subsystem_code,))
                        else:
                            cur.execute("""
                                SELECT 
                                    COALESCE(SUM(TotalDIN), 0) AS total_din,
                                    COALESCE(SUM(CompletedDIN), 0) AS completed_din
                                FROM SubsystemWeldingSummary
                                WHERE SystemCode = %s
                            """, (system_code,))
                    row = cur.fetchone() or {}
                    total_welding_din = float(row.get('total_din', 0) or 0)
                    completed_welding_din = float(row.get('completed_din', 0) or 0)
                finally:
                    conn.close()
            else:
                total_welding_din = 0
                completed_welding_din = 0
        else:
            # 无任何筛选：从统计数据中汇总（所有数据）
            total_welding_din = sum(float(item.get('TotalDIN', 0) or 0) for item in all_stats)
            completed_welding_din = sum(float(item.get('CompletedDIN', 0) or 0) for item in all_stats)
        welding_progress = (completed_welding_din / total_welding_din * 100) if total_welding_din > 0 else 0
    elif module_type == 'flushing':
        all_stats = get_flushing_stats(level, system_code, subsystem_code, matched_blocks, allowed_system_codes)
        total_count = len(all_stats)
        completed_count = sum(1 for item in all_stats if (item.get('Progress', 0) or 0) >= 100)
        in_progress_count = sum(1 for item in all_stats if 0 < (item.get('Progress', 0) or 0) < 100)
        total_pages = max(1, ceil(total_count / per_page))
        page = max(1, min(page, total_pages))
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        stats = all_stats[start_idx:end_idx]
        total_packages = sum(item.get('TotalPackages', 0) or 0 for item in all_stats)
        completed_packages = sum(item.get('CompletedPackages', 0) or 0 for item in all_stats)
        overall_progress = (completed_packages / total_packages * 100) if total_packages > 0 else 0
        # 吹扫模块：卡片展示试压包数据（总试压包数 = 总试压包总数）
        # 直接使用 get_flushing_stats 返回的数据，它已经考虑了所有筛选条件
        # 但需要查询所有试压包（不受吹扫筛选影响），所以需要重新查询
        conn = create_connection()
        if conn:
            try:
                cur = conn.cursor(dictionary=True)
                # 构建 WHERE 条件，考虑 Faclist 筛选
                where_clauses = ["h.IsDeleted = FALSE"]
                params = []
                
                if level == 'system':
                    if system_code:
                        where_clauses.append("h.SystemCode = %s")
                        params.append(system_code)
                    elif allowed_system_codes and len(allowed_system_codes) > 0:
                        code_placeholders = ','.join(['%s'] * len(allowed_system_codes))
                        where_clauses.append(f"h.SystemCode IN ({code_placeholders})")
                        params.extend(allowed_system_codes)
                    
                    # 如果有 Faclist 筛选（matched_blocks），需要进一步过滤
                    if matched_blocks and len(matched_blocks) > 0:
                        block_placeholders = ','.join(['%s'] * len(matched_blocks))
                        where_clauses.append(f"""
                            EXISTS (
                                SELECT 1 FROM WeldingList wl
                                WHERE wl.TestPackageID = h.TestPackageID
                                AND wl.Block IN ({block_placeholders})
                            )
                        """)
                        params.extend(matched_blocks)
                    
                    cur.execute(f"""
                        SELECT 
                            COUNT(DISTINCT h.TestPackageID) AS total_tested,
                            COUNT(DISTINCT CASE WHEN h.ActualDate IS NOT NULL THEN h.TestPackageID END) AS completed_tested
                        FROM HydroTestPackageList h
                        WHERE {' AND '.join(where_clauses)}
                    """, tuple(params))
                else:  # subsystem
                    if subsystem_code:
                        where_clauses.append("h.SubSystemCode = %s")
                        params.append(subsystem_code)
                    elif system_code:
                        where_clauses.append("h.SystemCode = %s")
                        params.append(system_code)
                    elif allowed_system_codes and len(allowed_system_codes) > 0:
                        code_placeholders = ','.join(['%s'] * len(allowed_system_codes))
                        where_clauses.append(f"h.SystemCode IN ({code_placeholders})")
                        params.extend(allowed_system_codes)
                    
                    # 如果有 Faclist 筛选（matched_blocks），需要进一步过滤
                    if matched_blocks and len(matched_blocks) > 0:
                        block_placeholders = ','.join(['%s'] * len(matched_blocks))
                        where_clauses.append(f"""
                            EXISTS (
                                SELECT 1 FROM WeldingList wl
                                WHERE wl.TestPackageID = h.TestPackageID
                                AND wl.Block IN ({block_placeholders})
                            )
                        """)
                        params.extend(matched_blocks)
                    
                    cur.execute(f"""
                        SELECT 
                            COUNT(DISTINCT h.TestPackageID) AS total_tested,
                            COUNT(DISTINCT CASE WHEN h.ActualDate IS NOT NULL THEN h.TestPackageID END) AS completed_tested
                        FROM HydroTestPackageList h
                        WHERE {' AND '.join(where_clauses)}
                    """, tuple(params))
                
                row = cur.fetchone() or {}
                card_total_packages = int(row.get('total_tested', 0) or 0)
                card_completed_packages = int(row.get('completed_tested', 0) or 0)
                card_progress = (card_completed_packages / card_total_packages * 100) if card_total_packages > 0 else 0
            finally:
                conn.close()
        else:
            card_total_packages = 0
            card_completed_packages = 0
            card_progress = 0
        # 计算焊接量统计（考虑Faclist筛选条件和系统筛选）
        if matched_blocks:
            # 有Faclist筛选：从BlockSystemSummary/BlockSubsystemSummary计算（所有符合筛选条件的数据）
            conn = create_connection()
            if conn:
                try:
                    cur = conn.cursor(dictionary=True)
                    block_placeholders = ','.join(['%s'] * len(matched_blocks))
                    if level == 'system':
                        # 使用allowed_system_codes获取所有符合筛选条件的系统代码
                        if allowed_system_codes and len(allowed_system_codes) > 0:
                            code_placeholders = ','.join(['%s'] * len(allowed_system_codes))
                            cur.execute(f"""
                                SELECT 
                                    COALESCE(SUM(TotalDIN), 0) AS total_din,
                                    COALESCE(SUM(CompletedDIN), 0) AS completed_din
                                FROM BlockSystemSummary
                                WHERE SystemCode IN ({code_placeholders})
                                  AND Block IN ({block_placeholders})
                            """, tuple(allowed_system_codes) + tuple(matched_blocks))
                        else:
                            cur.execute("SELECT 0 AS total_din, 0 AS completed_din")
                    else:
                        # 子系统级别：需要先获取符合筛选条件的子系统代码
                        if allowed_system_codes and len(allowed_system_codes) > 0:
                            code_placeholders = ','.join(['%s'] * len(allowed_system_codes))
                            cur.execute(f"""
                                SELECT DISTINCT SubSystemCode
                                FROM SubsystemList
                                WHERE SystemCode IN ({code_placeholders})
                                  AND IsDeleted = FALSE
                            """, tuple(allowed_system_codes))
                            subsystem_codes = [row['SubSystemCode'] for row in cur.fetchall() if row.get('SubSystemCode')]
                            if subsystem_codes:
                                sub_code_placeholders = ','.join(['%s'] * len(subsystem_codes))
                                cur.execute(f"""
                                    SELECT 
                                        COALESCE(SUM(TotalDIN), 0) AS total_din,
                                        COALESCE(SUM(CompletedDIN), 0) AS completed_din
                                    FROM BlockSubsystemSummary
                                    WHERE SubSystemCode IN ({sub_code_placeholders})
                                      AND Block IN ({block_placeholders})
                                """, tuple(subsystem_codes) + tuple(matched_blocks))
                            else:
                                cur.execute("SELECT 0 AS total_din, 0 AS completed_din")
                        else:
                            cur.execute("SELECT 0 AS total_din, 0 AS completed_din")
                    row = cur.fetchone() or {}
                    total_welding_din = float(row.get('total_din', 0) or 0)
                    completed_welding_din = float(row.get('completed_din', 0) or 0)
                finally:
                    conn.close()
            else:
                total_welding_din = 0
                completed_welding_din = 0
        elif system_code:
            # 无Faclist筛选但有系统筛选：直接从SystemWeldingSummary/SubsystemWeldingSummary查询
            conn = create_connection()
            if conn:
                try:
                    cur = conn.cursor(dictionary=True)
                    if level == 'system':
                        cur.execute("""
                            SELECT 
                                COALESCE(TotalDIN, 0) AS total_din,
                                COALESCE(CompletedDIN, 0) AS completed_din
                            FROM SystemWeldingSummary
                            WHERE SystemCode = %s
                        """, (system_code,))
                    else:
                        if subsystem_code:
                            cur.execute("""
                                SELECT 
                                    COALESCE(TotalDIN, 0) AS total_din,
                                    COALESCE(CompletedDIN, 0) AS completed_din
                                FROM SubsystemWeldingSummary
                                WHERE SubSystemCode = %s
                            """, (subsystem_code,))
                        else:
                            cur.execute("""
                                SELECT 
                                    COALESCE(SUM(TotalDIN), 0) AS total_din,
                                    COALESCE(SUM(CompletedDIN), 0) AS completed_din
                                FROM SubsystemWeldingSummary
                                WHERE SystemCode = %s
                            """, (system_code,))
                    row = cur.fetchone() or {}
                    total_welding_din = float(row.get('total_din', 0) or 0)
                    completed_welding_din = float(row.get('completed_din', 0) or 0)
                finally:
                    conn.close()
            else:
                total_welding_din = 0
                completed_welding_din = 0
        else:
            # 无任何筛选：从统计数据中汇总（所有数据）
            total_welding_din = sum(float(item.get('TotalDIN', 0) or 0) for item in all_stats)
            completed_welding_din = sum(float(item.get('CompletedDIN', 0) or 0) for item in all_stats)
        welding_progress = (completed_welding_din / total_welding_din * 100) if total_welding_din > 0 else 0
    elif module_type == 'reinstatement':
        all_stats = get_reinstatement_stats(level, system_code, subsystem_code, matched_blocks, allowed_system_codes)
        total_count = len(all_stats)
        completed_count = sum(1 for item in all_stats if (item.get('Progress', 0) or 0) >= 100)
        in_progress_count = sum(1 for item in all_stats if 0 < (item.get('Progress', 0) or 0) < 100)
        total_pages = max(1, ceil(total_count / per_page))
        page = max(1, min(page, total_pages))
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        stats = all_stats[start_idx:end_idx]
        total_packages = sum(item.get('TotalPackages', 0) or 0 for item in all_stats)
        completed_packages = sum(item.get('CompletedPackages', 0) or 0 for item in all_stats)
        overall_progress = (completed_packages / total_packages * 100) if total_packages > 0 else 0
        # 复位模块：卡片展示吹扫数据（总吹扫数 = 总试压包总数，因为吹扫是基于试压包的）
        # 需要查询所有试压包（作为吹扫的基数）和已完成吹扫的试压包数量
        conn = create_connection()
        if conn:
            try:
                cur = conn.cursor(dictionary=True)
                # 检查字段是否存在
                cur.execute("SHOW COLUMNS FROM HydroTestPackageList LIKE 'FlushingActualDate'")
                has_flushing_date = cur.fetchone() is not None
                flush_condition = "(h.FlushingActualDate IS NOT NULL OR tpa.ID IS NOT NULL)" if has_flushing_date else "tpa.ID IS NOT NULL"
                
                # 构建 WHERE 条件，考虑 Faclist 筛选
                where_clauses = ["h.IsDeleted = FALSE"]
                params = []
                
                if level == 'system':
                    if system_code:
                        where_clauses.append("h.SystemCode = %s")
                        params.append(system_code)
                    elif allowed_system_codes and len(allowed_system_codes) > 0:
                        code_placeholders = ','.join(['%s'] * len(allowed_system_codes))
                        where_clauses.append(f"h.SystemCode IN ({code_placeholders})")
                        params.extend(allowed_system_codes)
                    
                    # 如果有 Faclist 筛选（matched_blocks），需要进一步过滤
                    if matched_blocks and len(matched_blocks) > 0:
                        block_placeholders = ','.join(['%s'] * len(matched_blocks))
                        where_clauses.append(f"""
                            EXISTS (
                                SELECT 1 FROM WeldingList wl
                                WHERE wl.TestPackageID = h.TestPackageID
                                AND wl.Block IN ({block_placeholders})
                            )
                        """)
                        params.extend(matched_blocks)
                    
                    cur.execute(f"""
                        SELECT 
                            COUNT(DISTINCT h.TestPackageID) AS total_flushed,
                            COUNT(DISTINCT CASE WHEN {flush_condition} THEN h.TestPackageID END) AS completed_flushed
                        FROM HydroTestPackageList h
                        LEFT JOIN TestPackageAttachments tpa ON tpa.TestPackageID = h.TestPackageID 
                            AND tpa.ModuleName = 'Flushing_Certificate'
                        WHERE {' AND '.join(where_clauses)}
                    """, tuple(params))
                else:  # subsystem
                    if subsystem_code:
                        where_clauses.append("h.SubSystemCode = %s")
                        params.append(subsystem_code)
                    elif system_code:
                        where_clauses.append("h.SystemCode = %s")
                        params.append(system_code)
                    elif allowed_system_codes and len(allowed_system_codes) > 0:
                        code_placeholders = ','.join(['%s'] * len(allowed_system_codes))
                        where_clauses.append(f"h.SystemCode IN ({code_placeholders})")
                        params.extend(allowed_system_codes)
                    
                    # 如果有 Faclist 筛选（matched_blocks），需要进一步过滤
                    if matched_blocks and len(matched_blocks) > 0:
                        block_placeholders = ','.join(['%s'] * len(matched_blocks))
                        where_clauses.append(f"""
                            EXISTS (
                                SELECT 1 FROM WeldingList wl
                                WHERE wl.TestPackageID = h.TestPackageID
                                AND wl.Block IN ({block_placeholders})
                            )
                        """)
                        params.extend(matched_blocks)
                    
                    cur.execute(f"""
                        SELECT 
                            COUNT(DISTINCT h.TestPackageID) AS total_flushed,
                            COUNT(DISTINCT CASE WHEN {flush_condition} THEN h.TestPackageID END) AS completed_flushed
                        FROM HydroTestPackageList h
                        LEFT JOIN TestPackageAttachments tpa ON tpa.TestPackageID = h.TestPackageID 
                            AND tpa.ModuleName = 'Flushing_Certificate'
                        WHERE {' AND '.join(where_clauses)}
                    """, tuple(params))
                
                row = cur.fetchone() or {}
                card_total_packages = int(row.get('total_flushed', 0) or 0)  # 总试压包数（作为吹扫基数）
                card_completed_packages = int(row.get('completed_flushed', 0) or 0)  # 已完成吹扫数
                card_progress = (card_completed_packages / card_total_packages * 100) if card_total_packages > 0 else 0
            finally:
                conn.close()
        else:
            card_total_packages = 0
            card_completed_packages = 0
            card_progress = 0
        # 计算焊接量统计（考虑Faclist筛选条件和系统筛选）
        if matched_blocks:
            # 有Faclist筛选：从BlockSystemSummary/BlockSubsystemSummary计算（所有符合筛选条件的数据）
            conn = create_connection()
            if conn:
                try:
                    cur = conn.cursor(dictionary=True)
                    block_placeholders = ','.join(['%s'] * len(matched_blocks))
                    if level == 'system':
                        # 使用allowed_system_codes获取所有符合筛选条件的系统代码
                        if allowed_system_codes and len(allowed_system_codes) > 0:
                            code_placeholders = ','.join(['%s'] * len(allowed_system_codes))
                            cur.execute(f"""
                                SELECT 
                                    COALESCE(SUM(TotalDIN), 0) AS total_din,
                                    COALESCE(SUM(CompletedDIN), 0) AS completed_din
                                FROM BlockSystemSummary
                                WHERE SystemCode IN ({code_placeholders})
                                  AND Block IN ({block_placeholders})
                            """, tuple(allowed_system_codes) + tuple(matched_blocks))
                        else:
                            cur.execute("SELECT 0 AS total_din, 0 AS completed_din")
                    else:
                        # 子系统级别：需要先获取符合筛选条件的子系统代码
                        if allowed_system_codes and len(allowed_system_codes) > 0:
                            code_placeholders = ','.join(['%s'] * len(allowed_system_codes))
                            cur.execute(f"""
                                SELECT DISTINCT SubSystemCode
                                FROM SubsystemList
                                WHERE SystemCode IN ({code_placeholders})
                                  AND IsDeleted = FALSE
                            """, tuple(allowed_system_codes))
                            subsystem_codes = [row['SubSystemCode'] for row in cur.fetchall() if row.get('SubSystemCode')]
                            if subsystem_codes:
                                sub_code_placeholders = ','.join(['%s'] * len(subsystem_codes))
                                cur.execute(f"""
                                    SELECT 
                                        COALESCE(SUM(TotalDIN), 0) AS total_din,
                                        COALESCE(SUM(CompletedDIN), 0) AS completed_din
                                    FROM BlockSubsystemSummary
                                    WHERE SubSystemCode IN ({sub_code_placeholders})
                                      AND Block IN ({block_placeholders})
                                """, tuple(subsystem_codes) + tuple(matched_blocks))
                            else:
                                cur.execute("SELECT 0 AS total_din, 0 AS completed_din")
                        else:
                            cur.execute("SELECT 0 AS total_din, 0 AS completed_din")
                    row = cur.fetchone() or {}
                    total_welding_din = float(row.get('total_din', 0) or 0)
                    completed_welding_din = float(row.get('completed_din', 0) or 0)
                finally:
                    conn.close()
            else:
                total_welding_din = 0
                completed_welding_din = 0
        elif system_code:
            # 无Faclist筛选但有系统筛选：直接从SystemWeldingSummary/SubsystemWeldingSummary查询
            conn = create_connection()
            if conn:
                try:
                    cur = conn.cursor(dictionary=True)
                    if level == 'system':
                        cur.execute("""
                            SELECT 
                                COALESCE(TotalDIN, 0) AS total_din,
                                COALESCE(CompletedDIN, 0) AS completed_din
                            FROM SystemWeldingSummary
                            WHERE SystemCode = %s
                        """, (system_code,))
                    else:
                        if subsystem_code:
                            cur.execute("""
                                SELECT 
                                    COALESCE(TotalDIN, 0) AS total_din,
                                    COALESCE(CompletedDIN, 0) AS completed_din
                                FROM SubsystemWeldingSummary
                                WHERE SubSystemCode = %s
                            """, (subsystem_code,))
                        else:
                            cur.execute("""
                                SELECT 
                                    COALESCE(SUM(TotalDIN), 0) AS total_din,
                                    COALESCE(SUM(CompletedDIN), 0) AS completed_din
                                FROM SubsystemWeldingSummary
                                WHERE SystemCode = %s
                            """, (system_code,))
                    row = cur.fetchone() or {}
                    total_welding_din = float(row.get('total_din', 0) or 0)
                    completed_welding_din = float(row.get('completed_din', 0) or 0)
                finally:
                    conn.close()
            else:
                total_welding_din = 0
                completed_welding_din = 0
        else:
            # 无任何筛选：从统计数据中汇总（所有数据）
            total_welding_din = sum(float(item.get('TotalDIN', 0) or 0) for item in all_stats)
            completed_welding_din = sum(float(item.get('CompletedDIN', 0) or 0) for item in all_stats)
        welding_progress = (completed_welding_din / total_welding_din * 100) if total_welding_din > 0 else 0
    elif module_type.startswith('precom_'):
        task_type_map = {
            'precom_manhole': 'Manhole',
            'precom_motor_solo': 'MotorSolo',
            'precom_skid_install': 'SkidInstall',
            'precom_loop_test': 'LoopTest',
            'precom_alignment': 'Alignment',
            'precom_mrt': 'MRT',
            'precom_function_test': 'FunctionTest'
        }
        task_type = task_type_map.get(module_type, 'Manhole')
        all_stats = get_precom_task_stats(task_type, level, system_code, subsystem_code, matched_blocks, allowed_system_codes)
        total_count = len(all_stats)
        completed_count = sum(1 for item in all_stats if (item.get('Progress', 0) or 0) >= 100)
        in_progress_count = sum(1 for item in all_stats if 0 < (item.get('Progress', 0) or 0) < 100)
        total_pages = max(1, ceil(total_count / per_page))
        page = max(1, min(page, total_pages))
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        stats = all_stats[start_idx:end_idx]
        total_quantity = sum(item.get('TotalQuantity', 0) or 0 for item in all_stats)
        completed_quantity = sum(item.get('CompletedQuantity', 0) or 0 for item in all_stats)
        overall_progress = (completed_quantity / total_quantity * 100) if total_quantity > 0 else 0
        total_packages = total_quantity
        completed_packages = completed_quantity
        # 预试车任务模块：卡片展示施工进度数据（加权处理）
        # 计算加权施工进度：基于 QuantityTotal 和 QuantityDone
        total_weighted = 0
        completed_weighted = 0
        for item in all_stats:
            qty_total = float(item.get('TotalQuantity', 0) or 0)
            qty_done = float(item.get('CompletedQuantity', 0) or 0)
            total_weighted += qty_total
            completed_weighted += qty_done
        card_total_packages = int(total_weighted) if total_weighted > 0 else 0
        card_completed_packages = int(completed_weighted) if completed_weighted > 0 else 0
        card_progress = (completed_weighted / total_weighted * 100) if total_weighted > 0 else 0
        # 计算焊接量统计（考虑Faclist筛选条件和系统筛选）
        if matched_blocks:
            # 有Faclist筛选：从BlockSystemSummary/BlockSubsystemSummary计算
            conn = create_connection()
            if conn:
                try:
                    cur = conn.cursor(dictionary=True)
                    block_placeholders = ','.join(['%s'] * len(matched_blocks))
                    if level == 'system':
                        # 使用allowed_system_codes获取所有符合筛选条件的系统代码
                        if allowed_system_codes and len(allowed_system_codes) > 0:
                            code_placeholders = ','.join(['%s'] * len(allowed_system_codes))
                            cur.execute(f"""
                                SELECT 
                                    COALESCE(SUM(TotalDIN), 0) AS total_din,
                                    COALESCE(SUM(CompletedDIN), 0) AS completed_din
                                FROM BlockSystemSummary
                                WHERE SystemCode IN ({code_placeholders})
                                  AND Block IN ({block_placeholders})
                            """, tuple(allowed_system_codes) + tuple(matched_blocks))
                        else:
                            cur.execute("SELECT 0 AS total_din, 0 AS completed_din")
                    else:
                        # 子系统级别：需要先获取符合筛选条件的子系统代码
                        if allowed_system_codes and len(allowed_system_codes) > 0:
                            code_placeholders = ','.join(['%s'] * len(allowed_system_codes))
                            cur.execute(f"""
                                SELECT DISTINCT SubSystemCode
                                FROM SubsystemList
                                WHERE SystemCode IN ({code_placeholders})
                                  AND IsDeleted = FALSE
                            """, tuple(allowed_system_codes))
                            subsystem_codes = [row['SubSystemCode'] for row in cur.fetchall() if row.get('SubSystemCode')]
                            if subsystem_codes:
                                sub_code_placeholders = ','.join(['%s'] * len(subsystem_codes))
                                cur.execute(f"""
                                    SELECT 
                                        COALESCE(SUM(TotalDIN), 0) AS total_din,
                                        COALESCE(SUM(CompletedDIN), 0) AS completed_din
                                    FROM BlockSubsystemSummary
                                    WHERE SubSystemCode IN ({sub_code_placeholders})
                                      AND Block IN ({block_placeholders})
                                """, tuple(subsystem_codes) + tuple(matched_blocks))
                            else:
                                cur.execute("SELECT 0 AS total_din, 0 AS completed_din")
                        else:
                            cur.execute("SELECT 0 AS total_din, 0 AS completed_din")
                    row = cur.fetchone() or {}
                    total_welding_din = float(row.get('total_din', 0) or 0)
                    completed_welding_din = float(row.get('completed_din', 0) or 0)
                finally:
                    conn.close()
            else:
                total_welding_din = 0
                completed_welding_din = 0
        elif system_code:
            # 无Faclist筛选但有系统筛选：直接从SystemWeldingSummary/SubsystemWeldingSummary查询
            conn = create_connection()
            if conn:
                try:
                    cur = conn.cursor(dictionary=True)
                    if level == 'system':
                        cur.execute("""
                            SELECT 
                                COALESCE(TotalDIN, 0) AS total_din,
                                COALESCE(CompletedDIN, 0) AS completed_din
                            FROM SystemWeldingSummary
                            WHERE SystemCode = %s
                        """, (system_code,))
                    else:
                        if subsystem_code:
                            cur.execute("""
                                SELECT 
                                    COALESCE(TotalDIN, 0) AS total_din,
                                    COALESCE(CompletedDIN, 0) AS completed_din
                                FROM SubsystemWeldingSummary
                                WHERE SubSystemCode = %s
                            """, (subsystem_code,))
                        else:
                            cur.execute("""
                                SELECT 
                                    COALESCE(SUM(TotalDIN), 0) AS total_din,
                                    COALESCE(SUM(CompletedDIN), 0) AS completed_din
                                FROM SubsystemWeldingSummary
                                WHERE SystemCode = %s
                            """, (system_code,))
                    row = cur.fetchone() or {}
                    total_welding_din = float(row.get('total_din', 0) or 0)
                    completed_welding_din = float(row.get('completed_din', 0) or 0)
                finally:
                    conn.close()
            else:
                total_welding_din = 0
                completed_welding_din = 0
        else:
            # 无任何筛选：从统计数据中汇总（所有数据）
            total_welding_din = sum(float(item.get('TotalDIN', 0) or 0) for item in all_stats)
            completed_welding_din = sum(float(item.get('CompletedDIN', 0) or 0) for item in all_stats)
        welding_progress = (completed_welding_din / total_welding_din * 100) if total_welding_din > 0 else 0
    else:
        all_stats = get_overview_stats(level, system_code, subsystem_code, matched_blocks, allowed_system_codes)
        total_count = len(all_stats)
        completed_count = 0
        in_progress_count = 0
        total_pages = max(1, ceil(total_count / per_page))
        page = max(1, min(page, total_pages))
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        stats = all_stats[start_idx:end_idx]
        total_packages = sum(item.get('TotalPackages', 0) or 0 for item in all_stats)
        completed_packages = sum(item.get('TestedPackages', 0) or 0 for item in all_stats)
        overall_progress = (completed_packages / total_packages * 100) if total_packages > 0 else 0
    
    # 构建分页信息（包含Faclist筛选参数）
    base_url = f"/dashboard?module={module_type}&level={level}"
    if system_code:
        base_url += f"&system_code={system_code}"
    if subsystem_code:
        base_url += f"&subsystem_code={subsystem_code}"
    for key, value in fac_filters.items():
        if value:
            base_url += f"&{key}={value}"
    base_url += "&page="
    
    pagination = {
        'current_page': page,
        'total_pages': total_pages,
        'has_prev': page > 1,
        'has_next': page < total_pages,
        'prev_url': base_url + str(page-1) if page > 1 else None,
        'next_url': base_url + str(page+1) if page < total_pages else None,
        'start_index': start_idx + 1,
        'end_index': min(end_idx, total_count),
        'window': list(range(max(1, page - 2), min(total_pages, page + 2) + 1))
    }
    
    # 为非总览模块初始化焊接量统计变量（如果未定义）
    if module_type != 'overview':
        try:
            _ = total_welding_din
        except NameError:
            total_welding_din = 0
        try:
            _ = completed_welding_din
        except NameError:
            completed_welding_din = 0
        try:
            _ = welding_progress
        except NameError:
            welding_progress = 0
    
    # 初始化卡片数据变量（用于模板显示）
    card_total_packages = card_total_packages if 'card_total_packages' in locals() else 0
    card_completed_packages = card_completed_packages if 'card_completed_packages' in locals() else 0
    card_progress = card_progress if 'card_progress' in locals() else 0
    
    return render_template('dashboard.html',
                         module_type=module_type,
                         level=level,
                         stats=stats,
                         total_packages=total_packages,
                         completed_packages=completed_packages,
                         overall_progress=overall_progress,
                         total_welding_din=total_welding_din if module_type != 'overview' else 0,
                         completed_welding_din=completed_welding_din if module_type != 'overview' else 0,
                         welding_progress=welding_progress if module_type != 'overview' else 0,
                         card_total_packages=card_total_packages if module_type != 'overview' else 0,
                         card_completed_packages=card_completed_packages if module_type != 'overview' else 0,
                         card_progress=card_progress if module_type != 'overview' else 0,
                         module_types=MODULE_TYPES,
                         systems=systems,
                         subsystems=subsystems,
                         filter_system=system_code,
                         filter_subsystem=subsystem_code,
                         faclist_options=faclist_options,
                         filter_subproject=fac_filters['subproject_code'],
                         filter_train=fac_filters['train'],
                         filter_unit=fac_filters['unit'],
                         filter_simpleblk=fac_filters['simpleblk'],
                         filter_mainblock=fac_filters['mainblock'],
                         filter_block=fac_filters['block'],
                         filter_bccquarter=fac_filters['bccquarter'],
                         pagination=pagination,
                         total_count=total_count,
                         completed_count=completed_count,
                         in_progress_count=in_progress_count)


@dashboard_bp.route('/api/dashboard/stats')
@login_required
def api_stats():
    """API: 获取统计数据"""
    module_type = request.args.get('module', 'overview')
    level = request.args.get('level', 'system')
    
    if module_type == 'test':
        stats = get_test_package_stats(level)
    elif module_type == 'flushing':
        stats = get_flushing_stats(level)
    elif module_type == 'reinstatement':
        stats = get_reinstatement_stats(level)
    elif module_type.startswith('precom_'):
        task_type_map = {
            'precom_manhole': 'Manhole',
            'precom_motor_solo': 'MotorSolo',
            'precom_skid_install': 'SkidInstall',
            'precom_loop_test': 'LoopTest',
            'precom_alignment': 'Alignment',
            'precom_mrt': 'MRT',
            'precom_function_test': 'FunctionTest'
        }
        task_type = task_type_map.get(module_type, 'Manhole')
        stats = get_precom_task_stats(task_type, level)
    else:
        stats = get_overview_stats(level)
    
    return jsonify({'success': True, 'data': stats})


@dashboard_bp.route('/api/dashboard/planned-vs-actual')
@login_required
def api_planned_vs_actual():
    """API: 获取计划vs实际完成情况数据（组合图）"""
    module_type = request.args.get('module', 'test')
    period = request.args.get('period', 'month')
    if period not in ['year', 'quarter', 'month']:
        period = 'month'
    
    data = get_planned_vs_actual_data(module_type, period)
    return jsonify({'success': True, 'data': data})


@dashboard_bp.route('/api/dashboard/faclist_options')
@login_required
def api_faclist_options():
    """Faclist 筛选选项 API（用于 AJAX 更新下拉框）"""
    filter_subproject = (request.args.get('subproject_code') or '').strip() or None
    filter_train = (request.args.get('train') or '').strip() or None
    filter_unit = (request.args.get('unit') or '').strip() or None
    filter_simpleblk = (request.args.get('simpleblk') or '').strip() or None
    filter_mainblock = (request.args.get('mainblock') or '').strip() or None
    filter_block = (request.args.get('block') or '').strip() or None
    filter_bccquarter = (request.args.get('bccquarter') or '').strip() or None
    
    options = get_faclist_filter_options(
        filter_subproject=filter_subproject,
        filter_train=filter_train,
        filter_unit=filter_unit,
        filter_simpleblk=filter_simpleblk,
        filter_mainblock=filter_mainblock,
        filter_block=filter_block,
        filter_bccquarter=filter_bccquarter
    )
    
    return jsonify({
        'subproject_codes': options.get('subproject_codes', []),
        'trains': options.get('trains', []),
        'units': options.get('units', []),
        'simpleblks': options.get('simpleblks', []),
        'mainblocks': options.get('mainblocks', {}),
        'blocks': options.get('blocks', {}),
        'bccquarters': options.get('bccquarters', [])
    })


def get_precom_task_stats(task_type, level='system', system_code=None, subsystem_code=None, matched_blocks=None, allowed_system_codes=None):
    """获取预试车任务统计"""
    conn = create_connection()
    if not conn:
        return []
    
    try:
        cur = conn.cursor(dictionary=True)
        where_clauses = []
        params = [task_type]
        
        if level == 'system':
            where_clauses.append("s.IsDeleted = FALSE")
            if system_code:
                where_clauses.append("s.SystemCode = %s")
                params.append(system_code)
            if allowed_system_codes is not None:
                if len(allowed_system_codes) == 0:
                    return []
                placeholders = ','.join(['%s'] * len(allowed_system_codes))
                where_clauses.append(f"s.SystemCode IN ({placeholders})")
                params.extend(allowed_system_codes)
            
            sql = """
                SELECT 
                    s.SystemCode,
                    s.SystemDescriptionENG,
                    s.ProcessOrNonProcess,
                    COALESCE(SUM(pt.QuantityTotal), 0) AS TotalQuantity,
                    COALESCE(SUM(pt.QuantityDone), 0) AS CompletedQuantity,
                    COALESCE(sws.TotalDIN, 0) AS TotalDIN,
                    COALESCE(sws.CompletedDIN, 0) AS CompletedDIN,
                    CASE 
                        WHEN SUM(pt.QuantityTotal) > 0 
                        THEN (SUM(pt.QuantityDone) / SUM(pt.QuantityTotal)) * 100
                        ELSE 0
                    END AS Progress,
                    -- 尾项统计（试压包尾项 + 预试车任务尾项）
                    COALESCE((SELECT COUNT(*) FROM PunchList pl 
                        WHERE pl.TestPackageID IN 
                            (SELECT h.TestPackageID FROM HydroTestPackageList h 
                             WHERE h.SystemCode = s.SystemCode AND h.IsDeleted = FALSE)
                        AND (pl.Deleted IS NULL OR pl.Deleted != 'Y')
                    ), 0) + 
                    COALESCE((SELECT COUNT(*) FROM PrecomTaskPunch ptp 
                        INNER JOIN PrecomTask pt2 ON ptp.TaskID = pt2.TaskID 
                        WHERE pt2.SystemCode = s.SystemCode AND (ptp.Deleted IS NULL OR ptp.Deleted = 'N')
                    ), 0) AS PunchTotal,
                    COALESCE((SELECT COUNT(*) FROM PunchList pl 
                        WHERE pl.TestPackageID IN 
                            (SELECT h.TestPackageID FROM HydroTestPackageList h 
                             WHERE h.SystemCode = s.SystemCode AND h.IsDeleted = FALSE)
                        AND pl.Rectified = 'Y' AND (pl.Deleted IS NULL OR pl.Deleted != 'Y')
                    ), 0) + 
                    COALESCE((SELECT COUNT(*) FROM PrecomTaskPunch ptp 
                        INNER JOIN PrecomTask pt2 ON ptp.TaskID = pt2.TaskID 
                        WHERE pt2.SystemCode = s.SystemCode AND ptp.Rectified = 'Y' AND (ptp.Deleted IS NULL OR ptp.Deleted = 'N')
                    ), 0) AS PunchRectified,
                    COALESCE((SELECT COUNT(*) FROM PunchList pl 
                        WHERE pl.TestPackageID IN 
                            (SELECT h.TestPackageID FROM HydroTestPackageList h 
                             WHERE h.SystemCode = s.SystemCode AND h.IsDeleted = FALSE)
                        AND pl.Verified = 'Y' AND (pl.Deleted IS NULL OR pl.Deleted != 'Y')
                    ), 0) + 
                    COALESCE((SELECT COUNT(*) FROM PrecomTaskPunch ptp 
                        INNER JOIN PrecomTask pt2 ON ptp.TaskID = pt2.TaskID 
                        WHERE pt2.SystemCode = s.SystemCode AND ptp.Verified = 'Y' AND (ptp.Deleted IS NULL OR ptp.Deleted = 'N')
                    ), 0) AS PunchVerified
                FROM SystemList s
                LEFT JOIN PrecomTask pt ON pt.SystemCode = s.SystemCode 
                    AND pt.TaskType = %s
                LEFT JOIN SystemWeldingSummary sws ON sws.SystemCode = s.SystemCode
                WHERE """ + " AND ".join(where_clauses) + """
                GROUP BY s.SystemCode, s.SystemDescriptionENG, s.ProcessOrNonProcess, sws.TotalDIN, sws.CompletedDIN
                ORDER BY s.SystemCode
            """
            cur.execute(sql, tuple(params))
        else:  # subsystem
            where_clauses.append("sub.IsDeleted = FALSE")
            if system_code:
                where_clauses.append("sub.SystemCode = %s")
                params.append(system_code)
            if subsystem_code:
                where_clauses.append("sub.SubSystemCode = %s")
                params.append(subsystem_code)
            if allowed_system_codes is not None:
                if len(allowed_system_codes) == 0:
                    return []
                placeholders = ','.join(['%s'] * len(allowed_system_codes))
                where_clauses.append(f"sub.SystemCode IN ({placeholders})")
                params.extend(allowed_system_codes)
            
            sql = """
                SELECT 
                    sub.SubSystemCode,
                    sub.SystemCode,
                    sub.SubSystemDescriptionENG,
                    sub.ProcessOrNonProcess,
                    COALESCE(SUM(pt.QuantityTotal), 0) AS TotalQuantity,
                    COALESCE(SUM(pt.QuantityDone), 0) AS CompletedQuantity,
                    COALESCE(sws.TotalDIN, 0) AS TotalDIN,
                    COALESCE(sws.CompletedDIN, 0) AS CompletedDIN,
                    CASE 
                        WHEN SUM(pt.QuantityTotal) > 0 
                        THEN (SUM(pt.QuantityDone) / SUM(pt.QuantityTotal)) * 100
                        ELSE 0
                    END AS Progress,
                    -- 尾项统计（试压包尾项 + 预试车任务尾项）
                    COALESCE((SELECT COUNT(*) FROM PunchList pl 
                        WHERE pl.TestPackageID IN 
                            (SELECT h.TestPackageID FROM HydroTestPackageList h 
                             WHERE h.SubSystemCode = sub.SubSystemCode AND h.IsDeleted = FALSE)
                        AND (pl.Deleted IS NULL OR pl.Deleted != 'Y')
                    ), 0) + 
                    COALESCE((SELECT COUNT(*) FROM PrecomTaskPunch ptp 
                        INNER JOIN PrecomTask pt2 ON ptp.TaskID = pt2.TaskID 
                        WHERE pt2.SubSystemCode = sub.SubSystemCode AND (ptp.Deleted IS NULL OR ptp.Deleted = 'N')
                    ), 0) AS PunchTotal,
                    COALESCE((SELECT COUNT(*) FROM PunchList pl 
                        WHERE pl.TestPackageID IN 
                            (SELECT h.TestPackageID FROM HydroTestPackageList h 
                             WHERE h.SubSystemCode = sub.SubSystemCode AND h.IsDeleted = FALSE)
                        AND pl.Rectified = 'Y' AND (pl.Deleted IS NULL OR pl.Deleted != 'Y')
                    ), 0) + 
                    COALESCE((SELECT COUNT(*) FROM PrecomTaskPunch ptp 
                        INNER JOIN PrecomTask pt2 ON ptp.TaskID = pt2.TaskID 
                        WHERE pt2.SubSystemCode = sub.SubSystemCode AND ptp.Rectified = 'Y' AND (ptp.Deleted IS NULL OR ptp.Deleted = 'N')
                    ), 0) AS PunchRectified,
                    COALESCE((SELECT COUNT(*) FROM PunchList pl 
                        WHERE pl.TestPackageID IN 
                            (SELECT h.TestPackageID FROM HydroTestPackageList h 
                             WHERE h.SubSystemCode = sub.SubSystemCode AND h.IsDeleted = FALSE)
                        AND pl.Verified = 'Y' AND (pl.Deleted IS NULL OR pl.Deleted != 'Y')
                    ), 0) + 
                    COALESCE((SELECT COUNT(*) FROM PrecomTaskPunch ptp 
                        INNER JOIN PrecomTask pt2 ON ptp.TaskID = pt2.TaskID 
                        WHERE pt2.SubSystemCode = sub.SubSystemCode AND ptp.Verified = 'Y' AND (ptp.Deleted IS NULL OR ptp.Deleted = 'N')
                    ), 0) AS PunchVerified
                FROM SubsystemList sub
                LEFT JOIN PrecomTask pt ON pt.SubSystemCode = sub.SubSystemCode 
                    AND pt.TaskType = %s
                LEFT JOIN SubsystemWeldingSummary sws ON sws.SubSystemCode = sub.SubSystemCode
                WHERE """ + " AND ".join(where_clauses) + """
                GROUP BY sub.SubSystemCode, sub.SystemCode, sub.SubSystemDescriptionENG, sub.ProcessOrNonProcess, sws.TotalDIN, sws.CompletedDIN
                ORDER BY sub.SystemCode, sub.SubSystemCode
            """
            cur.execute(sql, tuple(params))
        return cur.fetchall()
    finally:
        conn.close()
