"""
quantumbot_pro/main.py — Motor Cuantitativo Principal para QuantumBot Pro v3.0
Orquestador de plataforma institucional con ensemble de 9 módulos, candado de aislamiento de entorno (P0.2),
reconciliador de estado con el exchange (P0.5), verificación real de SL/TP (P0.4), Kill Switch (P0.3),
y soporte multi-exchange (BingX & Bybit V5 Real/Demo).
"""

import asyncio
import os
import sys
import yaml
import pandas as pd
from typing import Dict, List, Any

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir  = os.path.dirname(current_dir)
if current_dir not in sys.path: sys.path.append(current_dir)
if parent_dir not in sys.path: sys.path.append(parent_dir)

from core.models import Direction
from core.data_fetcher import MultiTimeframeFetcher
from database.db_manager import QuantDatabaseManager
from analytics.market_regime import MarketRegimeDetector
from analytics.metrics import QuantitativeMetricsEngine
from analytics.price_action_engine import PriceActionConfirmationEngine
from machine_learning.ml_guard import SupervisedMLGuard
from risk.risk_manager import QuantumRiskManager
from risk.portfolio_manager import PortfolioManager
from risk.auto_calibrator import StrategyAutoCalibrator
from execution.bingx_executor import AsyncBingXExecutor
from execution.bybit_executor import AsyncBybitExecutor
from execution.position_manager import QuantumPositionManager
from execution.reconciler import ExchangeStateReconciler
from dashboard.terminal_dashboard import TerminalDashboard

# Estrategias (9 Módulos)
from strategies.oracle_fibonacci_dca_module import OracleFibonacciDCAModule
from strategies.blackeaglescap_module import BlackEaglesCapModule
from strategies.bot22_fvg_module import Bot22FVGModule
from strategies.bot23_oxford_module import Bot23OxfordModule
from strategies.smc_orderblock_module import SMCOrderBlockModule
from strategies.vwap_volume_module import VWAPVolumeModule
from strategies.mean_reversion_module import MeanReversionModule
from strategies.breakout_module import BreakoutModule
from strategies.volatility_module import VolatilityModule
from strategies.meta_strategy import MetaStrategyEnsemble


def load_env():
    candidates = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'),
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'),
        '.env'
    ]
    env_path = next((p for p in candidates if os.path.exists(p)), None)
    if env_path:
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    os.environ[k.strip()] = v.strip()


