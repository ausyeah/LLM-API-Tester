"""测速结果的结构化记录、CSV 导出与本地持久化（history.json）。"""
import csv
import json
import logging
import os
from datetime import datetime, timezone

from .net import redact_detail


log = logging.getLogger(__name__)

MAX_HISTORY = 500
CSV_FIELDS = (
    "timestamp", "provider", "model", "model_id", "protocol", "max_tokens",
    "ok", "state", "error_code", "ttft_ms", "ttfb_ms", "status", "source",
    "note", "error", "detail", "reported_model", "model_match",
)


def _effective_max_tokens(settings: dict, result: dict | None = None) -> int:
    configured = (result or {}).get("max_tokens", settings.get("max_tokens", 8))
    try:
        return max(1, min(65536, int(configured)))
    except (TypeError, ValueError):
        return 8


def make_record(provider, model, result: dict | None, settings: dict) -> dict:
    """生成不包含供应商 Key 的平面记录。"""
    result = result or {}
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "provider": provider.name,
        "model": model.name,
        "model_id": model.id,
        "protocol": provider.protocol,
        "max_tokens": _effective_max_tokens(settings, result),
        "ok": bool(result.get("ok")),
        "state": result.get("state", ""),
        "error_code": result.get("error_code", ""),
        "ttft_ms": result.get("ttft_ms"),
        "ttfb_ms": result.get("ttfb_ms"),
        "status": result.get("status", 0),
        "source": result.get("source", ""),
        "note": result.get("note", ""),
        "error": result.get("error", ""),
        "detail": redact_detail(result.get("detail", "")),
        "reported_model": result.get("reported_model", ""),
        "model_match": result.get("model_match", ""),
    }


def limit_records(records: list[dict] | None, limit: int = MAX_HISTORY) -> list[dict]:
    clean = [dict(record) for record in (records or [])
             if isinstance(record, dict)]
    return clean[-max(1, int(limit)):]


def export_csv(records: list[dict], path: str) -> None:
    """导出 UTF-8 BOM CSV，方便 Windows Excel 直接打开。"""
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for record in records:
            writer.writerow({field: record.get(field, "") for field in CSV_FIELDS})
