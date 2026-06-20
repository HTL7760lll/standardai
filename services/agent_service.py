"""
Agent 工具调用服务 — 让 LLM 自主决策检索策略

支持：
- 多跳对比检索（分别搜索每份标准后再对比）
- 自修正查询改写（搜不到→换词重搜）
- 迭代起草审查（逐条检查 + 追溯引用链）
"""
import json
import asyncio
from config import settings
from models import Document, DocumentChunk
from logging_config import get_logger

logger = get_logger(__name__)

MAX_TURNS = settings.AGENT_MAX_TURNS


# ═══════════════════════════════════════════════════════════════
# Agent System Prompt
# ═══════════════════════════════════════════════════════════════

_AGENT_SYSTEM_PROMPT = (
    "你是企业标准文档智能问答助手。你可以使用工具搜索标准文档中的相关内容。\n\n"
    "【工作流程】\n"
    "1. 理解用户问题，确定需要查找什么信息\n"
    "2. 不知道系统中有哪些标准时，先用 list_available_standards 查看\n"
    "3. 使用 search_standards 搜索相关条款，可指定 focus 提高精度\n"
    "4. 如果搜索结果预览信息不够，用 get_clause_content 获取条款全文\n"
    "5. 需要完整上下文时，用 expand_chunk_context 展开父子级 chunk\n"
    "6. 对于对比类问题：分别搜索每份标准，获取各自条款后再进行对比\n"
    "7. 检查条款冲突时，用 check_conflict 逐条审查\n\n"
    "【重要约束】\n"
    "- 每个回答必须基于工具返回的搜索结果，绝对禁止编造条款编号、数值、指标\n"
    "- 如果搜索无结果，尝试更换搜索词重新搜索；多次无结果则诚实告知用户\n"
    "- 对比分析时，确保先分别查询各标准的条款后再进行对比\n"
    "- 回答中引用条款时，标注来源标准名称和章节路径\n"
    "- 不要编造不存在的工具名称\n"
    "- 最多进行 {} 轮工具调用，超过后请基于已收集信息给出回答".format(MAX_TURNS)
)

# ═══════════════════════════════════════════════════════════════
# Tool Definitions (OpenAI Function Calling 格式)
# ═══════════════════════════════════════════════════════════════

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "search_standards",
            "description": (
                "搜索标准文档中的相关内容。当你需要查找某个术语、条款、要求或概念时使用。"
                "可以指定在哪些标准文档中搜索，也可以指定搜索焦点来提升精度。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索查询词，使用标准中可能出现的术语",
                    },
                    "document_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "要搜索的文档ID列表，空数组或不传表示搜索全部文档",
                    },
                    "focus": {
                        "type": "string",
                        "enum": ["scope", "definition", "requirement", "references", "general"],
                        "description": "搜索焦点：scope=适用范围, definition=术语定义, requirement=具体要求/指标, references=引用文件, general=综合",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回结果数量，默认5",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_clause_content",
            "description": (
                "获取某个标准中特定条款的完整内容。"
                "当你需要查看某个具体条款号（如 5.2.1）的详细内容时使用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "document_id": {
                        "type": "integer",
                        "description": "标准文档ID",
                    },
                    "clause_number": {
                        "type": "string",
                        "description": "条款编号，如 '5.2.1' 或 '3.1'",
                    },
                },
                "required": ["document_id", "clause_number"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_available_standards",
            "description": (
                "列出系统中所有可用的标准文档，包括文档ID、文件名和标准类型。"
                "当你需要了解有哪些标准可供参考时使用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "expand_chunk_context",
            "description": (
                "展开某个检索结果chunk的上下文（父级/子级chunk），获取更完整的章节内容。"
                "当你觉得某个检索结果的信息不够完整，需要看到前后文时使用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "chunk_id": {
                        "type": "integer",
                        "description": "要展开的chunk ID",
                    },
                },
                "required": ["chunk_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_conflict",
            "description": (
                "检查某条款内容是否与其他标准存在冲突。适用于起草辅助场景，"
                "对比草案条款与现行标准，发现可能的矛盾或重复。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "clause_text": {
                        "type": "string",
                        "description": "要检查的条款文本",
                    },
                    "exclude_document_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "需要排除的文档ID（通常排除草案本身）",
                    },
                },
                "required": ["clause_text"],
            },
        },
    },
]


