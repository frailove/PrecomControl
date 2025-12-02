from flask import Blueprint, request, redirect, render_template, jsonify
from models.subsystem import SubsystemModel
from models.system import SystemModel
from database import create_connection
from utils.exporters import export_subsystems_to_excel
from math import ceil
from urllib.parse import urlencode
import re

# 创建蓝图
subsystem_bp = Blueprint('subsystem', __name__)
PER_PAGE = 50


def build_pagination_base_path(args, path='/subsystems'):
    params = args.to_dict(flat=False)
    params.pop('page', None)
    query_pairs = []
    for key, values in params.items():
        for value in values:
            if value not in (None, ''):
                query_pairs.append((key, value))
    encoded = urlencode(query_pairs)
    if encoded:
        return f"{path}?{encoded}&page="
    return f"{path}?page="

def extract_drawing_pattern(drawing_number):
    """从 DrawingNumber 中提取匹配模式
    例如：'GCC-ASP-DDD-16150-12-2200-TKM-ISO-00004' -> '16150-12-2200'
    """
    if not drawing_number:
        return None
    parts = re.findall(r'\d+', drawing_number)
    if len(parts) >= 3:
        return '-'.join(parts[:3])
    elif len(parts) == 2:
        return '-'.join(parts)
    elif len(parts) == 1:
        return parts[0]
    return None



def fetch_drawings_by_block_patterns(cursor, block_patterns, chunk_size=50):
    """
    根据 block 模式批量匹配 DrawingNumber。
    性能优化：使用 Block 字段直接过滤（如果存在），否则回退到 LIKE 查询。
    这样可以利用索引，大幅提升性能。
    """
    if not block_patterns:
        return set()
    patterns = [p for p in block_patterns if p]
    if not patterns:
        return set()
    
    matched = set()
    
    # 性能优化：使用 Block 字段直接过滤（利用索引，O(1) 查找）
    cursor.execute("SHOW COLUMNS FROM WeldingList LIKE 'Block'")
    has_block_column = cursor.fetchone() is not None
    
    if has_block_column:
        # 使用 Block 字段直接过滤，利用索引，性能极佳
        temp_table_name = f"temp_block_patterns_{id(cursor)}"
        try:
            cursor.execute(f"""
                CREATE TEMPORARY TABLE {temp_table_name} (
                    pattern VARCHAR(255) NOT NULL,
                    INDEX idx_pattern (pattern(100))
                ) ENGINE=Memory
            """)
            
            for i in range(0, len(patterns), chunk_size):
                chunk = patterns[i:i + chunk_size]
                values = ','.join(['(%s)'] * len(chunk))
                params = tuple(chunk)
                cursor.execute(
                    f"INSERT INTO {temp_table_name} (pattern) VALUES {values}",
                    params
                )
            
            # 使用 Block 字段直接匹配（等值查询，可以使用索引）
            # patterns 已经是 Faclist 中的 Block 格式，直接匹配 WeldingList 中的 Block 字段
            cursor.execute(f"""
                SELECT DISTINCT wl.DrawingNumber
                FROM WeldingList wl
                INNER JOIN {temp_table_name} tmp ON wl.Block = tmp.pattern
                WHERE wl.DrawingNumber IS NOT NULL
                  AND wl.DrawingNumber <> ''
                  AND wl.Block IS NOT NULL
                  AND wl.Block <> ''
            """)
            
            for row in cursor.fetchall():
                drawing = row.get('DrawingNumber')
                if drawing:
                    matched.add(drawing)
            
            print(f"[DEBUG][fetch_drawings] 使用 Block 字段匹配，找到 {len(matched)} 个图纸号", flush=True)
        finally:
            try:
                cursor.execute(f"DROP TEMPORARY TABLE IF EXISTS {temp_table_name}")
            except:
                pass
    else:
        # 回退方案：如果 Block 字段不存在，使用 LIKE 查询（兼容旧数据）
        temp_table_name = f"temp_block_patterns_{id(cursor)}"
        try:
            cursor.execute(f"""
                CREATE TEMPORARY TABLE {temp_table_name} (
                    pattern VARCHAR(255) NOT NULL,
                    INDEX idx_pattern (pattern(50))
                ) ENGINE=Memory
            """)
            
            for i in range(0, len(patterns), chunk_size):
                chunk = patterns[i:i + chunk_size]
                values = ','.join(['(%s)'] * len(chunk))
                params = tuple(chunk)
                cursor.execute(
                    f"INSERT INTO {temp_table_name} (pattern) VALUES {values}",
                    params
                )
            
            cursor.execute(f"""
                SELECT DISTINCT wl.DrawingNumber
                FROM WeldingList wl
                INNER JOIN {temp_table_name} tmp ON wl.DrawingNumber LIKE CONCAT('%', tmp.pattern, '%')
                WHERE wl.DrawingNumber IS NOT NULL
                  AND wl.DrawingNumber <> ''
            """)
            
            for row in cursor.fetchall():
                drawing = row.get('DrawingNumber')
                if drawing:
                    matched.add(drawing)
        finally:
            try:
                cursor.execute(f"DROP TEMPORARY TABLE IF EXISTS {temp_table_name}")
            except:
                pass
    
    return matched

