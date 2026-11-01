"""
analytics/metrics.py — Panel de Métricas Cuantitativas e Institucionales (Hedge Fund Suite)
Calcula métricas estadísticas avanzadas: Sharpe, Sortino, Calmar, Deflated Sharpe Ratio (DSR formal),
Omega Ratio, Ulcer Index, VaR (95%/99%), CVaR, Recovery Factor, Rolling Sharpe y Max Consecutive Losses (P4 & P5).
"""

import math
import numpy as np
import pandas as pd
from scipy.stats import norm, skew, kurtosis
from typing import Dict, Any, List


class QuantitativeMetricsEngine:
    def __init__(self, risk_free_rate: float = 0.04):
        self.risk_free_rate = risk_free_rate  # 4% Tasa libre de riesgo anualizada

    def calculate_metrics(self, returns: List[float], equity_curve: List[float], holding_times_minutes: List[float] = None, n_trials: int = 10) -> Dict[str, Any]:
        """
        P4 & P5 — Validación matemática rigurosa de métricas e implementación formal del Deflated Sharpe Ratio (DSR).
        """
        if not returns or len(returns) < 5:
            return self._empty_metrics()

        rets = np.array(returns)
        eq = np.array(equity_curve)

        total_trades = len(rets)
        wins = rets[rets > 0]
        losses = rets[rets < 0]
        win_rate = (len(wins) / total_trades) * 100.0 if total_trades > 0 else 0.0

        total_profit = np.sum(wins) if len(wins) > 0 else 0.0
        total_loss = abs(np.sum(losses)) if len(losses) > 0 else 0.0
        profit_factor = total_profit / total_loss if total_loss > 0 else (999.0 if total_profit > 0 else 0.0)

        # 1. Retorno Promedio y Desviación Estándar
        mean_ret = np.mean(rets)
        std_ret = np.std(rets, ddof=1) if len(rets) > 1 else 1e-6

        # 2. Sharpe Ratio (Anualizado cripto 365 días)
        rf_per_trade = self.risk_free_rate / 365.0
        sharpe = ((mean_ret - rf_per_trade) / std_ret) * np.sqrt(365) if std_ret > 0 else 0.0

        # 3. Sortino Ratio (Volatilidad bajista)
        downside_rets = rets[rets < 0]
        std_downside = np.std(downside_rets, ddof=1) if len(downside_rets) > 1 else 1e-6
        sortino = ((mean_ret - rf_per_trade) / std_downside) * np.sqrt(365) if std_downside > 0 else 0.0

        # 4. Drawdown y Max Drawdown
        running_max = np.maximum.accumulate(eq)
        drawdowns = (eq - running_max) / (running_max + 1e-8)
        max_drawdown = abs(np.min(drawdowns)) * 100.0 if len(drawdowns) > 0 else 0.0

        # 5. Calmar Ratio
        total_return_pct = ((eq[-1] - eq[0]) / eq[0]) * 100.0 if len(eq) > 0 and eq[0] > 0 else 0.0
        calmar = (total_return_pct / max_drawdown) if max_drawdown > 0 else 0.0

        # 6. Omega Ratio
        gain_sum = np.sum(rets[rets > 0])
        loss_sum = abs(np.sum(rets[rets < 0]))
        omega = gain_sum / loss_sum if loss_sum > 0 else 999.0

        # 7. Ulcer Index
        ulcer_index = np.sqrt(np.mean(drawdowns ** 2)) * 100.0 if len(drawdowns) > 0 else 0.0

        # 8. Value at Risk (VaR 95% y 99%) & CVaR
        var_95 = abs(np.percentile(rets, 5)) * 100.0
        var_99 = abs(np.percentile(rets, 1)) * 100.0
        cvar_95 = abs(np.mean(rets[rets <= np.percentile(rets, 5)])) * 100.0 if len(rets[rets <= np.percentile(rets, 5)]) > 0 else var_95

        # 9. Recovery Factor
        net_profit_usd = eq[-1] - eq[0] if len(eq) > 0 else 0.0
        max_dd_usd = abs(np.min(eq - running_max)) if len(eq) > 0 else 0.0
        recovery_factor = net_profit_usd / max_dd_usd if max_dd_usd > 0 else 0.0

        # 10. Pérdidas Consecutivas Máximas
        max_consec_losses = 0
        curr_consec = 0
        for r in rets:
            if r < 0:
                curr_consec += 1
                if curr_consec > max_consec_losses:
                    max_consec_losses = curr_consec
            else:
                curr_consec = 0

        # 11. Tiempo de Retención Promedio
        avg_holding_min = float(np.mean(holding_times_minutes)) if holding_times_minutes and len(holding_times_minutes) > 0 else 0.0

        # 12. P5 — DEFLATED SHARPE RATIO (DSR FORMAL DE LÓPEZ DE PRADO)
        dsr = self.calculate_formal_dsr(rets, sharpe, n_trials=n_trials)

        return {
            "total_trades": total_trades,
            "win_rate_percent": round(win_rate, 2),
            "profit_factor": round(profit_factor, 2),
            "total_return_percent": round(total_return_pct, 2),
            "sharpe_ratio": round(sharpe, 2),
            "sortino_ratio": round(sortino, 2),
            "calmar_ratio": round(calmar, 2),
            "deflated_sharpe_ratio": round(dsr, 2),
            "omega_ratio": round(omega, 2),
            "ulcer_index": round(ulcer_index, 2),
            "max_drawdown_percent": round(max_drawdown, 2),
            "var_95_percent": round(var_95, 2),
            "var_99_percent": round(var_99, 2),
            "cvar_95_percent": round(cvar_95, 2),
            "recovery_factor": round(recovery_factor, 2),
            "max_consecutive_losses": max_consec_losses,
            "avg_holding_minutes": round(avg_holding_min, 1)
        }

    def calculate_formal_dsr(self, rets: np.ndarray, estimated_sharpe: float, n_trials: int = 10) -> float:
        """
        P5 — Cálculo riguroso del Deflated Sharpe Ratio (DSR):
        DSR = Z[ (SR_hat - SR_star) * sqrt(N - 1) / sqrt(1 - skew * SR_hat + (kurt - 1)/4 * SR_hat^2) ]
        """
        n = len(rets)
        std_ret = np.std(rets)
        if n < 5 or std_ret == 0:
            return 0.0

        sk = float(skew(rets))
        kt = float(kurtosis(rets, fisher=False))

        e_max_sr = (1.0 - 0.57721566) * norm.ppf(1.0 - 1.0 / n_trials) + 0.57721566 * norm.ppf(1.0 - 1.0 / (n_trials * np.e))
        sr_star = max(0.0, e_max_sr)

        denom = math.sqrt(max(1e-6, 1.0 - sk * estimated_sharpe + ((kt - 1.0) / 4.0) * (estimated_sharpe ** 2)))
        stat = ((estimated_sharpe - sr_star) * math.sqrt(n - 1)) / denom

        dsr_prob = norm.cdf(stat)
        return float(dsr_prob)

    def _empty_metrics(self) -> Dict[str, Any]:
        return {
            "total_trades": 0, "win_rate_percent": 0.0, "profit_factor": 0.0,
            "total_return_percent": 0.0, "sharpe_ratio": 0.0, "sortino_ratio": 0.0,
            "calmar_ratio": 0.0, "deflated_sharpe_ratio": 0.0, "omega_ratio": 0.0,
            "ulcer_index": 0.0, "max_drawdown_percent": 0.0, "var_95_percent": 0.0,
            "var_99_percent": 0.0, "cvar_95_percent": 0.0, "recovery_factor": 0.0,
            "max_consecutive_losses": 0, "avg_holding_minutes": 0.0
        }
