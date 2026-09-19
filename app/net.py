"""HTTP 客户端工厂与错误归类。"""
import re
import ssl

import httpx

# 需求 3.7/5：本地无 Key 服务（Ollama、vLLM 等）是明确目标，
# 因此只限制协议必须是 http/https，不拦截内网/环回地址。
ALLOWED_SCHEMES = ("http", "https")
_SECRET_QUERY = re.compile(
    r"[?&](?:key|api[_-]?key|token|access[_-]?token)=[^&\s]+",
    re.IGNORECASE)


def validate_base_url(url: str) -> str | None:
    """合法返回 None，否则返回可读错误。"""
    u = (url or "").strip()
    if not u:
        return "Base URL 不能为空"
    if "://" not in u:
        return "Base URL 需要带 http:// 或 https://"
    scheme = u.split("://", 1)[0].lower()
    if scheme not in ALLOWED_SCHEMES:
        return f"仅支持 http/https，不支持 {scheme}://"
    host = u.split("://", 1)[1].split("/", 1)[0]
    if not host:
        return "Base URL 缺少主机名"
    return None


def redact_detail(value: object, secrets=()) -> str:
    """移除错误文本里的 Key 和常见鉴权查询参数。"""
    text = str(value or "")
    for secret in secrets:
        if secret and len(str(secret)) >= 4:
            text = text.replace(str(secret), "[REDACTED]")
    text = _SECRET_QUERY.sub("[REDACTED_QUERY]", text)
    return text[:300]


def make_client(settings: dict, timeout_s: float | None = None) -> httpx.AsyncClient:
    t = float(timeout_s if timeout_s is not None else settings.get("timeout_s", 10))
    return httpx.AsyncClient(
        verify=not settings.get("skip_tls", False),
        proxy=settings.get("proxy") or None,
        timeout=httpx.Timeout(t),
        follow_redirects=False,
        trust_env=False,   # 只用界面里配置的代理，不被系统环境变量干扰
    )


def classify_error(e: Exception, timeout_s: float) -> tuple[str, str]:
    """返回 (短错误, 详情)。"""
    if _is_tls_error(e):
        return "TLS 错误", redact_detail(e)
    if isinstance(e, httpx.TimeoutException):
        return f"超时({timeout_s:g}s)", redact_detail(e)
    if isinstance(e, httpx.ConnectError):
        return "连接失败(DNS/网络)", redact_detail(e)
    return type(e).__name__, redact_detail(e)


def _is_tls_error(e: Exception) -> bool:
    current = e
    seen = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, ssl.SSLError):
            return True
        name = type(current).__name__.upper()
        if "TLS" in name or "SSL" in name:
            return True
        current = current.__cause__ or current.__context__
    return False


def exception_code(e: Exception) -> str:
    """把底层异常映射为稳定的机器可读状态。"""
    if _is_tls_error(e):
        return "tls_error"
    if isinstance(e, httpx.TimeoutException):
        return "timeout"
    if isinstance(e, httpx.ConnectError):
        return "network_error"
    return "client_error"


def http_error_code(status: int) -> str:
    """把 HTTP 状态码映射为稳定的机器可读状态。"""
    if status in (401, 403):
        return "auth_error"
    if status == 408:
        return "timeout"
    if status == 429:
        return "rate_limited"
    if status == 404:
        return "not_found"
    if status >= 500:
        return "server_error"
    return "http_error"
