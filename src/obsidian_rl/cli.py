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
    from obsidian_rl.env.trading_env import RewardConfig
    from obsidian_rl.evaluation.holdout import check_reserved_period_overlap
    from obsidian_rl.training.ppo import PpoHyperparams, TrainConfig, train_ppo

    settings = get_settings()
    train_candles = _load_range(args.train_start, args.train_end)
    eval_candles = _load_range(args.eval_start, args.eval_end)
    check_reserved_period_overlap(
        _parse_utc_date(args.train_start),
        _parse_utc_date(args.train_end),
        train_candles,
        purpose="training",
        settings=settings,
    )
    check_reserved_period_overlap(
        _parse_utc_date(args.eval_start),
        _parse_utc_date(args.eval_end) if args.eval_end else None,
        eval_candles,
        purpose="training evaluation",
        settings=settings,
    )
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
            reward=RewardConfig(turnover_penalty_bps=args.turnover_penalty_bps),
        )
    else:
        cfg = TrainConfig(
            total_timesteps=args.timesteps,
            n_envs=args.n_envs,
            seed=args.seed,
            device=args.device,
            reward=RewardConfig(turnover_penalty_bps=args.turnover_penalty_bps),
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
    from dataclasses import asdict
    from pathlib import Path

    from obsidian_rl.env.trading_env import RewardConfig
    from obsidian_rl.evaluation.holdout import check_reserved_period_overlap, get_holdout_start_ms
    from obsidian_rl.evaluation.walkforward import (
        create_experiment_id,
        evaluate_strategies_on_slice,
        make_folds,
        save_results,
        slice_candles,
        summarize,
    )
    from obsidian_rl.portfolio.costs import CostModel
    from obsidian_rl.strategies.baselines import default_baselines

    settings = get_settings()
    holdout_ms = _parse_utc_date(args.holdout_start)
    if holdout_ms > get_holdout_start_ms(settings):
        raise ValueError("walkforward holdout_start cannot exceed central reserved boundary")
    end_val_ms = holdout_ms - 1
    store = CandleStore(settings.data_dir, settings.symbol, settings.interval)
    candles = store.read(_parse_utc_date(args.data_start), end_val_ms)
    if candles.empty:
        raise SystemExit("no candles in requested range — run data-download first")
    check_reserved_period_overlap(
        _parse_utc_date(args.data_start),
        end_val_ms,
        candles,
        purpose="walkforward",
        settings=settings,
    )
    folds = make_folds(
        _parse_utc_date(args.data_start),
        holdout_ms,
        candles=candles,
        train_days=args.train_days,
        inner_eval_days=args.inner_eval_days,
        val_days=args.val_days,
        step_days=args.step_days,
    )
    seeds = [int(s) for s in args.seeds.split(",")] if not args.skip_ppo else []
    cost_model = CostModel()
    reward_config = RewardConfig(turnover_penalty_bps=args.turnover_penalty_bps)
    experiment_id = create_experiment_id(args.turnover_penalty_bps)
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
            inner_val = slice_candles(candles, fold.inner_eval_start_ms, fold.inner_eval_end_ms)
            cfg = TrainConfig(
                total_timesteps=args.timesteps,
                n_envs=args.n_envs,
                seed=seed,
                device=args.device,
                costs=cost_model,
                reward=reward_config,
            )
            model_id = f"{experiment_id}-f{fold.fold_id}-s{seed}"
            result = train_ppo(
                train,
                inner_val,
                cfg,
                settings.models_dir,
                model_id=model_id,
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
        extra={
            "cost_model": asdict(cost_model),
            "reward_config": asdict(reward_config),
            "turnover_penalty_bps": args.turnover_penalty_bps,
            "seeds": seeds,
            "timesteps": args.timesteps,
            "n_envs": args.n_envs,
            "fold_specs": [f.to_dict() for f in folds],
        },
        experiment_id=experiment_id,
    )
    print(f"results: {path}")
    print(summarize(all_rows).to_string())
    return 0


def cmd_holdout(args: argparse.Namespace) -> int:
    """Run the final untouched holdout ONCE for one selected model."""
    from obsidian_rl.evaluation.holdout import run_final_holdout

    settings = get_settings()
    rep_path, report_hash = run_final_holdout(settings, args.model_id, args.end)
    print("holdout completed")
    print(f"model_id: {args.model_id}")
    print(f"report path: {rep_path}")
    print(f"report sha256: {report_hash}")
    return 0


def _strategy_from_args(model_dir: str | None) -> tuple[object, str | None]:
    from pathlib import Path

    from obsidian_rl.strategies.baselines import RegimeFilteredMomentum
    from obsidian_rl.strategies.ppo_policy import PpoPolicyStrategy

    if model_dir:
        strat = PpoPolicyStrategy.from_dir(Path(model_dir))
        return strat, strat.strategy_id.removeprefix("ppo:")
    return RegimeFilteredMomentum(), None


def cmd_replay(args: argparse.Namespace) -> int:
    """Historical replay through the live-paper decision path (same code as live)."""
    from obsidian_rl.evaluation.holdout import check_reserved_period_overlap
    from obsidian_rl.ledger.ledger import Ledger
    from obsidian_rl.live.paper_trader import PaperTrader, replay_candles

    settings = get_settings()
    candles = _load_range(args.start, args.end)
    check_reserved_period_overlap(
        _parse_utc_date(args.start),
        _parse_utc_date(args.end) if args.end else None,
        candles,
        purpose="replay",
        settings=settings,
    )
    strategy, model_id = _strategy_from_args(args.model_dir)
    ledger = Ledger(settings.ledger_path)
    run = ledger.start_run(
        getattr(strategy, "strategy_id", "unknown"),
        "replay",
        10_000.0,
        cost_model={},
        model_id=model_id,
    )
    trader = PaperTrader(
        strategy,  # type: ignore[arg-type]
        ledger,
        run.run_id,
        interval=settings.interval,
        data_source="replay",
    )
    n = replay_candles(trader, candles)
    last_close = float(candles["close"].iloc[-1])  # type: ignore[index]
    trader.close_session(last_close)
    print(
        json.dumps(
            {
                "run_id": run.run_id,
                "decisions": n,
                "final_equity": trader.engine.state.net_equity(last_close),
                "fees": trader.engine.state.fees_paid,
                "turnover": trader.engine.state.turnover,
                "trade_count": trader.engine.state.trade_count,
            },
            indent=1,
        )
    )
    return 0


def cmd_paper_trade(args: argparse.Namespace) -> int:
    """Live paper trading on finalized websocket candles. NO exchange orders, ever."""
    import asyncio

    from obsidian_rl.live.runner import LivePaperRunner

    settings = get_settings()
    strategy, model_id = _strategy_from_args(args.model_dir)
    runner = LivePaperRunner(
        settings,
        strategy,  # type: ignore[arg-type]
        run_id=args.run_id,
        model_id=model_id,
    )
    print(f"live-paper run {runner.run_id} (SIMULATED paper execution; public data only)")
    asyncio.run(runner.run())
    return 0


def cmd_candidate_eval(args: argparse.Namespace) -> int:
    from obsidian_rl.evaluation.holdout import check_reserved_period_overlap
    from obsidian_rl.training.promotion import evaluate_candidate, evaluation_report_path

    settings = get_settings()
    val = _load_range(args.val_start, args.val_end)
    check_reserved_period_overlap(
        _parse_utc_date(args.val_start),
        _parse_utc_date(args.val_end) if args.val_end else None,
        val,
        purpose="candidate evaluation",
        settings=settings,
    )
    report = evaluate_candidate(settings.models_dir, args.model_id, val)
    result = "passed" if report["passes"] else "failed"
    report_path = evaluation_report_path(settings.models_dir, args.model_id)
    print(f"candidate evaluation {result}; report: {report_path}")
    if not report["passes"]:
        print(f"gate failures: {'; '.join(report['failures'])}", file=sys.stderr)
    return 0 if report["passes"] else 1


def cmd_promote(args: argparse.Namespace) -> int:
    from obsidian_rl.training.promotion import PromotionEvidenceError, current_champion, promote
    from obsidian_rl.training.registry import ModelCompatibilityError

    settings = get_settings()
    try:
        promote(settings.models_dir, args.model_id)
    except (ModelCompatibilityError, PromotionEvidenceError) as exc:
        print(f"promotion refused: {exc}", file=sys.stderr)
        return 1
    print(f"champion is now {current_champion(settings.models_dir)}")
    return 0


def cmd_rollback(args: argparse.Namespace) -> int:
    from obsidian_rl.training.promotion import rollback

    settings = get_settings()
    restored = rollback(settings.models_dir)
    print(f"rolled back; champion is now {restored}")
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
    p.add_argument(
        "--turnover-penalty-bps",
        type=float,
        default=0.0,
        help="turnover regularization penalty in bps (default: 0.0)",
    )
    p.set_defaults(func=cmd_train)

    p = sub.add_parser("walk-forward", help="walk-forward evaluation of PPO vs baselines")
    p.add_argument("--data-start", default="2020-01-01")
    p.add_argument("--holdout-start", default="2025-07-01", help="folds never touch this period")
    p.add_argument("--train-days", type=int, default=720)
    p.add_argument("--inner-eval-days", type=int, default=60, help="inner selection/evaluation window in days")
    p.add_argument("--val-days", type=int, default=180)
    p.add_argument("--step-days", type=int, default=270)
    p.add_argument("--seeds", default="42,43,44")
    p.add_argument("--timesteps", type=int, default=150_000)
    p.add_argument("--n-envs", type=int, default=8)
    p.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda"])
    p.add_argument("--skip-ppo", action="store_true", help="baselines only")
    p.add_argument(
        "--turnover-penalty-bps",
        type=float,
        default=0.0,
        help="turnover regularization penalty in bps (default: 0.0)",
    )
    p.set_defaults(func=cmd_walk_forward)

    p = sub.add_parser("holdout", help="run the untouched final holdout ONCE for one model")
    p.add_argument("--model-id", required=True, help="exact model ID matching current champion")
    p.add_argument("--end", required=True, help="fixed UTC end boundary for final holdout")
    p.set_defaults(func=cmd_holdout)

    p = sub.add_parser("replay", help="historical replay through the live-paper path")
    p.add_argument("--start", required=True)
    p.add_argument("--end", default=None)
    p.add_argument("--model-dir", default=None, help="frozen model dir (default: regime baseline)")
    p.set_defaults(func=cmd_replay)

    p = sub.add_parser(
        "paper-trade", help="live paper trading (public data, simulated fills, NO orders)"
    )
    p.add_argument("--model-dir", default=None, help="frozen model dir (default: regime baseline)")
    p.add_argument("--run-id", default=None, help="resume an existing ledger run")
    p.set_defaults(func=cmd_paper_trade)

    p = sub.add_parser("candidate-eval", help="gate a candidate on a validation period")
    p.add_argument("--model-id", required=True)
    p.add_argument("--val-start", required=True)
    p.add_argument("--val-end", default=None)
    p.set_defaults(func=cmd_candidate_eval)

    p = sub.add_parser("promote", help="explicitly promote a candidate to champion")
    p.add_argument("--model-id", required=True)
    p.set_defaults(func=cmd_promote)

    p = sub.add_parser("rollback", help="restore the previous champion")
    p.set_defaults(func=cmd_rollback)

    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
