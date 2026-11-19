"""Descriptive closed-trade accounting, not alpha testing or certification.

Input gross PnL uses ACTUAL fill prices, so execution slippage is already in it.
Subtract commissions and signed funding costs exactly once; do not subtract
slippage again. No implicit zero costs, USD conversion or allocation to voters.
"""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from collections import defaultdict
import math

from strategies.registry import DEFAULT_WEIGHTS


class EvidenceInvalid(ValueError):
    pass


def amount(value):
    try:
        if isinstance(value, bool):
            raise ValueError()
        result = Decimal(str(value))
        if not result.is_finite() or not math.isfinite(float(result)):
            raise ValueError()
        return result
    except (ValueError, InvalidOperation, TypeError) as exc:
        raise EvidenceInvalid('Missing or non-finite monetary amount') from exc


def timestamp(value):
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            raise ValueError()
        return parsed.astimezone(timezone.utc)
    except (AttributeError, TypeError, ValueError) as exc:
        raise EvidenceInvalid('Timezone-aware execution timestamps required') from exc


def finite_float(value):
    result = float(value)
    if not math.isfinite(result):
        raise EvidenceInvalid('Aggregate monetary metric exceeds finite report range')
    return result


def metrics(trades):
    pnl = [t['net'] for t in trades]
    wins = sum((v for v in pnl if v > 0), Decimal(0))
    losses = -sum((v for v in pnl if v < 0), Decimal(0))
    cumulative = peak = drawdown = Decimal(0)
    for trade in sorted(trades, key=lambda t: (t['closed'], t['id'])):
        cumulative += trade['net']
        peak = max(peak, cumulative)
        drawdown = max(drawdown, peak - cumulative)
    net = sum(pnl, Decimal(0))
    days = {t['closed'].date() for t in trades}
    span = ((max(days) - min(days)).days + 1) if days else 0
    return {
        'closed_trades': len(pnl), 'active_close_days': len(days), 'calendar_span_days': span,
        'gross_pnl_usd': finite_float(sum((t['gross'] for t in trades), Decimal(0))),
        'fees_usd': finite_float(sum((t['fees'] for t in trades), Decimal(0))),
        'funding_cost_usd': finite_float(sum((t['funding'] for t in trades), Decimal(0))),
        'net_pnl_usd': finite_float(net),
        'win_rate': sum(v > 0 for v in pnl) / len(pnl) if pnl else None,
        'mean_net_pnl_usd': finite_float(net / len(pnl)) if pnl else None,
        'profit_factor': finite_float(wins / losses) if losses else None,
        'profit_factor_reason': None if losses else 'NO_OBSERVED_LOSSES_OR_NO_TRADES',
        'closed_pnl_drawdown_usd': finite_float(drawdown),
        'review_status': ('NO_DATA' if not pnl else 'REVIEW_NET_LOSS' if net < 0
                          else 'DESCRIPTIVE_ONLY_NOT_VALIDATED'),
    }


def review_closed_trades(rows, *, provenance):
    """Read provided records in memory; never opens files or changes weights.

    Each input must represent one fully CLOSED, individually attributed module
    trade. Ensemble trades without independent attribution are rejected instead
    of copying their PnL to every contributing module. DEMO and SYNTHETIC cannot
    be mixed. Account equity is not inferred from PnL or test capital.
    """
    if provenance not in ('SYNTHETIC', 'DEMO'):
        raise EvidenceInvalid('Explicit SYNTHETIC or DEMO provenance required')
    grouped = {name: [] for name in DEFAULT_WEIGHTS}
    by_regime = defaultdict(list)
    seen = {}
    duplicates = 0
    for row in rows:
        if not isinstance(row, dict):
            raise EvidenceInvalid('Trade must be a record')
        required = {'trade_id', 'module_name', 'status', 'provenance', 'currency',
                    'opened_at', 'closed_at', 'gross_pnl_usd', 'fees_usd', 'funding_cost_usd'}
        if required - row.keys():
            raise EvidenceInvalid('Trade attribution, costs or timestamps missing')
        key = row['trade_id']
        module = row['module_name']
        if (not isinstance(key, str) or not key or not isinstance(module, str)
                or module not in grouped):
            raise EvidenceInvalid('Unknown trade identity or module attribution')
        if row['status'] != 'CLOSED' or row['provenance'] != provenance or row['currency'] != 'USD':
            raise EvidenceInvalid('Trade is open, mixed-provenance or not denominated in USD')
        opened, closed = timestamp(row['opened_at']), timestamp(row['closed_at'])
        if closed < opened:
            raise EvidenceInvalid('Close precedes open')
        gross, fees, funding = (amount(row[k]) for k in ('gross_pnl_usd', 'fees_usd', 'funding_cost_usd'))
        if fees < 0:
            raise EvidenceInvalid('Commission cost cannot be negative in this schema')
        regime = row.get('regime', 'UNKNOWN')
        if not isinstance(regime, str) or not regime:
            raise EvidenceInvalid('Regime label invalid')
        trade = dict(id=key, module=module, opened=opened, closed=closed, gross=gross,
                     fees=fees, funding=funding, net=gross-fees-funding, regime=regime)
        if key in seen:
            if seen[key] != trade:
                raise EvidenceInvalid('Conflicting duplicate trade ID')
            duplicates += 1
            continue
        seen[key] = trade
        grouped[module].append(trade)
        by_regime[(module, regime)].append(trade)
    return {
        'schema_version': 1, 'provenance': provenance,
        'evaluation': 'DESCRIPTIVE_ACCOUNTING_ONLY', 'strategy_validated': False,
        'account_equity_usd': None, 'account_equity_status': 'NOT_OBSERVED',
        'duplicate_rows_ignored': duplicates,
        'modules': {name: metrics(trades) for name, trades in grouped.items()},
        'by_regime': {name: {regime: metrics(trades) for (module, regime), trades in sorted(by_regime.items())
                            if module == name} for name in grouped},
        'limits': ['Closed-trade PnL only; no mark-to-market equity or open-position drawdown',
                   'No selection of winning regimes or automatic promotion',
                   'No statistical independence, significance or future profitability claim',
                   'Aggregate account PnL cannot establish individual module contribution'],
    }
