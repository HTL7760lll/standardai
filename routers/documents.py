from fastapi import APIRouter,HTTPException, Query, Depends,UploadFile,File,Form, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from routers.auth import get_current_user, require_role
from models import User

limiter = Limiter(key_func=get_remote_address)
from sqlalchemy.exc import SQLAlchemyError
import services.document_service
from schemas import (DocumentCreate, DocumentUpdate, DocumentOut, DocumentListResponse,
                     DocumentMessageOut, MessageOut, DocumentStatsResponse, DocumentSearchResponse, AskQuestion)
from sqlalchemy.orm import Session
from database import get_db
from fastapi.responses import FileResponse, StreamingResponse
import json
import asyncio
from pathlib import Path
import services.llm_service
import services.analysis_service


router = APIRouter()

@router.post("/documents/manual", response_model=DocumentMessageOut)  # 新增标准文件接口,但是不进行切片分析，只增加文本信息
async def create_document(document: DocumentCreate, db: Session = Depends(get_db)):
    existing_document = services.document_service.find_document(db,document.filename)
    if existing_document is not None:
        raise HTTPException(status_code=409, detail="标准文件已存在")
    new_document = services.document_service.create_document(db,document.filename,
    document.standard_type,document.industry,document.tags)
    if new_document is None:
        raise HTTPException(status_code=500, detail="新增标准文件失败")
    return {"message": "新增标准文件成功",
            "document": new_document,
            }

@router.post("/documents/upload", response_model=DocumentMessageOut)
@limiter.limit("10/minute")
async def upload_document(request: Request, file: UploadFile = File(...),
                          user: User = Depends(require_role("admin", "engineer")),
                          standard_type:str =Form(...), #Form是普通字段，因为返回的值是普通字段不是JSON
                          industry:str =Form(...),
                          tags: str = Form(...),
                          db: Session = Depends(get_db)):

    existing_document = services.document_service.find_document(db,file.filename)
    if existing_document is not None:
        raise HTTPException(status_code=409, detail="标准文件已存在")
    filepath = await services.document_service.get_file(file)
    if filepath is None:
        raise HTTPException(status_code=400, detail="只能上传 .pdf、.docx、.txt 类型的文件")
    try :
        new_document = services.document_service.create_document(db,file.filename,standard_type,industry,tags,filepath,owner_id=user.id)
        if new_document is None:
            raise HTTPException(status_code=500, detail="上传标准文件失败")

        # ── 后端自动切片：上传后立即解析+切片+生成 embedding ──
        chunk_result = None
        chunk_error = None
        try:
            text = services.document_service.parse_document(filepath)
            if text and text.strip():
                chunks_v2 = services.document_service.smart_split_v2(
                    text, filename=file.filename or ""
                )
                # 删除旧 chunks（如有）
                services.document_service.delete_chunks_by_id(db, new_document.id)
                # 保存新 chunks（含 embedding 生成）
                saved = services.document_service.save_document_chunk(
                    db, chunks_v2, new_document.id
                )
                if saved:
                    type_counts = {}
                    for c in chunks_v2:
                        ct = c.get("chunk_type", "unknown") if isinstance(c, dict) else "unknown"
                        type_counts[ct] = type_counts.get(ct, 0) + 1
                    chunk_result = {
                        "total_chunks": len(chunks_v2),
                        "chunk_types": type_counts,
                    }
            else:
                chunk_error = "文档解析结果为空，可能为扫描件或图片PDF"
        except ValueError as e:
            chunk_error = str(e)
        except Exception as e:
            chunk_error = f"自动切片失败: {str(e)}"
            print(f"[上传自动切片] 文档 {file.filename} 切片失败: {e}")

        return {
            "message": "上传标准文件成功",
            "document": new_document,
            "document_type": services.document_service._classify_document_type(
                text or "", file.filename or ""
            ) if text else "unknown",
            "auto_chunk": chunk_result,
            "chunk_error": chunk_error,
        }

    except SQLAlchemyError:
        file_path = Path(filepath)
        if file_path.exists():
            file_path.unlink()


# ═══════════════════════════════════════════════════════════════
# 追问建议生成（基于问题意图和检索结果）
# ═══════════════════════════════════════════════════════════════