def get_faclist_filter_options(filter_subproject=None, filter_train=None, filter_unit=None, 
                                filter_simpleblk=None, filter_mainblock=None, filter_block=None, 
                                filter_bccquarter=None):
    """获取 Faclist 筛选选项（支持根据已选择的筛选条件动态过滤）"""
    conn = create_connection()
    if not conn:
        return {}
    
    options = {
        'subproject_codes': [],
        'trains': [],
        'units': [],
        'simpleblks': [],
        'mainblocks': {},
        'blocks': {},
        'bccquarters': []
    }
    
    try:
        cur = conn.cursor(dictionary=True)
        # 构建 WHERE 条件
        where_clauses = []
        params = []
        
        if filter_subproject:
            where_clauses.append("SubProjectCode = %s")
            params.append(filter_subproject)
        if filter_train:
            where_clauses.append("Train = %s")
            params.append(filter_train)
        if filter_unit:
            where_clauses.append("Unit = %s")
            params.append(filter_unit)
        if filter_simpleblk:
            where_clauses.append("SimpleBLK = %s")
            params.append(filter_simpleblk)
        if filter_mainblock:
            where_clauses.append("MainBlock = %s")
            params.append(filter_mainblock)
        if filter_block:
            where_clauses.append("Block = %s")
            params.append(filter_block)
        if filter_bccquarter:
            where_clauses.append("BCCQuarter = %s")
            params.append(filter_bccquarter)
        
        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
        
        cur.execute(f"""
            SELECT DISTINCT SubProjectCode, Train, Unit, SimpleBLK, MainBlock, Block, BCCQuarter
            FROM Faclist
            WHERE ({where_sql})
              AND (SubProjectCode IS NOT NULL OR Train IS NOT NULL OR Unit IS NOT NULL 
               OR SimpleBLK IS NOT NULL OR MainBlock IS NOT NULL OR Block IS NOT NULL OR BCCQuarter IS NOT NULL)
            ORDER BY SubProjectCode, Train, Unit, SimpleBLK, MainBlock, Block, BCCQuarter
        """, tuple(params))
        
        for row in cur.fetchall():
            if row.get('SubProjectCode') and row['SubProjectCode'] not in options['subproject_codes']:
                options['subproject_codes'].append(row['SubProjectCode'])
            if row.get('Train') and row['Train'] not in options['trains']:
                options['trains'].append(row['Train'])
            if row.get('Unit') and row['Unit'] not in options['units']:
                options['units'].append(row['Unit'])
            if row.get('SimpleBLK') and row['SimpleBLK'] not in options['simpleblks']:
                options['simpleblks'].append(row['SimpleBLK'])
            if row.get('BCCQuarter') and row['BCCQuarter'] not in options['bccquarters']:
                options['bccquarters'].append(row['BCCQuarter'])
            
            if row.get('SimpleBLK'):
                if row['SimpleBLK'] not in options['mainblocks']:
                    options['mainblocks'][row['SimpleBLK']] = []
                if row.get('MainBlock') and row['MainBlock'] not in options['mainblocks'][row['SimpleBLK']]:
                    options['mainblocks'][row['SimpleBLK']].append(row['MainBlock'])
            
            if row.get('MainBlock'):
                if row['MainBlock'] not in options['blocks']:
                    options['blocks'][row['MainBlock']] = []
                if row.get('Block') and row['Block'] not in options['blocks'][row['MainBlock']]:
                    options['blocks'][row['MainBlock']].append(row['Block'])
        
        options['subproject_codes'].sort()
        options['trains'].sort()
        options['units'].sort()
        options['simpleblks'].sort()
        options['bccquarters'].sort()
        
    finally:
        conn.close()
    
    return options

def load_subsystem_stats(subsystem_codes, matched_drawing_numbers=None):
    """
    获取指定子系统的焊接 / 试压统计（仅针对当前页）。
    为了性能，这里直接读取预聚合表 SubsystemWeldingSummary，而不再实时汇总。
    matched_drawing_numbers 当前忽略（用于 Faclist 过滤时，子系统列表仍显示全局汇总）。
    """
    stats = {}
    if not subsystem_codes:
        return stats
    conn = create_connection()
    if not conn:
        return stats
    try:
        cur = conn.cursor(dictionary=True)
        code_placeholders = ','.join(['%s'] * len(subsystem_codes))
        cur.execute(
            f"""
            SELECT SystemCode,
                   SubSystemCode,
                   COALESCE(TotalDIN, 0) AS total_din,
                   COALESCE(CompletedDIN, 0) AS completed_din,
                   COALESCE(TotalPackages, 0) AS total_packages,
                   COALESCE(TestedPackages, 0) AS tested_packages
            FROM SubsystemWeldingSummary
            WHERE SubSystemCode IN ({code_placeholders})
            """,
            tuple(subsystem_codes)
        )
        for row in cur.fetchall():
            sub_code = row.get('SubSystemCode')
            if not sub_code:
                continue
            total_din = float(row['total_din'] or 0)
            completed_din = float(row['completed_din'] or 0)
            total_packages = int(row['total_packages'] or 0)
            tested_packages = int(row['tested_packages'] or 0)
            s = stats.setdefault(sub_code, {})
            s['total_din'] = total_din
            s['completed_din'] = completed_din
            s['welding_progress'] = (completed_din / total_din) if total_din > 0 else 0.0
            s['total_packages'] = total_packages
            s['tested_packages'] = tested_packages
            s['test_progress'] = (tested_packages / total_packages) if total_packages > 0 else 0.0
            s['SystemCode'] = row.get('SystemCode')
        return stats
    finally:
        if conn:
            conn.close()


