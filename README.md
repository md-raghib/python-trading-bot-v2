# Python Trading Bot v2 — RSI + EMA (2026 rebuild)

[![CI](https://github.com/md-raghib/python-trading-bot-v2/actions/workflows/ci.yml/badge.svg)](https://github.com/md-raghib/python-trading-bot-v2/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-3.10%20%7C%203.13-blue)

The 2021 Python trading bot from [this video](https://www.youtube.com/watch?v=JKZCM3TwG-Y), rebuilt with proper structure, honest backtests, risk limits and a DevOps-style deployment.

📺 **Channel:** [MRM — Learn DevOps with Raghib](https://www.youtube.com/@LearnDevOpswithRaghib00)

> [!WARNING]
> **Not financial advice. Educational project.** This bot does **paper trading and backtesting only** and has no live-broker integration on purpose. Past or backtested results do not predict future results. Rules for retail algo/API trading in India (SEBI and your broker's API terms) have changed since 2021, so check them before you connect anything to real money. You are solely responsible for how you use this code. See [LICENSE](LICENSE) (provided "as is", without warranty).

## What changed since 2021

| 2021 bot | v2 |
|---|---|
| One big script | Modules: `strategy`, `risk`, `broker`, `backtest`, `runner` |
| Tested live, with real money | Backtester with **naive vs honest** mode and paper trading |
| Filled on the same candle that made the signal | Fills on the **next** candle's open (no look-ahead) |
| No costs | Fees + slippage on every fill (set your broker's real charges) |
| No limits | Max trades/day, max daily loss, position size, stop-loss, target, kill switch |
| Ran on a laptop, died when it slept | Docker + `restart: unless-stopped`, sleeps outside market hours |
| Errors stopped the bot | Retries with backoff, per-symbol error isolation, Telegram alerts |
| Positions lost on restart | Paper state saved to `state/paper_state.json` |

## Quick start

Requires Python 3.9+ (CI tests 3.10 and 3.13).

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp config.example.yaml config.yaml     # put your 2021 rules in the strategy: section
pytest -q
```

### Backtest

```bash
# synthetic demo data (works offline)
python -m bot backtest --sample --compare

# real NSE data from Yahoo (free, delayed, 5m candles ≈ last 60 days only)
python -m bot backtest --symbols RELIANCE.NS TCS.NS --interval 5m --period 30d --compare --out reports

# your own CSV (timestamp,open,high,low,close,volume)
python -m bot backtest --csv data/RELIANCE_5m.csv --compare
```

`--compare` prints the **naive** (2021-style) and **honest** results side by side. That's the table for the video.

### Paper trading

```bash
python -m bot paper --once   # one iteration, good for testing
python -m bot paper          # run the loop
python -m bot status         # cash, open positions, P&L
python -m bot kill           # kill switch: square off and block entries
python -m bot resume         # kill switch off
```

### Run it 24/7 with Docker

```bash
cp config.example.yaml config.yaml
cp .env.example .env          # add TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID for alerts
docker compose up -d --build
docker compose logs -f
```

Run it on a small cloud VM rather than your laptop. The container restarts itself, and its state and logs live in mounted folders.

## How a candle is handled

1. Only **closed** candles are used. A half-formed candle can show a signal that disappears before it closes.
2. Indicators return no value until they have enough history (warm-up), and no trades happen during warm-up.
3. A **risk check runs before** any entry.
4. Stop-loss and target are checked inside each candle. If a candle touched both, the stop is assumed to have hit first (conservative).
5. No entries after 15:00, and everything is squared off at 15:15 IST.

## Known limitations

- Yahoo data is delayed and limited, which is fine for demos and wrong for real trading. Use your broker's data API for anything serious.
- In paper mode, fills use the last closed candle's price plus slippage. Real fills will differ.
- The default cost numbers are placeholders.
- Strategy is long-only.

## Project layout

```
bot/
  indicators.py    EMA, RSI (causal; tested for look-ahead)
  strategy.py      RSI + EMA rules
  risk.py          limits, position size, stop/target
  costs.py         fees + slippage
  broker.py        paper broker + persistence
  backtest.py      naive vs honest backtester
  runner.py        paper-trading loop
  market_hours.py  NSE session times
  alerts.py        Telegram alerts
  data.py          CSV / Yahoo / synthetic data
  cli.py           `python -m bot ...`
tests/
```

## Contributing & security

Issues and PRs are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md). Please report security problems privately as described in [SECURITY.md](SECURITY.md).

## License

[MIT](LICENSE)
