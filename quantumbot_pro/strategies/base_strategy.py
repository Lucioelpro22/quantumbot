"""
strategies/base_strategy.py — Interfaz Abstracta para Módulos de Estrategia
"""

from abc import ABC, abstractmethod
import pandas as pd
from typing import Dict, Optional
from core.models import StrategySignal


class BaseStrategyModule(ABC):
    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def generate_signal(self, yf_symbol: str, data: Dict[str, pd.DataFrame]) -> Optional[StrategySignal]:
        """Genera una señal cuantitativa basada en los datos multi-temporalidad."""
        pass
