import os
import json
import sys
from config import settings
from sentence_transformers import SentenceTransformer

os.environ["HF_ENDPOINT"] = settings.HF_ENDPOINT

_model = None
_model_load_error = None

EMBEDDING_MODEL_NAME = settings.EMBEDDING_MODEL
# BGE 模型检索任务 instruction 前缀（仅 BGE 模型使用）
BGE_RETRIEVAL_INSTRUCTION = "为这个句子生成表示以用于检索相关文章："


def get_model():
    """获取 embedding 模型实例，带异常处理和友好提示"""
    global _model, _model_load_error

    if _model is not None:
        return _model

    if _model_load_error is not None:
        raise _model_load_error

    try:
        print(f"[Embedding] 正在加载模型 {EMBEDDING_MODEL_NAME}，首次加载可能需要下载...")
        print("[Embedding] 下载源: https://hf-mirror.com")
        _model = SentenceTransformer(EMBEDDING_MODEL_NAME)
        print(f"[Embedding] 模型加载完成！最大序列长度: {_model.max_seq_length}")
    except Exception as e:
        _model_load_error = RuntimeError(
            f"Embedding 模型加载失败: {e}\n"
            "请检查网络连接，或尝试手动下载模型放置到本地。"
        )
        raise _model_load_error

    return _model


def generate_embedding(text: str) -> list[float]:
    """生成文本的向量嵌入（文档文本）"""
    try:
        model = get_model()
        embedding = model.encode(text)
        return embedding.tolist()
    except Exception as e:
        print(f"[Embedding] 生成 embedding 失败: {e}", file=sys.stderr)
        raise


def generate_query_embedding(question: str) -> list[float]:
    """生成查询向量（语义检索用）"""
    try:
        model = get_model()
        embedding = model.encode(question)
        return embedding.tolist()
    except Exception as e:
        print(f"[Embedding] 生成查询 embedding 失败: {e}", file=sys.stderr)
        raise


def generate_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """批量生成嵌入向量（用于证据句子抽取等场景）"""
    if not texts:
        return []
    try:
        model = get_model()
        embeddings = model.encode(texts, batch_size=32, show_progress_bar=False)
        return embeddings.tolist()
    except Exception as e:
        print(f"[Embedding] 批量生成 embedding 失败: {e}", file=sys.stderr)
        raise


def embedding_to_json(embedding: list[float]) -> str:
    return json.dumps(embedding)


def json_to_embedding(embedding_json: str) -> list[float]:
    return json.loads(embedding_json)

import math
def cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    """
    计算两个向量的余弦相似度
    返回值越接近 1，说明越相似
    """
    dot_product = 0
    norm_vec1 = 0
    norm_vec2 = 0

    for a, b in zip(vec1, vec2):
        dot_product += a * b
        norm_vec1 += a * a
        norm_vec2 += b * b

    if norm_vec1 == 0 or norm_vec2 == 0:
        return 0.0

    return dot_product / (math.sqrt(norm_vec1) * math.sqrt(norm_vec2))
