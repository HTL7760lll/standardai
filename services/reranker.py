"""
CrossEncoder 重排序 — 对检索候选结果精排，提升 top-k 准确率
"""
import os
import threading
from pathlib import Path
from logging_config import get_logger

logger = get_logger(__name__)

_model = None
_init_lock = threading.Lock()
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
    """线程安全懒加载 CrossEncoder 模型（优先本地文件）"""
    global _model
    if _model is not None:
        return _model

    with _init_lock:
        if _model is not None:
            return _model

        try:
            _download_model()
        except Exception as e:
            logger.warning(f"自动下载失败，尝试直接加载: {e}")

        from sentence_transformers import CrossEncoder

        if LOCAL_DIR.exists() and (LOCAL_DIR / "config.json").exists():
            logger.info(f"从本地加载重排序模型: {LOCAL_DIR}")
            _model = CrossEncoder(str(LOCAL_DIR), max_length=512)
        else:
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
        # 截断 + 清理不可见字符，避免 tokenizer 崩溃
        clean = content[:500].replace("\x00", "").replace("\r", "\n")
        pairs.append([question.strip(), clean.strip()])

    # 批量打分
    try:
        raw_scores = model.predict(pairs, show_progress_bar=False)
    except Exception as e:
        logger.warning(f"精排打分失败，跳过重排序: {e}")
        return candidates[:top_k]

    # Sigmoid归一化到 0-1
    import math
    scores = [1.0 / (1.0 + math.exp(-s)) for s in raw_scores]

    # 更新分数并排序
    for i, score in enumerate(scores):
        candidates[i]["score"] = round(score, 4)
        candidates[i]["match_type"] = candidates[i].get("match_type", "keyword") + "+rerank"

    candidates.sort(key=lambda x: x["score"], reverse=True)
    return candidates[:top_k]


def check_faithfulness(answer: str, chunks: list[str]) -> dict:
    """
    忠实度检测：用 CrossEncoder 逐句判断回答是否被检索原文支撑。
    - answer: LLM 生成的完整回答
    - chunks: 检索到的原文 chunk 列表
    返回 {"score": 0.0-1.0, "flagged": [可疑句子列表]}
    """
    if not answer or not chunks:
        return {"score": 1.0, "flagged": []}

    # 拆回答为句子
    import re
    sentences = [s.strip() for s in re.split(r'[。！？\n]', answer) if len(s.strip()) >= 8]

    if not sentences:
        return {"score": 1.0, "flagged": []}

    # 合并原文为一段（清理不可见字符）
    context = " ".join([c[:300].replace("\x00", "").replace("\r", "\n") for c in chunks[:5]])

    try:
        model = get_reranker()
    except Exception:
        return {"score": 0.5, "flagged": []}

    flagged = []
    total_score = 0.0

    for sent in sentences:
        # 每句 vs 原文，用 CrossEncoder 打分
        import math
        clean_sent = sent.strip().replace("\x00", "")
        clean_ctx = context.strip()
        try:
            raw = float(model.predict([[clean_sent, clean_ctx]], show_progress_bar=False)[0])
            score = 1.0 / (1.0 + math.exp(-raw))
        except Exception:
            continue  # 跳过无法打分的句子

        is_supported = score >= 0.5  # 大于 0.5 表示有依据

        if not is_supported:
            flagged.append({"sentence": sent, "score": round(score, 3)})

        total_score += 1.0 if is_supported else 0.0

    faithfulness = total_score / len(sentences) if sentences else 1.0
    return {"score": round(faithfulness, 3), "flagged": flagged}
