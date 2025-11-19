-- 为WeldingList表添加新字段
-- RevNo: 图纸版本号
-- HTResult: HT检测结果
-- PWHTResult: PWHT检测结果
-- ConstContractor: 施工承包商

-- 添加RevNo（图纸版本号）
ALTER TABLE WeldingList 
ADD COLUMN IF NOT EXISTS RevNo VARCHAR(50) NULL COMMENT '图纸版本号' AFTER DrawingNumber;

-- 添加HTResult（HT检测结果）
ALTER TABLE WeldingList 
ADD COLUMN IF NOT EXISTS HTResult VARCHAR(20) NULL COMMENT 'HT检测结果' AFTER PTResult;

-- 添加PWHTResult（PWHT检测结果）
ALTER TABLE WeldingList 
ADD COLUMN IF NOT EXISTS PWHTResult VARCHAR(20) NULL COMMENT 'PWHT检测结果' AFTER HTResult;

-- 添加ConstContractor（施工承包商）
ALTER TABLE WeldingList 
ADD COLUMN IF NOT EXISTS ConstContractor VARCHAR(100) NULL COMMENT '施工承包商' AFTER WeldID;

-- 完成
SELECT 'WeldingList表字段添加完成！' AS Status;