def load_subsystem_stats_with_faclist(subsystem_codes, matched_blocks):
    """
    当启用 Faclist 过滤时，基于 BlockSubsystemSummary 预聚合表计算当前页子系统的统计信息。
    完全避免扫描 WeldingList / HydroTestPackageList。
    """
    stats = {}
    if not subsystem_codes or not matched_blocks:
        return stats

    conn = create_connection()
    if not conn:
        return stats
    try:
        cur = conn.cursor(dictionary=True)
        code_placeholders = ','.join(['%s'] * len(subsystem_codes))

        # Block 格式已与 Faclist 一致，直接使用
        block_list = [b.strip() for b in matched_blocks if b and b.strip()]
        block_list = list(set(block_list))  # 去重
        if not block_list:
            return stats

        block_placeholders = ','.join(['%s'] * len(block_list))

        cur.execute(
            f"""
            SELECT
                SubSystemCode,
                MIN(SystemCode)                    AS SystemCode,
                COALESCE(SUM(TotalDIN), 0)         AS total_din,
                COALESCE(SUM(CompletedDIN), 0)     AS completed_din,
                COALESCE(SUM(TotalPackages), 0)    AS total_packages,
                COALESCE(SUM(TestedPackages), 0)   AS tested_packages
            FROM BlockSubsystemSummary
            WHERE SubSystemCode IN ({code_placeholders})
              AND Block IN ({block_placeholders})
            GROUP BY SubSystemCode
            """,
            tuple(subsystem_codes) + tuple(block_list),
        )

        for row in cur.fetchall():
            sub_code = row.get('SubSystemCode')
            if not sub_code:
                continue
            total_din = float(row['total_din'] or 0)
            completed_din = float(row['completed_din'] or 0)
            total_packages = int(row['total_packages'] or 0)
            tested_packages = int(row['tested_packages'] or 0)
            stats[sub_code] = {
                'total_din': total_din,
                'completed_din': completed_din,
                'welding_progress': (completed_din / total_din) if total_din > 0 else 0.0,
                'total_packages': total_packages,
                'tested_packages': tested_packages,
                'test_progress': (tested_packages / total_packages) if total_packages > 0 else 0.0,
                'SystemCode': row.get('SystemCode'),
            }

        return stats
    finally:
        conn.close()

def get_bootstrap_css():
    """返回Bootstrap CSS链接"""
    return '<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">'

def get_navbar():
    """返回导航栏"""
    return '''
    <nav class="navbar navbar-expand-lg navbar-dark bg-dark">
        <div class="container-fluid">
            <a class="navbar-brand" href="/">🚀 预试车管理系统</a>
            <div class="navbar-nav">
                <a class="nav-link" href="/">首页</a>
                <a class="nav-link" href="/systems">系统管理</a>
                <a class="nav-link" href="/subsystems">子系统管理</a>
                <a class="nav-link" href="/test_packages">试压包管理</a>
            </div>
        </div>
    </nav>
    '''

