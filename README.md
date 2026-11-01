# QuantumBot Pro

QuantumBot Pro is an open-source research framework for systematic crypto-trading experiments, portfolio risk controls, backtesting, stress testing, explainability, and guarded exchange-demo execution.

This public edition is intended for **research, education, backtesting, and Bybit Demo Trading**. It contains no API credentials, private account data, databases, trade histories, or production configuration.

## Public release safeguards

- The audited execution path is locked to `https://api-demo.bybit.com`.
- Live/real promotion is not automatic and requires a separate technical review.
- Maximum leverage in the audited demo flow is 3x.
- Risk per entry is capped at 0.25% of equity.
- Daily loss is capped at 1% and process-session drawdown at 8%.
- At most two positions may be open.
- Quantities are normalized to Bybit instrument constraints.
- Entry orders include protective stop-loss and take-profit values.
- REST acceptance is not treated as a confirmed fill.

## Repository structure

- `quantumbot_pro/` — research engine, strategies, execution, risk, analytics, backtesting, and demo validation.
- `quantumbot_harness/` — deterministic verification harness retained from the original private repository.
- `tests/` — safety, regression, and harness tests.
- `docs/` — operational and verification documentation.

## Setup

```bash
python -m venv .venv
python -m pip install -r requirements.txt
```

Copy `.env.example` to `.env` and use credentials created exclusively inside Bybit Demo Trading. Never commit `.env`, reuse production credentials, or grant withdrawal permissions.

## Demo execution

```bash
cd quantumbot_pro
python cli.py --mode demo
```

Read [`quantumbot_pro/BYBIT_DEMO_AUDIT.md`](quantumbot_pro/BYBIT_DEMO_AUDIT.md) before execution.

## Evidence collection

```bash
cd quantumbot_pro
python demo_profitability.py --collect
```

The evidence gate requires at least 100 closed trades, 60 calendar days, positive net PnL, profit factor of at least 1.20, and a positive lower bootstrap bound for the mean return. Passing the gate does not prove future profitability or authorize live trading.

## Disclaimer

This project is educational software, not financial advice. Backtests and demo results do not guarantee future performance. Trading involves substantial risk, including complete loss of capital.

## License

MIT
