"""
risk/risk_manager.py — Gestor Cuantitativo de Riesgo Institucional QuantumBot Pro v3.0
Sizing conservador con costos estimados y límites de pérdida.
La probabilidad ML no está calibrada: no se usa para aumentar el presupuesto.
Este cálculo no habilita operaciones ni garantiza un límite ante gaps.
"""

import math
from typing import Dict, Any, Optional
from core.models import Direction, RiskDecision, ScoreBreakdown
from risk.kill_switch import EmergencyKillSwitch


def finite_number(value):
    return type(value) in (int, float) and math.isfinite(value)


class QuantumRiskManager:
    def __init__(self, base_margin_usd: float = 25.0, leverage: int = 3,
                 max_risk_per_trade_pct: float = 0.0025, use_half_kelly: bool = True,
                 max_daily_loss_pct: float = 1.0, max_drawdown_pct: float = 8.0):

        if type(leverage) is not int or not 1 <= leverage <= 3:
            raise ValueError("Leverage must be between 1 and 3")
        if not finite_number(max_risk_per_trade_pct) or not 0 < max_risk_per_trade_pct <= 0.0025:
            raise ValueError("Risk budget must be positive and at most 0.25%")
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
        invalid_reason = None
        if not score.is_approved or score.direction != direction:
            invalid_reason = "Score no aprobado o dirección inconsistente"
        inputs = (entry_price, atr_price, ml_probability, account_equity, reward_risk_ratio,
                  current_daily_loss_pct, current_drawdown_pct)
        if (not all(finite_number(v) for v in inputs)
                or entry_price <= 0 or atr_price < 0 or account_equity <= 0
                or not 0 <= ml_probability <= 1 or reward_risk_ratio <= 0
                or current_daily_loss_pct < 0 or current_drawdown_pct < 0
                or type(consecutive_losses) is not int or consecutive_losses < 0):
            invalid_reason = "Datos de riesgo incompletos o inválidos"
        if invalid_reason:
            return RiskDecision(
                symbol=symbol, direction=direction, is_allowed=False, quantity=0.0,
                stop_loss_price=0.0, take_profit_price=0.0, leverage=self.leverage,
                reason=invalid_reason, score=score.total_score,
                ml_probability=ml_probability if finite_number(ml_probability) else 0.0,
                suggested_margin_usd=0.0,
            )

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

        if (not all(finite_number(v) for v in (stop_dist, stop_loss, take_profit))
                or stop_dist <= 0 or stop_loss <= 0 or take_profit <= 0
                or stop_loss == entry_price or take_profit == entry_price):
            return RiskDecision(
                symbol=symbol, direction=direction, is_allowed=False, quantity=0.0,
                stop_loss_price=0.0, take_profit_price=0.0, leverage=self.leverage,
                reason="Protección fuera de rango", score=score.total_score,
                ml_probability=ml_probability, suggested_margin_usd=0.0,
            )

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
        sizing_valid = (all(finite_number(v) and v > 0 for v in
                            (quantity, suggested_margin, economic_risk))
                        and economic_risk <= risk_budget * (1 + 1e-12))

        return RiskDecision(
            symbol=symbol,
            direction=direction,
            is_allowed=sizing_valid,
            quantity=quantity if sizing_valid else 0.0,
            stop_loss_price=stop_loss,
            take_profit_price=take_profit,
            leverage=self.leverage,
            reason=(f"Aprobado por Riesgo (Riesgo Económico Est: ${economic_risk:.2f})"
                    if sizing_valid else "Cálculo de tamaño inválido o fuera del presupuesto"),
            score=score.total_score,
            ml_probability=ml_probability,
            suggested_margin_usd=suggested_margin if sizing_valid else 0.0
        )
