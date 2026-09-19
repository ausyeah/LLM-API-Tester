"""测试引擎：连通性 + TTFT 首字（统一口径）。

TTFT 口径（需求 3.4）：
- 从发出流式请求开始，到第一条非空文本，毫秒，主指标；
- 空串不算首字，只有 role 的 chunk 忽略；
- 思考字段（reasoning_content / thinking / thought part）也算首字，结果标注来源；
- 流结束仍无文本 → 失败 no_content；
- TTFB 仅作附带，绝不冒充 TTFT。
拿到首字立即断开流，省 token 也省时间。
"""
import json
import time

import httpx

from .net import classify_error, exception_code, http_error_code, redact_detail

TTFT_PROMPT = "回复一个字：好"
TTFT_MAX_TOKENS = 8


def effective_max_tokens(settings: dict) -> int:
    try:
        return max(1, min(65536, int(settings.get("max_tokens", TTFT_MAX_TOKENS))))
    except (TypeError, ValueError):
        return TTFT_MAX_TOKENS


def _short_url(url: str) -> str:
    return url.split("?", 1)[0]


async def _iter_sse_json(resp: httpx.Response):
    """按 SSE 规范聚合 data: 行，产出解析后的 JSON 对象。"""
    buf: list[str] = []

    async def flush():
        if not buf:
            return None
        payload = "\n".join(buf)
        buf.clear()
        payload = payload.strip()
        if not payload or payload == "[DONE]":
            return None
        try:
            return json.loads(payload)
        except (ValueError, TypeError):
            return None

    async for raw in resp.aiter_lines():
        line = raw.rstrip("\r")
        if line == "":
            obj = await flush()
            if obj is not None:
                yield obj
        elif line.startswith("data:"):
            buf.append(line[5:].strip())
        # event:/id:/retry: 与注释行忽略
    obj = await flush()
    if obj is not None:
        yield obj


def _merge(dst: dict, src: dict) -> dict:
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            _merge(dst[k], v)
        else:
            dst[k] = v
    return dst


def connectivity_state(models: list[dict]) -> str:
    return "ok" if models else "reachable_no_models"


def failure_from_exception(exc: Exception, timeout_s: float, secret: str = "",
                           max_tokens: int | None = None) -> dict:
    error, detail = classify_error(exc, timeout_s)
    state = exception_code(exc)
    result = {"ok": False, "state": state, "error_code": state,
              "error": error, "detail": redact_detail(detail, (secret,)),
              "status": 0, "reachable": False, "latency_ms": None,
              "ttft_ms": None, "ttfb_ms": None, "source": "", "note": ""}
    if max_tokens is not None:
        result["max_tokens"] = effective_max_tokens({"max_tokens": max_tokens})
    return result


async def test_connectivity(client: httpx.AsyncClient, provider, proto,
                            settings: dict) -> dict:
    """打模型列表接口。ok 时带 models（parse_models 的输出）。"""
    timeout_s = float(settings.get("timeout_s", 10))
    headers = proto.models_headers(provider.api_key)
    best_error, best_detail = "失败", ""
    best_state, best_code = "http_error", "http_error"
    best_reachable = False
    best_latency = None
    best_status = 0
    attempts = []

    for url in proto.models_urls(provider.base_url, provider.api_key):
        t0 = time.perf_counter()
        try:
            resp = await client.get(url, headers=headers)
        except Exception as e:
            best_error, best_detail = classify_error(e, timeout_s)
            best_detail = redact_detail(best_detail, (provider.api_key,))
            best_state = best_code = exception_code(e)
            best_latency = round((time.perf_counter() - t0) * 1000)
            best_status = 0
            attempts.append({"url": _short_url(url), "status": 0,
                             "latency_ms": best_latency, "state": best_state})
            continue
        latency_ms = round((time.perf_counter() - t0) * 1000)
        status = resp.status_code
        best_latency = latency_ms
        best_status = status
        best_reachable = True
        if status >= 400:
            body = redact_detail(resp.text, (provider.api_key,))
            best_code = http_error_code(status)
            best_state = best_code
            best_error, best_detail = f"HTTP {status}", body
            attempts.append({"url": _short_url(url), "status": status,
                             "latency_ms": latency_ms, "state": best_state})
            if status == 404:
                continue  # 试下一个候选路径
            break
        try:
            data = resp.json()
        except ValueError:
            best_error, best_detail = "JSON 解析失败", redact_detail(
                resp.text, (provider.api_key,))
            best_state = best_code = "invalid_json"
            attempts.append({"url": _short_url(url), "status": status,
                             "latency_ms": latency_ms, "state": best_state})
            continue
        try:
            models = proto.parse_models(data)
        except Exception as e:
            best_error, best_detail = "模型列表解析失败", redact_detail(
                e, (provider.api_key,))
            best_state = best_code = "model_parse_error"
            attempts.append({"url": _short_url(url), "status": status,
                             "latency_ms": latency_ms, "state": best_state})
            continue
        state = connectivity_state(models)
        attempts.append({"url": _short_url(url), "status": status,
                         "latency_ms": latency_ms, "state": state})
        if state == "reachable_no_models":
            return {"ok": False, "state": state, "error_code": "no_models",
                    "reachable": True, "latency_ms": latency_ms,
                    "status": status, "error": "无模型列表",
                    "detail": "接口可达，但没有返回可用模型",
                    "models": [], "url": _short_url(url),
                    "attempts": attempts}
        return {"ok": True, "state": "ok", "error_code": "",
                "reachable": True, "latency_ms": latency_ms, "status": status,
                "error": "", "detail": f"{len(models)} 个模型",
                "models": models, "url": _short_url(url),
                "attempts": attempts}

    return {"ok": False, "state": best_state, "error_code": best_code,
            "reachable": best_reachable, "latency_ms": best_latency,
            "status": best_status,
            "error": best_error or "失败", "detail": best_detail,
            "models": [], "url": "", "attempts": attempts}


