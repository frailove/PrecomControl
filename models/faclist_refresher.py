import pandas as pd
import mysql.connector
from mysql.connector import Error
import os
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径（确保可以导入根目录的模块）
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from database import create_connection, create_faclist_table as db_create_faclist_table

class FaclistRefresher:
    def __init__(self, faclist_path=None):
        # 如果未提供路径，使用默认路径
        if faclist_path is None:
            # 尝试多个可能的路径
            possible_paths = [
                r"C:\Users\Frail\OneDrive\Ust-Luga GCC\Procedures\REPORTS\BI\Facility_List.xlsx",
                "Faclist.xlsx",
                os.path.join(os.path.dirname(__file__), "..", "Faclist.xlsx")
            ]
            for path in possible_paths:
                if os.path.exists(path):
                    self.faclist_path = path
                    break
            else:
                self.faclist_path = possible_paths[0]  # 使用第一个作为默认
        else:
            self.faclist_path = faclist_path
        self.df = None
        self.load_data()
    
    def load_data(self):
        """加载Faclist数据"""
        try:
            if os.path.exists(self.faclist_path):
                # 定义需要以文本格式读取的列（避免 Excel 自动转换为数字，丢失前导零）
                text_columns = ['Main_Block', 'Main Block', 'MainBlock', 'SIMPLEBLK', 'SimpleBLK', 
                              'Block', 'Sub-Project CODE', 'Sub-project_CODE', 'Sub-project Code', 'SubProjectCode',
                              'Train', 'Unit', '!BCC_Quarter', 'BCC_Quarter', 'BCC Quarter', 'BCCQuarter']
                
                # 先读取一次获取列名
                temp_df = pd.read_excel(self.faclist_path, nrows=0, engine='openpyxl')  # 只读取列名
                column_names = list(temp_df.columns)
                
                # 构建 dtype 字典：将所有可能的文本列指定为 str 类型
                dtype_dict = {}
                converters = {}
                
                # 定义转换函数（避免 lambda 闭包问题）
                def make_str_converter():
                    def converter(x):
                        if pd.isna(x) or x is None:
                            return ''
                        # 直接转换为字符串，保留原始格式（包括前导零）
                        # 注意：如果 Excel 中列是数字格式，前导零可能已丢失
                        return str(x)
                    return converter
                
                for col in column_names:
                    # 检查列名是否匹配需要保留前导零的列
                    if any(text_col.lower() in str(col).lower() for text_col in text_columns):
                        # 使用 converters 确保在读取时就将值转换为字符串（保留前导零）
                        converters[col] = make_str_converter()
                        # 同时指定 dtype 为 str（作为备用）
                        dtype_dict[col] = str
                
                # 使用 converters 读取 Excel（converters 优先级高于 dtype）
                # 使用 openpyxl 引擎以确保更好的兼容性
                # 注意：如果 Excel 中列已经是数字格式，converters 可能无法恢复前导零
                # 但至少可以确保读取为字符串类型
                if converters:
                    self.df = pd.read_excel(self.faclist_path, converters=converters, engine='openpyxl')
                else:
                    # 如果没有匹配的列，使用 dtype
                    self.df = pd.read_excel(self.faclist_path, dtype=dtype_dict if dtype_dict else None, engine='openpyxl')
                
                # 再次确保相关列为字符串类型，并处理空值
                for col in self.df.columns:
                    if any(text_col.lower() in str(col).lower() for text_col in text_columns):
                        # 转换为字符串，并处理各种空值表示
                        self.df[col] = self.df[col].astype(str)
                        self.df[col] = self.df[col].replace(['nan', 'None', 'NaN', 'NAN', 'None', 'NULL', 'null'], '')
                        # 对于空字符串，转换为 None（以便数据库存储为 NULL）
                        self.df[col] = self.df[col].replace('', None)
                
                print(f"✅ 成功加载Faclist数据，共 {len(self.df)} 行")
                print("列名:", list(self.df.columns))
                
                # 调试：打印前几行 MainBlock 的值（用于验证前导零是否保留）
                if 'MainBlock' in self.df.columns or 'Main Block' in self.df.columns or 'Main_Block' in self.df.columns:
                    mainblock_col = None
                    for col in self.df.columns:
                        if 'mainblock' in str(col).lower():
                            mainblock_col = col
                            break
                    if mainblock_col:
                        print(f"📋 MainBlock 示例值（前5个非空值）:")
                        sample_values = self.df[mainblock_col].dropna().head(5)
                        for idx, val in sample_values.items():
                            print(f"  行 {idx}: '{val}' (类型: {type(val).__name__})")
            else:
                print(f"❌ Faclist文件不存在: {self.faclist_path}")
                self.df = pd.DataFrame()
        except Exception as e:
            print(f"❌ 加载Faclist数据失败: {e}")
            import traceback
            traceback.print_exc()
            self.df = pd.DataFrame()
    
    def create_faclist_table(self):
        """创建Faclist表（如果不存在）
        表将创建在 config.py 中配置的 PRECOMCONTROL 数据库中
        """
        # 使用 database.py 中的统一函数
        return db_create_faclist_table()
    def refresh_faclist(self):
        """刷新Faclist数据"""
        if self.df is None or self.df.empty:
            print("❌ Faclist数据为空，无法刷新")
            return False
        
        # 先创建表
        if not self.create_faclist_table():
            return False
        
        connection = create_connection()
        if not connection:
            return False
        cursor = None
        try:
            cursor = connection.cursor()
            
            # 映射Excel列名到数据库列名（处理特殊字符）
            column_mapping = {
                'Block': 'Block',
                'Project': 'Project',
                'Sub-Project CODE': 'SubProjectCode',
                'Sub-Project Code': 'SubProjectCode',
                'Sub-project_CODE': 'SubProjectCode',
                'Sub-project Code': 'SubProjectCode',
                'SubProjectCode': 'SubProjectCode',
                'Train': 'Train',
                'Unit': 'Unit',
                'Main_Block': 'MainBlock',
                'Main Block': 'MainBlock',
                'MainBlock': 'MainBlock',
                'Descriptions': 'Descriptions',
                'SIMPLEBLK': 'SimpleBLK',
                'SimpleBLK': 'SimpleBLK',
                '!BCC_Quarter': 'BCCQuarter',
                'BCC_Quarter': 'BCCQuarter',
                'BCC Quarter': 'BCCQuarter',
                'BCCQuarter': 'BCCQuarter',
                '!BCC_START_UP_SEQUENCE': 'BCCStartUpSequence',
                'BCC_START_UP_SEQUENCE': 'BCCStartUpSequence',
                'BCC START UP SEQUENCE': 'BCCStartUpSequence',
                'BCCStartUpSequence': 'BCCStartUpSequence',
                'Title_Type': 'TitleType',
                'Title Type': 'TitleType',
                'TitleType': 'TitleType',
                'DrawingNumber': 'DrawingNumber',
                'Drawing Number': 'DrawingNumber',
                '图纸号': 'DrawingNumber'
            }
            
            # 准备数据：只选择存在的列
            db_columns = ['Block', 'Project', 'SubProjectCode', 'Train', 'Unit', 
                         'MainBlock', 'Descriptions', 'SimpleBLK', 'BCCQuarter', 
                         'BCCStartUpSequence', 'TitleType', 'DrawingNumber']
            
            # 构建数据行
            data_rows = []
            for _, row in self.df.iterrows():
                data_row = []
                for db_col in db_columns:
                    # 尝试从Excel中找到对应的列
                    value = None
                    for excel_col, mapped_col in column_mapping.items():
                        if mapped_col == db_col and excel_col in self.df.columns:
                            val = row.get(excel_col)
                            if pd.notna(val):
                                # 对于 MainBlock、SimpleBLK、Block 等字段，确保以文本格式保存（保留前导零）
                                if db_col in ['MainBlock', 'SimpleBLK', 'Block', 'SubProjectCode', 'Train', 'Unit', 'BCCQuarter']:
                                    # 强制转换为字符串，保留原始格式
                                    if pd.isna(val) or val is None:
                                        value = None
                                    else:
                                        # 先转换为字符串
                                        value = str(val).strip()
                                        # 如果是数字字符串，检查是否需要补零（但Excel可能已经丢失前导零）
                                        # 主要确保是字符串类型，不是数字
                                        if value.lower() in ['nan', 'none', '']:
                                            value = None
                                        # 确保值不为空
                                        if value and len(value) > 0:
                                            # 保持原始字符串格式
                                            pass
                                        else:
                                            value = None
                                else:
                                    value = str(val).strip() if val and pd.notna(val) else None
                            break
                    data_row.append(value if value else None)
                data_rows.append(tuple(data_row))
            
            # 清空表
            cursor.execute("TRUNCATE TABLE Faclist")
            
            # 批量插入
            if data_rows:
                placeholders = ','.join(['%s'] * len(db_columns))
                insert_sql = f"""
                    INSERT INTO Faclist ({','.join(db_columns)}) 
                    VALUES ({placeholders})
                """
                cursor.executemany(insert_sql, data_rows)
                connection.commit()
                print(f"✅ 成功刷新Faclist数据，共 {len(data_rows)} 行")
                return True
            else:
                print("⚠️ 没有有效数据可插入")
                return False
        except Error as e:
            print(f"❌ 刷新Faclist数据失败: {e}")
            connection.rollback()
            return False
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()
    def get_faclist(self):
        """获取所有Faclist数据"""
        connection = create_connection()
        if not connection:
            return []
        cursor = None
        try:
            cursor = connection.cursor(dictionary=True)
            cursor.execute("SELECT * FROM Faclist ORDER BY Block, DrawingNumber")
            return cursor.fetchall()
        except Error as e:
            print(f"❌ 获取Faclist数据失败: {e}")
            return []
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()
    
    def get_faclist_by_id(self, faclist_id):
        """根据ID获取Faclist数据"""
        connection = create_connection()
        if not connection:
            return None
        cursor = None
        try:
            cursor = connection.cursor(dictionary=True)
            cursor.execute("SELECT * FROM Faclist WHERE FaclistID = %s", (faclist_id,))
            return cursor.fetchone()
        except Error as e:
            print(f"❌ 获取Faclist数据失败: {e}")
            return None
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()
    
    def get_faclist_by_block(self, block_name):
        """根据Block名称获取Faclist数据"""
        connection = create_connection()
        if not connection:
            return []
        cursor = None
        try:
            cursor = connection.cursor(dictionary=True)
            cursor.execute("SELECT * FROM Faclist WHERE Block = %s", (block_name,))
            return cursor.fetchall()
        except Error as e:
            print(f"❌ 获取Faclist数据失败: {e}")
            return []
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()
    
    def get_faclist_by_drawing_number(self, drawing_number):
        """根据图纸号获取Faclist数据（用于关联区域信息）"""
        connection = create_connection()
        if not connection:
            return None
        cursor = None
        try:
            cursor = connection.cursor(dictionary=True)
            # 支持模糊匹配和精确匹配
            cursor.execute("""
                SELECT * FROM Faclist 
                WHERE DrawingNumber = %s 
                   OR DrawingNumber LIKE %s
                LIMIT 1
            """, (drawing_number, f"%{drawing_number}%"))
            return cursor.fetchone()
        except Error as e:
            print(f"❌ 根据图纸号获取Faclist数据失败: {e}")
            return None
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()
    
    def get_region_info_by_drawing_number(self, drawing_number):
        """根据图纸号获取区域信息（返回Block, Project, Train, Unit等）"""
        faclist = self.get_faclist_by_drawing_number(drawing_number)
        if faclist:
            return {
                'Block': faclist.get('Block'),
                'Project': faclist.get('Project'),
                'Train': faclist.get('Train'),
                'Unit': faclist.get('Unit'),
                'MainBlock': faclist.get('MainBlock'),
                'SimpleBLK': faclist.get('SimpleBLK')
            }
        return None


def main():
    """主函数：用于命令行运行"""
    import sys
    
    print("=" * 60)
    print("🔄 开始刷新 Faclist 数据...")
    print("=" * 60)
    
    # 如果提供了文件路径作为命令行参数，使用它
    faclist_path = sys.argv[1] if len(sys.argv) > 1 else None
    
    try:
        # 初始化 FaclistRefresher
        refresher = FaclistRefresher(faclist_path=faclist_path)
        
        # 刷新数据
        if refresher.refresh_faclist():
            print("\n" + "=" * 60)
            print("✅ Faclist 数据刷新成功！")
            print("=" * 60)
            return 0
        else:
            print("\n" + "=" * 60)
            print("❌ Faclist 数据刷新失败！")
            print("=" * 60)
            return 1
    except Exception as e:
        print(f"\n❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    exit(main())
