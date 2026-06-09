import models
from database import Base, engine

print("当前已经注册的表：", Base.metadata.tables.keys())

Base.metadata.create_all(bind=engine)

print("构建成功")