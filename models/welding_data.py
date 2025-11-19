import pandas as pd
import os
from datetime import datetime
import math

class WeldingDataAnalyzer:
    def __init__(self, excel_path="WeldingDB_2.xlsx"):
        self.excel_path = excel_path
        self.df = None
        self.load_data()
    
    def load_data(self):
        """加载Excel数据"""
        try:
            if os.path.exists(self.excel_path):
                # 读取Excel文件，跳过第一行（如果有标题行问题）
                self.df = pd.read_excel(self.excel_path, header=1)  # 第二行作为标题行
                print(f"✅ 成功加载焊接数据，共 {len(self.df)} 行数据")
                
                # 打印列名用于调试
                print("📋 Excel文件列名:")
                for i, col in enumerate(self.df.columns):
                    print(f"  {i}: {col}")
            else:
                print(f"❌ Excel文件不存在: {self.excel_path}")
                self.df = pd.DataFrame()
        except Exception as e:
            print(f"❌ 加载Excel文件失败: {e}")
            self.df = pd.DataFrame()
    
    def get_test_package_stats(self, test_package_id):
        """获取指定试压包的统计信息"""
        if self.df is None or self.df.empty:
            return self._get_empty_stats()
        
        try:
            # 根据试压包号筛选数据
            # 注意：列名可能需要根据实际情况调整
            package_data = self.df[self.df['试压包号'] == test_package_id]
            
            if package_data.empty:
                print(f"⚠️ 未找到试压包 {test_package_id} 的焊接数据")
                return self._get_empty_stats()
            
            # 计算统计信息
            total_joints = len(package_data)
            
            # 计算完成的焊口（焊接日期不为空）
            completed_joints = package_data[package_data['焊接日期'].notna()].shape[0]
            
            # 计算总DIN和完成的DIN
            total_din = package_data['尺寸'].sum() if '尺寸' in package_data.columns else 0
            completed_din_data = package_data[package_data['焊接日期'].notna()]
            completed_din = completed_din_data['尺寸'].sum() if '尺寸' in completed_din_data.columns else 0
            
            # 检查各项检测是否有不合格
            inspection_columns = {
                'VT检测结果': 'VT',
                'RT检测结果': 'RT', 
                'UT检测结果': 'UT',
                'PT检测结果': 'PT',
                'MT检测结果': 'MT',
                'PMI检测结果': 'PMI',
                'FT检测结果': 'FT'
            }
            
            inspection_status = {}
            for col, inspection_type in inspection_columns.items():
                if col in package_data.columns:
                    # 检查是否有不合格的记录
                    has_unqualified = any(
                        pd.notna(x) and '不合格' in str(x) 
                        for x in package_data[col]
                    )
                    inspection_status[inspection_type] = not has_unqualified
                else:
                    inspection_status[inspection_type] = True  # 如果列不存在，默认为合格
            
            stats = {
                'test_package_id': test_package_id,
                'total_joints': total_joints,
                'completed_joints': completed_joints,
                'completion_rate': round((completed_joints / total_joints * 100) if total_joints > 0 else 0, 2),
                'total_din': round(total_din, 2),
                'completed_din': round(completed_din, 2),
                'din_completion_rate': round((completed_din / total_din * 100) if total_din > 0 else 0, 2),
                'inspection_status': inspection_status,
                'all_inspections_passed': all(inspection_status.values()),
                'data_available': True
            }
            
            print(f"📊 试压包 {test_package_id} 统计: {completed_joints}/{total_joints} 焊口完成, DIN: {completed_din}/{total_din}")
            return stats
            
        except Exception as e:
            print(f"❌ 计算试压包 {test_package_id} 统计时出错: {e}")
            return self._get_empty_stats()
    
    def get_all_test_packages_stats(self):
        """获取所有试压包的统计信息"""
        if self.df is None or self.df.empty:
            return {}
        
        try:
            # 获取所有唯一的试压包号
            if '试压包号' in self.df.columns:
                test_package_ids = self.df['试压包号'].dropna().unique()
                stats = {}
                for package_id in test_package_ids:
                    stats[str(package_id)] = self.get_test_package_stats(package_id)
                return stats
            else:
                print("❌ Excel文件中没有找到'试压包号'列")
                return {}
        except Exception as e:
            print(f"❌ 获取所有试压包统计时出错: {e}")
            return {}
    
    def get_welding_joints_by_test_package(self, test_package_id):
        """获取指定试压包的所有焊口详情"""
        if self.df is None or self.df.empty:
            return []
        
        try:
            package_data = self.df[self.df['试压包号'] == test_package_id]
            
            joints = []
            for _, row in package_data.iterrows():
                joint = {
                    'weld_id': row.get('焊缝编号', ''),
                    'pipeline_number': row.get('管线号', ''),
                    'weld_date': row.get('焊接日期', ''),
                    'size': row.get('尺寸', 0),
                    'welder_root': row.get('焊工号根层', ''),
                    'welder_fill': row.get('焊工号填充、盖面', ''),
                    'wps_number': row.get('WPS编号', ''),
                    'vt_result': row.get('VT检测结果', ''),
                    'rt_result': row.get('RT检测结果', ''),
                    'ut_result': row.get('UT检测结果', ''),
                    'pt_result': row.get('PT检测结果', ''),
                    'mt_result': row.get('MT检测结果', ''),
                    'pmi_result': row.get('PMI检测结果', ''),
                    'ft_result': row.get('FT检测结果', ''),
                    'status': '已完成' if pd.notna(row.get('焊接日期')) else '未完成'
                }
                joints.append(joint)
            
            return joints
            
        except Exception as e:
            print(f"❌ 获取试压包 {test_package_id} 焊口详情时出错: {e}")
            return []
    
    def _get_empty_stats(self):
        """返回空的统计信息"""
        return {
            'test_package_id': '',
            'total_joints': 0,
            'completed_joints': 0,
            'completion_rate': 0,
            'total_din': 0,
            'completed_din': 0,
            'din_completion_rate': 0,
            'inspection_status': {
                'VT': True, 'RT': True, 'UT': True, 
                'PT': True, 'MT': True, 'PMI': True, 'FT': True
            },
            'all_inspections_passed': True,
            'data_available': False
        }

# 全局实例
welding_analyzer = WeldingDataAnalyzer()