def _generate_follow_ups(question: str, intent: str, references: list[dict]) -> list[str]:
    """
    根据用户问题和检索到的内容，智能生成 2-3 个追问方向。
    不调用 LLM，基于规则 + 检索结果推断。
    """
    follow_ups = []

    # 从检索结果中提取可追问的条款编号
    clause_numbers = []
    for ref in references:
        sn = ref.get("section_number", "")
        if sn and sn not in clause_numbers:
            clause_numbers.append(sn)

    # 基于意图类型生成追问
    if intent == "references":
        follow_ups.append("这些引用的标准中，哪些是最核心的？")
        follow_ups.append("引用的标准是否有版本要求？")
    elif intent == "clause_number":
        follow_ups.append("该条款是否有例外或豁免情况？")
        if clause_numbers:
            follow_ups.append("与这条相关的上级条款是什么？")
    elif intent == "scope":
        follow_ups.append("这份标准适用于哪些具体产品或场景？")
        if clause_numbers:
            follow_ups.append("适用范围是否有例外情况？")
    elif intent == "definition":
        follow_ups.append("这个术语在实际应用中如何理解？")
        if clause_numbers:
            follow_ups.append("相关术语之间有什么区别和联系？")
    elif intent == "requirement":
        follow_ups.append("这些要求的具体指标和参数是多少？")
        if len(clause_numbers) >= 2:
            follow_ups.append("不同条款之间是否有优先级或冲突？")
        follow_ups.append("是否有豁免或替代方案？")
    else:
        follow_ups.append("能否进一步说明具体条款内容？")
        if clause_numbers:
            follow_ups.append("相关条款对实际操作有什么指导意义？")
        follow_ups.append("这个标准是否引用了其他相关标准？")

    # 如果有关键条款号，追加精准追问
    if clause_numbers and len(follow_ups) < 3:
        for cn in clause_numbers[:2]:
            follow_ups.append("请详细解读第 {} 条款的具体内容".format(cn))

    # 限制 3 个
    return follow_ups[:3]


# ═══════════════════════════════════════════════════════════════
# 共享引用构建（/ask 和 /ask/stream 共用）
# ═══════════════════════════════════════════════════════════════

_CHUNK_TYPE_CN = {
    "cover": "封面", "preface": "前言/引言", "scope": "范围",
    "references": "规范性引用文件", "term": "术语定义", "clause": "正文条款",
    "table": "表格", "figure": "图示/公式", "appendix": "附录",
}


def _build_references(db, results, expanded_results):
    """从检索结果构建 references 列表（去重 + 评分 + 截断 + 来源标签）"""
    direct_ids = {item["chunk"].id for item in results}
    direct_scores = {item["chunk"].id: item["score"] for item in results}
    direct_match_types = {item["chunk"].id: item["match_type"] for item in results}

    references = []
    for chunk in expanded_results:
        doc = services.document_service.get_document_by_id(db, chunk.document_id)

        if chunk.id in direct_ids:
            mt = direct_match_types.get(chunk.id, "linked")
            references.append(_make_ref(chunk, doc,
                score=direct_scores.get(chunk.id, 0.0),
                match_type=mt,
                source_label="直接命中",
                priority=0 if mt in ("keyword", "hybrid") else 1))
        else:
            is_parent = any(item["chunk"].parent_chunk_id == chunk.id for item in results)
            is_child = any(chunk.parent_chunk_id and chunk.parent_chunk_id == item["chunk"].id for item in results)
            if is_parent:
                references.append(_make_ref(chunk, doc, score=0.0, match_type="linked",
                    source_label="关联上下文-父级", priority=2))
            elif is_child:
                references.append(_make_ref(chunk, doc, score=0.0, match_type="linked",
                    source_label="关联上下文-子级", priority=3))
            else:
                references.append(_make_ref(chunk, doc, score=0.0, match_type="linked",
                    source_label="关联上下文", priority=2))

    references.sort(key=lambda r: (r["priority"], -r["score"]))
    return references


def _make_ref(chunk, doc, score, match_type, source_label, priority):
    """构建单个 reference 条目"""
    raw = chunk.content or ""
    clean = services.document_service._strip_chunk_prefix(raw)
    limit = 800 if chunk.chunk_type == "table" else 1000
    if len(clean) > limit:
        clean = clean[:limit] + "\n[...内容过长，已截断...]"
    return {
        "document_id": chunk.document_id,
        "chunk_id": chunk.id,
        "filename": doc.filename if doc else None,
        "chunk_index": chunk.chunk_index,
        "chunk_type": chunk.chunk_type,
        "chunk_type_cn": _CHUNK_TYPE_CN.get(chunk.chunk_type, chunk.chunk_type or "未知"),
        "section_path": chunk.section_path,
        "page_number": chunk.page_number,
        "score": score,
        "content": clean,
        "content_length": len(raw),
        "match_type": match_type,
        "source_label": source_label,
        "priority": priority,
    }


