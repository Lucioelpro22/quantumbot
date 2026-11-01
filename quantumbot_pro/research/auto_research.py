"""
research/auto_research.py — Motor de Investigación Autónomo (Auto Research Engine)
Realiza experimentos de optimización continuos y autónomos (búsqueda de hiperparámetros,
nuevos filtros y umbrales de score).
NUNCA reemplaza la versión estable de producción a menos que supere el 100% de las pruebas estadísticas.
"""

import os
import yaml
import pandas as pd
import numpy as np
from typing import Dict, Any, List
from research.validation_gate import StatisticalValidationGate
from backtesting.backtest_engine import QuantBacktestEngine
from backtesting.walk_forward import WalkForwardOptimizer
from backtesting.monte_carlo import MonteCarloSimulator


class AutoResearchEngine:
    def __init__(self, config_path: str = None):
        self.val_gate = StatisticalValidationGate()
        self.backtester = QuantBacktestEngine()
        self.wfo = WalkForwardOptimizer()
        self.mc  = MonteCarloSimulator()

    def run_optimization_experiment(self, df1h: pd.DataFrame, df15m: pd.DataFrame, symbol: str = "BTC-USD") -> Dict[str, Any]:
        """
        Ejecuta un experimento de investigación autónomo probando variaciones de parámetros.
        """
        print("\n🔬 [AUTO RESEARCH] Iniciando experimento autónomo de investigación...")

        # 1. Evaluar versión Estable de Producción (Benchmark)
        stable_metrics = self.backtester.run_backtest(df1h, df15m, symbol)

        # 2. Generar Candidato con Ponderaciones / Umbrales Optimizados (Experimento)
        # Ejemplo: Variar min_execution_score a 85.0 y re-evaluar
        orig_score = self.backtester.ensemble.min_execution_score
        self.backtester.ensemble.min_execution_score = 85.0

        candidate_metrics = self.backtester.run_backtest(df1h, df15m, symbol)
        wf_res = self.wfo.run_walk_forward(df1h, df15m, symbol)
        mc_res = self.mc.run_simulation([t['roi_percent'] / 100.0 for t in candidate_metrics.get('trade_logs', [])])

        # Restaurar estado
        self.backtester.ensemble.min_execution_score = orig_score

        # 3. Evaluar con el Motor de Puerta de Validación Estadística
        is_approved, msg, summary = self.val_gate.evaluate_candidate_hypothesis(
            stable_metrics, candidate_metrics, wf_res, mc_res
        )

        experiment_report = {
            "experiment_status": "PROMOTED_TO_STABLE" if is_approved else "REJECTED_STABLE_PRESERVED",
            "validation_message": msg,
            "stable_sharpe": stable_metrics.get("sharpe_ratio", 0.0),
            "candidate_sharpe": candidate_metrics.get("sharpe_ratio", 0.0),
            "stable_profit_factor": stable_metrics.get("profit_factor", 0.0),
            "candidate_profit_factor": candidate_metrics.get("profit_factor", 0.0),
            "summary_details": summary
        }

        print(f"📊 [AUTO RESEARCH RESULTADO] {msg}")
        return experiment_report
