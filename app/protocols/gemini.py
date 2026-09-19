"""Gemini：/models + :streamGenerateContent?alt=sse。Key 走 query 参数。"""

DEFAULT_BASE = "https://generativelanguage.googleapis.com/v1beta"


class GeminiCompat:
    id = "gemini"
    label = "Gemini"

    def _base(self, base: str) -> str:
        return (base or DEFAULT_BASE).strip().rstrip("/")

    def models_urls(self, base: str, key: str) -> list[str]:
        url = f"{self._base(base)}/models"
        if key:
            url += f"?key={key}"
        return [url]

    def models_headers(self, key: str) -> dict:
        return {}

    def parse_models(self, data: dict) -> list[dict]:
        out = []
        for item in data.get("models") or []:
            name = item.get("name", "")
            mid = name.split("/")[-1] if name else ""
            if not mid:
                continue
            meta = {}
            if isinstance(item.get("inputTokenLimit"), int) and item["inputTokenLimit"] > 0:
                meta["ctx"] = item["inputTokenLimit"]
            out.append({"id": mid, "display_name": item.get("displayName", ""),
                        "api_meta": meta})
        return out

    def chat_urls(self, base: str, key: str, model: str) -> list[str]:
        url = f"{self._base(base)}/models/{model}:streamGenerateContent"
        params = ["alt=sse"]
        if key:
            params.append(f"key={key}")
        return [f"{url}?{'&'.join(params)}"]

    def chat_headers(self, key: str) -> dict:
        return {"Content-Type": "application/json"}

    def chat_body(self, model: str, prompt: str, max_tokens: int) -> dict:
        return {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"maxOutputTokens": max_tokens}}

    def disable_thinking_params(self, model: str) -> dict:
        m = (model or "").lower()
        if "gemini-2.5" in m or "gemini-3" in m:
            return {"generationConfig": {"thinkingConfig": {"thinkingBudget": 0}}}
        return {}

    def strip_param_names(self) -> list[str]:
        return ["thinkingBudget", "thinkingConfig"]

    def parse_model(self, obj: dict) -> str | None:
        """上游实际使用的模型（chunk 里的 modelVersion）。"""
        m = obj.get("modelVersion")
        return m if isinstance(m, str) and m.strip() else None

    def parse_sse(self, obj: dict) -> tuple[str | None, str | None]:
        for cand in obj.get("candidates") or []:
            for part in (cand.get("content") or {}).get("parts") or []:
                t = part.get("text")
                if isinstance(t, str) and t.strip():
                    return t, ("thinking" if part.get("thought") else "content")
        return None, None
