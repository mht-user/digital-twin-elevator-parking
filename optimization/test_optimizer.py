from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from optimizer import calculate_metrics, objective_tuple
from se_bridge import SimulationEngineerBridge


HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent


def read_csv(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate Optimization Engineer outputs"
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
        "--output-dir",
        default=str(HERE / "output"),
    )
    parser.add_argument(
        "--scenario",
        choices=["Normal", "Worst"],
        default="Normal",
    )
    parser.add_argument("--include-events", action="store_true")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    required_files = [
        output_dir / "recommendations.json",
        output_dir / "optimized_schedule.csv",
        output_dir / "optimization_history.csv",
    ]
    missing = [str(path) for path in required_files if not path.exists()]
    if missing:
        print("FAIL | Missing output files:")
        for path in missing:
            print("  ", path)
        print("Run run_optimizer.py first.")
        return 1

    payload = json.loads(
        (output_dir / "recommendations.json").read_text(encoding="utf-8")
    )
    optimized = read_csv(output_dir / "optimized_schedule.csv")
    history = read_csv(output_dir / "optimization_history.csv")

    bridge = SimulationEngineerBridge(args.se_file)
    data = bridge.load_dataset(args.dataset_dir)
    baseline = data["schedule"]

    baseline_results = bridge.simulate(
        baseline,
        data["events"],
        data["parking"],
        args.scenario,
        args.include_events,
    )
    final_results = bridge.simulate(
        optimized,
        data["events"],
        data["parking"],
        args.scenario,
        args.include_events,
    )

    before_metrics = calculate_metrics(baseline, baseline_results)
    after_metrics = calculate_metrics(optimized, final_results)

    checks = []

    def check(name: str, condition: bool):
        checks.append((name, bool(condition)))

    before_by_id = {row["schedule_id"]: row for row in baseline}
    after_by_id = {row["schedule_id"]: row for row in optimized}

    check("Same number of schedule rows", len(baseline) == len(optimized))
    check(
        "schedule_id set unchanged",
        set(before_by_id) == set(after_by_id),
    )

    changed_ids = []
    for schedule_id in before_by_id:
        before = before_by_id[schedule_id]
        after = after_by_id[schedule_id]
        if (
            before["day_of_week"] != after["day_of_week"]
            or before["shift"] != after["shift"]
            or before["room_id"] != after["room_id"]
        ):
            changed_ids.append(schedule_id)

    expected_moves = payload["moves_applied"]
    check(
        "Changed-session count equals moves applied",
        len(changed_ids) == expected_moves,
    )

    move_ids = [move["schedule_id"] for move in payload["moves"]]
    check("Each moved session is unique", len(move_ids) == len(set(move_ids)))
    check(
        "Changed sessions match recommendation history",
        set(changed_ids) == set(move_ids),
    )

    rooms = {room["room_id"]: room for room in data["rooms"]}

    all_target_rooms_valid = True
    all_buildings_preserved = True
    all_class_student_preserved = True

    for schedule_id in move_ids:
        before = before_by_id[schedule_id]
        after = after_by_id[schedule_id]

        if before["building"] != after["building"]:
            all_buildings_preserved = False

        if (
            before["class_id"] != after["class_id"]
            or before["num_students"] != after["num_students"]
        ):
            all_class_student_preserved = False

        room = rooms.get(after["room_id"])
        if (
            room is None
            or room["building"] != after["building"]
            or int(room["room_capacity"]) < int(after["num_students"])
        ):
            all_target_rooms_valid = False

    check("Buildings preserved for all moves", all_buildings_preserved)
    check(
        "Class identity/student count preserved for all moves",
        all_class_student_preserved,
    )
    check("All target rooms valid and large enough", all_target_rooms_valid)

    room_slots = set()
    room_conflict = False
    for row in optimized:
        key = (
            row["day_of_week"],
            row["shift"],
            row["room_id"],
        )
        if key in room_slots:
            room_conflict = True
            break
        room_slots.add(key)
    check("No room conflict", not room_conflict)

    class_slots = set()
    class_conflict = False
    for row in optimized:
        key = (
            row["class_id"],
            row["day_of_week"],
            row["shift"],
        )
        if key in class_slots:
            class_conflict = True
            break
        class_slots.add(key)
    check("No same-class same-slot conflict", not class_conflict)

    check(
        "Final OE objective improves over baseline",
        objective_tuple(after_metrics) < objective_tuple(before_metrics)
        if expected_moves > 0
        else objective_tuple(after_metrics) == objective_tuple(before_metrics),
    )

    # Every accepted move must improve total-overload / objective monotonically.
    history_monotonic = True
    previous_after = None
    for row in history:
        before_overload = float(row["total_overload_before"])
        after_overload = float(row["total_overload_after"])
        if after_overload >= before_overload:
            history_monotonic = False
            break
        if previous_after is not None and abs(before_overload - previous_after) > 1e-9:
            history_monotonic = False
            break
        previous_after = after_overload

    check("Optimization history improves monotonically", history_monotonic)

    saved_after = payload["after"]
    check(
        "Saved final metrics match fresh official-SE evaluation",
        abs(
            saved_after["total_overload_excess"]
            - after_metrics["total_overload_excess"]
        ) < 1e-9
        and abs(
            saved_after["max_worst_util"]
            - after_metrics["max_worst_util"]
        ) < 1e-9
        and int(saved_after["bottleneck_points"])
        == int(after_metrics["bottleneck_points"]),
    )

    # Ensure the new SE slot-based interface is really being consumed.
    check(
        "Official SE output contains slot-based flow fields",
        bool(final_results)
        and all(
            key in final_results[0]
            for key in [
                "slot",
                "incoming",
                "outgoing",
                "checkin_util",
                "checkout_util",
                "worst_util",
                "bottleneck_direction",
            ]
        ),
    )

    print("OPTIMIZATION ENGINEER TEST")
    print("-" * 78)
    for name, ok in checks:
        print(f"{'PASS' if ok else 'FAIL':4} | {name}")
    print("-" * 78)

    status = all(ok for _, ok in checks)
    print("STATUS:", "PASS" if status else "FAIL")
    return 0 if status else 1


if __name__ == "__main__":
    sys.exit(main())
