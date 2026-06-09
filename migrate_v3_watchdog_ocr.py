"""
数据库迁移脚本 v3：
- 新增 standard_versions 表（标准版本追踪）
- 新增 standard_status_log 表（状态变更日志）
- 新增 ocr_result_cache 表（OCR 缓存）
"""
from sqlalchemy import text
from database import engine, SessionLocal

MIGRATIONS = [
    # ── standard_versions ──
    """
    CREATE TABLE IF NOT EXISTS standard_versions (
        id INTEGER NOT NULL AUTO_INCREMENT,
        standard_number VARCHAR(100) NOT NULL,
        standard_name VARCHAR(300) NULL,
        version_year VARCHAR(10) NULL,
        document_id INTEGER NULL,
        status VARCHAR(20) DEFAULT 'unknown',
        replaced_by_number VARCHAR(100) NULL,
        replaced_by_name VARCHAR(300) NULL,
        publish_date DATETIME NULL,
        effective_date DATETIME NULL,
        expire_date DATETIME NULL,
        source VARCHAR(30) DEFAULT 'user_upload',
        last_checked DATETIME NULL,
        check_result TEXT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        PRIMARY KEY (id),
        INDEX ix_standard_versions_id (id),
        INDEX ix_standard_versions_standard_number (standard_number),
        INDEX ix_standard_versions_document_id (document_id),
        INDEX ix_standard_versions_status (status)
    )
    """,
    # ── standard_status_log ──
    """
    CREATE TABLE IF NOT EXISTS standard_status_log (
        id INTEGER NOT NULL AUTO_INCREMENT,
        standard_version_id INTEGER NOT NULL,
        from_status VARCHAR(20) NULL,
        to_status VARCHAR(20) NOT NULL,
        change_reason TEXT NULL,
        triggered_by VARCHAR(30) DEFAULT 'system',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (id),
        INDEX ix_standard_status_log_id (id),
        INDEX ix_standard_status_log_standard_version_id (standard_version_id)
    )
    """,
    # ── ocr_result_cache ──
    """
    CREATE TABLE IF NOT EXISTS ocr_result_cache (
        id INTEGER NOT NULL AUTO_INCREMENT,
        content_hash VARCHAR(64) NOT NULL,
        ocr_text TEXT NOT NULL,
        model_name VARCHAR(50) NULL,
        page_count INTEGER DEFAULT 1,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (id),
        UNIQUE INDEX ix_ocr_result_cache_content_hash (content_hash)
    )
    """,
]


def run():
    db = SessionLocal()
    success = 0
    for i, sql in enumerate(MIGRATIONS):
        try:
            db.execute(text(sql))
            db.commit()
            print(f"[{i+1}/{len(MIGRATIONS)}] OK: {sql.strip()[:80]}...")
            success += 1
        except Exception as e:
            err = str(e)
            if "Duplicate" in err or "already exists" in err:
                print(f"[{i+1}/{len(MIGRATIONS)}] SKIP (已存在)")
            else:
                print(f"[{i+1}/{len(MIGRATIONS)}] FAIL: {err}")
    db.close()
    print(f"\n迁移完成: {success}/{len(MIGRATIONS)} 条执行成功")


if __name__ == "__main__":
    run()