@subsystem_bp.route('/subsystems')
def subsystems():
    """子系统列表页面（工业化UI）"""
    import time
    import sys
    total_start = time.time()
    
    search_query = (request.args.get('q') or '').strip()
    filter_system = (request.args.get('system_code') or '').strip()
    
    # 调试：打印接收到的参数（强制刷新输出）
    if filter_system:
        print(f"[DEBUG] 接收到 filter_system: '{filter_system}' (类型: {type(filter_system)})", flush=True)
    else:
        # 安全：不打印完整的 request.args，避免泄露敏感信息（如URL中的密码参数）
        print(f"[DEBUG] 未接收到 filter_system", flush=True)
    filter_type = (request.args.get('type') or '').strip()
    filter_subproject = (request.args.get('subproject_code') or '').strip()
    filter_train = (request.args.get('train') or '').strip()
    filter_unit = (request.args.get('unit') or '').strip()
    filter_simpleblk = (request.args.get('simpleblk') or '').strip()
    filter_mainblock = (request.args.get('mainblock') or '').strip()
    filter_block = (request.args.get('block') or '').strip()
    filter_bccquarter = (request.args.get('bccquarter') or '').strip()

    # 标记当前是否启用了 Faclist 过滤条件（后续用于决定是否去解析 Block -> 子系统代码）
    has_faclist_filters = any([
        filter_subproject, filter_train, filter_unit,
        filter_simpleblk, filter_mainblock, filter_block, filter_bccquarter
    ])

    # 和系统列表保持一致：无论是否使用 Faclist 筛选，都从 Faclist 生成下拉选项（方便用户直接选择）
    faclist_start = time.time()
    faclist_options = get_faclist_filter_options(
        filter_subproject=filter_subproject or None,
        filter_train=filter_train or None,
        filter_unit=filter_unit or None,
        filter_simpleblk=filter_simpleblk or None,
        filter_mainblock=filter_mainblock or None,
        filter_block=filter_block or None,
        filter_bccquarter=filter_bccquarter or None,
    )
    print(f"[DEBUG][subsystems] Faclist 查询耗时: {time.time() - faclist_start:.2f} 秒", flush=True)

    def build_option_list(source_map, key_filter):
        if not source_map:
            return []
        if key_filter and key_filter in source_map:
            return sorted([str(value) for value in source_map[key_filter]])
        unique_values = set()
        for values in source_map.values():
            for value in values:
                if value:
                    unique_values.add(str(value))
        return sorted(unique_values)

    available_mainblocks = build_option_list(faclist_options.get('mainblocks', {}), filter_simpleblk)
    available_blocks = build_option_list(faclist_options.get('blocks', {}), filter_mainblock)

    # 处理 Faclist 筛选条件，获取允许的子系统代码（类似于系统管理页面）
    def get_matched_drawing_numbers(cur):
        if not any([filter_subproject, filter_train, filter_unit, filter_simpleblk, filter_mainblock, filter_block, filter_bccquarter]):
            return None
        clauses = []
        params = []
        if filter_subproject:
            clauses.append("SubProjectCode = %s")
            params.append(filter_subproject)
        if filter_train:
            clauses.append("Train = %s")
            params.append(filter_train)
        if filter_unit:
            clauses.append("Unit = %s")
            params.append(filter_unit)
        if filter_simpleblk:
            clauses.append("SimpleBLK = %s")
            params.append(filter_simpleblk)
        if filter_mainblock:
            clauses.append("MainBlock = %s")
            params.append(filter_mainblock)
        if filter_block:
            clauses.append("Block = %s")
            params.append(filter_block)
        if filter_bccquarter:
            clauses.append("BCCQuarter = %s")
            params.append(filter_bccquarter)
        if not clauses:
            return None
        where_clause = ' AND '.join(clauses)
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
        print(f"[DEBUG][_get_matched_drawing_numbers] 从 Faclist 找到 {len(matched_blocks)} 个 Block", flush=True)
        if not matched_blocks:
            return set()
        
        # Block 格式已与 Faclist 一致，直接使用
        block_patterns = {b.strip() for b in matched_blocks if b and b.strip()}
        
        print(f"[DEBUG][_get_matched_drawing_numbers] 准备匹配的 Block patterns: {list(block_patterns)[:5]}...", flush=True)
        matched_drawings = fetch_drawings_by_block_patterns(cur, block_patterns)
        print(f"[DEBUG][_get_matched_drawing_numbers] 找到 {len(matched_drawings)} 个匹配的图纸号", flush=True)
        return matched_drawings

    def resolve_subsystem_codes_by_blocks(cursor, matched_blocks):
        """
        使用 BlockSubsystemSummary（Block 维度预聚合表）将 Faclist Block 列表映射为 SubSystemCode 列表。
        优先走预聚合表；若预聚合表无数据（例如尚未刷新），则回退到 WeldingList 直接匹配，保证功能正确。
        """
        if not matched_blocks:
            return []

        # Block 格式已与 Faclist 一致，直接使用
        blocks = [b.strip() for b in matched_blocks if b and b.strip()]
        blocks = list(set(blocks))  # 去重
        if not blocks:
            return []

        placeholders = ','.join(['%s'] * len(blocks))
        cursor.execute(
            f"""
            SELECT DISTINCT SubSystemCode
            FROM BlockSubsystemSummary
            WHERE Block IN ({placeholders})
              AND SubSystemCode IS NOT NULL
              AND SubSystemCode <> ''
            """,
            tuple(blocks),
        )

        codes = []
        for row in cursor.fetchall():
            sub_code = row.get('SubSystemCode')
            if sub_code:
                codes.append(sub_code)

        # 如果预聚合表里没有任何匹配，说明 BlockSubsystemSummary 还没刷新好或者没有覆盖到这些 Block
        # 为了保证功能正确，这里回退到直接从 WeldingList 解析（可能会相对慢一点，但不会返回空结果）
        if not codes:
            print(
                f"[DEBUG][subsystems] BlockSubsystemSummary 未命中任何子系统代码，回退到 WeldingList 直接匹配（blocks={len(blocks)})",
                flush=True,
            )
            wl_codes = set()
            # 为避免 SQL 过长，对 Block 列表分批处理
            chunk_size = 200
            for i in range(0, len(blocks), chunk_size):
                chunk = blocks[i : i + chunk_size]
                ph = ','.join(['%s'] * len(chunk))
                # 直接从 WeldingList 获取子系统代码
                cursor.execute(
                    f"""
                    SELECT DISTINCT SubSystemCode
                    FROM WeldingList
                    WHERE Block IN ({ph})
                      AND SubSystemCode IS NOT NULL
                      AND SubSystemCode <> ''
                      AND Block IS NOT NULL
                      AND Block <> ''
                    """,
                    tuple(chunk),
                )
                for row in cursor.fetchall():
                    sub_code = row.get('SubSystemCode')
                    if sub_code:
                        wl_codes.add(sub_code)

                # 再从 HydroTestPackageList 通过 WeldingList 关联获取子系统代码
                cursor.execute(
                    f"""
                    SELECT DISTINCT h.SubSystemCode
                    FROM HydroTestPackageList h
                    INNER JOIN WeldingList wl ON wl.TestPackageID = h.TestPackageID
                    WHERE wl.Block IN ({ph})
                      AND h.SubSystemCode IS NOT NULL
                      AND h.SubSystemCode <> ''
                      AND wl.Block IS NOT NULL
                      AND wl.Block <> ''
                    """,
                    tuple(chunk),
                )
                for row in cursor.fetchall():
                    sub_code = row.get('SubSystemCode')
                    if sub_code:
                        wl_codes.add(sub_code)

            codes = sorted(wl_codes)

        return codes
    
    def resolve_subsystem_codes_for_filters(cursor, matched_drawing_numbers):
        """
        根据图纸号筛选条件，解析出允许的子系统代码。
        性能优化：如果数量小，直接用 IN；如果数量大，使用临时表。
        """
        if not matched_drawing_numbers:
            return None
        
        codes = set()
        
        # 如果数量较小，直接用 IN 查询（更快）
        if len(matched_drawing_numbers) <= 500:
            drawing_list = list(matched_drawing_numbers)
            placeholders = ','.join(['%s'] * len(drawing_list))
            
            # 查询 WeldingList
            cursor.execute(f"""
                SELECT DISTINCT SubSystemCode
                FROM WeldingList
                WHERE SubSystemCode IS NOT NULL
                  AND SubSystemCode <> ''
                  AND DrawingNumber IN ({placeholders})
            """, tuple(drawing_list))
            for row in cursor.fetchall():
                if row.get('SubSystemCode'):
                    codes.add(row['SubSystemCode'])
            
            # 查询 HydroTestPackageList
            cursor.execute(f"""
                SELECT DISTINCT h.SubSystemCode
                FROM HydroTestPackageList h
                INNER JOIN WeldingList wl ON wl.TestPackageID = h.TestPackageID
                WHERE h.SubSystemCode IS NOT NULL
                  AND h.SubSystemCode <> ''
                  AND wl.DrawingNumber IN ({placeholders})
            """, tuple(drawing_list))
            for row in cursor.fetchall():
                if row.get('SubSystemCode'):
                    codes.add(row['SubSystemCode'])
        else:
            # 数量大时，使用临时表
            temp_table_name = f"temp_drawings_resolve_{id(cursor)}"
            try:
                cursor.execute(f"""
                    CREATE TEMPORARY TABLE {temp_table_name} (
                        DrawingNumber VARCHAR(255) NOT NULL,
                        INDEX idx_drawing (DrawingNumber(100))
                    ) ENGINE=Memory
                """)
                
                drawing_list = list(matched_drawing_numbers)
                chunk_size = 1000
                for i in range(0, len(drawing_list), chunk_size):
                    chunk = drawing_list[i:i + chunk_size]
                    values = ','.join(['(%s)'] * len(chunk))
                    cursor.execute(
                        f"INSERT INTO {temp_table_name} (DrawingNumber) VALUES {values}",
                        tuple(chunk)
                    )
                
                cursor.execute(f"""
                    SELECT DISTINCT wl.SubSystemCode
                    FROM WeldingList wl
                    INNER JOIN {temp_table_name} tmp ON wl.DrawingNumber = tmp.DrawingNumber
                    WHERE wl.SubSystemCode IS NOT NULL
                      AND wl.SubSystemCode <> ''
                """)
                for row in cursor.fetchall():
                    if row.get('SubSystemCode'):
                        codes.add(row['SubSystemCode'])
                
                cursor.execute(f"""
                    SELECT DISTINCT h.SubSystemCode
                    FROM HydroTestPackageList h
                    INNER JOIN WeldingList wl ON wl.TestPackageID = h.TestPackageID
                    INNER JOIN {temp_table_name} tmp2 ON wl.DrawingNumber = tmp2.DrawingNumber
                    WHERE h.SubSystemCode IS NOT NULL
                      AND h.SubSystemCode <> ''
                """)
                for row in cursor.fetchall():
                    if row.get('SubSystemCode'):
                        codes.add(row['SubSystemCode'])
            finally:
                try:
                    cursor.execute(f"DROP TEMPORARY TABLE IF EXISTS {temp_table_name}")
                except:
                    pass
        
        return list(codes)

    matched_blocks = None
    allowed_subsystem_codes = None
    if has_faclist_filters:
        conn = create_connection()
        if conn:
            try:
                cur = conn.cursor(dictionary=True)
                
                # 性能优化：直接使用 Block 字段匹配子系统代码，比通过 DrawingNumber 快得多
                # 1. 从 Faclist 获取 Block
                clauses = []
                params = []
                if filter_subproject:
                    clauses.append("SubProjectCode = %s")
                    params.append(filter_subproject)
                if filter_train:
                    clauses.append("Train = %s")
                    params.append(filter_train)
                if filter_unit:
                    clauses.append("Unit = %s")
                    params.append(filter_unit)
                if filter_simpleblk:
                    clauses.append("SimpleBLK = %s")
                    params.append(filter_simpleblk)
                if filter_mainblock:
                    clauses.append("MainBlock = %s")
                    params.append(filter_mainblock)
                if filter_block:
                    clauses.append("Block = %s")
                    params.append(filter_block)
                if filter_bccquarter:
                    clauses.append("BCCQuarter = %s")
                    params.append(filter_bccquarter)
                
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
                    print(f"[DEBUG][subsystems] 从 Faclist 找到 {len(matched_blocks)} 个 Block", flush=True)
                    
                    if matched_blocks:
                        # 2. 直接使用 Block 字段匹配子系统代码（性能优化：利用 Block 索引）
                        resolve_start = time.time()
                        allowed_subsystem_codes = resolve_subsystem_codes_by_blocks(cur, matched_blocks)
                        print(f"[DEBUG][subsystems] resolve_subsystem_codes_by_blocks 耗时: {time.time() - resolve_start:.2f} 秒，找到 {len(allowed_subsystem_codes) if allowed_subsystem_codes else 0} 个子系统代码", flush=True)
                    else:
                        allowed_subsystem_codes = []
                        matched_blocks = []  # 确保设置为空列表
                        print(f"[DEBUG][subsystems] 没有匹配的 Block，设置 allowed_subsystem_codes = []", flush=True)
            finally:
                conn.close()

    # 获取系统信息（用于显示系统名称等）
    if filter_system and filter_system.strip() and filter_system != '/':
        current_system = SystemModel.get_system_by_code(filter_system)
        systems = [current_system] if current_system else []
    else:
        systems = SystemModel.get_all_systems()

    # 分页参数
    page_str = request.args.get('page', '1')
    try:
        page = int(page_str)
    except ValueError:
        page = 1
    page = max(page, 1)

    # 使用分页查询，只获取当前页的子系统（关键优化！）
    subsystem_query_start = time.time()
    # 使用 allowed_codes 过滤分页，确保只显示符合 Faclist 筛选条件的子系统
    subsystems, total_count, process_count, non_process_count = SubsystemModel.list_subsystems(
        search=search_query or None,
        process_type=filter_type or None,
        system_code=filter_system if (filter_system and filter_system.strip() and filter_system != '/') else None,
        allowed_codes=allowed_subsystem_codes,  # 恢复过滤功能，确保筛选器正确工作
        page=page,
        per_page=PER_PAGE
    )
    print(f"[DEBUG] 分页查询子系统耗时: {time.time() - subsystem_query_start:.2f}秒，获取到 {len(subsystems)} 个子系统（当前页）", flush=True)

    # 从预聚合表加载统计（性能优化：不再实时扫描 WeldingList / HydroTestPackageList）
    stats_start = time.time()
    has_faclist_filters = any([
        filter_subproject, filter_train, filter_unit,
        filter_simpleblk, filter_mainblock, filter_block, filter_bccquarter
    ])
    
    if has_faclist_filters and matched_blocks:
        # Faclist 过滤时：实时计算（仅针对当前页的子系统，直接使用 Block 匹配）
        stats_by_subsystem = load_subsystem_stats_with_faclist(
            [s['SubSystemCode'] for s in subsystems],
            matched_blocks
        )
        print(f"[DEBUG] Faclist 过滤统计耗时: {time.time() - stats_start:.2f} 秒", flush=True)
    else:
        # 无 Faclist 过滤：直接读预聚合表（极快）
        stats_by_subsystem = load_subsystem_stats([s['SubSystemCode'] for s in subsystems], None)
        print(f"[DEBUG] 预聚合表统计耗时: {time.time() - stats_start:.2f} 秒", flush=True)

    default_stats = {
        'total_din': 0.0,
        'completed_din': 0.0,
        'welding_progress': 0.0,
        'total_packages': 0,
        'tested_packages': 0,
        'test_progress': 0.0
    }
    for subsystem in subsystems:
        stats = stats_by_subsystem.get(subsystem['SubSystemCode'], {})
        merged_stats = default_stats.copy()
        merged_stats.update({k: v for k, v in stats.items() if v is not None})
        subsystem['stats'] = merged_stats

    total_pages = max(1, ceil(total_count / PER_PAGE)) if total_count else 1

    pagination_base = build_pagination_base_path(request.args, '/subsystems')
    pagination = {
        'current_page': page,
        'total_pages': total_pages,
        'has_prev': page > 1,
        'has_next': page < total_pages,
        'base_url': pagination_base,
        'prev_url': f"{pagination_base}{page - 1}" if page > 1 else None,
        'next_url': f"{pagination_base}{page + 1}" if page < total_pages else None,
        'start_index': ((page - 1) * PER_PAGE + 1) if total_count else 0,
        'end_index': min(page * PER_PAGE, total_count),
    }
    window_start = max(1, page - 2)
    window_end = min(total_pages, page + 2)
    pagination['window'] = list(range(window_start, window_end + 1))

    total_time = time.time() - total_start
    print(f"[DEBUG] ========== 总耗时: {total_time:.2f}秒 ==========", flush=True)

    return render_template(
        'subsystem_list_industrial.html',
        subsystems=subsystems,
        systems=systems,
        faclist_options=faclist_options,
        search_query=search_query,
        filter_system=filter_system,
        filter_type=filter_type,
        filter_subproject=filter_subproject,
        filter_train=filter_train,
        filter_unit=filter_unit,
        filter_simpleblk=filter_simpleblk,
        filter_mainblock=filter_mainblock,
        filter_block=filter_block,
        filter_bccquarter=filter_bccquarter,
        available_mainblocks=available_mainblocks,
        available_blocks=available_blocks,
        total_count=total_count,
        process_count=process_count,
        non_process_count=non_process_count,
        pagination=pagination,
        active_page='subsystems'
    )

