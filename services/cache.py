"""
轻量内存缓存 —— 热点数据 TTL 缓存，避免每次请求查库
"""
import time
import threading
from logging_config import get_logger

logger = get_logger(__name__)

_cache: dict[str, tuple[float, any]] = {}
_lock = threading.Lock()
_hits = 0
_misses = 0


def get(key: str):
    """读取缓存，过期返回 None"""
    global _hits, _misses
    with _lock:
        if key in _cache:
            expires_at, value = _cache[key]
            if time.time() < expires_at:
                _hits += 1
                return value
            del _cache[key]
    _misses += 1
    return None


def set(key: str, value: any, ttl: int = 300):
    """写入缓存，默认 TTL 300 秒"""
    with _lock:
        _cache[key] = (time.time() + ttl, value)


def delete(key: str):
    with _lock:
        _cache.pop(key, None)


def clear():
    with _lock:
        _cache.clear()


def stats() -> dict:
    return {
        "size": len(_cache),
        "hits": _hits,
        "misses": _misses,
    }
