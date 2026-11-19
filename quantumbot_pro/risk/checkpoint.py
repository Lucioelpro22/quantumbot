"""Single-writer engineering risk checkpoint; never auto-resets missing state.

No operational storage is initialized by the engine. A future authorized
operator must establish the UTC daily baseline separately. No account/deposit
reconciliation or multi-worker safety is claimed by this component.
"""
import json
import math
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


class RiskStateUnknown(RuntimeError):
    pass


def _positive(value):
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise RiskStateUnknown('Invalid risk checkpoint amount')
    return value


class RiskCheckpoint:
    def __init__(self, path):
        self.path = Path(path)
        self.failed = False

    def _read(self):
        if self.failed:
            raise RiskStateUnknown('Risk checkpoint latched after failure')
        try:
            if self.path.is_symlink():
                raise ValueError('Symlink checkpoint denied')
            # Bounded read; no arbitrary data files accepted as risk checkpoints.
            with self.path.open('r', encoding='utf-8') as handle:
                text = handle.read(4097)
            if len(text) > 4096:
                raise ValueError('Oversized checkpoint')
            state = json.loads(text)
            if set(state) != {'schema', 'day', 'day_start_equity', 'peak_equity', 'blocked'}:
                raise ValueError('Invalid schema')
            if state['schema'] != 1 or type(state['blocked']) is not bool:
                raise ValueError('Invalid version or latch')
            datetime.strptime(state['day'], '%Y-%m-%d')
            if _positive(state['peak_equity']) < _positive(state['day_start_equity']):
                raise ValueError('Invalid high-water mark')
            return state
        except (OSError, ValueError, TypeError, KeyError, RiskStateUnknown) as exc:
            self.failed = True
            raise RiskStateUnknown('Missing or corrupt risk checkpoint; reconciliation required') from exc

    def _write(self, state):
        temp_path = None
        try:
            fd, temp_path = tempfile.mkstemp(prefix='.risk-', dir=self.path.parent)
            with os.fdopen(fd, 'w', encoding='utf-8') as handle:
                json.dump(state, handle, allow_nan=False)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, self.path)
            # Durability on platforms supporting directory fsync.
            if hasattr(os, 'O_DIRECTORY'):
                fd = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
        except (OSError, ValueError) as exc:
            self.failed = True
            raise RiskStateUnknown('Checkpoint persistence failed; entries denied') from exc
        finally:
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)

    def observe(self, equity, now=None, *, max_daily_loss_pct=None, max_drawdown_pct=None):
        equity = _positive(equity)
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            raise RiskStateUnknown('UTC-aware time required')
        state = self._read()
        if state['blocked']:
            raise RiskStateUnknown('Persistent risk latch requires reconciliation')
        if state['day'] != now.astimezone(timezone.utc).date().isoformat():
            raise RiskStateUnknown('Daily baseline missing; reviewed rollover required')
        state['peak_equity'] = max(state['peak_equity'], equity)
        loss = max(0.0, (state['day_start_equity'] - equity) / state['day_start_equity'] * 100)
        drawdown = max(0.0, (state['peak_equity'] - equity) / state['peak_equity'] * 100)
        breached = ((max_daily_loss_pct is not None and loss >= _positive(max_daily_loss_pct))
                    or (max_drawdown_pct is not None and drawdown >= _positive(max_drawdown_pct)))
        if breached:
            state['blocked'] = True
        self._write(state)
        if breached:
            raise RiskStateUnknown('Loss limit reached; persistent latch set')
        return loss, drawdown

    def block(self):
        state = self._read()
        state['blocked'] = True
        self._write(state)
