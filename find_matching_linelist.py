# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, '.')

from database import create_connection

pipeline_id = '049-ATM-0002'

conn = create_connection()
cur = conn.cursor(dictionary=True)

# 搜索包含"049-ATM-0002"的LineList记录
print(f"Searching LineList for entries containing: {pipeline_id}")
print("="*80)

cur.execute("""
    SELECT LineID, NDEGrade
    FROM LineList
    WHERE LineID LIKE %s
""", (f'%{pipeline_id}%',))

results = cur.fetchall()

if results:
    print(f"\nFound {len(results)} matching entries:")
    for r in results:
        print(f"  LineID: {r['LineID']}")
        print(f"    NDEGrade: {r['NDEGrade']}")
else:
    print("\nNo matching entries found")
    
    # 尝试只用数字部分匹配
    parts = pipeline_id.split('-')
    if len(parts) >= 2:
        search_pattern = f"%{parts[0]}%{parts[1]}%"
        print(f"\nTrying pattern: {search_pattern}")
        
        cur.execute("""
            SELECT LineID, NDEGrade
            FROM LineList
            WHERE LineID LIKE %s
            LIMIT 10
        """, (search_pattern,))
        
        fuzzy_results = cur.fetchall()
        if fuzzy_results:
            print(f"Found {len(fuzzy_results)} fuzzy matches:")
            for r in fuzzy_results:
                print(f"  {r['LineID']} | NDEGrade: {r['NDEGrade']}")

conn.close()