@subsystem_bp.route('/subsystems/filter_options')
def get_filter_options():
    """获取动态筛选选项（AJAX接口）"""
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
    
    mainblocks_list = []
    if filter_simpleblk and filter_simpleblk in options.get('mainblocks', {}):
        mainblocks_list = options['mainblocks'][filter_simpleblk]
    else:
        all_mainblocks = set()
        for mainblocks_list in options.get('mainblocks', {}).values():
            all_mainblocks.update(mainblocks_list)
        mainblocks_list = sorted(all_mainblocks)
    
    blocks_list = []
    if filter_mainblock and filter_mainblock in options.get('blocks', {}):
        blocks_list = options['blocks'][filter_mainblock]
    else:
        all_blocks = set()
        for blocks_list in options.get('blocks', {}).values():
            all_blocks.update(blocks_list)
        blocks_list = sorted(all_blocks)
    
    from flask import jsonify
    return jsonify({
        'subproject_codes': options.get('subproject_codes', []),
        'trains': options.get('trains', []),
        'units': options.get('units', []),
        'simpleblks': options.get('simpleblks', []),
        'mainblocks': mainblocks_list,
        'blocks': blocks_list,
        'bccquarters': options.get('bccquarters', [])
    })

@subsystem_bp.route('/subsystems/api/faclist_options')
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
    
    # 保持 mainblocks 和 blocks 的嵌套结构（前端需要根据 simpleblk/mainblock 来查找）
    # 同时为了兼容性，也提供扁平列表格式
    from flask import jsonify
    return jsonify({
        'subproject_codes': options.get('subproject_codes', []),
        'trains': options.get('trains', []),
        'units': options.get('units', []),
        'simpleblks': options.get('simpleblks', []),
        'mainblocks': options.get('mainblocks', {}),  # 保持嵌套结构：{simpleblk: [mainblocks]}
        'blocks': options.get('blocks', {}),  # 保持嵌套结构：{mainblock: [blocks]}
        'bccquarters': options.get('bccquarters', [])
    })

