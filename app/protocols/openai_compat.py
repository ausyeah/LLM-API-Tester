"""OpenAI Compatible：/models + /chat/completions（SSE）。"""


def sniff_api_meta(item: dict) -> dict:
    """从 /models 条目里嗅探上下文长度与输入模态（各家字段不一，尽力而为）。"""
    meta = {}
    for k in ("context_length", "max_model_len", "context_window",
              "max_context_tokens", "input_token_limit"):
        v = item.get(k)
        if isinstance(v, int) and v > 0:
            meta["ctx"] = v
            break
    arch = item.get("architecture") if isinstance(item.get("architecture"), dict) else {}
    mods = item.get("input_modalities") or arch.get("input_modalities")
    if isinstance(mods, list):
        good = [m for m in mods if m in ("text", "image", "audio", "video")]
        if good:
            meta["mod"] = good
    return meta


class OpenAICompat:
    id = "openai"
    label = "OpenAI Compatible"

    # ---- 模型列表 ----
    def models_urls(self, base: str, key: str) -> list[str]:
        return [_join(normalize(base), "models")]

    def models_headers(self, key: str) -> dict:
        return {"Authorization": f"Bearer {key}"} if key else {}

    def parse_models(self, data: dict) -> list[dict]:
        out = []
        for item in data.get("data") or []:
            if isinstance(item, str):
                out.append({"id": item, "display_name": "", "api_meta": {}})
            elif isinstance(item, dict) and item.get("id"):
                out.append({"id": str(item["id"]),
                            "display_name": item.get("display_name")
                            or item.get("name") or "",
                            "api_meta": sniff_api_meta(item)})
        return out

    # ---- 首字测速 ----
    def chat_urls(self, base: str, key: str, model: str) -> list[str]:
        return [_join(normalize(base), "chat/completions")]

    def chat_headers(self, key: str) -> dict:
        h = {"Content-Type": "application/json"}
        if key:
            h["Authorization"] = f"Bearer {key}"
        return h

    def chat_body(self, model: str, prompt: str, max_tokens: int) -> dict:
        return {"model": model, "stream": True, "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}]}

    def disable_thinking_params(self, model: str) -> dict:
        m = (model or "").lower()
        if "glm" in m:
            return {"thinking": {"type": "disabled"}}
        if "qwen" in m:
            return {"enable_thinking": False}
        # OpenAI 系 o/gpt-5 支持 reasoning_effort；不认识的服务端多半报 400，
        # 测试器会按 strip_param_names 去掉后重试
        return {"reasoning_effort": "minimal"}

    def strip_param_names(self) -> list[str]:
        return ["reasoning_effort", "enable_thinking", "thinking"]

    def parse_model(self, obj: dict) -> str | None:
        """上游实际使用的模型（每个 chunk 都带 model 字段）。"""
        m = obj.get("model")
        return m if isinstance(m, str) and m.strip() else None

    def parse_sse(self, obj: dict) -> tuple[str | None, str | None]:
        for ch in obj.get("choices") or []:
            delta = ch.get("delta") or ch.get("message") or {}
            rc = delta.get("reasoning_content") or delta.get("reasoning")
            if isinstance(rc, str) and rc.strip():
                return rc, "thinking"
            c = delta.get("content")
            if isinstance(c, str) and c.strip():
                return c, "content"
        return None, None


def normalize(base: str) -> str:
    from . import normalize_base
    return normalize_base(base, "openai")


def _join(base: str, *parts: str) -> str:
    from . import join_url
    return join_url(base, *parts)
