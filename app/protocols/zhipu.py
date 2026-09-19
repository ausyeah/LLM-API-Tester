"""Zhipu / Z.AI v4：OpenAI 风格路径，不补 /v1；GLM 系默认关思考。"""
from .openai_compat import OpenAICompat


class ZhipuV4(OpenAICompat):
    id = "zhipu"
    label = "Zhipu / Z.AI v4"

    def disable_thinking_params(self, model: str) -> dict:
        m = (model or "").lower()
        if m.startswith("glm") or "glm-" in m:
            return {"thinking": {"type": "disabled"}}
        return {}
