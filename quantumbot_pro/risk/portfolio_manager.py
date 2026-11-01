"""
risk/portfolio_manager.py — Gestor de Portafolio & Matriz de Correlación de Cartera
Calcula la correlación entre activos en tiempo real y bloquea sobre-exposiciones.
"""

import pandas as pd
import numpy as np
from typing import Any, Dict, List, Tuple
from core.models import Direction


class PortfolioManager:
    def __init__(self, max_correlation: float = 0.80):
        self.max_correlation = max_correlation

    def is_correlation_safe(
        self,
        target_symbol: str,
        target_direction: Direction,
        active_positions: Dict[str, Any],
        prices_cache: Dict[str, pd.DataFrame]
    ) -> Tuple[bool, str]:
        """
        Verifica la matriz de correlación de Pearson entre activos abiertos.
        Bloquea si la correlación con un activo existente en la misma dirección supera max_correlation.
        """
        if not active_positions:
            return True, "Portafolio libre"

        target_df = prices_cache.get(target_symbol)
        if target_df is None or len(target_df) < 20:
            return True, "Datos insuficientes para correlación — Pase libre"

        target_returns = target_df['Close'].pct_change().dropna()

        for active_sym, pos in active_positions.items():
            if active_sym == target_symbol:
                continue

            active_side = pos.get('positionSide', '')
            active_df  = prices_cache.get(active_sym)

            if active_df is not None and len(active_df) >= 20:
                active_returns = active_df['Close'].pct_change().dropna()

                # Alineación de retornos
                combined = pd.concat([target_returns, active_returns], axis=1).dropna()
                if len(combined) >= 15:
                    corr = float(combined.corr().iloc[0, 1])

                    # Misma dirección + Alta correlación positiva => Sobre-exposición
                    if target_direction.value == active_side and corr >= self.max_correlation:
                        return False, f"Alta Correlación ({corr:.2f} >= {self.max_correlation}) con {active_sym} ({active_side})"

        return True, "Filtro de Correlación OK"
