"""
MySQL 连接管理工具
用于查找和终止长时间运行的 MySQL 连接
"""
import mysql.connector
from config import FlaskConfig

def get_mysql_connection():
    """获取 MySQL 连接"""
    return mysql.connector.connect(
        host=FlaskConfig.MYSQL_HOST,
        port=FlaskConfig.MYSQL_PORT,
        user=FlaskConfig.MYSQL_USER,
        password=FlaskConfig.MYSQL_PASSWORD,
        database=FlaskConfig.MYSQL_DATABASE
    )

def show_processlist():
    """显示所有活动连接"""
    conn = get_mysql_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SHOW PROCESSLIST")
        processes = cur.fetchall()
        
        print("\n=== 所有活动连接 ===")
        print(f"{'ID':<8} {'User':<15} {'Host':<20} {'DB':<15} {'Time':<8} {'State':<20} {'Info'}")
        print("-" * 120)
        for p in processes:
            info = (p.get('Info') or '')[:50] if p.get('Info') else ''
            print(f"{p['Id']:<8} {p.get('User', ''):<15} {p.get('Host', ''):<20} {p.get('db', ''):<15} "
                  f"{p.get('Time', 0):<8} {str(p.get('State', ''))[:20]:<20} {info}")
    finally:
        conn.close()

def find_thread(thread_id):
    """查找指定 thread id 的连接信息"""
    conn = get_mysql_connection()
    try:
        cur = conn.cursor(dictionary=True)
        
        # 从 PROCESSLIST 查找
        cur.execute("SHOW PROCESSLIST")
        processes = cur.fetchall()
        found = [p for p in processes if p['Id'] == thread_id]
        
        if found:
            p = found[0]
            print(f"\n=== 找到 Thread ID {thread_id} ===")
            print(f"用户: {p.get('User')}")
            print(f"主机: {p.get('Host')}")
            print(f"数据库: {p.get('db')}")
            print(f"运行时间: {p.get('Time')} 秒")
            print(f"状态: {p.get('State')}")
            print(f"当前查询: {p.get('Info') or '(无)'}")
            
            # 从 INNODB_TRX 查找事务信息
            cur.execute("""
                SELECT trx_id, trx_state, trx_started, trx_tables_locked, 
                       trx_rows_locked, trx_rows_modified
                FROM information_schema.INNODB_TRX
                WHERE trx_mysql_thread_id = %s
            """, (thread_id,))
            trx = cur.fetchone()
            if trx:
                print(f"\n事务信息:")
                print(f"  事务ID: {trx['trx_id']}")
                print(f"  状态: {trx['trx_state']}")
                print(f"  开始时间: {trx['trx_started']}")
                print(f"  锁定表数: {trx['trx_tables_locked']}")
                print(f"  锁定行数: {trx['trx_rows_locked']}")
                print(f"  修改行数: {trx['trx_rows_modified']}")
        else:
            print(f"\n未找到 Thread ID {thread_id}")
    finally:
        conn.close()

def kill_thread(thread_id):
    """终止指定 thread id 的连接"""
    conn = get_mysql_connection()
    try:
        cur = conn.cursor()
        cur.execute(f"KILL {thread_id}")
        print(f"\n✓ 已终止 Thread ID {thread_id}")
    except mysql.connector.Error as e:
        print(f"\n✗ 终止失败: {e}")
    finally:
        conn.close()

def find_long_running_transactions(min_seconds=60):
    """查找长时间运行的事务"""
    conn = get_mysql_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT 
                p.ID as thread_id,
                p.USER,
                p.HOST,
                p.DB,
                p.TIME as duration_seconds,
                p.STATE,
                p.INFO as current_query,
                t.trx_id,
                t.trx_state,
                t.trx_started,
                t.trx_tables_locked,
                t.trx_rows_locked
            FROM information_schema.PROCESSLIST p
            LEFT JOIN information_schema.INNODB_TRX t ON p.ID = t.trx_mysql_thread_id
            WHERE p.TIME > %s AND p.USER != 'system user'
            ORDER BY p.TIME DESC
        """, (min_seconds,))
        
        transactions = cur.fetchall()
        if transactions:
            print(f"\n=== 长时间运行的事务（超过 {min_seconds} 秒）===")
            print(f"{'Thread ID':<12} {'User':<15} {'Host':<20} {'Time(s)':<10} {'State':<15} {'Locked Rows':<12}")
            print("-" * 100)
            for t in transactions:
                print(f"{t['thread_id']:<12} {t.get('USER', ''):<15} {str(t.get('HOST', ''))[:20]:<20} "
                      f"{t.get('duration_seconds', 0):<10} {str(t.get('STATE', ''))[:15]:<15} "
                      f"{t.get('trx_rows_locked', 0):<12}")
        else:
            print(f"\n没有找到超过 {min_seconds} 秒的事务")
    finally:
        conn.close()

if __name__ == '__main__':
    import sys
    
    if len(sys.argv) < 2:
        print("用法:")
        print("  python kill_mysql_thread.py list                    # 显示所有连接")
        print("  python kill_mysql_thread.py find <thread_id>        # 查找指定连接")
        print("  python kill_mysql_thread.py kill <thread_id>        # 终止指定连接")
        print("  python kill_mysql_thread.py long [min_seconds]      # 查找长时间运行的事务")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == 'list':
        show_processlist()
    elif command == 'find':
        if len(sys.argv) < 3:
            print("错误: 需要提供 thread_id")
            sys.exit(1)
        find_thread(int(sys.argv[2]))
    elif command == 'kill':
        if len(sys.argv) < 3:
            print("错误: 需要提供 thread_id")
            sys.exit(1)
        thread_id = int(sys.argv[2])
        print(f"警告: 即将终止 Thread ID {thread_id}")
        confirm = input("确认继续? (yes/no): ")
        if confirm.lower() == 'yes':
            kill_thread(thread_id)
        else:
            print("已取消")
    elif command == 'long':
        min_seconds = int(sys.argv[2]) if len(sys.argv) > 2 else 60
        find_long_running_transactions(min_seconds)
    else:
        print(f"未知命令: {command}")

