#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
清理测试数据脚本
删除系统、子系统、试压包、焊接数据等测试数据，但保留用户账号数据
"""

import sys
import os
import shutil
from database import create_connection
from mysql.connector import Error

def cleanup_test_data():
    """清理测试数据，保留用户账号数据"""
    connection = create_connection(use_pool=False)  # 清理时使用直接连接
    if not connection:
        print("❌ 无法连接到数据库")
        return False
    
    try:
        cursor = connection.cursor()
        
        print("=" * 60)
        print("开始清理测试数据...")
        print("=" * 60)
        
        # 统计删除前的数据量
        print("\n📊 删除前的数据统计：")
        tables_to_check = [
            'SystemList', 'SubsystemList', 'HydroTestPackageList', 
            'WeldingList', 'PIDList', 'ISODrawingList', 
            'TestPackageAttachments', 'JointSummary', 'NDEPWHTStatus',
            'JointTestVerification', 'PunchList', 'PunchListImportLog', 
            'LineList', 'TestPackagePreparationAlert'
        ]
        
        stats_before = {}
        for table in tables_to_check:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                stats_before[table] = count
                print(f"  {table}: {count} 条记录")
            except Error as e:
                print(f"  {table}: 表不存在或无法访问 ({e})")
        
        # 确认操作
        print("\n⚠️  警告：此操作将删除以下数据：")
        print("  - 所有系统数据 (SystemList)")
        print("  - 所有子系统数据 (SubsystemList)")
        print("  - 所有试压包数据 (HydroTestPackageList)")
        print("  - 所有焊接数据 (WeldingList)")
        print("  - 所有试压包相关资料 (PIDList, ISODrawingList, TestPackageAttachments等)")
        print("  - 所有管线清单数据 (LineList)")
        print("  - 所有试压包提醒数据 (TestPackagePreparationAlert)")
        
        # 检查上传文件
        uploads_dir = os.path.join(os.path.dirname(__file__), 'uploads', 'test_packages')
        has_upload_files = os.path.exists(uploads_dir) and os.listdir(uploads_dir)
        
        if has_upload_files:
            print("  - 所有试压包上传文件 (uploads/test_packages/)")
        
        print("\n✅ 将保留以下数据：")
        print("  - 用户账号 (UserAccount)")
        print("  - 角色和权限 (Role, Permission, UserRole, RolePermission)")
        print("  - 审计日志 (AuditLog)")
        print("  - 备份记录 (DataBackup)")
        print("  - 同步日志 (SyncLog)")
        print("  - 变更日志 (ChangeLog)")
        
        response = input("\n是否继续？(输入 'YES' 确认): ")
        if response != 'YES':
            print("❌ 操作已取消")
            return False
        
        print("\n🗑️  开始删除数据...")
        
        # 1. 删除依赖表数据（按外键依赖顺序）
        # 注意：由于有 ON DELETE CASCADE，删除 HydroTestPackageList 时会自动删除相关子表数据
        # 但为了安全，我们显式删除
        
        # 1.1 删除 PunchList 相关（没有 CASCADE，需要先删除）
        print("\n1. 删除 PunchList 数据...")
        cursor.execute("DELETE FROM PunchList")
        print(f"   ✓ 已删除 {cursor.rowcount} 条 PunchList 记录")
        
        cursor.execute("DELETE FROM PunchListImportLog")
        print(f"   ✓ 已删除 {cursor.rowcount} 条 PunchListImportLog 记录")
        
        # 1.2 删除 WeldingList（外键关联 TestPackageID, SystemCode, SubSystemCode）
        print("\n2. 删除 WeldingList 数据...")
        cursor.execute("DELETE FROM WeldingList")
        print(f"   ✓ 已删除 {cursor.rowcount} 条 WeldingList 记录")
        
        # 1.3 删除试压包相关子表（有 ON DELETE CASCADE，但显式删除更安全）
        print("\n3. 删除试压包相关资料...")
        
        tables_with_cascade = [
            'PIDList',
            'ISODrawingList', 
            'TestPackageAttachments',
            'JointSummary',
            'NDEPWHTStatus',
            'JointTestVerification'
        ]
        
        for table in tables_with_cascade:
            try:
                cursor.execute(f"DELETE FROM {table}")
                print(f"   ✓ 已删除 {cursor.rowcount} 条 {table} 记录")
            except Error as e:
                print(f"   ⚠ {table}: {e}")
        
        # 1.4 删除 HydroTestPackageList（主表）
        print("\n4. 删除 HydroTestPackageList 数据...")
        cursor.execute("DELETE FROM HydroTestPackageList")
        print(f"   ✓ 已删除 {cursor.rowcount} 条 HydroTestPackageList 记录")
        
        # 1.5 删除 SubsystemList（外键关联 SystemCode，有 ON DELETE CASCADE）
        print("\n5. 删除 SubsystemList 数据...")
        cursor.execute("DELETE FROM SubsystemList")
        print(f"   ✓ 已删除 {cursor.rowcount} 条 SubsystemList 记录")
        
        # 1.6 删除 SystemList（主表）
        print("\n6. 删除 SystemList 数据...")
        cursor.execute("DELETE FROM SystemList")
        print(f"   ✓ 已删除 {cursor.rowcount} 条 SystemList 记录")
        
        # 1.7 删除 LineList（没有外键约束，但可能有关联数据）
        print("\n7. 删除 LineList 数据...")
        try:
            cursor.execute("DELETE FROM LineList")
            print(f"   ✓ 已删除 {cursor.rowcount} 条 LineList 记录")
        except Error as e:
            print(f"   ⚠ LineList: {e}")
        
        # 1.8 删除 TestPackagePreparationAlert（关联 SystemCode）
        print("\n8. 删除 TestPackagePreparationAlert 数据...")
        try:
            cursor.execute("DELETE FROM TestPackagePreparationAlert")
            print(f"   ✓ 已删除 {cursor.rowcount} 条 TestPackagePreparationAlert 记录")
        except Error as e:
            print(f"   ⚠ TestPackagePreparationAlert: {e}")
        
        # 提交事务
        connection.commit()
        print("\n✅ 所有数据库测试数据已删除并提交")
        
        # 2. 清理上传文件
        uploads_dir = os.path.join(os.path.dirname(__file__), 'uploads', 'test_packages')
        if os.path.exists(uploads_dir):
            print("\n9. 清理试压包上传文件...")
            try:
                # 删除 test_packages 目录下的所有内容
                for item in os.listdir(uploads_dir):
                    item_path = os.path.join(uploads_dir, item)
                    if os.path.isdir(item_path):
                        shutil.rmtree(item_path)
                        print(f"   ✓ 已删除目录: {item}")
                    elif os.path.isfile(item_path):
                        os.remove(item_path)
                        print(f"   ✓ 已删除文件: {item}")
                print("   ✓ 所有试压包上传文件已清理")
            except Exception as e:
                print(f"   ⚠ 清理上传文件时出错: {e}")
        
        # 统计删除后的数据量
        print("\n📊 删除后的数据统计：")
        for table in tables_to_check:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                deleted = stats_before.get(table, 0) - count
                print(f"  {table}: {count} 条记录 (已删除 {deleted} 条)")
            except Error:
                pass
        
        # 验证用户数据是否保留
        print("\n✅ 验证保留的数据：")
        try:
            cursor.execute("SELECT COUNT(*) FROM UserAccount")
            user_count = cursor.fetchone()[0]
            print(f"  UserAccount: {user_count} 条记录 ✓")
        except Error as e:
            print(f"  UserAccount: 无法访问 ({e})")
        
        try:
            cursor.execute("SELECT COUNT(*) FROM Role")
            role_count = cursor.fetchone()[0]
            print(f"  Role: {role_count} 条记录 ✓")
        except Error:
            pass
        
        print("\n" + "=" * 60)
        print("✅ 清理完成！")
        print("=" * 60)
        
        return True
        
    except Error as e:
        print(f"\n❌ 数据库错误: {e}")
        connection.rollback()
        return False
    except Exception as e:
        print(f"\n❌ 发生错误: {e}")
        connection.rollback()
        return False
    finally:
        if connection:
            connection.close()
            print("\n数据库连接已关闭")

if __name__ == "__main__":
    print("""
    ╔═══════════════════════════════════════════════════════════╗
    ║           测试数据清理脚本                                 ║
    ║                                                           ║
    ║   此脚本将删除所有测试数据，但保留用户账号数据            ║
    ╚═══════════════════════════════════════════════════════════╝
    """)
    
    success = cleanup_test_data()
    sys.exit(0 if success else 1)

