# -*- coding: utf-8 -*-
"""
NDT符合性检查器
根据管线清单的NDEGrade要求，检查每条管线、每个焊工的检测比例是否满足要求
"""
from database import create_connection
import re

def parse_nde_grade(nde_grade_str):
    """
    解析NDEGrade字符串，提取各类检测的要求比例
    
    规则：
    1. VT始终是100%要求
    2. 如果只有百分比没有测试类型（如"10%"），理解为：VT=100%, RT=该百分比
    3. 如果指定了测试类型（如"10%RT,15%PT"），则按指定的类型
    
    示例：
        "10%" -> {'VT': 100.0, 'RT': 10.0}
        "10%RT,15%PT" -> {'VT': 100.0, 'RT': 10.0, 'PT': 15.0}
        "100%" -> {'VT': 100.0, 'RT': 100.0}
    
    返回：dict {test_type: percentage}
    """
    if not nde_grade_str or str(nde_grade_str).strip() in ['', 'nan', 'None']:
        return {'VT': 100.0}  # 默认只要求VT 100%
    
    result = {'VT': 100.0}  # VT始终是100%
    nde_grade_str = str(nde_grade_str).strip()
    
    # 按逗号分割
    parts = [p.strip() for p in nde_grade_str.split(',')]
    
    has_explicit_type = False
    only_percentage = None
    
    for part in parts:
        # 匹配模式1：数字%测试类型（例如："10%RT", "15%PT"）
        match = re.match(r'(\d+(?:\.\d+)?)\s*%\s*([A-Z]+)', part, re.IGNORECASE)
        if match:
            percentage = float(match.group(1))
            test_type = match.group(2).upper()
            result[test_type] = percentage
            has_explicit_type = True
            continue
        
        # 匹配模式2：测试类型数字%（例如："RT10%"）
        match = re.match(r'([A-Z]+)\s*(\d+(?:\.\d+)?)\s*%', part, re.IGNORECASE)
        if match:
            test_type = match.group(1).upper()
            percentage = float(match.group(2))
            result[test_type] = percentage
            has_explicit_type = True
            continue
        
        # 匹配模式3：只有百分比（例如："10%", "5%"）
        match = re.match(r'(\d+(?:\.\d+)?)\s*%', part)
        if match:
            only_percentage = float(match.group(1))
    
    # 如果只有百分比没有测试类型，理解为 VT=100% + RT=该百分比
    if not has_explicit_type and only_percentage is not None:
        result['RT'] = only_percentage
    
    return result


