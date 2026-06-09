"""
标准动态监控服务
- 标准版本登记（上传时自动触发）
- 标准状态查询（定时/手动检查）
- 状态变更日志记录
"""
import json
import re
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy import or_
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from models import StandardVersion, StandardStatusLog, Document


def register_standard_version(
    db: Session,
    document_id: int,
    standard_number: str,
    standard_name: str = "",
    source: str = "user_upload"
) -> Optional[StandardVersion]:
    """
    登记标准版本信息。
    - 如果 standard_number 已存在 → 更新关联
    - 如果不存在 → 新建记录
    """
    if not standard_number or standard_number.strip() == "":
        return None

    standard_number = standard_number.strip()

    try:
        # 查找已存在的版本记录
        existing = db.query(StandardVersion).filter(
            StandardVersion.standard_number == standard_number
        ).first()

        if existing:
            # 更新：关联新上传的文件，状态重置
            old_status = existing.status
            existing.document_id = document_id
            existing.standard_name = standard_name or existing.standard_name
            existing.source = source
            existing.last_checked = None  # 新上传需重新检查
            db.flush()

            if old_status != "unknown":
                _log_status_change(db, existing.id, old_status, "unknown",
                                   "新文件上传，状态待重新检查")
        else:
            existing = StandardVersion(
                standard_number=standard_number,
                standard_name=standard_name,
                document_id=document_id,
                status="unknown",
                source=source,
                last_checked=None,
            )
            db.add(existing)
            db.flush()

        db.commit()
        return existing

    except SQLAlchemyError:
        db.rollback()
        return None


def extract_standard_number_from_doc(db: Session, document_id: int) -> Optional[str]:
    """
    从文档的 Analysis 结果中提取标准编号。
    优先用 AI 分析结果，其次用正则从文件名提取。
    """
    from models import DocumentAnalysis

    analysis = db.query(DocumentAnalysis).filter(
        DocumentAnalysis.document_id == document_id
    ).order_by(DocumentAnalysis.created_at.desc()).first()

    if analysis and analysis.standard_type_guess:
        # 尝试从 standard_type_guess 字段提取编号
        # 这个字段可能存了编号信息
        pass

    # 从文件名提取（兜底）
    doc = db.query(Document).filter(Document.id == document_id).first()
    if doc:
        filename = doc.filename or ""
        # 复用 document_service 中的标准编号正则
        from services.document_service import _STD_NUM_RE
        match = _STD_NUM_RE.search(filename)
        if match:
            return match.group(0).strip()

    return None


