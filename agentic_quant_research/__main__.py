"""CLI for the offline workflow and optional user-supplied inputs."""
import argparse
import json
from pathlib import Path
import pandas as pd
from .core import default_proposals, generate_market, run_workflow


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--market-csv", type=Path)
    parser.add_argument("--proposals", type=Path)
    parser.add_argument("--output", type=Path, default=Path("local-runs/demo"))
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--stop-after", choices=["admitted", "frozen"])
    args = parser.parse_args()
    if args.demo and (args.market_csv or args.proposals):
        parser.error("Choose demo or a market CSV/proposal JSON pair")
    if bool(args.market_csv) != bool(args.proposals):
        parser.error("Both --market-csv and --proposals are required")
    if args.market_csv:
        market = pd.read_csv(args.market_csv, dtype={"asset": str})
        proposals = json.loads(args.proposals.read_text(encoding="utf-8"))
        kind = "user-supplied"
    else:
        market, proposals, kind = generate_market(), default_proposals(), "synthetic"
    result = run_workflow(market, proposals, args.output, resume=args.resume, stop_after=args.stop_after, data_kind=kind)
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
