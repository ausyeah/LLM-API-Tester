"""协议适配层：不同 API 格式的 URL / 请求头 / 模型列表 / 流式首字解析。"""
import re

from .anthropic import AnthropicMessages
from .gemini import GeminiCompat
from .openai_compat import OpenAICompat
from .zhipu import ZhipuV4

_REGISTRY = {p.id: p for p in
             (OpenAICompat(), AnthropicMessages(), GeminiCompat(), ZhipuV4())}


def get_protocol(pid: str):
    try:
        return _REGISTRY[pid]
    except KeyError:
        raise ValueError(f"未知协议: {pid}") from None


def join_url(base: str, *parts: str) -> str:
    url = (base or "").strip().rstrip("/")
    for part in parts:
        url += "/" + part.strip("/")
    return url


def normalize_base(base: str, protocol: str) -> str:
    """OpenAI 格式按惯例补 /v1（用户没写的话）；其他协议用户填什么用什么。"""
    b = (base or "").strip().rstrip("/")
    if protocol == "openai" and b and not re.search(r"/v\d+$", b):
        b += "/v1"
    return b
