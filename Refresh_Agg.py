# 刷新 Block 聚合表的快速脚本
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.refresh_aggregated_data import refresh_block_summaries

if __name__ == '__main__':
    print("开始刷新 BlockSystemSummary 和 BlockSubsystemSummary...")
    block_sys_rows, block_subsys_rows = refresh_block_summaries(verbose=True)
    print(f"\n刷新完成！")
    print(f"BlockSystemSummary: {block_sys_rows} 行")
    print(f"BlockSubsystemSummary: {block_subsys_rows} 行")