"""
risk/kill_switch.py — Interruptor de Emergencia (Kill Switch P0.3)
Permite detener inmediatamente todas las nuevas operaciones y cancelar órdenes pendientes ante:
- Comando manual de usuario.
- Superación del Máximo Drawdown Permitido (MAX_DRAWDOWN).
- Superación de la Pérdida Máxima Diaria (MAX_DAILY_LOSS).
- Racha inaceptable de Pérdidas Consecutivas (MAX_CONSECUTIVE_LOSSES).
"""

import os
import sqlite3
import datetime
from typing import Dict, Any, Tuple


class EmergencyKillSwitch:
    def __init__(self, max_daily_loss_pct: float = 5.0, max_drawdown_pct: float = 10.0, max_consecutive_losses: int = 4):
        self.max_daily_loss_pct = max_daily_loss_pct
        self.max_drawdown_pct = max_drawdown_pct
        self.max_consecutive_losses = max_consecutive_losses
        self.manual_kill_active = False

    def activate_manual_kill(self, reason: str = "Interrupción Manual de Emergencia"):
        self.manual_kill_active = True
        print(f"[KILL SWITCH ACTIVADO MANUALMENTE] Motivo: {reason}")

    def deactivate_manual_kill(self):
        self.manual_kill_active = False
        print("[KILL SWITCH DESACTIVADO MANUALMENTE]")

    def evaluate_kill_switch_conditions(self, current_daily_loss_pct: float,
                                        current_drawdown_pct: float,
                                        consecutive_losses: int) -> Tuple[bool, str]:
        """
        P0.3 / P1.5 / P1.6 / P1.7 — Evalúa si se debe gatillar el Kill Switch automático.
        """
        if self.manual_kill_active:
            return True, "Kill Switch Activado Manualmente por Operador"

        if current_daily_loss_pct >= self.max_daily_loss_pct:
            return True, f"Límite de Pérdida Diaria Superado ({current_daily_loss_pct:.2f}% >= {self.max_daily_loss_pct:.2f}%)"

        if current_drawdown_pct >= self.max_drawdown_pct:
            return True, f"Máximo Drawdown de Emergencia Alcanzado ({current_drawdown_pct:.2f}% >= {self.max_drawdown_pct:.2f}%)"

        if consecutive_losses >= self.max_consecutive_losses:
            return True, f"Límite de Pérdidas Consecutivas Alcanzado ({consecutive_losses} >= {self.max_consecutive_losses})"

        return False, "Operación Normal — Sistema Seguro"
