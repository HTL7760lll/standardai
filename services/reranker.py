"""
CrossEncoder 重排序 — 对检索候选结果精排，提升 top-k 准确率
"""
import os
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

from sentence_transformers import CrossEncoder
from logging_config import get_logger

logger = get_logger(__name__)

_model = None
MODEL_NAME = "BAAI/bge-reranker-base"


def get_reranker() -> CrossEncoder:
    """懒加载 CrossEncoder 模型"""
    global _model
    if _model is None:
        logger.info(f"加载重排序模型 {MODEL_NAME}...")
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
