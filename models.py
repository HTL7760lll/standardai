from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, JSON, Text, Boolean

from database import Base


# ── 用户模型 ──
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(200), nullable=False)
    role = Column(String(20), default="engineer")  # admin / engineer / viewer
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)

# 文件保存模型
class Document(Base): #定义数据库模型

    __tablename__ ="documents"
    id = Column(Integer, primary_key=True,index=True)
    filename = Column(String(100),nullable=False,unique=True)
    filepath = Column(String(100),nullable=False)
    standard_type = Column(String(100),nullable=False,index=True)
    industry = Column(String(100),nullable=False,index=True)
    tags = Column(JSON)
    created_at = Column(DateTime,default=datetime.now)
    updated_at = Column(DateTime,default=datetime.now,onupdate=datetime.now)

# 文件切片模型
class DocumentChunk(Base):

    __tablename__ ="document_chunks"
    id = Column(Integer, primary_key=True,index=True) #每个 chunk 自己的编号
    document_id = Column(Integer,nullable=False,index=True) #属于哪个文档
    chunk_index = Column(Integer,nullable=False) #这个文档中的第几个切片
    embedding = Column(Text,nullable=False)
    content = Column(Text,nullable=False)  #切片文本内容
    created_at= Column(DateTime,default=datetime.now) #创建时间
    # 新增字段：结构化切片
    chunk_type = Column(String(20),nullable=True) #类型: cover/preface/scope/references/term/clause/table/figure/appendix
    section_path = Column(String(500),nullable=True) #章节路径，如 "5技术要求 > 5.2检验要求 > 5.2.1出厂检验"
    section_number = Column(String(50),nullable=True) #条款编号，如 "5.2.1"
    parent_chunk_id = Column(Integer,nullable=True,index=True) #父级chunk ID
    page_number = Column(Integer,nullable=True) #所在页码


# Chunk 关系表
class ChunkRelation(Base):
    __tablename__ = "chunk_relations"

    id = Column(Integer, primary_key=True, index=True)
    chunk_id = Column(Integer, nullable=False, index=True)
    related_chunk_id = Column(Integer, nullable=False)
    relation_type = Column(String(20), nullable=False)  # parent / child / sibling
    created_at = Column(DateTime, default=datetime.now)

# 文档分析模型
class DocumentAnalysis(Base):
    __tablename__ = "document_analysis"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, nullable=False, index=True)
    standard_type_guess = Column(String(100), nullable=True)
    industry_guess = Column(String(100), nullable=True)
    summary = Column(Text, nullable=True)
    keywords = Column(Text, nullable=True)
    scope = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now)


# ── OCR 缓存 ──

class OcrResultCache(Base):
    """OCR 结果缓存表"""
    __tablename__ = "ocr_result_cache"

    id = Column(Integer, primary_key=True, index=True)
    content_hash = Column(String(64), unique=True, nullable=False, index=True)
    ocr_text = Column(Text, nullable=False)
    model_name = Column(String(50), nullable=True)
    page_count = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.now)
