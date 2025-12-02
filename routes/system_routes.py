from flask import Blueprint, request, redirect, render_template, jsonify
from models.system import SystemModel
from database import create_connection
from utils.exporters import export_systems_to_excel
from utils.pipeline_alerts import update_pipeline_alert
from math import ceil
from urllib.parse import urlencode
import re
import time

# 创建蓝图
system_bp = Blueprint('system', __name__)

PER_PAGE = 50


def build_pagination_base_path(args, path='/systems'):
    """构建分页基础URL（保留其他查询参数）"""
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


def resolve_system_codes_by_blocks(cursor, matched_blocks):
    """
    使用 BlockSystemSummary（Block 维度预聚合表）将 Faclist Block 列表映射为 SystemCode 列表。
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
        SELECT DISTINCT SystemCode
        FROM BlockSystemSummary
        WHERE Block IN ({placeholders})
          AND SystemCode IS NOT NULL
          AND SystemCode <> ''
        """,
        tuple(blocks),
    )

    codes = []
    for row in cursor.fetchall():
        sys_code = row.get('SystemCode')
        if sys_code:
            codes.append(sys_code)

    # 如果预聚合表里没有任何匹配，说明 BlockSystemSummary 还没刷新好或者没有覆盖到这些 Block
    # 为了保证功能正确，这里回退到直接从 WeldingList 解析（可能会相对慢一点，但不会返回空结果）
    if not codes:
        print(
            f"[DEBUG][systems] BlockSystemSummary 未命中任何系统代码，回退到 WeldingList 直接匹配（blocks={len(blocks)})",
            flush=True,
        )
        wl_codes = set()
        # 为避免 SQL 过长，对 Block 列表分批处理
        chunk_size = 200
        for i in range(0, len(blocks), chunk_size):
            chunk = blocks[i : i + chunk_size]
            ph = ','.join(['%s'] * len(chunk))
            # 直接从 WeldingList 获取系统代码
            cursor.execute(
                f"""
                SELECT DISTINCT SystemCode
                FROM WeldingList
                WHERE Block IN ({ph})
                  AND SystemCode IS NOT NULL
                  AND SystemCode <> ''
                  AND Block IS NOT NULL
                  AND Block <> ''
                """,
                tuple(chunk),
            )
            for row in cursor.fetchall():
                sys_code = row.get('SystemCode')
                if sys_code:
                    wl_codes.add(sys_code)

            # 再从 HydroTestPackageList 通过 WeldingList 关联获取系统代码
            cursor.execute(
                f"""
                SELECT DISTINCT h.SystemCode
                FROM HydroTestPackageList h
                INNER JOIN WeldingList wl ON wl.TestPackageID = h.TestPackageID
                WHERE wl.Block IN ({ph})
                  AND h.SystemCode IS NOT NULL
                  AND h.SystemCode <> ''
                  AND wl.Block IS NOT NULL
                  AND wl.Block <> ''
                """,
                tuple(chunk),
            )
            for row in cursor.fetchall():
                sys_code = row.get('SystemCode')
                if sys_code:
                    wl_codes.add(sys_code)

        codes = sorted(wl_codes)

    return codes

