"""Small command line interface; never submits exchange orders."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["download", "run", "report", "all"])
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--config", type=Path, default=None)
    args = parser.parse_args()
    root = args.root.resolve()
    from .runner import load_config
    config = load_config(args.config or root / "configs" / "research.toml")
    if args.command in {"download", "all"}:
        from .data import download_and_prepare
        audit = download_and_prepare(root, config)
        print(json.dumps(audit, indent=2, default=str))
    if args.command in {"run", "all"}:
        from .runner import run_research
        print(json.dumps(run_research(root, config), indent=2, default=str))
    if args.command in {"report", "all"}:
        from .reporting import create_report
        print(json.dumps(create_report(root), indent=2, default=str))


if __name__ == "__main__":
    main()
