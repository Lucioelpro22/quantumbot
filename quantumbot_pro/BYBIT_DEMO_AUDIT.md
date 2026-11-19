# Bybit Demo — operationally blocked

The earlier demo instructions are superseded by the repository's current
[operational disposition](../OPERATIONAL_STATE.md). This is not authorization to
create credentials, run a cycle, download market data or collect a ledger.

The engine, concrete exchange clients and collection entry points now reject
operational access. `ALLOW_LIVE_TRADING=true` does not grant permission.

The former 100-trade / 60-day / profit-factor / bootstrap thresholds described
criteria, not achieved results. This remediation ran no profitability evaluation.
No strategy is promoted, and no real or demo exchange order is submitted.

For metadata-only diagnosis use `python -B -m quantumbot_pro.cli --mode status`
from the repository root. For synthetic engineering validation use the explicit
suite documented in the root README. Runtime on external machines remains unknown.
