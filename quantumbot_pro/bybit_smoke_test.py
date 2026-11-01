"""Prueba de solo lectura para Bybit Demo; nunca crea, cambia ni cancela órdenes."""
import json
import os
import hashlib
import hmac
import time
import urllib.parse
import urllib.request
from pathlib import Path


def load_env():
    for candidate in (Path(__file__).resolve().parent / ".env", Path(__file__).resolve().parent.parent / ".env"):
        if candidate.exists():
            for line in candidate.read_text(encoding="utf-8").splitlines():
                if line and not line.lstrip().startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ.setdefault(key.strip(), value.strip())
            return candidate
    raise RuntimeError("No se encontró .env")


def main():
    env_path = load_env()
    key = os.getenv("BYBIT_API_KEY", "").strip()
    secret = os.getenv("BYBIT_SECRET_KEY", "").strip()
    if not key or not secret:
        raise RuntimeError("Faltan BYBIT_API_KEY o BYBIT_SECRET_KEY")
    endpoint = "https://api-demo.bybit.com"

    def get(path, params):
        query = urllib.parse.urlencode(sorted(params.items()))
        timestamp, recv_window = str(int(time.time() * 1000)), "5000"
        payload = timestamp + key + recv_window + query
        signature = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
        request = urllib.request.Request(
            f"{endpoint}{path}?{query}",
            headers={"X-BAPI-API-KEY": key, "X-BAPI-SIGN": signature,
                     "X-BAPI-TIMESTAMP": timestamp, "X-BAPI-RECV-WINDOW": recv_window}
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))

    balance = get("/v5/account/wallet-balance", {"accountType": "UNIFIED", "coin": "USDT"})
    positions = get("/v5/position/list", {"category": "linear", "settleCoin": "USDT"})
    instrument = get("/v5/market/instruments-info", {"category": "linear", "symbol": "BTCUSDT"})
    active = [p for p in positions.get("result", {}).get("list", []) if float(p.get("size", 0) or 0) > 0]
    summary = {
        "endpoint": endpoint,
        "env_file": str(env_path),
        "auth_balance_ok": balance.get("retCode") == 0,
        "balance_message": balance.get("retMsg"),
        "positions_ok": positions.get("retCode") == 0,
        "positions_message": positions.get("retMsg"),
        "active_positions": len(active) if positions.get("retCode") == 0 else None,
        "position_protection": [
            {"symbol": p.get("symbol"), "side": p.get("side"), "leverage": p.get("leverage"),
             "has_stop_loss": float(p.get("stopLoss", 0) or 0) > 0,
             "has_take_profit": float(p.get("takeProfit", 0) or 0) > 0,
             "status": p.get("positionStatus")}
            for p in active
        ],
        "market_metadata_ok": instrument.get("retCode") == 0,
        "market_metadata_message": instrument.get("retMsg"),
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    if not all((summary["auth_balance_ok"], summary["positions_ok"], summary["market_metadata_ok"])):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
