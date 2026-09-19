"""离线逻辑自检：协议解析 / 徽章目录 / DPAPI / 配置往返（不联网）。"""
import asyncio
import os
import ssl
import sys

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import config, crypto_dpapi, history
from app.catalog import format_ctx, parse_ctx, resolve
from app.models import ModelRow
from app.net import exception_code, http_error_code, validate_base_url
from app.protocols import get_protocol, normalize_base
from app.tester import (connectivity_state, failure_from_exception,
                        effective_max_tokens, format_ttft_result,
                        test_connectivity)

checks = []


class FakeResponse:
    def __init__(self, status, payload=None, text=""):
        self.status_code = status
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is ValueError:
            raise ValueError("bad json")
        return self._payload


class FakeClient:
    def __init__(self, response):
        self.response = response

    async def get(self, url, headers=None):
        return self.response


def check(name, cond, extra=""):
    checks.append(cond)
    print(("PASS" if cond else "FAIL"), name, extra)


def main():
    oa = get_protocol("openai")
    an = get_protocol("anthropic")
    ge = get_protocol("gemini")
    zp = get_protocol("zhipu")

    check("openai 补 /v1", normalize_base("https://example.com", "openai")
          == "https://example.com/v1")
    check("openai 已有 /v1 不重复",
          normalize_base("https://example.com/v1/", "openai")
          == "https://example.com/v1")
    check("anthropic 不补路径",
          normalize_base("https://api.z.ai/api/anthropic", "anthropic")
          == "https://api.z.ai/api/anthropic")
    check("zhipu 不补路径",
          normalize_base("https://api.z.ai/api/paas/v4", "zhipu")
          == "https://api.z.ai/api/paas/v4")

    check("anthropic models 两个候选路径",
          an.models_urls("https://api.z.ai/api/anthropic", "k")
          == ["https://api.z.ai/api/anthropic/v1/models",
              "https://api.z.ai/api/anthropic/models"])
    h = an.models_headers("K")
    check("anthropic 头", h.get("x-api-key") == "K" and "anthropic-version" in h)
    check("openai key 空 -> 无鉴权头", oa.models_headers("") == {})

    ms = oa.parse_models({"data": [
        {"id": "gpt-4o"},
        {"id": "x", "context_length": 8192},
        {"id": "y", "architecture": {"input_modalities": ["text", "image"]}},
    ]})
    check("openai parse_models + 元数据嗅探",
          [m["id"] for m in ms] == ["gpt-4o", "x", "y"]
          and ms[1]["api_meta"].get("ctx") == 8192
          and ms[2]["api_meta"].get("mod") == ["text", "image"])

    check("openai sse role-only 忽略",
          oa.parse_sse({"choices": [{"delta": {"role": "assistant",
                                               "content": ""}}]}) == (None, None))
    check("openai sse reasoning -> thinking",
          oa.parse_sse({"choices": [{"delta": {"reasoning_content": "想"}}]})[1]
          == "thinking")
    check("openai sse content",
          oa.parse_sse({"choices": [{"delta": {"content": "好"}}]}) == ("好", "content"))
    check("anthropic sse thinking",
          an.parse_sse({"type": "content_block_delta",
                        "delta": {"type": "thinking_delta", "thinking": "嗯"}})[1]
          == "thinking")
    check("anthropic sse text",
          an.parse_sse({"type": "content_block_delta",
                        "delta": {"type": "text_delta", "text": "好"}})
          == ("好", "content"))
    check("gemini sse",
          ge.parse_sse({"candidates": [{"content": {"parts": [{"text": "好"}]}}]})
          == ("好", "content"))
    check("gemini sse thought -> thinking",
          ge.parse_sse({"candidates": [{"content": {"parts": [
              {"text": "嗯", "thought": True}]}}]})[1] == "thinking")
    check("zhipu 关思考参数", zp.disable_thinking_params("glm-4.7")
          == {"thinking": {"type": "disabled"}})

    r1 = resolve("glm-5.3-flash", {})
    check("glm-5.3-flash 对照表",
          r1["mod"] == ["image", "text"] and r1["ctx"] == 1000000
          and "low" in r1["think"],
          str(r1))
    r2 = resolve("totally-unknown-model", {})
    check("未知模型只有 T 不编造", r2["mod"] == ["text"] and not r2["think"]
          and r2["ctx"] is None)
    r3 = resolve("some-vl-7b", {})
    check("启发式 vl -> 图", "image" in r3["mod"])
    check("接口元数据优先", resolve("unknown-model", {"ctx": 12345})["ctx"] == 12345)
    check("手动覆盖优先级",
          resolve("unknown-model", {"ctx": 12345}, {"ctx": 99})["ctx"] == 99
          and resolve("some-vl-7b", {}, {"mod": ["text"]})["mod"] == ["text"]
          and set(resolve("unknown", {}, {"mod": ["text", "pdf"]})["mod"])
          == {"text", "pdf"})
    check("parse_ctx",
          parse_ctx("1M") == 1_000_000 and parse_ctx("200K") == 200_000
          and parse_ctx("204800") == 204_800 and parse_ctx("") is None
          and parse_ctx("abc") is None)
    check("format_ctx", format_ctx(1000000) == "1M" and format_ctx(204800) == "204800")

    enc = crypto_dpapi.protect("sk-test-abc")
    check("DPAPI 往返", crypto_dpapi.unprotect(enc) == "sk-test-abc"
          and enc.startswith("dpapi:"))

    import tempfile
    tmp = tempfile.mkdtemp(prefix="llmapitester-")
    orig_dir, orig_path = config.CONFIG_DIR, config.CONFIG_PATH
    config.CONFIG_DIR = tmp
    config.CONFIG_PATH = os.path.join(tmp, "config.json")
    try:
        p = config.new_provider(name="往返测试", base_url="https://example.com/v1",
                                api_key="sk-xyz", protocol="openai")
        p.models = [ModelRow(id="m1", manual=True,
                             result={"ok": True, "state": "ok",
                                     "ttft_ms": 123, "ttfb_ms": 80})]
        p.history = [history.make_record(
            p, p.models[0], p.models[0].result, {"max_tokens": 3})]
        config.save([p], config.default_settings())
        ps, st = config.load()
        check("配置往返(含 Key 加密)",
              len(ps) == 1 and ps[0].api_key == "sk-xyz" and ps[0].name == "往返测试"
              and ps[0].models[0].manual
              and ps[0].models[0].result["ttft_ms"] == 123
              and len(ps[0].history) == 1
              and ps[0].history[0]["max_tokens"] == 3
              and st["timeout_s"] == 10)
        csv_path = os.path.join(tmp, "results.csv")
        history.export_csv(ps[0].history, csv_path)
        with open(csv_path, encoding="utf-8-sig") as f:
            csv_text = f.read()
        check("历史导出不含 Key",
              "sk-xyz" not in csv_text and "m1" in csv_text
              and "ttft_ms" in csv_text)

        check("最大输出 Token 设置",
              config.default_settings()["max_tokens"] == 8
              and effective_max_tokens({"max_tokens": 3}) == 3
              and effective_max_tokens({"max_tokens": 999999}) == 65536
              and get_protocol("openai").chat_body(
                  "m1", "p", effective_max_tokens({"max_tokens": 3}))
              ["max_tokens"] == 3)
    finally:
        config.CONFIG_DIR, config.CONFIG_PATH = orig_dir, orig_path

    examples = config.seed_examples()
    check("示例供应商不含 Key",
          len(examples) >= 2
          and all(not p.api_key for p in examples)
          and all(p.models for p in examples))

    check("URL 校验", validate_base_url("ftp://x") is not None
          and validate_base_url("") is not None
          and validate_base_url("https://api.x.com/v1") is None)

    check("HTTP 错误状态归类",
          http_error_code(401) == "auth_error"
          and http_error_code(429) == "rate_limited"
          and http_error_code(503) == "server_error"
          and http_error_code(404) == "not_found")
    check("网络异常状态归类",
          exception_code(httpx.TimeoutException("timeout")) == "timeout"
          and exception_code(httpx.ConnectError("connect")) == "network_error"
          and exception_code(ssl.SSLError("tls")) == "tls_error")
    check("空模型列表标为可达但无模型",
          connectivity_state([]) == "reachable_no_models"
          and connectivity_state([{"id": "m1"}]) == "ok")
    p = config.new_provider(name="状态测试", base_url="https://example.com/v1",
                            api_key="secret-key", protocol="openai")
    empty_conn = asyncio.run(test_connectivity(
        FakeClient(FakeResponse(200, {"data": []})), p,
        get_protocol("openai"), {"timeout_s": 1}))
    auth_conn = asyncio.run(test_connectivity(
        FakeClient(FakeResponse(401, {}, "invalid key")), p,
        get_protocol("openai"), {"timeout_s": 1}))
    check("连通结果返回结构化状态",
          empty_conn["state"] == "reachable_no_models"
          and empty_conn["reachable"]
          and not empty_conn["ok"]
          and auth_conn["state"] == "auth_error"
          and auth_conn["reachable"]
          and auth_conn["status"] == 401)
    failure = failure_from_exception(
        httpx.ConnectError("request https://x.test/?key=secret-key"), 10)
    check("异常详情脱敏",
          failure["state"] == "network_error"
          and "secret-key" not in failure["detail"]
          and "?key=" not in failure["detail"])

    from app.tester import model_match
    check("model_match 判定",
          model_match("glm-5.3-flash", "glm-5.3-flash") == "match"
          and model_match("glm-4.7", "glm-4.7:latest") == "suffix"
          and model_match("glm-4.7", "models/glm-4.7") == "suffix"
          and model_match("glm-4.7", "glm-5.3") == "mismatch"
          and model_match("glm-4.7", "") == "unknown")

    oa_m = oa.parse_model({"model": "routed-model", "choices": []})
    an_m = an.parse_model({"type": "message_start",
                           "message": {"model": "glm-5.3"}})
    ge_m = ge.parse_model({"modelVersion": "gemini-2.5-flash"})
    check("parse_model 各协议", oa_m == "routed-model" and an_m == "glm-5.3"
          and ge_m == "gemini-2.5-flash")

    f1 = format_ttft_result({"ok": True, "ttft_ms": 900, "source": "content",
                             "reported_model": "other-model",
                             "model_match": "mismatch"})
    check("不一致时标注上游模型",
          f1[0] == "TTFT 900ms · 上游:other-model" and f1[1] and f1[2])
    f2 = format_ttft_result({"ok": True, "ttft_ms": 900, "source": "content",
                             "reported_model": "glm-4.7:latest",
                             "model_match": "suffix"})
    check("后缀差异仅标注不警告",
          f2[0].endswith("· 上游:glm-4.7:latest") and f2[1] and not f2[2])
    f3 = format_ttft_result({"ok": True, "ttft_ms": 900, "source": "content",
                             "reported_model": "glm-4.7", "model_match": "match"})
    check("一致时不标注", f3[0] == "TTFT 900ms" and f3[1] and not f3[2])

    check("TTFT 结果格式化",
          format_ttft_result({"ok": True, "ttft_ms": 823, "source": "thinking",
                              "note": "疑似强制思考"})[0].startswith("TTFT 823ms")
          and format_ttft_result({"ok": False, "error": "no_content"})[0]
          == "失败: 无文本输出")

    n_ok = sum(checks)
    print(f"\n{n_ok}/{len(checks)} passed")
    sys.exit(0 if n_ok == len(checks) else 1)


if __name__ == "__main__":
    main()