def check_ndt_compliance_by_pipeline(test_package_id):
    """
    检查试压包内所有管线的NDT符合性（优化版：使用hashmap，一次查询）
    
    返回：{
        'total_pipelines': int,
        'compliant_pipelines': int,
        'non_compliant_pipelines': int,
        'details': {pipeline_id: {...}}
    }
    """
    conn = create_connection()
    if not conn:
        return None
    
    try:
        cur = conn.cursor(dictionary=True)
        
        # 1. 一次性查询所有数据（使用GROUP BY，避免多次查询）
        cur.execute("""
            SELECT 
                wl.PipelineNumber,
                wl.WelderRoot,
                COUNT(*) as total_welds,
                SUM(CASE WHEN wl.VTResult IS NOT NULL AND wl.VTResult != '' THEN 1 ELSE 0 END) as VT_count,
                SUM(CASE WHEN wl.RTResult IS NOT NULL AND wl.RTResult != '' THEN 1 ELSE 0 END) as RT_count,
                SUM(CASE WHEN wl.PTResult IS NOT NULL AND wl.PTResult != '' THEN 1 ELSE 0 END) as PT_count,
                SUM(CASE WHEN wl.UTResult IS NOT NULL AND wl.UTResult != '' THEN 1 ELSE 0 END) as UT_count,
                SUM(CASE WHEN wl.MTResult IS NOT NULL AND wl.MTResult != '' THEN 1 ELSE 0 END) as MT_count,
                SUM(CASE WHEN wl.PMIResult IS NOT NULL AND wl.PMIResult != '' THEN 1 ELSE 0 END) as PMI_count,
                SUM(CASE WHEN wl.FTResult IS NOT NULL AND wl.FTResult != '' THEN 1 ELSE 0 END) as FT_count,
                ll.NDEGrade
            FROM WeldingList wl
            LEFT JOIN LineList ll ON wl.PipelineNumber = ll.LineID
            WHERE wl.TestPackageID = %s 
              AND wl.PipelineNumber IS NOT NULL
              AND wl.PipelineNumber != ''
              AND wl.WelderRoot IS NOT NULL
              AND wl.WelderRoot != ''
            GROUP BY wl.PipelineNumber, wl.WelderRoot, ll.NDEGrade
        """, (test_package_id,))
        
        all_stats = cur.fetchall()
        
        if not all_stats:
            return {
                'total_pipelines': 0,
                'compliant_pipelines': 0,
                'non_compliant_pipelines': 0,
                'details': {}
            }
        
        # 2. 使用字典（hashmap）组织数据，避免遍历
        pipelines_dict = {}
        
        for stat in all_stats:
            pipeline_id = stat['PipelineNumber']
            welder_name = stat['WelderRoot']
            nde_grade_str = stat['NDEGrade']
            total_welds = stat['total_welds']
            
            # 解析NDEGrade要求（只需解析一次每个管线）
            if pipeline_id not in pipelines_dict:
                nde_requirements = parse_nde_grade(nde_grade_str)
                pipelines_dict[pipeline_id] = {
                    'nde_requirement': nde_requirements,
                    'welders': {},
                    'pipeline_compliant': True
                }
            
            pipeline_info = pipelines_dict[pipeline_id]
            nde_requirements = pipeline_info['nde_requirement']
            
            # 3. 计算该焊工的检测比例
            welder_detail = {'total_welds': total_welds}
            welder_compliant = True
            test_types = ['VT', 'RT', 'PT', 'UT', 'MT', 'PMI', 'FT']
            
            for test_type in test_types:
                count = stat.get(f'{test_type}_count', 0)
                actual_pct = (count / total_welds * 100) if total_welds > 0 else 0
                required_pct = nde_requirements.get(test_type, 0)
                compliant = actual_pct >= required_pct if required_pct > 0 else True
                
                welder_detail[test_type] = {
                    'count': count,
                    'percentage': round(actual_pct, 2),
                    'required': required_pct,
                    'compliant': compliant
                }
                
                if not compliant:
                    welder_compliant = False
            
            welder_detail['welder_compliant'] = welder_compliant
            pipeline_info['welders'][welder_name] = welder_detail
            
            if not welder_compliant:
                pipeline_info['pipeline_compliant'] = False
        
        # 4. 统计符合性
        compliant_count = sum(1 for p in pipelines_dict.values() if p['pipeline_compliant'])
        non_compliant_count = len(pipelines_dict) - compliant_count
        
        return {
            'total_pipelines': len(pipelines_dict),
            'compliant_pipelines': compliant_count,
            'non_compliant_pipelines': non_compliant_count,
            'details': pipelines_dict
        }
        
    finally:
        conn.close()


