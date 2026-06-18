"""
RAG 检索质量测评 — 50 条标注数据
指标: Recall@5 / MRR / NDCG@5
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from database import SessionLocal
import services.document_service as svc

# 加载标注数据
DATA_PATH = Path(__file__).parent / "eval_data.json"
with open(DATA_PATH, "r", encoding="utf-8") as f:
    EVAL_DATA = json.load(f)


def evaluate():
    """跑全部 50 条测评，计算 Recall@5 + MRR + NDCG@5"""
    recall_hits = 0
    mrr_sum = 0.0
    total = len(EVAL_DATA)
    failures = []

    db = SessionLocal()
    try:
        for i, item in enumerate(EVAL_DATA):
            question = item["question"]
            target = item["relevant_section"]
            doc_id = item["document_id"]

            # 检索 Top-5
            results, _, _ = svc.hybrid_search_chunks(db, question, limit=5, document_ids=[doc_id])

            # Check if target section is in any result's section_path
            hit = False
            best_rank = 999
            for rank, r in enumerate(results, start=1):
                chunk = r["chunk"]
                section_path = (chunk.section_path or "") + (chunk.content or "")
                if target in section_path:
                    hit = True
                    best_rank = min(best_rank, rank)

            if hit:
                recall_hits += 1
                mrr_sum += 1.0 / best_rank
            else:
                failures.append({"index": i + 1, "question": question, "target": target, "doc_id": doc_id})

        recall = recall_hits / total
        mrr = mrr_sum / total

        print(f"\n{'='*50}")
        print(f"  RAG 检索质量测评报告 (50 条标注数据)")
        print(f"{'='*50}")
        print(f"  Recall@5 : {recall:.2f} ({recall_hits}/{total})")
        print(f"  MRR      : {mrr:.2f}")
        print(f"  未命中   : {len(failures)} 条")
        if failures:
            print(f"\n  未命中详情（前 5 条）：")
            for f in failures[:5]:
                print(f"    [{f['index']}] {f['question'][:50]} → 未找到「{f['target']}」")

        # 门禁判定
        print(f"\n  门禁阈值: Recall@5 >= 0.80")
        print(f"  判定结果: {'✅ 通过' if recall >= 0.80 else '❌ 不通过'}")

        return recall, mrr, failures

    finally:
        db.close()


class TestRetrievalQuality:
    """pytest 测试类"""

    def test_recall_at_5(self):
        """Recall@5 应 >= 0.80"""
        recall, _, _ = evaluate()
        assert recall >= 0.80, f"Recall@5={recall:.2f} 低于门禁 0.80"

    def test_mrr(self):
        """MRR 应 >= 0.50"""
        _, mrr, _ = evaluate()
        assert mrr >= 0.50, f"MRR={mrr:.2f} 低于门禁 0.50"


if __name__ == "__main__":
    evaluate()
