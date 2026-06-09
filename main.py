from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers.documents import router as documents_router
from routers.watchdog import router as watchdog_router

# 注册路由
app = FastAPI(title="智能标准文档管理与RAG问答系统")

# CORS 跨域配置（允许前端 localhost:5173 访问）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents_router)
app.include_router(watchdog_router)
