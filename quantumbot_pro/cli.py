"""
cli.py — Interfaz de Línea de Comandos Unificada para QuantumBot Pro v3.0
Soporta los modos: live, demo, backtest, walkforward, montecarlo, stress, crisis, research, xai.

Ejemplos:
  python cli.py --mode demo
  python cli.py --mode research --symbol BTC-USD
  python cli.py --mode crisis --symbol BTC-USD
  python cli.py --mode xai
"""

import sys
import os
import argparse
import asyncio

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path: sys.path.append(current_dir)

from core.data_fetcher import MultiTimeframeFetcher
from backtesting.backtest_engine import QuantBacktestEngine
from backtesting.walk_forward import WalkForwardOptimizer
from backtesting.monte_carlo import MonteCarloSimulator
from backtesting.stress_test import StressTestEngine
from backtesting.crisis_simulator import SystemicCrisisSimulator
from research.auto_research import AutoResearchEngine
from analytics.xai_engine import ExplainableAIEngine
from database.db_manager import QuantDatabaseManager
from main import QuantumBotEngine


def parse_args():
    parser = argparse.ArgumentParser(description="QuantumBot Pro v3.0 — Autonomous Quant & XAI Platform CLI")
    parser.add_argument("--mode", type=str, default="demo",
                        choices=["live", "demo", "backtest", "walkforward", "montecarlo", "stress", "crisis", "research", "xai"],
                        help="Modo de ejecución del sistema")
    parser.add_argument("--symbol", type=str, default="BTC-USD", help="Símbolo a evaluar (ej: BTC-USD)")
    return parser.parse_args()


async def run_cli():
    args = parse_args()
    print("=" * 80)
    print(f"🚀 QUANTUMBOT PRO v3.0 — AUTONOMOUS QUANT & XAI PLATFORM [MODO: {args.mode.upper()}]")
    print("=" * 80)

    if args.mode in ["live", "demo"]:
        config_dir = os.path.join(current_dir, 'config')
        bot = QuantumBotEngine(config_dir)
        print(f"\n[+] Iniciando motor en tiempo real (Modo: {args.mode.upper()})...\n")
        await bot.run_cycle()

    elif args.mode == "xai":
        db = QuantDatabaseManager()
        decisions = db.get_recent_decisions(limit=5)
        xai_engine = ExplainableAIEngine()
        print("\n🔍 ULTIMOS REGISTROS AUDITABLES EXPLAINABLE AI (XAI):\n")
        if not decisions:
            print("  (No hay decisiones registradas aún en la base de datos)")
        for d in decisions:
            print(f"• ID {d['id']} | {d['timestamp']} | {d['symbol']} | {d['direction']} | Score: {d['total_score']} | ML Prob: {d['ml_probability']*100:.1f}% | Razón: {d['reason']}")

    elif args.mode in ["backtest", "walkforward", "montecarlo", "stress", "crisis", "research"]:
        fetcher = MultiTimeframeFetcher()
        print(f"\n[+] Descargando velas históricas para {args.symbol}...")
        data = await fetcher.fetch_symbol_data(args.symbol)

        df1h  = data.get('1h')
        df15m = data.get('15m')

        if df1h is None or df15m is None:
            print("[!] Error: No se pudieron descargar datos de mercado suficientes.")
            return

        if args.mode == "backtest":
            print("\n[+] Ejecutando Backtesting Event-Driven Realista...")
            engine = QuantBacktestEngine()
            results = engine.run_backtest(df1h, df15m, args.symbol)
            print("\n📊 REPORTE DE MÉTRICAS INSTITUCIONALES:")
            for k, v in results.items():
                if k != "trade_logs": print(f"  • {k.replace('_', ' ').title()}: {v}")

        elif args.mode == "walkforward":
            print("\n[+] Ejecutando Optimización Walk-Forward...")
            wfo = WalkForwardOptimizer()
            results = wfo.run_walk_forward(df1h, df15m, args.symbol)
            print("\n🔬 RESULTADO WALK-FORWARD:")
            for k, v in results.items(): print(f"  • {k.replace('_', ' ').title()}: {v}")

        elif args.mode == "montecarlo":
            print("\n[+] Ejecutando Simulación Monte Carlo (1,000 Iteraciones)...")
            engine = QuantBacktestEngine()
            backtest_res = engine.run_backtest(df1h, df15m, args.symbol)
            returns = [t['roi_percent'] / 100.0 for t in backtest_res.get('trade_logs', [])]
            mc = MonteCarloSimulator(n_simulations=1000)
            mc_res = mc.run_simulation(returns)
            print("\n🎲 RESULTADO MONTE CARLO:")
            for k, v in mc_res.items(): print(f"  • {k.replace('_', ' ').title()}: {v}")

        elif args.mode == "crisis":
            print("\n[+] Ejecutando Simulador de Choques de Crisis (COVID-19, FTX Collapse, Flash Crash)...")
            cs = SystemicCrisisSimulator()
            c_res = cs.run_all_crisis_scenarios(df1h, df15m)
            print("\n⚡ RESULTADO DE SIMULADOR DE CRISIS SISTÉMICAS:")
            print(f"  • Supervivencia Total: {'🟢 PASADA' if c_res['all_crisis_passed'] else '🔴 FALLADA'}")
            for sc, det in c_res["scenario_details"].items():
                print(f"    - {sc}: Max DD {det['max_drawdown_percent']}% | PF {det['profit_factor']} | PASADO: {det['survival_passed']}")

        elif args.mode == "research":
            print("\n[+] Ejecutando Bucle de Investigación Autónoma (Auto Research Engine)...")
            ar = AutoResearchEngine()
            res = ar.run_optimization_experiment(df1h, df15m, args.symbol)
            print(f"\n🧪 RESULTADO AUTO RESEARCH: {res['experiment_status']}")
            print(f"  • {res['validation_message']}")


if __name__ == '__main__':
    asyncio.run(run_cli())
