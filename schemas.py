
from pydantic import BaseModel,Field,field_validator
from datetime import datetime

class DocumentCreate(BaseModel): #新增时用
    filename:str
    @field_validator("filename") #数据验证器
    @classmethod
    def check_filename(cls, value):
        value = value.strip()
        if value == "":
            raise ValueError("文件名不能为空")
        return value
    standard_type:str
    @field_validator("standard_type")
    @classmethod
    def check_standard_type(cls, value):
        value = value.strip()
        if value == "":
            raise ValueError("标准类型不能为空")
        return value
    industry:str
    @field_validator("industry")
    @classmethod
    def check_industry(cls, value):
        value = value.strip()
        if value == "":
            raise ValueError("行业不能为空")
        return value
    tags: list[str] = Field(..., min_length=1)
    @field_validator("tags")
    @classmethod
    def check_tags(cls, value):
        cleaned_tags = []
        for tag in  value:
            tag = tag.strip()
            if tag == "":
                raise  ValueError("标签不能为空")
            cleaned_tags.append(tag)
        return cleaned_tags



class DocumentUpdate(BaseModel): #修改时用
    filename: str | None = Field(None)
    standard_type:str | None = Field(None)
    industry: str  | None = Field(None)
    tags: list[str] | None = Field(None)

class DocumentOut(BaseModel): #返回单个数据时用
    id: int
    filename: str
    filepath: str | None = None
    standard_type: str
    industry: str
    tags: list[str] | None = None
    created_at: datetime
    updated_at: datetime
    model_config = {
        "from_attributes": True #它的作用是让 Pydantic 能识别 SQLAlchemy 的 Document 对象
    }

class DocumentMessageOut(BaseModel):
    message: str
    document: DocumentOut

class MessageOut(BaseModel):
    message: str

class DocumentListResponse(BaseModel): #返回多个数据时用
    message: str
    documents: list[DocumentOut]
    page: int
    page_size: int
    total_count: int

class DocumentStatsResponse(BaseModel):
    total: int
    standard_types: dict[str, int] #字典[键的类型，值的类型]
    industries: dict[str, int]
    tags: dict[str, int]

class DocumentSearchItemOut(BaseModel):
    id: int
    filename: str
    standard_type: str
    industry: str
    tags: list[str] | None = None
    match_fields: list[str]

class DocumentSearchResponse(BaseModel):
    message: str
    keyword: str
    total_count: int
    page: int
    page_size: int
    has_more: bool
    documents: list[DocumentSearchItemOut]

class AskQuestion(BaseModel):
    document_id: int | None = None
    question: str
    limit: int = 5