# ═══════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════

def _augment_query_with_focus(query: str, focus: str) -> str:
    """按 focus 类型增强查询词"""
    focus_map = {
        "scope": "适用范围",
        "definition": "术语定义",
        "requirement": "要求指标",
        "references": "规范性引用文件",
        "general": "",
    }
    tag = focus_map.get(focus, "")
    if tag and tag not in query:
        return f"{query} {tag}"
    return query


def _format_search_results_for_llm(refs: list[dict], confidence: str) -> str:
    """将检索结果格式化为 LLM 友好的紧凑 JSON（截断 600 字符/条）"""
    items = []
    for i, r in enumerate(refs[:5]):
        items.append({
            "rank": i + 1,
            "chunk_id": r.get("chunk_id"),
            "document_id": r.get("document_id"),
            "filename": r.get("filename"),
            "chunk_type": r.get("chunk_type_cn") or r.get("chunk_type"),
            "section_path": r.get("section_path"),
            "section_number": r.get("section_number"),
            "source_label": r.get("source_label"),
            "score": r.get("score"),
            "content": (r.get("content") or "")[:600],
        })
    return json.dumps({
        "total_results": len(refs),
        "confidence": confidence,
        "results": items,
    }, ensure_ascii=False)


def _dedup_references(refs: list[dict]) -> list[dict]:
    """按 chunk_id 去重，保留最高分"""
    seen = {}
    for r in refs:
        cid = r.get("chunk_id")
        if cid is None:
            continue
        if cid not in seen or (r.get("score") or 0) > (seen[cid].get("score") or 0):
            seen[cid] = r
    return sorted(seen.values(), key=lambda x: x.get("score") or 0, reverse=True)


def sse_event(event_type: str, data: dict) -> str:
    """构建一行 SSE data 字符串"""
    payload = {"type": event_type, **data}
    return "data: {}\n\n".format(json.dumps(payload, ensure_ascii=False))


# ═══════════════════════════════════════════════════════════════
# 工具执行分发器
# ═══════════════════════════════════════════════════════════════

def execute_tool_call(db, tool_name: str, arguments: dict) -> str:
    """
    执行单个工具调用，返回 JSON string 喂给 LLM。
    所有异常在此捕获，返回错误信息而非抛出。
    """
    try:
        if tool_name == "search_standards":
            return _exec_search_standards(db, arguments)
        elif tool_name == "get_clause_content":
            return _exec_get_clause_content(db, arguments)
        elif tool_name == "list_available_standards":
            return _exec_list_standards(db)
        elif tool_name == "expand_chunk_context":
            return _exec_expand_chunk_context(db, arguments)
        elif tool_name == "check_conflict":
            return _exec_check_conflict(db, arguments)
        else:
            return json.dumps({"error": "Unknown tool: {}".format(tool_name)})
    except Exception as e:
        logger.warning(f"工具执行失败 [{tool_name}]: {e}")
        return json.dumps({"error": "工具执行失败: {}".format(str(e))})


def _exec_search_standards(db, args: dict) -> str:
    from services import document_service
    query = args.get("query", "")
    doc_ids = args.get("document_ids") or None
    limit = args.get("limit", 5)
    focus = args.get("focus", "general")

    if focus != "general":
        query = _augment_query_with_focus(query, focus)

    results, confidence, _ = document_service.hybrid_search_chunks(
        db, query, limit, document_ids=doc_ids
    )
    expanded = document_service.expand_search_results(db, results, depth=1)
    refs = document_service.build_references(db, results, expanded)
    return _format_search_results_for_llm(refs, confidence)


def _exec_get_clause_content(db, args: dict) -> str:
    doc_id = args.get("document_id")
    clause_num = args.get("clause_number", "")

    chunks = db.query(DocumentChunk).filter(
        DocumentChunk.document_id == doc_id,
        DocumentChunk.section_number.like(f"{clause_num}%"),
    ).all()

    if not chunks:
        # 宽松匹配
        chunks = db.query(DocumentChunk).filter(
            DocumentChunk.document_id == doc_id,
            DocumentChunk.content.contains(clause_num),
        ).limit(3).all()

    if not chunks:
        return json.dumps({"found": False, "message": f"未找到条款 {clause_num} 的内容"}, ensure_ascii=False)

    doc = db.query(Document).filter(Document.id == doc_id).first()
    filename = doc.filename if doc else "未知"

    return json.dumps({
        "found": True,
        "document_id": doc_id,
        "filename": filename,
        "clauses": [
            {
                "chunk_id": c.id,
                "section_number": c.section_number,
                "section_path": c.section_path,
                "chunk_type": c.chunk_type,
                "content": (c.content or "")[:1200],
            }
            for c in chunks[:5]
        ],
    }, ensure_ascii=False)