class QuantumBotEngine:
    def __init__(self, config_dir: str):
        load_env()

        with open(os.path.join(config_dir, 'settings.yaml'), 'r') as f:
            self.settings = yaml.safe_load(f)
        with open(os.path.join(config_dir, 'symbols.yaml'), 'r') as f:
            self.symbols_cfg = yaml.safe_load(f)

        env_mode = self.settings['app'].get('environment', 'demo').lower()
        exchange_name = self.settings['app'].get('exchange', 'bingx').lower()

        # P0.2 — AISLAMIENTO ESTRICTO DE ENTORNO (DEVELOPMENT != PAPER != LIVE)
        if env_mode in ('live', 'real'):
            allow_live = os.getenv('ALLOW_LIVE_TRADING', 'false').lower() == 'true'
            if not allow_live:
                raise PermissionError("🚨 [CANDADO P0.2] Para ejecutar en MODO REAL debes configurar ALLOW_LIVE_TRADING=true en tu archivo .env")

        use_demo = env_mode == 'demo'

        if not use_demo:
            raise PermissionError("Esta versión auditada está bloqueada a Bybit Demo. La promoción a real requiere una nueva revisión.")

        # Selección de Exchange (BingX / Bybit) y Entorno (Demo / Real)
        if exchange_name == 'bybit':
            if use_demo:
                self.api_key    = os.getenv('BYBIT_API_KEY')
                self.secret_key = os.getenv('BYBIT_SECRET_KEY')
            else:
                self.api_key    = os.getenv('BYBIT_REAL_API_KEY') or os.getenv('BYBIT_API_KEY')
                self.secret_key = os.getenv('BYBIT_REAL_SECRET_KEY') or os.getenv('BYBIT_SECRET_KEY')

            self.executor = AsyncBybitExecutor(self.api_key, self.secret_key, use_testnet=use_demo)
        else:
            self.api_key    = os.getenv('BINGX_API_KEY')
            self.secret_key = os.getenv('BINGX_SECRET_KEY')
            self.executor   = AsyncBingXExecutor(self.api_key, self.secret_key, use_vst=use_demo)

        # Componentes Principales
        self.db_manager    = QuantDatabaseManager()
        self.fetcher       = MultiTimeframeFetcher()
        self.regime_det    = MarketRegimeDetector()
        self.pa_engine     = PriceActionConfirmationEngine(min_wick_ratio=0.55)
        self.metrics_eng   = QuantitativeMetricsEngine()
        self.ml_guard      = SupervisedMLGuard(min_probability=self.settings['score']['min_ml_probability'])
        self.risk_manager  = QuantumRiskManager(
            base_margin_usd=self.settings['risk']['margin_per_asset'],
            leverage=self.settings['risk']['trade_leverage'],
            max_risk_per_trade_pct=self.settings['risk']['max_risk_per_trade_pct'],
            max_daily_loss_pct=self.settings['risk']['max_daily_loss_pct'],
            max_drawdown_pct=self.settings['risk']['max_drawdown_pct'],
            use_half_kelly=self.settings['risk']['use_half_kelly']
        )
        self.port_manager  = PortfolioManager(max_correlation=self.settings['risk']['max_correlation'])
        self.pos_manager   = QuantumPositionManager(getattr(self.executor, 'client', None), db_manager=self.db_manager)
        self.reconciler    = ExchangeStateReconciler(getattr(self.executor, 'client', None), db_manager=self.db_manager)
        self.dashboard     = TerminalDashboard()
        self.calibrator    = StrategyAutoCalibrator()

        # P0.5 — Reconciliación al Iniciar
        if getattr(self.executor, 'client', None):
            self.reconciler.reconcile_state()

        # Módulos del Ensemble (9 Estrategias)
        self.strategy_modules = [
            OracleFibonacciDCAModule(),
            BlackEaglesCapModule(),
            Bot23OxfordModule(),
            Bot22FVGModule(),
            SMCOrderBlockModule(),
            VWAPVolumeModule(),
            MeanReversionModule(),
            BreakoutModule(),
            VolatilityModule()
        ]
        self.ensemble = MetaStrategyEnsemble(
            weights=self.calibrator.weights,
            min_execution_score=self.settings['score']['min_execution_score']
        )
        self.day_start_equity = None
        self.peak_equity = None

    async def run_cycle(self):
        # 1. Obtener balance y posiciones activas del Exchange seleccionado
        equity = await self.executor.get_account_balance()
        active_positions = await self.executor.get_active_positions()
        if equity <= 0:
            raise RuntimeError("Equity no disponible; ciclo bloqueado")
        if self.day_start_equity is None:
            self.day_start_equity = equity
        self.peak_equity = max(self.peak_equity or equity, equity)
        daily_loss_pct = max(0.0, (self.day_start_equity - equity) / self.day_start_equity * 100.0)
        drawdown_pct = max(0.0, (self.peak_equity - equity) / self.peak_equity * 100.0)
        slots_remaining = max(0, self.settings['risk']['max_open_positions'] - len(active_positions))

        # 2. Gestionar Cierres Parciales (1:1 R:R) y Breakeven si aplica
        if hasattr(self.pos_manager, 'manage_open_positions') and self.pos_manager.client:
            await self.pos_manager.manage_open_positions(active_positions)

        self.dashboard.print_header(f"{self.settings['app']['exchange'].upper()} ({self.settings['app']['environment'].upper()})", equity)

        evaluations = []
        prices_cache = {}

        # 3. Descargar datos y procesar activos en paralelo
        symbols_list = self.symbols_cfg['symbols']
        fetch_tasks  = [self.fetcher.fetch_symbol_data(s['yf_symbol']) for s in symbols_list]
        all_data     = await asyncio.gather(*fetch_tasks)

        for s_info, data in zip(symbols_list, all_data):
            yf_sym = s_info['yf_symbol']
            bx_sym = s_info['bingx_symbol']
            trade_sym = bx_sym.replace('-', '') if self.settings['app']['exchange'].lower() == 'bybit' else bx_sym

            if not data or '1h' not in data:
                continue

            df15m = data.get('15m')
            if df15m is not None:
                prices_cache[trade_sym] = df15m

            # A. Clasificar Régimen de Mercado (7 estados)
            regime = self.regime_det.analyze_regime(yf_sym, data['1h'])

            # B. Generar Señales de los 9 Módulos con Confianza (0-100)
            signals = []
            for mod in self.strategy_modules:
                sig = mod.generate_signal(yf_sym, data)
                if sig:
                    signals.append(sig)

            # C. Evaluar Meta-Strategy Ensemble
            score = self.ensemble.evaluate_ensemble(yf_sym, signals, regime)

            # D. Evaluar Guardián Supervisado ML
            atr_pct = regime.atr_percent
            adx_val = regime.adx_value
            bb_bw   = regime.bb_bandwidth

            ml_ok, ml_prob, ml_reason = self.ml_guard.evaluate_signal_gate(
                yf_sym, score.direction.value, score.total_score, adx_val, atr_pct, bb_bw
            )

            # E. EVALUAR FILTRO DE ACCIÓN DEL PRECIO (Price Action Confirmation)
            pa_ok, pa_pattern, pa_score = self.pa_engine.evaluate_price_action(df15m, score.direction.value)

            # F. Evaluar Gestión de Riesgo & Kill Switch
            curr_price = float(data['1h']['Close'].iloc[-2]) if not data['1h'].empty else 0.0
            atr_val    = curr_price * (atr_pct / 100.0)
            risk_dec   = self.risk_manager.calculate_risk_decision(
                trade_sym, score.direction, curr_price, atr_val, score, ml_prob,
                current_daily_loss_pct=daily_loss_pct,
                current_drawdown_pct=drawdown_pct,
                account_equity=equity,
                reward_risk_ratio=self.settings['risk']['risk_reward_ratio']
            )

            if slots_remaining <= 0:
                risk_dec.is_allowed = False
                risk_dec.reason = "Rechazado: máximo de posiciones abiertas alcanzado"

            if not ml_ok:
                risk_dec.is_allowed = False
                risk_dec.reason = ml_reason

            # Exigir confirmación de Acción del Precio si hay intento de dirección LONG/SHORT
            if risk_dec.is_allowed and score.direction != Direction.NEUTRAL and not pa_ok:
                risk_dec.is_allowed = False
                risk_dec.reason = f"Rechazado por Acción del Precio: {pa_pattern}"

            # G. Evaluar Filtro de Correlación
            if risk_dec.is_allowed and trade_sym not in active_positions:
                corr_ok, corr_msg = self.port_manager.is_correlation_safe(
                    trade_sym, score.direction, active_positions, prices_cache
                )
                if not corr_ok:
                    risk_dec.is_allowed = False
                    risk_dec.reason = corr_msg

            # H. Registrar en Base de Datos Persistente SQLite
            self.db_manager.save_decision(
                trade_sym, regime.regime.value, score.direction.value,
                score.total_score, ml_prob, risk_dec.is_allowed, risk_dec.reason,
                signals, self.ensemble.weights
            )

            # I. Ejecutar si fue APROBADO por todas las capas
            if risk_dec.is_allowed and trade_sym not in active_positions:
                print(f"🚀 [ENTRADA APRECIADA QUANTUM v3.0 - PA: {pa_pattern}] Orden para {trade_sym} {score.direction.value} (Score {score.total_score:.1f} / ML Prob {ml_prob*100:.1f}%)")
                exec_res = await self.executor.execute_trade_decision(risk_dec)
                if exec_res.get('status') == 'SUCCESS':
                    slots_remaining -= 1
                    active_positions[trade_sym] = {'symbol': trade_sym, 'size': exec_res.get('filled_qty', 0)}
                    self.db_manager.save_trade_execution({
                        "symbol": trade_sym, "direction": score.direction.value,
                        "entry_price": float(exec_res.get('avg_price') or curr_price),
                        "quantity": float(exec_res.get('filled_qty') or risk_dec.quantity),
                        "leverage": risk_dec.leverage, "status": "FILLED_CONFIRMED"
                    })

            evaluations.append({
                "symbol": yf_sym,
                "regime": regime,
                "score": score,
                "ml_prob": ml_prob,
                "decision": risk_dec
            })

        self.dashboard.print_market_scan(evaluations)
        self.dashboard.print_footer()

    async def start(self, interval_seconds: int = 300):
        print(f"Starting QuantumBot Pro v3.0 Platform Daemon (Exchange: {self.settings['app']['exchange'].upper()} | Env: {self.settings['app']['environment'].upper()})...")
        while True:
            try:
                await self.run_cycle()
            except Exception as e:
                print(f"[!] Exception in main engine loop: {e}")
            await asyncio.sleep(interval_seconds)


if __name__ == '__main__':
    config_directory = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config')
    bot = QuantumBotEngine(config_directory)
    asyncio.run(bot.run_cycle())
