-- 扩展试压包相关表结构
-- 执行此脚本以添加试压包检查清单功能所需的表和字段

-- 1. 扩展 HydroTestPackageList 表，添加基础信息字段
-- 注意：如果列已存在会报错，但这是正常的（幂等性）

ALTER TABLE HydroTestPackageList 
ADD COLUMN PipeMaterial VARCHAR(100) NULL COMMENT '管道材质' AFTER Description;

ALTER TABLE HydroTestPackageList 
ADD COLUMN TestType VARCHAR(50) NULL COMMENT '测试类型：气压、水压、观察包' AFTER PipeMaterial;

ALTER TABLE HydroTestPackageList 
ADD COLUMN TestMedium VARCHAR(100) NULL COMMENT '测试介质' AFTER TestType;

ALTER TABLE HydroTestPackageList 
ADD COLUMN DesignPressure DECIMAL(10, 2) NULL COMMENT '设计压力' AFTER TestMedium;

ALTER TABLE HydroTestPackageList 
ADD COLUMN TestPressure DECIMAL(10, 2) NULL COMMENT '测试压力' AFTER DesignPressure;

-- 如果存在旧的 Pressure 字段，复制数据到 TestPressure
UPDATE HydroTestPackageList SET TestPressure = Pressure WHERE Pressure IS NOT NULL AND TestPressure IS NULL;

