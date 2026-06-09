"""
标准动态监控接口
"""
from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy.orm import Session
from database import get_db
import services.watchdog_service as watchdog_service

router = APIRouter(prefix="/standards", tags=["standards-watchdog"])


@router.get("/watchdog")
def get_standards_status(
    status: str | None = Query(None, description="按状态筛选: active/expiring/replaced/abolished/unknown"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, le=100),
    db: Session = Depends(get_db),
):
    """获取所有标准状态监控列表"""
    total, items = watchdog_service.get_all_standards_status(
        db, status=status, page=page, page_size=page_size
    )
    return {
        "message": "查询成功",
        "total": total,
        "page": page,
        "page_size": page_size,
        "standards": items,
    }


@router.get("/watchdog/{version_id}")
def get_standard_detail(version_id: int, db: Session = Depends(get_db)):
    """获取标准详情（含变更日志）"""
    detail = watchdog_service.get_standard_detail(db, version_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="标准版本记录不存在")
    return {
        "message": "查询成功",
        "standard": detail,
    }


@router.post("/watchdog/{version_id}/check")
def trigger_standard_check(version_id: int, db: Session = Depends(get_db)):
    """手动触发单个标准的状态检查"""
    from datetime import datetime

    v = db.query(watchdog_service.StandardVersion).filter(
        watchdog_service.StandardVersion.id == version_id
    ).first()
    if v is None:
        raise HTTPException(status_code=404, detail="标准版本记录不存在")

    try:
        result = watchdog_service._check_standard_online(v.standard_number)
        old_status = v.status
        new_status = result.get("status", v.status)

        if new_status != old_status:
            v.status = new_status
            v.replaced_by_number = result.get("replaced_by_number") or v.replaced_by_number
            v.replaced_by_name = result.get("replaced_by_name") or v.replaced_by_name
            watchdog_service._log_status_change(
                db, version_id, old_status, new_status,
                "手动触发检查", "user"
            )

        v.last_checked = datetime.now()
        import json
        v.check_result = json.dumps(result, ensure_ascii=False)
        db.commit()
        db.refresh(v)

        return {
            "message": "检查完成",
            "standard_number": v.standard_number,
            "status": v.status,
            "previous_status": old_status,
            "check_result": result,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"检查失败: {str(e)}")


@router.post("/watchdog/batch-check")
def trigger_batch_check(db: Session = Depends(get_db)):
    """批量检查所有需要更新的标准状态"""
    result = watchdog_service.batch_check_standards(db)
    return {
        "message": "批量检查完成",
        "checked": result["checked"],
        "updated": result["updated"],
        "failed": result["failed"],
    }


@router.patch("/watchdog/{version_id}/status")
def update_standard_status_manually(
    version_id: int,
    new_status: str = Query(..., description="新状态: active/expiring/replaced/abolished"),
    replaced_by_number: str | None = Query(None),
    replaced_by_name: str | None = Query(None),
    expire_date: str | None = Query(None, description="到期日 YYYY-MM-DD"),
    change_reason: str | None = Query(None, description="变更原因"),
    db: Session = Depends(get_db),
):
    """手动更新标准状态"""
    v = watchdog_service.update_standard_status(
        db, version_id, new_status,
        replaced_by_number=replaced_by_number,
        replaced_by_name=replaced_by_name,
        expire_date=expire_date,
        triggered_by="user",
        change_reason=change_reason,
    )
    if v is None:
        raise HTTPException(status_code=404, detail="标准版本记录不存在")
    return {
        "message": "状态更新成功",
        "standard_number": v.standard_number,
        "new_status": v.status,
    }