def _exec_list_standards(db) -> str:
    docs = db.query(Document).order_by(Document.id.desc()).limit(30).all()
    return json.dumps({
        "total": len(docs),
        "capped": len(docs) >= 30,
        "standards": [
            {
                "id": d.id,
                "filename": d.filename,
            }
            for d in docs
        ],
    }, ensure_ascii=False)


def _exec_expand_chunk_context(db, args: dict) -> str:
    from services import document_service
    chunk_id = args.get("chunk_id")
    chunk = db.query(DocumentChunk).filter(DocumentChunk.id == chunk_id).first()
    if not chunk:
        return json.dumps({"found": False, "message": f"chunk {chunk_id} 不存在"}, ensure_ascii=False)

    results = [{"chunk": chunk}]
    expanded = document_service.expand_search_results(db, results, depth=1)
    refs = document_service.build_references(db, results, expanded)
    return _format_search_results_for_llm(refs, "medium")


def _exec_check_conflict(db, args: dict) -> str:
    from services import document_service
    clause_text = args.get("clause_text", "")
    exclude_ids = args.get("exclude_document_ids") or []

    if exclude_ids:
        all_ids = [d[0] for d in db.query(Document.id).filter(Document.id.notin_(exclude_ids)).all()]
    else:
        all_ids = [d[0] for d in db.query(Document.id).all()]

    if not all_ids:
        return json.dumps({"found": False, "message": "系统中没有其他标准可供对比"}, ensure_ascii=False)

    results, confidence, _ = document_service.hybrid_search_chunks(
        db, clause_text, 5, document_ids=all_ids
    )
    expanded = document_service.expand_search_results(db, results, depth=1)
    refs = document_service.build_references(db, results, expanded)
    return _format_search_results_for_llm(refs, confidence)


# ═══════════════════════════════════════════════════════════════
# Agent 循环 — 非流式
# ═══════════════════════════════════════════════════════════════

