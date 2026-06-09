"""
数据库迁移脚本：为 document_chunks 表新增结构化切片字段 + 创建 chunk_relations 表
"""
from sqlalchemy import text
from database import engine, SessionLocal

MIGRATIONS = [
    # document_chunks 新增列
    "ALTER TABLE document_chunks ADD COLUMN chunk_type VARCHAR(20) NULL",
    "ALTER TABLE document_chunks ADD COLUMN section_path VARCHAR(500) NULL",
    "ALTER TABLE document_chunks ADD COLUMN section_number VARCHAR(50) NULL",
    "ALTER TABLE document_chunks ADD COLUMN parent_chunk_id INTEGER NULL",
    "ALTER TABLE document_chunks ADD COLUMN page_number INTEGER NULL",
    # chunk_relations 表
    """
    CREATE TABLE IF NOT EXISTS chunk_relations (
        id INTEGER NOT NULL AUTO_INCREMENT,
        chunk_id INTEGER NOT NULL,
        related_chunk_id INTEGER NOT NULL,
        relation_type VARCHAR(20) NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (id),
        INDEX ix_chunk_relations_id (id),
        INDEX ix_chunk_relations_chunk_id (chunk_id)
    )
    """,
    # parent_chunk_id 索引
    "CREATE INDEX IF NOT EXISTS ix_document_chunks_parent_chunk_id ON document_chunks (parent_chunk_id)",
]

def run():
    db = SessionLocal()
    success = 0
    for i, sql in enumerate(MIGRATIONS):
        try:
            db.execute(text(sql))
            db.commit()
            print(f"[{i+1}/{len(MIGRATIONS)}] OK: {sql[:80]}...")
            success += 1
        except Exception as e:
            err = str(e)
            # 忽略 "Duplicate column" 和 "already exists" 错误
            if "Duplicate column" in err or "already exists" in err or "Duplicate key" in err:
                print(f"[{i+1}/{len(MIGRATIONS)}] SKIP (已存在): {sql[:80]}...")
            else:
                print(f"[{i+1}/{len(MIGRATIONS)}] FAIL: {err}")
    db.close()
    print(f"\n迁移完成: {success}/{len(MIGRATIONS)} 条执行成功")


if __name__ == "__main__":
    run()
