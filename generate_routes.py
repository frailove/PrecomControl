# -*- coding: utf-8 -*-
from pathlib import Path

content = """
from flask import Blueprint, request, redirect, jsonify, send_file, render_template
from models.test_package import TestPackageModel
from models.system import SystemModel
from models.subsystem import SubsystemModel
from database import create_connection, ensure_hydro_columns
from utils.exporters import export_test_packages_to_excel
from utils.test_package_exporter import export_test_package_from_template
from utils.test_package_status import TestPackageStatus
from utils.pipeline_alerts import get_pipeline_alerts, update_pipeline_alert
from utils.refresh_aggregated_data import PIPELINE_SYSTEM_SHARE_THRESHOLD, refresh_nde_pwht_status
from urllib.parse import urlencode, unquote
from werkzeug.utils import secure_filename
from math import ceil
from datetime import datetime
import pandas as pd
import os
import re

test_package_bp = Blueprint('test_package', __name__)
PER_PAGE = 50

ATTACHMENT_MODULES = [
    {"code": "3.0", "module": "PID_Drawings", "title": "P&ID Drawings", "description": "Piping & Instrument Diagram"},
    {"code": "4.0", "module": "ISO_Drawings", "title": "Hydro Test ISO", "description": "Hydrostatic test isometrics"},
    {"code": "5.0", "module": "Symbols_Legend", "title": "Symbols Legend", "description": "Legend and abbreviations"},
    {"code": "8.0", "module": "Test_Flow_Chart", "title": "Test Flow Chart", "description": "Test procedure"},
    {"code": "9.0", "module": "Test_Check_List", "title": "Test Check List", "description": "Checklist"},
    {"code": "10.0", "module": "Calibration_Certificates", "title": "Calibration Certificates", "description": "Instrument calibration"},
    {"code": "11.0", "module": "Test_Certificate", "title": "Test Certificate", "description": "Pipeline certificate"},
    {"code": "12.0", "module": "Flushing_Certificate", "title": "Flushing Certificate", "description": "Flushing or cleaning"},
    {"code": "13.0", "module": "Reinstatement_Check_List", "title": "Reinstatement Check List", "description": "Reinstatement"},
    {"code": "14.0", "module": "Others", "title": "Other Attachments", "description": "Additional documents"}
]

REQUIRED_ATTACHMENT_MODULES = [
    "PID_Drawings",
    "ISO_Drawings",
    "Symbols_Legend",
    "Test_Check_List",
    "Calibration_Certificates",
    "Test_Certificate"
]

UPLOAD_FOLDER = 'uploads/test_packages'
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'dwg', 'dxf', 'xlsx', 'xls', 'doc', 'docx', 'zip'}

PUNCH_HEADER_MAP = {
    'punchno': 'PunchNo',
    'itemno': 'PunchNo',
    'punch no': 'PunchNo',
    'iso': 'ISODrawingNo',
    'iso/tag': 'ISODrawingNo',
    'sheetno': 'SheetNo',
    'revno': 'RevNo',
    'description': 'Description',
    'description of punch': 'Description',
    'category': 'Category',
    'cause': 'Cause',
    'issuedby': 'IssuedBy',
    'rectified': 'Rectified',
    'rectifieddate': 'RectifiedDate',
    'verified': 'Verified',
    'verifieddate': 'VerifiedDate',
    'remarks': 'Remarks',
    'testpackageid': 'TestPackageID'
}

def ensure_punch_list_schema():
    conn = create_connection()
    if not conn:
        return
    try:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS PunchListImportLog (
                ImportID INT AUTO_INCREMENT PRIMARY KEY,
                TestPackageID VARCHAR(50) NOT NULL,
                FileName VARCHAR(255),
                TotalCount INT DEFAULT 0,
                InsertedCount INT DEFAULT 0,
                UpdatedCount INT DEFAULT 0,
                ErrorCount INT DEFAULT 0,
                Message TEXT,
                CreatedAt DATETIME DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_punch_import_tp (TestPackageID)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )
        cur.execute(
            """
            SELECT COUNT(*)
            FROM information_schema.columns
            WHERE table_schema = DATABASE()
              AND table_name = 'PunchList'
              AND column_name = 'PunchNo'
            """
        )
        if cur.fetchone()[0] == 0:
            cur.execute("ALTER TABLE PunchList ADD COLUMN PunchNo VARCHAR(100) NULL AFTER ID")
        cur.execute("SHOW INDEX FROM PunchList WHERE Key_name = 'idx_punch_no'")
        if cur.fetchone() is None:
            cur.execute("ALTER TABLE PunchList ADD INDEX idx_punch_no (PunchNo)")
    except Exception as exc:
        print(f"ensure_punch_list_schema failed: {exc}")
    finally:
        conn.close()


ensure_punch_list_schema()


def normalize_header(value):
    if value is None:
        return ''
    if not isinstance(value, str):
        value = str(value)
    return value.splitlines()[0].strip().lower()


def parse_flag(value):
    if value is None:
        return 'N'
    v = str(value).strip().upper()
    if v in {'Y', 'YES', '1'}:
        return 'Y'
    if v in {'N', 'NO', '0', ''}:
        return 'N'
    return None


def parse_datetime(value):
    if value in (None, ''):
        return None
    dt = pd.to_datetime(value, errors='coerce')
    if pd.isna(dt):
        return None
    return dt.to_pydatetime()


def sanitize_date_columns(df, columns):
    for col in columns:
        if col in df.columns:
            series = pd.to_datetime(df[col], errors='coerce')
            df[col] = series.dt.strftime('%Y-%m-%d')
            df[col] = df[col].where(series.notna(), None)


def extract_drawing_pattern(drawing_number):
    if not drawing_number:
        return None
    parts = re.findall(r'\d+', drawing_number)
    if len(parts) >= 3:
        return '-'.join(parts[:3])
    if len(parts) == 2:
        return '-'.join(parts)
    if len(parts) == 1:
        return parts[0]
    return None


def normalize_block_for_matching(block):
    if not block:
        return None
    parts = [p.strip() for p in str(block).split('-') if p.strip()]
    if len(parts) == 3:
        return '-'.join([parts[1], parts[2], parts[0]])
    if len(parts) == 2:
        return '-'.join([parts[1], parts[0]])
    if len(parts) == 1:
        return parts[0]
    if len(parts) > 3:
        return '-'.join(parts[1:] + [parts[0]])
    return None


def fetch_drawings_by_block_patterns(cursor, block_patterns, chunk_size=25):
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
    conn = create_connection()
    if not conn:
        return {}

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

    where_sql = " AND ".join(clauses) if clauses else "1=1"

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
        cur.execute(
            f"""
            SELECT DISTINCT SubProjectCode, Train, Unit, SimpleBLK, MainBlock, Block, BCCQuarter
            FROM Faclist
            WHERE ({where_sql})
              AND (SubProjectCode IS NOT NULL OR Train IS NOT NULL OR Unit IS NOT NULL
                   OR SimpleBLK IS NOT NULL OR MainBlock IS NOT NULL OR Block IS NOT NULL OR BCCQuarter IS NOT NULL)
            ORDER BY SubProjectCode, Train, Unit, SimpleBLK, MainBlock, Block, BCCQuarter
            """,
            tuple(params)
        )
        for row in cur.fetchall():
            if row.get('SubProjectCode') and row['SubProjectCode'] not in options['subproject_codes']:
                options['subproject_codes'].append(str(row['SubProjectCode']))
            if row.get('Train') and row['Train'] not in options['trains']:
                options['trains'].append(str(row['Train']))
            if row.get('Unit') and row['Unit'] not in options['units']:
                options['units'].append(str(row['Unit']))
            if row.get('SimpleBLK') and row['SimpleBLK'] not in options['simpleblks']:
                options['simpleblks'].append(str(row['SimpleBLK']))
            if row.get('BCCQuarter') and row['BCCQuarter'] not in options['bccquarters']:
                options['bccquarters'].append(str(row['BCCQuarter']))

            if row.get('SimpleBLK'):
                simpleblk = str(row['SimpleBLK'])
                options['mainblocks'].setdefault(simpleblk, [])
                if row.get('MainBlock') and str(row['MainBlock']) not in options['mainblocks'][simpleblk]:
                    options['mainblocks'][simpleblk].append(str(row['MainBlock']))

            if row.get('MainBlock'):
                mainblock = str(row['MainBlock'])
                options['blocks'].setdefault(mainblock, [])
                if row.get('Block') and str(row['Block']) not in options['blocks'][mainblock]:
                    options['blocks'][mainblock].append(str(row['Block']))

        options['subproject_codes'].sort()
        options['trains'].sort()
        options['units'].sort()
        options['simpleblks'].sort()
        options['bccquarters'].sort()
        for mainblock in options['blocks']:
            options['blocks'][mainblock].sort(
                key=lambda x: tuple(int(p) if p.isdigit() else 999999 for p in x.split('-')) if '-' in x else (int(x) if x.isdigit() else 999999)
            )
    finally:
        conn.close()

    return options


def get_bootstrap_css():
    return '<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">'


def get_navbar():
    return '''
    <nav class="navbar navbar-expand-lg navbar-dark bg-dark">
        <div class="container-fluid">
            <a class="navbar-brand" href="/">Pre-commissioning Suite</a>
            <div class="navbar-nav">
                <a class="nav-link" href="/">Home</a>
                <a class="nav-link" href="/systems">Systems</a>
                <a class="nav-link" href="/subsystems">Subsystems</a>
                <a class="nav-link" href="/test_packages">Test Packages</a>
            </div>
        </div>
    </nav>
    '''

... (rest of file omitted for brevity) ...
"""

Path('routes/test_package_routes.py').write_text(content, encoding='utf-8')