def model_match(requested: str, reported: str) -> str:
    """请求模型 vs 上游返回模型：match 一致 / suffix 仅版本后缀差异 / mismatch 不一致 / unknown 上游未报告。"""
    if not reported:
        return "unknown"
    if requested == reported:
        return "match"

    def norm(s: str) -> str:
        s = s.strip().lower()
        if s.startswith("models/"):
            s = s[len("models/"):]
        return s.split(":", 1)[0].split("@", 1)[0]

    if norm(requested) == norm(reported):
        return "suffix"
    return "mismatch"


async def _ttft_attempt(client, url, headers, body, settings,
                        proto, secret: str = "") -> dict:
    """发一次流式请求。返回 dict；400 时带 status 与 detail 供重试判断。"""
    timeout_s = float(settings.get("timeout_s", 10))
    t0 = time.perf_counter()
    try:
        async with client.stream("POST", url, headers=headers, json=body) as resp:
            if resp.status_code >= 400:
                raw = (await resp.aread())[:400]
                state = http_error_code(resp.status_code)
                return {"ok": False, "state": state, "error_code": state,
                        "error": f"HTTP {resp.status_code}",
                        "detail": redact_detail(raw.decode(errors="replace"),
                                                 (secret,)),
                        "status": resp.status_code, "reachable": True,
                        "reported_model": ""}
            ttfb_ms = round((time.perf_counter() - t0) * 1000)
            reported = ""
            async for obj in _iter_sse_json(resp):
                if not reported:
                    m = proto.parse_model(obj)
                    if m:
                        reported = m
                text, source = proto.parse_sse(obj)
                if text and text.strip():
                    ttft_ms = round((time.perf_counter() - t0) * 1000)
                    return {"ok": True, "state": "ok", "error_code": "",
                            "ttft_ms": ttft_ms, "ttfb_ms": ttfb_ms,
                            "source": source, "error": "", "detail": "",
                            "status": resp.status_code, "reachable": True,
                            "reported_model": reported}
            return {"ok": False, "state": "no_content", "error_code": "no_content",
                    "error": "no_content",
                    "detail": "流已结束但没有产出任何文本", "ttfb_ms": ttfb_ms,
                    "status": resp.status_code or 200, "reachable": True,
                    "reported_model": reported}
    except Exception as e:
        return failure_from_exception(e, timeout_s, secret)


async def run_ttft(client: httpx.AsyncClient, provider, proto, model_id: str,
                   settings: dict, cancelled=lambda: False) -> dict:
    headers = proto.chat_headers(provider.api_key)
    max_tokens = effective_max_tokens(settings)
    base_body = proto.chat_body(model_id, TTFT_PROMPT, max_tokens)
    disable = proto.disable_thinking_params(model_id)
    note = ""
    urls = proto.chat_urls(provider.base_url, provider.api_key, model_id)

    for i, url in enumerate(urls):
        if cancelled():
            return {"ok": False, "state": "cancelled", "error_code": "cancelled",
                    "error": "cancelled", "detail": "已取消",
                    "ttft_ms": None, "ttfb_ms": None, "source": "", "note": "",
                    "max_tokens": max_tokens}
        body = _merge(dict(base_body), disable) if disable else dict(base_body)
        r = await _ttft_attempt(client, url, headers, body, settings, proto,
                                provider.api_key)

        # 服务端不认识关思考参数时，去掉参数重试一次
        if (r.get("status") == 400 and disable and not note
                and any(name in (r.get("detail") or "")
                        for name in proto.strip_param_names())):
            note = "服务端不接受关思考参数，已去掉后重试"
            r = await _ttft_attempt(client, url, headers, dict(base_body),
                                    settings, proto, provider.api_key)

        if r.get("status") == 404 and i < len(urls) - 1:
            continue  # 试下一个候选路径

        if r.get("ok") and (r.get("source") or "content") == "thinking":
            tag = "疑似强制思考" if disable else "首字来自思考字段"
            note = (note + "；" if note else "") + tag
        r["note"] = note
        r["max_tokens"] = max_tokens
        r["requested_model"] = model_id
        r["model_match"] = model_match(model_id, r.get("reported_model") or "")
        return r

    return {"ok": False, "error": "失败", "detail": "无可用请求路径",
            "state": "not_found", "error_code": "not_found",
            "ttft_ms": None, "ttfb_ms": None, "source": "", "note": note,
            "max_tokens": max_tokens, "requested_model": model_id,
            "reported_model": "", "model_match": "unknown"}


def format_ttft_result(r: dict) -> tuple[str, bool, bool]:
    """(显示文本, 是否成功, 是否模型不一致警告)。"""
    if r.get("ok"):
        base = f"TTFT {r['ttft_ms']}ms"
        if r.get("source") == "thinking":
            base += " · 思考"
        if r.get("note"):
            base += f" · {r['note']}"
        rep = r.get("reported_model") or ""
        mt = r.get("model_match") or "unknown"
        warn = False
        if rep and mt in ("mismatch", "suffix"):
            base += f" · 上游:{rep}"
            warn = mt == "mismatch"
        return base, True, warn
    err = r.get("error") or "失败"
    if err == "cancelled":
        return "已取消", False, False
    if err == "no_content":
        return "失败: 无文本输出", False, False
    labels = {"auth_error": "鉴权失败", "rate_limited": "已限流",
              "server_error": "服务端错误", "timeout": "超时",
              "network_error": "网络错误", "tls_error": "TLS 错误"}
    label = labels.get(r.get("state"))
    if label:
        return f"失败: {label} · {err}", False, False
    return f"失败: {err}", False, False