@router.post("/ask")
@limiter.limit("30/minute")
def ask(request: Request, body: AskQuestion, db: Session = Depends(get_db),
        user: User = Depends(get_current_user)):
    # 确定检索范围：支持单文档、多文档对比、全库
    doc_ids = body.document_ids
    is_comparison = doc_ids is not None and len(doc_ids) >= 2
    auto_matched_doc = None

    # 自动文档匹配（仅在未指定文档时）
    if doc_ids is None:
        matched_id = services.document_service._match_question_to_documents(db, body.question)
        if matched_id is not None:
            doc_ids = [matched_id]
            auto_matched_doc = services.document_service.get_document_by_id(db, matched_id)

    results, confidence, confidence_detail = services.document_service.hybrid_search_chunks(
        db, body.question, body.limit, document_ids=doc_ids
    )

    # 自动匹配回退：如果限定文档无结果，回退到全库搜索
    auto_match_fallback = False
    if len(results) == 0 and doc_ids is not None and body.document_ids is None:
        auto_match_fallback = True
        doc_ids = None
        results, confidence, confidence_detail = services.document_service.hybrid_search_chunks(
            db, body.question, body.limit, document_ids=None
        )

    # 零结果查询扩展：用简化查询重试一次
    if len(results) == 0:
        expanded_q = services.document_service._expand_query_synonyms(body.question)
        if expanded_q != body.question:
            results, confidence, confidence_detail = services.document_service.hybrid_search_chunks(
                db, expanded_q, body.limit, document_ids=doc_ids
            )

    search_terms = services.document_service.extract_search_terms(body.question)
    question_intent = services.document_service.infer_question_intent(body.question)

    # 联动检索 + 引用构建
    expanded_results = services.document_service.expand_search_results(db, results, depth=1)
    references = _build_references(db, results, expanded_results)

    if len(references) == 0:
        return {
            "question": body.question,
            "answer": "没有找到相关参考资料，暂时无法回答。请确认：1) 已上传标准文件 2) 已为该文件生成切片。",
            "references": [],
            "retrieval_confidence": "none",
            "confidence_detail": confidence_detail,
            "auto_matched_document": {
                "document_id": auto_matched_doc.id,
                "filename": auto_matched_doc.filename,
            } if auto_matched_doc else None,
            "auto_match_fallback": auto_match_fallback,
            "prompt_preview": None,
        }

    # ═══ 对比模式：专用结构化 prompt ═══
    if is_comparison:
        # 按标准分组构建对比上下文
        comparison_context = services.document_service._format_comparison_context(references)
        comparison_answer = services.llm_service.generate_comparison_answer(
            body.question, comparison_context, references
        )
        return {
            "question": body.question,
            "question_intent": question_intent,
            "search_mode": "comparison",
            "search_terms": search_terms,
            "answer": comparison_answer,
            "references": [{
                "document_id": r["document_id"],
                "filename": r["filename"],
                "chunk_index": r["chunk_index"],
                "chunk_type": r["chunk_type"],
                "chunk_type_cn": r["chunk_type_cn"],
                "section_path": r["section_path"],
                "page_number": r["page_number"],
                "score": r["score"],
                "content_preview": r["content"][:300],
                "content_length": r["content_length"],
                "match_type": r["match_type"],
                "source_label": r["source_label"],
            } for r in references],
            "retrieval_confidence": confidence,
            "confidence_detail": confidence_detail,
            "is_comparison": True,
            "comparison_count": len(doc_ids),
            "auto_matched_document": {
                "document_id": auto_matched_doc.id,
                "filename": auto_matched_doc.filename,
            } if auto_matched_doc else None,
            "auto_match_fallback": auto_match_fallback,
        }

    # ═══ Grounded Evidence Extraction 三层防御 ═══

    # 层1：从 references 抽取与问题最相关的证据句子
    evidence_sentences = services.document_service.extract_evidence_sentences(
        body.question, references
    )

    if not evidence_sentences:
        # 有 references 但无足够相似的句子 → 诚实告知
        return {
            "question": body.question,
            "question_intent": question_intent,
            "search_terms": search_terms,
            "answer": (
                "当前资料中未找到与该问题直接相关的具体内容。\n\n"
                "建议：1) 尝试使用标准中出现的术语重新提问 2) 确认已上传相关标准文件 3) 尝试扩大检索范围。"
            ),
            "references": [{
                "document_id": r["document_id"],
                "filename": r["filename"],
                "chunk_index": r["chunk_index"],
                "chunk_type": r["chunk_type"],
                "chunk_type_cn": r["chunk_type_cn"],
                "section_path": r["section_path"],
                "page_number": r["page_number"],
                "score": r["score"],
                "content_preview": r["content"][:300],
                "content_length": r["content_length"],
                "match_type": r["match_type"],
                "source_label": r["source_label"],
            } for r in references],
            "retrieval_confidence": confidence,
            "confidence_detail": confidence_detail,
            "auto_matched_document": {
                "document_id": auto_matched_doc.id,
                "filename": auto_matched_doc.filename,
            } if auto_matched_doc else None,
            "auto_match_fallback": auto_match_fallback,
            "evidence_count": 0,
            "selected_count": 0,
        }

    # 层2：LLM 从候选句子中选择相关句子并排序（JSON 结构化输出）
    selection = services.llm_service.select_evidence_sentences(
        body.question, evidence_sentences
    )

    # 层3：组装最终答案 + 逐句验证来源可追溯
    assembled = services.document_service.assemble_verified_answer(
        selection, evidence_sentences
    )

    # ── 追问建议 ──
    follow_up_questions = _generate_follow_ups(body.question, question_intent, references)

    # ── 相关标准推荐（仅单文档模式下推荐）──
    recommendations = None
    if not is_comparison and doc_ids and len(doc_ids) == 1:
        recommendations = services.document_service.recommend_related_standards(
            db, doc_ids[0], body.question
        )

    return {
        "question": body.question,
        "question_intent": question_intent,
        "search_mode": "hybrid",
        "search_terms": search_terms,
        "answer": assembled["answer"],
        "references": [{
            "document_id": r["document_id"],
            "filename": r["filename"],
            "chunk_index": r["chunk_index"],
            "chunk_type": r["chunk_type"],
            "chunk_type_cn": r["chunk_type_cn"],
            "section_path": r["section_path"],
            "page_number": r["page_number"],
            "score": r["score"],
            "content_preview": r["content"][:300],
            "content_length": r["content_length"],
            "match_type": r["match_type"],
            "source_label": r["source_label"],
        } for r in references],
        "citations": assembled.get("citations", []),
        "not_found": assembled.get("not_found", []),
        "evidence_count": assembled.get("evidence_count", 0),
        "selected_count": assembled.get("selected_count", 0),
        "follow_up_questions": follow_up_questions,
        "recommendations": recommendations,
        "retrieval_confidence": confidence,
        "confidence_detail": confidence_detail,
        "is_comparison": is_comparison,
        "comparison_count": len(doc_ids) if doc_ids else 0,
        "auto_matched_document": {
            "document_id": auto_matched_doc.id,
            "filename": auto_matched_doc.filename,
        } if auto_matched_doc else None,
        "auto_match_fallback": auto_match_fallback,
    }


