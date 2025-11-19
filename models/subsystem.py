from database import create_connection
from mysql.connector import Error

class SubsystemModel:
    @staticmethod
    def list_subsystems(search=None, process_type=None, system_code=None, allowed_codes=None, page=1, per_page=50):
        """分页获取子系统列表，返回 (records, total_count, process_count, non_process_count)"""
        connection = create_connection()
        if not connection:
            return [], 0, 0, 0

        try:
            cursor = connection.cursor(dictionary=True)
            conditions = []
            params = []

            if system_code:
                conditions.append("s.SystemCode = %s")
                params.append(system_code)

            if process_type:
                conditions.append("s.ProcessOrNonProcess = %s")
                params.append(process_type)

            if search:
                like = f"%{search}%"
                conditions.append("(s.SubSystemCode LIKE %s OR COALESCE(s.SubSystemDescriptionENG, '') LIKE %s)")
                params.extend([like, like])

            if allowed_codes is not None:
                if not allowed_codes:
                    return [], 0, 0, 0
                placeholders = ','.join(['%s'] * len(allowed_codes))
                conditions.append(f"s.SubSystemCode IN ({placeholders})")
                params.extend(list(allowed_codes))

            where_clause = " AND ".join(conditions) if conditions else "1=1"
            count_sql = f"""
                SELECT s.ProcessOrNonProcess, COUNT(*) AS cnt
                FROM SubsystemList s
                WHERE {where_clause}
                GROUP BY s.ProcessOrNonProcess
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
                SELECT s.*, sys.SystemDescriptionENG as SystemDescription 
                FROM SubsystemList s 
                LEFT JOIN SystemList sys ON s.SystemCode = sys.SystemCode 
                WHERE {where_clause}
                ORDER BY s.SystemCode, s.SubSystemCode
                LIMIT %s OFFSET %s
            """
            data_params = list(params)
            data_params.extend([per_page, offset])
            cursor.execute(data_sql, tuple(data_params))
            subsystems = cursor.fetchall()
            return subsystems, total_count, process_count, non_process_count
        except Error as e:
            print(f"❌ 分页查询子系统列表失败: {e}")
            return [], 0, 0, 0
        finally:
            if connection:
                connection.close()

    @staticmethod
    def get_all_subsystems():
        """获取所有子系统"""
        connection = create_connection()
        if not connection:
            return []
        
        try:
            cursor = connection.cursor(dictionary=True)
            query = """
                SELECT s.*, sys.SystemDescriptionENG as SystemDescription 
                FROM SubsystemList s 
                LEFT JOIN SystemList sys ON s.SystemCode = sys.SystemCode 
                ORDER BY s.SystemCode, s.SubSystemCode
            """
            cursor.execute(query)
            subsystems = cursor.fetchall()
            print(f"📊 获取到 {len(subsystems)} 个子系统")
            return subsystems
        except Error as e:
            print(f"❌ 查询子系统列表失败: {e}")
            return []
        finally:
            if connection:
                connection.close()
    
    @staticmethod
    def get_subsystem_by_code(subsystem_code):
        """根据子系统代码获取子系统信息"""
        connection = create_connection()
        if not connection:
            return None
        
        try:
            cursor = connection.cursor(dictionary=True)
            query = """
                SELECT s.*, sys.SystemDescriptionENG as SystemDescription 
                FROM SubsystemList s 
                LEFT JOIN SystemList sys ON s.SystemCode = sys.SystemCode 
                WHERE s.SubSystemCode = %s
            """
            cursor.execute(query, (subsystem_code,))
            subsystem = cursor.fetchone()
            return subsystem
        except Error as e:
            print(f"❌ 获取子系统信息失败: {e}")
            return None
        finally:
            if connection:
                connection.close()
    
    @staticmethod
    def get_subsystems_by_system(system_code):
        """根据系统代码获取子系统（包含系统描述）"""
        connection = create_connection()
        if not connection:
            return []
        
        try:
            cursor = connection.cursor(dictionary=True)
            query = """
                SELECT s.*, sys.SystemDescriptionENG as SystemDescription 
                FROM SubsystemList s 
                LEFT JOIN SystemList sys ON s.SystemCode = sys.SystemCode 
                WHERE s.SystemCode = %s
                ORDER BY s.SubSystemCode
            """
            cursor.execute(query, (system_code,))
            subsystems = cursor.fetchall()
            return subsystems
        except Error as e:
            print(f"❌ 根据系统获取子系统失败: {e}")
            return []
        finally:
            if connection:
                connection.close()
    
    @staticmethod
    def create_subsystem(subsystem_data):
        """创建新子系统"""
        connection = create_connection()
        if not connection:
            return False
        
        try:
            cursor = connection.cursor()
            query = """
                INSERT INTO SubsystemList 
                (SubSystemCode, SystemCode, SubSystemDescriptionENG, SubSystemDescriptionRUS, 
                 ProcessOrNonProcess, Priority, Remarks, created_by) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(query, (
                subsystem_data['SubSystemCode'],
                subsystem_data['SystemCode'],
                subsystem_data['SubSystemDescriptionENG'],
                subsystem_data.get('SubSystemDescriptionRUS', ''),
                subsystem_data['ProcessOrNonProcess'],
                subsystem_data.get('Priority', 0),
                subsystem_data.get('Remarks', ''),
                subsystem_data.get('created_by', 'admin')
            ))
            connection.commit()
            print(f"✅ 子系统 {subsystem_data['SubSystemCode']} 添加成功")
            return True
        except Error as e:
            print(f"❌ 添加子系统失败: {e}")
            connection.rollback()
            return False
        finally:
            if connection:
                connection.close()
    
    @staticmethod
    def update_subsystem(subsystem_code, update_data):
        """更新子系统信息"""
        connection = create_connection()
        if not connection:
            return False
        
        try:
            cursor = connection.cursor()
            query = """
                UPDATE SubsystemList 
                SET SystemCode = %s, SubSystemDescriptionENG = %s, SubSystemDescriptionRUS = %s,
                    ProcessOrNonProcess = %s, Priority = %s, Remarks = %s, last_updated_by = %s
                WHERE SubSystemCode = %s
            """
            cursor.execute(query, (
                update_data['SystemCode'],
                update_data['SubSystemDescriptionENG'],
                update_data.get('SubSystemDescriptionRUS', ''),
                update_data['ProcessOrNonProcess'],
                update_data.get('Priority', 0),
                update_data.get('Remarks', ''),
                update_data.get('last_updated_by', 'admin'),
                subsystem_code
            ))
            connection.commit()
            print(f"✅ 子系统 {subsystem_code} 更新成功")
            return cursor.rowcount > 0
        except Error as e:
            print(f"❌ 更新子系统失败: {e}")
            connection.rollback()
            return False
        finally:
            if connection:
                connection.close()
    
    @staticmethod
    def delete_subsystem(subsystem_code):
        """删除子系统"""
        connection = create_connection()
        if not connection:
            return False
        
        try:
            cursor = connection.cursor()
            cursor.execute("DELETE FROM SubsystemList WHERE SubSystemCode = %s", (subsystem_code,))
            connection.commit()
            print(f"✅ 子系统 {subsystem_code} 删除成功")
            return cursor.rowcount > 0
        except Error as e:
            print(f"❌ 删除子系统失败: {e}")
            connection.rollback()
            return False
        finally:
            if connection:
                connection.close()