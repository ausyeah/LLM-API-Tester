"""配置持久化：%APPDATA%\\LLMApiTester\\config.json，Key 用 DPAPI 加密。

只读写固定常量路径 CONFIG_PATH；写入前就地规范化并校验路径限制在配置目录内。
若写入中途崩溃导致 JSON 截断，load() 会兜底回默认配置。
"""
import json
import logging
import os
import tempfile
import uuid

from . import crypto_dpapi, history
from .models import ModelRow, Provider

log = logging.getLogger(__name__)

CONFIG_DIR = os.path.normpath(os.path.abspath(
    os.environ.get("APPDATA") or os.path.expanduser("~"))) + os.sep + "LLMApiTester"
CONFIG_PATH = CONFIG_DIR + os.sep + "config.json"

PROTOCOL_LABELS = {
    "openai": "OpenAI Compatible",
    "anthropic": "Anthropic Messages",
    "gemini": "Gemini",
    "zhipu": "Zhipu / Z.AI v4",
}


def default_settings() -> dict:
    return {"timeout_s": 10, "concurrency": 3, "max_tokens": 8,
            "proxy": "", "skip_tls": False,
            "last_provider": None, "theme": "system",
            "provider_sort": "name_asc"}


def new_provider(protocol: str = "openai", **kw) -> Provider:
    return Provider(id=uuid.uuid4().hex, protocol=protocol, **kw)


def seed_examples() -> list[Provider]:
    """首次启动的空 Key 示例，不含任何真实凭证。"""
    openai = new_provider(
        name="示例 · OpenAI Compatible",
        base_url="https://api.openai.com/v1",
        api_key="",
        protocol="openai",
        note="示例：填入自己的 Key 后即可测连通",
    )
    openai.models = [
        ModelRow(id="gpt-4o", display_name="GPT-4o", manual=True),
        ModelRow(id="gpt-4o-mini", display_name="GPT-4o mini", manual=True),
    ]
    anthropic = new_provider(
        name="示例 · Anthropic",
        base_url="https://api.anthropic.com",
        api_key="",
        protocol="anthropic",
        note="示例：也可改成网关地址，如 https://api.z.ai/api/anthropic",
    )
    anthropic.models = [
        ModelRow(id="claude-sonnet-4-5", display_name="Claude Sonnet 4.5", manual=True),
        ModelRow(id="glm-5.3-flash", display_name="GLM-5.3-Flash", manual=True),
    ]
    return [openai, anthropic]


def load() -> tuple[list[Provider], dict]:
    settings = default_settings()
    if not os.path.exists(CONFIG_PATH):
        examples = seed_examples()
        try:
            save(examples, settings)
        except Exception as e:
            log.warning("写入示例配置失败: %s", e)
        return examples, settings
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as e:
        log.warning("配置读取失败，使用默认配置: %s", e)
        return [], settings

    settings.update({k: raw.get("settings", {}).get(k, v)
                     for k, v in settings.items()})
    providers = []
    for p in raw.get("providers", []):
        try:
            key = crypto_dpapi.unprotect(p.get("api_key_enc", ""))
            models = [ModelRow(id=m["id"],
                               display_name=m.get("display_name", ""),
                               manual=bool(m.get("manual")),
                               api_meta=m.get("api_meta") or {},
                               meta_over=m.get("meta_over") or {})
                      for m in p.get("models", [])]
            for row, raw_model in zip(models, p.get("models", [])):
                row.result = (raw_model.get("result")
                              if isinstance(raw_model.get("result"), dict)
                              else None)
            providers.append(Provider(
                id=p["id"], name=p.get("name", ""), base_url=p.get("base_url", ""),
                api_key=key, protocol=p.get("protocol", "openai"),
                note=p.get("note", ""), enabled=bool(p.get("enabled", True)),
                models=models,
                history=history.limit_records(p.get("history", []))))
        except Exception as e:
            log.warning("跳过损坏的供应商配置: %s", e)
    return providers, settings


def save(providers: list[Provider], settings: dict) -> None:
    os.makedirs(CONFIG_DIR, exist_ok=True)
    data = {
        "settings": {k: settings.get(k, v) for k, v in default_settings().items()},
        "providers": [{
            "id": p.id, "name": p.name, "base_url": p.base_url,
            "api_key_enc": crypto_dpapi.protect(p.api_key) if p.api_key else "",
            "protocol": p.protocol, "note": p.note, "enabled": p.enabled,
            "models": [{"id": m.id, "display_name": m.display_name,
                        "manual": m.manual, "api_meta": m.api_meta,
                        "meta_over": m.meta_over, "result": m.result}
                       for m in p.models],
            "history": history.limit_records(p.history),
        } for p in providers],
    }
    # 写入点就地防穿越：规范化路径，拒绝向上跳级，限制在配置目录内
    allowed = os.path.normpath(os.path.abspath(CONFIG_DIR))
    target = os.path.normpath(os.path.abspath(CONFIG_PATH))
    if os.path.relpath(target, allowed).startswith(".."):
        raise ValueError("配置路径越出允许目录")
    temp_path = None
    try:
        fd, temp_path = tempfile.mkstemp(
            dir=allowed, prefix="config-", suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, target)
        temp_path = None
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)
