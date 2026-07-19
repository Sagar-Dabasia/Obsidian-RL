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


def cmd_walk_forward(args: argparse.Namespace) -> int:
    from pathlib import Path

    from obsidian_rl.evaluation.walkforward import (
        evaluate_strategies_on_slice,
        make_folds,
        save_results,
        slice_candles,
        summarize,
    )
    from obsidian_rl.portfolio.costs import CostModel
    from obsidian_rl.strategies.baselines import default_baselines

    settings = get_settings()
    candles = _load_range(args.data_start, None)
    holdout_ms = _parse_utc_date(args.holdout_start)
    folds = make_folds(
        _parse_utc_date(args.data_start),
        holdout_ms,
        train_days=args.train_days,
        val_days=args.val_days,
        step_days=args.step_days,
    )
    seeds = [int(s) for s in args.seeds.split(",")] if not args.skip_ppo else []
    cost_model = CostModel()
    all_rows = []
    for fold in folds:
        val = slice_candles(candles, fold.val_start_ms, fold.val_end_ms)
        strategies: list[tuple[str, object, int | None]] = [
            (b.strategy_id, b, None)  # type: ignore[attr-defined]
            for b in default_baselines()
        ]
        for seed in seeds:
            from obsidian_rl.strategies.ppo_policy import PpoPolicyStrategy
            from obsidian_rl.training.ppo import TrainConfig, train_ppo

            train = slice_candles(candles, fold.train_start_ms, fold.train_end_ms)
            cfg = TrainConfig(
                total_timesteps=args.timesteps,
                n_envs=args.n_envs,
                seed=seed,
                device=args.device,
                costs=cost_model,
            )
            result = train_ppo(
                train,
                val,
                cfg,
                settings.models_dir,
                model_id=f"wf-f{fold.fold_id}-s{seed}-{args.timesteps}",
            )
            strategies.append(
                (
                    f"ppo-{args.timesteps}",
                    PpoPolicyStrategy.from_dir(result.record.model_dir),
                    seed,
                )
            )
        rows = evaluate_strategies_on_slice(
            val,
            strategies,  # type: ignore[arg-type]
            fold_id=fold.fold_id,
            cost_model=cost_model,
        )
        all_rows.extend(rows)
        print(f"fold {fold.fold_id} done: {len(rows)} evaluations")
    path = save_results(
        all_rows,
        Path("artifacts/walkforward"),
        extra={"folds": len(folds), "seeds": seeds, "timesteps": args.timesteps},
    )
    print(f"results: {path}")
    print(summarize(all_rows).to_string())
    return 0


def cmd_holdout(args: argparse.Namespace) -> int:
    """Run the final untouched holdout ONCE for one selected model."""
    from pathlib import Path

    from obsidian_rl.evaluation.walkforward import (
        evaluate_strategies_on_slice,
        save_results,
        slice_candles,
        summarize,
    )
    from obsidian_rl.portfolio.costs import CostModel
    from obsidian_rl.strategies.baselines import default_baselines
    from obsidian_rl.strategies.ppo_policy import PpoPolicyStrategy

    candles = _load_range(args.holdout_start, args.end)
    holdout = slice_candles(
        candles,
        _parse_utc_date(args.holdout_start),
        _parse_utc_date(args.end) if args.end else 2**62,
    )
    strategies: list[tuple[str, object, int | None]] = [
        (b.strategy_id, b, None)  # type: ignore[attr-defined]
        for b in default_baselines()
    ]
    if args.model_dir:
        strat = PpoPolicyStrategy.from_dir(Path(args.model_dir))
        strategies.append((strat.strategy_id, strat, None))
    rows = evaluate_strategies_on_slice(
        holdout,
        strategies,  # type: ignore[arg-type]
        fold_id=-1,
        cost_model=CostModel(),
    )
    path = save_results(rows, Path("artifacts/holdout"), extra={"model_dir": args.model_dir})
    print(f"results: {path}")
    print(summarize(rows).to_string())
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

    p = sub.add_parser("walk-forward", help="walk-forward evaluation of PPO vs baselines")
    p.add_argument("--data-start", default="2020-01-01")
    p.add_argument("--holdout-start", default="2025-07-01", help="folds never touch this period")
    p.add_argument("--train-days", type=int, default=720)
    p.add_argument("--val-days", type=int, default=180)
    p.add_argument("--step-days", type=int, default=270)
    p.add_argument("--seeds", default="42,43,44")
    p.add_argument("--timesteps", type=int, default=150_000)
    p.add_argument("--n-envs", type=int, default=8)
    p.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda"])
    p.add_argument("--skip-ppo", action="store_true", help="baselines only")
    p.set_defaults(func=cmd_walk_forward)

    p = sub.add_parser("holdout", help="run the untouched final holdout ONCE for one model")
    p.add_argument("--holdout-start", default="2025-07-01")
    p.add_argument("--end", default=None)
    p.add_argument("--model-dir", default=None, help="validated model registry directory")
    p.set_defaults(func=cmd_holdout)

    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