def resolve_system_codes_for_filters(cursor, matched_drawing_numbers):
    """
    根据匹配到的图纸获取对应的系统代码集合。
    性能优化：如果有 Block 字段，直接使用 Block 匹配（更快），否则使用 DrawingNumber 匹配。
    """
    if matched_drawing_numbers is None:
        return None
    if not matched_drawing_numbers:
        return []
    
    codes = set()
    
    # 性能优化：检查是否有 Block 字段，如果有，直接从 _get_matched_drawing_numbers 获取的 Block patterns 匹配
    # 但这里我们已经有 matched_drawing_numbers，所以还是用 DrawingNumber 匹配
    # 不过可以优化：如果 matched_drawing_numbers 数量很大，使用临时表；如果数量小，直接用 IN
    
    # 如果数量较小，直接用 IN 查询（更快）
    if len(matched_drawing_numbers) <= 500:
        drawing_list = list(matched_drawing_numbers)
        placeholders = ','.join(['%s'] * len(drawing_list))
        
        # 查询 WeldingList
        cursor.execute(f"""
            SELECT DISTINCT SystemCode
            FROM WeldingList
            WHERE SystemCode IS NOT NULL
              AND SystemCode <> ''
              AND DrawingNumber IN ({placeholders})
        """, tuple(drawing_list))
        for row in cursor.fetchall():
            if row.get('SystemCode'):
                codes.add(row['SystemCode'])
        
        # 查询 HydroTestPackageList（通过 WeldingList 关联）
        cursor.execute(f"""
            SELECT DISTINCT h.SystemCode
            FROM HydroTestPackageList h
            INNER JOIN WeldingList wl ON wl.TestPackageID = h.TestPackageID
            WHERE h.SystemCode IS NOT NULL
              AND h.SystemCode <> ''
              AND wl.DrawingNumber IN ({placeholders})
        """, tuple(drawing_list))
        for row in cursor.fetchall():
            if row.get('SystemCode'):
                codes.add(row['SystemCode'])
    else:
        # 数量大时，使用临时表（避免 SQL 语句过长）
        temp_table_name = f"temp_drawings_resolve_{id(cursor)}"
        try:
            cursor.execute(f"""
                CREATE TEMPORARY TABLE {temp_table_name} (
                    DrawingNumber VARCHAR(255) NOT NULL,
                    INDEX idx_drawing (DrawingNumber(100))
                ) ENGINE=Memory
            """)
            
            # 批量插入 drawing numbers（分块插入，每批 1000 个）
            drawing_list = list(matched_drawing_numbers)
            chunk_size = 1000
            for i in range(0, len(drawing_list), chunk_size):
                chunk = drawing_list[i:i + chunk_size]
                values = ','.join(['(%s)'] * len(chunk))
                cursor.execute(
                    f"INSERT INTO {temp_table_name} (DrawingNumber) VALUES {values}",
                    tuple(chunk)
                )
            
            # 查询 WeldingList
            cursor.execute(f"""
                SELECT DISTINCT wl.SystemCode
                FROM WeldingList wl
                INNER JOIN {temp_table_name} tmp ON wl.DrawingNumber = tmp.DrawingNumber
                WHERE wl.SystemCode IS NOT NULL
                  AND wl.SystemCode <> ''
            """)
            for row in cursor.fetchall():
                if row.get('SystemCode'):
                    codes.add(row['SystemCode'])
            
            # 查询 HydroTestPackageList
            cursor.execute(f"""
                SELECT DISTINCT h.SystemCode
                FROM HydroTestPackageList h
                INNER JOIN WeldingList wl ON wl.TestPackageID = h.TestPackageID
                INNER JOIN {temp_table_name} tmp2 ON wl.DrawingNumber = tmp2.DrawingNumber
                WHERE h.SystemCode IS NOT NULL
                  AND h.SystemCode <> ''
            """)
            for row in cursor.fetchall():
                if row.get('SystemCode'):
                    codes.add(row['SystemCode'])
        finally:
            # 清理临时表
            try:
                cursor.execute(f"DROP TEMPORARY TABLE IF EXISTS {temp_table_name}")
            except:
                pass
    
    return list(codes)


def load_system_stats(system_codes, matched_drawing_numbers=None):
    """
    获取指定系统的焊接/试压统计（仅针对当前页）。
    为了性能，这里直接读取预聚合表 SystemWeldingSummary，而不再从 WeldingList / HydroTestPackageList 实时汇总。
    matched_drawing_numbers 目前忽略（用于 Faclist 过滤时，系统列表仍显示全局汇总）。
    """
    stats = {}
    if not system_codes:
        return stats
    conn = create_connection()
    if not conn:
        return stats
    try:
        cur = conn.cursor(dictionary=True)
        code_placeholders = ','.join(['%s'] * len(system_codes))
        cur.execute(
            f"""
            SELECT SystemCode,
                   COALESCE(TotalDIN, 0) AS total_din,
                   COALESCE(CompletedDIN, 0) AS completed_din,
                   COALESCE(TotalPackages, 0) AS total_packages,
                   COALESCE(TestedPackages, 0) AS tested_packages
            FROM SystemWeldingSummary
            WHERE SystemCode IN ({code_placeholders})
            """,
            tuple(system_codes)
        )
        for row in cur.fetchall():
            sys_code = row.get('SystemCode')
            if not sys_code:
                continue
            total_din = float(row['total_din'] or 0)
            completed_din = float(row['completed_din'] or 0)
            total_packages = int(row['total_packages'] or 0)
            tested_packages = int(row['tested_packages'] or 0)
            s = stats.setdefault(sys_code, {})
            s['total_din'] = total_din
            s['completed_din'] = completed_din
            s['welding_progress'] = (completed_din / total_din) if total_din > 0 else 0.0
            s['total_packages'] = total_packages
            s['tested_packages'] = tested_packages
            s['test_progress'] = (tested_packages / total_packages) if total_packages > 0 else 0.0
        return stats
    finally:
        conn.close()


