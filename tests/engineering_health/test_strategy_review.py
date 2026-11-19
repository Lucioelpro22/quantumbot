"""Synthetic arithmetic and boundary regressions; no market data or strategy backtests."""
import ast
import itertools
from pathlib import Path
import socket
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'quantumbot_pro'))
from analytics.strategy_review import EvidenceInvalid, review_closed_trades
from strategies.registry import DEFAULT_WEIGHTS, validate_weights
from strategies.meta_strategy import MetaStrategyEnsemble
from risk.auto_calibrator import StrategyAutoCalibrator
from risk.risk_manager import QuantumRiskManager
from core.models import Direction, MarketRegimeState, RegimeType, StrategySignal, ScoreBreakdown

MODULES = list(DEFAULT_WEIGHTS)
A, B = MODULES[:2]


def forbid_network(*args, **kwargs):
    raise AssertionError('Network forbidden in synthetic strategy tests')


def setUpModule():
    global PATCHES
    PATCHES = [patch.object(socket.socket, 'connect', forbid_network),
               patch.object(socket, 'create_connection', forbid_network),
               patch.object(socket, 'getaddrinfo', forbid_network)]
    for p in PATCHES:
        p.start()


def tearDownModule():
    for p in reversed(PATCHES):
        p.stop()


def trade(**changes):
    return dict(dict(trade_id='one', module_name=A, status='CLOSED', provenance='SYNTHETIC',
                     currency='USD', opened_at='2026-01-01T01:00:00Z',
                     closed_at='2026-01-01T02:00:00Z', gross_pnl_usd='10',
                     fees_usd='2', funding_cost_usd='1', regime='TEST_LABEL'), **changes)


def signal(module=A, **changes):
    return StrategySignal(**dict(dict(module_name=module, symbol='TEST', direction=Direction.LONG,
                              strength=1, confidence=100, timeframe='15m', price=100,
                              atr=1, description='synthetic fixture'), **changes))


def regime(**changes):
    return MarketRegimeState(**dict(dict(symbol='TEST', regime=RegimeType.SIDEWAYS_CHOP,
                                  adx_value=20, atr_percent=1, bb_bandwidth=1,
                                  is_tradable=True, reason='synthetic fixture'), **changes))


def evaluate(signals, weights=None, state=None):
    return MetaStrategyEnsemble(weights=weights).evaluate_ensemble('TEST', signals, state or regime())


