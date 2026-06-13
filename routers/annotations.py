"""用户标注笔记 API"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from database import get_db
from models import Annotation, User
from routers.auth import get_current_user

router = APIRouter(prefix="/annotations", tags=["annotations"])


class AnnotationCreate(BaseModel):
    document_id: int
    chunk_id: int | None = None
    content: str


@router.post("")
def create_annotation(req: AnnotationCreate, db: Session = Depends(get_db),
                       user: User = Depends(get_current_user)):
    if not req.content.strip():
        raise HTTPException(400, "标注内容不能为空")
    ann = Annotation(user_id=user.id, document_id=req.document_id,
                     chunk_id=req.chunk_id, content=req.content.strip())
    db.add(ann); db.commit(); db.refresh(ann)
    return {"id": ann.id, "content": ann.content, "created_at": str(ann.created_at)}


@router.get("")
def list_annotations(document_id: int | None = None, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    q = db.query(Annotation).filter(Annotation.user_id == user.id)
    if document_id: q = q.filter(Annotation.document_id == document_id)
    anns = q.order_by(Annotation.created_at.desc()).all()
    return [{"id": a.id, "document_id": a.document_id, "chunk_id": a.chunk_id,
             "content": a.content, "created_at": str(a.created_at)} for a in anns]


@router.delete("/{annotation_id}")
def delete_annotation(annotation_id: int, db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)):
    ann = db.query(Annotation).filter(Annotation.id == annotation_id, Annotation.user_id == user.id).first()
    if not ann:
        raise HTTPException(404, "标注不存在或无权删除")
    db.delete(ann); db.commit()
    return {"message": "已删除"}
