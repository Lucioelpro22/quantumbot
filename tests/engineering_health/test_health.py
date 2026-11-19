"""Synthetic-only regression suite. No trading loop, market fixtures or credentials.

Run: python -B -m unittest discover -s tests/engineering_health -v
"""
import ast
import asyncio
import contextlib
import copy
import importlib
import io
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch, AsyncMock
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'quantumbot_pro'))
from operational_policy import OperationalBlocked, health_snapshot
from bybit_client import BybitClient
from bingx_client import BingXClient
from execution.bybit_executor import AsyncBybitExecutor, ExchangeStateUnknown
from risk.checkpoint import RiskCheckpoint, RiskStateUnknown
from database.db_manager import QuantDatabaseManager
import cli


# If a regression attempts actual network I/O, fail instead of contacting a service.
def forbid_network(*args, **kwargs):
    raise AssertionError('Network forbidden in engineering regression suite')


def setUpModule():
    global NETWORK_PATCHES
    NETWORK_PATCHES = [patch.object(socket.socket, 'connect', forbid_network),
                       patch.object(socket, 'create_connection', forbid_network),
                       patch.object(socket, 'getaddrinfo', forbid_network)]
    for item in NETWORK_PATCHES:
        item.start()


def tearDownModule():
    for item in reversed(NETWORK_PATCHES):
        item.stop()


def response(rows, cursor=''):
    return {'retCode': 0, 'result': {'list': rows, 'nextPageCursor': cursor}}


def position(**changes):
    return dict(symbol='BTCUSDT', size='0.10', side='Buy', positionIdx=1,
                stopLoss='90', takeProfit='120', positionStatus='Normal', **changes)


class FakeExchange:
    def __init__(self):
        self.positions = response([position()])
        self.order = dict(symbol='BTCUSDT', orderId='order-1', orderStatus='Filled',
                          cumExecQty='0.10', avgPrice='100')
        self.instrument = response([{'symbol': 'BTCUSDT', 'lotSizeFilter': {
            'qtyStep': '0.05', 'minOrderQty': '0.05', 'maxMktOrderQty': '10'}}])
        self.calls = []
        self.fail_create = False
        self.protection_code = 0

    def get_positions(self, **kwargs):
        return copy.deepcopy(self.positions)

    def get_instrument(self, symbol):
        return copy.deepcopy(self.instrument)

    def get_order(self, symbol, order_id):
        return response([copy.deepcopy(self.order)])

    def setup_symbol(self, *args, **kwargs):
        return {'retCode': 0}

    def request(self, method, path, params):
        self.calls.append((method, path, copy.deepcopy(params)))
        if path == '/v5/order/create':
            if self.fail_create:
                raise TimeoutError('synthetic timeout after possible acceptance')
            return {'retCode': 0, 'result': {'orderId': 'order-1'}}
        return {'retCode': self.protection_code}


def executor(fake=None):
    # Never construct a production client or weaken the application policy.
    obj = object.__new__(AsyncBybitExecutor)
    obj.reconciliation_required = False
    obj.client = fake or FakeExchange()
    return obj


def decision(**changes):
    value = dict(is_allowed=True, symbol='BTC-USDT', direction=SimpleNamespace(value='LONG'),
                 leverage=3, stop_loss_price=90, take_profit_price=120, quantity=0.10, reason='fixture')
    value.update(changes)
    return SimpleNamespace(**value)


