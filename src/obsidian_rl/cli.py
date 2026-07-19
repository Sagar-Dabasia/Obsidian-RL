"""Command-line entry points: python -m obsidian_rl.cli <command> [options]."""

import argparse
import json
import logging
import sys
from datetime import UTC, datetime

from obsidian_rl.config import get_settings
from obsidian_rl.data.store import CandleStore
from obsidian_rl.data.validation import validate_candles


def _parse_utc_date(value: str) -> int:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return int(dt.timestamp() * 1000)


def cmd_data_download(args: argparse.Namespace) -> int:
    from obsidian_rl.data.download import initial_download

    settings = get_settings()
    end_ms = _parse_utc_date(args.end) if args.end else None
    store = initial_download(settings, _parse_utc_date(args.start), end_ms)
    print(json.dumps(store.summary(), indent=1))
    return 0


def cmd_data_update(args: argparse.Namespace) -> int:
    from obsidian_rl.data.download import incremental_update

    settings = get_settings()
    new_rows = incremental_update(settings)
    print(f"new finalized candles: {new_rows}")
    return 0


def cmd_data_validate(args: argparse.Namespace) -> int:
    settings = get_settings()
    store = CandleStore(settings.data_dir, settings.symbol, settings.interval)
    df = store.read()
    rep = validate_candles(df, settings.interval, gaps_are_errors=args.strict)
    print(rep.summary())
    if rep.gaps:
        for last_ok, next_open in rep.gaps[:20]:
            print(
                f"  gap: {datetime.fromtimestamp(last_ok / 1000, tz=UTC)} -> "
                f"{datetime.fromtimestamp(next_open / 1000, tz=UTC)}"
            )
    return 0 if rep.ok else 1


def cmd_data_summary(args: argparse.Namespace) -> int:
    settings = get_settings()
    store = CandleStore(settings.data_dir, settings.symbol, settings.interval)
    print(json.dumps(store.summary(), indent=1))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="obsidian_rl",
        description="Obsidian-RL research platform (paper trading only; no exchange orders)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("data-download", help="initial bulk historical download")
    p.add_argument("--start", required=True, help="UTC start date, e.g. 2021-01-01")
    p.add_argument("--end", default=None, help="UTC end date (default: now)")
    p.set_defaults(func=cmd_data_download)

    p = sub.add_parser("data-update", help="incremental update with finalized candles")
    p.set_defaults(func=cmd_data_update)

    p = sub.add_parser("data-validate", help="validate the stored dataset")
    p.add_argument("--strict", action="store_true", help="treat gaps as errors")
    p.set_defaults(func=cmd_data_validate)

    p = sub.add_parser("data-summary", help="dataset summary")
    p.set_defaults(func=cmd_data_summary)

    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
