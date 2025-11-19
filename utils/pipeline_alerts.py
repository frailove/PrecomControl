from database import create_connection


def ensure_alert_table(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS TestPackagePreparationAlert (
            AlertID INT AUTO_INCREMENT PRIMARY KEY,
            SystemCode VARCHAR(50) NOT NULL,
            PipelineNumber VARCHAR(100) NOT NULL,
            TotalDIN DECIMAL(18,4) NOT NULL DEFAULT 0,
            CompletedDIN DECIMAL(18,4) NOT NULL DEFAULT 0,
            CompletionRate DECIMAL(5,4) NOT NULL DEFAULT 0,
            SystemDINShare DECIMAL(5,4) NOT NULL DEFAULT 0,
            ThresholdMet TINYINT(1) NOT NULL DEFAULT 0,
            CreatedAt DATETIME DEFAULT CURRENT_TIMESTAMP,
            Status VARCHAR(20) DEFAULT 'PENDING',
            Remarks VARCHAR(255),
            INDEX idx_alert_system (SystemCode),
            INDEX idx_alert_status (Status)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """
    )


def get_pipeline_alerts(status='PENDING'):
    conn = create_connection()
    if not conn:
        return []
    try:
        cur = conn.cursor(dictionary=True)
        ensure_alert_table(cur)
        cur.execute(
            """
            SELECT AlertID, SystemCode, PipelineNumber, TotalDIN, CompletedDIN,
                   CompletionRate, SystemDINShare, CreatedAt, Status
            FROM TestPackagePreparationAlert
            WHERE Status = %s
            ORDER BY SystemCode, PipelineNumber
            """,
            (status,)
        )
        return cur.fetchall()
    finally:
        conn.close()


def update_pipeline_alert(alert_id, status):
    conn = create_connection()
    if not conn:
        return False
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE TestPackagePreparationAlert
            SET Status = %s
            WHERE AlertID = %s
            """,
            (status, alert_id)
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()
