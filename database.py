import os
import mysql.connector
from mysql.connector import Error, pooling
from mysql.connector.pooling import MySQLConnectionPool
import threading
import logging
from config import DB_CONFIG

# 配置数据库模块的日志记录器
db_logger = logging.getLogger('database')

# 全局连接池
_connection_pool = None
_pool_lock = threading.Lock()

def ensure_hydro_columns():
    """Ensure HydroTestPackageList has SystemCode/SubSystemCode columns."""
    connection = create_connection()
    if not connection:
        return False
    try:
        cursor = connection.cursor()
        cursor.execute("SHOW TABLES LIKE 'HydroTestPackageList'")
        if not cursor.fetchone():
            return False
        cursor.execute("SHOW COLUMNS FROM HydroTestPackageList LIKE 'SystemCode'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE HydroTestPackageList ADD COLUMN SystemCode VARCHAR(512) NULL AFTER TestPackageID")
        cursor.execute("SHOW COLUMNS FROM HydroTestPackageList LIKE 'SubSystemCode'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE HydroTestPackageList ADD COLUMN SubSystemCode VARCHAR(512) NULL AFTER SystemCode")
        connection.commit()
        return True
    except Error:
        return False
    finally:
        if connection:
            connection.close()

def init_connection_pool():
    """初始化数据库连接池（生产环境推荐）"""
    global _connection_pool
    if _connection_pool is not None:
        return _connection_pool
    
    with _pool_lock:
        if _connection_pool is not None:
            return _connection_pool
        
        try:
            # 连接池配置：MySQL 官方 MySQLConnectionPool 最大值为 32
            requested_size = int(os.environ.get('DB_POOL_SIZE', '32'))
            pool_size = max(1, min(requested_size, 32))
            pool_config = {
                **DB_CONFIG,
                'pool_name': 'precom_pool',
                'pool_size': pool_size,
                'pool_reset_session': True,  # 重置会话状态
                'autocommit': False,  # 手动提交事务
                'allow_local_infile': True
            }
            _connection_pool = MySQLConnectionPool(**pool_config)
            db_logger.info(f"连接池初始化成功，池大小: {pool_config['pool_size']}")
            print(f"[DB] 连接池初始化成功，池大小: {pool_config['pool_size']}")
            return _connection_pool
        except Error as e:
            db_logger.error(f"连接池初始化失败: {e}", exc_info=True)
            print(f"[DB] 连接池初始化失败: {e}")
            return None

def create_connection(use_pool=True):
    """创建数据库连接（优先使用连接池）"""
    global _connection_pool
    
    # 优先使用连接池（生产环境）
    if use_pool:
        if _connection_pool is None:
            init_connection_pool()
        
        if _connection_pool is not None:
            try:
                connection = _connection_pool.get_connection()
                if connection.is_connected():
                    return connection
            except Error as e:
                db_logger.error(f"从连接池获取连接失败: {e}", exc_info=True)
                print(f"[DB] 从连接池获取连接失败: {e}")
                # 连接池失败时回退到直接连接
                pass
    
    # 回退到直接连接（开发环境或连接池不可用时）
    try:
        connection = mysql.connector.connect(allow_local_infile=True, **DB_CONFIG)
        if connection.is_connected():
            return connection
    except Error as e:
        db_logger.error(f"直接连接失败: {e}", exc_info=True)
        print(f"[DB] 直接连接失败: {e}")
        return None
    
    return None