@router.post("/ask/stream")
@limiter.limit("30/minute")
async def ask_stream(request: Request, body: AskQuestion, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    """
    SSE 流式问答接口。
    先推送检索元信息（references + recommendations），再逐 token 推送 LLM 生成内容。
    """
    # ── 0. 自动文档匹配 ──
    doc_ids = body.document_ids
    auto_matched_doc = None
    if doc_ids is None:
        matched_id = services.document_service._match_question_to_documents(db, body.question)
        if matched_id is not None:
            doc_ids = [matched_id]
            auto_matched_doc = services.document_service.get_document_by_id(db, matched_id)

    # ── 1. 检索阶段（同步，和 /ask 逻辑一致）──
    results, confidence, confidence_detail = services.document_service.hybrid_search_chunks(
        db, body.question, body.limit, document_ids=doc_ids
    )

    # 自动匹配回退：如果限定文档无结果，回退到全库搜索
    auto_match_fallback = False
    if len(results) == 0 and doc_ids is not None and body.document_ids is None:
        auto_match_fallback = True
        doc_ids = None
        results, confidence, confidence_detail = services.document_service.hybrid_search_chunks(
            db, body.question, body.limit, document_ids=None
        )

    # 零结果查询扩展
    if len(results) == 0:
        expanded_q = services.document_service._expand_query_synonyms(body.question)
        if expanded_q != body.question:
            results, confidence, confidence_detail = services.document_service.hybrid_search_chunks(
                db, expanded_q, body.limit, document_ids=doc_ids
            )

    search_terms = services.document_service.extract_search_terms(body.question)
    question_intent = services.document_service.infer_question_intent(body.question)
    expanded_results = services.document_service.expand_search_results(db, results, depth=1)

    # 引用构建
    references = _build_references(db, results, expanded_results)

    if len(references) == 0:
        async def empty_stream():
            yield "data: {}\n\n".format(json.dumps({
                "type": "meta",
                "references": [],
                "recommendations": None,
                "follow_up_questions": [],
                "retrieval_confidence": "none",
                "auto_matched_document": {
                    "document_id": auto_matched_doc.id,
                    "filename": auto_matched_doc.filename,
                } if auto_matched_doc else None,
                "auto_match_fallback": auto_match_fallback,
            }, ensure_ascii=False))
            yield "data: {}\n\n".format(json.dumps({
                "type": "answer",
                "content": "没有找到相关参考资料，暂时无法回答。请确认：1) 已上传标准文件 2) 已为该文件生成切片。",
            }, ensure_ascii=False))
            yield "data: {}\n\n".format(json.dumps({"type": "done"}))

        return StreamingResponse(empty_stream(), media_type="text/event-stream")

    # ── 对比模式（流式版）──
    is_comparison = body.document_ids is not None and len(body.document_ids) >= 2
    if is_comparison:
        async def comparison_stream():
            # 先发 meta
            yield "data: {}\n\n".format(json.dumps({
                "type": "meta",
                "references": [{
                    "document_id": r["document_id"],
                    "filename": r["filename"],
                    "chunk_index": r["chunk_index"],
                    "chunk_type": r["chunk_type"],
                    "chunk_type_cn": r["chunk_type_cn"],
                    "section_path": r["section_path"],
                    "page_number": r["page_number"],
                    "score": r["score"],
                    "content_preview": r["content"][:300],
                    "content_length": r["content_length"],
                    "match_type": r["match_type"],
                    "source_label": r["source_label"],
                } for r in references],
                "recommendations": None,
                "follow_up_questions": [],
                "is_comparison": True,
                "comparison_count": len(body.document_ids),
                "auto_matched_document": {
                    "document_id": auto_matched_doc.id,
                    "filename": auto_matched_doc.filename,
                } if auto_matched_doc else None,
                "auto_match_fallback": auto_match_fallback,
            }, ensure_ascii=False))
            # 生成对比回答并逐token输出
            comparison_context = services.document_service._format_comparison_context(references)
            stream = services.llm_service.generate_comparison_answer_stream(
                body.question, comparison_context, references
            )
            try:
                for chunk in stream:
                    content = chunk.choices[0].delta.content or ""
                    if content:
                        yield "data: {}\n\n".format(json.dumps({"type": "token", "content": content}, ensure_ascii=False))
            except Exception as e:
                yield "data: {}\n\n".format(json.dumps({"type": "error", "message": "生成回答时出错，请重试"}, ensure_ascii=False))
            yield "data: {}\n\n".format(json.dumps({"type": "done"}))

        return StreamingResponse(comparison_stream(), media_type="text/event-stream")

    # ═══ Grounded Evidence Extraction 三层防御（流式版）═══

    # 层1：抽取证据句子
    evidence_sentences = services.document_service.extract_evidence_sentences(
        body.question, references
    )

    # ── 3. 推荐（仅单文档模式）──
    recommendations = None
    if doc_ids and len(doc_ids) == 1:
        recommendations = services.document_service.recommend_related_standards(
            db, doc_ids[0], body.question
        )

    # ── 4. 追问建议 ──
    follow_up_questions = _generate_follow_ups(body.question, question_intent, references)

    # ── 5. SSE 流式响应 ──
    async def event_stream():
        # 先推送元信息
        meta = {
            "type": "meta",
            "question_intent": question_intent,
            "search_terms": search_terms,
            "references": [{
                "document_id": r["document_id"],
                "filename": r["filename"],
                "chunk_index": r["chunk_index"],
                "chunk_type": r["chunk_type"],
                "chunk_type_cn": r["chunk_type_cn"],
                "section_path": r["section_path"],
                "page_number": r["page_number"],
                "score": r["score"],
                "content_preview": r["content"][:300],
                "content_length": r["content_length"],
                "match_type": r["match_type"],
                "source_label": r["source_label"],
            } for r in references],
            "recommendations": recommendations,
            "follow_up_questions": follow_up_questions,
            "retrieval_confidence": confidence,
            "confidence_detail": confidence_detail,
            "auto_matched_document": {
                "document_id": auto_matched_doc.id,
                "filename": auto_matched_doc.filename,
            } if auto_matched_doc else None,
            "auto_match_fallback": auto_match_fallback,
        }
        yield "data: {}\n\n".format(json.dumps(meta, ensure_ascii=False))

        # 无证据句子 → 直接返回提示
        if not evidence_sentences:
            yield "data: {}\n\n".format(json.dumps({
                "type": "answer",
                "content": (
                    "当前资料中未找到与该问题直接相关的具体内容。"
                    "建议尝试使用标准中出现的术语重新提问，或确认已上传相关标准文件。"
                ),
            }, ensure_ascii=False))
            yield "data: {}\n\n".format(json.dumps({"type": "done"}))
            return

        # 层2：LLM 选择句子（异步执行，不阻塞事件循环）
        yield "data: {}\n\n".format(json.dumps({
            "type": "status",
            "message": "正在从标准文件中筛选证据...（已找到 {} 个候选句子）".format(len(evidence_sentences)),
        }, ensure_ascii=False))

        import concurrent.futures
        loop = asyncio.get_event_loop()
        selection = await loop.run_in_executor(
            None, services.llm_service.select_evidence_sentences,
            body.question, evidence_sentences
        )

        # 层3：组装验证
        assembled = services.document_service.assemble_verified_answer(
            selection, evidence_sentences
        )

        # 推送 citations
        yield "data: {}\n\n".format(json.dumps({
            "type": "citations",
            "citations": assembled.get("citations", []),
            "not_found": assembled.get("not_found", []),
            "evidence_count": assembled.get("evidence_count", 0),
            "selected_count": assembled.get("selected_count", 0),
        }, ensure_ascii=False))

        # 真正流式推送：调用 DeepSeek stream API，token 逐个到达
        # 构建与 /ask 同质量的 prompt（复用非流式端点的 prompt 逻辑）
        ref_text = "\n\n".join([
            f"资料 {j+1} [{r['source_label']}] 类型={r['chunk_type_cn']} 路径={r['section_path'] or ''}\n{r['content']}"
            for j, r in enumerate(references[:5])
        ])
        intent_hint = ""
        if question_intent == "scope":
            intent_hint = "【提示：用户问适用范围，优先参考类型为 范围（scope）的资料】\n"
        elif question_intent == "definition":
            intent_hint = "【提示：用户问定义/术语，优先参考类型为 术语定义（term）的资料】\n"
        elif question_intent == "requirement":
            intent_hint = "【提示：用户问具体要求/指标，优先参考类型为 正文条款（clause）的资料】\n"

        stream_prompt = (
            f"你是企业标准文档问答助手。严格根据参考资料回答，不要编造。\n\n"
            f"【参考资料格式】类型标注了资料角色，章节路径用于条款引用，"
            f"直接命中=最相关资料，关联上下文=辅助背景。\n\n"
            f"{intent_hint}"
            f"用户问题：{body.question}\n\n"
            f"参考资料：\n{ref_text}"
        )
        stream = services.llm_service.generate_answer_stream(stream_prompt)
        answer_len = 0
        for chunk in stream:
            content = chunk.choices[0].delta.content or ""
            if content:
                answer_len += len(content)
                yield "data: {}\n\n".format(json.dumps({
                    "type": "token",
                    "content": content,
                }, ensure_ascii=False))

        yield "data: {}\n\n".format(json.dumps({
            "type": "done",
            "full_answer_length": answer_len,
        }))

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/documents", response_model=DocumentListResponse)  # 查询标准文件接口
async def get_documents(filename: str | None = Query(None),standard_type: str | None = Query(None),
                        industry: str | None = Query(None),tag: str | None = Query(None),page: int = Query(1, ge=1),
                        page_size: int = Query(5, le=100),db: Session = Depends(get_db)):
    total_count,page_documents =  (services.document_service.get_documents(db,
                                                                           filename,
                                                                           standard_type,
                                                                           industry,tag,page,page_size)
                                   )
    result = {"message": "查询标准文件成功",
              "documents": page_documents,
              "page": page,
              "page_size": page_size,
              "total_count": total_count,
              }
    return result


@router.get("/documents/citations/graph")
def get_citation_graph(db: Session = Depends(get_db)):
    """标准引用关系图谱"""
    graph = services.document_service.build_citation_graph(db)
    return {"message": "引用关系图谱", "graph": graph}


@router.get("/documents/stats", response_model=DocumentStatsResponse)  # 标准文件统计接口
async def get_document_stats(db: Session = Depends(get_db)):
    total,standard_types,industries,tag_stats = services.document_service.get_document_stats(db)
    return {"total": total,
            "standard_types": standard_types,
            "industries": industries,
            "tags": tag_stats,
            }


@router.get("/documents/search", response_model=DocumentSearchResponse)  # 标准化关键词搜索接口哦
async def search_documents(keyword: str = Query(..., min_length=1, max_length=20),
                           page: int = Query(1, ge=1),page_size: int = Query(5, le=100),
                           db: Session = Depends(get_db)):
    keyword, total_count, has_more, page_documents = services.document_service.search_documents(
        db,keyword, page, page_size
    )
    return {"message": "搜索标准文件成功",
            "keyword": keyword,
            "total_count": total_count,
            "page": page,
            "page_size": page_size,
            "has_more": has_more,
            "documents": page_documents,
            }

@router.get("/documents/{document_id}", response_model=DocumentOut)  # 根据标准文件的id去查询相对应的标准文件
async def get_document_by_id(document_id: int,db: Session = Depends(get_db)):
    document = services.document_service.get_document_by_id(db,document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


@router.patch("/documents/{document_id}", response_model=DocumentMessageOut)  # 根据标准文件的id去修改相对应的标准文件信息
async def update_document_by_id(document_id: int, patch_document: DocumentUpdate,
                                db: Session = Depends(get_db)):
    document = services.document_service.get_document_by_id(db,document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="您要修改的标准文件不存在")
    existing_document = services.document_service.find_document(db, patch_document.filename)
    if existing_document is not None and existing_document.id != document_id:
        raise HTTPException(status_code=409, detail="标准文件已存在")
    document = services.document_service.patch_document(
        db,patch_document.filename,patch_document.standard_type,patch_document.industry,patch_document.tags,document)
    if document is None:
        raise HTTPException(status_code=500, detail="修改标准文件失败")
    return {"message": "修改标准文件信息成功",
            "document": document, }


@router.get("/documents/{document_id}/clauses")
def get_clauses(document_id: int, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    """获取文档的条款列表（起草辅助用）"""
    clauses = services.document_service.extract_clauses(db, document_id)
    return {"clauses": clauses}


@router.post("/documents/{document_id}/draft-check")
def draft_check(document_id: int, req: AskQuestion, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    """起草辅助：检查草案条款是否与现行标准冲突"""
    # 获取该文档外的所有文档ID
    from models import Document
    all_docs = db.query(Document.id).filter(Document.id != document_id).all()
    other_ids = [d[0] for d in all_docs]
    if not other_ids:
        return {"answer": "系统中暂无其他标准可供对比"}

    # 用对比模式检索
    results, conf, detail = services.document_service.hybrid_search_chunks(
        db, req.question, req.limit, document_ids=other_ids
    )
    expanded = services.document_service.expand_search_results(db, results, depth=1)
    refs = _build_references(db, results, expanded)
    ctx = services.document_service._format_comparison_context(refs)

    # 获取草案条款详情
    clause_chunks = db.query(DocumentChunk).filter(
        DocumentChunk.document_id == document_id,
        DocumentChunk.section_path.isnot(None)
    ).all()
    clause_info = "\n".join([f"- {c.section_path}: { (c.content or '')[:200]}" for c in clause_chunks[:5]])

    prompt = (
        f"你是标准起草审查专家。用户正在起草一份标准，需要检查草案条款是否与现行标准冲突。\n\n"
        f"草案条款内容：\n{clause_info}\n\n"
        f"用户问题：{req.question}\n\n"
        f"现行标准参考资料：\n{ctx}\n\n"
        f"请给出：1) 是否存在冲突 2) 差异对比 3) 修改建议"
    )

    answer = services.llm_service.generate_answer(prompt)
    return {
        "answer": answer,
        "references": [{
            "document_id": r["document_id"], "filename": r["filename"],
            "section_path": r["section_path"], "source_label": r["source_label"],
        } for r in refs[:5]],
    }


@router.delete("/documents/{document_id}", response_model=MessageOut)  # 根据标准文件的id去删除相对应的文件
async def delete_document_by_id(document_id: int,
                                db: Session = Depends(get_db),
                                user: User = Depends(require_role("admin", "engineer"))):
    document = services.document_service.get_document_by_id(db,document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="您要删除的标准文件不存在")
    # engineer 只能删自己的文档
    if user.role == "engineer" and document.owner_id != user.id:
        raise HTTPException(status_code=403, detail="您只能删除自己上传的文档")
    # 先删磁盘文件
    file_path = Path(document.filepath) if document.filepath else None
    delete_success = services.document_service.delete_document(db, document)
    if delete_success is False:
        raise HTTPException(status_code=500, detail="删除标准文件失败")
    # 再清理磁盘上的文件
    if file_path and file_path.exists():
        file_path.unlink()
    return {"message": "删除指定标准文件成功"}


@router.get("/documents/{document_id}/download")
async def download_document(document_id: int,db: Session = Depends(get_db)):
    document = services.document_service.get_document_by_id(db,document_id)
    if document is None:
        raise HTTPException(status_code=404,detail="您要的标准文件不存在")
    path = document.filepath
    file_path = Path(path)
    if document.filename is None:
        raise HTTPException(status_code=404, detail="您要的标准文件不存在")
    if not file_path.exists():
        raise HTTPException(status_code=404,detail="该文件资源已被删除")
    return FileResponse(path=file_path,filename=document.filename,media_type='application/octet-stream',)

@router.post("/documents/{document_id}/chunks")
async def chunk_documents(document_id: int,db: Session = Depends(get_db),
                          user: User = Depends(require_role("admin", "engineer"))):
    document = services.document_service.get_document_by_id(db, document_id)
    if document is None:  # 判断这个文件id在不在数据库
        raise HTTPException(status_code=404, detail="您要的标准文件不存在")
    filepath = document.filepath

    if filepath is None: #判断有没有这个文件资源，可能有id但是被删除了，没有文件
        raise HTTPException(status_code=400, detail="该文件没有上传资源")

    try:
        text = services.document_service.parse_document(filepath)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="文档解析失败，请确认文件可读且未加密")

    if text is None or text.strip() == "":
        raise HTTPException(status_code=400, detail="文档解析结果为空，无法生成切片")
    # v2 结构感知切片：返回 list[dict]，每个 dict 含 content + 元信息
    chunks_v2 = services.document_service.smart_split_v2(text, filename=document.filename or "")
    delete_success = services.document_service.delete_chunks_by_id(db, document_id)  # 删旧 chunks

    if delete_success is False:
        raise HTTPException(status_code=404, detail="文件切片删除失败")
    save_chunk = services.document_service.save_document_chunk(db, chunks_v2, document_id)  # 存新 chunks

    if save_chunk is None:
        raise HTTPException(status_code=500, detail="文档切片保存失败")

    # 统计各类型数量
    type_counts = {}
    for c in chunks_v2:
        ct = c.get("chunk_type", "unknown") if isinstance(c, dict) else "unknown"
        type_counts[ct] = type_counts.get(ct, 0) + 1

    return {
        "message": "文档切片预览成功（v3 分类感知切片）",
        "document_id": document.id,
        "filename": document.filename,
        "document_type": services.document_service._classify_document_type(text, document.filename or ""),
        "total_chunks": len(chunks_v2),
        "chunk_types": type_counts,
    }


@router.post("/documents/{document_id}/analyze")
def analyze_document(
        document_id: int,
        db: Session = Depends(get_db),
        user: User = Depends(require_role("admin", "engineer"))
):
    document = services.document_service.get_document_by_id(db, document_id)

    if document is None:
        raise HTTPException(status_code=404, detail="标准文件不存在")

    analysis = services.analysis_service.generate_document_analysis(db,document)
    if analysis is None:
        raise HTTPException(
            status_code=400,
            detail="该文档暂无可分析内容，请先生成 chunks 或检查文档解析结果"
        )

    return {
        "message": "文档分析成功",
        "document_id": document.id,
        "filename": document.filename,
        "analysis": {
            "id": analysis.id,
            "standard_type_guess": analysis.standard_type_guess,
            "industry_guess": analysis.industry_guess,
            "summary": analysis.summary,
            "keywords": analysis.keywords,
            "scope": analysis.scope,
            "created_at": analysis.created_at,
        }
    }