@subsystem_bp.route('/subsystems/add', methods=['GET', 'POST'])
def add_subsystem():
    """Add subsystem page (industrial UI)"""
    systems = SystemModel.get_all_systems()
    error_message = None

    if request.method == 'POST':
        form_subsystem = {
            'SubSystemCode': (request.form.get('SubSystemCode') or '').strip(),
            'SystemCode': (request.form.get('SystemCode') or '').strip(),
            'SubSystemDescriptionENG': (request.form.get('SubSystemDescriptionENG') or '').strip(),
            'SubSystemDescriptionRUS': (request.form.get('SubSystemDescriptionRUS') or '').strip(),
            'ProcessOrNonProcess': (request.form.get('ProcessOrNonProcess') or '').strip(),
            'Priority': int(request.form.get('Priority', 0) or 0),
            'Remarks': (request.form.get('Remarks') or '').strip()
        }
        subsystem_data = {**form_subsystem, 'created_by': 'admin'}
        if SubsystemModel.create_subsystem(subsystem_data):
            return redirect('/subsystems')
        error_message = 'Failed to create subsystem. Please verify the codes.'
    else:
        form_subsystem = {
            'SubSystemCode': '',
            'SystemCode': '',
            'SubSystemDescriptionENG': '',
            'SubSystemDescriptionRUS': '',
            'ProcessOrNonProcess': '',
            'Priority': 0,
            'Remarks': ''
        }

    return render_template(
        'subsystem_edit_industrial.html',
        mode='create',
        subsystem=form_subsystem,
        systems=systems,
        error_message=error_message,
        active_page='subsystems'
    )

