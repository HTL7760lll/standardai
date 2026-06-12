from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker,declarative_base
from config import settings

# 1. 数据库连接地址（从 .env 读取）
DATABASE_URL = settings.DATABASE_URL

# 2. 创建 engine
engine = create_engine(DATABASE_URL, pool_size=10, max_overflow=20, pool_recycle=3600)

# 3. 创建 SessionLocal
SessionLocal = sessionmaker( #会话工厂
    autocommit=False,
    autoflush=False,
    bind=engine
)

# 4. 创建 Base
Base = declarative_base() #ORM模型基类

def get_db():
    db = SessionLocal()  # 创建一个数据库会话
    try:
        yield db # 把这个数据库会话交给接口使用。
    finally:
        db.close() # 接口执行完之后，关闭数据库会话。