class AccountingTests(unittest.TestCase):
    def test_empty_data_is_not_a_balance_or_validation(self):
        report = review_closed_trades([], provenance='DEMO')
        self.assertIsNone(report['account_equity_usd'])
        self.assertFalse(report['strategy_validated'])
        self.assertEqual(len(report['modules']), 9)
        self.assertTrue(all(m['review_status'] == 'NO_DATA' for m in report['modules'].values()))

    def test_costs_funding_credit_and_fill_slippage_not_double_counted(self):
        report = review_closed_trades([trade(funding_cost_usd='-1', slippage_usd='3')], provenance='SYNTHETIC')
        self.assertEqual(report['modules'][A]['net_pnl_usd'], 9)
        self.assertEqual(report['by_regime'][A]['TEST_LABEL']['net_pnl_usd'], 9)
        self.assertFalse(report['strategy_validated'])

    def test_high_win_rate_net_loss_never_promotes_weights(self):
        rows = [trade(trade_id=str(i), gross_pnl_usd=5 if i < 8 else -40,
                      fees_usd=1, funding_cost_usd=0) for i in range(10)]
        calibrator = StrategyAutoCalibrator()
        before = dict(calibrator.weights)
        report = calibrator.review_trade_history(rows, provenance='SYNTHETIC')
        self.assertEqual(report['modules'][A]['win_rate'], 0.8)
        self.assertEqual(report['modules'][A]['net_pnl_usd'], -50)
        self.assertEqual(report['modules'][A]['review_status'], 'REVIEW_NET_LOSS')
        returned = calibrator.calibrate_from_trade_history(rows)
        returned[A] = 1
        self.assertEqual(calibrator.weights, before)

    def test_duplicate_trade_not_counted_twice(self):
        row = trade()
        r = review_closed_trades([row, row.copy()], provenance='SYNTHETIC')
        self.assertEqual(r['duplicate_rows_ignored'], 1)
        self.assertEqual(r['modules'][A]['closed_trades'], 1)

    def test_conflicting_duplicate_rejected(self):
        with self.assertRaises(EvidenceInvalid):
            review_closed_trades([trade(), trade(gross_pnl_usd=100)], provenance='SYNTHETIC')

    def test_missing_cost_not_assumed_zero(self):
        row = trade()
        del row['fees_usd']
        with self.assertRaises(EvidenceInvalid):
            review_closed_trades([row], provenance='SYNTHETIC')

    def test_aggregate_overflow_not_reported_as_profit(self):
        with self.assertRaises(EvidenceInvalid):
            review_closed_trades([trade(trade_id=str(i), gross_pnl_usd='1e308')
                                  for i in range(2)], provenance='SYNTHETIC')

    def test_invalid_attribution_provenance_status_dates_amounts_rejected(self):
        for changes in ({'module_name':'ensemble'}, {'module_name':[]}, {'status':'OPEN'},
                        {'provenance':'DEMO'}, {'currency':'USDT'}, {'fees_usd':-1},
                        {'gross_pnl_usd':'NaN'}, {'gross_pnl_usd':'1e999'},
                        {'closed_at':'2026-01-01'}, {'closed_at':'2025-01-01T00:00:00Z'}):
            with self.subTest(changes=changes), self.assertRaises(EvidenceInvalid):
                review_closed_trades([trade(**changes)], provenance='SYNTHETIC')

    def test_drawdown_is_ordered_closed_pnl_and_days_include_gaps(self):
        rows = [trade(trade_id='b', gross_pnl_usd=-5, fees_usd=0, funding_cost_usd=0,
                      closed_at='2026-01-03T02:00:00Z'),
                trade(trade_id='a', gross_pnl_usd=10, fees_usd=0, funding_cost_usd=0)]
        m = review_closed_trades(rows, provenance='SYNTHETIC')['modules'][A]
        self.assertEqual((m['active_close_days'],m['calendar_span_days']), (2,3))
        self.assertEqual(m['closed_pnl_drawdown_usd'],5)
        self.assertEqual(m['profit_factor'],2)


class ConsensusTests(unittest.TestCase):
    def test_registry_matches_nine_engine_module_constructor_names(self):
        names = set()
        for p in (ROOT/'quantumbot_pro/strategies').glob('*_module.py'):
            for node in ast.walk(ast.parse(p.read_text())):
                if isinstance(node, ast.FunctionDef) and node.name == '__init__':
                    args = node.args.args
                    for arg, default in zip(args[-len(node.args.defaults):], node.args.defaults):
                        if arg.arg == 'name' and isinstance(default, ast.Constant):
                            names.add(default.value)
                if isinstance(node, ast.Call):
                    for k in node.keywords:
                        if k.arg == 'name' and isinstance(k.value, ast.Constant):
                            names.add(k.value.value)
        self.assertEqual(names, set(DEFAULT_WEIGHTS))
        self.assertEqual(StrategyAutoCalibrator().weights, MetaStrategyEnsemble().weights)
        self.assertEqual(DEFAULT_WEIGHTS['VWAP_Volume_Delta'], .08)

    def test_duplicate_module_cannot_manufacture_approval(self):
        one = evaluate([signal()])
        repeated = evaluate([signal()]*20)
        self.assertEqual(one.total_score, repeated.total_score)
        self.assertFalse(repeated.is_approved)

    def test_conflicting_module_abstains(self):
        r = evaluate([signal(),signal(direction=Direction.SHORT)])
        self.assertEqual(r.direction,Direction.NEUTRAL)
        self.assertFalse(r.is_approved)

    def test_unknown_module_other_symbol_and_invalid_signal_ignored(self):
        r = evaluate([signal('unknown'), signal(symbol='OTHER'),
                      signal().model_copy(update={'confidence':float('nan')})])
        self.assertEqual(r.total_score,0)

    def test_regime_bonus_cannot_create_direction(self):
        self.assertEqual(evaluate([], state=regime(regime=RegimeType.BULLISH_TREND)).direction,
                         Direction.NEUTRAL)

    def test_tie_is_neutral_without_long_bias(self):
        r = evaluate([signal(),signal(B,direction=Direction.SHORT)],weights={A:.5,B:.5})
        self.assertEqual(r.direction,Direction.NEUTRAL)

    def test_shared_evidence_counted_once(self):
        r = evaluate([signal(metadata={'evidence_id':'event'}),signal(B,metadata={'evidence_id':'event'})])
        self.assertAlmostEqual(r.total_score,20)
        self.assertEqual(r.contributing_modules,[A])
        self.assertIn(B,r.ignored_modules)

    def test_shared_evidence_with_conflicting_direction_abstains(self):
        r = evaluate([signal(metadata={'evidence_id':'event'}),
                      signal(B,direction=Direction.SHORT,metadata={'evidence_id':'event'})])
        self.assertFalse(r.is_approved)
        self.assertEqual(r.total_score,0)

    def test_permutations_produce_same_consensus(self):
        signals = [signal(), signal(confidence=60), signal(B,direction=Direction.SHORT)]
        outputs = [evaluate(list(p)).model_dump() for p in itertools.permutations(signals)]
        self.assertTrue(all(v == outputs[0] for v in outputs))

    def test_empty_and_zero_weights_have_no_fallback(self):
        self.assertEqual(evaluate([signal()],weights={}).total_score,0)
        self.assertEqual(evaluate([signal()],weights={A:0}).total_score,0)

    def test_weight_update_never_normalizes_unused_budget(self):
        e = MetaStrategyEnsemble()
        e.update_weights({A:.2})
        self.assertEqual(e.weights,{A:.2})
        for w in ({A:1,B:1},{'unknown':.1},{A:float('nan')},{A:True},{A:-.1}):
            with self.subTest(w=w), self.assertRaises(ValueError):
                validate_weights(w)

    def test_invalid_or_nontradable_regime_blocks(self):
        for state in (regime(symbol='OTHER'),regime(is_tradable=False),regime(adx_value=float('nan'))):
            self.assertFalse(evaluate([signal(m) for m in MODULES],state=state).is_approved)

    def test_valid_synthetic_consensus_can_approve_without_enabling_execution(self):
        r = evaluate([signal(m) for m in MODULES])
        self.assertTrue(r.is_approved)
        self.assertAlmostEqual(r.total_score,100)
        from operational_policy import require_operational_access, OperationalBlocked
        with self.assertRaises(OperationalBlocked):
            require_operational_access('demo')


