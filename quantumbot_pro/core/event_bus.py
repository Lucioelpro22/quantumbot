"""
core/event_bus.py — Bus de Eventos Asincrónico para QuantumBot Pro v1.0
Permite una arquitectura desacoplada basada en eventos (Event-Driven Architecture).
"""

import asyncio
from typing import Callable, Dict, List, Any


class EventBus:
    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = {}

    def subscribe(self, event_type: str, handler: Callable):
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(handler)

    async def publish(self, event_type: str, data: Any):
        if event_type in self._subscribers:
            tasks = []
            for handler in self._subscribers[event_type]:
                if asyncio.iscoroutinefunction(handler):
                    tasks.append(handler(data))
                else:
                    handler(data)
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)


# Instancia global del Event Bus
event_bus = EventBus()