def init_database():
    """初始化数据库表"""
    connection = create_connection()
    if not connection:
        return False
    
    cursor = None
    try:
        cursor = connection.cursor()
        
        # 创建SystemList表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS SystemList (
                SystemCode VARCHAR(512) PRIMARY KEY,
                SystemDescriptionENG VARCHAR(255) NOT NULL,
                SystemDescriptionRUS VARCHAR(255),
                ProcessOrNonProcess ENUM('Process', 'NonProcess') NOT NULL,
                Priority INT DEFAULT 0,
                Remarks TEXT,
                created_by VARCHAR(255),
                last_updated_by VARCHAR(255),
                updateDate TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_process_type (ProcessOrNonProcess),
                INDEX idx_priority (Priority)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)
        
        # 创建SubsystemList表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS SubsystemList (
                SubSystemCode VARCHAR(512) PRIMARY KEY,
                SystemCode VARCHAR(512) NOT NULL,
                SubSystemDescriptionENG VARCHAR(255) NOT NULL,
                SubSystemDescriptionRUS VARCHAR(255),
                ProcessOrNonProcess ENUM('Process', 'NonProcess') NOT NULL,
                Priority INT DEFAULT 0,
                Remarks TEXT,
                created_by VARCHAR(255),
                last_updated_by VARCHAR(255),
                updateDate TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                FOREIGN KEY (SystemCode) REFERENCES SystemList(SystemCode) ON DELETE CASCADE,
                INDEX idx_system_code (SystemCode),
                INDEX idx_process_type (ProcessOrNonProcess)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)
        
        # 创建HydroTestPackageList表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS HydroTestPackageList (
                TestPackageID VARCHAR(512) PRIMARY KEY,
                SystemCode VARCHAR(512) NOT NULL,
                SubSystemCode VARCHAR(512) NOT NULL,
                Description VARCHAR(255) NOT NULL,
                PlannedDate DATE,
                ActualDate DATE,
                Status ENUM('Pending', 'InProgress', 'Completed', 'Hold') DEFAULT 'Pending',
                Pressure DECIMAL(10, 2),
                TestDuration INT COMMENT 'Duration in minutes',
                Remarks TEXT,
                created_by VARCHAR(255),
                last_updated_by VARCHAR(255),
                updateDate TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                FOREIGN KEY (SystemCode) REFERENCES SystemList(SystemCode),
                FOREIGN KEY (SubSystemCode) REFERENCES SubsystemList(SubSystemCode),
                INDEX idx_status (Status),
                INDEX idx_planned_date (PlannedDate)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)
        
        cursor.execute("""
            CREATE TABLE WeldingList (
                WeldID VARCHAR(50) PRIMARY KEY,  -- 焊口唯一标识
                TestPackageID VARCHAR(50),       -- 关联试压包ID
                SystemCode VARCHAR(50),          -- 关联系统代码
                SubSystemCode VARCHAR(50),       -- 关联子系统代码
                WeldDate DATE,                   -- 焊接日期
                Size DECIMAL(10,2),              -- 尺寸(DIN)
                WelderID VARCHAR(50),            -- 焊工ID
                WPSNumber VARCHAR(50),           -- 焊接工艺规程编号
                VTResult VARCHAR(20),            -- VT检测结果
                RTResult VARCHAR(20),            -- RT检测结果
                UTResult VARCHAR(20),            -- UT检测结果
                PTResult VARCHAR(20),            -- PT检测结果
                MTResult VARCHAR(20),            -- MT检测结果
                Remarks TEXT,                    -- 备注
                created_by VARCHAR(50),          -- 创建人
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (TestPackageID) REFERENCES HydroTestPackageList(TestPackageID),
                FOREIGN KEY (SystemCode) REFERENCES SystemList(SystemCode),
                FOREIGN KEY (SubSystemCode) REFERENCES SubsystemList(SubSystemCode)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;;
        """)


        connection.commit()
        print("[DB] Tables initialized successfully")
        return True
        
    except Error as e:
        print(f"[DB] Init tables failed: {e}")
        return False
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

