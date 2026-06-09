import json
from sqlalchemy.exc import SQLAlchemyError
from models import DocumentAnalysis, DocumentChunk
import services.llm_service


def get_analysis_context(db, document_id: int, limit: int = 10) -> str:
    chunks = db.query(DocumentChunk).filter(
        DocumentChunk.document_id == document_id
    ).order_by(DocumentChunk.chunk_index.asc()).all()

    if not chunks:
        return ""

    selected_chunks = []
    selected_ids = set()

    # 前 3 个 chunk 必选（通常包含封面、标题、标准编号）
    for chunk in chunks[:3]:
        selected_chunks.append(chunk)
        selected_ids.add(chunk.id)

    analysis_keywords = [
        "范围",
        "适用范围",
        "适用于",
        "本文件适用于",
        "本标准适用于",
        "前言",
        "术语",
        "定义",
        "术语和定义",
        "要求",
        "规定",
        "对象",
        "核心要求",
        "基本要求",
        "标准编号",
        "标准名称",
    ]

    for chunk in chunks:
        if chunk.id in selected_ids:
            continue

        content = chunk.content or ""

        if any(keyword in content for keyword in analysis_keywords):
            selected_chunks.append(chunk)
            selected_ids.add(chunk.id)

        if len(selected_chunks) >= limit:
            break

    context_text = "\n\n".join([
        f"切片 {chunk.chunk_index}：\n{(chunk.content or '')[:1500]}"
        for chunk in selected_chunks
    ])

    return context_text

def generate_document_analysis(db, document):
    context_text = get_analysis_context(db, document.id, limit=8)

    if context_text.strip() == "":
        return None

    prompt = f"""
    你是一位优秀的标准文档分析助手，你的工作任务是根据用户提交上来的指定标准文件内容生成结构化分析结果，要求清晰具体。

    请严格根据【文档内容】分析，不要编造。

    【重要提示】
    - 标准名称和标准编号通常出现在文档开头（前言、封面、标题页），请仔细从"切片 0"和"切片 1"中查找。
    - 标准编号常见格式如：GB/T 46350-2025、GB 47485-2026、NY/T 898、ISO 9001:2015 等。
    - 标准名称通常是紧跟在标准编号后面的一句话，如"信息技术 云计算 AI云服务通用要求"。
    - 如果文档开头确实没有找到标准名称和编号，才写"资料中未找到"。

    行业分类只能从以下候选中选择一个：
    信息技术、生物技术、制造业、食品、医疗器械、工程建设、能源、安全生产、环境保护、交通运输、农林牧渔、教育、金融、通用管理、公共事业与环保、未知

    标准类型只能从以下候选中选择一个：
    强制性国家标准、推荐性国家标准、行业标准、地方标准、团体标准、企业标准、其他标准

    请只返回 JSON格式，不要返回 Markdown，不要使用 ```json 包裹。

    请返回以下 JSON 字段：

    {{
      "standard_name": "标准名称，从文档开头/封面提取，如果确实找不到则写'资料中未找到'",
      "standard_number": "标准编号，如 GB/T xxxxx、NY/T xxxx 等格式，如果确实找不到则写'资料中未找到'",
      "standard_type_guess": "标准类型",
      "industry_guess": "所属行业",
      "industry_reason": "判断该行业的依据，说明引用了哪些关键词或内容",
      "summary": "用 150 字以内总结该标准主要内容",
      "scope": "该标准适用范围，如果资料中没有找到，请写资料中未明确说明",
      "applicable_objects": ["适用对象1", "适用对象2"],
      "core_requirements": ["核心要求1", "核心要求2", "核心要求3"],
      "keywords": ["关键词1", "关键词2", "关键词3"]
    }}

    文档名称：
    {document.filename}

    文档内容：
    {context_text}
    """

    answer = services.llm_service.generate_answer(prompt)

    try:
        data = json.loads(answer)
    except json.JSONDecodeError:
        data = {
            "standard_name": "资料中未找到",
            "standard_number": "资料中未找到",
            "standard_type_guess": "未知",
            "industry_guess": "未知",
            "industry_reason": "模型返回内容不是合法 JSON，无法解析行业判断依据",
            "summary": answer,
            "scope": "资料中未明确说明",
            "applicable_objects": [],
            "core_requirements": [],
            "keywords": [],
        }

    keywords = data.get("keywords", [])

    if isinstance(keywords, list):
        keywords_text = ",".join(keywords)  #将列表转化成字符串给python
    else:
        keywords_text = str(keywords)

    analysis = DocumentAnalysis(
        document_id=document.id,
        standard_type_guess= data.get("standard_type_guess"),
        industry_guess=data.get("industry_guess"),
        summary=data.get("summary"),
        keywords=keywords_text,
        scope=data.get("scope"),)

    try:
        db.add(analysis)
        db.commit()
        db.refresh(analysis)
        return analysis

    except SQLAlchemyError:
        db.rollback()
        return None