def run_agent(
    db,
    question: str,
    document_ids: list[int] | None = None,
    system_prompt_override: str | None = None,
) -> dict:
    """
    运行 Agent 循环。
    返回: {"answer": str, "tool_calls": list, "references": list, "turn_count": int}
    """
    import services.llm_service as llm_service

    # 如果用户预选了文档，将文档信息注入初始消息
    user_content = question
    system_content = system_prompt_override or _AGENT_SYSTEM_PROMPT
    if document_ids and len(document_ids) > 0:
        docs = db.query(Document).filter(Document.id.in_(document_ids)).all()
        logger.info(f"Agent 预选文档 {len(docs)} 份: {[d.filename for d in docs]}")
        if docs:
            doc_list = "\n".join([f"- [{d.id}] {d.filename}" for d in docs])
            doc_ids_str = ",".join([str(d.id) for d in docs])
            user_content = (
                f"【用户已选定以下 {len(docs)} 份标准文档，只需在这 {len(docs)} 份中搜索对比】\n"
                f"{doc_list}\n\n"
                f"用户问题：{question}\n\n"
                f"重要提示：用户已明确选定了这 {len(docs)} 份文档（ID: {doc_ids_str}），"
                f"请直接使用 search_standards 分别搜索这些文档，"
                f"不要调用 list_available_standards，不要询问用户要查哪份标准。"
            )
            # 修改 system prompt，强调不要再列举标准
            system_content += (
                f"\n\n【当前会话约束】用户已预选了 {len(docs)} 份文档（ID: {doc_ids_str}），"
                f"请跳过 list_available_standards，直接用 search_standards 搜索这些文档。"
            )

    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
    ]

    tool_call_log = []
    all_refs = []

    for turn in range(MAX_TURNS):
        try:
            response = llm_service.generate_agent_response(messages, TOOL_DEFINITIONS)
        except Exception as e:
            logger.error(f"Agent 第{turn+1}轮 LLM 调用失败: {e}")
            return {
                "answer": f"模型调用失败（第{turn+1}轮）: {e}",
                "tool_calls": tool_call_log,
                "references": _dedup_references(all_refs),
                "turn_count": turn + 1,
            }

        choice = response.choices[0]
        message = choice.message

        # ── 最终回答 ──
        if choice.finish_reason == "stop" or (
            choice.finish_reason != "tool_calls" and not message.tool_calls
        ):
            final_answer = message.content or ""
            # 如果经过多轮搜索但 answer 为空，强制总结
            if not final_answer.strip() and tool_call_log:
                messages.append({
                    "role": "user",
                    "content": "请根据以上所有搜索结果，用中文回答最初的问题：" + question,
                })
                final_answer = llm_service.generate_answer_from_messages(messages)
                if not final_answer.strip():
                    final_answer = (
                        f"系统已完成 {turn + 1} 轮检索，收集了 {len(_dedup_references(all_refs))} "
                        "条参考资料，但未能生成有效回答。建议尝试更精确的提问。"
                    )

            return {
                "answer": final_answer,
                "tool_calls": tool_call_log,
                "references": _dedup_references(all_refs),
                "turn_count": turn + 1,
            }

        # ── 工具调用 ──
        if message.tool_calls:
            # 追加 assistant 消息
            assistant_msg = {"role": "assistant", "content": message.content}
            tc_list = []
            for tc in message.tool_calls:
                tc_list.append({
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                })
            assistant_msg["tool_calls"] = tc_list
            messages.append(assistant_msg)

            # 逐个执行工具
            for tc in message.tool_calls:
                tool_name = tc.function.name
                try:
                    arguments = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    arguments = {}

                logger.info(f"Agent 执行工具 [{tool_name}] 参数: {json.dumps(arguments, ensure_ascii=False)[:200]}")
                result = execute_tool_call(db, tool_name, arguments)

                tool_call_log.append({
                    "tool": tool_name,
                    "arguments": arguments,
                    "result_preview": result[:500],
                })

                # 积累 search_standards 的结果
                if tool_name == "search_standards":
                    try:
                        parsed = json.loads(result)
                        for item in parsed.get("results", []):
                            all_refs.append(item)
                    except Exception:
                        pass

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })

            continue  # 下一轮

        # 其他 finish_reason（length 等）
        final_answer = message.content or "模型未能完成回答"
        return {
            "answer": final_answer,
            "tool_calls": tool_call_log,
            "references": _dedup_references(all_refs),
            "turn_count": turn + 1,
        }

    # 超过最大轮次 → 强制总结
    logger.warning(f"Agent 超过最大轮次 {MAX_TURNS}，强制总结")
    messages.append({
        "role": "user",
        "content": (
            f"已达到最大搜索轮次（{MAX_TURNS}轮）。"
            f"请根据以上所有搜索结果，用中文回答最初的问题：{question}\n"
            "如果某些信息未找到，请诚实说明。"
        ),
    })
    final_answer = llm_service.generate_answer_from_messages(messages)

    return {
        "answer": final_answer,
        "tool_calls": tool_call_log,
        "references": _dedup_references(all_refs),
        "turn_count": MAX_TURNS,
    }


# ═══════════════════════════════════════════════════════════════
# Agent 循环 — 流式 (SSE)
# ═══════════════════════════════════════════════════════════════

