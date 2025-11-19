from flask import Blueprint, request, redirect, render_template
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

def normalize_block_for_matching(block):
    """将 Block 转换为匹配模式
    例如：Block '2200-16150-12' -> '16150-12-2200' (第二部分-第三部分-第一部分)
    """
    if not block:
        return None
    parts = [p.strip() for p in str(block).split('-') if p.strip()]
    if len(parts) == 3:
        return '-'.join([parts[1], parts[2], parts[0]])
    elif len(parts) == 2:
        return '-'.join([parts[1], parts[0]])
    elif len(parts) == 1:
        return parts[0]
    elif len(parts) > 3:
        return '-'.join(parts[1:] + [parts[0]])
    return None


def fetch_drawings_by_block_patterns(cursor, block_patterns, chunk_size=25):
    """根据 block 模式批量匹配 DrawingNumber，避免全表扫描"""
    if not block_patterns:
        return set()
    patterns = [p for p in block_patterns if p]
    if not patterns:
        return set()

    matched = set()
    for i in range(0, len(patterns), chunk_size):
        chunk = patterns[i:i + chunk_size]
        like_clause = " OR ".join(["DrawingNumber LIKE %s"] * len(chunk))
        params = tuple(f"%{pattern}%" for pattern in chunk)
        cursor.execute(
            f"""
            SELECT DISTINCT DrawingNumber
            FROM WeldingList
            WHERE DrawingNumber IS NOT NULL
              AND DrawingNumber <> ''
              AND ({like_clause})
            """,
            params
        )
        for row in cursor.fetchall():
            drawing = row.get('DrawingNumber')
            if drawing:
                matched.add(drawing)
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

    # 优化：如果只有 filter_system 且没有其他筛选条件，可以跳过 Faclist 查询
    has_faclist_filters = any([filter_subproject, filter_train, filter_unit, filter_simpleblk, filter_mainblock, filter_block, filter_bccquarter])
    faclist_start = time.time()
    if has_faclist_filters:
        faclist_options = get_faclist_filter_options(
            filter_subproject=filter_subproject or None,
            filter_train=filter_train or None,
            filter_unit=filter_unit or None,
            filter_simpleblk=filter_simpleblk or None,
            filter_mainblock=filter_mainblock or None,
            filter_block=filter_block or None,
            filter_bccquarter=filter_bccquarter or None
        )
        print(f"[DEBUG] Faclist 查询耗时: {time.time() - faclist_start:.2f}秒", flush=True)
    else:
        # 没有 Faclist 筛选条件时，返回空选项，避免查询 Faclist 表
        faclist_options = {
            'subproject_codes': [],
            'trains': [],
            'units': [],
            'simpleblks': [],
            'mainblocks': {},
            'blocks': {},
            'bccquarters': []
        }
        print(f"[DEBUG] 跳过 Faclist 查询（无筛选条件）", flush=True)

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
        if not matched_blocks:
            return set()
        block_patterns = set()
        for block in matched_blocks:
            pattern = normalize_block_for_matching(block)
            if pattern:
                block_patterns.add(pattern)
        return fetch_drawings_by_block_patterns(cur, block_patterns)

    def resolve_subsystem_codes_for_filters(cursor, matched_drawing_numbers):
        """根据图纸号筛选条件，解析出允许的子系统代码"""
        if not matched_drawing_numbers:
            return None
        codes = set()
        placeholders = ','.join(['%s'] * len(matched_drawing_numbers))
        params = list(matched_drawing_numbers)
        
        cursor.execute(
            f"""
            SELECT DISTINCT SubSystemCode
            FROM WeldingList
            WHERE SubSystemCode IS NOT NULL
              AND SubSystemCode <> ''
              AND DrawingNumber IN ({placeholders})
            """,
            params
        )
        for row in cursor.fetchall():
            if row.get('SubSystemCode'):
                codes.add(row['SubSystemCode'])

        cursor.execute(
            f"""
            SELECT DISTINCT h.SubSystemCode
            FROM HydroTestPackageList h
            WHERE h.SubSystemCode IS NOT NULL
              AND h.SubSystemCode <> ''
              AND EXISTS (
                  SELECT 1 FROM WeldingList wl
                  WHERE wl.TestPackageID = h.TestPackageID
                    AND wl.DrawingNumber IN ({placeholders})
              )
            """,
            params
        )
        for row in cursor.fetchall():
            if row.get('SubSystemCode'):
                codes.add(row['SubSystemCode'])
        return list(codes)

    matched_drawing_numbers = None
    allowed_subsystem_codes = None
    if has_faclist_filters:
        conn = create_connection()
        if conn:
            try:
                cur = conn.cursor(dictionary=True)
                matched_drawing_numbers = get_matched_drawing_numbers(cur)
                allowed_subsystem_codes = resolve_subsystem_codes_for_filters(cur, matched_drawing_numbers) if matched_drawing_numbers else None
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
    subsystems, total_count, process_count, non_process_count = SubsystemModel.list_subsystems(
        search=search_query or None,
        process_type=filter_type or None,
        system_code=filter_system if (filter_system and filter_system.strip() and filter_system != '/') else None,
        allowed_codes=allowed_subsystem_codes,
        page=page,
        per_page=PER_PAGE
    )
    print(f"[DEBUG] 分页查询子系统耗时: {time.time() - subsystem_query_start:.2f}秒，获取到 {len(subsystems)} 个子系统（当前页）", flush=True)

    # 只对当前页的子系统进行统计查询（关键优化！）
    def load_subsystem_stats(subsystem_codes, matched_drawing_numbers=None):
        """获取指定子系统的焊接/试压统计（仅针对当前页）"""
        stats = {}
        if not subsystem_codes:
            return stats
        conn = create_connection()
        if not conn:
            return stats
        try:
            cur = conn.cursor(dictionary=True)
            code_placeholders = ','.join(['%s'] * len(subsystem_codes))

            welding_where = [
                f"SubSystemCode IN ({code_placeholders})",
                "SubSystemCode IS NOT NULL",
                "SubSystemCode <> ''"
            ]
            welding_params = list(subsystem_codes)
            if matched_drawing_numbers is not None:
                if not matched_drawing_numbers:
                    return stats
                drawing_placeholders = ','.join(['%s'] * len(matched_drawing_numbers))
                welding_where.append(f"DrawingNumber IN ({drawing_placeholders})")
                welding_params.extend(list(matched_drawing_numbers))

            cur.execute(
                f"""
                SELECT SubSystemCode, SystemCode,
                       COALESCE(SUM(Size), 0) AS total_din,
                       COALESCE(SUM(CASE WHEN WeldDate IS NOT NULL THEN Size ELSE 0 END), 0) AS completed_din
                FROM WeldingList
                WHERE {' AND '.join(welding_where)}
                GROUP BY SubSystemCode, SystemCode
                """,
                tuple(welding_params)
            )
            for row in cur.fetchall():
                sub_code = row['SubSystemCode']
                if not sub_code:
                    continue
                total_din = float(row['total_din'] or 0)
                completed_din = float(row['completed_din'] or 0)
                stats.setdefault(sub_code, {})
                stats[sub_code]['total_din'] = total_din
                stats[sub_code]['completed_din'] = completed_din
                stats[sub_code]['welding_progress'] = (completed_din / total_din) if total_din > 0 else 0.0
                stats[sub_code]['SystemCode'] = row['SystemCode']

            test_where = [
                f"h.SubSystemCode IN ({code_placeholders})",
                "h.SubSystemCode IS NOT NULL",
                "h.SubSystemCode <> ''"
            ]
            test_params = list(subsystem_codes)
            if matched_drawing_numbers is not None:
                if not matched_drawing_numbers:
                    return stats
                drawing_placeholders = ','.join(['%s'] * len(matched_drawing_numbers))
                test_where.append(
                    f"""
                    EXISTS (
                        SELECT 1 FROM WeldingList wl
                        WHERE wl.TestPackageID = h.TestPackageID
                          AND wl.DrawingNumber IN ({drawing_placeholders})
                    )
                    """
                )
                test_params.extend(list(matched_drawing_numbers))

            cur.execute(
                f"""
                SELECT h.SubSystemCode, h.SystemCode,
                       COUNT(DISTINCT h.TestPackageID) AS total_packages,
                       COUNT(DISTINCT CASE WHEN h.ActualDate IS NOT NULL THEN h.TestPackageID END) AS tested_packages
                FROM HydroTestPackageList h
                WHERE {' AND '.join(test_where)}
                GROUP BY h.SubSystemCode, h.SystemCode
                """,
                tuple(test_params)
            )
            for row in cur.fetchall():
                sub_code = row['SubSystemCode']
                if not sub_code:
                    continue
                stats.setdefault(sub_code, {})
                total_packages = int(row['total_packages'] or 0)
                tested_packages = int(row['tested_packages'] or 0)
                stats[sub_code]['total_packages'] = total_packages
                stats[sub_code]['tested_packages'] = tested_packages
                stats[sub_code]['test_progress'] = (tested_packages / total_packages) if total_packages > 0 else 0.0
                stats[sub_code]['SystemCode'] = row['SystemCode']
            return stats
        finally:
            if conn:
                conn.close()

    # 只对当前页的子系统进行统计查询
    stats_start = time.time()
    stats_by_subsystem = load_subsystem_stats([s['SubSystemCode'] for s in subsystems], matched_drawing_numbers)
    print(f"[DEBUG] 统计查询耗时: {time.time() - stats_start:.2f}秒（仅针对当前页的 {len(subsystems)} 个子系统）", flush=True)

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
                        block_patterns = set()
                        for block in matched_blocks:
                            pattern = normalize_block_for_matching(block)
                            if pattern:
                                block_patterns.add(pattern)
                        
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