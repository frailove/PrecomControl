import pandas as pd
import os
from pathlib import Path
from datetime import datetime
import re
from database import create_welding_table
from database import create_connection
from mysql.connector import Error
import tempfile
import csv
import math
import time
import logging

DATE_PATTERN = re.compile(r'^\d{4}-\d{2}-\d{2}$')

def resolve_welding_files(path_or_dir):
    """
    根据用户输入寻找实际的焊接数据文件
    - 支持传入单个文件
    - 支持传入目录，自动枚举目录下所有 WeldingDB_*.xlsx
    - 支持通配符
    返回路径字符串列表，按文件名排序
    """
    if not path_or_dir:
        return []
    path_obj = Path(path_or_dir)
    if path_obj.is_file():
        return [str(path_obj)]
    if path_obj.is_dir():
        candidates = sorted(path_obj.glob("WeldingDB_*.xlsx"))
        return [str(p) for p in candidates]
    # 允许直接传 pattern
    matches = sorted(Path(path_obj.parent).glob(path_obj.name))
    return [str(p) for p in matches]


class WeldingDataImporter:
    # Excel列名到数据库列名的映射
    EXCEL_COLUMNS = {
        '施工承包商': 'ConstContractor',
        '介质':'SystemCode',
        '子系统':'SubSystemCode',
        '图纸号':'DrawingNumber',
        '版本号':'RevNo',
        '页码':'PageNumber',
        '管线号':'PipelineNumber', 
        '流程图号':'PIDDrawingNumber',
        '管道材料等级':'PipingMaterialClass',
        '压力等级':'PressureClass',
        '介质级别':'MediumLevel',
        '管段号':'SpoolNo',
        '焊缝编号': 'WeldJoint',
        '安装/F预制/S':'JointTypeFS',
        '设计比例':'NDTDesignRatio',
        '母材材质1':'Material1',
        '母材材质2':'Material2',
        '外径1':'OuterDiameter1',
        '外径2':'OuterDiameter2',
        '厚度1':'SCH1',
        '厚度2':'SCH2',
        '焊接类型':'WeldingType',
        '接头类型(俄标)':'WeldJointTypeRUS',
        'WPS编号':'WPSNumber',
        '焊接方法(根层)':'WeldMethodRoot',
        '焊接方法(填充、盖面)':'WeldMethodCover',
        '焊接环境温度℃':'WeldEnvironmentTemperature',
        '焊工号根层':'WelderRoot',
        '焊工号填充、盖面':'WelderFill',
        '是否热处理':'IsHeatTreatment',
        '热处理日期':'HeatTreatmentDate',
        '热处理报告号':'HeatTreatmentReportNumber',
        '热处理工':'HeatTreatmentWorker',
        '试压包号': 'TestPackageID',
        '焊接日期': 'WeldDate',
        '尺寸': 'Size',
        'VT报告号':'VTReportNumber',
        'VT报告日期':'VTReportDate',
        'VT检测结果': 'VTResult',
        'RT报告号':'RTReportNumber',
        'RT报告日期':'RTReportDate',
        'RT检测结果': 'RTResult',
        'PT报告号':'PTReportNumber',
        'PT报告日期':'PTReportDate',
        'PT检测结果': 'PTResult',
        'UT报告号':'UTReportNumber',
        'UT报告日期':'UTReportDate',
        'UT检测结果': 'UTResult',
        'MT报告号':'MTReportNumber',
        'MT报告日期':'MTReportDate',
        'MT检测结果': 'MTResult',
        'PMI报告号':'PMIReportNumber',
        'PMI报告日期':'PMIReportDate',
        'PMI检测结果': 'PMIResult',
        'FT报告号':'FTReportNumber',
        'FT报告日期':'FTReportDate',
        'FT检测结果': 'FTResult',
        'HT报告号':'HTReportNumber',
        'HT报告日期':'HTReportDate',
        'HT检测结果':'HTResult',
        'PWHT报告号':'PWHTReportNumber',
        'PWHT报告日期':'PWHTReportDate',
        'PWHT检测结果':'PWHTResult',
        '焊口状态':'JointStatus'
    }
    DATE_SOURCE_COLUMNS = [
        '焊接日期',
        '热处理日期',
        'VT报告日期',
        'RT报告日期',
        'PT报告日期',
        'UT报告日期',
        'MT报告日期',
        'PMI报告日期',
        'FT报告日期',
        'HT报告日期',
        'PWHT报告日期'
    ]
    
    CHUNK_SIZE = 50000  # 导入分片大小

    def __init__(self, excel_path, verbose=False):
        self.excel_files = resolve_welding_files(excel_path)
        if not self.excel_files:
            raise FileNotFoundError(f"未找到焊接数据文件: {excel_path}")
        self.excel_path = self.excel_files[0]
        self.df = None
        self.verbose = verbose
        self.invalid_date_records = []
        self.load_data()
    
    def load_data(self):
        """加载Excel数据（参考原加载逻辑）"""
        try:
            data_frames = []
            total_rows = 0
            self.invalid_date_records = []
            for idx, excel_file in enumerate(self.excel_files, start=1):
                if not os.path.exists(excel_file):
                    print(f"WARNING: File not found: {excel_file}")
                    continue
                raw_df = pd.read_excel(excel_file, header=1, dtype=str)
                raw_df = raw_df.where(raw_df.notna(), None)
                normalized_columns = []
                for col in raw_df.columns:
                    if isinstance(col, str):
                        first_line = col.splitlines()[0].strip()
                        normalized_columns.append(first_line)
                    else:
                        normalized_columns.append(col)
                raw_df.columns = normalized_columns
                for date_col in self.DATE_SOURCE_COLUMNS:
                    self._collect_invalid_dates(raw_df, date_col, os.path.basename(excel_file))
                data_frames.append(raw_df)
                total_rows += len(raw_df)
                print(f"SUCCESS: Loaded {len(raw_df)} rows from welding data ({os.path.basename(excel_file)})")
            if data_frames:
                self.df = pd.concat(data_frames, ignore_index=True)
                print(f"📈 合计加载焊口数据 {total_rows} 行，来源文件 {len(data_frames)} 个")
                if self.verbose:
                    print("Excel column mapping:")
                    for excel_col, db_col in self.EXCEL_COLUMNS.items():
                        if excel_col in self.df.columns:
                            print(f"  '{excel_col}' -> '{db_col}'")
                        else:
                            print(f"  WARNING: Column not found: '{excel_col}'")
                self._write_invalid_date_log()
            else:
                print("ERROR: 未成功读取任何焊接数据文件")
                self.df = pd.DataFrame()
        except Exception as e:
            print(f"ERROR: Failed to load Excel: {e}")
            self.df = pd.DataFrame()

    def _collect_invalid_dates(self, df, column_name, source_file):
        if column_name not in df.columns:
            return
        series = df[column_name]
        for idx, val in series.items():
            if val is None or (isinstance(val, float) and math.isnan(val)):
                continue
            text = str(val).strip()
            if not text or text.lower() in {'nan', 'nat', 'none', 'null'}:
                continue
            if DATE_PATTERN.match(text):
                continue
            self.invalid_date_records.append({
                'SourceFile': source_file,
                'Column': column_name,
                'ExcelRow': idx + 2,  # header=1 数据从第2行开始
                'RawValue': text
            })

    def _write_invalid_date_log(self):
        if not self.invalid_date_records:
            return
        out_path = Path(self.excel_path).parent / 'invalid_weld_dates.csv'
        try:
            pd.DataFrame(self.invalid_date_records).to_csv(out_path, index=False, encoding='utf-8-sig')
            print(f"[WARN] 检测到 {len(self.invalid_date_records)} 个非标准日期值，详见 {out_path}")
        except Exception as log_error:
            print(f"[WARN] 写入 invalid_weld_dates.csv 失败: {log_error}")
    
    def _retry_connection(self, max_retries=5, initial_delay=2, max_delay=60):
        """
        重试获取数据库连接
        max_retries: 最大重试次数
        initial_delay: 初始延迟（秒）
        max_delay: 最大延迟（秒，指数退避上限）
        """
        delay = initial_delay
        for attempt in range(max_retries):
            try:
                connection = create_connection()
                if connection and connection.is_connected():
                    if attempt > 0:
                        print(f"✅ 连接成功（第 {attempt + 1} 次尝试）")
                    return connection
            except Exception as e:
                if attempt < max_retries - 1:
                    print(f"⚠️  连接失败（尝试 {attempt + 1}/{max_retries}）: {e}，{delay}秒后重试...")
                    time.sleep(delay)
                    delay = min(delay * 2, max_delay)  # 指数退避
                else:
                    print(f"❌ 连接失败（已重试 {max_retries} 次）: {e}")
        return None
    
    def _retry_execute(self, connection, cursor, sql, max_retries=5, initial_delay=2, max_delay=60):
        """
        重试执行SQL语句
        """
        delay = initial_delay
        for attempt in range(max_retries):
            try:
                # 检查连接是否有效
                if not connection.is_connected():
                    print(f"⚠️  连接已断开，尝试重新连接...")
                    connection.close()
                    connection = self._retry_connection()
                    if not connection:
                        raise Error("无法重新建立连接")
                    cursor = connection.cursor()
                
                cursor.execute(sql)
                return True, connection, cursor
            except Error as e:
                error_msg = str(e)
                # 判断是否为可重试的错误
                is_retryable = any(keyword in error_msg.lower() for keyword in [
                    'lost connection', 'connection', 'timeout', 'gone away', 
                    'server has gone away', 'broken pipe', 'network'
                ])
                
                if is_retryable and attempt < max_retries - 1:
                    print(f"⚠️  SQL执行失败（尝试 {attempt + 1}/{max_retries}）: {e}，{delay}秒后重试...")
                    time.sleep(delay)
                    delay = min(delay * 2, max_delay)  # 指数退避
                    
                    # 尝试重新连接
                    try:
                        connection.close()
                    except:
                        pass
                    connection = self._retry_connection()
                    if connection:
                        cursor = connection.cursor()
                else:
                    raise
        return False, connection, cursor
    
    def import_to_database(self):
        """将数据导入数据库（带重试机制）"""
        if self.df is None or self.df.empty:
            print("ERROR: No data to import")
            return False
        
        # 使用重试机制获取连接
        connection = self._retry_connection()
        if not connection:
            print("ERROR: 无法建立数据库连接，已重试多次")
            return False
        
        cursor = None
        try:
            cursor = connection.cursor()
            checks_disabled = False
            try:
                cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
                cursor.execute("SET UNIQUE_CHECKS = 0")
                checks_disabled = True
            except Exception:
                pass
            # 清空表（可选，根据需求决定是否保留历史数据）
            cursor.execute("TRUNCATE TABLE WeldingList")
            # 目标列顺序（与表结构一致且仅包含实际需要列）
            target_columns = [
                # 基础信息
                'WeldID', 'ConstContractor', 'SystemCode', 'SubSystemCode', 'WeldJoint', 'JointTypeFS',
                'DrawingNumber', 'PageNumber', 'RevNo', 'PID', 'PIDDrawingNumber',
                # 管道材料信息
                'PipingMaterialClass', 'PressureClass', 'MediumLevel', 'SpoolNo', 'NDTDesignRatio',
                'Material1', 'Material2', 'OuterDiameter1', 'OuterDiameter2', 'SCH1', 'SCH2',
                # 焊接信息
                'WeldingType', 'WeldJointTypeRUS', 'PipelineNumber', 'TestPackageID', 'WeldDate', 'Size',
                # 焊工和WPS
                'WelderRoot', 'WelderFill', 'WPSNumber', 'WeldMethodRoot', 'WeldMethodCover', 'WeldEnvironmentTemperature',
                # 热处理
                'IsHeatTreatment', 'HeatTreatmentDate', 'HeatTreatmentReportNumber', 'HeatTreatmentWorker',
                # VT检测
                'VTReportNumber', 'VTReportDate', 'VTResult',
                # RT检测
                'RTReportNumber', 'RTReportDate', 'RTResult',
                # UT检测
                'UTReportNumber', 'UTReportDate', 'UTResult',
                # PT检测
                'PTReportNumber', 'PTReportDate', 'PTResult',
                # HT检测
                'HTReportNumber', 'HTReportDate', 'HTResult',
                # PWHT检测
                'PWHTReportNumber', 'PWHTReportDate', 'PWHTResult',
                # MT检测
                'MTReportNumber', 'MTReportDate', 'MTResult',
                # PMI检测
                'PMIReportNumber', 'PMIReportDate', 'PMIResult',
                # FT检测
                'FTReportNumber', 'FTReportDate', 'FTResult',
                # 状态
                'Status', 'JointStatus'
            ]

            # 从原始DataFrame生成有效记录的数据框
            df = self.df.copy()

            # 统一处理所有文本字段（使用excel_columns映射）
            def extract_text_field(df, excel_col_name, default=''):
                """从Excel列提取文本字段"""
                if excel_col_name in df.columns:
                    return df[excel_col_name].astype(str).str.strip()
                else:
                    return default
            
            # 提取所有字段
            for excel_col, db_col in self.EXCEL_COLUMNS.items():
                if excel_col not in ['焊接日期', '热处理日期'] and 'date' not in excel_col.lower():  # 日期字段单独处理
                    df[db_col] = extract_text_field(df, excel_col)
            
            # WelderFill已在统一提取中处理
            
            # 如果某些字段不在映射中，手动添加
            if 'PID' not in df.columns:
                df['PID'] = ''
            # WeldID = DrawingNumber-PipelineNumber-WeldJoint；若三者皆空，则生成 AUTO-<index>
            def compose_weld_id(r):
                parts = [r['DrawingNumber'], r['PageNumber'], r['PipelineNumber'], r['WeldJoint']]
                parts = [p for p in parts if p]
                return '-'.join(parts) if parts else 'AUTO-' + str(r.name)
            df['WeldID'] = df.apply(compose_weld_id, axis=1)

            # 预测有效行数
            predicted_rows = len(df)

            # 列映射与转换
            df['TestPackageID'] = df['试压包号'].astype(str).str.strip() if '试压包号' in df.columns else ''
            df['SystemCode'] = df['介质'].astype(str).str.strip() if '介质' in df.columns else 'UNDEFINED'
            df['SystemCode'] = df['SystemCode'].apply(
                lambda x: x if x and str(x).strip().lower() not in {'nan', 'none', 'null'} else 'UNDEFINED'
            )
            df['SubSystemCode'] = df['子系统'].astype(str).str.strip() if '子系统' in df.columns else ''

            def ensure_subsystem(row):
                subsystem = row.get('SubSystemCode')
                if subsystem:
                    return subsystem
                if row.get('SystemCode'):
                    return f"{row['SystemCode']}_UNDEFINED"
                if row.get('TestPackageID'):
                    return f"{row['TestPackageID']}_UNDEFINED"
                return "UNDEFINED"

            df['SubSystemCode'] = df.apply(ensure_subsystem, axis=1)

            # 先根据Excel数据填充系统/子系统/试压包主数据（如不存在则插入，占位描述后续维护）
            try:
                unique_systems = sorted(set([c for c in df['SystemCode'].tolist() if c]))
                if unique_systems:
                    sys_values = [(sc, sc, None, 'Process', 0, '', 'admin', 'admin') for sc in unique_systems]
                    cursor.executemany(
                        """
                        INSERT IGNORE INTO SystemList
                        (SystemCode, SystemDescriptionENG, SystemDescriptionRUS, ProcessOrNonProcess, Priority, Remarks, created_by, last_updated_by)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                        """,
                        sys_values
                    )
                    connection.commit()  # 立即提交
                    
                unique_subs = set()
                for _, r in df[['SubSystemCode','SystemCode']].drop_duplicates().iterrows():
                    scode = str(r['SystemCode']).strip()
                    sub = str(r['SubSystemCode']).strip()
                    if scode and sub:
                        unique_subs.add((sub, scode))
                if unique_subs:
                    sub_values = [(sub, sysc, sub, None, 'Process', 0, '', 'admin', 'admin') for (sub, sysc) in unique_subs]
                    cursor.executemany(
                        """
                        INSERT IGNORE INTO SubsystemList
                        (SubSystemCode, SystemCode, SubSystemDescriptionENG, SubSystemDescriptionRUS, ProcessOrNonProcess, Priority, Remarks, created_by, last_updated_by)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        """,
                        sub_values
                    )
                    connection.commit()  # 立即提交
                    
                unique_tps = set()
                for _, r in df[['TestPackageID','SystemCode','SubSystemCode']].drop_duplicates().iterrows():
                    tpid = str(r['TestPackageID']).strip()
                    scode = str(r['SystemCode']).strip()
                    sub = str(r['SubSystemCode']).strip()
                    if tpid:
                        unique_tps.add((tpid, scode if scode else None, sub if sub else None))
                if unique_tps:
                    tp_values = [(tpid, scode, sub, tpid, None, None, 'Pending', None, None, '', 'admin', 'admin') for (tpid, scode, sub) in unique_tps]
                    cursor.executemany(
                        """
                        INSERT IGNORE INTO HydroTestPackageList
                        (TestPackageID, SystemCode, SubSystemCode, Description, PlannedDate, ActualDate, Status, Pressure, TestDuration, Remarks, created_by, last_updated_by)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        """,
                        tp_values
                    )
                    connection.commit()  # 立即提交
                    
            except Exception as seed_e:
                if self.verbose:
                    print(f"WARNING: Failed to seed master data: {seed_e}")

            # 日期标准化为YYYY-MM-DD
            def to_date_str(v):
                if v is None or (isinstance(v, float) and math.isnan(v)):
                    return None
                text = str(v).strip()
                if text == '' or text.lower() in {'nan', 'nat', 'none', 'null'}:
                    return None
                if DATE_PATTERN.match(text):
                    return text
                dt = pd.to_datetime(text, errors='coerce')
                if pd.isna(dt):
                    return None
                formatted = dt.strftime('%Y-%m-%d')
                return formatted if DATE_PATTERN.match(formatted) else None
            
            # 处理所有日期字段
            date_field_mapping = {
                '焊接日期': 'WeldDate',
                '热处理日期': 'HeatTreatmentDate',
                'VT报告日期': 'VTReportDate',
                'RT报告日期': 'RTReportDate',
                'PT报告日期': 'PTReportDate',
                'UT报告日期': 'UTReportDate',
                'MT报告日期': 'MTReportDate',
                'PMI报告日期': 'PMIReportDate',
                'FT报告日期': 'FTReportDate',
                'HT报告日期': 'HTReportDate',
                'PWHT报告日期': 'PWHTReportDate'
            }
            
            for excel_col, db_col in date_field_mapping.items():
                if excel_col in df.columns:
                    df[db_col] = df[excel_col].apply(to_date_str)
                else:
                    df[db_col] = None
            date_cols = list(date_field_mapping.values())

            def normalize_date_series(series):
                if series is None:
                    return None
                def _normalize(val):
                    if val is None or (isinstance(val, float) and math.isnan(val)):
                        return None
                    text = str(val).strip()
                    if text == '' or text.lower() in {'nan', 'nat', 'none', 'null'}:
                        return None
                    if DATE_PATTERN.match(text):
                        return text
                    dt = pd.to_datetime(text, errors='coerce')
                    if pd.isna(dt):
                        return None
                    formatted = dt.strftime('%Y-%m-%d')
                    return formatted if DATE_PATTERN.match(formatted) else None
                return series.apply(_normalize)

            for db_col in date_cols:
                df[db_col] = normalize_date_series(df.get(db_col))

            # 尺寸为数值或NULL
            def to_size(v):
                try:
                    return float(v)
                except Exception:
                    return None
            df['Size'] = df['尺寸'].apply(lambda v: to_size(v) if pd.notna(v) else None)

            # 检测结果字段
            def to_str_series(column_name: str):
                if column_name in df.columns:
                    s = df[column_name]
                    s = s.where(pd.notna(s), '')  # NaN -> ''
                    return s.astype(str).str.strip()
                else:
                    return pd.Series([''] * len(df))

            for cn, en in [
                ('VT检测结果', 'VTResult'),
                ('RT检测结果', 'RTResult'),
                ('UT检测结果', 'UTResult'),
                ('PT检测结果', 'PTResult'),
                ('HT检测结果', 'HTResult'),
                ('PWHT检测结果', 'PWHTResult'),
                ('MT检测结果', 'MTResult'),
                ('PMI检测结果', 'PMIResult'),
                ('FT检测结果', 'FTResult'),
            ]:
                df[en] = to_str_series(cn)

            # 焊工/WPS 字段已在统一提取中处理

            # 额外派生列：测试（不写入数据库，仅用于统计/校验）
            test_source_cols = ['VT检测结果', 'RT检测结果', 'UT检测结果', 'PT检测结果', 'HT检测结果', 'PWHT检测结果', 'MT检测结果', 'PMI检测结果', 'FT检测结果']
            def derive_test_status(row):
                for c in test_source_cols:
                    v = row.get(c)
                    if pd.notna(v) and str(v).strip() != '':
                        return '已完成'
                return '未完成'
            df['测试'] = df.apply(derive_test_status, axis=1)

            # 状态：所有测试结果均为"合格"时标记为已完成，否则未完成
            def evaluate_status(row):
                cols = ['VTResult', 'RTResult', 'UTResult', 'PTResult', 'HTResult', 'PWHTResult', 'MTResult', 'PMIResult', 'FTResult']
                values = [str(row.get(c) or '').strip() for c in cols]
                non_empty = [v for v in values if v != '']
                # 只要有一个非空且不为"合格"，即未完成
                if any(v != '合格' for v in non_empty):
                    return '未完成'
                # 没有不合格，且至少一个为"合格"，则已完成
                if any(v == '合格' for v in non_empty):
                    return '已完成'
                # 全部为空
                return '未完成'
            df['Status'] = df.apply(evaluate_status, axis=1)

            # 仅保留目标列顺序
            export_df = df[target_columns]

            # 将所有字符串列的空字符串标准化为 NULL（以写出为 \\N）
            for col in export_df.columns:
                if export_df[col].dtype == 'object':  # 字符串类型列
                    export_df.loc[:, col] = export_df[col].apply(
                        lambda x: None if (isinstance(x, str) and x.strip() in ['', 'nan', 'NaN', 'None']) else x
                    )
            date_regex = DATE_PATTERN.pattern
            for date_col in date_cols:
                if date_col in export_df.columns:
                    export_df.loc[:, date_col] = normalize_date_series(export_df[date_col])
                    series = export_df[date_col]
                    value_str = series.astype(str)
                    invalid_mask = series.notna() & ~value_str.str.fullmatch(date_regex)
                    if invalid_mask.any():
                        sample_values = value_str[invalid_mask].head(3).tolist()
                        sample_ids = export_df.loc[invalid_mask, 'WeldID'].head(3).tolist() if 'WeldID' in export_df.columns else []
                        print(f"[WARN] {date_col} 检测到 {invalid_mask.sum()} 个非法日期值, 示例: {sample_values}, WeldID: {sample_ids}")
                        for sample_value, sample_weld in zip(sample_values, sample_ids):
                            self.invalid_date_records.append({
                                'SourceFile': 'merged',
                                'Column': date_col,
                                'ExcelRow': None,
                                'WeldID': sample_weld,
                                'RawValue': sample_value
                            })
                        export_df.loc[invalid_mask, date_col] = None

            # 诊断：仅在verbose时打印唯一值/重复情况
            if self.verbose:
                try:
                    unique_weld_ids = export_df['WeldID'].nunique(dropna=False)
                    dup_rows = len(export_df) - unique_weld_ids
                    print(f"📈 焊缝编号唯一值 {unique_weld_ids}，重复行 {dup_rows}")
                    if dup_rows > 0:
                        dup_sample = export_df['WeldID'].value_counts().head(5)
                        print("🔁 重复最多的前5个焊缝编号：")
                        for wid, cnt in dup_sample.items():
                            if cnt > 1:
                                print(f"  {wid}: {cnt} 次")
                except Exception:
                    pass

            total_loaded = 0
            if len(export_df) == 0:
                chunk_iterator = [export_df]
            else:
                chunk_iterator = (
                    export_df.iloc[start:start + self.CHUNK_SIZE]
                    for start in range(0, len(export_df), self.CHUNK_SIZE)
                )

            # 记录最近一次写出的临时CSV路径，便于出错时排查
            last_temp_csv_path = None

            try:
                cursor.execute("SET SESSION local_infile = 1")
            except Exception:
                pass

            # 为了在 MySQL 端更安全地处理日期，将 WeldDate 先读入用户变量，再用 STR_TO_DATE 转换。
            # 这样即使某行列错位导致 '1.0' 之类的值进入，也会被转换为 NULL，而不会抛 1292 错误。
            load_columns = []
            for col in target_columns:
                if col == 'WeldDate':
                    load_columns.append('@tmp_WeldDate')
                else:
                    load_columns.append(col)
            columns_str = ', '.join(load_columns)

            for chunk in chunk_iterator:
                if chunk.empty:
                    continue

                # 防御性清洗：
                # - 去掉所有字符串字段中的换行符，防止 CSV 行结构被拆成多行导致列错位
                # - 去掉普通字符串中的反斜杠，避免与 ESCAPED BY '\\' 组合成 \" 之类导致 MySQL 误解析
                for col in chunk.columns:
                    if chunk[col].dtype == 'object':
                        chunk.loc[:, col] = chunk[col].apply(
                            lambda v: (
                                v.replace('\r', ' ')
                                 .replace('\n', ' ')
                                 .replace('\\', ' ')
                            ) if isinstance(v, str) else v
                        )

                # 二次校验日期列，确保 chunk 中不会残留非法值
                for date_col in date_cols:
                    if date_col in chunk.columns:
                        chunk_series = chunk[date_col]
                        chunk_str = chunk_series.astype(str)
                        invalid_mask = chunk_series.notna() & ~chunk_str.str.fullmatch(date_regex)
                        if invalid_mask.any():
                            sample_vals = chunk_str[invalid_mask].head(3).tolist()
                            sample_ids = chunk.loc[invalid_mask, 'WeldID'].head(3).tolist() if 'WeldID' in chunk.columns else []
                            print(f"[WARN] chunk 中 {date_col} 发现 {invalid_mask.sum()} 个非法值, 示例值: {sample_vals}, WeldID: {sample_ids}")
                            for sample_value, sample_weld in zip(sample_vals, sample_ids):
                                self.invalid_date_records.append({
                                    'SourceFile': 'chunk',
                                    'Column': date_col,
                                    'ExcelRow': None,
                                    'WeldID': sample_weld,
                                    'RawValue': sample_value
                                })
                            chunk.loc[invalid_mask, date_col] = None

                with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, newline='', encoding='utf-8') as tmp:
                    temp_csv_path = tmp.name
                    # 使用 QUOTE_ALL 并在清洗换行后写出，降低列错位风险
                    chunk.to_csv(
                        tmp,
                        index=False,
                        na_rep='\\N',
                        lineterminator='\r\n',
                        quoting=csv.QUOTE_ALL
                    )

                last_temp_csv_path = temp_csv_path
                print(f"[DEBUG] Temp CSV path: {temp_csv_path}, rows in chunk: {len(chunk)}")

                escaped_path = temp_csv_path.replace('\\', r'\\')
                load_sql = (
                    f"LOAD DATA LOCAL INFILE '{escaped_path}' REPLACE INTO TABLE WeldingList "
                    "CHARACTER SET utf8mb4 "
                    "FIELDS TERMINATED BY ',' ENCLOSED BY '\"' ESCAPED BY '\\\\' "
                    "LINES TERMINATED BY '\r\n' "
                    "IGNORE 1 LINES "
                    f"({columns_str}) "
                    "SET WeldDate = STR_TO_DATE(NULLIF(@tmp_WeldDate, ''), '%Y-%m-%d')"
                )
                
                # 使用重试机制执行LOAD DATA
                chunk_retry_delay = 2
                chunk_max_retries = 5
                chunk_loaded = False
                
                for chunk_attempt in range(chunk_max_retries):
                    try:
                        # 检查连接是否有效
                        if not connection.is_connected():
                            print(f"⚠️  连接已断开，尝试重新连接（chunk {total_loaded // self.CHUNK_SIZE + 1}）...")
                            try:
                                cursor.close()
                                connection.close()
                            except:
                                pass
                            connection = self._retry_connection()
                            if not connection:
                                raise Error("无法重新建立连接")
                            cursor = connection.cursor()
                            # 重新设置会话参数
                            try:
                                cursor.execute("SET SESSION local_infile = 1")
                                if checks_disabled:
                                    cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
                                    cursor.execute("SET UNIQUE_CHECKS = 0")
                            except:
                                pass
                        
                        cursor.execute(load_sql)
                        connection.commit()
                        total_loaded += len(chunk)
                        chunk_loaded = True
                        if chunk_attempt > 0:
                            print(f"✅ Chunk {total_loaded // self.CHUNK_SIZE} 导入成功（第 {chunk_attempt + 1} 次尝试）")
                        break
                    except Error as e:
                        error_msg = str(e)
                        is_retryable = any(keyword in error_msg.lower() for keyword in [
                            'lost connection', 'connection', 'timeout', 'gone away',
                            'server has gone away', 'broken pipe', 'network'
                        ])
                        
                        if is_retryable and chunk_attempt < chunk_max_retries - 1:
                            print(f"⚠️  Chunk导入失败（尝试 {chunk_attempt + 1}/{chunk_max_retries}）: {e}，{chunk_retry_delay}秒后重试...")
                            time.sleep(chunk_retry_delay)
                            chunk_retry_delay = min(chunk_retry_delay * 2, 60)  # 指数退避
                        else:
                            print(f"❌ Chunk导入失败（已重试 {chunk_max_retries} 次）: {e}")
                            raise
                
                if not chunk_loaded:
                    raise Error(f"Chunk导入失败，已重试 {chunk_max_retries} 次")
                #try:
                #    os.remove(temp_csv_path)
                #except Exception:
                #    pass

            # 使用实际表计数，而不是受影响行数（REPLACE 会2倍计数）
            try:
                cursor.execute("SELECT COUNT(*) FROM WeldingList")
                table_count = cursor.fetchone()[0]
            except Exception:
                table_count = None
            print(f"SUCCESS: Table now contains {table_count} rows (recent batch total {total_loaded})")
            # 诊断：显示前10条警告（若有）
            if self.verbose:
                try:
                    cursor.execute("SHOW COUNT(*) WARNINGS")
                    warn_count = cursor.fetchone()
                    if warn_count:
                        print(f"WARNING count: {warn_count[0]}")
                    cursor.execute("SHOW WARNINGS LIMIT 10")
                    warnings = cursor.fetchall()
                    if warnings:
                        print("WARNINGS (first 10):")
                        for w in warnings:
                            print(str(w))
                except Exception:
                    pass

            # 校验
            if self.verbose and (table_count is not None and table_count != predicted_rows):
                print("WARNING: Imported row count does not match expected, please check source data or CSV format.")

            # 测试状态汇总仅在 verbose 模式打印
            if self.verbose:
                try:
                    completed = (df['测试'] == '已完成').sum()
                    pending = (df['测试'] == '未完成').sum()
                    print(f"📊 测试状态：已完成 {completed}，未完成 {pending}")
                except Exception:
                    pass

            return True
        except Error as e:
            print(f"ERROR: Database operation failed: {e}")
            connection.rollback()
            return False
        finally:
            if connection and cursor:
                try:
                    if checks_disabled:
                        cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
                        cursor.execute("SET UNIQUE_CHECKS = 1")
                except Exception:
                    pass
            if connection:
                connection.close()