async def run_agent_stream(
    db,
    question: str,
    document_ids: list[int] | None = None,
):
    """
    异步生成器，产出 SSE data 字符串。
    事件类型:
        meta → (tool_call → tool_result) × N → token × M → done
    """
    import services.llm_service as llm_service

    # 如果用户预选了文档，将文档信息注入初始消息
    user_content = question
    system_content = _AGENT_SYSTEM_PROMPT
    if document_ids and len(document_ids) > 0:
        docs = db.query(Document).filter(Document.id.in_(document_ids)).all()
        if docs:
            doc_list = "\n".join([f"- [{d.id}] {d.filename}" for d in docs])
            doc_ids_str = ",".join([str(d.id) for d in docs])
            user_content = (
                f"【用户已选定以下 {len(docs)} 份标准文档，只需在这 {len(docs)} 份中搜索对比】\n"
                f"{doc_list}\n\n"
                f"用户问题：{question}\n\n"
                f"重要提示：用户已明确选定了这 {len(docs)} 份文档（ID: {doc_ids_str}），"
                f"请直接使用 search_standards 分别搜索这些文档，"
                f"不要调用 list_available_standards，不要询问用户要查哪份标准。"
            )
            system_content += (
                f"\n\n【当前会话约束】用户已预选了 {len(docs)} 份文档（ID: {doc_ids_str}），"
                f"请跳过 list_available_standards，直接用 search_standards 搜索这些文档。"
            )

    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
    ]

    for turn in range(MAX_TURNS):
        # 流式调用 LLM
        try:
            stream = llm_service.generate_agent_response_stream(messages, TOOL_DEFINITIONS)
        except Exception as e:
            yield sse_event("error", {"message": f"模型调用失败: {e}"})
            yield sse_event("done", {"turn_count": turn + 1})
            return

        accumulated_content = ""
        accumulated_tool_calls = {}  # index → {id, name, arguments}

        for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta is None:
                continue

            # 内容 token
            if delta.content:
                accumulated_content += delta.content
                yield sse_event("token", {"content": delta.content})

            # 工具调用 delta
            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in accumulated_tool_calls:
                        accumulated_tool_calls[idx] = {
                            "id": tc_delta.id or "",
                            "name": "",
                            "arguments": "",
                        }
                    entry = accumulated_tool_calls[idx]
                    if tc_delta.id:
                        entry["id"] = tc_delta.id
                    if tc_delta.function:
                        if tc_delta.function.name:
                            entry["name"] += tc_delta.function.name
                        if tc_delta.function.arguments:
                            entry["arguments"] += tc_delta.function.arguments

            # 检查 finish_reason
            finish = chunk.choices[0].finish_reason if chunk.choices else None

            if finish == "stop" and not accumulated_tool_calls:
                yield sse_event("done", {"turn_count": turn + 1})
                return

            if finish == "tool_calls" or (finish == "stop" and accumulated_tool_calls):
                break  # 跳出 chunk 迭代，处理工具调用

        # 通知前端每个工具调用
        for idx in sorted(accumulated_tool_calls.keys()):
            tc = accumulated_tool_calls[idx]
            yield sse_event("tool_call", {
                "name": tc["name"],
                "arguments": tc["arguments"][:300],
                "status": "calling",
            })

        # 追加 assistant 消息
        assistant_msg = {
            "role": "assistant",
            "content": accumulated_content or None,
            "tool_calls": [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": tc["arguments"],
                    },
                }
                for tc in accumulated_tool_calls.values()
            ],
        }
        messages.append(assistant_msg)

        # 执行工具
        for idx in sorted(accumulated_tool_calls.keys()):
            tc = accumulated_tool_calls[idx]
            yield sse_event("tool_status", {
                "name": tc["name"],
                "status": "executing",
            })

            try:
                arguments = json.loads(tc["arguments"])
            except json.JSONDecodeError:
                arguments = {}

            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, execute_tool_call, db, tc["name"], arguments
            )

            yield sse_event("tool_result", {
                "name": tc["name"],
                "result_preview": result[:300],
            })

            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": result,
            })

        # 如果不是 tool_calls finish，break
        if finish == "stop":
            yield sse_event("done", {"turn_count": turn + 1})
            return

    # 超过最大轮次 → 强制总结（不传 tools，禁止再调工具）
    yield sse_event("error", {"message": f"超过最大轮次 {MAX_TURNS}，基于已收集信息回答"})
    final_prompt = (
        f"已达到最大搜索轮次（{MAX_TURNS}轮）。"
        f"请根据以上所有搜索结果，用中文回答最初的问题：{question}\n"
        "如果某些信息未找到，请诚实说明。"
    )
    messages.append({"role": "user", "content": final_prompt})
    # 兜底阶段不再允许工具调用
    try:
        final_stream = llm_service.generate_answer_stream(
            prompt=final_prompt,
            system_prompt=_AGENT_SYSTEM_PROMPT,
        )
        for chunk in final_stream:
            content = chunk.choices[0].delta.content or ""
            if content:
                yield sse_event("token", {"content": content})
    except Exception as e:
        yield sse_event("error", {"message": f"最终回答生成失败: {e}"})

    yield sse_event("done", {"turn_count": MAX_TURNS})
