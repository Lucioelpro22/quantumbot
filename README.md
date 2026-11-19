# QuantumBot Pro — engineering hold

The current operational disposition is **BLOCKED**. LIVE, demo/paper/shadow
execution, market acquisition, backtesting and research runs are not authorized.
The historical holdout is **EXPOSED / CONTAMINATED** and remains locked.
A historical `APPROVED` phase or zero-access counter is not current permission.
See [OPERATIONAL_STATE.md](OPERATIONAL_STATE.md).

This branch repairs bounded engineering failures; it does not certify a strategy,
restore holdout independence, or establish that an external bot process is stopped.
The published engine and exchange transports deny operational access unconditionally.

## Offline diagnosis

No credentials, dependencies or database are needed for this command (Python 3.10+):

```bash
python -B -m quantumbot_pro.cli --mode status
```

This prints **policy metadata**, with runtime `UNKNOWN`. It does not inspect your
computer, open `.env`, contact an exchange or read a trading ledger. Operational
CLI modes return exit code 2 before importing the engine. Environment flags cannot
unlock them. The legacy engine also rejects construction and cycles.

## Engineering regression tests

```bash
python -B -m unittest discover -s tests/engineering_health -v
```

This explicit standard-library suite uses synthetic responses, in-memory SQLite
and temporary risk checkpoints. Socket resolution/connections are denied by test
fixtures. It does not run the historical research suites or evaluate strategies.

The concrete Bybit/BingX clients have no enabled transport. Protocol tests use
local fake objects. The database adapter only accepts the explicit `:memory:`
path; persistent trading storage remains blocked. Risk checkpoints are a
single-writer engineering component, not an operational account ledger.

## Integration status

The existing frozen-baseline admission workflow is preserved. A new tree is
expected to fail `REMOTE_CANDIDATE_TREE_NOT_APPROVED` until an independent review
approves the exact source and runner environment. Do not rebind the baseline to
this branch simply to make CI pass. Passing synthetic tests does not authorize
execution, formal phase promotion, or use of the contaminated holdout.

[Remediation scope, evidence and remaining work](docs/HEALTH_REMEDIATION_2026-11-18.md)

MIT license. No validated profitability claim.
