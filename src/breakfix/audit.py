"""Audit trail delle esecuzioni dell'agente, costruito sugli span di ContextTracing.

ContextTracing tiene gli span in memoria e li cancella quando il trace si chiude: qui li
salviamo su file (uno per esecuzione) prima che succeda. Ogni file risponde alle domande
di un audit: chi ha chiesto cosa, quale modello ha deciso, quali comandi ha eseguito,
quali sono stati bloccati dal guardrail, quanto è costato.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from opentelemetry.sdk.trace import ReadableSpan

from .guardrail import BLOCKED_PREFIX


def _iso(ns: int | None) -> str | None:
    return datetime.fromtimestamp(ns / 1e9, tz=timezone.utc).isoformat() if ns else None


def _span_record(span: ReadableSpan) -> dict[str, Any]:
    attributes = dict(span.attributes or {})
    record: dict[str, Any] = {
        "name": span.name,
        "type": attributes.pop("type", None),
        "span_id": f"{span.context.span_id:016x}",
        "parent_span_id": f"{span.parent.span_id:016x}" if span.parent else None,
        "start": _iso(span.start_time),
        "duration_s": round((span.end_time - span.start_time) / 1e9, 3) if span.end_time else None,
        "status": span.status.status_code.name,
        "attributes": attributes,
    }
    if record["type"] == "tool":
        result = str(attributes.get("tool_result", ""))
        record["blocked_by_guardrail"] = BLOCKED_PREFIX in result
        try:
            record["is_error"] = bool(json.loads(result).get("isError"))
        except (ValueError, AttributeError):
            record["is_error"] = None
    return record


def _summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    tools = [r for r in records if r["type"] == "tool"]
    generations = [r for r in records if r["type"] == "generation"]
    tokens = {
        key: sum(int(r["attributes"].get(f"{key}_tokens_used", 0) or 0) for r in generations)
        for key in ("prompt", "completion", "cached", "thinking")
    }
    return {
        "llm_calls": len(generations),
        "tool_calls": len(tools),
        "blocked_by_guardrail": sum(r["blocked_by_guardrail"] for r in tools),
        "tool_errors": sum(bool(r["is_error"]) for r in tools),
        "tokens": tokens,
    }


def write_run(
    audit_dir: Path,
    *,
    trace_id: int,
    spans: Sequence[ReadableSpan],
    task: str,
    model: str,
    final_answer: str | None,
    error: str | None = None,
) -> Path:
    """Scrive l'audit di un'esecuzione e restituisce il percorso del file."""
    records = sorted((_span_record(s) for s in spans), key=lambda r: r["start"] or "")
    written_at = datetime.now(timezone.utc)
    trace_hex = f"{trace_id:032x}"
    run = {
        "trace_id": trace_hex,
        "written_at": written_at.isoformat(),
        "task": task,
        "model": model,
        "status": "ok" if final_answer is not None and error is None else "error",
        "error": error,
        "final_answer": final_answer,
        "summary": _summary(records),
        "spans": records,
    }
    audit_dir.mkdir(parents=True, exist_ok=True)
    path = audit_dir / f"{written_at:%Y%m%d-%H%M%S}-{trace_hex[:8]}.json"
    path.write_text(json.dumps(run, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return path