def create_welding_table():
    """创建焊接数据表（不包含外键）"""
    connection = create_connection()
    if not connection:
        return False
    
    try:
        cursor = connection.cursor(buffered=True)  # 使用 buffered cursor 避免 Unread result
        # 创建焊接表（字段对应Excel列）
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS WeldingList (
                WeldID VARCHAR(255) PRIMARY KEY,  -- 焊缝编号（主键，放宽长度）
                SystemCode VARCHAR(512),         -- 系统代码（来自Excel"介质"）
                SubSystemCode VARCHAR(512),      -- 子系统代码（来自Excel"子系统"或派生）
                DrawingNumber VARCHAR(255),      -- 图纸号
                PipelineNumber VARCHAR(50),      -- 管线号
                TestPackageID VARCHAR(512),      -- 试压包号
                WeldDate DATE,                   -- 焊接日期
                Size DECIMAL(10,2),              -- 尺寸(DIN)
                WelderRoot VARCHAR(50),          -- 焊工号根层
                WelderFill VARCHAR(50),          -- 焊工号填充、盖面
                WPSNumber VARCHAR(50),           -- WPS编号
                VTResult VARCHAR(20),            -- VT检测结果
                RTResult VARCHAR(20),            -- RT检测结果
                UTResult VARCHAR(20),            -- UT检测结果
                PTResult VARCHAR(20),            -- PT检测结果
                MTResult VARCHAR(20),            -- MT检测结果
                PMIResult VARCHAR(20),           -- PMI检测结果
                FTResult VARCHAR(20),            -- FT检测结果
                Status VARCHAR(20),              -- 状态（已完成/未完成）
                ImportDate TIMESTAMP DEFAULT CURRENT_TIMESTAMP  -- 导入时间
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)
        # 兼容已存在的旧表：确保 DrawingNumber 存在（兼容不支持 IF NOT EXISTS 的版本）
        try:
            cursor.execute("SHOW COLUMNS FROM WeldingList LIKE 'DrawingNumber'")
            col = cursor.fetchone()
            if not col:
                cursor.execute("ALTER TABLE WeldingList ADD COLUMN DrawingNumber VARCHAR(255) AFTER WeldID")
                connection.commit()
        except Error:
            pass
            
        # 兼容已存在的旧表：放宽 WeldID 长度到 255
        try:
            cursor.execute("SHOW COLUMNS FROM WeldingList LIKE 'WeldID'")
            col = cursor.fetchone()
            # col[1] 是类型定义，如 'varchar(50)'
            if col and isinstance(col[1], str) and 'varchar' in col[1].lower() and '255' not in col[1]:
                cursor.execute("ALTER TABLE WeldingList MODIFY COLUMN WeldID VARCHAR(255) NOT NULL")
                connection.commit()
        except Error:
            pass
            
        # 兼容已存在的旧表：确保 WeldJoint 存在
        try:
            cursor.execute("SHOW COLUMNS FROM WeldingList LIKE 'WeldJoint'")
            col = cursor.fetchone()
            if not col:
                cursor.execute("ALTER TABLE WeldingList ADD COLUMN WeldJoint VARCHAR(255) AFTER WeldID")
                connection.commit()
        except Error:
            pass
        # 兼容已存在的旧表：确保 SystemCode/SubSystemCode 存在
        try:
            cursor.execute("SHOW COLUMNS FROM WeldingList LIKE 'SystemCode'")
            result = cursor.fetchone()
            if not result:
                cursor.execute("ALTER TABLE WeldingList ADD COLUMN SystemCode VARCHAR(512) AFTER WeldID")
                connection.commit()
                
            cursor.execute("SHOW COLUMNS FROM WeldingList LIKE 'SubSystemCode'")
            result = cursor.fetchone()
            if not result:
                cursor.execute("ALTER TABLE WeldingList ADD COLUMN SubSystemCode VARCHAR(512) AFTER SystemCode")
                connection.commit()
        except Error:
            pass

        # 兼容旧表：放宽 SystemCode / SubSystemCode / TestPackageID 长度，避免长代码溢出
        try:
            cursor.execute("SHOW COLUMNS FROM WeldingList LIKE 'SystemCode'")
            col = cursor.fetchone()
            if col and isinstance(col[1], str) and 'varchar' in col[1].lower() and '512' not in col[1]:
                cursor.execute("ALTER TABLE WeldingList MODIFY COLUMN SystemCode VARCHAR(512)")
                connection.commit()
        except Error:
            pass

        try:
            cursor.execute("SHOW COLUMNS FROM WeldingList LIKE 'SubSystemCode'")
            col = cursor.fetchone()
            if col and isinstance(col[1], str) and 'varchar' in col[1].lower() and '512' not in col[1]:
                cursor.execute("ALTER TABLE WeldingList MODIFY COLUMN SubSystemCode VARCHAR(512)")
                connection.commit()
        except Error:
            pass

        try:
            cursor.execute("SHOW COLUMNS FROM WeldingList LIKE 'TestPackageID'")
            col = cursor.fetchone()
            if col and isinstance(col[1], str) and 'varchar' in col[1].lower() and '512' not in col[1]:
                cursor.execute("ALTER TABLE WeldingList MODIFY COLUMN TestPackageID VARCHAR(512)")
                connection.commit()
        except Error:
            pass

        # 兼容：确保 JointStatus 列存在且长度为 512
        try:
            cursor.execute("SHOW COLUMNS FROM WeldingList LIKE 'JointStatus'")
            col = cursor.fetchone()
            if not col:
                cursor.execute("ALTER TABLE WeldingList ADD COLUMN JointStatus VARCHAR(512) NULL COMMENT '焊口状态' AFTER Status")
                connection.commit()
            else:
                col_type = col[1] if isinstance(col[1], str) else ''
                if 'varchar' in col_type.lower() and '512' not in col_type:
                    cursor.execute("ALTER TABLE WeldingList MODIFY COLUMN JointStatus VARCHAR(512) NULL COMMENT '焊口状态'")
                    connection.commit()
        except Error:
            pass

        # 兼容：确保 HydroTestPackageList 存在 SystemCode/SubSystemCode 列，并放宽长度
        try:
            cursor.execute("SHOW TABLES LIKE 'HydroTestPackageList'")
            table_exists = cursor.fetchone()
            if table_exists:
                cursor.execute("SHOW COLUMNS FROM HydroTestPackageList LIKE 'SystemCode'")
                result = cursor.fetchone()
                if not result:
                    cursor.execute("ALTER TABLE HydroTestPackageList ADD COLUMN SystemCode VARCHAR(512) NULL AFTER TestPackageID")
                    connection.commit()
                    
                cursor.execute("SHOW COLUMNS FROM HydroTestPackageList LIKE 'SubSystemCode'")
                result = cursor.fetchone()
                if not result:
                    cursor.execute("ALTER TABLE HydroTestPackageList ADD COLUMN SubSystemCode VARCHAR(512) NULL AFTER SystemCode")
                    connection.commit()
        except Error:
            pass

        
        # 添加性能优化索引（分别提交避免冲突）
        try:
            # TestPackageID 索引（用于 GROUP BY 和 JOIN）
            cursor.execute("SHOW INDEX FROM WeldingList WHERE Key_name = 'idx_testpackageid'")
            result = cursor.fetchone()
            if not result:
                cursor.execute("CREATE INDEX idx_testpackageid ON WeldingList(TestPackageID)")
                connection.commit()
            
            # DrawingNumber 索引（用于 Block 匹配）
            cursor.execute("SHOW INDEX FROM WeldingList WHERE Key_name = 'idx_drawingnumber'")
            result = cursor.fetchone()
            if not result:
                cursor.execute("CREATE INDEX idx_drawingnumber ON WeldingList(DrawingNumber)")
                connection.commit()
            
            # SystemCode 和 SubSystemCode 索引（用于筛选）
            cursor.execute("SHOW INDEX FROM WeldingList WHERE Key_name = 'idx_systemcode'")
            result = cursor.fetchone()
            if not result:
                cursor.execute("CREATE INDEX idx_systemcode ON WeldingList(SystemCode)")
                connection.commit()
            
            cursor.execute("SHOW INDEX FROM WeldingList WHERE Key_name = 'idx_subsystemcode'")
            result = cursor.fetchone()
            if not result:
                cursor.execute("CREATE INDEX idx_subsystemcode ON WeldingList(SubSystemCode)")
                connection.commit()
            
            # 复合索引用于常见查询
            cursor.execute("SHOW INDEX FROM WeldingList WHERE Key_name = 'idx_testpackage_status'")
            result = cursor.fetchone()
            if not result:
                cursor.execute("CREATE INDEX idx_testpackage_status ON WeldingList(TestPackageID, Status)")
                connection.commit()
        except Error as e:
            print(f"WARNING: Index creation warning (may already exist): {e}")
        
        connection.commit()
        print("SUCCESS: WeldingList table created")
        return True
    except Error as e:
        print(f"ERROR: Failed to create WeldingList table: {e}")
        return False
    finally:
        if connection:
            connection.close()

