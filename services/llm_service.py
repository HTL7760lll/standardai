import json
import re
from config import settings
from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam

client = OpenAI(
    api_key=settings.DEEPSEEK_API_KEY,
    base_url=settings.DEEPSEEK_BASE_URL,
)

if not settings.DEEPSEEK_API_KEY or settings.DEEPSEEK_API_KEY.startswith("your_"):
    raise RuntimeError(
        "DEEPSEEK_API_KEY 未配置，请在 .env 文件中设置 DEEPSEEK_API_KEY=你的密钥"
    )


_SYSTEM_PROMPT = (
    "你是一个专业的企业标准文档问答助手。请严格根据参考资料回答问题，不要编造。"
)


def generate_answer(prompt: str) -> str:
    messages: list[ChatCompletionMessageParam] = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]

    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=messages,
        temperature=0.2,
    )

    if not response.choices:
        return "模型没有返回有效结果。"

    content = response.choices[0].message.content

    if content is None:
        return "模型没有返回有效内容。"

    return content


def generate_answer_stream(prompt: str, system_prompt: str | None = None):
    """
    SSE 流式生成回答。
    返回 openai Stream 对象，调用方迭代获取 token。
    """
    messages: list[ChatCompletionMessageParam] = [
        {"role": "system", "content": system_prompt or _SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]

    return client.chat.completions.create(
        model="deepseek-chat",
        messages=messages,
        temperature=0.2,
        stream=True,
    )


# ═══════════════════════════════════════════════════════════════
# Grounded Evidence Extraction — 层2：LLM 证据句子选择
# ═══════════════════════════════════════════════════════════════

def select_evidence_sentences(question: str, sentences: list[dict]) -> dict:
    """
    层2：让 LLM 从候选原文句子中选择与问题相关的句子，按逻辑排序。
    LLM 只能选择/排序，不得添加原文中不存在的事实、数字、条款号。

    返回: {"selected": [{"sentence_id": int, "action": "keep", "relevance": str}],
            "not_found": [str], "summary": str}
    """
    if not sentences:
        return {"selected": [], "not_found": ["候选句子为空"], "summary": ""}

    # 构建候选句子文本
    sent_lines = []
    for s in sentences:
        meta = ""
        if s.get("section_path"):
            meta += " | {}".format(s["section_path"])
        if s.get("page_number"):
            meta += " | 第{}页".format(s["page_number"])
        sent_lines.append("[{}]{}\n  {}".format(s["sentence_id"], meta, s["text"]))

    sent_text = "\n".join(sent_lines)

    prompt = (
        "你是标准文档证据筛选器。用户提问后，我给你一组来自标准文件的原文句子。\n\n"
        "【用户问题】\n{question}\n\n"
        "【候选原文句子】\n{sent_text}\n\n"
        "【你的任务——严格约束】\n"
        "1. 选出与问题直接相关的句子，按逻辑顺序排列\n"
        "2. 只能从候选句子中选择，禁止修改句子中的任何文字\n"
        "3. 绝对禁止：添加原文中没有的数字、条款号、百分比、条件、日期、人名、地名\n"
        "4. 如果候选句子不能完整回答用户问题，必须在 not_found 中诚实标注哪些信息缺失\n"
        "5. 如果候选句子能完整回答，not_found 为空数组 []\n"
        "6. summary 用一句话概括找到了什么（不要包含原文中没出现的具体数值）\n\n"
        "【输出格式——只输出JSON，不要其他任何文字】\n"
        "{{\n"
        '  "selected": [\n'
        '    {{"sentence_id": 3, "action": "keep", "relevance": "直接回答问题的核心条款"}},\n'
        '    {{"sentence_id": 7, "action": "keep", "relevance": "补充条件和例外"}}\n'
        '  ],\n'
        '  "not_found": ["需要但候选句中没有的信息"],\n'
        '  "summary": "一句话概述找到的信息（不添加原文没有的数值）"\n'
        "}}\n\n"
        "重要：sentence_id 必须是候选句子中方括号 [ ] 内的数字。只输出上述 JSON 对象，不要输出 Markdown 代码块标记。"
    ).format(question=question, sent_text=sent_text)

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "你是证据筛选器。只输出JSON，禁止编造任何事实、数字或条款编号。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
        )
        content = response.choices[0].message.content
    except Exception as e:
        print(f"[证据筛选] LLM 调用失败: {e}")
        return {"selected": [], "not_found": ["LLM调用失败: {}".format(str(e))], "summary": ""}

    if content is None:
        return {"selected": [], "not_found": ["LLM返回为空"], "summary": ""}

    # 解析 JSON
    content = content.strip()
    # 去掉可能的 markdown 代码块标记
    if content.startswith("```"):
        content = re.sub(r'^```(?:json)?\s*\n', '', content)
        content = re.sub(r'\n```\s*$', '', content)

    try:
        result = json.loads(content)
    except json.JSONDecodeError:
        # 尝试提取 JSON 对象
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if match:
            try:
                result = json.loads(match.group())
            except json.JSONDecodeError:
                return {"selected": [], "not_found": ["JSON解析失败"], "summary": content[:200]}
        else:
            return {"selected": [], "not_found": ["JSON解析失败"], "summary": content[:200]}

    # 验证结果结构
    if not isinstance(result, dict):
        return {"selected": [], "not_found": ["返回格式异常"], "summary": str(result)[:200]}

    result.setdefault("selected", [])
    result.setdefault("not_found", [])
    result.setdefault("summary", "")

    return result
