# Strategy engineering review — 18 November 2026 (America/Buenos_Aires)

This is a source-code correction and synthetic regression result, not a strategy
profitability audit. Demo equity, account ledger and the running Antigravity
process were not available for observation. No real balance is assumed and no
USD 1,000/day capability is established.

Implementation authorization is recorded in
`quantumbot_harness/specs/SPEC-ENGINEERING-STRATEGY-REVIEW-001.json`. This records
the user's instruction to implement proposals, not independent approval,
research authorization or permission to trade.

## Confirmed source defects and changes

| Before | Implemented correction | Source |
| --- | --- | --- |
| Calibrator covered seven of the engine's nine modules; VWAP had a different weight key from its emitted name | Shared canonical nine-module registry; no unknown-module fallback or automatic normalization | `strategies/registry.py`, `risk/auto_calibrator.py`, `strategies/meta_strategy.py` |
| Win rate alone automatically raised weights, even with net losses | Legacy calibration leaves weights unchanged and requests manual review; explicit descriptive accounting includes fees and signed funding | `risk/auto_calibrator.py`, `analytics/strategy_review.py` |
| Repeated signals could multiply one module's weight; ties favored a direction | One vote per module, conflicting directions abstain, exact shared evidence counted once, directional ties produce no trade | `strategies/meta_strategy.py` |
| Regime bonus could create a direction without underlying votes | Bonus only applies after a nonzero directional consensus; nontradable or invalid regime rejects | `strategies/meta_strategy.py` |
| Risk sizing could allow a score that consensus had rejected | Approval and direction consistency required; malformed/nonfinite inputs deny; position budget includes estimated fees/slippage | `risk/risk_manager.py` |
| Four-decimal stop rounding could destroy protection for low-priced instruments | Preserve calculated prices; reject zero/nonfinite or degenerate protection; validate final economic budget | `risk/risk_manager.py` |

Default risk sizing is limited to 0.25% of observed equity, leverage 1–3 and
estimated notional at most 60% of equity. Daily loss and drawdown defaults are
1% and 8%. These are code constraints, not guarantees against gaps, execution
cost changes or losses. No ML probability or Kelly estimate raises the budget.
Instrument tick normalization and real exchange behavior remain unqualified.

## Descriptive accounting contract

`review_closed_trades(rows, provenance='DEMO' | 'SYNTHETIC')` accepts only records
already supplied in memory. It does not open a ledger, query a broker, download
prices or execute a strategy. It is not wired into an operational loop.

Each fully closed trade requires its unique ID, one canonical attributed module,
explicit USD denomination, timezone-aware open/close timestamps, gross realized
PnL at actual fill prices, commission costs and signed funding costs. Positive
funding is a cost; negative funding is a credit. Slippage is already reflected
in actual fills and is not subtracted a second time. Missing costs, ensemble-only
attribution, mixed provenance, unknown modules and conflicting IDs reject.
Identical repeated trade IDs are counted once. USDT is not silently treated as USD.

Outputs cover all nine modules, including NO_DATA entries: gross/net PnL, costs,
win rate, mean closed-trade result, profit factor when defined, active close days,
calendar span and drawdown of cumulative closed-trade PnL. Regime labels provide
only descriptive groups, not an optimized regime selector. Account equity is
always NOT_OBSERVED; closed-PnL drawdown is not mark-to-market account drawdown.

## Validation actually performed

- **64 tests passed**, zero failures/errors/skips: previous 35 health regressions
  plus 29 strategy accounting, consensus and risk boundary regressions.
- Command: `python -B -m unittest discover -s tests/engineering_health -v` with
  Pydantic v2 installed. The runtime used was the preinstalled Codex primary
  Python environment. The original 35-test suite alone remains stdlib-only.
- Fixtures include 80% winners with negative net PnL, funding credit, repeated and
  conflicting trade IDs, unordered closes, duplicate/conflicting votes, shared
  evidence, invalid scores, nonfinite data and subnormal price protection.
- Socket connections and DNS resolution denied inside both test modules.
- Existing SPEC schema, Python syntax and whitespace checks passed.
- Original frozen governance, CI and historical tests are unchanged. Operational
  denial policy is unchanged from the preceding health remediation commit.
- Status CLI still reports LIVE BLOCKED, FINAL_HOLDOUT LOCKED, research stopped,
  historical holdout EXPOSED / CONTAMINATED and runtime UNKNOWN.

## Limits and decisions still requiring human review

These tests establish arithmetic and rejection behavior only. There are no new
market benchmarks, measured execution returns, independently validated strategies
or evidence of self-financing. The historical nine weights and regime bonuses
are not optimized or statistically validated. Shared-evidence deduplication
works only when an explicit event identifier is supplied; absence of an ID does
not prove independence or remove correlation between strategies. A module with
multiple valid observations retains its highest-strength/confidence observation;
its historical budget is counted at most once.

To rank strategies by actual demo performance, an authorized export with balance,
account identity, timestamps, attributed fills and costs is still needed. Missing
attribution cannot be reconstructed by assigning the same ensemble PnL to every
voter. Demo records themselves would not certify future live returns.

Human review must assess attribution quality, any eventual weight/configuration
change, and independent approval of this exact candidate source/environment.
No baseline rebind, CI bypass, merge, deployment, market backtest, new hypothesis,
credential read, holdout read or exchange operation is part of this change.
The earlier full health report remains a record of its 35-test stage; this
follow-up supplies the cumulative 64-test result.