def create_faclist_table():
    """创建Faclist表（区域信息表）"""
    connection = create_connection()
    if not connection:
        return False
    
    try:
        cursor = connection.cursor()
        # 创建Faclist表，包含区域信息字段
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS Faclist (
                FaclistID INT AUTO_INCREMENT PRIMARY KEY,
                Block VARCHAR(255),
                Project VARCHAR(255),
                SubProjectCode VARCHAR(255),
                Train VARCHAR(50),
                Unit VARCHAR(50),
                MainBlock VARCHAR(255),
                Descriptions TEXT,
                SimpleBLK VARCHAR(255),
                BCCQuarter VARCHAR(50),
                BCCStartUpSequence VARCHAR(50),
                TitleType VARCHAR(50),
                DrawingNumber VARCHAR(255),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_block (Block),
                INDEX idx_drawing_number (DrawingNumber),
                INDEX idx_project (Project)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)
        
        # 兼容已存在的表：如果 Descriptions 字段是 VARCHAR，改为 TEXT
        try:
            cursor.execute("SHOW COLUMNS FROM Faclist LIKE 'Descriptions'")
            col = cursor.fetchone()
            if col and 'varchar' in col[1].lower():
                cursor.execute("ALTER TABLE Faclist MODIFY COLUMN Descriptions TEXT")
                print("[DB] Updated Faclist.Descriptions to TEXT")
        except Error:
            pass  # 表可能不存在或字段已经是 TEXT
        
        connection.commit()
        print("[DB] Faclist table ensured")
        return True
    except Error as e:
        print(f"[DB] Ensure Faclist failed: {e}")
        return False
    finally:
        if connection:
            connection.close()