class PolicyTests(unittest.TestCase):
    def test_all_operational_modes_denied_even_with_environment_flags(self):
        with patch.dict(os.environ, {'ALLOW_LIVE_TRADING': 'true', 'ENVIRONMENT': 'demo'}):
            for mode in ('live', 'demo', 'paper', 'shadow', 'backtest', 'walkforward',
                         'montecarlo', 'stress', 'crisis', 'research', 'xai'):
                with self.subTest(mode=mode), contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(cli.main(['--mode', mode]), 2)

    def test_status_is_metadata_only(self):
        with patch('builtins.open', side_effect=AssertionError('unexpected file read')):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(cli.main([]), 0)
            self.assertEqual(json.loads(output.getvalue()), health_snapshot())
            self.assertEqual(health_snapshot()['runtime'], 'UNKNOWN')

    def test_direct_clients_deny_all_environment_combinations(self):
        for demo in (True, False):
            for testnet in (True, False):
                with self.assertRaises(OperationalBlocked):
                    BybitClient('fixture', 'fixture', use_demo=demo, use_testnet=testnet)
        with self.assertRaises(OperationalBlocked):
            BingXClient('fixture', 'fixture', use_vst=False)

    def test_transport_denies_even_without_constructor(self):
        for cls in (BybitClient, BingXClient):
            for method in ('GET', 'POST'):
                with self.assertRaises(OperationalBlocked):
                    object.__new__(cls).request(method, '/v5/order/create', {})

    def test_engine_denies_before_configuration_or_credentials(self):
        from main import QuantumBotEngine, load_env
        with patch('builtins.open', side_effect=AssertionError('file access')):
            with self.assertRaises(OperationalBlocked):
                QuantumBotEngine('/nonexistent')
            with self.assertRaises(OperationalBlocked):
                load_env()
            with self.assertRaises(OperationalBlocked):
                asyncio.run(object.__new__(QuantumBotEngine).run_cycle())

    def test_scheduler_and_tools_deny_before_any_io(self):
        for name, attr in (('scheduler_quantumbot', 'main'), ('bybit_smoke_test', 'main'),
                           ('oxford_crypto_validation', 'main'), ('price_alert_daemon', 'main_loop')):
            module = importlib.import_module(name)
            function = getattr(module, attr)
            with patch('builtins.open', side_effect=AssertionError('file access')):
                with self.assertRaises(OperationalBlocked):
                    result = function()
                    if asyncio.iscoroutine(result):
                        asyncio.run(result)

    def test_profitability_does_not_read_ledger_or_collect(self):
        import demo_profitability
        with patch.object(Path, 'open', side_effect=AssertionError('ledger read')):
            with self.assertRaises(OperationalBlocked):
                demo_profitability.evaluate(Path('forbidden.csv'))
            with self.assertRaises(OperationalBlocked):
                demo_profitability.collect(FakeExchange())

    def test_production_db_is_never_opened(self):
        with patch('sqlite3.connect', side_effect=AssertionError('db opened')):
            for path in (None, 'database/quantumbot.db', 'file::memory:?cache=shared'):
                with self.assertRaises(OperationalBlocked):
                    QuantDatabaseManager(path)

    def test_memory_adapter_handles_quotes_and_deduplicates(self):
        db = QuantDatabaseManager(':memory:')
        self.addCleanup(db.close)
        for _ in range(2):
            db.set_position_partial_closed("position';DROP TABLE partials;--", 'BTC', 'LONG', 100)
        self.assertEqual(len(db.get_partial_closed_positions()), 1)
        db.save_decision('BTC', 'fixture', 'LONG', 90, 0.8, False, "can't trade", [], {})
        self.assertEqual(db.get_recent_decisions()[0]['reason'], "can't trade")
        db.save_trade_execution({'status': 'SYNTHETIC'})

    def test_guarded_research_methods_stop_before_input_processing(self):
        # AST verifies first executable statement without importing research code.
        targets = {'backtesting/backtest_engine.py': 'run_backtest',
                   'backtesting/walk_forward.py': 'run_walk_forward',
                   'backtesting/stress_test.py': 'run_stress_test',
                   'backtesting/monte_carlo.py': 'run_simulation',
                   'research/auto_research.py': 'run_optimization_experiment',
                   'core/data_fetcher.py': 'fetch_symbol_data',
                   'strategies/oxford_daily_ma.py': 'evaluate_oxford'}
        for path, method in targets.items():
            tree = ast.parse((ROOT / 'quantumbot_pro' / path).read_text())
            node = next(n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == method)
            body = node.body
            if isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                body = body[1:]
            self.assertEqual(body[0].value.func.id, 'require_operational_access', path)


class ExecutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_empty_positions_is_distinct_from_query_failure(self):
        obj = executor()
        obj.client.positions = response([])
        self.assertEqual(await obj.get_active_positions(), {})
        obj.client.positions = {'retCode': 10000}
        with self.assertRaises(ExchangeStateUnknown):
            await obj.get_active_positions()
        self.assertTrue(obj.reconciliation_required)

    async def test_incomplete_positions_fail_closed(self):
        invalid = [None, {}, {'retCode': 0}, response([], 'next'), response([None]),
                   response([{'size': 'NaN'}]), response([{'size': '-1'}]),
                   response([position(), position()])]
        for value in invalid:
            obj = executor(); obj.client.positions = value
            with self.subTest(value=value), self.assertRaises(ExchangeStateUnknown):
                await obj.get_active_positions()

    async def test_quantity_is_exact_multiple_of_step(self):
        obj = executor()
        self.assertEqual(str(await obj._normalize_quantity('BTCUSDT', 0.129)), '0.10')
        self.assertEqual(await obj._normalize_quantity('BTCUSDT', 0.01), 0)
        self.assertEqual(await obj._normalize_quantity('BTCUSDT', 11), 0)

    async def test_quantity_nan_and_invalid_metadata_rejected(self):
        obj = executor()
        with self.assertRaises(ExchangeStateUnknown):
            await obj._normalize_quantity('BTCUSDT', float('nan'))
        obj.client.instrument['result']['list'][0]['lotSizeFilter']['qtyStep'] = '0'
        with self.assertRaises(ExchangeStateUnknown):
            await obj._normalize_quantity('BTCUSDT', 0.1)

    async def test_full_fill_requires_correct_protection(self):
        obj = executor()
        result = await obj.execute_trade_decision(decision())
        self.assertEqual(result['status'], 'SUCCESS')
        self.assertTrue(result['sl_confirmed'])
        self.assertLessEqual(len(result['client_order_id']), 36)

    async def test_partial_fill_latches_and_blocks_next_entry(self):
        obj = executor(); obj.client.order.update(orderStatus='PartiallyFilled', cumExecQty='0.05')
        result = await obj.execute_trade_decision(decision())
        self.assertEqual(result['status'], 'RECONCILIATION_REQUIRED')
        self.assertEqual(result['filled_qty'], '0.05')
        with self.assertRaises(ExchangeStateUnknown):
            await obj.execute_trade_decision(decision())
        self.assertEqual(len(obj.client.calls), 1)

    async def test_cancelled_partial_and_unknown_order_never_free_capacity(self):
        for status in ('Cancelled', 'PartiallyFilledCanceled', 'Rejected'):
            obj = executor(); obj.client.order.update(orderStatus=status, cumExecQty='0.05')
            result = await obj.execute_trade_decision(decision())
            self.assertEqual(result['status'], 'RECONCILIATION_REQUIRED')

    async def test_post_timeout_not_retried(self):
        obj = executor(); obj.client.fail_create = True
        self.assertEqual((await obj.execute_trade_decision(decision()))['status'], 'RECONCILIATION_REQUIRED')
        self.assertEqual(len(obj.client.calls), 1)

    async def test_filled_with_wrong_or_missing_protection_is_not_success(self):
        for field, value in [('stopLoss', '91'), ('takeProfit', '0'), ('positionIdx', 2),
                             ('side', 'Sell'), ('symbol', 'ETHUSDT'), ('positionStatus', 'Liq')]:
            obj = executor(); obj.client.positions['result']['list'][0][field] = value
            with self.subTest(field=field):
                result = await obj.execute_trade_decision(decision())
                self.assertEqual(result['status'], 'RECONCILIATION_REQUIRED')
                self.assertTrue(obj.reconciliation_required)

    async def test_failed_stop_request_is_not_success(self):
        obj = executor(); obj.client.protection_code = 10000
        self.assertEqual((await obj.execute_trade_decision(decision()))['status'], 'RECONCILIATION_REQUIRED')

    async def test_wrong_order_identity_and_fill_quantity_rejected(self):
        for field, value in [('orderId', 'other'), ('symbol', 'ETHUSDT'), ('cumExecQty', '0.05'), ('avgPrice', 'NaN')]:
            obj = executor(); obj.client.order[field] = value
            with self.subTest(field=field):
                self.assertEqual((await obj.execute_trade_decision(decision()))['status'], 'RECONCILIATION_REQUIRED')

    async def test_unconfirmed_order_halts(self):
        obj = executor(); obj.client.order['orderStatus'] = 'New'
        with patch('execution.bybit_executor.asyncio.sleep', new=AsyncMock()):
            self.assertEqual((await obj.execute_trade_decision(decision()))['status'], 'RECONCILIATION_REQUIRED')

    async def test_invalid_decision_never_submits(self):
        for change in ({'is_allowed': False}, {'leverage': 25}, {'stop_loss_price': 150}):
            obj = executor()
            self.assertEqual((await obj.execute_trade_decision(decision(**change)))['status'], 'REJECTED')
            self.assertEqual(obj.client.calls, [])

    async def test_leverage_failure_stops_before_margin_setup(self):
        client = object.__new__(BybitClient)
        with patch.object(client, 'request', return_value={'retCode': 10000}) as request:
            self.assertEqual(client.setup_symbol('BTCUSDT', leverage=3)['retCode'], 10000)
            self.assertEqual(request.call_count, 1)


