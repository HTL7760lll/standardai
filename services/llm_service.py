import os
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"

load_dotenv(ENV_PATH)

api_key = os.getenv("DEEPSEEK_API_KEY")

if not api_key:
    raise RuntimeError("DEEPSEEK_API_KEY 未读取到，请检查 .env 文件路径和变量名")

client = OpenAI(
    api_key=api_key,
    base_url="https://api.deepseek.com"
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
