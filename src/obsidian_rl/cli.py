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


def cmd_gpu_check(args: argparse.Namespace) -> int:
    from obsidian_rl.training.device import detect_device

    print(json.dumps(detect_device("auto").to_dict(), indent=1))
    return 0


def _load_range(start: str | None, end: str | None) -> "object":
    settings = get_settings()
    store = CandleStore(settings.data_dir, settings.symbol, settings.interval)
    start_ms = _parse_utc_date(start) if start else None
    end_ms = _parse_utc_date(end) if end else None
    df = store.read(start_ms, end_ms)
    if df.empty:
        raise SystemExit("no candles in requested range — run data-download first")
    return df


def cmd_train(args: argparse.Namespace) -> int:
    from obsidian_rl.training.ppo import PpoHyperparams, TrainConfig, train_ppo

    settings = get_settings()
    train_candles = _load_range(args.train_start, args.train_end)
    eval_candles = _load_range(args.eval_start, args.eval_end)
    if args.smoke:
        cfg = TrainConfig(
            total_timesteps=4096,
            n_envs=1,
            seed=args.seed,
            device="cpu",
            episode_length=256,
            checkpoint_freq=2048,
            eval_freq=2048,
            hyperparams=PpoHyperparams(n_steps=256, batch_size=64, net_arch=(32, 32)),
        )
    else:
        cfg = TrainConfig(
            total_timesteps=args.timesteps, n_envs=args.n_envs, seed=args.seed, device=args.device
        )
    result = train_ppo(train_candles, eval_candles, cfg, settings.models_dir)
    print(
        json.dumps(
            {
                "model_id": result.record.model_id,
                "model_dir": str(result.record.model_dir),
                "device": result.device.to_dict(),
                "eval_mean_reward": result.eval_mean_reward,
                "wall_seconds": round(result.wall_seconds, 1),
            },
            indent=1,
        )
    )
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

    p = sub.add_parser("gpu-check", help="report torch/CUDA capability")
    p.set_defaults(func=cmd_gpu_check)

    p = sub.add_parser("train", help="train PPO (use --smoke for a fast CPU run)")
    p.add_argument("--train-start", required=True)
    p.add_argument("--train-end", required=True)
    p.add_argument("--eval-start", required=True)
    p.add_argument("--eval-end", default=None)
    p.add_argument("--smoke", action="store_true", help="fast CPU smoke configuration")
    p.add_argument("--timesteps", type=int, default=2_000_000)
    p.add_argument("--n-envs", type=int, default=8)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda"])
    p.set_defaults(func=cmd_train)

    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
