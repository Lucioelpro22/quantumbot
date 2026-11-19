"""Metadata-only CLI. Operational modes reject before any engine import."""
import argparse
import json

if __package__:
    from .operational_policy import OperationalBlocked, health_snapshot, require_operational_access
else:
    from operational_policy import OperationalBlocked, health_snapshot, require_operational_access


def main(argv=None):
    parser = argparse.ArgumentParser(description="QuantumBot engineering health (offline)")
    parser.add_argument("--mode", default="status", choices=[
        "status", "live", "demo", "paper", "shadow", "backtest", "walkforward",
        "montecarlo", "stress", "crisis", "research", "xai",
    ])
    parser.add_argument("--symbol", default=None)
    args = parser.parse_args(argv)
    if args.mode != "status":
        try:
            require_operational_access(args.mode)
        except OperationalBlocked as exc:
            print(str(exc))
            return 2
    print(json.dumps(health_snapshot(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
