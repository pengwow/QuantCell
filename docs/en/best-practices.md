---
title: Best Practices
description: Project conventions for strategy R&D, backtesting, data, deployment and security
---

# Best Practices

## Strategy R&D

- **Backtest first, then paper, then live** — pass each stage's gate before
  moving to the next
- Parameter-sensitive strategies (momentum, mean reversion, RL)
  **must run Walk-Forward**
- Re-validate HPO results with an independent Walk-Forward run — double
  protection against overfitting
- Strategies only compute signals internally: no placing orders, no network
  access, no direct exchange state reads
- LLM strategy backtests go through ReplayProvider only — a replay miss
  raises an error, never silent degradation

## Backtesting

- Be explicit about the `runner` choice: the default unified kernel is fine,
  and unsupported data types auto-fall back to the Python path
- Mind the semantic boundaries of data types: `fundingRate` is a feature
  column, not the settlement channel; `bookDepth` / `bookTicker` aggregate
  into synthetic prices, not tradable order books
- Coin-margined accounting is approximate (multiplier not included in
  notional value) — interpret PnL cautiously for heavily-leveraged
  coin-margin scenarios
- When comparing strategies, fix capital, interval and symbol sets to keep
  the measurement basis consistent

## Data

- Run `quantcell data quality check` before backtesting — missing gaps
  directly distort results
- Timestamps use nanosecond-precision ISO 8601; symbols use `BASE/QUOTE`
- Validate aggregation output on a small batch from any new data source
  before scaling up collection

## Code conventions (backend)

- The route layer only receives parameters and calls services; business
  logic lives in the service layer
- Raise errors via `HTTPException` uniformly; leave validation to Pydantic
- Use dependency injection (`Depends`) to keep tests mockable
- Prefer top-level imports; when a function-level import is truly required,
  add a comment explaining why
- All logging goes through `backend/utils/logger.py` — **print is
  forbidden**; emit structured logs with request_id and never log secrets
- Scripts use `typer`, not argparse
- Timestamp strings follow ISO 8601 (RFC 3339), primarily with 9-digit
  (nanosecond) precision

## Code conventions (frontend)

- For antd v6 component spacing use `<Space orientation="vertical">` or
  `<Flex gap>` — **never** Tailwind `space-y-*` between antd components
  (it breaks under CSS-in-JS)
- Standard spacing values: `small` (8px) / `middle` (16px) / `large` (24px);
  no magic margins
- After finishing a page, self-check that adjacent blocks have visible gaps

## Engine dependency (Rust kernel)

After modifying Rust kernel sources, the standard command to sync into the
backend environment (the package name is the local path dependency in
`backend/pyproject.toml`):

```bash
cd backend && uv sync --frozen --reinstall-package <engine-package>
```

- **`--reinstall-package` is mandatory**: uv does not check source
  freshness for maturin path dependencies — without it the stale .so gets
  reinstalled
- Never hand-install via `uv pip install <wheel>` (the next `uv sync`
  silently reverts it to the old version)
- After syncing the engine, run the conformance gate first, then the full
  suite: `uv run pytest tests/conformance/ -q`

## Git commits

- Use `feat/ fix/ docs/ refactor/` prefixes in commit messages
- Split commits by logical unit; don't pile files into one commit
- Run the matching lint / test before committing (`make lint` / `make test`)

## Environments

- Layer config per environment (`.env.dev / .env.test / .env.prod`),
  managed with pydantic-settings
- No hardcoded secrets; production config is never committed
- API prefix `/api/v1`, reserving room for incompatible upgrades

## Deployment

- Production frontend: `make frontend-build` then deploy the static
  artifacts, or use the desktop client / remote mode directly
- Production backend startup: `uvicorn main:app --host 0.0.0.0 --port 8000`
  (systemd / container orchestration and log collection recommended)
- Live-trading servers expose only necessary ports and permissions; use
  least-privilege exchange keys (withdrawals disabled)
