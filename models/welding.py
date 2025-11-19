from database import create_connection  # 复用现有数据库连接工具
from mysql.connector import Error

class WeldingModel:
    @staticmethod
    def create_welding(welding_data):
        """创建新焊口记录"""
        connection = create_connection()
        if not connection:
            return False
        
        try:
            cursor = connection.cursor()
            query = """
                INSERT INTO WeldingList 
                (WeldID, TestPackageID, SystemCode, SubSystemCode, WeldDate,
                 Size, WelderID, WPSNumber, VTResult, RTResult, UTResult,
                 PTResult, MTResult, Remarks, created_by) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(query, (
                welding_data['WeldID'],
                welding_data['TestPackageID'],
                welding_data['SystemCode'],
                welding_data['SubSystemCode'],
                welding_data.get('WeldDate'),
                welding_data.get('Size'),
                welding_data.get('WelderID'),
                welding_data.get('WPSNumber'),
                welding_data.get('VTResult'),
                welding_data.get('RTResult'),
                welding_data.get('UTResult'),
                welding_data.get('PTResult'),
                welding_data.get('MTResult'),
                welding_data.get('Remarks', ''),
                welding_data.get('created_by', 'admin')
            ))
            connection.commit()
            print(f"✅ 焊口 {welding_data['WeldID']} 添加成功")
            return True
        except Error as e:
            print(f"❌ 添加焊口失败: {e}")
            connection.rollback()
            return False
        finally:
            if connection:
                connection.close()

    @staticmethod
    def get_weldings_by_test_package(test_package_id):
        """根据试压包ID获取所有焊口"""
        connection = create_connection()
        if not connection:
            return []
        
        try:
            cursor = connection.cursor(dictionary=True)
            query = """
                SELECT * FROM WeldingList 
                WHERE TestPackageID = %s 
                ORDER BY WeldDate DESC
            """
            cursor.execute(query, (test_package_id,))
            return cursor.fetchall()
        except Error as e:
            print(f"❌ 获取试压包焊口失败: {e}")
            return []
        finally:
            if connection:
                connection.close()

    @staticmethod
    def get_weldings_by_system(system_code):
        """根据系统代码获取所有焊口"""
        connection = create_connection()
        if not connection:
            return []
        
        try:
            cursor = connection.cursor(dictionary=True)
            query = """
                SELECT * FROM WeldingList 
                WHERE SystemCode = %s 
                ORDER BY WeldDate DESC
            """
            cursor.execute(query, (system_code,))
            return cursor.fetchall()
        except Error as e:
            print(f"❌ 获取系统焊口失败: {e}")
            return []
        finally:
            if connection:
                connection.close()

    @staticmethod
    def get_weldings_by_subsystem(subsystem_code):
        """根据子系统代码获取所有焊口"""
        connection = create_connection()
        if not connection:
            return []
        
        try:
            cursor = connection.cursor(dictionary=True)
            query = """
                SELECT * FROM WeldingList 
                WHERE SubSystemCode = %s 
                ORDER BY WeldDate DESC
            """
            cursor.execute(query, (subsystem_code,))
            return cursor.fetchall()
        except Error as e:
            print(f"❌ 获取子系统焊口失败: {e}")
            return []
        finally:
            if connection:
                connection.close()

    # 其他方法：get_welding_by_id、update_welding、delete_welding（类似现有模块）