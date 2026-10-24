"""Eval del fixer sugli scenari: rottura -> agente -> check.

Il verdetto non è la risposta dell'agente ma check.sh: un modello può dire "ho riparato"
senza averlo fatto. Passi, comandi bloccati e token vengono dall'audit trail
dell'esecuzione: sono il riferimento con cui chi si esercita può confrontarsi.
Ogni scenario parte con una memory vuota, così una soluzione (o un'injection) letta
in uno scenario non finisce nel successivo.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from datapizza.core.clients.client import Client
from datapizza.memory import Memory

from .agent import AUDIT_DIR, STATE_DIR, AgentRunError, build_llm_client, run_agent
from .lab import DockerLab, Lab, Scenario, get_scenario, load_scenarios


EVAL_DIR = STATE_DIR / "eval"


@dataclass
class EvalRow:
    scenario: str
    category: str
    difficulty: str
    passed: bool
    check_output: str
    tool_calls: int
    blocked_by_guardrail: int
    llm_calls: int
    tokens: int
    duration_s: float
    audit_path: str
    error: str | None = None


async def evaluate_scenario(scenario: Scenario, client: Client, lab: Lab, audit_dir: Path = AUDIT_DIR) -> EvalRow:
    lab.start(scenario)
    started = time.monotonic()
    error = None
    try:
        _, audit_path = await run_agent(scenario.task, client, Memory(), audit_dir=audit_dir)
    except AgentRunError as exc:
        audit_path, error = exc.audit_path, str(exc)
    duration = time.monotonic() - started
    # Anche se l'agente è fallito a metà, conta lo stato in cui ha lasciato la sandbox.
    check = lab.check(scenario)
    summary = json.loads(audit_path.read_text(encoding="utf-8"))["summary"]
    return EvalRow(
        scenario=scenario.id,
        category=scenario.category,
        difficulty=scenario.difficulty,
        passed=check.passed,
        check_output=check.output,
        tool_calls=summary["tool_calls"],
        blocked_by_guardrail=summary["blocked_by_guardrail"],
        llm_calls=summary["llm_calls"],
        tokens=summary["tokens"]["prompt"] + summary["tokens"]["completion"],
        duration_s=round(duration, 1),
        audit_path=str(audit_path),
        error=error,
    )


def write_report(rows: list[EvalRow], model: str, eval_dir: Path = EVAL_DIR) -> Path:
    written_at = datetime.now(timezone.utc)
    report = {
        "written_at": written_at.isoformat(),
        "model": model,
        "passed": sum(r.passed for r in rows),
        "total": len(rows),
        "rows": [asdict(r) for r in rows],
    }
    eval_dir.mkdir(parents=True, exist_ok=True)
    path = eval_dir / f"{written_at:%Y%m%d-%H%M%S}.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def print_table(rows: list[EvalRow]) -> None:
    print(f"{'scenario':<18} {'esito':<5} {'tool':>4} {'blocc.':>6} {'token':>7} {'sec':>6}")
    for r in rows:
        print(f"{r.scenario:<18} {'PASS' if r.passed else 'FAIL':<5} {r.tool_calls:>4} "
              f"{r.blocked_by_guardrail:>6} {r.tokens:>7} {r.duration_s:>6}")
        if not r.passed:
            print(f"    {r.error or r.check_output}")
    print(f"\n{sum(r.passed for r in rows)}/{len(rows)} scenari riparati")


async def evaluate(scenarios: list[Scenario], client: Client, lab: Lab) -> list[EvalRow]:
    rows = []
    for scenario in scenarios:
        print(f"... {scenario.id}", file=sys.stderr)
        rows.append(await evaluate_scenario(scenario, client, lab))
    return rows


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(prog="breakfix-eval", description="Eval del fixer sugli scenari")
    parser.add_argument("scenarios", nargs="*", help="id degli scenari (default: tutti)")
    args = parser.parse_args()
    try:
        scenarios = [get_scenario(i) for i in args.scenarios] if args.scenarios else load_scenarios()
    except KeyError as exc:
        sys.exit(exc.args[0])

    client = build_llm_client()
    rows = asyncio.run(evaluate(scenarios, client, DockerLab()))
    print_table(rows)
    print(f"Report: {write_report(rows, client.model_name)}")
    sys.exit(0 if all(r.passed for r in rows) else 1)


if __name__ == "__main__":
    main()