@subsystem_bp.route('/subsystems/edit/<subsystem_code>', methods=['GET', 'POST'])
def edit_subsystem(subsystem_code):
    """Edit subsystem page (industrial UI)"""
    systems = SystemModel.get_all_systems()
    subsystem = SubsystemModel.get_subsystem_by_code(subsystem_code)

    if not subsystem:
        return render_template(
            'subsystem_edit_industrial.html',
            mode='edit',
            subsystem=None,
            systems=systems,
            error_message='Subsystem not found',
            active_page='subsystems'
        ), 404

    if request.method == 'POST':
        update_data = {
            'SystemCode': request.form['SystemCode'],
            'SubSystemDescriptionENG': request.form['SubSystemDescriptionENG'],
            'SubSystemDescriptionRUS': request.form.get('SubSystemDescriptionRUS', ''),
            'ProcessOrNonProcess': request.form['ProcessOrNonProcess'],
            'Priority': int(request.form.get('Priority', 0)),
            'Remarks': request.form.get('Remarks', ''),
            'modified_by': 'admin'
        }
        if SubsystemModel.update_subsystem(subsystem_code, update_data):
            return redirect('/subsystems')
        error_message = 'Failed to update subsystem. Please review the input.'
        subsystem = {**subsystem, **update_data}
        return render_template(
            'subsystem_edit_industrial.html',
            mode='edit',
            subsystem=subsystem,
            systems=systems,
            error_message=error_message,
            active_page='subsystems'
        )

    return render_template(
        'subsystem_edit_industrial.html',
        mode='edit',
        subsystem=subsystem,
        systems=systems,
        error_message=None,
        active_page='subsystems'
    )

