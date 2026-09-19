"""Anthropic Messages：/v1/models + /v1/messages（SSE）。

用户填什么用什么，不自动补 /v1 以外的路径；内部依次试 /v1/... 与不带版本两种。
"""


class AnthropicMessages:
    id = "anthropic"
    label = "Anthropic Messages"

    def _base(self, base: str) -> str:
        return (base or "").strip().rstrip("/")

    def models_urls(self, base: str, key: str) -> list[str]:
        b = self._base(base)
        return [f"{b}/v1/models", f"{b}/models"]

    def models_headers(self, key: str) -> dict:
        h = {"anthropic-version": "2023-06-01"}
        if key:
            h["x-api-key"] = key
        return h

    def parse_models(self, data: dict) -> list[dict]:
        out = []
        for item in data.get("data") or []:
            if isinstance(item, dict) and item.get("id"):
                out.append({"id": str(item["id"]),
                            "display_name": item.get("display_name", ""),
                            "api_meta": {}})
        return out

    def chat_urls(self, base: str, key: str, model: str) -> list[str]:
        b = self._base(base)
        return [f"{b}/v1/messages", f"{b}/messages"]

    def chat_headers(self, key: str) -> dict:
        h = {"anthropic-version": "2023-06-01", "Content-Type": "application/json"}
        if key:
            h["x-api-key"] = key
        return h

    def chat_body(self, model: str, prompt: str, max_tokens: int) -> dict:
        return {"model": model, "max_tokens": max_tokens, "stream": True,
                "messages": [{"role": "user", "content": prompt}]}

    def disable_thinking_params(self, model: str) -> dict:
        # Anthropic 协议默认不思考；若网关强制思考，会从 thinking delta 标注出来
        return {}

    def strip_param_names(self) -> list[str]:
        return []

    def parse_model(self, obj: dict) -> str | None:
        """上游实际使用的模型（message_start 事件携带）。"""
        if obj.get("type") == "message_start":
            m = (obj.get("message") or {}).get("model")
            return m if isinstance(m, str) and m.strip() else None
        return None

    def parse_sse(self, obj: dict) -> tuple[str | None, str | None]:
        if obj.get("type") == "content_block_delta":
            d = obj.get("delta") or {}
            if d.get("type") == "thinking_delta":
                t = d.get("thinking")
                if isinstance(t, str) and t.strip():
                    return t, "thinking"
            t = d.get("text")
            if isinstance(t, str) and t.strip():
                return t, "content"
        return None, None