def _extract_standard_number_multi_source(db, doc) -> tuple[str, str]:
    """
    从多个来源提取标准编号和标准名称。
    优先级：文档内容(封面chunk) > 分析结果 > 文件名
    返回: (standard_number, extraction_source)
    """
    from services.document_service import _STD_NUM_RE
    filename = doc.filename or ""

    # ── 来源1：从文档 chunks 内容中提取（封面/前言 chunk）──
    try:
        from models import DocumentChunk
        cover_chunks = db.query(DocumentChunk).filter(
            DocumentChunk.document_id == doc.id,
            DocumentChunk.chunk_type.in_(["cover", "preface"])
        ).order_by(DocumentChunk.chunk_index.asc()).limit(3).all()

        for chunk in cover_chunks:
            content = chunk.content or ""
            # 去掉内置前缀再搜索
            clean = content.split("---\n", 1)[-1] if "---\n" in content else content
            match = _STD_NUM_RE.search(clean)
            if match:
                return (match.group(0).strip(), "document_content")
    except Exception:
        pass

    # ── 来源2：从 DocumentAnalysis 表中提取 ──
    try:
        from models import DocumentAnalysis
        analysis = db.query(DocumentAnalysis).filter(
            DocumentAnalysis.document_id == doc.id
        ).order_by(DocumentAnalysis.created_at.desc()).first()

        if analysis and analysis.standard_type_guess:
            # 分析结果的 standard_type_guess 可能包含编号信息
            guess = analysis.standard_type_guess or ""
            match = _STD_NUM_RE.search(guess)
            if match:
                return (match.group(0).strip(), "analysis_result")
    except Exception:
        pass

    # ── 来源3：从文件名提取 ──
    match = _STD_NUM_RE.search(filename)
    if match:
        return (match.group(0).strip(), "filename")

    # ── 来源4：如果有文件路径，尝试解析文档前几页 ──
    filepath = doc.filepath
    if filepath:
        try:
            from pathlib import Path
            from services.document_service import parse_document
            fp = Path(filepath)
            if fp.exists():
                text = parse_document(str(fp))
                if text and len(text) > 50:
                    # 只搜前 3000 个字符（封面区域）
                    head = text[:3000]
                    match = _STD_NUM_RE.search(head)
                    if match:
                        return (match.group(0).strip(), "document_parse")
        except Exception:
            pass

    return ("", "none")


@router.post("/watchdog/register/{document_id}")
def register_document_to_watchdog(document_id: int, db: Session = Depends(get_db)):
    """将已有文档手动注册到标准监控（多源提取标准编号）"""
    from models import Document

    doc = db.query(Document).filter(Document.id == document_id).first()
    if doc is None:
        raise HTTPException(status_code=404, detail="文档不存在")

    filename = doc.filename or ""
    std_num, source = _extract_standard_number_multi_source(db, doc)

    if not std_num:
        raise HTTPException(
            status_code=400,
            detail="无法从文件名、文档内容或分析结果中提取标准编号。"
                   "请确保：1) 文件名含标准编号，或 2) 先生成切片（封面内容可被解析），或 3) 先执行文档分析"
        )

    v = watchdog_service.register_standard_version(
        db, document_id, std_num, filename, source=source
    )
    if v is None:
        raise HTTPException(status_code=500, detail="注册失败")

    return {
        "message": "注册成功",
        "standard_number": v.standard_number,
        "status": v.status,
        "extraction_source": source,
    }


@router.post("/watchdog/backfill-all")
def backfill_all_documents(db: Session = Depends(get_db)):
    """一键回填：将库内所有已有文档注册到标准监控（多源提取标准编号）"""
    from models import Document

    docs = db.query(Document).all()
    registered = 0
    skipped = 0

    for doc in docs:
        filename = doc.filename or ""
        std_num, source = _extract_standard_number_multi_source(db, doc)
        if std_num:
            v = watchdog_service.register_standard_version(
                db, doc.id, std_num, filename, source=f"backfill_{source}"
            )
            if v:
                registered += 1
            else:
                skipped += 1
        else:
            skipped += 1

    return {
        "message": "回填完成",
        "total": len(docs),
        "registered": registered,
        "skipped": skipped,
    }