def load_system_stats_with_faclist(system_codes, matched_blocks):
    """
    当启用 Faclist 过滤时，基于 BlockSystemSummary 预聚合表计算当前页系统的统计信息。
    完全避免扫描 WeldingList / HydroTestPackageList。
    """
    stats = {}
    if not system_codes or not matched_blocks:
        return stats

    conn = create_connection()
    if not conn:
        return stats
    try:
        cur = conn.cursor(dictionary=True)
        code_placeholders = ','.join(['%s'] * len(system_codes))

        # Block 格式已与 Faclist 一致，直接使用
        block_list = [b.strip() for b in matched_blocks if b and b.strip()]
        block_list = list(set(block_list))  # 去重
        if not block_list:
            return stats

        block_placeholders = ','.join(['%s'] * len(block_list))

        # 直接在 BlockSystemSummary 上做聚合
        cur.execute(
            f"""
            SELECT
                SystemCode,
                COALESCE(SUM(TotalDIN), 0)       AS total_din,
                COALESCE(SUM(CompletedDIN), 0)   AS completed_din,
                COALESCE(SUM(TotalPackages), 0)  AS total_packages,
                COALESCE(SUM(TestedPackages), 0) AS tested_packages
            FROM BlockSystemSummary
            WHERE SystemCode IN ({code_placeholders})
              AND Block IN ({block_placeholders})
            GROUP BY SystemCode
            """,
            tuple(system_codes) + tuple(block_list),
        )

        for row in cur.fetchall():
            sys_code = row.get('SystemCode')
            if not sys_code:
                continue
            total_din = float(row['total_din'] or 0)
            completed_din = float(row['completed_din'] or 0)
            total_packages = int(row['total_packages'] or 0)
            tested_packages = int(row['tested_packages'] or 0)
            stats[sys_code] = {
                'total_din': total_din,
                'completed_din': completed_din,
                'welding_progress': (completed_din / total_din) if total_din > 0 else 0.0,
                'total_packages': total_packages,
                'tested_packages': tested_packages,
                'test_progress': (tested_packages / total_packages) if total_packages > 0 else 0.0,
            }

        return stats
    finally:
        conn.close()
        
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
    根据 Block 模式列表批量匹配 DrawingNumber。
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
    # 检查 Block 字段是否存在
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
            
            # 批量插入 patterns
            for i in range(0, len(patterns), chunk_size):
                chunk = patterns[i:i + chunk_size]
                values = ','.join(['(%s)'] * len(chunk))
                params = tuple(chunk)
                cursor.execute(
                    f"INSERT INTO {temp_table_name} (pattern) VALUES {values}",
                    params
                )
            
            # 使用 Block 字段直接匹配（等值查询，可以使用索引）
            # 注意：patterns 已经是 Faclist 中的 Block 格式，直接匹配 WeldingList 中的 Block 字段
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

