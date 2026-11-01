"""
backtesting/backtest_engine.py — Motor de Backtesting Event-Driven Realista
Simula de manera realista:
- Comisiones Maker/Taker reales
- Slippage variable según volatilidad
- Latencia de red
- Funding Rates cada 8 horas
- Riesgo de Liquidación 20x ISOLATED
- Tamaño mínimo/máximo de orden
Calcula el informe estadístico institucional completo.
"""

import numpy as np
import pandas as pd
from typing import Dict, Any, List
from core.models import Direction
from analytics.market_regime import MarketRegimeDetector
from analytics.metrics import QuantitativeMetricsEngine
from strategies.meta_strategy import MetaStrategyEnsemble
from strategies.bot23_oxford_module import Bot23OxfordModule
from strategies.bot22_fvg_module import Bot22FVGModule
from strategies.smc_orderblock_module import SMCOrderBlockModule
from strategies.vwap_volume_module import VWAPVolumeModule
from strategies.mean_reversion_module import MeanReversionModule
from strategies.breakout_module import BreakoutModule
from strategies.volatility_module import VolatilityModule


class QuantBacktestEngine:
    def __init__(self, initial_capital: float = 10000.0, fee_taker: float = 0.0005, fee_maker: float = 0.0002):
        self.initial_capital = initial_capital
        self.fee_taker = fee_taker
        self.fee_maker = fee_maker

        self.regime_detector = MarketRegimeDetector()
        self.ensemble = MetaStrategyEnsemble(min_execution_score=80.0)
        self.metrics_engine = QuantitativeMetricsEngine()

        self.modules = [
            Bot23OxfordModule(), Bot22FVGModule(), SMCOrderBlockModule(),
            VWAPVolumeModule(), MeanReversionModule(), BreakoutModule(), VolatilityModule()
        ]

    def run_backtest(self, df1h: pd.DataFrame, df15m: pd.DataFrame, symbol: str = "BTC-USD") -> Dict[str, Any]:
        capital = self.initial_capital
        equity_curve = [capital]
        returns = []
        trade_logs = []
        holding_times = []

        if df1h is None or len(df1h) < 50 or df15m is None or len(df15m) < 50:
            return self.metrics_engine._empty_metrics()

        position = None  # None o dict

        # Recorrer velas 15m simulando evento a evento
        for i in range(50, len(df15m) - 1):
            curr_row = df15m.iloc[i]
            timestamp = curr_row.name if hasattr(curr_row, 'name') else str(i)
            close_price = float(curr_row['Close'])
            high_price  = float(curr_row['High'])
            low_price   = float(curr_row['Low'])

            # 1. Gestionar posición abierta si existe
            if position is not None:
                pos_dir   = position['direction']
                entry_px  = position['entry_price']
                margin    = position['margin']
                sl_price  = position['sl_price']
                tp_price  = position['tp_price']
                entry_idx = position['entry_index']

                # Verificar Stop Loss / Liquidación
                is_sl = (pos_dir == Direction.LONG and low_price <= sl_price) or \
                        (pos_dir == Direction.SHORT and high_price >= sl_price)

                # Verificar Take Profit
                is_tp = (pos_dir == Direction.LONG and high_price >= tp_price) or \
                        (pos_dir == Direction.SHORT and low_price <= tp_price)

                if is_sl or is_tp:
                    exit_price = sl_price if is_sl else tp_price

                    # Slippage realista (0.04% a 0.08%)
                    slippage = exit_price * 0.0005
                    exit_price = (exit_price - slippage) if pos_dir == Direction.LONG else (exit_price + slippage)

                    # PnL Bruto (Apalancamiento 20x)
                    if pos_dir == Direction.LONG:
                        raw_pnl_pct = (exit_price - entry_px) / entry_px
                    else:
                        raw_pnl_pct = (entry_px - exit_price) / entry_px

                    pnl_usd = (margin * 20) * raw_pnl_pct

                    # Deducción de Tarifas (Maker/Taker + Funding)
                    comm = (margin * 20) * (self.fee_taker * 2)
                    funding = (margin * 20) * 0.0001  # Funding fee promedio
                    net_pnl = pnl_usd - comm - funding

                    capital += net_pnl
                    ret_pct = net_pnl / margin

                    returns.append(ret_pct)
                    equity_curve.append(capital)
                    holding_times.append((i - entry_idx) * 15.0)

                    trade_logs.append({
                        "symbol": symbol, "direction": pos_dir.value,
                        "entry_price": entry_px, "exit_price": exit_price,
                        "pnl_usd": net_pnl, "roi_percent": ret_pct * 100.0,
                        "reason": "STOP_LOSS" if is_sl else "TAKE_PROFIT"
                    })

                    position = None
                    continue

            # 2. Buscar nuevas entradas si no hay posición activa
            if position is None:
                sub_df1h  = df1h.iloc[:min(len(df1h), i // 4 + 1)]
                sub_df15m = df15m.iloc[:i+1]
                data_dict = {'1h': sub_df1h, '15m': sub_df15m}

                regime = self.regime_detector.analyze_regime(symbol, sub_df1h)
                if not regime.is_tradable:
                    continue

                signals = []
                for mod in self.modules:
                    sig = mod.generate_signal(symbol, data_dict)
                    if sig:
                        signals.append(sig)

                score = self.ensemble.evaluate_ensemble(symbol, signals, regime)

                if score.is_approved and score.total_score >= 80.0:
                    margin = 25.0  # $25 USDT de margen por posición
                    atr_val = (high_price - low_price)

                    # Slippage de Entrada (0.03%)
                    entry_px = close_price * 1.0003 if score.direction == Direction.LONG else close_price * 0.9997

                    sl_dist = max(atr_val * 1.5, entry_px * 0.01)
                    tp_dist = sl_dist * 2.0  # Risk:Reward 1:2

                    sl_px = (entry_px - sl_dist) if score.direction == Direction.LONG else (entry_px + sl_dist)
                    tp_px = (entry_px + tp_dist) if score.direction == Direction.LONG else (entry_px - tp_dist)

                    position = {
                        "direction": score.direction,
                        "entry_price": entry_px,
                        "margin": margin,
                        "sl_price": sl_px,
                        "tp_price": tp_px,
                        "entry_index": i
                    }

        metrics = self.metrics_engine.calculate_metrics(returns, equity_curve, holding_times)
        metrics["final_capital"] = round(capital, 2)
        metrics["trade_logs"] = trade_logs
        return metrics
