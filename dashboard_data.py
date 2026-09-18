"""
dashboard_data.py
=========================================================================
Xuat 1 file JSON DUY NHAT gom du lieu can cho dashboard (Digital Twin
Lite - lich hoc & bai xe NEU):

  - meta                : thong tin chay (thoi diem, scenario, dataset,
                           optimizer co san hay khong, so move da ap dung)
  - summary[scenario]    : before/after cac chi so tong hop (bottleneck,
                           overload, max util, load std...) - dung de
                           lam card KPI
  - grid[scenario]       : FULL GRID before/after - moi (ngay, slot,
                           bai xe) du co phat sinh nhu cau hay khong -
                           dung de ve heatmap/bieu do theo thoi gian
  - event_impact         : rieng cac (ngay, slot) bi anh huong boi
                           events.csv - so sanh demand khi TAT/BAT event
  - daily_load[before/after] : tong SV theo ngay va theo (ngay, ca hoc)
                           - dung ve bar chart can bang tai
  - moves                : danh sach move OE da ap dung (neu co optimizer)
  - reference             : bang tra cuu tinh (rooms theo building,
                           suc chua bai xe theo scenario) cho dashboard
                           filter/legend

Cach chay (dat cung cap voi run_simulation.py, code OE trong ./optimize/):
    python3 dashboard_data.py
    python3 dashboard_data.py --scenarios Normal,Worst --output dashboard_data.json

Neu thu muc optimize/ chua co (vd OE chua nop bai), script VAN CHAY duoc -
chi la phan "after" / "moves" se bi bo qua va "meta.optimizer_available"
= false, thay vi crash ca file.
=========================================================================
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from run_simulation import (
    DAY_ORDER,
    SLOT_ORDER,
    build_event_shift_slot_map,
    load_dataset,
    run_simulation_from_data,
    validate_dataset,
)

HERE = Path(__file__).resolve().parent
OPTIMIZER_DIR = HERE / "optimize"

# ---------------------------------------------------------------------
# Adapter voi package OE (./optimize/) - cung 1 kieu voi test_pipeline.py:
# KHONG sua file nao trong optimize/, chi goi vao 2 ham cong khai.
# Neu thieu, dashboard van xuat duoc phan "before" (baseline), chi bo
# qua phan "after"/"moves".
# ---------------------------------------------------------------------
try:
    sys.path.insert(0, str(OPTIMIZER_DIR))
    from se_bridge import SimulationEngineerBridge  # trong optimize/
    from optimizer import calculate_metrics, optimize_multi_move  # trong optimize/

    _OPTIMIZER_IMPORT_ERROR: Optional[Exception] = None
except (ImportError, FileNotFoundError, AttributeError) as exc:  # pragma: no cover
    SimulationEngineerBridge = None  # type: ignore
    calculate_metrics = None  # type: ignore
    optimize_multi_move = None  # type: ignore
    _OPTIMIZER_IMPORT_ERROR = exc

SCENARIOS = ("Normal", "Worst")
DAYS_USED = [d for d in DAY_ORDER if d != "Sun"]  # dataset chi dung Mon-Sat


def _f(value) -> float:
    return float(value)


def _i(value) -> int:
    return int(float(value))


# ---------------------------------------------------------------------
# Grid + summary (dung chung 1 lan simulate full_grid cho ca 2 muc dich,
# tranh goi SE 2 lan cho cung 1 schedule/scenario)
# ---------------------------------------------------------------------

def simulate_full_grid(schedule, events, parking, scenario, include_events=True):
    return run_simulation_from_data(
        schedule=schedule,
        events=events,
        parking=parking,
        scenario=scenario,
        include_events=include_events,
        full_grid=True,
    )


def summarize(schedule, grid_results) -> dict:
    """Metrics tong hop - dung y het cong thuc OE dang dung
    (optimizer.calculate_metrics) neu co san; neu khong co optimizer thi
    tu tinh lai bang cong thuc tuong duong de dashboard van co KPI."""
    if calculate_metrics is not None:
        return calculate_metrics(schedule, grid_results)

    worst_utils = [_f(r["worst_util"]) for r in grid_results]
    daily = {d: 0.0 for d in DAYS_USED}
    day_shift = {(d, s): 0.0 for d in DAYS_USED for s in ("Ca1", "Ca2", "Ca3", "Ca4")}
    for row in schedule:
        d, s = row["day_of_week"], row["shift"]
        n = _f(row["num_students"])
        if d in daily:
            daily[d] += n
        if (d, s) in day_shift:
            day_shift[(d, s)] += n

    def _pstdev(values):
        values = list(values)
        n = len(values)
        if n == 0:
            return 0.0
        mean = sum(values) / n
        return (sum((v - mean) ** 2 for v in values) / n) ** 0.5

    return {
        "bottleneck_points": sum(r["status"] == "BOTTLENECK" for r in grid_results),
        "peak_points": sum(r["status"] == "PEAK" for r in grid_results),
        "total_overload_excess": sum(max(u - 1.0, 0.0) for u in worst_utils),
        "max_worst_util": max(worst_utils, default=0.0),
        "daily_load_std": _pstdev(daily.values()),
        "day_shift_load_std": _pstdev(day_shift.values()),
    }


def grid_to_json_rows(grid_results) -> List[dict]:
    """Sap xep on dinh (ngay -> slot -> bai xe) de dashboard ve chart
    khong bi lech thu tu giua cac lan chay."""
    day_index = {d: i for i, d in enumerate(DAY_ORDER)}
    slot_index = {s: i for i, s in enumerate(SLOT_ORDER)}

    def key(row):
        return (
            day_index.get(row["day"], 99),
            slot_index.get(row["shift"], 99),
            row["lot_id"],
        )

    rows = sorted(grid_results, key=key)
    return [
        {
            "day": r["day"],
            "slot": r["shift"],  # flow-slot S0..S4 (KHONG phai Ca hoc)
            "lot_id": r["lot_id"],
            "incoming": round(_f(r["incoming"]), 4),
            "outgoing": round(_f(r["outgoing"]), 4),
            "checkin_util": round(_f(r["checkin_util"]), 6),
            "checkout_util": round(_f(r["checkout_util"]), 6),
            "worst_util": round(_f(r["worst_util"]), 6),
            "status": r["status"],
            "bottleneck_direction": r["bottleneck_direction"],
        }
        for r in rows
    ]


# ---------------------------------------------------------------------
# Event impact (BAT/TAT include_events tren CHINH schedule dang xet -
# quy doi Ca-shift trong events.csv sang flow-slot S0-S4 dung cach SE
# tu quy doi, khong so sanh tho "Ca2" voi "S1"/"S2")
# ---------------------------------------------------------------------

def affected_event_slots(events) -> set:
    shift_slot_map = build_event_shift_slot_map()
    slots = set()
    for e in events:
        arrival_slot, departure_slot = shift_slot_map[e["shift"]]
        slots.add((e["day_of_week"], arrival_slot))
        slots.add((e["day_of_week"], departure_slot))
    return slots


def event_impact(schedule, events, parking, scenario) -> List[dict]:
    if not events:
        return []

    slots = affected_event_slots(events)

    off = simulate_full_grid(schedule, events, parking, scenario, include_events=False)
    on = simulate_full_grid(schedule, events, parking, scenario, include_events=True)

    off_map = {(r["day"], r["shift"], r["lot_id"]): r for r in off}
    on_map = {(r["day"], r["shift"], r["lot_id"]): r for r in on}

    rows = []
    for key in sorted(on_map):
        day, slot, lot_id = key
        if (day, slot) not in slots:
            continue
        before = off_map.get(key)
        after = on_map[key]
        rows.append(
            {
                "day": day,
                "slot": slot,
                "lot_id": lot_id,
                "incoming_no_event": round(_f(before["incoming"]), 4) if before else 0.0,
                "incoming_with_event": round(_f(after["incoming"]), 4),
                "outgoing_no_event": round(_f(before["outgoing"]), 4) if before else 0.0,
                "outgoing_with_event": round(_f(after["outgoing"]), 4),
                "worst_util_no_event": round(_f(before["worst_util"]), 6) if before else 0.0,
                "worst_util_with_event": round(_f(after["worst_util"]), 6),
            }
        )
    return rows


# ---------------------------------------------------------------------
# Daily load breakdown (cho bar chart can bang tai theo ngay / ngay+ca)
# ---------------------------------------------------------------------

def daily_load_breakdown(schedule) -> dict:
    by_day: Dict[str, float] = defaultdict(float)
    by_day_shift: Dict[str, float] = defaultdict(float)

    for row in schedule:
        day = row["day_of_week"]
        shift = row["shift"]
        n = _f(row["num_students"])
        by_day[day] += n
        by_day_shift[f"{day}|{shift}"] += n

    return {
        "by_day": [
            {"day": d, "total_students": round(by_day.get(d, 0.0), 2)}
            for d in DAYS_USED
            if d in by_day
        ],
        "by_day_shift": [
            {
                "day": key.split("|")[0],
                "shift": key.split("|")[1],
                "total_students": round(value, 2),
            }
            for key, value in sorted(by_day_shift.items())
        ],
    }


# ---------------------------------------------------------------------
# Reference tables (cho filter/legend cua dashboard)
# ---------------------------------------------------------------------

def reference_tables(data: dict) -> dict:
    rooms_by_building: Dict[str, int] = defaultdict(int)
    for r in data["rooms"]:
        rooms_by_building[r["building"]] += 1

    parking_by_scenario: Dict[str, List[dict]] = defaultdict(list)
    for p in data["parking"]:
        parking_by_scenario[p["scenario"]].append(
            {
                "lot_id": p["parking_lot_id"],
                "name": p.get("name"),
                "capacity_slots": _i(p["capacity_slots"]),
                "max_checkin_throughput_veh_per_30min": _i(
                    p["max_checkin_throughput_veh_per_30min"]
                ),
                "max_checkout_throughput_veh_per_30min": _i(
                    p["max_checkout_throughput_veh_per_30min"]
                ),
            }
        )

    return {
        "rooms_by_building": dict(sorted(rooms_by_building.items())),
        "parking_by_scenario": {
            scenario: sorted(lots, key=lambda r: r["lot_id"])
            for scenario, lots in parking_by_scenario.items()
        },
        "num_classes": len(data["classes"]),
        "num_schedule_rows": len(data["schedule"]),
        "num_events": len(data["events"]),
    }


# ---------------------------------------------------------------------
# Optimizer (optional) - tra ve None neu package OE khong co san
# ---------------------------------------------------------------------

def get_optimized_schedule(
    data: dict,
    scenario: str,
    max_moves: int,
    top_k: int,
    include_events: bool,
) -> Optional[dict]:
    if SimulationEngineerBridge is None or optimize_multi_move is None:
        return None

    bridge = SimulationEngineerBridge(str(HERE / "run_simulation.py"))
    result = optimize_multi_move(
        bridge=bridge,
        schedule=data["schedule"],
        rooms=data["rooms"],
        parking=data["parking"],
        events=data["events"],
        scenario=scenario,
        include_events=include_events,
        max_moves=max_moves,
        top_k=top_k,
    )
    return {
        "optimized_schedule": result.optimized_schedule,
        "moves": result.moves,
        "stop_reason": result.stop_reason,
        "total_evaluated_candidates": result.total_evaluated_candidates,
        "total_improving_candidates": result.total_improving_candidates,
    }


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

def build_dashboard_data(
    dataset_dir: Path,
    se_file: Path,
    scenarios: List[str],
    include_events: bool,
    max_moves: int,
    top_k: int,
) -> dict:
    data = load_dataset(dataset_dir)
    validate_dataset(data)

    optimizer_available = SimulationEngineerBridge is not None and optimize_multi_move is not None

    summary: Dict[str, dict] = {}
    grid: Dict[str, dict] = {}
    daily_load: Dict[str, dict] = {}
    moves_by_scenario: Dict[str, list] = {}
    optimizer_notes: Dict[str, str] = {}

    for scenario in scenarios:
        baseline_grid = simulate_full_grid(
            data["schedule"], data["events"], data["parking"], scenario, include_events
        )
        baseline_summary = summarize(data["schedule"], baseline_grid)

        summary[scenario] = {"before": baseline_summary}
        grid[scenario] = {"before": grid_to_json_rows(baseline_grid)}
        daily_load[scenario] = {"before": daily_load_breakdown(data["schedule"])}

        opt = get_optimized_schedule(data, scenario, max_moves, top_k, include_events)
        if opt is None:
            optimizer_notes[scenario] = (
                f"optimize/ khong san sang ({_OPTIMIZER_IMPORT_ERROR}); "
                "chi co du lieu 'before'."
            )
            continue

        optimized_schedule = opt["optimized_schedule"]
        after_grid = simulate_full_grid(
            optimized_schedule, data["events"], data["parking"], scenario, include_events
        )
        after_summary = summarize(optimized_schedule, after_grid)

        summary[scenario]["after"] = after_summary
        grid[scenario]["after"] = grid_to_json_rows(after_grid)
        daily_load[scenario]["after"] = daily_load_breakdown(optimized_schedule)
        moves_by_scenario[scenario] = opt["moves"]

    # event_impact chi can tinh tren schedule GOC (before) - muc dich la
    # cho thay tac dong cua events.csv len demand, khong lien quan optimize.
    primary_scenario = scenarios[0]
    event_impact_rows = event_impact(
        data["schedule"], data["events"], data["parking"], primary_scenario
    )

    payload = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "scenarios": scenarios,
            "include_events": include_events,
            "optimizer_available": optimizer_available,
            "max_moves": max_moves,
            "moves_applied": {
                scenario: len(moves_by_scenario.get(scenario, []))
                for scenario in scenarios
            },
            "optimizer_notes": optimizer_notes,
        },
        "summary": summary,
        "grid": grid,
        "event_impact": {
            "scenario": primary_scenario,
            "rows": event_impact_rows,
        },
        "daily_load": daily_load,
        "moves": moves_by_scenario,
        "reference": reference_tables(data),
    }
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Xuat du lieu tong hop (before/after + full grid) cho dashboard"
    )
    parser.add_argument("--dataset-dir", default=str(HERE / "Dataset"))
    parser.add_argument("--se-file", default=str(HERE / "run_simulation.py"))
    parser.add_argument(
        "--scenarios",
        default="Normal,Worst",
        help="Danh sach scenario, cach nhau boi dau phay (mac dinh: Normal,Worst)",
    )
    parser.add_argument(
        "--no-events",
        action="store_true",
        help="Tat events.csv khi tinh before/after chinh (mac dinh: BAT)",
    )
    parser.add_argument("--max-moves", type=int, default=3)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--output", default=str(HERE / "dashboard_data.json"))
    args = parser.parse_args()

    scenarios = [s.strip() for s in args.scenarios.split(",") if s.strip()]
    invalid = [s for s in scenarios if s not in SCENARIOS]
    if invalid:
        parser.error(f"Scenario khong hop le: {invalid} (chi nhan {list(SCENARIOS)})")

    payload = build_dashboard_data(
        dataset_dir=Path(args.dataset_dir),
        se_file=Path(args.se_file),
        scenarios=scenarios,
        include_events=not args.no_events,
        max_moves=args.max_moves,
        top_k=args.top_k,
    )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("=" * 78)
    print(f"Optimizer available   : {payload['meta']['optimizer_available']}")
    for scenario in scenarios:
        before = payload["summary"][scenario]["before"]
        after = payload["summary"][scenario].get("after")
        print(f"[{scenario}]")
        print(f"  bottleneck_points     : {before['bottleneck_points']}", end="")
        print(f" -> {after['bottleneck_points']}" if after else " (chua optimize)")
        if after is not None:
            print(
                f"  total_overload_excess : {before['total_overload_excess']:.4f} "
                f"-> {after['total_overload_excess']:.4f}"
            )
            print(
                f"  max_worst_util        : {before['max_worst_util']:.4f} "
                f"-> {after['max_worst_util']:.4f}"
            )
            print(f"  moves_applied         : {payload['meta']['moves_applied'][scenario]}")
    print(f"Event-impact rows      : {len(payload['event_impact']['rows'])}")
    print(f"Output                 : {output_path}")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