def get_all_standards_status(
    db: Session,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20
) -> tuple[int, list[dict]]:
    """获取标准状态总览列表"""
    query = db.query(StandardVersion)
    if status:
        query = query.filter(StandardVersion.status == status)

    total = query.count()
    versions = query.order_by(StandardVersion.updated_at.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()

    result = []
    for v in versions:
        doc = None
        if v.document_id:
            doc = db.query(Document).filter(Document.id == v.document_id).first()

        result.append({
            "id": v.id,
            "standard_number": v.standard_number,
            "standard_name": v.standard_name,
            "version_year": v.version_year,
            "document_id": v.document_id,
            "filename": doc.filename if doc else None,
            "status": v.status,
            "replaced_by_number": v.replaced_by_number,
            "replaced_by_name": v.replaced_by_name,
            "effective_date": v.effective_date.isoformat() if v.effective_date else None,
            "expire_date": v.expire_date.isoformat() if v.expire_date else None,
            "source": v.source,
            "last_checked": v.last_checked.isoformat() if v.last_checked else None,
            "created_at": v.created_at.isoformat() if v.created_at else None,
        })

    return total, result


def get_standard_detail(db: Session, version_id: int) -> Optional[dict]:
    """获取标准详情含变更日志"""
    v = db.query(StandardVersion).filter(StandardVersion.id == version_id).first()
    if not v:
        return None

    logs = db.query(StandardStatusLog).filter(
        StandardStatusLog.standard_version_id == version_id
    ).order_by(StandardStatusLog.created_at.desc()).limit(20).all()

    doc = None
    if v.document_id:
        doc = db.query(Document).filter(Document.id == v.document_id).first()

    return {
        "id": v.id,
        "standard_number": v.standard_number,
        "standard_name": v.standard_name,
        "version_year": v.version_year,
        "document_id": v.document_id,
        "filename": doc.filename if doc else None,
        "status": v.status,
        "replaced_by_number": v.replaced_by_number,
        "replaced_by_name": v.replaced_by_name,
        "publish_date": v.publish_date.isoformat() if v.publish_date else None,
        "effective_date": v.effective_date.isoformat() if v.effective_date else None,
        "expire_date": v.expire_date.isoformat() if v.expire_date else None,
        "source": v.source,
        "last_checked": v.last_checked.isoformat() if v.last_checked else None,
        "check_result": json.loads(v.check_result) if v.check_result else None,
        "created_at": v.created_at.isoformat() if v.created_at else None,
        "updated_at": v.updated_at.isoformat() if v.updated_at else None,
        "status_logs": [{
            "id": log.id,
            "from_status": log.from_status,
            "to_status": log.to_status,
            "change_reason": log.change_reason,
            "triggered_by": log.triggered_by,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        } for log in logs],
    }


def update_standard_status(
    db: Session,
    version_id: int,
    new_status: str,
    replaced_by_number: str | None = None,
    replaced_by_name: str | None = None,
    expire_date: str | None = None,
    triggered_by: str = "manual",
    change_reason: str | None = None,
) -> Optional[StandardVersion]:
    """手动更新标准状态"""
    v = db.query(StandardVersion).filter(StandardVersion.id == version_id).first()
    if not v:
        return None

    try:
        old_status = v.status
        v.status = new_status
        if replaced_by_number is not None:
            v.replaced_by_number = replaced_by_number
        if replaced_by_name is not None:
            v.replaced_by_name = replaced_by_name
        if expire_date is not None:
            v.expire_date = datetime.fromisoformat(expire_date) if expire_date else v.expire_date

        _log_status_change(db, version_id, old_status, new_status,
                           change_reason or "手动状态更新", triggered_by)
        db.commit()
        db.refresh(v)
        return v
    except SQLAlchemyError:
        db.rollback()
        return None


def batch_check_standards(
    db: Session,
    check_interval_days: int = 30
) -> dict:
    """
    批量检查需要更新的标准状态。
    返回检查统计。
    """
    now = datetime.now()
    threshold = now - timedelta(days=check_interval_days)

    versions = db.query(StandardVersion).filter(
        or_(
            StandardVersion.last_checked.is_(None),
            StandardVersion.last_checked < threshold,
        )
    ).all()

    checked = 0
    updated = 0
    failed = 0

    for v in versions:
        try:
            result = _check_standard_online(v.standard_number)
            checked += 1

            if result.get("status") and result["status"] != v.status:
                old_status = v.status
                v.status = result["status"]
                v.replaced_by_number = result.get("replaced_by_number") or v.replaced_by_number
                v.replaced_by_name = result.get("replaced_by_name") or v.replaced_by_name
                v.effective_date = result.get("effective_date") or v.effective_date
                v.expire_date = result.get("expire_date") or v.expire_date
                v.check_result = json.dumps(result, ensure_ascii=False)
                v.last_checked = now

                _log_status_change(db, v.id, old_status, v.status,
                                   "自动检查发现状态变更", "system")
                updated += 1
            else:
                v.last_checked = now
                v.check_result = json.dumps(result, ensure_ascii=False)

        except Exception as e:
            v.last_checked = now
            v.check_result = json.dumps({"error": str(e)})
            failed += 1

    db.commit()
    return {"checked": checked, "updated": updated, "failed": failed}


def _check_standard_online(standard_number: str) -> dict:
    """
    在国家标准公开平台查询标准状态。
    当前版本：基于已知数据做启发式推断（后续可接入真实爬虫）。
    返回 dict 包含 status 等信息。
    """
    # 清理标准编号
    clean_num = standard_number.strip().upper()

    result = {
        "status": "unknown",
        "standard_name": "",
        "replaced_by_number": None,
        "replaced_by_name": None,
        "effective_date": None,
        "expire_date": None,
        "source": "heuristic",
    }

    # 启发式判断（基于标准编号年份）
    year_match = re.search(r'[—\-](\d{4})', standard_number)
    if year_match:
        year = int(year_match.group(1))
        now_year = datetime.now().year

        if now_year - year > 15:
            result["status"] = "expiring"
            result["note"] = "标准已发布超过15年，可能即将废止"
            return result
        elif now_year - year <= 5:
            result["status"] = "active"
            result["note"] = "标准较新，应当现行有效"
            return result

    result["status"] = "active"
    result["note"] = "无法确认精确状态，请手动核实"
    return result


def _log_status_change(
    db: Session,
    version_id: int,
    from_status: str,
    to_status: str,
    reason: str = "",
    triggered_by: str = "system"
):
    """记录状态变更日志"""
    log = StandardStatusLog(
        standard_version_id=version_id,
        from_status=from_status,
        to_status=to_status,
        change_reason=reason,
        triggered_by=triggered_by,
    )
    db.add(log)
