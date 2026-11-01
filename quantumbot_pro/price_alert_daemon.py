"""
price_alert_daemon.py — Demonio de Alertas de Precios de Entrada (PDF Levels Monitor)
Monitorea continuamente los 95 niveles de entrada 'Pendiente' extraídos del PDF.
Dispara alertas instantáneas cuando el precio de mercado se aproxima (+/- 0.8%) o toca el nivel objetivo.
Usa consulta híbrida vía BingX API + Yahoo Finance.
"""

import os
import sys
import json
import time
import asyncio
import datetime
import requests
import yfinance as yf

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if current_dir not in sys.path: sys.path.append(current_dir)
if parent_dir not in sys.path: sys.path.append(parent_dir)

from database.db_manager import QuantDatabaseManager

ALERTS_CONFIG = os.path.join(current_dir, 'config', 'price_alerts.json')
LOG_DIR = os.path.join(current_dir, 'logs')
os.makedirs(LOG_DIR, exist_ok=True)
ALERT_LOG_FILE = os.path.join(LOG_DIR, 'price_alerts.log')


def log_alert(msg: str):
    ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f"[{ts}] {msg}"
    try:
        print(line)
    except Exception:
        pass
    with open(ALERT_LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(line + '\n')


class PriceAlertMonitor:
    def __init__(self, proximity_pct: float = 0.8):
        self.proximity_pct = proximity_pct  # Alerta si está dentro del 0.8%
        self.db = QuantDatabaseManager()
        self.alerts_list = self._load_alerts()
        self.triggered_alerts = set()
        self.bingx_tickers_cache = {}

    def _load_alerts(self):
        if not os.path.exists(ALERTS_CONFIG):
            return []
        with open(ALERTS_CONFIG, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _fetch_bingx_prices(self) -> dict:
        prices = {}
        try:
            url = "https://open-api.bingx.com/openApi/swap/v2/quote/ticker"
            res = requests.get(url, timeout=5)
            if res.status_code == 200:
                data = res.json()
                if data.get('code') == 0:
                    for item in data.get('data', []):
                        sym = item.get('symbol')  # ej: "BTC-USDT"
                        price = float(item.get('lastPrice', 0))
                        if price > 0:
                            asset = sym.split('-')[0]
                            prices[asset] = price
                            prices[f"{asset}-USD"] = price
        except Exception:
            pass
        return prices

    def fetch_live_prices(self) -> dict:
        # 1. Probar BingX Ticker API (muy rápido y cubre criptomonedas reales)
        prices = self._fetch_bingx_prices()

        # 2. Fallback a Yahoo Finance para activos faltantes
        missing_assets = [a['asset'] for a in self.alerts_list if a['asset'] not in prices]
        if missing_assets:
            yf_symbols = [f"{a}-USD" for a in list(set(missing_assets))]
            try:
                df = yf.download(" ".join(yf_symbols), period="1d", interval="1m", progress=False, group_by="ticker")
                for asset in missing_assets:
                    sym = f"{asset}-USD"
                    try:
                        if len(yf_symbols) == 1:
                            px = float(df['Close'].dropna().iloc[-1])
                        else:
                            px = float(df[sym]['Close'].dropna().iloc[-1])
                        if px > 0:
                            prices[asset] = px
                            prices[sym] = px
                    except Exception:
                        pass
            except Exception:
                pass
        return prices

    def check_alerts(self):
        prices = self.fetch_live_prices()
        if not prices:
            return

        for item in self.alerts_list:
            asset = item['asset']
            curr_px = prices.get(asset) or prices.get(item['symbol'])
            if not curr_px:
                continue

            entry_min = item['entry_min']
            entry_max = item['entry_max']
            direction = item['direction']
            alert_type = item['type']
            tv_link    = item['tv_link']

            # Distancia porcentual al nivel de entrada
            if entry_min <= curr_px <= entry_max:
                dist_pct = 0.0
                is_hit = True
            elif curr_px < entry_min:
                dist_pct = abs((entry_min - curr_px) / curr_px) * 100.0
                is_hit = dist_pct <= self.proximity_pct and direction == "LONG"
            else:
                dist_pct = abs((curr_px - entry_max) / curr_px) * 100.0
                is_hit = dist_pct <= self.proximity_pct and direction == "SHORT"

            alert_key = f"{asset}_{entry_min}_{entry_max}_{direction}"

            if is_hit or dist_pct <= self.proximity_pct:
                if alert_key not in self.triggered_alerts:
                    self.triggered_alerts.add(alert_key)
                    banner = (
                        f"\n[ALERTA NIVELES ENTRADA] {asset} ({direction})\n"
                        f"  * Precio Mercado Actual: ${curr_px:,.4f}\n"
                        f"  * Nivel Entrada PDF:     ${entry_min:,.4f} - ${entry_max:,.4f}\n"
                        f"  * Tipo Operacion:        {alert_type}\n"
                        f"  * Distancia al Nivel:    {dist_pct:.2f}%\n"
                        f"  * Grafica TradingView:   {tv_link}\n"
                    )
                    log_alert(banner)
                    try:
                        import winsound
                        winsound.Beep(1000, 500)
                    except Exception:
                        pass


async def main_loop():
    print("=" * 80)
    print("MONITOR DE ALERTAS DE PRECIO DE ENTRADA (NIVELES DEL PDF)")
    print("Monitoreando 95 niveles de entrada Pendiente en tiempo real via BingX + Yahoo Finance...")
    print("=" * 80)

    monitor = PriceAlertMonitor(proximity_pct=0.8)

    while True:
        try:
            monitor.check_alerts()
        except Exception as e:
            print(f"[!] Error en monitor de alertas: {e}")
        await asyncio.sleep(15)


if __name__ == '__main__':
    asyncio.run(main_loop())
