"""Il laboratorio: gli scenari e la CLI `breakfix-sandbox` per usarli.

Uno scenario è una cartella in scenarios/ con:
- scenario.toml: titolo, categoria, difficoltà, il sintomo da dare a chi ripara, le man page utili;
- break.sh: rompe la sandbox sana;
- check.sh: pass/fail, preceduto dalle funzioni di scenarios/_lib.sh;
- fix.sh: la riparazione di riferimento (deve passare il guardrail, come quella del fixer).

Gli script girano come root nel container ma arrivano dall'host su stdin: chi si esercita
nella sandbox non può modificarli, e il verdetto lo dà sempre check.sh.
"""

from __future__ import annotations

import argparse
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from . import sandbox
from .sandbox import DockerSandbox, ExecResult


SCENARIOS_DIR = Path(__file__).resolve().parents[2] / "scenarios"
CATEGORIES = ("permessi", "memoria")
DIFFICULTIES = ("facile", "media", "difficile")


@dataclass(frozen=True)
class Scenario:
    id: str
    title: str
    category: str
    difficulty: str
    task: str
    man: tuple[str, ...]
    path: Path

    def script(self, name: str) -> str:
        text = (self.path / f"{name}.sh").read_text(encoding="utf-8")
        if name == "check":
            text = (SCENARIOS_DIR / "_lib.sh").read_text(encoding="utf-8") + "\n" + text
        return text


def load_scenarios(directory: Path = SCENARIOS_DIR) -> list[Scenario]:
    scenarios = []
    for toml_path in sorted(directory.glob("*/scenario.toml")):
        meta = tomllib.loads(toml_path.read_text(encoding="utf-8"))
        scenario = Scenario(
            id=toml_path.parent.name,
            title=meta["title"],
            category=meta["category"],
            difficulty=meta["difficulty"],
            task=meta["task"],
            man=tuple(meta.get("man", ())),
            path=toml_path.parent,
        )
        if scenario.category not in CATEGORIES or scenario.difficulty not in DIFFICULTIES:
            raise ValueError(f"{scenario.id}: categoria o difficoltà non valida")
        scenarios.append(scenario)
    return scenarios


def get_scenario(scenario_id: str) -> Scenario:
    for scenario in load_scenarios():
        if scenario.id == scenario_id:
            return scenario
    raise KeyError(f"scenario sconosciuto: {scenario_id!r} (vedi `breakfix-sandbox list`)")


@dataclass(frozen=True)
class CheckResult:
    passed: bool
    output: str


class Lab(Protocol):
    def start(self, scenario: Scenario) -> None: ...
    def check(self, scenario: Scenario) -> CheckResult: ...


class DockerLab:
    """Applica gli scenari al container Docker della sandbox."""

    def __init__(self) -> None:
        self.box = DockerSandbox()

    def start(self, scenario: Scenario) -> None:
        """Container nuovo e sano, poi la rottura."""
        sandbox.reset(scenario.id)
        result = self.box.run_script(scenario.script("break"))
        if result.exit_code != 0:
            raise RuntimeError(f"{scenario.id}: la rottura è fallita: {_output(result)}")

    def check(self, scenario: Scenario) -> CheckResult:
        if not sandbox.is_running():
            return CheckResult(False, "FAIL: il container non è più in esecuzione")
        result = self.box.run_script(scenario.script("check"))
        return CheckResult(result.exit_code == 0, _output(result))

    def fix(self, scenario: Scenario) -> None:
        result = self.box.run_script(scenario.script("fix"))
        if result.exit_code != 0:
            raise RuntimeError(f"{scenario.id}: il fix di riferimento è fallito: {_output(result)}")

    def validate(self, scenario: Scenario) -> list[str]:
        """Lo scenario è valido se: sana passa, rotta fallisce, riparata passa, container vivo."""
        problems = []
        sandbox.reset(scenario.id)
        if not (healthy := self.check(scenario)).passed:
            problems.append(f"la sandbox sana non passa il check: {healthy.output}")
        try:
            self.start(scenario)
            if (broken := self.check(scenario)).passed:
                problems.append(f"dopo la rottura il check passa: {broken.output}")
            self.fix(scenario)
        except RuntimeError as exc:
            return [*problems, str(exc)]
        if not (fixed := self.check(scenario)).passed:
            problems.append(f"dopo il fix di riferimento il check fallisce: {fixed.output}")
        return problems


