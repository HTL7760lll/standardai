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
    """获取 embedding 模型实例，带异常处理和自动重试"""
    global _model, _model_load_error

    if _model is not None:
        return _model

    if _model_load_error is not None:
        # 不清除错误缓存，避免每次请求都重试下载（消耗网络和 CPU）
        raise _model_load_error

    import time
    max_retries = 3
    last_error = None

    for attempt in range(1, max_retries + 1):
        try:
            print(f"[Embedding] 正在加载模型 {EMBEDDING_MODEL_NAME}（尝试 {attempt}/{max_retries}）...")
            # 优先从本地缓存加载，避免 SSL/网络问题
            try:
                _model = SentenceTransformer(EMBEDDING_MODEL_NAME, local_files_only=True)
                print("[Embedding] 从本地缓存加载模型")
            except Exception:
                print("[Embedding] 本地缓存未命中，尝试从网络下载...")
                print("[Embedding] 下载源: https://hf-mirror.com")
                _model = SentenceTransformer(EMBEDDING_MODEL_NAME)
            _model_load_error = None  # 成功后清除错误
            print(f"[Embedding] 模型加载完成！最大序列长度: {_model.max_seq_length}")
            return _model
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                wait = 5 * attempt
                print(f"[Embedding] 加载失败（{e}），{wait}秒后重试...")
                time.sleep(wait)

    _model_load_error = RuntimeError(
        f"Embedding 模型加载失败（重试{max_retries}次）: {last_error}\n"
        "请检查网络连接，或尝试手动下载模型放置到本地。"
    )
    raise _model_load_error


def generate_embedding(text: str) -> list[float]:
    """生成文本的向量嵌入（文档文本）"""
    try:
        model = get_model()
        embedding = model.encode(_clean_text(text))
        return embedding.tolist()
    except (UnboundLocalError, TypeError) as e:
        # tokenizer 内部 BUG：某些字符导致静默失败
        # 降级：纯 ASCII+中文清洗后再试
        print(f"[Embedding] tokenizer 异常，降级清洗后重试: {e}", file=sys.stderr)
        try:
            import re
            fallback = re.sub(r'[^\x20-\x7e一-鿿\n]', ' ', text)
            if not fallback.strip():
                raise ValueError("清洗后文本为空")
            embedding = model.encode(fallback)
            return embedding.tolist()
        except Exception:
            # 最终兜底：返回零向量，不阻塞流程
            print(f"[Embedding] 降级清洗也失败，使用零向量", file=sys.stderr)
            return [0.0] * 1024
    except Exception as e:
        print(f"[Embedding] 生成 embedding 失败: {e}", file=sys.stderr)
        raise


def _clean_text(text: str) -> str:
    """清洗 OCR 乱码字符，防止 tokenizer 崩溃"""
    import re
    # null 和行尾符
    text = text.replace("\x00", "").replace("\r", "\n")
    # PDF 字形 ID（/G21 /G2A 等）
    text = re.sub(r'[/Gg][0-9A-Fa-f]{1,3}', ' ', text)
    # 所有控制字符（除了换行和制表符）
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', text)
    # 非 ASCII 但也不是中文/日韩/常用字符的 → 去掉
    text = re.sub(r'[^\x20-\x7e一-鿿　-〿＀-￯\n]', ' ', text)
    return text


def generate_query_embedding(question: str) -> list[float]:
    """生成查询向量（语义检索用）"""
    try:
        model = get_model()
        embedding = model.encode(_clean_text(question))
        return embedding.tolist()
    except (UnboundLocalError, TypeError) as e:
        print(f"[Embedding] tokenizer 异常，降级清洗后重试: {e}", file=sys.stderr)
        try:
            import re
            fallback = re.sub(r'[^\x20-\x7e一-鿿\n]', ' ', question)
            if not fallback.strip():
                raise ValueError("清洗后文本为空")
            embedding = model.encode(fallback)
            return embedding.tolist()
        except Exception:
            print(f"[Embedding] 降级清洗也失败，使用零向量", file=sys.stderr)
            return [0.0] * 1024
    except Exception as e:
        print(f"[Embedding] 生成查询 embedding 失败: {e}", file=sys.stderr)
        raise


def generate_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """批量生成嵌入向量（用于证据句子抽取等场景）"""
    if not texts:
        return []
    try:
        model = get_model()
        cleaned = [_clean_text(t) for t in texts]
        embeddings = model.encode(cleaned, batch_size=32, show_progress_bar=False)
        return embeddings.tolist()
    except (UnboundLocalError, TypeError) as e:
        print(f"[Embedding] tokenizer 异常，降级清洗后重试: {e}", file=sys.stderr)
        try:
            import re
            fallback = [re.sub(r'[^\x20-\x7e一-鿿\n]', ' ', t) for t in texts]
            embeddings = model.encode(fallback, batch_size=32, show_progress_bar=False)
            return embeddings.tolist()
        except Exception:
            print(f"[Embedding] 降级清洗也失败，使用零向量", file=sys.stderr)
            return [[0.0] * 1024 for _ in texts]
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
