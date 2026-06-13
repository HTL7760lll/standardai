import time
import uuid
import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from config import settings
from logging_config import setup_logging, get_logger
from routers.documents import router as documents_router

setup_logging()
logger = get_logger(__name__)

app = FastAPI(title=settings.APP_TITLE)

origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    request_id = str(uuid.uuid4())[:8]
    start = time.time()
    structlog.contextvars.bind_contextvars(request_id=request_id)
    response = await call_next(request)
    elapsed = time.time() - start
    logger.info("request", method=request.method, path=request.url.path,
                status=response.status_code, duration_ms=round(elapsed*1000, 2))
    structlog.contextvars.unbind_contextvars("request_id")
    return response

@app.get("/health")
def health_check():
    from database import engine
    try:
        conn = engine.connect(); conn.close()
        db_status = "connected"
    except Exception:
        db_status = "disconnected"
    llm_status = "available" if settings.DEEPSEEK_API_KEY else "unavailable"
    return {"status": "ok", "database": db_status, "llm": llm_status}


@app.on_event("startup")
def build_vector_index():
    """启动时构建 faiss 向量索引"""
    try:
        from database import SessionLocal
        import services.vector_index as vi
        db = SessionLocal()
        vi.rebuild_from_db(db)
        db.close()
    except Exception as e:
        logger.warning(f"faiss 索引构建跳过: {e}")

app.include_router(documents_router)