class RiskBoundaryTests(unittest.TestCase):
    def decide(self, **changes):
        kwargs = dict(symbol='TEST', direction=Direction.LONG, entry_price=100, atr_price=1,
                      score=ScoreBreakdown(symbol='TEST', direction=Direction.LONG,
                                           total_score=90,is_approved=True),
                      ml_probability=.8,account_equity=1000)
        kwargs.update(changes)
        return QuantumRiskManager().calculate_risk_decision(**kwargs)

    def test_rejected_score_blocks_sizing(self):
        r = self.decide(score=ScoreBreakdown(symbol='TEST',direction=Direction.LONG,total_score=20))
        self.assertFalse(r.is_allowed)
        self.assertEqual(r.quantity,0)

    def test_direction_mismatch_blocks_sizing(self):
        self.assertFalse(self.decide(direction=Direction.SHORT).is_allowed)

    def test_invalid_equity_probability_and_overflow_fail_closed(self):
        for changes in ({'account_equity':0},{'account_equity':float('nan')}, {'account_equity':None},
                        {'ml_probability':'bad'},{'ml_probability':1.1},{'atr_price':1e308},
                        {'consecutive_losses':-1},{'entry_price':True}):
            with self.subTest(changes=changes):
                self.assertFalse(self.decide(**changes).is_allowed)

    def test_leverage_and_risk_budget_cannot_exceed_caps(self):
        for changes in ({'leverage':25},{'leverage':True},{'max_risk_per_trade_pct':.01}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                QuantumRiskManager(**changes)

    def test_small_prices_preserve_stop_and_economic_budget(self):
        r = self.decide(entry_price=.00012345, atr_price=.000001)
        self.assertTrue(r.is_allowed)
        self.assertGreater(r.stop_loss_price,0)
        risk = QuantumRiskManager().calculate_account_economic_risk(.00012345,r.stop_loss_price,r.quantity)
        self.assertLessEqual(risk, 2.5 + 1e-10)

    def test_daily_loss_boundary_stops_approval(self):
        self.assertFalse(self.decide(current_daily_loss_pct=1).is_allowed)

    def test_subnormal_price_cannot_create_zero_distance_protection(self):
        self.assertFalse(self.decide(entry_price=5e-324,atr_price=0).is_allowed)
