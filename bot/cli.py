"""Command line: python -m bot <command>"""

from __future__ import annotations

import argparse
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .backtest import BacktestResult, run_backtest
from .config import Config, load_config
from .data import fetch_yfinance, load_csv, make_sample
from .strategy import RsiEmaStrategy

DISCLAIMER = "⚠️  Not financial advice. Paper trading and backtests only — no real orders are placed."


def setup_logging(log_dir: str, verbose: bool = False) -> None:
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    root.handlers.clear()
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    fh = RotatingFileHandler(Path(log_dir) / "bot.log", maxBytes=5_000_000, backupCount=5)
    fh.setFormatter(fmt)
    root.addHandler(sh)
    root.addHandler(fh)
    logging.getLogger("yfinance").setLevel(logging.WARNING)


def _print_table(rows: list[dict]) -> None:
    if not rows:
        print("no results")
        return
    keys = list(rows[0].keys())
    widths = {k: max(len(k), *(len(str(r[k])) for r in rows)) for k in keys}
    print("  ".join(k.ljust(widths[k]) for k in keys))
    print("  ".join("-" * widths[k] for k in keys))
    for r in rows:
        print("  ".join(str(r[k]).ljust(widths[k]) for k in keys))


def _save(result: BacktestResult, out_dir: Path) -> None:
    import pandas as pd
    out_dir.mkdir(parents=True, exist_ok=True)
    name = f"{result.symbol.replace('/', '_')}_{result.mode}"
    pd.DataFrame([t.__dict__ for t in result.trades]).to_csv(out_dir / f"{name}_trades.csv", index=False)
    result.equity.rename("equity").to_csv(out_dir / f"{name}_equity.csv")


def cmd_backtest(cfg: Config, args: argparse.Namespace) -> int:
    datasets = []
    if args.csv:
        for path in args.csv:
            datasets.append((Path(path).stem, load_csv(path)))
    elif args.sample:
        datasets.append(("SAMPLE (synthetic)", make_sample(days=args.sample_days)))
    else:
        for sym in args.symbols or cfg.symbols:
            print(f"downloading {sym} {args.interval} {args.period} ...")
            datasets.append((sym, fetch_yfinance(sym, args.interval, args.period)))

    modes = [True, False] if args.compare else [args.naive]
    strategy = RsiEmaStrategy(cfg.strategy)
    rows = []
    for name, df in datasets:
        for naive in modes:
            res = run_backtest(df, name, strategy, cfg.risk, cfg.costs, cfg.hours,
                               naive=naive, starting_cash=cfg.starting_cash)
            rows.append(res.summary())
            if args.out:
                _save(res, Path(args.out))
    print()
    print(DISCLAIMER)
    print(f"period: {datasets[0][1].index[0]} → {datasets[0][1].index[-1]}")
    _print_table(rows)
    if args.compare:
        print("\nnaive  = signal and fill on the same candle close, no costs (how beginner bots are often tested)")
        print("honest = fill on the NEXT candle's open, with fees + slippage")
    if args.out:
        print(f"\ntrades + equity curves saved to {args.out}/")
    return 0


def cmd_paper(cfg: Config, args: argparse.Namespace) -> int:
    from .runner import PaperTrader
    print(DISCLAIMER)
    trader = PaperTrader(cfg)
    if args.once:
        print("status:", trader.step())
        return 0
    trader.run_forever()
    return 0


def cmd_kill(cfg: Config, args: argparse.Namespace) -> int:
    cfg.kill_file.parent.mkdir(parents=True, exist_ok=True)
    cfg.kill_file.write_text("killed\n")
    print(f"Kill switch ON ({cfg.kill_file}). The bot will square off and stop entering.")
    return 0


def cmd_resume(cfg: Config, args: argparse.Namespace) -> int:
    if cfg.kill_file.exists():
        cfg.kill_file.unlink()
    print("Kill switch OFF.")
    return 0


def cmd_status(cfg: Config, args: argparse.Namespace) -> int:
    import json
    path = Path(cfg.state_dir) / "paper_state.json"
    print(f"kill switch: {'ON' if cfg.kill_switch_on() else 'off'}")
    if not path.exists():
        print("no paper state yet")
        return 0
    b = json.loads(path.read_text())["broker"]
    print(f"cash: {b['cash']:.2f} (started {b['starting_cash']:.2f})")
    print(f"open positions: {list(b['positions']) or 'none'}")
    print(f"closed trades: {len(b['trades'])}, net P&L {sum(t['net_pnl'] for t in b['trades']):+.2f}")
    return 0


def cmd_sample(cfg: Config, args: argparse.Namespace) -> int:
    df = make_sample(days=args.days)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out)
    print(f"wrote {len(df)} SYNTHETIC candles to {args.out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="bot", description="RSI + EMA paper-trading bot")
    p.add_argument("--config", default="config.yaml")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("backtest", help="run a backtest")
    src = b.add_mutually_exclusive_group()
    src.add_argument("--csv", nargs="+", help="CSV file(s) with timestamp,open,high,low,close,volume")
    src.add_argument("--symbols", nargs="+", help="Yahoo symbols, e.g. RELIANCE.NS")
    src.add_argument("--sample", action="store_true", help="use synthetic demo data")
    b.add_argument("--sample-days", type=int, default=30)
    b.add_argument("--interval", default="5m")
    b.add_argument("--period", default="30d")
    mode = b.add_mutually_exclusive_group()
    mode.add_argument("--naive", action="store_true", help="2021-style: same-candle fills, no costs")
    mode.add_argument("--compare", action="store_true", help="run naive and honest side by side")
    b.add_argument("--out", help="folder to save trades/equity CSVs")
    b.set_defaults(func=cmd_backtest)

    pp = sub.add_parser("paper", help="run the paper-trading loop")
    pp.add_argument("--once", action="store_true", help="run a single iteration and exit")
    pp.set_defaults(func=cmd_paper)

    sub.add_parser("kill", help="turn the kill switch ON").set_defaults(func=cmd_kill)
    sub.add_parser("resume", help="turn the kill switch OFF").set_defaults(func=cmd_resume)
    sub.add_parser("status", help="show paper account status").set_defaults(func=cmd_status)

    s = sub.add_parser("sample-data", help="write synthetic candles to CSV")
    s.add_argument("--out", default="data/sample.csv")
    s.add_argument("--days", type=int, default=30)
    s.set_defaults(func=cmd_sample)

    args = p.parse_args(argv)
    cfg = load_config(args.config)
    setup_logging(cfg.log_dir, args.verbose)
    return args.func(cfg, args)
