# -*- coding: utf-8 -*-
"""
管线清单导入器
从 nordinfo/管线清单.xls 导入数据到 LineList 表
"""
import pandas as pd
import mysql.connector
from config import DB_CONFIG
import os

class LineListImporter:
    def __init__(self, excel_path):
        self.excel_path = excel_path
        self.df = None
        self.load_excel()
    
    def load_excel(self):
        """加载Excel文件"""
        try:
            # 读取Excel，header=1表示第2行是列名，第1行是标题
            self.df = pd.read_excel(self.excel_path, sheet_name=0, header=1)
            
            # 跳过第一行（它是列名的另一个版本）
            self.df = self.df.iloc[1:].reset_index(drop=True)
            
            print(f"SUCCESS: Loaded {len(self.df)} rows from line list")
            
        except Exception as e:
            print(f"ERROR loading Excel: {e}")
            self.df = pd.DataFrame()
    
    def import_to_database(self):
        """导入数据到LineList表"""
        if self.df is None or self.df.empty:
            print("ERROR: No data to import")
            return False
        
        conn = mysql.connector.connect(allow_local_infile=True, **DB_CONFIG)
        if not conn:
            return False
        
        try:
            cursor = conn.cursor()
            
            # 清空表
            cursor.execute("TRUNCATE TABLE LineList")
            print("Table truncated")
            
            # 准备数据DataFrame
            df = self.df.copy()
            
            # 列映射（根据位置索引）
            # D列（索引3）：管线号
            # Z列（索引25）：NDE Grade
            
            if len(df.columns) > 3:
                df['LineID'] = df.iloc[:, 3].astype(str).str.strip()  # D列
            else:
                df['LineID'] = ''
            
            # 其他列（根据实际列索引）
            if len(df.columns) > 0:
                df['ProjectNo'] = df.iloc[:, 0].astype(str).str.strip() if pd.notna(df.iloc[:, 0]).any() else ''
            else:
                df['ProjectNo'] = ''
            
            if len(df.columns) > 1:
                df['AreaCode'] = df.iloc[:, 1].astype(str).str.strip() if pd.notna(df.iloc[:, 1]).any() else ''
            else:
                df['AreaCode'] = ''
            
            if len(df.columns) > 2:
                df['WorkArea'] = df.iloc[:, 2].astype(str).str.strip() if pd.notna(df.iloc[:, 2]).any() else ''
            else:
                df['WorkArea'] = ''
            
            if len(df.columns) > 4:
                df['DrawingNo'] = df.iloc[:, 4].astype(str).str.strip() if pd.notna(df.iloc[:, 4]).any() else ''
            else:
                df['DrawingNo'] = ''
            
            if len(df.columns) > 7:
                df['SystemCode'] = df.iloc[:, 7].astype(str).str.strip() if pd.notna(df.iloc[:, 7]).any() else ''
            else:
                df['SystemCode'] = ''
            
            if len(df.columns) > 10:
                df['PipingClass'] = df.iloc[:, 10].astype(str).str.strip() if pd.notna(df.iloc[:, 10]).any() else ''
            else:
                df['PipingClass'] = ''
            
            if len(df.columns) > 21:
                df['PIDNo'] = df.iloc[:, 21].astype(str).str.strip() if pd.notna(df.iloc[:, 21]).any() else ''
            else:
                df['PIDNo'] = ''
            
            if len(df.columns) > 25:
                df['NDEGrade'] = df.iloc[:, 25].astype(str).str.strip() if pd.notna(df.iloc[:, 25]).any() else ''
            else:
                df['NDEGrade'] = ''
            
            # 过滤掉无效行（LineID为空或为标题行）
            df = df[df['LineID'].notna() & (df['LineID'] != '') & ~df['LineID'].str.contains('Line NO', na=False)]
            
            if len(df) == 0:
                print("WARNING: No valid data after filtering")
                return False
            
            # 去除重复的管线号（保留第一条）
            df_before = len(df)
            df = df.drop_duplicates(subset=['LineID'], keep='first')
            df_after = len(df)
            if df_before != df_after:
                print(f"Removed {df_before - df_after} duplicate LineIDs")
            
            print(f"Valid rows after filtering: {df_after}")
            
            # 准备导入数据
            import_data = []
            for _, row in df.iterrows():
                import_data.append((
                    row['LineID'],
                    row.get('ProjectNo', ''),
                    row.get('AreaCode', ''),
                    row.get('WorkArea', ''),
                    row.get('DrawingNo', ''),
                    row.get('SystemCode', ''),
                    row.get('PipingClass', ''),
                    row.get('PIDNo', ''),
                    row.get('NDEGrade', '')
                ))
            
            # 批量插入
            cursor.executemany("""
                INSERT INTO LineList 
                (LineID, ProjectNo, AreaCode, WorkArea, DrawingNo, SystemCode, 
                 PipingClass, PIDNo, NDEGrade)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, import_data)
            
            conn.commit()
            print(f"SUCCESS: Imported {len(import_data)} lines")
            
            return True
            
        except Exception as e:
            print(f"ERROR during import: {e}")
            import traceback
            traceback.print_exc()
            conn.rollback()
            return False
        finally:
            conn.close()


if __name__ == '__main__':
    excel_path = os.path.join('nordinfo', '管线清单.xls')
    importer = LineListImporter(excel_path)
    importer.import_to_database()

