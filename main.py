import time
import uuid
import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from config import settings
from logging_config import setup_logging, get_logger
from routers.documents import router as documents_router
from routers.auth import router as auth_router
from routers.annotations import router as annotations_router

setup_logging()
logger = get_logger(__name__)

limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])
app = FastAPI(title=settings.APP_TITLE)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

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

app.include_router(auth_router)
app.include_router(annotations_router)
app.include_router(documents_router)