# 使用示例
if __name__ == "__main__":
    # 目标Excel路径/目录（目录时自动匹配最新的 WeldingDB_*.xlsx）
    excel_source = r"C:\Projects\PrecomControl\nordinfo"
    resolved_files = resolve_welding_files(excel_source)
    if not resolved_files:
        raise FileNotFoundError(f"未在 {excel_source} 找到 WeldingDB_*.xlsx 文件")
    print(f"使用焊接数据文件: {', '.join(resolved_files)}")
    
    # 1. 导入前备份
    print(f"\n{'='*60}")
    print(f"步骤 1/3: 创建导入前备份...")
    print(f"{'='*60}")
    
    from utils.backup_manager import create_backup
    try:
        backup_id = create_backup(
            trigger='PRE_IMPORT',
            description=f'WeldingList导入前自动备份 - {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}'
        )
        print(f"✓ 备份完成，备份ID: {backup_id}")
    except Exception as e:
        print(f"✗ 备份失败: {e}")
        print("警告: 未创建备份，但将继续导入")
        backup_id = None
    
    # 2. 确保表存在并导入数据
    print(f"\n{'='*60}")
    print(f"步骤 2/3: 导入WeldingList数据...")
    print(f"{'='*60}")
    
    create_welding_table()
    
    importer = WeldingDataImporter(excel_source, verbose=False)
    import_success = importer.import_to_database()
    
    # 3. 导入后智能同步
    if import_success:
        print(f"\n{'='*60}")
        print(f"步骤 3/3: 智能同步主数据...")
        print(f"{'='*60}")
        
        from utils.sync_manager import sync_after_import
        try:
            sync_id = sync_after_import(backup_id=backup_id)
            print(f"✓ 同步完成，同步ID: {sync_id}")
        except Exception as e:
            print(f"✗ 同步失败: {e}")
            print("警告: 同步失败，但WeldingList已导入")
        
        print(f"\n{'='*60}")
        print(f"✅ 全部完成！")
        print(f"{'='*60}\n")
    else:
        print(f"\n{'='*60}")
        print(f"❌ 导入失败！")
        print(f"{'='*60}")
        print(f"提示: 可以使用备份 {backup_id} 恢复数据")
        print(f"      运行: python -c \"from utils.restore_manager import restore_backup; restore_backup({backup_id}, preview=False)\"")
        print(f"{'='*60}\n")


