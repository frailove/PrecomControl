-- 创建管线清单表（LineList）和扩展焊接清单表（WeldingList）

USE precom;

-- 1. 创建 LineList 表（管线清单）
CREATE TABLE IF NOT EXISTS LineList (
    LineID VARCHAR(255) PRIMARY KEY COMMENT '管线号（主键）',
    ProjectNo VARCHAR(50) NULL COMMENT '项目号',
    AreaCode VARCHAR(50) NULL COMMENT '区域代码',
    WorkArea VARCHAR(50) NULL COMMENT '工区',
    DrawingNo VARCHAR(128) NULL COMMENT '图纸号',
    RevNo VARCHAR(50) NULL COMMENT '版本号',
    PipeSize VARCHAR(50) NULL COMMENT '管径',
    SystemCode VARCHAR(50) NULL COMMENT '系统代码/介质',
    MediumDescription TEXT NULL COMMENT '介质描述',
    FluidCode VARCHAR(50) NULL COMMENT '流体代码',
    FluidPhase VARCHAR(50) NULL COMMENT '流体相态',
    PipingClass VARCHAR(100) NULL COMMENT '管道等级',
    DesignPressure VARCHAR(50) NULL COMMENT '设计压力',
    DesignTemperature VARCHAR(50) NULL COMMENT '设计温度',
    OperatingPressure VARCHAR(50) NULL COMMENT '操作压力',
    OperatingTemperature VARCHAR(50) NULL COMMENT '操作温度',
    InsulationType VARCHAR(100) NULL COMMENT '保温类型',
    InsulationThickness VARCHAR(50) NULL COMMENT '保温厚度',
    TestFluid VARCHAR(100) NULL COMMENT '试验介质',
    TestPressure VARCHAR(50) NULL COMMENT '试验压力',
    PaintCode VARCHAR(100) NULL COMMENT '油漆代码',
    Medium VARCHAR(100) NULL COMMENT '介质',
    PressureCategory VARCHAR(100) NULL COMMENT '压力等级',
    PIDNo VARCHAR(128) NULL COMMENT 'P&ID号',
    InspectionPercentage VARCHAR(50) NULL COMMENT '检验比例',
    NDEGrade VARCHAR(100) NULL COMMENT 'NDE等级/NDT比例',
    MinDefectCount INT NULL COMMENT '最低缺陷数量要求',
    DefectInspection VARCHAR(100) NULL COMMENT '缺陷检查',
    ConstructionUnit VARCHAR(100) NULL COMMENT '施工单位',
    ConstructionTeam VARCHAR(100) NULL COMMENT '施工班组',
    NDEInfo TEXT NULL COMMENT 'NDE信息',
    Status VARCHAR(50) NULL COMMENT '状态',
    DrawingAttachment VARCHAR(255) NULL COMMENT '图纸附件',
    Remarks TEXT NULL COMMENT '备注',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_project (ProjectNo),
    INDEX idx_area (AreaCode),
    INDEX idx_system (SystemCode),
    INDEX idx_pid (PIDNo)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='管线清单表';

-- 2. 扩展 WeldingList 表，添加新字段
-- 流程图号
ALTER TABLE WeldingList ADD COLUMN PIDDrawingNumber VARCHAR(128) NULL COMMENT '流程图号/P&ID号' AFTER PID;

-- 管道材料等级
ALTER TABLE WeldingList ADD COLUMN PipingMaterialClass VARCHAR(100) NULL COMMENT '管道材料等级' AFTER PIDDrawingNumber;

-- 压力等级
ALTER TABLE WeldingList ADD COLUMN PressureClass VARCHAR(50) NULL COMMENT '压力等级' AFTER PipingMaterialClass;

-- 介质级别
ALTER TABLE WeldingList ADD COLUMN MediumLevel VARCHAR(50) NULL COMMENT '介质级别' AFTER PressureClass;

-- 管段号
ALTER TABLE WeldingList ADD COLUMN SpoolNo VARCHAR(100) NULL COMMENT '管段号' AFTER MediumLevel;

-- NDT设计比例
ALTER TABLE WeldingList ADD COLUMN NDTDesignRatio VARCHAR(100) NULL COMMENT 'NDT设计比例' AFTER SpoolNo;

-- 母材材质
ALTER TABLE WeldingList ADD COLUMN Material1 VARCHAR(100) NULL COMMENT '母材材质1' AFTER NDTDesignRatio;
ALTER TABLE WeldingList ADD COLUMN Material2 VARCHAR(100) NULL COMMENT '母材材质2' AFTER Material1;

-- 外径
ALTER TABLE WeldingList ADD COLUMN OuterDiameter1 VARCHAR(50) NULL COMMENT '外径1' AFTER Material2;
ALTER TABLE WeldingList ADD COLUMN OuterDiameter2 VARCHAR(50) NULL COMMENT '外径2' AFTER OuterDiameter1;

-- 厚度/SCH
ALTER TABLE WeldingList ADD COLUMN SCH1 VARCHAR(50) NULL COMMENT '厚度1/SCH1' AFTER OuterDiameter2;
ALTER TABLE WeldingList ADD COLUMN SCH2 VARCHAR(50) NULL COMMENT '厚度2/SCH2' AFTER SCH1;

-- 焊接类型
ALTER TABLE WeldingList ADD COLUMN WeldingType VARCHAR(100) NULL COMMENT '焊接类型' AFTER SCH2;

-- 接头类型（俄标）
ALTER TABLE WeldingList ADD COLUMN WeldJointTypeRUS VARCHAR(100) NULL COMMENT '接头类型(俄标)' AFTER WeldingType;

-- 焊接方法
ALTER TABLE WeldingList ADD COLUMN WeldMethodRoot VARCHAR(100) NULL COMMENT '焊接方法(根层)' AFTER WPSNumber;
ALTER TABLE WeldingList ADD COLUMN WeldMethodCover VARCHAR(100) NULL COMMENT '焊接方法(填充、盖面)' AFTER WeldMethodRoot;

-- 焊接环境温度
ALTER TABLE WeldingList ADD COLUMN WeldEnvironmentTemperature VARCHAR(50) NULL COMMENT '焊接环境温度℃' AFTER WeldMethodCover;

-- 焊工号（填充、盖面）- 重命名原有的 WelderFill
ALTER TABLE WeldingList CHANGE COLUMN WelderFill WelderCover VARCHAR(50) NULL COMMENT '焊工号填充、盖面';

-- 热处理相关
ALTER TABLE WeldingList ADD COLUMN IsHeatTreatment VARCHAR(20) NULL COMMENT '是否热处理' AFTER WeldEnvironmentTemperature;
ALTER TABLE WeldingList ADD COLUMN HeatTreatmentDate DATE NULL COMMENT '热处理日期' AFTER IsHeatTreatment;
ALTER TABLE WeldingList ADD COLUMN HeatTreatmentReportNumber VARCHAR(100) NULL COMMENT '热处理报告号' AFTER HeatTreatmentDate;
ALTER TABLE WeldingList ADD COLUMN HeatTreatmentWorker VARCHAR(100) NULL COMMENT '热处理工' AFTER HeatTreatmentReportNumber;

-- VT检测相关
ALTER TABLE WeldingList ADD COLUMN VTReportNumber VARCHAR(100) NULL COMMENT 'VT报告号' AFTER HeatTreatmentWorker;
ALTER TABLE WeldingList ADD COLUMN VTReportDate DATE NULL COMMENT 'VT报告日期' AFTER VTReportNumber;

-- RT检测相关
ALTER TABLE WeldingList ADD COLUMN RTReportNumber VARCHAR(100) NULL COMMENT 'RT报告号' AFTER VTResult;
ALTER TABLE WeldingList ADD COLUMN RTReportDate DATE NULL COMMENT 'RT报告日期' AFTER RTReportNumber;

-- PT检测相关
ALTER TABLE WeldingList ADD COLUMN PTReportNumber VARCHAR(100) NULL COMMENT 'PT报告号' AFTER PTResult;
ALTER TABLE WeldingList ADD COLUMN PTReportDate DATE NULL COMMENT 'PT报告日期' AFTER PTReportNumber;

-- UT检测相关
ALTER TABLE WeldingList ADD COLUMN UTReportNumber VARCHAR(100) NULL COMMENT 'UT报告号' AFTER UTResult;
ALTER TABLE WeldingList ADD COLUMN UTReportDate DATE NULL COMMENT 'UT报告日期' AFTER UTReportNumber;

-- MT检测相关
ALTER TABLE WeldingList ADD COLUMN MTReportNumber VARCHAR(100) NULL COMMENT 'MT报告号' AFTER MTResult;
ALTER TABLE WeldingList ADD COLUMN MTReportDate DATE NULL COMMENT 'MT报告日期' AFTER MTReportNumber;

-- PMI检测相关
ALTER TABLE WeldingList ADD COLUMN PMIReportNumber VARCHAR(100) NULL COMMENT 'PMI报告号' AFTER PMIResult;
ALTER TABLE WeldingList ADD COLUMN PMIReportDate DATE NULL COMMENT 'PMI报告日期' AFTER PMIReportNumber;

-- FT检测相关
ALTER TABLE WeldingList ADD COLUMN FTReportNumber VARCHAR(100) NULL COMMENT 'FT报告号' AFTER FTResult;
ALTER TABLE WeldingList ADD COLUMN FTReportDate DATE NULL COMMENT 'FT报告日期' AFTER FTReportNumber;

-- HT检测相关（如果HT列已存在）
ALTER TABLE WeldingList ADD COLUMN HTReportNumber VARCHAR(100) NULL COMMENT 'HT报告号' AFTER HTResult;
ALTER TABLE WeldingList ADD COLUMN HTReportDate DATE NULL COMMENT 'HT报告日期' AFTER HTReportNumber;

-- PWHT检测相关（如果PWHT列已存在）
ALTER TABLE WeldingList ADD COLUMN PWHTReportNumber VARCHAR(100) NULL COMMENT 'PWHT报告号' AFTER PWHTResult;
ALTER TABLE WeldingList ADD COLUMN PWHTReportDate DATE NULL COMMENT 'PWHT报告日期' AFTER PWHTReportNumber;

-- 焊口状态
ALTER TABLE WeldingList ADD COLUMN JointStatus VARCHAR(50) NULL COMMENT '焊口状态' AFTER Status;

-- 安装/F预制/S
ALTER TABLE WeldingList ADD COLUMN JointTypeFS VARCHAR(10) NULL COMMENT '安装/F预制/S' AFTER WeldJoint;

-- 施工承包商
ALTER TABLE WeldingList ADD COLUMN ConstContractor VARCHAR(100) NULL COMMENT '施工承包商' AFTER WeldID;

-- 完成
SELECT 'WeldingList表扩展完成，所有新字段已添加' AS Status;
SELECT 'LineList表创建完成' AS Status;

