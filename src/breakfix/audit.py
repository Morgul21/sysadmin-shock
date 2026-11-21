"""Audit trail delle esecuzioni dell'agente, costruito sugli span di ContextTracing.

ContextTracing tiene gli span in memoria e li cancella quando il trace si chiude: qui li
salviamo su file (uno per esecuzione) prima che succeda. Ogni file risponde alle domande
di un audit: chi ha chiesto cosa, quale modello ha deciso, quali comandi ha eseguito,
quali sono stati bloccati dal guardrail e perché (regola, frammento, motivo), quanto è costato.
"""

from __future__ import annotations

import ast
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from opentelemetry.sdk.trace import ReadableSpan

from .guardrail import BLOCKED_PREFIX, check_command, parse_message


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
        _add_tool_fields(record)
    return record


def _add_tool_fields(record: dict[str, Any]) -> None:
    """Campi derivati di uno span di tool: bloccato dal guardrail (e perché), errore."""
    result = str(record["attributes"].get("tool_result", ""))
    record["blocked_by_guardrail"] = BLOCKED_PREFIX in result
    try:
        data = json.loads(result)
        record["is_error"] = bool(data.get("isError"))
        text = "\n".join(str(c.get("text", "")) for c in data.get("content") or [])
    except (ValueError, AttributeError):
        record["is_error"] = None
        text = result
    record["guardrail"] = _guardrail_record(text, _command(record)) if record["blocked_by_guardrail"] else None


def _guardrail_record(text: str, command: str) -> dict[str, str]:
    """Perché il guardrail ha bloccato il comando: regola, pezzo di comando colpevole, motivo."""
    blocked = parse_message(text)
    if blocked is None:  # messaggio in un formato che non riconosciamo: meglio il testo grezzo che niente
        return {"rule": "", "match": "", "reason": text.strip()}
    match = blocked.match
    if not match:
        # audit scritti prima che il messaggio riportasse il frammento: lo ricava il guardrail di
        # oggi, ma solo se arriva alla stessa regola (altrimenti meglio nessun frammento che uno sbagliato)
        again = check_command(command)
        match = again.match if again and again.rule == blocked.rule else ""
    return {"rule": blocked.rule, "match": match, "reason": blocked.reason}


def _command(record: dict[str, Any]) -> str:
    """Il comando di una chiamata a exec_in_sandbox (gli argomenti arrivano come repr di un dict)."""
    arguments = record["attributes"].get("tool_arguments", "")
    try:
        return str(ast.literal_eval(str(arguments)).get("command", arguments))
    except (ValueError, SyntaxError, AttributeError):
        return str(arguments)


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
        "guardrail_blocks": [
            {"span_id": r["span_id"], "command": _command(r), **r["guardrail"]}
            for r in tools if r["blocked_by_guardrail"]
        ],
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
    extra: dict[str, Any] | None = None,
) -> Path:
    """Scrive l'audit di un'esecuzione e restituisce il percorso del file.

    `extra`: campi propri di un agente (es. per il tutor la risposta bloccata dal guardrail di output).
    """
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
        **(extra or {}),
        "summary": _summary(records),
        "spans": records,
    }
    audit_dir.mkdir(parents=True, exist_ok=True)
    path = audit_dir / f"{written_at:%Y%m%d-%H%M%S}-{trace_hex[:8]}.json"
    path.write_text(json.dumps(run, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return path


def backfill(path: Path) -> bool:
    """Aggiunge a un audit già scritto i campi derivati di oggi (es. il perché dei blocchi del guardrail).

    Gli span restano com'erano: cambiano solo i campi derivati. Restituisce True se il file è cambiato.
    """
    original = path.read_text(encoding="utf-8")
    run = json.loads(original)
    records = run.get("spans") or []
    for record in records:
        if record.get("type") == "tool":
            record.pop("guardrail", None)  # ricalcolato, e messo in fondo come nei file nuovi
            _add_tool_fields(record)
    if "summary" in run:  # solo i campi del guardrail: token e conteggi restano quelli dell'esecuzione
        fresh = _summary(records)
        summary = {}
        for key, value in run["summary"].items():
            summary[key] = fresh[key] if key == "blocked_by_guardrail" else value
            if key == "blocked_by_guardrail":
                summary["guardrail_blocks"] = fresh["guardrail_blocks"]
        run["summary"] = summary
    updated = json.dumps(run, indent=2, ensure_ascii=False, default=str)
    if updated == original:
        return False
    path.write_text(updated, encoding="utf-8")
    return True


def main(argv: list[str] | None = None) -> None:
    import argparse

    from .agent import default_audit_dir

    parser = argparse.ArgumentParser(description="Aggiorna gli audit già scritti con i campi derivati di oggi.")
    parser.add_argument("paths", nargs="*", type=Path, help="file o directory (default: la directory degli audit)")
    args = parser.parse_args(argv)
    files: list[Path] = []
    for p in args.paths or [default_audit_dir()]:
        files.extend(sorted(p.glob("*.json")) if p.is_dir() else [p])
    changed = sum(backfill(f) for f in files)
    print(f"Audit aggiornati: {changed} su {len(files)}")


if __name__ == "__main__":
    main()