@system_bp.route('/systems')
def systems():
    """系统列表页面（工业化UI）"""
    total_start = time.time()

    search_query = (request.args.get('q') or '').strip()
    filter_type = (request.args.get('type') or '').strip()
    filter_subproject = (request.args.get('subproject_code') or '').strip()
    filter_train = (request.args.get('train') or '').strip()
    filter_unit = (request.args.get('unit') or '').strip()
    filter_simpleblk = (request.args.get('simpleblk') or '').strip()
    filter_mainblock = (request.args.get('mainblock') or '').strip()
    filter_block = (request.args.get('block') or '').strip()
    filter_bccquarter = (request.args.get('bccquarter') or '').strip()
    # 保持原有行为：无论是否使用 Faclist 筛选，都从 Faclist 生成下拉选项（方便选择）
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
    print(f"[DEBUG][systems] Faclist 查询耗时: {time.time() - faclist_start:.2f} 秒", flush=True)

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

    page_str = request.args.get('page', '1')
    try:
        page = int(page_str)
    except ValueError:
        page = 1
    page = max(page, 1)

    def _get_matched_drawing_numbers(cur):
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
        print(f"[DEBUG][_get_matched_drawing_numbers] 从 Faclist 找到 {len(matched_blocks)} 个 Block", flush=True)
        if not matched_blocks:
            return set()

        # Block 格式已与 Faclist 一致，直接使用
        block_patterns = {b.strip() for b in matched_blocks if b and b.strip()}
        
        print(f"[DEBUG][_get_matched_drawing_numbers] 准备匹配的 Block patterns: {list(block_patterns)[:5]}...", flush=True)
        matched_drawings = fetch_drawings_by_block_patterns(cur, block_patterns)
        print(f"[DEBUG][_get_matched_drawing_numbers] 找到 {len(matched_drawings)} 个匹配的图纸号", flush=True)
        return matched_drawings

    matched_blocks = None
    allowed_system_codes = None
    if any([filter_subproject, filter_train, filter_unit, filter_simpleblk, filter_mainblock, filter_block, filter_bccquarter]):
        conn = create_connection()
        if conn:
            try:
                cur = conn.cursor(dictionary=True)
                filters_start = time.time()
                
                # 性能优化：直接使用 Block 字段匹配系统代码，比通过 DrawingNumber 快得多
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
                    print(f"[DEBUG][systems] 从 Faclist 找到 {len(matched_blocks)} 个 Block", flush=True)
                    
                    if matched_blocks:
                        # 2. 直接使用 Block 字段匹配系统代码（性能优化：利用 Block 索引）
                        resolve_start = time.time()
                        allowed_system_codes = resolve_system_codes_by_blocks(cur, matched_blocks)
                        print(f"[DEBUG][systems] resolve_system_codes_by_blocks 耗时: {time.time() - resolve_start:.2f} 秒，找到 {len(allowed_system_codes) if allowed_system_codes else 0} 个系统代码", flush=True)
                    else:
                        allowed_system_codes = []
                        matched_blocks = []  # 确保设置为空列表
                        print(f"[DEBUG][systems] 没有匹配的 Block，设置 allowed_system_codes = []", flush=True)
                else:
                    matched_blocks = []  # 如果没有筛选条件，设置为空列表
                
                print(f"[DEBUG][systems] Faclist -> 系统代码解析耗时: {time.time() - filters_start:.2f} 秒", flush=True)
            finally:
                conn.close()

    list_start = time.time()
    # 使用 allowed_codes 过滤分页，确保只显示符合 Faclist 筛选条件的系统
    systems, total_count, process_count, non_process_count = SystemModel.list_systems(
        search=search_query or None,
        process_type=filter_type or None,
        allowed_codes=allowed_system_codes,  # 恢复过滤功能，确保筛选器正确工作
        page=page,
        per_page=PER_PAGE
    )
    print(f"[DEBUG][systems] SystemList 分页查询耗时: {time.time() - list_start:.2f} 秒，当前页 {len(systems)} 条", flush=True)

    # 从预聚合表加载统计（性能优化：不再实时扫描 WeldingList / HydroTestPackageList）
    stats_start = time.time()
    has_faclist_filters = any([
        filter_subproject, filter_train, filter_unit,
        filter_simpleblk, filter_mainblock, filter_block, filter_bccquarter
    ])
    
    if has_faclist_filters and matched_blocks:
        # Faclist 过滤时：实时计算（仅针对当前页的系统，直接使用 Block 匹配）
        stats_by_system = load_system_stats_with_faclist(
            [s['SystemCode'] for s in systems],
            matched_blocks
        )
        print(f"[DEBUG][systems] Faclist 过滤统计耗时: {time.time() - stats_start:.2f} 秒", flush=True)
    else:
        # 无 Faclist 过滤：直接读预聚合表（极快）
        stats_by_system = load_system_stats([s['SystemCode'] for s in systems], None)
        print(f"[DEBUG][systems] 预聚合表统计耗时: {time.time() - stats_start:.2f} 秒", flush=True)

    default_stats = {
        'total_din': 0.0,
        'completed_din': 0.0,
        'welding_progress': 0.0,
        'total_packages': 0,
        'tested_packages': 0,
        'test_progress': 0.0
    }
    for system in systems:
        stats = stats_by_system.get(system['SystemCode'], {})
        merged_stats = default_stats.copy()
        merged_stats.update({k: v for k, v in stats.items() if v is not None})
        system['stats'] = merged_stats

    total_pages = max(1, ceil(total_count / PER_PAGE)) if total_count else 1
    pagination_base = build_pagination_base_path(request.args, '/systems')
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
    print(f"[DEBUG][systems] ========= /systems 总耗时: {total_time:.2f} 秒 =========", flush=True)

    return render_template(
        'system_list_industrial.html',
        systems=systems,
        faclist_options=faclist_options,
        search_query=search_query,
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
        active_page='systems'
    )