-- 2. 创建 P&ID List 表
CREATE TABLE IF NOT EXISTS PIDList (
    ID INT AUTO_INCREMENT PRIMARY KEY,
    TestPackageID VARCHAR(50) NOT NULL,
    PIDNo VARCHAR(128) NOT NULL COMMENT 'P&ID编号',
    RevNo VARCHAR(128) NULL COMMENT '版本号',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (TestPackageID) REFERENCES HydroTestPackageList(TestPackageID) ON DELETE CASCADE,
    INDEX idx_test_package (TestPackageID)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 3. 创建 ISO Drawing List 表
CREATE TABLE IF NOT EXISTS ISODrawingList (
    ID INT AUTO_INCREMENT PRIMARY KEY,
    TestPackageID VARCHAR(50) NOT NULL,
    ISODrawingNo VARCHAR(128) NOT NULL COMMENT 'ISO图纸编号',
    RevNo VARCHAR(128) NULL COMMENT '版本号',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (TestPackageID) REFERENCES HydroTestPackageList(TestPackageID) ON DELETE CASCADE,
    INDEX idx_test_package (TestPackageID)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 4. 创建附件表
CREATE TABLE IF NOT EXISTS TestPackageAttachments (
    ID INT AUTO_INCREMENT PRIMARY KEY,
    TestPackageID VARCHAR(50) NOT NULL,
    ModuleName VARCHAR(100) NOT NULL COMMENT '模块名称：PID_Drawings, ISO_Drawings等',
    FileName VARCHAR(255) NOT NULL COMMENT '原始文件名',
    FilePath VARCHAR(500) NOT NULL COMMENT '服务器存储路径',
    FileSize BIGINT NULL COMMENT '文件大小（字节）',
    UploadedBy VARCHAR(100) NULL COMMENT '上传人',
    UploadedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (TestPackageID) REFERENCES HydroTestPackageList(TestPackageID) ON DELETE CASCADE,
    INDEX idx_test_package (TestPackageID),
    INDEX idx_module (ModuleName)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 5. 创建 Joint Summary 表
CREATE TABLE IF NOT EXISTS JointSummary (
    ID INT AUTO_INCREMENT PRIMARY KEY,
    TestPackageID VARCHAR(50) NOT NULL UNIQUE,
    TotalJoints INT DEFAULT 0 COMMENT '焊口总量',
    CompletedJoints INT DEFAULT 0 COMMENT '焊口完成量',
    RemainingJoints INT DEFAULT 0 COMMENT '焊口剩余量',
    TotalDIN DECIMAL(10, 2) DEFAULT 0 COMMENT 'DIN总量',
    CompletedDIN DECIMAL(10, 2) DEFAULT 0 COMMENT 'DIN完成量',
    RemainingDIN DECIMAL(10, 2) DEFAULT 0 COMMENT 'DIN剩余量',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (TestPackageID) REFERENCES HydroTestPackageList(TestPackageID) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 6. 创建 NDE/PWHT Backlog Status 表
CREATE TABLE IF NOT EXISTS NDEPWHTStatus (
    ID INT AUTO_INCREMENT PRIMARY KEY,
    TestPackageID VARCHAR(50) NOT NULL UNIQUE,
    VT_Total INT DEFAULT 0,
    VT_Completed INT DEFAULT 0,
    VT_Remaining INT DEFAULT 0,
    RT_Total INT DEFAULT 0,
    RT_Completed INT DEFAULT 0,
    RT_Remaining INT DEFAULT 0,
    PT_Total INT DEFAULT 0,
    PT_Completed INT DEFAULT 0,
    PT_Remaining INT DEFAULT 0,
    HT_Total INT DEFAULT 0,
    HT_Completed INT DEFAULT 0,
    HT_Remaining INT DEFAULT 0,
    PWHT_Total INT DEFAULT 0,
    PWHT_Completed INT DEFAULT 0,
    PWHT_Remaining INT DEFAULT 0,
    PMI_Total INT DEFAULT 0,
    PMI_Completed INT DEFAULT 0,
    PMI_Remaining INT DEFAULT 0,
    UT_Total INT DEFAULT 0,
    UT_Completed INT DEFAULT 0,
    UT_Remaining INT DEFAULT 0,
    MT_Total INT DEFAULT 0,
    MT_Completed INT DEFAULT 0,
    MT_Remaining INT DEFAULT 0,
    FT_Total INT DEFAULT 0,
    FT_Completed INT DEFAULT 0,
    FT_Remaining INT DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (TestPackageID) REFERENCES HydroTestPackageList(TestPackageID) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 7. 创建 Joint Test Verification 表
CREATE TABLE IF NOT EXISTS JointTestVerification (
    ID INT AUTO_INCREMENT PRIMARY KEY,
    TestPackageID VARCHAR(50) NOT NULL UNIQUE,
    SubcontractorQC_Inspector VARCHAR(100) NULL COMMENT '分包商QC检查人',
    SubcontractorQC_Date DATE NULL COMMENT '分包商QC检查日期',
    ContractorQC_Inspector VARCHAR(100) NULL COMMENT '承包商QC检查人',
    ContractorQC_Date DATE NULL COMMENT '承包商QC检查日期',
    AQC_Representative VARCHAR(100) NULL COMMENT 'AQC代表人',
    AQC_Date DATE NULL COMMENT 'AQC检查日期',
    Owner_Representative VARCHAR(100) NULL COMMENT '业主代表人',
    Owner_Date DATE NULL COMMENT '业主检查日期',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (TestPackageID) REFERENCES HydroTestPackageList(TestPackageID) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 8. 创建 Punch List 表
CREATE TABLE IF NOT EXISTS PunchList (
    ID INT AUTO_INCREMENT PRIMARY KEY,
    PunchNo VARCHAR(100) NULL COMMENT '尾项编号/序号',
    TestPackageID VARCHAR(50) NOT NULL,
    ISODrawingNo VARCHAR(128) NOT NULL COMMENT 'ISO图纸编号',
    SheetNo VARCHAR(128) NULL COMMENT '图纸页号',
    RevNo VARCHAR(128) NULL COMMENT '版本号',
    Description TEXT NOT NULL COMMENT '缺陷描述',
    Category ENUM('A', 'B', 'C', 'D') NOT NULL COMMENT '缺陷等级',
    Cause ENUM('N', 'F', 'E') NOT NULL COMMENT '原因：N/F/E',
    IssuedBy VARCHAR(128) NULL COMMENT '发现人',
    Rectified ENUM('Y', 'N') DEFAULT 'N' COMMENT '是否整改',
    RectifiedDate DATETIME NULL COMMENT '整改完成时间',
    Verified ENUM('Y', 'N') DEFAULT 'N' COMMENT '是否验证',
    VerifiedDate DATETIME NULL COMMENT '验证完成时间',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (TestPackageID) REFERENCES HydroTestPackageList(TestPackageID) ON DELETE CASCADE,
    INDEX idx_test_package (TestPackageID),
    INDEX idx_punch_no (PunchNo),
    INDEX idx_category (Category),
    INDEX idx_rectified (Rectified)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 为已存在的PunchList表添加时间字段（如果表已创建）
ALTER TABLE PunchList 
ADD COLUMN RectifiedDate DATETIME NULL COMMENT '整改完成时间' AFTER Rectified;

ALTER TABLE PunchList 
ADD COLUMN VerifiedDate DATETIME NULL COMMENT '验证完成时间' AFTER Verified;

ALTER TABLE PunchList 
ADD COLUMN IF NOT EXISTS PunchNo VARCHAR(100) NULL COMMENT '尾项编号/序号' AFTER ID;

ALTER TABLE PunchList 
ADD INDEX IF NOT EXISTS idx_punch_no (PunchNo);

-- Punch List导入日志
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 9. 为WeldingList表添加PID字段（供将来使用）
ALTER TABLE WeldingList 
ADD COLUMN PID VARCHAR(128) NULL COMMENT 'P&ID编号' AFTER DrawingNumber;

-- 完成
SELECT '✅ 所有扩展表创建完成！' AS Status;

