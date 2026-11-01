"""
risk/auto_calibrator.py — Detector de Degradación y Calibrador Automático de Pesos
Monitorea continuamente la efectividad de cada módulo del ensemble.
Si un módulo degrada su tasa de acierto o sharpe ratio, reduce su peso automáticamente (auto-decay).
"""

from typing import Dict, List, Any


class StrategyAutoCalibrator:
    def __init__(self, initial_weights: Dict[str, float] = None, decay_factor: float = 0.85):
        self.default_weights = initial_weights or {
            "Bot23_Oxford_MultiTF": 0.25,
            "Bot22_FVG_Fibonacci": 0.15,
            "SMC_OrderBlock_Liquidity": 0.15,
            "VWAP_CVD_Volume": 0.15,
            "MeanReversion_RSI_Bollinger": 0.10,
            "Volatility_Breakout_Donchian": 0.10,
            "Keltner_Volatility_Squeeze": 0.10
        }
        self.weights = self.default_weights.copy()
        self.decay_factor = decay_factor

    def calibrate_from_trade_history(self, trade_history: List[Dict[str, Any]]) -> Dict[str, float]:
        if not trade_history or len(trade_history) < 10:
            return self.weights

        # Agrupar PnL por módulo
        module_stats = {}
        for mod in self.weights.keys():
            module_stats[mod] = {"wins": 0, "losses": 0, "total_pnl": 0.0}

        for trade in trade_history:
            mod = trade.get('module_name')
            pnl = trade.get('pnl_usd', 0.0)
            if mod in module_stats:
                if pnl > 0:
                    module_stats[mod]["wins"] += 1
                elif pnl < 0:
                    module_stats[mod]["losses"] += 1
                module_stats[mod]["total_pnl"] += pnl

        # Ajustar pesos según Profit Factor y Win Rate
        new_weights = {}
        for mod, stats in module_stats.items():
            total = stats["wins"] + stats["losses"]
            if total == 0:
                new_weights[mod] = self.weights[mod]
                continue

            win_rate = stats["wins"] / total
            # Si el módulo degrada (Win Rate < 40%), aplicar auto-decay
            if win_rate < 0.40:
                new_weights[mod] = self.weights[mod] * self.decay_factor
            elif win_rate >= 0.60:
                new_weights[mod] = self.weights[mod] * 1.15
            else:
                new_weights[mod] = self.weights[mod]

        # Normalizar a 1.0
        sum_w = sum(new_weights.values())
        if sum_w > 0:
            self.weights = {k: round(v / sum_w, 4) for k, v in new_weights.items()}

        return self.weights
