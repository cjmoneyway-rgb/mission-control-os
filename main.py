"""Command-line entry point for Mission Control OS."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from mission_control import MissionControlOS


SAMPLE_DIRECTIVE = (
    "Develop a Moneyway Journal executive article from a podcast conversation, "
    "preserve The CJ Moneyway philosophy, identify repurposing opportunities, "
    "recommend the next operational action, and conclude with the required CEO "
    "Executive Summary."
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Mission Control OS™ governance-first executive workflow"
    )
    parser.add_argument("directive", nargs="*", help="Executive directive to process")
    parser.add_argument(
        "--provider", choices=("mock", "openai"), default="mock",
        help="mock is deterministic and free; openai uses the Responses API",
    )
    parser.add_argument("--model", default=os.getenv("OPENAI_MODEL", "gpt-5.6"))
    parser.add_argument("--demo", action="store_true", help="Run the approved sample directive")
    parser.add_argument("--json", action="store_true", help="Print the complete record as JSON")
    parser.add_argument("--no-log", action="store_true", help="Disable the JSONL audit record")
    parser.add_argument("--audit-log", default="logs/executions.jsonl")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    directive = SAMPLE_DIRECTIVE if args.demo else " ".join(args.directive).strip()
    if not directive and not sys.stdin.isatty():
        directive = sys.stdin.read().strip()
    if not directive:
        print("Provide a directive, pipe one through stdin, or use --demo.", file=sys.stderr)
        return 2
    if args.provider == "openai" and not os.getenv("OPENAI_API_KEY"):
        print(
            "OPENAI_API_KEY is required for --provider openai. Use mock mode for a free offline run.",
            file=sys.stderr,
        )
        return 2

    try:
        system = MissionControlOS(
            provider=args.provider,
            model=args.model,
            audit_log=None if args.no_log else Path(args.audit_log),
        )
        record = system.run(directive)
    except (RuntimeError, ValueError) as exc:
        print(f"Mission Control error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(record.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(record.output)
        print(
            f"\n---\nExecution ID: {record.execution_id}\n"
            f"Provider: {record.provider}\n"
            f"Route: {record.department.name} ({record.route.confidence:.0%})\n"
            f"Governance: {record.governance.status}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
