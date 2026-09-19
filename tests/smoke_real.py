"""真实端点联调：连通 → 拉模型 → 首字测速。

Key 一律从环境变量读取，不写进源码：
  LLMTEST_OPENAI_KEY      （必需，OpenAI Compatible 供应商）
  LLMTEST_OPENAI_URL      （可选，默认 https://example.com/v1）
  LLMTEST_ANTHROPIC_KEY   （必需，Anthropic 供应商）
  LLMTEST_ANTHROPIC_URL   （可选，默认 https://api.z.ai/api/anthropic）

用法: python tests/smoke_real.py [--full]
默认每家只测 1 个模型；--full 时对全部模型测首字。
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.net import make_client
from app.protocols import get_protocol
from app.tester import run_ttft, test_connectivity


def load_providers():
    out = []
    spec = [
        ("openai", "LLMTEST_OPENAI_KEY", "LLMTEST_OPENAI_URL",
         "https://example.com/v1", "OpenAI Compatible"),
        ("anthropic", "LLMTEST_ANTHROPIC_KEY", "LLMTEST_ANTHROPIC_URL",
         "https://api.z.ai/api/anthropic", "Anthropic"),
    ]
    for proto, key_env, url_env, default_url, label in spec:
        key = os.environ.get(key_env, "").strip()
        if not key:
            print(f"[跳过] {label}: 未设置 {key_env}")
            continue
        out.append({
            "name": f"{label}({proto})",
            "base_url": os.environ.get(url_env, "").strip() or default_url,
            "api_key": key,
            "protocol": proto,
        })
    return out


class FakeProvider:
    def __init__(self, d):
        self.id = d["name"]
        self.name = d["name"]
        self.base_url = d["base_url"]
        self.api_key = d["api_key"]
        self.protocol = d["protocol"]


async def probe(p_dict, full=False):
    p = FakeProvider(p_dict)
    proto = get_protocol(p.protocol)
    out = {"name": p.name}
    async with make_client({"timeout_s": 10, "proxy": "", "skip_tls": False}) as client:
        conn = await test_connectivity(client, p, proto, {"timeout_s": 10})
        out["connectivity"] = ({k: conn[k] for k in
                                ("ok", "status", "latency_ms", "error", "detail")}
                               if conn["ok"] else conn)
        if not conn["ok"]:
            print(json.dumps(out, ensure_ascii=False, indent=2))
            return out
        models = conn["models"]
        out["models_count"] = len(models)
        out["models_sample"] = [m["id"] for m in models][:12]

        ids = [m["id"] for m in models]
        targets = ids if full else ids[:1]
        out["ttft"] = {}
        for mid in targets:
            r = await run_ttft(client, p, proto, mid, {"timeout_s": 10})
            out["ttft"][mid] = r
            print(json.dumps(out["ttft"][mid], ensure_ascii=False))
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return out


async def main():
    full = "--full" in sys.argv
    providers = load_providers()
    if not providers:
        sys.exit("没有任何可测供应商：请设置 LLMTEST_OPENAI_KEY / LLMTEST_ANTHROPIC_KEY")
    for p in providers:
        await probe(p, full)


if __name__ == "__main__":
    asyncio.run(main())