@subsystem_bp.route('/subsystems/export')
def export_subsystems():
    """导出子系统数据到Excel"""
    # 复用列表页面的筛选逻辑（简化版，直接调用列表函数获取数据）
    # 这里为了简化，我们直接调用 subsystems() 函数获取数据
    # 但更好的方式是提取公共逻辑
    from flask import current_app
    # 由于需要复用大量逻辑，我们直接在这里实现简化版本
    # 读取筛选参数
    q = (request.args.get('q') or '').strip()
    filter_system = (request.args.get('system_code') or '').strip()
    filter_type = (request.args.get('type') or '').strip()
    filter_subproject = (request.args.get('subproject_code') or '').strip()
    filter_train = (request.args.get('train') or '').strip()
    filter_unit = (request.args.get('unit') or '').strip()
    filter_simpleblk = (request.args.get('simpleblk') or '').strip()
    filter_mainblock = (request.args.get('mainblock') or '').strip()
    filter_block = (request.args.get('block') or '').strip()
    filter_bccquarter = (request.args.get('bccquarter') or '').strip()
    
    all_subsystems = SubsystemModel.get_all_subsystems()
    
    # 获取统计信息（与列表页面相同的逻辑）
    stats_by_subsystem = {}
    conn = create_connection()
    if conn:
        try:
            cur = conn.cursor(dictionary=True)
            matched_drawing_numbers = None
            if filter_subproject or filter_train or filter_unit or filter_simpleblk or filter_mainblock or filter_block or filter_bccquarter:
                faclist_where = []
                faclist_params = []
                
                if filter_subproject:
                    faclist_where.append("SubProjectCode = %s")
                    faclist_params.append(filter_subproject)
                if filter_train:
                    faclist_where.append("Train = %s")
                    faclist_params.append(filter_train)
                if filter_unit:
                    faclist_where.append("Unit = %s")
                    faclist_params.append(filter_unit)
                if filter_simpleblk:
                    faclist_where.append("SimpleBLK = %s")
                    faclist_params.append(filter_simpleblk)
                if filter_mainblock:
                    faclist_where.append("MainBlock = %s")
                    faclist_params.append(filter_mainblock)
                if filter_block:
                    faclist_where.append("Block = %s")
                    faclist_params.append(filter_block)
                if filter_bccquarter:
                    faclist_where.append("BCCQuarter = %s")
                    faclist_params.append(filter_bccquarter)
                
                if faclist_where:
                    faclist_sql = f"""
                        SELECT DISTINCT Block 
                        FROM Faclist 
                        WHERE {' AND '.join(faclist_where)}
                          AND Block IS NOT NULL
                          AND Block <> ''
                    """
                    cur.execute(faclist_sql, tuple(faclist_params))
                    matched_blocks = [row['Block'] for row in cur.fetchall() if row.get('Block')]
                    
                    if matched_blocks:
                        # Block 格式已与 Faclist 一致，直接使用
                        block_patterns = {b.strip() for b in matched_blocks if b and b.strip()}
                        
                        matched_drawing_numbers = fetch_drawings_by_block_patterns(cur, block_patterns)
            
            # 焊接统计
            welding_where_clauses = ["SubSystemCode IS NOT NULL AND SubSystemCode <> ''"]
            welding_params = []
            if matched_drawing_numbers is not None:
                if matched_drawing_numbers:
                    placeholders = ','.join(['%s'] * len(matched_drawing_numbers))
                    welding_where_clauses.append(f"DrawingNumber IN ({placeholders})")
                    welding_params.extend(list(matched_drawing_numbers))
                else:
                    welding_where_clauses = ["1=0"]
            
            welding_where = " AND ".join(welding_where_clauses)
            
            cur.execute(f"""
                SELECT SubSystemCode,
                       COALESCE(SUM(Size), 0) AS total_din,
                       COALESCE(SUM(CASE WHEN WeldDate IS NOT NULL THEN Size ELSE 0 END), 0) AS completed_din
                FROM WeldingList
                WHERE {welding_where}
                GROUP BY SubSystemCode
            """, tuple(welding_params))
            for row in cur.fetchall():
                sub_code = row['SubSystemCode']
                if sub_code not in stats_by_subsystem:
                    stats_by_subsystem[sub_code] = {}
                stats_by_subsystem[sub_code]['total_din'] = float(row['total_din'] or 0)
                stats_by_subsystem[sub_code]['completed_din'] = float(row['completed_din'] or 0)
                stats_by_subsystem[sub_code]['welding_progress'] = (stats_by_subsystem[sub_code]['completed_din'] / stats_by_subsystem[sub_code]['total_din']) if stats_by_subsystem[sub_code]['total_din'] > 0 else 0.0
            
            # 测试统计
            test_where = "h.SubSystemCode IS NOT NULL AND h.SubSystemCode <> ''"
            test_params = []
            if matched_drawing_numbers is not None:
                if matched_drawing_numbers:
                    placeholders = ','.join(['%s'] * len(matched_drawing_numbers))
                    test_where = f"""
                        h.SubSystemCode IS NOT NULL 
                        AND h.SubSystemCode <> ''
                        AND EXISTS (
                            SELECT 1 FROM WeldingList wl
                            WHERE wl.TestPackageID = h.TestPackageID
                              AND wl.DrawingNumber IN ({placeholders})
                        )
                    """
                    test_params.extend(list(matched_drawing_numbers))
                else:
                    test_where = "1=0"
            
            cur.execute(f"""
                SELECT h.SubSystemCode,
                       COUNT(DISTINCT h.TestPackageID) AS total_packages,
                       COUNT(DISTINCT CASE WHEN h.ActualDate IS NOT NULL THEN h.TestPackageID END) AS tested_packages
                FROM HydroTestPackageList h
                WHERE {test_where}
                GROUP BY h.SubSystemCode
            """, tuple(test_params))
            for row in cur.fetchall():
                sub_code = row['SubSystemCode']
                if sub_code not in stats_by_subsystem:
                    stats_by_subsystem[sub_code] = {}
                stats_by_subsystem[sub_code]['total_packages'] = int(row['total_packages'] or 0)
                stats_by_subsystem[sub_code]['tested_packages'] = int(row['tested_packages'] or 0)
                stats_by_subsystem[sub_code]['test_progress'] = (stats_by_subsystem[sub_code]['tested_packages'] / stats_by_subsystem[sub_code]['total_packages']) if stats_by_subsystem[sub_code]['total_packages'] > 0 else 0.0
        finally:
            conn.close()
    
    # 应用筛选
    filtered_subsystems = all_subsystems
    if q:
        filtered_subsystems = [s for s in filtered_subsystems if q.lower() in s['SubSystemCode'].lower() or q.lower() in (s['SubSystemDescriptionENG'] or '').lower()]
    if filter_system:
        filtered_subsystems = [s for s in filtered_subsystems if s['SystemCode'] == filter_system]
    if filter_type:
        filtered_subsystems = [s for s in filtered_subsystems if s['ProcessOrNonProcess'] == filter_type]
    if filter_subproject or filter_train or filter_unit or filter_simpleblk or filter_mainblock or filter_block or filter_bccquarter:
        filtered_subsystems = [s for s in filtered_subsystems if s['SubSystemCode'] in stats_by_subsystem]
    
    # 读取用户选择的列
    selected_columns = request.args.getlist('columns')
    if not selected_columns:
        selected_columns = None  # 如果没有选择，导出所有列
    
    return export_subsystems_to_excel(filtered_subsystems, stats_by_subsystem, selected_columns)

@subsystem_bp.route('/subsystems/delete/<subsystem_code>', methods=['POST'])
def delete_subsystem(subsystem_code):
    """删除子系统"""
    SubsystemModel.delete_subsystem(subsystem_code)
    return redirect('/subsystems')

@subsystem_bp.route('/api/subsystems/autocomplete')
def autocomplete_subsystems():
    """子系统代码自动补齐API"""
    query = (request.args.get('q') or '').strip()
    system_code = (request.args.get('system_code') or '').strip()
    limit = int(request.args.get('limit', 20))
    
    conn = create_connection()
    if not conn:
        return jsonify([])
    
    try:
        cur = conn.cursor(dictionary=True)
        conditions = []
        params = []
        
        if system_code:
            conditions.append("SystemCode = %s")
            params.append(system_code)
        
        if query:
            search_pattern = f"%{query}%"
            conditions.append("(SubSystemCode LIKE %s OR SubSystemDescriptionENG LIKE %s)")
            params.extend([search_pattern, search_pattern])
        
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        
        cur.execute(
            f"""
            SELECT SubSystemCode, SubSystemDescriptionENG, SystemCode
            FROM SubsystemList
            WHERE {where_clause}
            ORDER BY SubSystemCode
            LIMIT %s
            """,
            tuple(params + [limit])
        )
        results = cur.fetchall()
        return jsonify([{
            'code': r['SubSystemCode'],
            'label': f"{r['SubSystemCode']} - {r['SubSystemDescriptionENG'] or ''}",
            'system_code': r['SystemCode']
        } for r in results])
    except Exception as e:
        return jsonify([])
    finally:
        conn.close()