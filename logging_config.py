"""
结构化日志配置 —— structlog + 文件轮转
输出 JSON 格式到 stdout 和文件，自动注入 request_id
"""
import structlog
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from config import settings

LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)


def _add_request_id(logger, method_name, event_dict):
    """为每条日志注入 request_id（如有上下文）"""
    ctx = structlog.contextvars.get_contextvars()
    if "request_id" not in event_dict and "request_id" in ctx:
        event_dict["request_id"] = ctx["request_id"]
    return event_dict


def setup_logging():
    """初始化结构化日志"""
    # 文件处理器：单文件最大 10MB，保留 5 个备份
    file_handler = RotatingFileHandler(
        settings.LOG_FILE, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setLevel(getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))

    # 配置标准库 logging → structlog 桥接
    logging.basicConfig(
        format="%(message)s",
        level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
        handlers=[logging.StreamHandler(), file_handler],
    )

    # 配置 structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,  # 注入 request_id
            _add_request_id,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer() if settings.LOG_LEVEL.upper() == "DEBUG"
            else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = __name__):
    """获取结构化日志实例"""
    return structlog.get_logger(name)
