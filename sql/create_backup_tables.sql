-- ================================================
-- 数据备份与同步管理表
-- ================================================

-- 1. 数据备份记录表
CREATE TABLE IF NOT EXISTS DataBackup (
    BackupID INT AUTO_INCREMENT PRIMARY KEY COMMENT '备份ID',
    BackupType VARCHAR(20) NOT NULL COMMENT '备份类型：FULL-全量, INCREMENTAL-增量, MANUAL-手动',
    BackupTrigger VARCHAR(50) NOT NULL COMMENT '触发原因：SCHEDULED-定时, PRE_IMPORT-导入前, MANUAL-手动',
    BackupTime DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '备份时间',
    BackupBy VARCHAR(100) DEFAULT 'SYSTEM' COMMENT '备份执行者',
    
    -- 备份内容统计
    WeldingListCount INT DEFAULT 0 COMMENT 'WeldingList记录数',
    TestPackageCount INT DEFAULT 0 COMMENT '试压包记录数',
    SystemCount INT DEFAULT 0 COMMENT '系统记录数',
    SubsystemCount INT DEFAULT 0 COMMENT '子系统记录数',
    
    -- 备份文件信息
    BackupFilePath VARCHAR(500) COMMENT '备份文件路径（JSON格式存储多个表的备份路径）',
    BackupSize BIGINT COMMENT '备份大小（字节）',
    
    -- 备份状态
    Status VARCHAR(20) DEFAULT 'COMPLETED' COMMENT '状态：RUNNING, COMPLETED, FAILED',
    ErrorMessage TEXT COMMENT '错误信息（如果失败）',
    
    -- 备份保留策略
    IsRetained BOOLEAN DEFAULT TRUE COMMENT '是否保留（用于清理策略）',
    RetentionExpiry DATETIME COMMENT '保留到期日期',
    
    -- 备份描述
    Description VARCHAR(500) COMMENT '备份描述',
    
    INDEX idx_backup_time (BackupTime),
    INDEX idx_backup_type (BackupType),
    INDEX idx_status (Status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='数据备份记录表';


-- 2. 同步日志表
CREATE TABLE IF NOT EXISTS SyncLog (
    SyncID INT AUTO_INCREMENT PRIMARY KEY COMMENT '同步ID',
    SyncTime DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '同步时间',
    SyncType VARCHAR(50) NOT NULL COMMENT '同步类型：WELDING_IMPORT, MASTER_DATA_SYNC',
    
    -- 关联的备份
    BackupID INT COMMENT '关联的备份ID',
    
    -- 同步统计
    RecordsAdded INT DEFAULT 0 COMMENT '新增记录数',
    RecordsUpdated INT DEFAULT 0 COMMENT '更新记录数',
    RecordsDeleted INT DEFAULT 0 COMMENT '删除记录数（软删除）',
    RecordsSkipped INT DEFAULT 0 COMMENT '跳过记录数',
    
    -- 详细信息
    DetailsJSON TEXT COMMENT '详细信息（JSON格式）',
    
    -- 同步状态
    Status VARCHAR(20) DEFAULT 'COMPLETED' COMMENT '状态：RUNNING, COMPLETED, FAILED, PARTIAL',
    ErrorMessage TEXT COMMENT '错误信息',
    
    -- 执行时间
    StartTime DATETIME COMMENT '开始时间',
    EndTime DATETIME COMMENT '结束时间',
    Duration INT COMMENT '持续时间（秒）',
    
    FOREIGN KEY (BackupID) REFERENCES DataBackup(BackupID) ON DELETE SET NULL,
    INDEX idx_sync_time (SyncTime),
    INDEX idx_sync_type (SyncType),
    INDEX idx_status (Status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='数据同步日志表';


-- 3. 变更日志表（用于审计和追踪）
CREATE TABLE IF NOT EXISTS ChangeLog (
    ChangeID INT AUTO_INCREMENT PRIMARY KEY COMMENT '变更ID',
    ChangeTime DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '变更时间',
    
    -- 变更对象
    TableName VARCHAR(100) NOT NULL COMMENT '表名',
    RecordID VARCHAR(100) NOT NULL COMMENT '记录ID',
    
    -- 变更类型
    ChangeType VARCHAR(20) NOT NULL COMMENT '变更类型：INSERT, UPDATE, DELETE, SOFT_DELETE, RESTORE',
    
    -- 变更内容
    FieldName VARCHAR(100) COMMENT '字段名（UPDATE时）',
    OldValue TEXT COMMENT '旧值',
    NewValue TEXT COMMENT '新值',
    
    -- 变更来源
    ChangedBy VARCHAR(100) COMMENT '变更者',
    ChangeSource VARCHAR(50) COMMENT '变更来源：USER, SYSTEM, IMPORT, SYNC',
    
    -- 关联的同步
    SyncID INT COMMENT '关联的同步ID',
    
    -- 备注
    Remarks VARCHAR(500) COMMENT '备注',
    
    FOREIGN KEY (SyncID) REFERENCES SyncLog(SyncID) ON DELETE SET NULL,
    INDEX idx_change_time (ChangeTime),
    INDEX idx_table_record (TableName, RecordID),
    INDEX idx_change_type (ChangeType)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='数据变更日志表';

-- 4. 试压包编制提醒表
CREATE TABLE IF NOT EXISTS TestPackagePreparationAlert (
    AlertID INT AUTO_INCREMENT PRIMARY KEY COMMENT '提醒ID',
    SystemCode VARCHAR(50) NOT NULL COMMENT '系统代码/介质',
    PipelineNumber VARCHAR(100) NOT NULL COMMENT '管线号',
    TotalDIN DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT '该管线总DIN',
    CompletedDIN DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT '该管线完成DIN',
    CompletionRate DECIMAL(5,4) NOT NULL DEFAULT 0 COMMENT '管线完成率',
    SystemDINShare DECIMAL(5,4) NOT NULL DEFAULT 0 COMMENT '完成管线占系统DIN的比例',
    ThresholdMet TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否达到系统阈值',
    CreatedAt DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '生成时间',
    Status VARCHAR(20) DEFAULT 'PENDING' COMMENT '状态：PENDING/ACKED/IGNORED',
    Remarks VARCHAR(255) COMMENT '备注',
    INDEX idx_alert_system (SystemCode),
    INDEX idx_alert_status (Status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='试压包编制提醒表';


-- 5. 为主数据表添加软删除和同步相关字段
-- HydroTestPackageList
ALTER TABLE HydroTestPackageList 
ADD COLUMN IF NOT EXISTS IsDeleted BOOLEAN DEFAULT FALSE COMMENT '是否软删除',
ADD COLUMN IF NOT EXISTS DeletedTime DATETIME COMMENT '删除时间',
ADD COLUMN IF NOT EXISTS LastSyncTime DATETIME COMMENT '最后同步时间',
ADD COLUMN IF NOT EXISTS DataSource VARCHAR(50) DEFAULT 'WELDING_LIST' COMMENT '数据来源：WELDING_LIST, MANUAL',
ADD COLUMN IF NOT EXISTS IsManuallyModified BOOLEAN DEFAULT FALSE COMMENT '是否手动修改过',
ADD INDEX IF NOT EXISTS idx_is_deleted (IsDeleted),
ADD INDEX IF NOT EXISTS idx_last_sync (LastSyncTime);

-- SystemList
ALTER TABLE SystemList 
ADD COLUMN IF NOT EXISTS IsDeleted BOOLEAN DEFAULT FALSE COMMENT '是否软删除',
ADD COLUMN IF NOT EXISTS DeletedTime DATETIME COMMENT '删除时间',
ADD COLUMN IF NOT EXISTS LastSyncTime DATETIME COMMENT '最后同步时间',
ADD COLUMN IF NOT EXISTS DataSource VARCHAR(50) DEFAULT 'WELDING_LIST' COMMENT '数据来源',
ADD COLUMN IF NOT EXISTS IsManuallyModified BOOLEAN DEFAULT FALSE COMMENT '是否手动修改过',
ADD INDEX IF NOT EXISTS idx_is_deleted (IsDeleted),
ADD INDEX IF NOT EXISTS idx_last_sync (LastSyncTime);

-- SubsystemList
ALTER TABLE SubsystemList 
ADD COLUMN IF NOT EXISTS IsDeleted BOOLEAN DEFAULT FALSE COMMENT '是否软删除',
ADD COLUMN IF NOT EXISTS DeletedTime DATETIME COMMENT '删除时间',
ADD COLUMN IF NOT EXISTS LastSyncTime DATETIME COMMENT '最后同步时间',
ADD COLUMN IF NOT EXISTS DataSource VARCHAR(50) DEFAULT 'WELDING_LIST' COMMENT '数据来源',
ADD COLUMN IF NOT EXISTS IsManuallyModified BOOLEAN DEFAULT FALSE COMMENT '是否手动修改过',
ADD INDEX IF NOT EXISTS idx_is_deleted (IsDeleted),
ADD INDEX IF NOT EXISTS idx_last_sync (LastSyncTime);

-- WeldingList（添加标记字段）
ALTER TABLE WeldingList
ADD COLUMN IF NOT EXISTS IsDeleted BOOLEAN DEFAULT FALSE COMMENT '是否软删除',
ADD COLUMN IF NOT EXISTS DeletedTime DATETIME COMMENT '删除时间',
ADD INDEX IF NOT EXISTS idx_is_deleted (IsDeleted);


-- 5. 创建视图：仅显示未删除的记录
CREATE OR REPLACE VIEW ActiveTestPackages AS
SELECT * FROM HydroTestPackageList WHERE IsDeleted = FALSE;

CREATE OR REPLACE VIEW ActiveSystems AS
SELECT * FROM SystemList WHERE IsDeleted = FALSE;

CREATE OR REPLACE VIEW ActiveSubsystems AS
SELECT * FROM SubsystemList WHERE IsDeleted = FALSE;

CREATE OR REPLACE VIEW ActiveWelding AS
SELECT * FROM WeldingList WHERE IsDeleted = FALSE;