def calculate_ndt_status_for_package(test_package_id):
    """
    计算试压包的NDT总体状态
    
    返回：{
        'total_required': int,  # 要求检测的总数
        'total_completed': int,  # 已完成的检测数
        'total_compliant': int,  # 符合要求的检测数
        'compliance_rate': float,  # 符合率（%）
        'by_test_type': {
            'RT': {'required': 10, 'completed': 8, 'compliant': 8},
            'PT': {'required': 15, 'completed': 12, 'compliant': 10},
            ...
        }
    }
    """
    compliance_result = check_ndt_compliance_by_pipeline(test_package_id)
    
    if not compliance_result:
        return None
    
    # 统计各类检测的总体情况
    by_test_type = {}
    test_types = ['VT', 'RT', 'PT', 'UT', 'MT', 'PMI', 'FT']
    
    for test_type in test_types:
        by_test_type[test_type] = {
            'required': 0,
            'completed': 0,
            'compliant': 0
        }
    
    # 遍历所有管线的所有焊工
    for pipeline_id, pipeline_detail in compliance_result['details'].items():
        for welder_name, welder_detail in pipeline_detail['welders'].items():
            for test_type in test_types:
                if test_type in welder_detail:
                    test_info = welder_detail[test_type]
                    
                    # 如果有要求，累计
                    if test_info['required'] > 0:
                        by_test_type[test_type]['required'] += welder_detail['total_welds']
                    
                    # 累计完成数
                    by_test_type[test_type]['completed'] += test_info['count']
                    
                    # 累计符合数（满足比例要求的）
                    if test_info['compliant']:
                        by_test_type[test_type]['compliant'] += test_info['count']
    
    # 计算总体统计
    total_required = sum(t['required'] for t in by_test_type.values())
    total_completed = sum(t['completed'] for t in by_test_type.values())
    total_compliant = sum(t['compliant'] for t in by_test_type.values())
    
    compliance_rate = (total_compliant / total_required * 100) if total_required > 0 else 0
    
    return {
        'total_required': total_required,
        'total_completed': total_completed,
        'total_compliant': total_compliant,
        'compliance_rate': round(compliance_rate, 2),
        'by_test_type': by_test_type,
        'pipeline_summary': {
            'total': compliance_result['total_pipelines'],
            'compliant': compliance_result['compliant_pipelines'],
            'non_compliant': compliance_result['non_compliant_pipelines']
        }
    }


if __name__ == '__main__':
    # 测试
    test_package_id = 'AT-031-AT-0001'
    
    print(f"Checking NDT compliance for package: {test_package_id}")
    print("=" * 80)
    
    result = check_ndt_compliance_by_pipeline(test_package_id)
    
    if result:
        print(f"\nPipeline summary:")
        print(f"  Total pipelines: {result['total_pipelines']}")
        print(f"  Compliant: {result['compliant_pipelines']}")
        print(f"  Non-compliant: {result['non_compliant_pipelines']}")
        
        print(f"\nDetailed analysis (first 3 pipelines):")
        for i, (pipeline_id, detail) in enumerate(list(result['details'].items())[:3], 1):
            print(f"\n  {i}. Pipeline: {pipeline_id}")
            print(f"     NDE Requirement: {detail['nde_requirement']}")
            print(f"     Pipeline Compliant: {detail['pipeline_compliant']}")
            
            for welder_name, welder_info in list(detail['welders'].items())[:2]:  # 只显示前2个焊工
                print(f"\n     Welder: {welder_name}")
                print(f"       Total welds: {welder_info['total_welds']}")
                print(f"       Compliant: {welder_info['welder_compliant']}")
                
                for test_type in ['RT', 'PT', 'UT', 'VT']:
                    if test_type in welder_info and welder_info[test_type]['required'] > 0:
                        info = welder_info[test_type]
                        status = 'OK' if info['compliant'] else 'FAIL'
                        print(f"         {test_type}: {info['count']}/{welder_info['total_welds']} "
                              f"({info['percentage']}% vs {info['required']}% required) [{status}]")
    
    print("\n" + "=" * 80)
    print("Overall NDT status:")
    print("=" * 80)
    
    status = calculate_ndt_status_for_package(test_package_id)
    if status:
        print(f"  Compliance rate: {status['compliance_rate']}%")
        print(f"  Required tests: {status['total_required']}")
        print(f"  Completed tests: {status['total_completed']}")
        print(f"  Compliant tests: {status['total_compliant']}")
        
        print(f"\n  By test type:")
        for test_type, info in status['by_test_type'].items():
            if info['required'] > 0:
                print(f"    {test_type}: {info['completed']}/{info['required']} "
                      f"({info['compliant']} compliant)")

