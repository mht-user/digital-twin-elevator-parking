from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from optimizer import optimize_multi_move
from se_bridge import SimulationEngineerBridge


HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    if not rows:
        path.write_text("", encoding="utf-8")
        return

    fieldnames = []
    seen = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                fieldnames.append(key)

    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Optimization Engineer - Iterative Multi-Move"
    )
    parser.add_argument(
        "--se-file",
        default=str(PROJECT_ROOT / "run_simulation.py"),
    )
    parser.add_argument(
        "--dataset-dir",
        default=str(PROJECT_ROOT / "Dataset"),
    )
    parser.add_argument(
        "--scenario",
        choices=["Normal", "Worst"],
        default="Normal",
    )
    parser.add_argument(
        "--include-events",
        action="store_true",
        help="Include fixed events in SE evaluation",
    )
    parser.add_argument(
        "--max-moves",
        type=int,
        default=3,
        help="Maximum number of schedule moves (default: 3)",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=10,
        help="Save top K candidates for each iteration",
    )
    parser.add_argument(
        "--output-dir",
        default=str(HERE / "output"),
    )
    args = parser.parse_args()

    bridge = SimulationEngineerBridge(args.se_file)
    data = bridge.load_dataset(args.dataset_dir)

    result = optimize_multi_move(
        bridge=bridge,
        schedule=data["schedule"],
        rooms=data["rooms"],
        parking=data["parking"],
        events=data["events"],
        scenario=args.scenario,
        include_events=args.include_events,
        max_moves=args.max_moves,
        top_k=args.top_k,
    )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    write_csv(
        output_dir / "baseline_simulation.csv",
        result.baseline_results,
    )
    write_csv(
        output_dir / "final_simulation.csv",
        result.final_results,
    )
    write_csv(
        output_dir / "optimized_schedule.csv",
        result.optimized_schedule,
    )
    write_csv(
        output_dir / "optimization_history.csv",
        result.moves,
    )
    write_csv(
        output_dir / "candidate_history.csv",
        result.candidate_history,
    )

    metric_names = [
        "bottleneck_points",
        "peak_points",
        "total_overload_excess",
        "max_worst_util",
        "daily_load_std",
        "day_shift_load_std",
    ]
    write_csv(
        output_dir / "before_after_metrics.csv",
        [
            {
                "metric": metric,
                "before": result.baseline_metrics[metric],
                "after": result.final_metrics[metric],
            }
            for metric in metric_names
        ],
    )

    payload = {
        "scenario": result.scenario,
        "include_events": result.include_events,
        "max_moves": result.max_moves,
        "moves_applied": len(result.moves),
        "stop_reason": result.stop_reason,
        "simulation_source": "official Simulation Engineer run_simulation.py",
        "total_evaluated_candidates": result.total_evaluated_candidates,
        "total_improving_candidates": result.total_improving_candidates,
        "before": result.baseline_metrics,
        "after": result.final_metrics,
        "moves": result.moves,
    }
    (output_dir / "recommendations.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("=" * 84)
    print(f"Scenario              : {result.scenario}")
    print(f"Include events        : {result.include_events}")
    print(f"Max moves             : {result.max_moves}")
    print(f"Moves applied         : {len(result.moves)}")
    print(f"Stop reason           : {result.stop_reason}")
    print(f"Candidates evaluated  : {result.total_evaluated_candidates}")
    print()

    if result.moves:
        print("MOVE HISTORY")
        for move in result.moves:
            print(
                f"  #{move['move_no']} {move['schedule_id']} | "
                f"{move['from_day']} {move['from_shift']} {move['from_room']} "
                f"-> {move['to_day']} {move['to_shift']} {move['to_room']}"
            )
            print(
                f"     source bottleneck: "
                f"{move['source_bottleneck_day']} "
                f"{move['source_bottleneck_slot']} "
                f"{move['source_bottleneck_lot']} "
                f"{move['source_bottleneck_direction']} | "
                f"{pct(move['source_worst_util_before'])} "
                f"-> {pct(move['source_worst_util_after'])}"
            )
        print()

    before = result.baseline_metrics
    after = result.final_metrics

    print("GLOBAL BEFORE -> AFTER")
    print(
        f"  Bottlenecks         : {before['bottleneck_points']}"
        f" -> {after['bottleneck_points']}"
    )
    print(
        f"  Peak points (info)  : {before['peak_points']}"
        f" -> {after['peak_points']}"
    )
    print(
        f"  Total overload      : {before['total_overload_excess']:.4f}"
        f" -> {after['total_overload_excess']:.4f}"
    )
    print(
        f"  Max worst util      : {pct(before['max_worst_util'])}"
        f" -> {pct(after['max_worst_util'])}"
    )
    print(
        f"  Daily load std      : {before['daily_load_std']:.2f}"
        f" -> {after['daily_load_std']:.2f}"
    )
    print(
        f"  Day/shift load std  : {before['day_shift_load_std']:.2f}"
        f" -> {after['day_shift_load_std']:.2f}"
    )
    print()
    print(f"Outputs               : {output_dir}")


if __name__ == "__main__":
    main()
