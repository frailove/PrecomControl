"""
工具函数：为 WeldingList 表中的现有数据填充 Block 字段
从 DrawingNumber 中提取 Block 信息，用于性能优化
"""
import sys
import os
import re

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import create_connection

def extract_block_from_drawing(drawing_number):
    """
    从 DrawingNumber 中提取 Block 模式，格式与 Faclist 中的 Block 格式完全一致（A-B-C）。
    例如：'GCC-ASP-DDD-00051-00-5100-TKM-ISO-00004' -> '5100-00051-00'
    规则：提取前三个数字部分，按 Faclist 格式排列 [parts[2], parts[0], parts[1]]
    这样存储的 Block 可以直接与 Faclist 中的 Block 进行等值匹配，无需任何转换
    """
    if not drawing_number:
        return None
    drawing_str = str(drawing_number).strip()
    if not drawing_str:
        return None
    # 提取所有数字部分
    parts = re.findall(r'\d+', drawing_str)
    if len(parts) >= 3:
        # 例如：'GCC-ASP-DDD-00051-00-5100-TKM-ISO-00004' 
        # parts = ['00051', '00', '5100', ...]
        # 应该存储为：'5100-00051-00' (第三部分-第一部分-第二部分，即 A-B-C 格式)
        # 与 Faclist 中的 Block 格式完全一致，可直接等值匹配
        return f"{parts[2]}-{parts[0]}-{parts[1]}"
    elif len(parts) == 2:
        # 两个部分：按原始顺序
        return '-'.join(parts)
    elif len(parts) == 1:
        return parts[0]
    return None

def update_welding_block_field(verbose=True):
    """
    为 WeldingList 表中的现有数据填充 Block 字段
    从 DrawingNumber 中提取 Block 信息
    """
    conn = None
    try:
        conn = create_connection()
        if not conn:
            print("ERROR: 无法建立数据库连接")
            return False
        
        cur = conn.cursor()
        
        # 检查 Block 字段是否存在，如果不存在则添加
        cur.execute("SHOW COLUMNS FROM WeldingList LIKE 'Block'")
        if not cur.fetchone():
            if verbose:
                print("⚠️  Block 字段不存在，正在添加...")
            try:
                # 添加 Block 字段
                cur.execute("ALTER TABLE WeldingList ADD COLUMN Block VARCHAR(255) AFTER DrawingNumber")
                conn.commit()
                
                # 添加 Block 索引（性能优化）
                try:
                    cur.execute("SHOW INDEX FROM WeldingList WHERE Key_name = 'idx_block'")
                    if not cur.fetchone():
                        cur.execute("CREATE INDEX idx_block ON WeldingList(Block)")
                        conn.commit()
                        if verbose:
                            print("✅ 已添加 Block 字段和索引")
                except Exception as idx_e:
                    if verbose:
                        print(f"⚠️  添加 Block 索引失败（可能已存在）: {idx_e}")
            except Exception as e:
                print(f"ERROR: 添加 Block 字段失败: {e}")
                import traceback
                traceback.print_exc()
                return False
        
        # 获取所有需要更新的记录（所有有 DrawingNumber 的记录，包括之前已填充的）
        # 这样可以覆盖之前格式错误的 Block 值
        cur.execute("""
            SELECT WeldID, DrawingNumber 
            FROM WeldingList 
            WHERE DrawingNumber IS NOT NULL 
              AND DrawingNumber <> ''
        """)
        
        records = cur.fetchall()
        total = len(records)
        if total == 0:
            if verbose:
                print("✅ 所有记录的 Block 字段已填充")
            return True
        
        if verbose:
            print(f"📊 找到 {total} 条需要更新 Block 字段的记录")
        
        updated = 0
        failed = 0
        
        # 批量更新（每批 1000 条）
        batch_size = 1000
        for i in range(0, total, batch_size):
            batch = records[i:i + batch_size]
            updates = []
            for row in batch:
                # 处理元组或字典格式的返回结果
                if isinstance(row, dict):
                    weld_id = row.get('WeldID')
                    drawing_number = row.get('DrawingNumber')
                else:
                    # 元组格式：(WeldID, DrawingNumber)
                    weld_id = row[0] if len(row) > 0 else None
                    drawing_number = row[1] if len(row) > 1 else None
                
                if weld_id and drawing_number:
                    block = extract_block_from_drawing(drawing_number)
                    if block:
                        updates.append((block, weld_id))
            
            if updates:
                try:
                    cur.executemany(
                        "UPDATE WeldingList SET Block = %s WHERE WeldID = %s",
                        updates
                    )
                    updated += len(updates)
                    conn.commit()
                    if verbose and (i + batch_size) % 5000 == 0:
                        print(f"  已更新 {updated}/{total} 条记录...")
                except Exception as e:
                    failed += len(updates)
                    if verbose:
                        print(f"  WARNING: 批量更新失败: {e}")
                    conn.rollback()
        
        if verbose:
            print(f"✅ Block 字段更新完成: 成功 {updated} 条，失败 {failed} 条")
        
        return True
    except Exception as e:
        import traceback
        print(f"ERROR: 更新 Block 字段失败: {e}")
        print(f"错误详情:")
        traceback.print_exc()
        if conn:
            try:
                conn.rollback()
            except:
                pass
        return False
    finally:
        if conn:
            try:
                conn.close()
            except:
                pass

if __name__ == '__main__':
    print("开始更新 WeldingList 表的 Block 字段...")
    update_welding_block_field(verbose=True)
    print("完成！")