@system_bp.route('/systems/alerts/<int:alert_id>', methods=['POST'])
def handle_pipeline_alert(alert_id):
    data = request.get_json(silent=True) or {}
    action = data.get('action')
    if action not in ('ACKED', 'IGNORED'):
        return jsonify({'success': False, 'message': '无效操作'}), 400
    if update_pipeline_alert(alert_id, action):
        return jsonify({'success': True})
    return jsonify({'success': False, 'message': '更新失败'}), 500
@system_bp.route('/systems/filter_options')
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

@system_bp.route('/api/faclist_options')
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

@system_bp.route('/systems/add', methods=['GET', 'POST'])
def add_system():
    """添加系统页面（工业化UI）"""
    error_message = None
    form_system = {
        'SystemCode': request.form.get('SystemCode', '').strip(),
        'SystemDescriptionENG': request.form.get('SystemDescriptionENG', '').strip(),
        'ProcessOrNonProcess': request.form.get('ProcessOrNonProcess', '').strip(),
        'Priority': int(request.form.get('Priority', 0)) if request.method == 'POST' else 0,
        'Remarks': request.form.get('Remarks', '').strip()
    }
    if request.method == 'POST':
        # 获取表单数据
        system_data = {
            'SystemCode': form_system['SystemCode'],
            'SystemDescriptionENG': form_system['SystemDescriptionENG'],
            'ProcessOrNonProcess': form_system['ProcessOrNonProcess'],
            'Priority': form_system['Priority'],
            'Remarks': form_system['Remarks']
        }
        
        if SystemModel.create_system(system_data):
            return redirect('/systems')
        error_message = "添加系统失败，请检查系统代码是否重复"
    else:
        form_system = {
            'SystemCode': '',
            'SystemDescriptionENG': '',
            'ProcessOrNonProcess': '',
            'Priority': 0,
            'Remarks': ''
        }
    return render_template(
        'system_edit_industrial.html',
        mode='create',
        system=form_system,
        error_message=error_message,
        active_page='systems'
    )

@system_bp.route('/systems/edit/<system_code>', methods=['GET', 'POST'])
def edit_system(system_code):
    """编辑系统页面（工业化UI）"""
    system = SystemModel.get_system_by_code(system_code)
    
    if not system:
        return render_template(
            'system_edit_industrial.html',
            mode='edit',
            system=None,
            error_message="系统不存在",
            active_page='systems'
        ), 404
    
    if request.method == 'POST':
        # 获取表单数据
        update_data = {
            'SystemDescriptionENG': request.form['SystemDescriptionENG'],
            'ProcessOrNonProcess': request.form['ProcessOrNonProcess'],
            'Priority': int(request.form.get('Priority', 0)),
            'Remarks': request.form.get('Remarks', '')
        }
        
        if SystemModel.update_system(system_code, update_data):
            return redirect('/systems')
        error_message = "更新系统失败，请重试"
        system = {**system, **update_data}
        return render_template(
            'system_edit_industrial.html',
            mode='edit',
            system=system,
            error_message=error_message,
            active_page='systems'
        )
    
    return render_template(
        'system_edit_industrial.html',
        mode='edit',
        system=system,
        error_message=None,
        active_page='systems'
    )

