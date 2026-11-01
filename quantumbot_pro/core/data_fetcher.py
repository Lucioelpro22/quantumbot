"""
core/data_fetcher.py — Agregador Asincrónico de Datos Multi-Timeframe
Descarga y limpia simultáneamente datos de velas en 1D, 4H, 1H, 15M, 5M, 1M.
"""

import asyncio
import pandas as pd
import numpy as np
import yfinance as yf
from pathlib import Path
from typing import Dict, Tuple, Optional


class MultiTimeframeFetcher:
    def __init__(self):
        self._cache: Dict[str, Dict[str, pd.DataFrame]] = {}
        cache_dir = Path(__file__).resolve().parent.parent / "data" / "yfinance_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        yf.set_tz_cache_location(str(cache_dir))

    async def fetch_symbol_data(self, yf_symbol: str) -> Dict[str, pd.DataFrame]:
        """Descarga de forma asincrónica velas multi-temporalidad para un activo."""
        loop = asyncio.get_running_loop()

        def _download():
            d1d  = yf.download(yf_symbol, period='180d', interval='1d', progress=False)
            d1h  = yf.download(yf_symbol, period='30d',  interval='1h', progress=False)
            d15m = yf.download(yf_symbol, period='7d',   interval='15m', progress=False)
            d5m  = yf.download(yf_symbol, period='5d',   interval='5m', progress=False)

            result = {}
            for tf, df in [('1d', d1d), ('1h', d1h), ('15m', d15m), ('5m', d5m)]:
                if df is not None and not df.empty:
                    if isinstance(df.columns, pd.MultiIndex):
                        df.columns = df.columns.get_level_values(0)
                    cleaned = df.dropna()

                    # Resampling para obtener 4H a partir de 1H
                    if tf == '1h' and len(cleaned) >= 20:
                        df4h = cleaned.resample('4h').agg({
                            'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'
                        }).dropna()
                        result['4h'] = df4h

                    result[tf] = cleaned
            return result

        try:
            data = await loop.run_in_executor(None, _download)
            self._cache[yf_symbol] = data
            return data
        except Exception as e:
            print(f"[!] Error descargando datos para {yf_symbol}: {e}")
            return {}

    def get_cached_data(self, yf_symbol: str) -> Optional[Dict[str, pd.DataFrame]]:
        return self._cache.get(yf_symbol)
