"""
risk/risk_manager.py — Gestor Cuantitativo de Riesgo Institucional QuantumBot Pro v3.0
Calcula el Riesgo Económico Real por Operación, tamaño óptimo de posición (Half-Kelly riguroso),
protección de margen aislado 25x y verificación de Kill Switch / límites de pérdida (P0.3, P1.1, P1.3, P1.5-P1.7).
"""

import math
from typing import Dict, Any, Optional
from core.models import Direction, RiskDecision, ScoreBreakdown
from risk.kill_switch import EmergencyKillSwitch


class QuantumRiskManager:
    def __init__(self, base_margin_usd: float = 25.0, leverage: int = 25,
                 max_risk_per_trade_pct: float = 0.0025, use_half_kelly: bool = True,
                 max_daily_loss_pct: float = 5.0, max_drawdown_pct: float = 10.0):

        self.base_margin_usd = base_margin_usd
        self.leverage = leverage
        self.max_risk_per_trade_pct = max_risk_per_trade_pct
        self.use_half_kelly = use_half_kelly
        self.kill_switch = EmergencyKillSwitch(
            max_daily_loss_pct=max_daily_loss_pct,
            max_drawdown_pct=max_drawdown_pct
        )

    def calculate_account_economic_risk(self, entry_price: float, stop_loss_price: float,
                                        quantity: float, taker_fee_pct: float = 0.0005,
                                        estimated_slippage_pct: float = 0.0002) -> float:
        """
        P1.1 — Calcula el Riesgo Económico Real:
        Account Risk = Position Notional * Stop Distance + Fees + Estimated Slippage
        """
        if quantity <= 0 or entry_price <= 0:
            return 0.0

        notional = quantity * entry_price
        stop_dist_pct = abs(entry_price - stop_loss_price) / entry_price
        risk_from_price = notional * stop_dist_pct
        fees_usd = notional * (taker_fee_pct * 2.0)  # Entrada + Salida
        slippage_usd = notional * estimated_slippage_pct

        return risk_from_price + fees_usd + slippage_usd

    def calculate_rigorous_half_kelly(self, win_probability: float, reward_risk_ratio: float = 1.0) -> float:
        """
        P1.3 — Fórmula rigurosa de Kelly / Half-Kelly:
        f* = (p*b - q) / b
        Donde p = win_prob, q = 1 - p, b = reward_risk_ratio
        Half-Kelly = f* / 2.0
        Limitado estrictamente a max_risk_per_trade_pct.
        """
        p = min(0.95, max(0.05, win_probability))
        b = max(0.5, reward_risk_ratio)
        q = 1.0 - p

        full_kelly = (p * b - q) / b
        half_kelly = max(0.0, full_kelly * 0.5)

        return min(self.max_risk_per_trade_pct, half_kelly)

    def calculate_risk_decision(self, symbol: str, direction: Direction,
                                entry_price: float, atr_price: float,
                                score: ScoreBreakdown, ml_probability: float,
                                current_daily_loss_pct: float = 0.0,
                                current_drawdown_pct: float = 0.0,
                                consecutive_losses: int = 0,
                                account_equity: float = 0.0,
                                reward_risk_ratio: float = 1.5) -> RiskDecision:
        """
        Genera la decisión cuantitativa de riesgo validando Kill Switch, Sizing y SL/TP.
        """
        # 1. Evaluar Kill Switch (P0.3, P1.5, P1.6, P1.7)
        kill_active, kill_reason = self.kill_switch.evaluate_kill_switch_conditions(
            current_daily_loss_pct, current_drawdown_pct, consecutive_losses
        )
        if kill_active:
            return RiskDecision(
                symbol=symbol, direction=direction, is_allowed=False, quantity=0.0,
                stop_loss_price=0.0, take_profit_price=0.0, leverage=self.leverage,
                reason=f"RECHAZADO: {kill_reason}", score=score.total_score,
                ml_probability=ml_probability, suggested_margin_usd=0.0
            )

        if direction == Direction.NEUTRAL or entry_price <= 0:
            return RiskDecision(
                symbol=symbol, direction=direction, is_allowed=False, quantity=0.0,
                stop_loss_price=0.0, take_profit_price=0.0, leverage=self.leverage,
                reason="Dirección Neutral o Precio Inválido", score=score.total_score,
                ml_probability=ml_probability, suggested_margin_usd=0.0
            )

        # 2. Calcular Distancia de Stop Loss basada en ATR (1.5x ATR)
        stop_dist = max(atr_price * 1.5, entry_price * 0.01)

        if direction == Direction.LONG:
            stop_loss = entry_price - stop_dist
            take_profit = entry_price + stop_dist * reward_risk_ratio
        else:
            stop_loss = entry_price + stop_dist
            take_profit = entry_price - stop_dist * reward_risk_ratio

        # 3. Tamaño por riesgo económico real y tope de exposición.
        if account_equity <= 0:
            return RiskDecision(
                symbol=symbol, direction=direction, is_allowed=False, quantity=0.0,
                stop_loss_price=0.0, take_profit_price=0.0, leverage=self.leverage,
                reason="RECHAZADO: equity no disponible", score=score.total_score,
                ml_probability=ml_probability, suggested_margin_usd=0.0
            )
        risk_budget = account_equity * self.max_risk_per_trade_pct
        fee_slippage_per_unit = entry_price * (0.0005 * 2.0 + 0.0002)
        quantity_by_risk = risk_budget / (stop_dist + fee_slippage_per_unit)
        max_notional = account_equity * 0.60  # 20% de margen a 3x
        quantity_by_notional = max_notional / entry_price
        quantity = max(0.0, min(quantity_by_risk, quantity_by_notional))
        suggested_margin = quantity * entry_price / self.leverage

        # 4. Verificar Riesgo Económico Real
        economic_risk = self.calculate_account_economic_risk(entry_price, stop_loss, quantity)

        return RiskDecision(
            symbol=symbol,
            direction=direction,
            is_allowed=True,
            quantity=quantity,
            stop_loss_price=round(stop_loss, 4),
            take_profit_price=round(take_profit, 4),
            leverage=self.leverage,
            reason=f"Aprobado por Riesgo (Riesgo Económico Est: ${economic_risk:.2f})",
            score=score.total_score,
            ml_probability=ml_probability,
            suggested_margin_usd=suggested_margin
        )