def _output(result: ExecResult) -> str:
    return (result.stdout + result.stderr).strip()


# --- CLI ---------------------------------------------------------------------------


def _cmd_list(_: argparse.Namespace) -> None:
    for s in load_scenarios():
        print(f"{s.id:<18} {s.category:<9} {s.difficulty:<10} {s.title}")


def _cmd_start(args: argparse.Namespace) -> None:
    scenario = get_scenario(args.scenario)
    DockerLab().start(scenario)
    print(f"Scenario {scenario.id}: {scenario.title}\n\n{scenario.task}\n")
    print("Entra con `breakfix-sandbox shell`, ripara, poi verifica con `breakfix-sandbox check`.")


def _cmd_check(_: argparse.Namespace) -> None:
    scenario_id = sandbox.active_scenario()
    if not scenario_id:
        sys.exit("Nessuno scenario attivo: avviane uno con `breakfix-sandbox start <id>`")
    result = DockerLab().check(get_scenario(scenario_id))
    print(result.output)
    sys.exit(0 if result.passed else 1)


def _cmd_validate(args: argparse.Namespace) -> None:
    lab = DockerLab()
    scenarios = [get_scenario(i) for i in args.scenarios] if args.scenarios else load_scenarios()
    invalid = 0
    for scenario in scenarios:
        problems = lab.validate(scenario)
        invalid += bool(problems)
        print(f"{'OK ' if not problems else 'KO '} {scenario.id}")
        for problem in problems:
            print(f"    - {problem}")
    sandbox.reset()
    sys.exit(1 if invalid else 0)


def _cmd_exec(args: argparse.Namespace) -> None:
    result = sandbox.get_sandbox().exec(args.command)
    print(result.model_dump_json(indent=2))
    sys.exit(0 if result.exit_code == 0 else 1)


def main() -> None:
    parser = argparse.ArgumentParser(prog="breakfix-sandbox", description="Gestisce la sandbox e gli scenari")
    commands = parser.add_subparsers(dest="action", required=True)
    commands.add_parser("up", help="builda l'immagine e avvia una sandbox sana").set_defaults(
        func=lambda _: sandbox.up())
    commands.add_parser("down", help="rimuove il container").set_defaults(func=lambda _: sandbox.down())
    commands.add_parser("shell", help="shell di root nella sandbox").set_defaults(func=lambda _: sandbox.shell())
    exec_parser = commands.add_parser("exec", help="esegue un comando (senza guardrail)")
    exec_parser.add_argument("command")
    exec_parser.set_defaults(func=_cmd_exec)
    commands.add_parser("list", help="elenca gli scenari").set_defaults(func=_cmd_list)
    start_parser = commands.add_parser("start", help="sandbox nuova + rottura dello scenario")
    start_parser.add_argument("scenario")
    start_parser.set_defaults(func=_cmd_start)
    commands.add_parser("check", help="pass/fail dello scenario attivo").set_defaults(func=_cmd_check)
    validate_parser = commands.add_parser("validate", help="verifica rottura, check e fix di riferimento")
    validate_parser.add_argument("scenarios", nargs="*", help="default: tutti")
    validate_parser.set_defaults(func=_cmd_validate)

    args = parser.parse_args()
    try:
        args.func(args)
    except KeyError as exc:
        sys.exit(exc.args[0])
    except RuntimeError as exc:
        sys.exit(str(exc))


if __name__ == "__main__":
    main()
