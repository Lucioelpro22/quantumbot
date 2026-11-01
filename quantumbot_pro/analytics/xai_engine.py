"""
analytics/xai_engine.py — Motor de Inteligencia Explicable (Explainable AI Engine)
Genera informes estructurados XAI respondiendo con precisión quirúrgica a:
- ¿Por qué entré / No entré / Cerré?
- ¿Qué estrategia tuvo mayor peso y cuál fue la probabilidad estimada por la IA?
- ¿Cuál era el régimen de mercado?
- ¿Qué indicadores coincidieron y cuáles estuvieron en contra?
"""

import json
import datetime
from typing import Dict, Any, List
from core.models import StrategySignal, ScoreBreakdown, MarketRegimeState, RiskDecision


class ExplainableAIEngine:
    def __init__(self):
        pass

    def generate_trade_audit_log(self, symbol: str, action_type: str, decision: RiskDecision,
                                 score: ScoreBreakdown, regime: MarketRegimeState,
                                 signals: List[StrategySignal], ml_prob: float,
                                 weights: Dict[str, float]) -> Dict[str, Any]:
        """
        Genera un informe explicativo auditables (JSON & Markdown)
        """
        aligned_signals = []
        conflicting_signals = []

        target_dir = decision.direction.value

        for sig in signals:
            sig_dict = {
                "module": sig.module_name,
                "direction": sig.direction.value,
                "confidence": sig.confidence,
                "strength": sig.strength,
                "weight": weights.get(sig.module_name, 0.10),
                "description": sig.description
            }
            if sig.direction.value == target_dir:
                aligned_signals.append(sig_dict)
            else:
                conflicting_signals.append(sig_dict)

        # Encontrar el módulo de mayor impacto
        top_module = "None"
        max_impact = -1.0
        for sig in signals:
            impact = weights.get(sig.module_name, 0.10) * (sig.confidence / 100.0)
            if impact > max_impact:
                max_impact = impact
                top_module = sig.module_name

        audit = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "symbol": symbol,
            "action_type": action_type,  # ENTRY, REJECT, EXIT
            "decision_summary": {
                "is_allowed": decision.is_allowed,
                "direction": decision.direction.value,
                "total_score": score.total_score,
                "ml_probability_percent": round(ml_prob * 100.0, 1),
                "reason": decision.reason
            },
            "market_context": {
                "regime": regime.regime.value,
                "adx_strength": regime.adx_value,
                "atr_percent": regime.atr_percent,
                "bb_bandwidth": regime.bb_bandwidth,
                "is_tradable": regime.is_tradable
            },
            "explainable_breakdown": {
                "why_action_taken": decision.reason,
                "dominant_strategy_module": top_module,
                "aligned_indicators": aligned_signals,
                "conflicting_indicators": conflicting_signals
            }
        }
        return audit

    def format_xai_markdown(self, audit: Dict[str, Any]) -> str:
        """
        Convierte la auditoría XAI en un formato Markdown legible por humanos.
        """
        ds = audit["decision_summary"]
        mc = audit["market_context"]
        eb = audit["explainable_breakdown"]

        md = []
        md.append(f"### 🤖 EXPLAINABLE AI AUDIT REPORT — {audit['symbol']} [{audit['action_type']}]")
        md.append(f"**Decisión:** {'🟢 APROBADA' if ds['is_allowed'] else '🔴 RECHAZADA'} | **Dirección:** {ds['direction']} | **Score:** {ds['total_score']:.1f}/100 | **IA Prob:** {ds['ml_probability_percent']}%")
        md.append(f"**Régimen de Mercado:** `{mc['regime']}` (ADX: {mc['adx_strength']:.1f}, ATR: {mc['atr_percent']:.2f}%)")
        md.append(f"**Justificación:** {eb['why_action_taken']}")
        md.append(f"**Módulo Dominante:** `{eb['dominant_strategy_module']}`")

        if eb['aligned_indicators']:
            md.append("\n**Indicadores Coincidentes (A Favor):**")
            for a in eb['aligned_indicators']:
                md.append(f"  • `{a['module']}` ({a['confidence']:.0f}% Confianza): {a['description']}")

        if eb['conflicting_indicators']:
            md.append("\n**Indicadores en Conflicto (En Contra):**")
            for c in eb['conflicting_indicators']:
                md.append(f"  • `{c['module']}` ({c['confidence']:.0f}% Confianza): {c['description']}")

        return "\n".join(md)
