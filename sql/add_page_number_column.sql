-- 为 WeldingList 表添加 PageNumber（页码）列

USE precom;

-- 添加 PageNumber 列（在 DrawingNumber 之后）
ALTER TABLE WeldingList 
ADD COLUMN PageNumber VARCHAR(50) NULL COMMENT '图纸页码' 
AFTER DrawingNumber;

-- 验证列是否添加成功
SHOW COLUMNS FROM WeldingList LIKE 'PageNumber';

SELECT 'PageNumber列已成功添加到WeldingList表' AS Status;