class ReconciliationTests(unittest.TestCase):
    def test_failed_response_cannot_report_reconciled(self):
        from execution.reconciler import ExchangeStateReconciler
        db = QuantDatabaseManager(':memory:'); self.addCleanup(db.close)
        client = object.__new__(BybitClient)
        with patch.object(client, 'get_positions', return_value={'retCode': 10000}):
            with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(ExchangeStateUnknown):
                ExchangeStateReconciler(client, db).reconcile_state()

    def test_unprotected_position_cannot_report_reconciled(self):
        from execution.reconciler import ExchangeStateReconciler
        db = QuantDatabaseManager(':memory:'); self.addCleanup(db.close)
        client = object.__new__(BybitClient)
        row = position(); row['takeProfit'] = '0'
        with patch.object(client, 'get_positions', return_value=response([row])):
            with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(ExchangeStateUnknown):
                ExchangeStateReconciler(client, db).reconcile_state()

    def test_complete_empty_response_can_reconcile(self):
        from execution.reconciler import ExchangeStateReconciler
        db = QuantDatabaseManager(':memory:'); self.addCleanup(db.close)
        client = object.__new__(BybitClient)
        with patch.object(client, 'get_positions', return_value=response([])):
            with contextlib.redirect_stdout(io.StringIO()):
                result = ExchangeStateReconciler(client, db).reconcile_state()
        self.assertEqual(result['status'], 'RECONCILED')
        self.assertEqual(result['active_exchange_positions'], 0)


class RiskCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / 'synthetic-risk.json'
        self.now = datetime(2026, 11, 18, 12, tzinfo=timezone.utc)
        self.initial = dict(schema=1, day='2026-11-18', day_start_equity=1000,
                            peak_equity=1000, blocked=False)
        self.path.write_text(json.dumps(self.initial))

    def test_restart_preserves_loss_and_high_water_mark(self):
        RiskCheckpoint(self.path).observe(1100, self.now)
        daily_loss, drawdown = RiskCheckpoint(self.path).observe(980, self.now)
        self.assertAlmostEqual(daily_loss, 2.0)
        self.assertAlmostEqual(drawdown, 120 / 1100 * 100)

    def test_loss_limit_latch_survives_restart_and_recovery(self):
        with self.assertRaises(RiskStateUnknown):
            RiskCheckpoint(self.path).observe(989, self.now, max_daily_loss_pct=1)
        with self.assertRaises(RiskStateUnknown):
            RiskCheckpoint(self.path).observe(1100, self.now, max_daily_loss_pct=1)

    def test_missing_checkpoint_never_initializes_automatically(self):
        self.path.unlink()
        with self.assertRaises(RiskStateUnknown):
            RiskCheckpoint(self.path).observe(1000, self.now)
        self.assertFalse(self.path.exists())

    def test_corrupt_checkpoint_never_resets(self):
        for text in ('{}', 'broken', '[]', '{"schema": 1}', 'x' * 5000):
            self.path.write_text(text)
            with self.assertRaises(RiskStateUnknown):
                RiskCheckpoint(self.path).observe(1000, self.now)
            self.assertEqual(self.path.read_text(), text)

    def test_invalid_equity_rejected(self):
        for equity in (float('nan'), float('inf'), -1, 0, True):
            with self.assertRaises(RiskStateUnknown):
                RiskCheckpoint(self.path).observe(equity, self.now)

    def test_day_rollover_does_not_hide_loss(self):
        tomorrow = self.now.replace(day=19)
        with self.assertRaises(RiskStateUnknown):
            RiskCheckpoint(self.path).observe(800, tomorrow)
        self.assertEqual(json.loads(self.path.read_text()), self.initial)

    def test_block_survives_restart(self):
        RiskCheckpoint(self.path).block()
        with self.assertRaises(RiskStateUnknown):
            RiskCheckpoint(self.path).observe(1000, self.now)

    def test_failed_persistence_latches_and_preserves_previous_state(self):
        checkpoint = RiskCheckpoint(self.path)
        with patch('os.replace', side_effect=OSError('synthetic disk full')):
            with self.assertRaises(RiskStateUnknown):
                checkpoint.observe(1100, self.now)
        self.assertEqual(json.loads(self.path.read_text()), self.initial)
        with self.assertRaises(RiskStateUnknown):
            checkpoint.observe(1000, self.now)
        self.assertEqual(list(self.path.parent.glob('.risk-*')), [])


if __name__ == '__main__':
    unittest.main()