@system_bp.route('/systems/export')
def export_systems():
    """导出系统数据到Excel"""
    # 读取筛选参数（与列表页面相同）
    q = (request.args.get('q') or '').strip()
    filter_type = (request.args.get('type') or '').strip()
    filter_subproject = (request.args.get('subproject_code') or '').strip()
    filter_train = (request.args.get('train') or '').strip()
    filter_unit = (request.args.get('unit') or '').strip()
    filter_simpleblk = (request.args.get('simpleblk') or '').strip()
    filter_mainblock = (request.args.get('mainblock') or '').strip()
    filter_block = (request.args.get('block') or '').strip()
    filter_bccquarter = (request.args.get('bccquarter') or '').strip()
    
    # 读取用户选择的列
    selected_columns = request.args.getlist('columns')
    if not selected_columns:
        selected_columns = None  # 如果没有选择，导出所有列
    
    # 获取所有系统并应用筛选（复用列表页面的逻辑）
    all_systems = SystemModel.get_all_systems()
    
    # 从数据库聚合统计信息（与列表页面相同的逻辑）
    stats_by_system = {}
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
            
            welding_where_clauses = ["SystemCode IS NOT NULL AND SystemCode <> ''"]
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
                SELECT SystemCode,
                       COALESCE(SUM(Size), 0) AS total_din,
                       COALESCE(SUM(CASE WHEN WeldDate IS NOT NULL THEN Size ELSE 0 END), 0) AS completed_din
                FROM WeldingList
                WHERE {welding_where}
                GROUP BY SystemCode
            """, tuple(welding_params))
            for row in cur.fetchall():
                sys_code = row['SystemCode']
                if sys_code not in stats_by_system:
                    stats_by_system[sys_code] = {}
                stats_by_system[sys_code]['total_din'] = float(row['total_din'] or 0)
                stats_by_system[sys_code]['completed_din'] = float(row['completed_din'] or 0)
                stats_by_system[sys_code]['welding_progress'] = (stats_by_system[sys_code]['completed_din'] / stats_by_system[sys_code]['total_din']) if stats_by_system[sys_code]['total_din'] > 0 else 0.0
            
            test_where = "h.SystemCode IS NOT NULL AND h.SystemCode <> ''"
            test_params = []
            if matched_drawing_numbers is not None:
                if matched_drawing_numbers:
                    placeholders = ','.join(['%s'] * len(matched_drawing_numbers))
                    test_where = f"""
                        h.SystemCode IS NOT NULL 
                        AND h.SystemCode <> ''
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
                SELECT h.SystemCode,
                       COUNT(DISTINCT h.TestPackageID) AS total_packages,
                       COUNT(DISTINCT CASE WHEN h.ActualDate IS NOT NULL THEN h.TestPackageID END) AS tested_packages
                FROM HydroTestPackageList h
                WHERE {test_where}
                GROUP BY h.SystemCode
            """, tuple(test_params))
            for row in cur.fetchall():
                sys_code = row['SystemCode']
                if sys_code not in stats_by_system:
                    stats_by_system[sys_code] = {}
                stats_by_system[sys_code]['total_packages'] = int(row['total_packages'] or 0)
                stats_by_system[sys_code]['tested_packages'] = int(row['tested_packages'] or 0)
                stats_by_system[sys_code]['test_progress'] = (stats_by_system[sys_code]['tested_packages'] / stats_by_system[sys_code]['total_packages']) if stats_by_system[sys_code]['total_packages'] > 0 else 0.0
        finally:
            conn.close()
    
    # 应用筛选
    filtered_systems = all_systems
    if q:
        filtered_systems = [s for s in filtered_systems if q.lower() in s['SystemCode'].lower() or q.lower() in (s['SystemDescriptionENG'] or '').lower()]
    if filter_type:
        filtered_systems = [s for s in filtered_systems if s['ProcessOrNonProcess'] == filter_type]
    if filter_subproject or filter_train or filter_unit or filter_simpleblk or filter_mainblock or filter_block or filter_bccquarter:
        filtered_systems = [s for s in filtered_systems if s['SystemCode'] in stats_by_system]
    
    return export_systems_to_excel(filtered_systems, stats_by_system, selected_columns)

@system_bp.route('/systems/delete/<system_code>', methods=['POST'])
def delete_system(system_code):
    """删除系统"""
    SystemModel.delete_system(system_code)
    return redirect('/systems')

@system_bp.route('/api/systems/autocomplete')
def autocomplete_systems():
    """系统编码自动补齐API"""
    query = (request.args.get('q') or '').strip()
    limit = int(request.args.get('limit', 20))
    
    conn = create_connection()
    if not conn:
        return jsonify([])
    
    try:
        cur = conn.cursor(dictionary=True)
        if query:
            search_pattern = f"%{query}%"
            cur.execute(
                """
                SELECT SystemCode, SystemDescriptionENG
                FROM SystemList
                WHERE SystemCode LIKE %s OR SystemDescriptionENG LIKE %s
                ORDER BY SystemCode
                LIMIT %s
                """,
                (search_pattern, search_pattern, limit)
            )
        else:
            cur.execute(
                """
                SELECT SystemCode, SystemDescriptionENG
                FROM SystemList
                ORDER BY SystemCode
                LIMIT %s
                """,
                (limit,)
            )
        results = cur.fetchall()
        return jsonify([{
            'code': r['SystemCode'],
            'label': f"{r['SystemCode']} - {r['SystemDescriptionENG'] or ''}"
        } for r in results])
    except Exception as e:
        return jsonify([])
    finally:
        conn.close()