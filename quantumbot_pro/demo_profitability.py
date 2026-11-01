"""Recolecta PnL cerrado de Bybit Demo y evalúa criterios de promoción."""
import argparse
import csv
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
LEDGER = ROOT / "data" / "bybit_demo_closed_pnl.csv"


def load_env():
    path = ROOT.parent / ".env"
    if not path.exists():
        path = ROOT / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line and not line.lstrip().startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def collect(client, output=LEDGER):
    output.parent.mkdir(parents=True, exist_ok=True)
    existing = {}
    if output.exists():
        with output.open(newline="", encoding="utf-8") as handle:
            existing = {row["order_id"]: row for row in csv.DictReader(handle)}
    cursor = None
    while True:
        response = client.get_closed_pnl(cursor=cursor)
        if response.get("retCode") != 0:
            raise RuntimeError(response.get("retMsg", "No se pudo consultar closed PnL"))
        for item in response.get("result", {}).get("list", []):
            pnl = float(item.get("closedPnl", 0))
            entry_value = abs(float(item.get("cumEntryValue", 0)))
            existing[item["orderId"]] = {
                "order_id": item["orderId"], "timestamp_ms": item.get("updatedTime", item.get("createdTime")),
                "symbol": item.get("symbol"), "side": item.get("side"), "pnl_usd": pnl,
                "return_pct": (pnl / entry_value * 100.0) if entry_value else 0.0,
                "open_fee": item.get("openFee", ""), "close_fee": item.get("closeFee", "")
            }
        cursor = response.get("result", {}).get("nextPageCursor") or None
        if not cursor:
            break
    fields = ["order_id", "timestamp_ms", "symbol", "side", "pnl_usd", "return_pct", "open_fee", "close_fee"]
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows(sorted(existing.values(), key=lambda row: int(row["timestamp_ms"])))
    return output


def evaluate(path=LEDGER):
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    pnl = np.array([float(row["pnl_usd"]) for row in rows], dtype=float)
    returns = np.array([float(row["return_pct"]) / 100.0 for row in rows], dtype=float)
    times = [datetime.fromtimestamp(int(row["timestamp_ms"]) / 1000, tz=timezone.utc) for row in rows]
    wins, losses = pnl[pnl > 0].sum(), abs(pnl[pnl < 0].sum())
    profit_factor = float(wins / losses) if losses else (999.0 if wins else 0.0)
    equity = np.cumsum(np.r_[0.0, pnl])
    peak = np.maximum.accumulate(equity)
    max_drawdown_usd = float(abs(np.min(equity - peak)))
    rng = np.random.default_rng(20260805)
    boot_means = np.array([rng.choice(returns, len(returns), replace=True).mean() for _ in range(5000)]) if len(returns) else np.array([0.0])
    ci_low = float(np.percentile(boot_means, 2.5))
    days = (max(times) - min(times)).days + 1 if times else 0
    gates = {
        "at_least_100_closed_trades": len(rows) >= 100,
        "at_least_60_calendar_days": days >= 60,
        "positive_net_pnl": float(pnl.sum()) > 0,
        "profit_factor_at_least_1_20": profit_factor >= 1.20,
        "bootstrap_mean_return_ci_above_zero": ci_low > 0,
    }
    return {
        "verdict": "PASS_DEMO_EVIDENCE" if all(gates.values()) else "INSUFFICIENT_OR_FAIL",
        "trades": len(rows), "calendar_days": days, "net_pnl_usd": round(float(pnl.sum()), 4),
        "profit_factor": round(profit_factor, 3), "max_drawdown_usd": round(max_drawdown_usd, 4),
        "bootstrap_95pct_mean_return_lower_bound": round(ci_low, 8), "gates": gates,
        "warning": "PASS no garantiza rentabilidad futura ni habilita trading real automáticamente."
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--collect", action="store_true")
    parser.add_argument("--report", default=str(ROOT / "reports" / "demo_profitability.json"))
    args = parser.parse_args()
    load_env()
    if args.collect:
        from bybit_client import BybitClient
        key, secret = os.getenv("BYBIT_API_KEY"), os.getenv("BYBIT_SECRET_KEY")
        if not key or not secret: raise SystemExit("Faltan claves exclusivas de Bybit Demo")
        collect(BybitClient(key, secret, use_testnet=False, use_demo=True))
    if not LEDGER.exists(): raise SystemExit("No hay ledger. Ejecuta primero con --collect")
    report = evaluate()
    report_path = Path(args.report); report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
