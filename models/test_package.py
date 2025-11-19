from database import create_connection
from database import ensure_hydro_columns
from mysql.connector import Error

class TestPackageModel:
    @staticmethod
    def list_test_packages(search=None, system_code=None, subsystem_code=None, status=None,
                           allowed_drawing_numbers=None, page=1, per_page=50, sort_order=None):
        """分页获取试压包列表（含焊口与DIN统计）"""
        try:
            ensure_hydro_columns()
        except Exception:
            pass

        if per_page is None or per_page <= 0:
            per_page = 50
        page = max(page or 1, 1)

        if allowed_drawing_numbers is not None:
            allowed_drawing_numbers = [num for num in allowed_drawing_numbers if num]
            if not allowed_drawing_numbers:
                return [], 0, 0, 0, 0

        connection = create_connection()
        if not connection:
            return [], 0, 0, 0, 0

        try:
            cursor = connection.cursor(dictionary=True)
            where_clauses = ["wl.TestPackageID IS NOT NULL", "wl.TestPackageID <> ''"]
            params = []

            if search:
                where_clauses.append("wl.TestPackageID LIKE %s")
                params.append(f"%{search}%")
            if system_code:
                where_clauses.append("h.SystemCode = %s")
                params.append(system_code)
            if subsystem_code:
                where_clauses.append("h.SubSystemCode = %s")
                params.append(subsystem_code)
            if status:
                where_clauses.append("LOWER(COALESCE(h.Status, 'Pending')) = %s")
                params.append(status.strip().lower())
            if allowed_drawing_numbers is not None:
                placeholders = ','.join(['%s'] * len(allowed_drawing_numbers))
                where_clauses.append(f"wl.DrawingNumber IN ({placeholders})")
                params.extend(allowed_drawing_numbers)

            where_sql = " AND ".join(where_clauses)

            count_sql = f"""
                SELECT
                    COUNT(DISTINCT wl.TestPackageID) AS total_count,
                    COUNT(DISTINCT CASE WHEN LOWER(COALESCE(h.Status, 'Pending')) = 'completed' THEN wl.TestPackageID END) AS completed_count,
                    COUNT(DISTINCT CASE WHEN LOWER(COALESCE(h.Status, 'Pending')) = 'in progress' THEN wl.TestPackageID END) AS in_progress_count,
                    COUNT(DISTINCT CASE WHEN LOWER(COALESCE(h.Status, 'Pending')) NOT IN ('completed', 'in progress') THEN wl.TestPackageID END) AS pending_count
                FROM WeldingList wl
                LEFT JOIN HydroTestPackageList h ON h.TestPackageID = wl.TestPackageID
                WHERE {where_sql}
            """
            cursor.execute(count_sql, tuple(params))
            row = cursor.fetchone() or {}
            total_count = int(row.get('total_count') or 0)
            completed_count = int(row.get('completed_count') or 0)
            in_progress_count = int(row.get('in_progress_count') or 0)
            pending_count = int(row.get('pending_count') or 0)

            offset = (page - 1) * per_page
            progress_expr = """
                CASE
                    WHEN COALESCE(SUM(wl.Size), 0) = 0 THEN 0
                    ELSE COALESCE(SUM(CASE WHEN wl.WeldDate IS NOT NULL THEN wl.Size ELSE 0 END), 0) / COALESCE(SUM(wl.Size), 0)
                END
            """
            order_by_clause = "wl.TestPackageID"
            if sort_order == 'progress_asc':
                order_by_clause = "progress ASC, wl.TestPackageID"
            elif sort_order == 'progress_desc':
                order_by_clause = "progress DESC, wl.TestPackageID"

            data_sql = f"""
                SELECT wl.TestPackageID,
                       COUNT(*) AS total_welds,
                       SUM(CASE WHEN wl.Status = '宸插畬鎴?' THEN 1 ELSE 0 END) AS completed_welds,
                       COALESCE(SUM(wl.Size), 0) AS total_din,
                       COALESCE(SUM(CASE WHEN wl.WeldDate IS NOT NULL THEN wl.Size ELSE 0 END), 0) AS completed_din,
                       {progress_expr} AS progress,
                       MAX(CASE WHEN wl.VTResult = '鍚堟牸' THEN 1 ELSE 0 END) AS vt_pass,
                       MAX(CASE WHEN wl.RTResult = '鍚堟牸' THEN 1 ELSE 0 END) AS rt_pass,
                       MAX(CASE WHEN wl.UTResult = '鍚堟牸' THEN 1 ELSE 0 END) AS ut_pass,
                       MAX(CASE WHEN wl.PTResult = '鍚堟牸' THEN 1 ELSE 0 END) AS pt_pass,
                       MAX(CASE WHEN wl.MTResult = '鍚堟牸' THEN 1 ELSE 0 END) AS mt_pass,
                       MAX(CASE WHEN wl.PMIResult = '鍚堟牸' THEN 1 ELSE 0 END) AS pmi_pass,
                       MAX(CASE WHEN wl.FTResult = '鍚堟牸' THEN 1 ELSE 0 END) AS ft_pass,
                       MAX(h.SystemCode) AS SystemCode,
                       MAX(h.SubSystemCode) AS SubSystemCode,
                       MAX(COALESCE(h.Description, '')) AS Description,
                       MAX(h.PlannedDate) AS PlannedDate,
                       MAX(h.ActualDate) AS ActualDate,
                       MAX(h.Status) AS HPStatus,
                       MAX(h.Pressure) AS Pressure,
                       MAX(h.TestDuration) AS TestDuration,
                       MAX(h.Remarks) AS Remarks,
                       MAX(h.TestType) AS TestType,
                       MAX(h.DesignPressure) AS DesignPressure,
                       MAX(h.TestPressure) AS TestPressure
                FROM WeldingList wl
                LEFT JOIN HydroTestPackageList h ON h.TestPackageID = wl.TestPackageID
                WHERE {where_sql}
                GROUP BY wl.TestPackageID
                ORDER BY {order_by_clause}
                LIMIT %s OFFSET %s
            """
            data_params = list(params)
            data_params.extend([per_page, offset])
            cursor.execute(data_sql, tuple(data_params))
            packages = cursor.fetchall() or []
            for pkg in packages:
                pkg['progress'] = float(pkg.get('progress') or 0.0)
            return packages, total_count, completed_count, in_progress_count, pending_count
        except Error:
            connection.rollback()
            return [], 0, 0, 0, 0
        finally:
            if connection:
                connection.close()

    @staticmethod
    def _sync_from_weldinglist(filter_test_package_id: str | None = None) -> dict:
        """将 WeldingList 中的试压包及其 SystemCode/SubSystemCode 补齐到 HydroTestPackageList。
        若已存在则忽略，不覆盖用户维护字段。
        同步前确保 SystemList/SubsystemList 存在对应 ID 以满足 NOT NULL + 外键约束。
        返回统计信息。
        """
        stats = {"systems_seeded": 0, "subsystems_seeded": 0, "hydros_inserted": 0, "candidates": 0}
        try:
            ensure_hydro_columns()
        except Exception:
            pass
        connection = create_connection()
        if not connection:
            return stats
        try:
            cursor = connection.cursor()
            # 先获取 distinct (TestPackageID, SystemCode, SubSystemCode)
            base_select = (
                "SELECT wl.TestPackageID, "
                "       MAX(NULLIF(TRIM(wl.SystemCode), '')) AS SystemCode, "
                "       MAX(NULLIF(TRIM(wl.SubSystemCode), '')) AS SubSystemCode "
                "FROM WeldingList wl "
                "WHERE wl.TestPackageID IS NOT NULL AND wl.TestPackageID <> '' {where_clause} "
                "GROUP BY wl.TestPackageID"
            )
            if filter_test_package_id:
                sql = base_select.format(where_clause="AND wl.TestPackageID = %s")
                cursor.execute(sql, (filter_test_package_id,))
            else:
                sql = base_select.format(where_clause="")
                cursor.execute(sql)
            rows = cursor.fetchall() or []
            stats["candidates"] = len(rows)

            # 容错：缺失 SystemCode/SubSystemCode 时生成占位ID
            def norm_sys(tpid, sc):
                sc = (sc or '').strip()
                return sc if sc else f"SYS-{tpid}"
            def norm_sub(tpid, sc, sub):
                scn = norm_sys(tpid, sc)
                sub = (sub or '').strip()
                return sub if sub else f"{scn}-SUB"

            normalized = [(tpid, norm_sys(tpid, sc), norm_sub(tpid, sc, sub)) for (tpid, sc, sub) in rows]

            # 先种子 SystemList / SubsystemList（仅按ID占位）
            system_rows = {sc for (_, sc, __) in normalized}
            subsystem_rows = {(sub, sc) for (_, sc, sub) in [(t, s, sub) for (t, s, sub) in normalized]}

            if system_rows:
                cursor.executemany(
                    """
                    INSERT IGNORE INTO SystemList
                    (SystemCode, SystemDescriptionENG, SystemDescriptionRUS, ProcessOrNonProcess, Priority, Remarks, created_by, last_updated_by)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    [(sc, sc, None, 'Process', 0, '', 'admin', 'admin') for sc in system_rows]
                )
                stats["systems_seeded"] = max(cursor.rowcount or 0, 0)
            if subsystem_rows:
                cursor.executemany(
                    """
                    INSERT IGNORE INTO SubsystemList
                    (SubSystemCode, SystemCode, SubSystemDescriptionENG, SubSystemDescriptionRUS, ProcessOrNonProcess, Priority, Remarks, created_by, last_updated_by)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    [(sub, sc, sub, None, 'Process', 0, '', 'admin', 'admin') for (sub, sc) in subsystem_rows]
                )
                stats["subsystems_seeded"] = max(cursor.rowcount or 0, 0)

            # 再插入 HydroTestPackageList 占位行（IGNORE 不覆盖已有）
            if normalized:
                cursor.executemany(
                    """
                    INSERT IGNORE INTO HydroTestPackageList
                    (TestPackageID, SystemCode, SubSystemCode, Description, PlannedDate, ActualDate, Status, Pressure, TestDuration, Remarks, created_by, last_updated_by)
                    VALUES (%s, %s, %s, %s, NULL, NULL, 'Pending', NULL, NULL, '', 'admin', 'admin')
                    """,
                    [(tpid, sc, sub, tpid) for (tpid, sc, sub) in normalized]
                )
                stats["hydros_inserted"] = max(cursor.rowcount or 0, 0)
            connection.commit()
            return stats
        except Error:
            connection.rollback()
            return stats
        finally:
            if connection:
                connection.close()

    @staticmethod
    def sync_all_from_welding() -> dict:
        """对全部试压包执行一次同步，返回统计信息。"""
        return TestPackageModel._sync_from_weldinglist(None)

    @staticmethod
    def get_all_test_packages():
        """获取所有试压包"""
        try:
            ensure_hydro_columns()
        except Exception:
            pass
        # 先从焊接表同步一次，确保列表完整
        TestPackageModel._sync_from_weldinglist()
        connection = create_connection()
        if not connection:
            return []
        
        try:
            cursor = connection.cursor(dictionary=True)
            query = """
                SELECT t.*, 
                       sys.SystemDescriptionENG as SystemDescription,
                       sub.SubSystemDescriptionENG as SubSystemDescription
                FROM HydroTestPackageList t
                LEFT JOIN SystemList sys ON t.SystemCode = sys.SystemCode
                LEFT JOIN SubsystemList sub ON t.SubSystemCode = sub.SubSystemCode
                ORDER BY t.PlannedDate, t.TestPackageID
            """
            cursor.execute(query)
            test_packages = cursor.fetchall()
            print(f"📊 获取到 {len(test_packages)} 个试压包")
            return test_packages
        except Error as e:
            print(f"❌ 查询试压包列表失败: {e}")
            return []
        finally:
            if connection:
                connection.close()
    
    @staticmethod
    def get_test_package_by_id(test_package_id):
        """根据试压包ID获取试压包信息"""
        try:
            ensure_hydro_columns()
        except Exception:
            pass
        # 针对该ID同步一次，避免不存在
        TestPackageModel._sync_from_weldinglist(test_package_id)
        connection = create_connection()
        if not connection:
            return None
        
        try:
            cursor = connection.cursor(dictionary=True)
            query = """
                SELECT t.*, 
                       sys.SystemDescriptionENG as SystemDescription,
                       sub.SubSystemDescriptionENG as SubSystemDescription
                FROM HydroTestPackageList t
                LEFT JOIN SystemList sys ON t.SystemCode = sys.SystemCode
                LEFT JOIN SubsystemList sub ON t.SubSystemCode = sub.SubSystemCode
                WHERE t.TestPackageID = %s
            """
            cursor.execute(query, (test_package_id,))
            test_package = cursor.fetchone()
            return test_package
        except Error as e:
            print(f"❌ 获取试压包信息失败: {e}")
            return None
        finally:
            if connection:
                connection.close()
    
    @staticmethod
    def create_test_package(test_package_data):
        """创建新试压包"""
        try:
            ensure_hydro_columns()
        except Exception:
            pass
        connection = create_connection()
        if not connection:
            return False
        
        try:
            cursor = connection.cursor()
            query = """
                INSERT INTO HydroTestPackageList 
                (TestPackageID, SystemCode, SubSystemCode, Description, 
                 PlannedDate, ActualDate, Status, Pressure, TestDuration, 
                 Remarks, created_by) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(query, (
                test_package_data['TestPackageID'],
                test_package_data['SystemCode'],
                test_package_data['SubSystemCode'],
                test_package_data['Description'],
                test_package_data.get('PlannedDate'),
                test_package_data.get('ActualDate'),
                test_package_data.get('Status', 'Pending'),
                test_package_data.get('Pressure'),
                test_package_data.get('TestDuration'),
                test_package_data.get('Remarks', ''),
                test_package_data.get('created_by', 'admin')
            ))
            connection.commit()
            print(f"✅ 试压包 {test_package_data['TestPackageID']} 添加成功")
            return True
        except Error as e:
            print(f"❌ 添加试压包失败: {e}")
            connection.rollback()
            return False
        finally:
            if connection:
                connection.close()
    
    @staticmethod
    def update_test_package(test_package_id, update_data):
        """更新试压包信息（支持动态字段）"""
        try:
            ensure_hydro_columns()
        except Exception:
            pass
        connection = create_connection()
        if not connection:
            return False
        
        try:
            cursor = connection.cursor()
            
            # 动态构建UPDATE语句，只更新提供的字段
            set_clauses = []
            params = []
            
            # 基础字段
            for field in ['SystemCode', 'SubSystemCode', 'Description', 'PlannedDate', 'ActualDate', 
                         'Status', 'Pressure', 'TestDuration', 'Remarks', 'last_updated_by']:
                if field in update_data:
                    set_clauses.append(f"{field} = %s")
                    params.append(update_data[field])
            
            # 扩展字段（如果数据库表已扩展）
            for field in ['PipeMaterial', 'TestType', 'TestMedium', 'DesignPressure', 'TestPressure']:
                if field in update_data:
                    set_clauses.append(f"{field} = %s")
                    params.append(update_data[field])
            
            # 添加WHERE条件的参数
            params.append(test_package_id)
            
            if not set_clauses:
                return False
            
            query = f"""
                UPDATE HydroTestPackageList 
                SET {', '.join(set_clauses)}
                WHERE TestPackageID = %s
            """
            
            cursor.execute(query, tuple(params))
            connection.commit()
            print(f"✅ 试压包 {test_package_id} 更新成功")
            return cursor.rowcount > 0
        except Error as e:
            print(f"❌ 更新试压包失败: {e}")
            connection.rollback()
            return False
        finally:
            if connection:
                connection.close()
    
    @staticmethod
    def delete_test_package(test_package_id):
        """删除试压包"""
        try:
            ensure_hydro_columns()
        except Exception:
            pass
        connection = create_connection()
        if not connection:
            return False
        
        try:
            cursor = connection.cursor()
            cursor.execute("DELETE FROM HydroTestPackageList WHERE TestPackageID = %s", (test_package_id,))
            connection.commit()
            print(f"✅ 试压包 {test_package_id} 删除成功")
            return cursor.rowcount > 0
        except Error as e:
            print(f"❌ 删除试压包失败: {e}")
            connection.rollback()
            return False
        finally:
            if connection:
                connection.close()
    
    @staticmethod
    def get_test_packages_by_status(status):
        """根据状态获取试压包"""
        try:
            ensure_hydro_columns()
        except Exception:
            pass
        # 同步一次，确保状态过滤有数据可查
        TestPackageModel._sync_from_weldinglist()
        connection = create_connection()
        if not connection:
            return []
        
        try:
            cursor = connection.cursor(dictionary=True)
            query = """
                SELECT t.*, 
                       sys.SystemDescriptionENG as SystemDescription,
                       sub.SubSystemDescriptionENG as SubSystemDescription
                FROM HydroTestPackageList t
                LEFT JOIN SystemList sys ON t.SystemCode = sys.SystemCode
                LEFT JOIN SubsystemList sub ON t.SubSystemCode = sub.SubSystemCode
                WHERE t.Status = %s
                ORDER BY t.PlannedDate, t.TestPackageID
            """
            cursor.execute(query, (status,))
            test_packages = cursor.fetchall()
            return test_packages
        except Error as e:
            print(f"❌ 根据状态获取试压包失败: {e}")
            return []
        finally:
            if connection:
                connection.close()