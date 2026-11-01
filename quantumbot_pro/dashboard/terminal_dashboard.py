"""
dashboard/terminal_dashboard.py — Dashboard Cuantitativo en Tiempo Real
Renderiza el estado del mercado, scores de decisión, posiciones activas y métricas de rendimiento.
"""

from typing import Dict, Any, List
from core.models import MarketRegimeState, ScoreBreakdown, RiskDecision


class TerminalDashboard:
    def print_header(self, environment: str, equity: float):
        print("=" * 85)
        print(f" QUANTUMBOT PRO v1.0 — HEDGE FUND QUANTITATIVE ENGINE [{environment.upper()}] ".center(85, "="))
        print("=" * 85)
        print(f" 💵 Capital Total (Equity VST/USDT): ${equity:,.2f}")
        print("-" * 85)

    def print_market_scan(
        self,
        evaluations: List[Dict[str, Any]]
    ):
        print(f"{'Activo':<10} | {'Regimen Mercado':<20} | {'Dir':<5} | {'Score':>6} | {'ML Prob':>8} | {'Estado / Decisión':<22}")
        print("-" * 85)
        for ev in evaluations:
            sym     = ev['symbol']
            regime  = ev['regime'].regime.value
            score   = ev['score']
            prob    = ev['ml_prob']
            dir_str = score.direction.value if score else "NEUT"
            sc_val  = score.total_score if score else 0.0
            status  = "APROBADO" if ev['decision'].is_allowed else "RECHAZADO"

            print(f"{sym:<10} | {regime:<20} | {dir_str:<5} | {sc_val:>6.1f} | {prob*100:>7.1f}% | {status:<22}")
        print("-" * 85)

    def print_footer(self):
        print("[OK] Ciclo de evaluación cuantitativa QuantumBot Pro v1.0 completado.\n")