def ensure_user_management_tables():
    """创建或更新用户/权限相关数据表"""
    connection = create_connection()
    if not connection:
        return False
    try:
        cursor = connection.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS UserAccount (
                UserID INT AUTO_INCREMENT PRIMARY KEY,
                Username VARCHAR(50) NOT NULL UNIQUE,
                FullName VARCHAR(255),
                Email VARCHAR(150),
                Phone VARCHAR(50),
                PasswordHash VARCHAR(255) NOT NULL,
                IsActive TINYINT(1) NOT NULL DEFAULT 1,
                IsSuperAdmin TINYINT(1) NOT NULL DEFAULT 0,
                FailedLoginAttempts INT NOT NULL DEFAULT 0,
                LockedUntil DATETIME NULL,
                LastLoginAt DATETIME NULL,
                LastLoginIP VARCHAR(64),
                CreatedBy VARCHAR(50),
                UpdatedBy VARCHAR(50),
                CreatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UpdatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_username (Username),
                INDEX idx_email (Email)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS Role (
                RoleID INT AUTO_INCREMENT PRIMARY KEY,
                RoleName VARCHAR(255) NOT NULL UNIQUE,
                Description VARCHAR(255),
                IsSystemRole TINYINT(1) NOT NULL DEFAULT 0,
                CreatedBy VARCHAR(50),
                UpdatedBy VARCHAR(50),
                CreatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UpdatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS Permission (
                PermissionID INT AUTO_INCREMENT PRIMARY KEY,
                PermissionCode VARCHAR(255) NOT NULL UNIQUE,
                ModuleName VARCHAR(255) NOT NULL,
                DisplayName VARCHAR(150) NOT NULL,
                Description VARCHAR(255),
                CreatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UpdatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_module (ModuleName)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS UserRole (
                UserRoleID INT AUTO_INCREMENT PRIMARY KEY,
                UserID INT NOT NULL,
                RoleID INT NOT NULL,
                CreatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY uq_user_role (UserID, RoleID),
                CONSTRAINT fk_userrole_user FOREIGN KEY (UserID) REFERENCES UserAccount(UserID) ON DELETE CASCADE,
                CONSTRAINT fk_userrole_role FOREIGN KEY (RoleID) REFERENCES Role(RoleID) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS RolePermission (
                RolePermissionID INT AUTO_INCREMENT PRIMARY KEY,
                RoleID INT NOT NULL,
                PermissionID INT NOT NULL,
                CreatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY uq_role_permission (RoleID, PermissionID),
                CONSTRAINT fk_rolepermission_role FOREIGN KEY (RoleID) REFERENCES Role(RoleID) ON DELETE CASCADE,
                CONSTRAINT fk_rolepermission_permission FOREIGN KEY (PermissionID) REFERENCES Permission(PermissionID) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS AuditLog (
                AuditID BIGINT AUTO_INCREMENT PRIMARY KEY,
                UserID INT NULL,
                UsernameSnapshot VARCHAR(255),
                ActionCode VARCHAR(255) NOT NULL,
                ActionName VARCHAR(150),
                TargetType VARCHAR(255),
                TargetID VARCHAR(255),
                RequestMethod VARCHAR(10),
                RequestPath VARCHAR(255),
                RequestPayload LONGTEXT,
                ClientIP VARCHAR(64),
                UserAgent VARCHAR(255),
                Remark VARCHAR(255),
                CreatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_action_code (ActionCode),
                INDEX idx_target (TargetType, TargetID),
                INDEX idx_created_at (CreatedAt),
                CONSTRAINT fk_auditlog_user FOREIGN KEY (UserID) REFERENCES UserAccount(UserID) ON DELETE SET NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)
        # 模块权限表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ModulePermission (
                ModuleID INT AUTO_INCREMENT PRIMARY KEY,
                ModuleCode VARCHAR(50) NOT NULL UNIQUE,
                ModuleName VARCHAR(255) NOT NULL,
                DisplayName VARCHAR(150) NOT NULL,
                Description VARCHAR(255),
                IconClass VARCHAR(255),
                RoutePath VARCHAR(255),
                DisplayOrder INT DEFAULT 0,
                IsActive TINYINT(1) NOT NULL DEFAULT 1,
                CreatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UpdatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_module_code (ModuleCode),
                INDEX idx_display_order (DisplayOrder)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)
        # 用户模块权限表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS UserModulePermission (
                UserModulePermissionID INT AUTO_INCREMENT PRIMARY KEY,
                UserID INT NOT NULL,
                ModuleID INT NOT NULL,
                CreatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY uq_user_module (UserID, ModuleID),
                CONSTRAINT fk_usermodule_user FOREIGN KEY (UserID) REFERENCES UserAccount(UserID) ON DELETE CASCADE,
                CONSTRAINT fk_usermodule_module FOREIGN KEY (ModuleID) REFERENCES ModulePermission(ModuleID) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)
        # 角色模块权限表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS RoleModulePermission (
                RoleModulePermissionID INT AUTO_INCREMENT PRIMARY KEY,
                RoleID INT NOT NULL,
                ModuleID INT NOT NULL,
                CreatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY uq_role_module (RoleID, ModuleID),
                CONSTRAINT fk_rolemodule_role FOREIGN KEY (RoleID) REFERENCES Role(RoleID) ON DELETE CASCADE,
                CONSTRAINT fk_rolemodule_module FOREIGN KEY (ModuleID) REFERENCES ModulePermission(ModuleID) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)
        connection.commit()
        return True
    except Error as e:
        print(f"[DB] ensure_user_management_tables failed: {e}")
        return False
    finally:
        if connection:
            connection.close()


def ensure_precom_tables():
    """创建或更新预试车任务相关表（PrecomTask / PrecomTaskAttachment / PrecomTaskPunch）"""
    connection = create_connection()
    if not connection:
        return False

    try:
        cursor = connection.cursor()

        # 预试车任务主表
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS PrecomTask (
                TaskID INT AUTO_INCREMENT PRIMARY KEY,
                TaskType VARCHAR(50) NOT NULL COMMENT '任务类型：Manhole/MotorSolo/SkidInstall/LoopTest/Alignment/MRT/FunctionTest 等',
                SystemCode VARCHAR(50) NULL,
                SubSystemCode VARCHAR(50) NOT NULL,
                DrawingNumber VARCHAR(255) NULL COMMENT '图纸号 / Vendor Print',
                TagNumber VARCHAR(255) NULL COMMENT '设备位号 / 电机位号 / Skid Tag',
                PointTag VARCHAR(255) NULL COMMENT '回路中的仪表点位（Loop 测试用）',
                Description VARCHAR(255) NULL COMMENT '对象描述',
                PositionBlock VARCHAR(255) NULL COMMENT '位置信息，通常来自 Faclist.Block/MainBlock',
                QuantityTotal INT NOT NULL DEFAULT 1 COMMENT '总数量',
                QuantityDone INT NOT NULL DEFAULT 0 COMMENT '已完成数量',
                PlannedDate DATETIME NULL COMMENT '测试计划时间',
                ActualDate DATETIME NULL COMMENT '测试实际时间',
                PerformedBy VARCHAR(255) NULL COMMENT '执行人',
                TestType VARCHAR(50) NULL COMMENT '测试类型（用于 Loop/MRT/FunctionTest 等）',
                -- 施工进度信息（预留字段，供后续统计使用）
                ProgressID VARCHAR(255) NULL COMMENT '施工进度 ID / 工作包 ID / WBS',
                Discipline VARCHAR(255) NULL COMMENT '专业',
                WorkPackage VARCHAR(255) NULL COMMENT '工作包名称',
                KeyQuantityTotal INT NULL COMMENT '关键工程量总量',
                KeyQuantityDone INT NULL COMMENT '关键工程量完成量',
                KeyProgressPercent DECIMAL(5,2) NULL COMMENT '关键工程量完成比例（%）',
                CreatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UpdatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_precom_type (TaskType),
                INDEX idx_precom_subsystem (SubSystemCode),
                INDEX idx_precom_block (PositionBlock),
                INDEX idx_precom_system (SystemCode)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """
        )

        # 预试车任务附件表
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS PrecomTaskAttachment (
                AttachmentID INT AUTO_INCREMENT PRIMARY KEY,
                TaskID INT NOT NULL,
                FileName VARCHAR(255) NOT NULL,
                FilePath VARCHAR(512) NOT NULL,
                FileSize BIGINT NULL,
                UploadedBy VARCHAR(255) NULL,
                UploadedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                ModuleName VARCHAR(255) NULL COMMENT '附件类型：Report/Checklist/Photos 等',
                INDEX idx_precom_attachment_task (TaskID),
                CONSTRAINT fk_precom_attachment_task FOREIGN KEY (TaskID)
                    REFERENCES PrecomTask(TaskID) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """
        )

        # 预试车任务 Punch / 尾项表
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS PrecomTaskPunch (
                ID INT AUTO_INCREMENT PRIMARY KEY,
                TaskID INT NOT NULL,
                PunchNo VARCHAR(255) NULL,
                RefNo VARCHAR(255) NULL COMMENT '参考号：ISO / Tag No.',
                SheetNo VARCHAR(255) NULL,
                RevNo VARCHAR(50) NULL,
                Description TEXT NOT NULL,
                Category VARCHAR(255) NULL,
                Cause VARCHAR(255) NULL,
                IssuedBy VARCHAR(255) NULL,
                Rectified CHAR(1) NOT NULL DEFAULT 'N',
                RectifiedDate DATETIME NULL,
                Verified CHAR(1) NOT NULL DEFAULT 'N',
                VerifiedDate DATETIME NULL,
                CreatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UpdatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_precom_punch_task (TaskID),
                INDEX idx_precom_punch_no (PunchNo),
                CONSTRAINT fk_precom_punch_task FOREIGN KEY (TaskID)
                    REFERENCES PrecomTask(TaskID) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """
        )
        # 兼容已有旧表：为 Punch 表补充 SheetNo / RevNo 列（兼容不支持 IF NOT EXISTS 的版本）
        try:
            cursor.execute("SHOW COLUMNS FROM PrecomTaskPunch LIKE 'SheetNo'")
            col = cursor.fetchone()
            if not col:
                cursor.execute(
                    "ALTER TABLE PrecomTaskPunch ADD COLUMN SheetNo VARCHAR(255) NULL AFTER RefNo"
                )
                connection.commit()
        except Error:
            pass

        try:
            cursor.execute("SHOW COLUMNS FROM PrecomTaskPunch LIKE 'RevNo'")
            col = cursor.fetchone()
            if not col:
                cursor.execute(
                    "ALTER TABLE PrecomTaskPunch ADD COLUMN RevNo VARCHAR(50) NULL AFTER SheetNo"
                )
                connection.commit()
        except Error:
            pass

        # 预试车任务施工活动表（关键工程量明细，可多条）
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS PrecomTaskActivity (
                ID INT AUTO_INCREMENT PRIMARY KEY,
                TaskID INT NOT NULL,
                ActID VARCHAR(255) NULL COMMENT '施工任务 ID / ACT ID',
                Block VARCHAR(255) NULL COMMENT '关联 Block',
                ActDescription VARCHAR(512) NULL COMMENT '施工任务描述',
                Scope VARCHAR(255) NULL COMMENT 'SCOPE / 范围',
                Discipline VARCHAR(255) NULL COMMENT '专业',
                WorkPackage VARCHAR(255) NULL COMMENT '工作包',
                WeightFactor DECIMAL(10,2) NULL COMMENT '权重因子',
                ManHours DECIMAL(10,2) NULL COMMENT '工时',
                Subproject VARCHAR(255) NULL COMMENT '子项目',
                CreatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UpdatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_precom_activity_task (TaskID),
                CONSTRAINT fk_precom_activity_task FOREIGN KEY (TaskID)
                    REFERENCES PrecomTask(TaskID) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """
        )

        # 兼容已有旧表：为 PrecomTask 表补充施工进度相关列
        try:
            cursor.execute("SHOW COLUMNS FROM PrecomTask LIKE 'ProgressID'")
            col = cursor.fetchone()
            if not col:
                cursor.execute(
                    "ALTER TABLE PrecomTask ADD COLUMN ProgressID VARCHAR(255) NULL AFTER TestType"
                )
                connection.commit()
        except Error:
            pass

        try:
            cursor.execute("SHOW COLUMNS FROM PrecomTask LIKE 'Discipline'")
            col = cursor.fetchone()
            if not col:
                cursor.execute(
                    "ALTER TABLE PrecomTask ADD COLUMN Discipline VARCHAR(255) NULL AFTER ProgressID"
                )
                connection.commit()
        except Error:
            pass

        try:
            cursor.execute("SHOW COLUMNS FROM PrecomTask LIKE 'WorkPackage'")
            col = cursor.fetchone()
            if not col:
                cursor.execute(
                    "ALTER TABLE PrecomTask ADD COLUMN WorkPackage VARCHAR(255) NULL AFTER Discipline"
                )
                connection.commit()
        except Error:
            pass

        try:
            cursor.execute("SHOW COLUMNS FROM PrecomTask LIKE 'KeyQuantityTotal'")
            col = cursor.fetchone()
            if not col:
                cursor.execute(
                    "ALTER TABLE PrecomTask ADD COLUMN KeyQuantityTotal INT NULL AFTER WorkPackage"
                )
                connection.commit()
        except Error:
            pass

        try:
            cursor.execute("SHOW COLUMNS FROM PrecomTask LIKE 'KeyQuantityDone'")
            col = cursor.fetchone()
            if not col:
                cursor.execute(
                    "ALTER TABLE PrecomTask ADD COLUMN KeyQuantityDone INT NULL AFTER KeyQuantityTotal"
                )
                connection.commit()
        except Error:
            pass

        try:
            cursor.execute("SHOW COLUMNS FROM PrecomTask LIKE 'KeyProgressPercent'")
            col = cursor.fetchone()
            if not col:
                cursor.execute(
                    "ALTER TABLE PrecomTask ADD COLUMN KeyProgressPercent DECIMAL(5,2) NULL AFTER KeyQuantityDone"
                )
                connection.commit()
        except Error:
            pass

        connection.commit()
        print("[DB] PrecomTask tables ensured successfully")
        return True
    except Error as e:
        print(f"[DB] ensure_precom_tables failed: {e}")
        return False
    finally:
        if connection:
            connection.close()