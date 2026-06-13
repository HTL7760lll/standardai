"""
faiss 向量索引 —— 替代 O(n) 线性扫描，提供毫秒级 ANN 语义检索
"""
import faiss
import numpy as np
from logging_config import get_logger

logger = get_logger(__name__)

_dim = 384  # MiniLM-L12-v2 输出维度
_index: faiss.IndexFlatIP | None = None  # Inner Product = Cosine（需归一化）
_chunk_ids: list[int] = []  # faiss 索引位置 → chunk.id 映射
_built = False


def build_index(embeddings: list[tuple[int, list[float]]]):
    """
    构建 faiss 索引。
    embeddings: [(chunk_id, vector), ...]
    """
    global _index, _chunk_ids, _built

    if not embeddings:
        logger.warning("向量索引构建跳过：无数据")
        return

    vectors = np.array([v for _, v in embeddings], dtype=np.float32)
    # L2 归一化 → Inner Product = Cosine Similarity
    faiss.normalize_L2(vectors)

    _index = faiss.IndexFlatIP(_dim)
    _index.add(vectors)
    _chunk_ids = [cid for cid, _ in embeddings]
    _built = True
    logger.info(f"faiss 索引构建完成：{_index.ntotal} 条向量")


def search(query_vector: list[float], k: int = 5) -> list[tuple[int, float]]:
    """
    搜索最相似的 k 个向量。
    返回: [(chunk_id, score), ...]
    """
    global _index, _chunk_ids, _built

    if not _built or _index is None:
        return []

    q = np.array([query_vector], dtype=np.float32)
    faiss.normalize_L2(q)
    scores, indices = _index.search(q, min(k, _index.ntotal))

    results = []
    for score, idx in zip(scores[0], indices[0]):
        if idx < 0 or idx >= len(_chunk_ids):
            continue
        results.append((_chunk_ids[idx], float(score)))
    return results


def is_built() -> bool:
    return _built


def rebuild_from_db(db):
    """从数据库重新加载所有 embedding 并重建索引"""
    from models import DocumentChunk

    chunks = db.query(DocumentChunk).filter(
        DocumentChunk.embedding.isnot(None)
    ).all()

    if not chunks:
        logger.warning("faiss 索引重建跳过：数据库无 embedding")
        return

    import services.embedding_service as es
    data = []
    for c in chunks:
        try:
            vec = es.json_to_embedding(c.embedding)
            data.append((c.id, vec))
        except Exception:
            continue

    build_index(data)
