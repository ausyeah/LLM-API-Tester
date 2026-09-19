"""模型元数据：接口字段 > 内置对照表（精确再最长前缀）> 名字启发式。

只补空、不瞎覆盖；未知模型绝不编造思考档。
表数据可按需手改，只影响徽章展示。
"""

EXACT = {
    "glm-5.3-flash": {"mod": ["text", "image"], "ctx": 1000000,
                      "think": ["low", "high", "max"]},
    "glm-5.3": {"mod": ["text", "image"], "ctx": 204800,
                "think": ["low", "high", "max"]},
    "glm-5.3-audio": {"mod": ["text", "image", "audio"], "ctx": 131072,
                      "think": ["low", "high", "max"]},
    "glm-4.7": {"mod": ["text"], "ctx": 204800},
    "glm-4.7-flash": {"mod": ["text", "image"], "ctx": 204800},
}

# 最长前缀优先
PREFIX = [
    ("glm-5", {"mod": ["text", "image"], "ctx": 131072,
               "think": ["low", "high", "max"]}),
    ("glm-4v", {"mod": ["text", "image"], "ctx": 8192}),
    ("glm-4-plus", {"mod": ["text"], "ctx": 128000}),
    ("glm-", {"mod": ["text"], "ctx": 128000}),

    ("gpt-5", {"mod": ["text", "image"], "ctx": 400000,
               "think": ["minimal", "low", "medium", "high"]}),
    ("gpt-4o", {"mod": ["text", "image", "audio"], "ctx": 128000}),
    ("gpt-4", {"mod": ["text"], "ctx": 128000}),
    ("o4-mini", {"mod": ["text", "image"], "ctx": 200000,
                 "think": ["low", "medium", "high"]}),
    ("o3", {"mod": ["text", "image"], "ctx": 200000,
            "think": ["low", "medium", "high"]}),
    ("o1", {"mod": ["text", "image"], "ctx": 200000,
            "think": ["low", "medium", "high"]}),

    ("claude-opus-4", {"mod": ["text", "image"], "ctx": 200000,
                       "think": ["budget"]}),
    ("claude-sonnet-4", {"mod": ["text", "image"], "ctx": 200000,
                         "think": ["budget"]}),
    ("claude-3-7", {"mod": ["text", "image"], "ctx": 200000,
                    "think": ["budget"]}),
    ("claude-3-5", {"mod": ["text", "image"], "ctx": 200000}),
    ("claude-", {"mod": ["text", "image"], "ctx": 200000}),

    ("gemini-2.5", {"mod": ["text", "image", "audio", "video"], "ctx": 1048576,
                    "think": ["budget"]}),
    ("gemini-2", {"mod": ["text", "image", "audio", "video"], "ctx": 1000000}),
    ("gemini-", {"mod": ["text", "image"], "ctx": 32000}),

    ("qwen3-vl", {"mod": ["text", "image", "video"], "ctx": 131072,
                  "think": ["enable"]}),
    ("qwen-vl", {"mod": ["text", "image"], "ctx": 32768}),
    ("qwen3", {"mod": ["text"], "ctx": 131072, "think": ["enable"]}),
    ("qwq", {"mod": ["text"], "ctx": 131072, "think": ["always"]}),
    ("qwen", {"mod": ["text"], "ctx": 32768}),

    ("deepseek-r1", {"mod": ["text"], "ctx": 128000, "think": ["always"]}),
    ("deepseek-chat", {"mod": ["text"], "ctx": 128000}),
    ("deepseek-v", {"mod": ["text"], "ctx": 128000}),
    ("deepseek", {"mod": ["text"], "ctx": 64000}),
]

_HEURISTIC_VISION = ("vl", "vision")
_HEURISTIC_AUDIO = ("asr", "audio", "speech", "tts", "omni")
_HEURISTIC_VIDEO = ("video",)


def _catalog(model_id: str) -> dict | None:
    mid = (model_id or "").lower()
    if mid in EXACT:
        return EXACT[mid]
    best = None
    for prefix, meta in PREFIX:
        if mid.startswith(prefix) and (best is None or len(prefix) > len(best[0])):
            best = (prefix, meta)
    return best[1] if best else None


def _heuristics(model_id: str) -> set:
    m = (model_id or "").lower()
    mods = set()
    if any(k in m for k in _HEURISTIC_VISION):
        mods.add("image")
    if any(k in m for k in _HEURISTIC_AUDIO):
        mods.add("audio")
    if any(k in m for k in _HEURISTIC_VIDEO):
        mods.add("video")
    return mods


def resolve(model_id: str, api_meta: dict | None,
            meta_over: dict | None = None) -> dict:
    """返回 {mod: [...], ctx: int|None, think: [...]}。

    优先级：手动覆盖(meta_over) > 接口(api_meta) > 对照表 > 启发式。
    手动勾选过模态就完全以勾选为准，不再叠加启发式。
    """
    api = api_meta or {}
    over = meta_over or {}
    cat = _catalog(model_id) or {}

    if over.get("mod"):
        mods = set(over["mod"])
    else:
        mod = api.get("mod") or cat.get("mod") or ["text"]
        mods = set(mod) | _heuristics(model_id)
    if not mods:
        mods = {"text"}

    ctx = over.get("ctx") or api.get("ctx") or cat.get("ctx")
    think = api.get("think") or cat.get("think") or []
    return {"mod": sorted(mods), "ctx": ctx, "think": list(think)}


def format_ctx(ctx) -> str | None:
    if not isinstance(ctx, int) or ctx <= 0:
        return None
    if ctx >= 1_000_000:
        v = ctx / 1_000_000
        return f"{v:.0f}M" if abs(v - round(v)) < 0.05 else f"{v:.1f}M"
    return str(ctx)


def parse_ctx(text: str) -> int | None:
    """"1M" / "200K" / "204800" → token 数；空或非法返回 None（跟随）。"""
    import re
    t = (text or "").strip().upper().replace(" ", "").replace(",", "")
    if not t:
        return None
    m = re.match(r"^(\d+(?:\.\d+)?)([KM])?$", t)
    if not m:
        return None
    v = float(m.group(1))
    unit = m.group(2)
    if unit == "K":
        v *= 1_000
    elif unit == "M":
        v *= 1_000_000
    return int(v) if 0 < v <= 100_000_000 else None
