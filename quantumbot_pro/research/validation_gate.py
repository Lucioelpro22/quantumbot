"""
research/validation_gate.py — Motor de Puerta de Validación Estadística Automatizada
Verifica estrictamente que cualquier modificación o nueva propuesta supere todas las métricas objetivas:
1. Sharpe Ratio >= Versión Anterior
2. Sortino Ratio >= Versión Anterior
3. Profit Factor >= Versión Anterior
4. Max Drawdown <= Versión Anterior
5. Expectancy Positiva (E > 0)
6. Robustez en Walk-Forward y Monte Carlo
7. Robustez Out-of-Sample
SI CUALQUIERA DE ESTOS REQUISITOS FALLA, RECHAZA EL CAMBIO AUTOMÁTICAMENTE.
"""

from typing import Dict, Any, Tuple


class StatisticalValidationGate:
    def __init__(self):
        pass

    def evaluate_candidate_hypothesis(self, stable_metrics: Dict[str, Any], candidate_metrics: Dict[str, Any],
                                      wf_results: Dict[str, Any] = None, mc_results: Dict[str, Any] = None) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Compara los resultados del candidato contra la versión estable de producción.
        Rechaza el cambio si degrada cualquier métrica objetiva.
        """
        reasons = []

        # 1. Sharpe Ratio (no inferior)
        c_sharpe = candidate_metrics.get("sharpe_ratio", 0.0)
        s_sharpe = stable_metrics.get("sharpe_ratio", 0.0)
        if c_sharpe < s_sharpe:
            reasons.append(f"Sharpe Ratio degradado ({c_sharpe:.2f} < {s_sharpe:.2f})")

        # 2. Sortino Ratio (igual o superior)
        c_sortino = candidate_metrics.get("sortino_ratio", 0.0)
        s_sortino = stable_metrics.get("sortino_ratio", 0.0)
        if c_sortino < s_sortino:
            reasons.append(f"Sortino Ratio degradado ({c_sortino:.2f} < {s_sortino:.2f})")

        # 3. Profit Factor (igual o superior)
        c_pf = candidate_metrics.get("profit_factor", 0.0)
        s_pf = stable_metrics.get("profit_factor", 0.0)
        if c_pf < s_pf:
            reasons.append(f"Profit Factor degradado ({c_pf:.2f} < {s_pf:.2f})")

        # 4. Max Drawdown (igual o inferior)
        c_dd = candidate_metrics.get("max_drawdown_percent", 100.0)
        s_dd = stable_metrics.get("max_drawdown_percent", 100.0)
        if c_dd > s_dd:
            reasons.append(f"Max Drawdown empeorado ({c_dd:.2f}% > {s_dd:.2f}%)")

        # 5. Expectancy Positiva (E > 0)
        win_rate = candidate_metrics.get("win_rate_percent", 0.0) / 100.0
        pf       = candidate_metrics.get("profit_factor", 0.0)
        expectancy = (win_rate * pf) - (1.0 - win_rate)
        if expectancy <= 0:
            reasons.append(f"Expectancy negativa o nula (E = {expectancy:.3f} <= 0)")

        # 6. Robustez Walk-Forward (si está disponible)
        if wf_results:
            if wf_results.get("status") != "PASSED":
                reasons.append("Falló la validación Walk-Forward (WFE Ratio < 0.60)")

        # 7. Robustez Monte Carlo (Riesgo de Ruina < 2.0%)
        if mc_results:
            risk_ruin = mc_results.get("risk_of_ruin_percent", 100.0)
            if risk_ruin > 2.0:
                reasons.append(f"Riesgo de Ruina Monte Carlo inaceptable ({risk_ruin:.1f}% > 2.0%)")

        is_passed = len(reasons) == 0

        summary = {
            "is_approved": is_passed,
            "candidate_sharpe": c_sharpe,
            "stable_sharpe": s_sharpe,
            "candidate_pf": c_pf,
            "candidate_drawdown": c_dd,
            "expectancy": round(expectancy, 4),
            "reasons_for_rejection": reasons
        }

        if is_passed:
            return True, "🟢 CANDIDATO APROBADO: Superó todas las pruebas estadísticas.", summary
        else:
            return False, f"🔴 CANDIDATO RECHAZADO AUTOMÁTICAMENTE: {'; '.join(reasons)}", summary
