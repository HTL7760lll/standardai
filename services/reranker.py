"""
CrossEncoder 重排序 — 对检索候选结果精排，提升 top-k 准确率
"""
import os
from pathlib import Path
from logging_config import get_logger

logger = get_logger(__name__)

_model = None
MODEL_NAME = "BAAI/bge-reranker-base"
LOCAL_DIR = Path(__file__).parent.parent / "models" / "bge-reranker-base"


def _download_model():
    """通过 hf-mirror 手动下载模型到本地"""
    if LOCAL_DIR.exists() and (LOCAL_DIR / "config.json").exists():
        return  # 已下载

    from huggingface_hub import snapshot_download
    LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        MODEL_NAME,
        local_dir=str(LOCAL_DIR),
        endpoint="https://hf-mirror.com",
        resume_download=True,
    )
    logger.info(f"重排序模型下载完成: {LOCAL_DIR}")


def get_reranker():
    """懒加载 CrossEncoder 模型（优先本地文件）"""
    global _model
    if _model is None:
        # 手动下载到本地
        try:
            _download_model()
        except Exception as e:
            logger.warning(f"自动下载失败，尝试直接加载: {e}")

        from sentence_transformers import CrossEncoder

        if LOCAL_DIR.exists() and (LOCAL_DIR / "config.json").exists():
            logger.info(f"从本地加载重排序模型: {LOCAL_DIR}")
            _model = CrossEncoder(str(LOCAL_DIR), max_length=512)
        else:
            # 兜底：联网下载
            logger.info(f"本地模型不存在，联网加载 {MODEL_NAME}...")
            os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
            _model = CrossEncoder(MODEL_NAME, max_length=512)

        logger.info("重排序模型加载完成")
    return _model


def rerank(question: str, candidates: list[dict], top_k: int = 5) -> list[dict]:
    """
    对候选结果重新排序。
    candidates: [{"chunk": DocumentChunk, "score": float, ...}, ...]
    返回 top_k 个重新排序后的结果，score 已更新为 reranker 分数。
    """
    if not candidates or len(candidates) <= 1:
        return candidates

    try:
        model = get_reranker()
    except Exception as e:
        logger.warning(f"重排序模型不可用，跳过精排: {e}")
        return candidates[:top_k]

    # 构建 (question, content) 对
    pairs = []
    for item in candidates:
        content = item["chunk"].content or ""
        # 取前 500 字，平衡速度和上下文
        pairs.append([question, content[:500]])

    # 批量打分
    scores = model.predict(pairs, show_progress_bar=False)

    # 更新分数并排序
    for i, score in enumerate(scores):
        candidates[i]["score"] = float(score)
        candidates[i]["match_type"] = candidates[i].get("match_type", "keyword") + "+rerank"

    candidates.sort(key=lambda x: x["score"], reverse=True)
    return candidates[:top_k]
