from database import create_connection
from mysql.connector import Error

class SystemModel:
    @staticmethod
    def list_systems(search=None, process_type=None, allowed_codes=None, page=1, per_page=50):
        """分页获取系统列表，返回 (records, total_count, process_count, non_process_count)"""
        connection = create_connection()
        if not connection:
            return [], 0, 0, 0

        try:
            cursor = connection.cursor(dictionary=True)
            conditions = []
            params = []

            if process_type:
                conditions.append("ProcessOrNonProcess = %s")
                params.append(process_type)

            if search:
                like = f"%{search}%"
                conditions.append("(SystemCode LIKE %s OR COALESCE(SystemDescriptionENG, '') LIKE %s)")
                params.extend([like, like])

            if allowed_codes is not None:
                if not allowed_codes:
                    return [], 0, 0, 0
                placeholders = ','.join(['%s'] * len(allowed_codes))
                conditions.append(f"SystemCode IN ({placeholders})")
                params.extend(list(allowed_codes))

            where_clause = " AND ".join(conditions) if conditions else "1=1"
            count_sql = f"""
                SELECT ProcessOrNonProcess, COUNT(*) AS cnt
                FROM SystemList
                WHERE {where_clause}
                GROUP BY ProcessOrNonProcess
            """
            cursor.execute(count_sql, tuple(params))
            total_count = 0
            process_count = 0
            non_process_count = 0
            for row in cursor.fetchall():
                cnt = row['cnt'] or 0
                total_count += cnt
                if row['ProcessOrNonProcess'] == 'Process':
                    process_count += cnt
                else:
                    non_process_count += cnt

            offset = max(page - 1, 0) * per_page
            data_sql = f"""
                SELECT SystemCode, SystemDescriptionENG, ProcessOrNonProcess, Priority, Remarks
                FROM SystemList
                WHERE {where_clause}
                ORDER BY SystemCode
                LIMIT %s OFFSET %s
            """
            data_params = list(params)
            data_params.extend([per_page, offset])
            cursor.execute(data_sql, tuple(data_params))
            systems = cursor.fetchall()
            return systems, total_count, process_count, non_process_count
        except Error as e:
            print(f"❌ 分页查询系统列表失败: {e}")
            return [], 0, 0, 0
        finally:
            if connection:
                connection.close()

    @staticmethod
    def get_all_systems():
        """获取所有系统"""
        connection = create_connection()
        if not connection:
            return []
        
        try:
            cursor = connection.cursor(dictionary=True)
            cursor.execute("SELECT * FROM SystemList ORDER BY SystemCode")
            systems = cursor.fetchall()
            print(f"📊 获取到 {len(systems)} 个系统")
            return systems
        except Error as e:
            print(f"❌ 查询系统列表失败: {e}")
            return []
        finally:
            if connection:
                connection.close()
    
    @staticmethod
    def get_system_by_code(system_code):
        """根据系统代码获取系统信息"""
        connection = create_connection()
        if not connection:
            return None
        
        try:
            cursor = connection.cursor(dictionary=True)
            cursor.execute("SELECT * FROM SystemList WHERE SystemCode = %s", (system_code,))
            system = cursor.fetchone()
            return system
        except Error as e:
            print(f"❌ 获取系统信息失败: {e}")
            return None
        finally:
            if connection:
                connection.close()
    
    @staticmethod
    def create_system(system_data):
        """创建新系统"""
        connection = create_connection()
        if not connection:
            return False
        
        try:
            cursor = connection.cursor()
            query = """
                INSERT INTO SystemList 
                (SystemCode, SystemDescriptionENG, ProcessOrNonProcess, Priority, Remarks) 
                VALUES (%s, %s, %s, %s, %s)
            """
            cursor.execute(query, (
                system_data['SystemCode'],
                system_data['SystemDescriptionENG'],
                system_data['ProcessOrNonProcess'],
                system_data['Priority'],
                system_data['Remarks']
            ))
            connection.commit()
            print(f"✅ 系统 {system_data['SystemCode']} 添加成功")
            return True
        except Error as e:
            print(f"❌ 添加系统失败: {e}")
            connection.rollback()
            return False
        finally:
            if connection:
                connection.close()
    
    @staticmethod
    def update_system(system_code, update_data):
        """更新系统信息"""
        connection = create_connection()
        if not connection:
            return False
        
        try:
            cursor = connection.cursor()
            query = """
                UPDATE SystemList 
                SET SystemDescriptionENG = %s, ProcessOrNonProcess = %s, 
                    Priority = %s, Remarks = %s 
                WHERE SystemCode = %s
            """
            cursor.execute(query, (
                update_data['SystemDescriptionENG'],
                update_data['ProcessOrNonProcess'],
                update_data['Priority'],
                update_data['Remarks'],
                system_code
            ))
            connection.commit()
            print(f"✅ 系统 {system_code} 更新成功")
            return cursor.rowcount > 0
        except Error as e:
            print(f"❌ 更新系统失败: {e}")
            connection.rollback()
            return False
        finally:
            if connection:
                connection.close()
    
    @staticmethod
    def delete_system(system_code):
        """删除系统"""
        connection = create_connection()
        if not connection:
            return False
        
        try:
            cursor = connection.cursor()
            cursor.execute("DELETE FROM SystemList WHERE SystemCode = %s", (system_code,))
            connection.commit()
            print(f"✅ 系统 {system_code} 删除成功")
            return cursor.rowcount > 0
        except Error as e:
            print(f"❌ 删除系统失败: {e}")
            connection.rollback()
            return False
        finally:
            if connection:
                connection.close()