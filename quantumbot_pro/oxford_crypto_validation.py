"""Valida el modelo Oxford diario sobre BTC y ETH con costos explícitos."""
import json
from dataclasses import asdict
from pathlib import Path

import yfinance as yf

from strategies.oxford_daily_ma import evaluate_oxford


def main():
    cache = Path(__file__).resolve().parent / "data" / "yfinance_cache"
    cache.mkdir(parents=True, exist_ok=True)
    yf.set_tz_cache_location(str(cache))
    results = []
    for symbol in ("BTC-USD", "ETH-USD"):
        data = yf.download(symbol, start="2017-01-01", interval="1d", auto_adjust=False, progress=False)
        if hasattr(data.columns, "nlevels") and data.columns.nlevels > 1:
            data.columns = data.columns.get_level_values(0)
        full = asdict(evaluate_oxford(data["Close"], symbol, ma_days=5, round_trip_cost_bps=12.0))
        oos_close = data.loc[data.index >= "2022-01-01", "Close"]
        oos = asdict(evaluate_oxford(oos_close, symbol, ma_days=5, round_trip_cost_bps=12.0))
        results.append({"full_history": full, "out_of_sample_2022_plus": oos})
    payload = {
        "model": "Oxford M4U2 SMA(5) long/cash, signal delayed one bar",
        "cost_assumption": "12 bps round trip",
        "results": results,
        "promotion_rule": "Research only; reject if OOS max drawdown exceeds 20%, profit factor is below 1.20, or Sharpe is below 1.0."
    }
    output = Path(__file__).resolve().parent / "reports" / "oxford_crypto_validation.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
