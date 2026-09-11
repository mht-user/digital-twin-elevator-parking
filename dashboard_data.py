"""
dashboard_data.py (v3)
=========================================================================
Ghep noi run_simulation_from_data() (Simulation Engineer, ban chinh thuc)
thanh dung 3 khoi du lieu Front-end can:
    - heatmap      -> "Current Schedule Heatmap"
    - kpi          -> "KPI"
    - parking_view -> "Parking View"

Khong dung pandas - lam viec truc tiep tren List[dict] cho khop voi
kieu du lieu that su cua run_simulation.py ban chot.

Cach chay:
    python3 dashboard_data.py --scenario Normal
    python3 dashboard_data.py --scenario Worst --no-events
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path

from run_simulation import DATASET_DIR, load_dataset, run_simulation_from_data

DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
SHIFT_LABELS = ["Ca1", "Ca2", "Ca3", "Ca4"]


def build_heatmap(schedule: list) -> dict:
    """Tong SV (cong don 4 toa) theo (ngay, ca) -> khoi Heatmap."""
    totals = defaultdict(int)
    for row in schedule:
        key = (row["day_of_week"], row["shift"])
        totals[key] += int(row["num_students"])

    heatmap = {day: {shift: 0 for shift in SHIFT_LABELS} for day in DAY_LABELS}
    for (day, shift), total in totals.items():
        if day in heatmap and shift in heatmap[day]:
            heatmap[day][shift] = total
    return heatmap


def build_kpi(schedule: list, parking_view: list) -> dict:
    total_sessions = len(schedule)
    total_students = sum(int(r["num_students"]) for r in schedule)

    heatmap = build_heatmap(schedule)
    peak_day, peak_shift, peak_value = None, None, -1
    for day, shifts in heatmap.items():
        for shift, value in shifts.items():
            if value > peak_value:
                peak_day, peak_shift, peak_value = day, shift, value
    peak_demand = {"day": peak_day, "shift": peak_shift, "value": peak_value}

    worst_row = max(parking_view, key=lambda r: r["worst_util"])
    worst_parking = {
        "lot": worst_row["parking_lot"],
        "day": worst_row["day"],
        "shift": worst_row["shift"],
        "direction": worst_row["bottleneck_direction"],
        "utilization_pct": round(worst_row["worst_util"] * 100),
    }
    worst_day_time = {"day": worst_row["day"], "shift": worst_row["shift"]}

    return {
        "total_sessions": total_sessions,
        "total_students": total_students,
        "peak_demand": peak_demand,
        "worst_parking": worst_parking,
        "worst_day_time": worst_day_time,
    }


def build_parking_view(results: list) -> list:
    """Giu nguyen 2 chieu checkin/checkout tach rieng - KHONG gop lam 1
    cot 'capacity'/'utilization' chung chung nhu ban truoc (day la dung
    gop y cua leader: phai ro rang dang do nghen o cong nao)."""
    view = []
    for r in results:
        view.append({
            "day": r["day"],
            "shift": r["shift"],
            "parking_lot": r["lot_id"],
            "incoming": r["incoming"],
            "outgoing": r["outgoing"],
            "checkin_capacity": r["checkin_capacity"],
            "checkout_capacity": r["checkout_capacity"],
            "checkin_utilization_pct": round(r["checkin_util"] * 100),
            "checkout_utilization_pct": round(r["checkout_util"] * 100),
            "worst_utilization_pct": round(r["worst_util"] * 100),
            "worst_util": r["worst_util"],
            "bottleneck_direction": r["bottleneck_direction"],
            "status": r["status"],
        })
    return view


def build_dashboard_payload(schedule=None, events=None, parking=None,
                             scenario: str = "Normal", include_events: bool = True,
                             dataset_dir: Path = DATASET_DIR) -> dict:
    """Nhan schedule/events/parking o dang du lieu san co (list[dict]) -
    dung khi can chay lai simulation tren schedule da toi uu (Before/After,
    vd sau khi goi make_what_if_schedule() hoac recommend_best_move()).
    Neu khong truyen gi, tu doc tu dataset_dir (dung cho lan chay dau)."""
    if schedule is None or events is None or parking is None:
        data = load_dataset(dataset_dir)
        schedule = data["schedule"]
        events = data["events"]
        parking = data["parking"]

    results = run_simulation_from_data(schedule, events, parking, scenario=scenario, include_events=include_events)
    parking_view = build_parking_view(results)

    return {
        "scenario": scenario,
        "include_events": include_events,
        "heatmap": build_heatmap(schedule),
        "kpi": build_kpi(schedule, parking_view),
        "parking_view": [{k: v for k, v in row.items() if k != "worst_util"} for row in parking_view],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build dashboard-ready JSON from run_simulation_from_data()")
    parser.add_argument("--scenario", default="Normal", choices=["Normal", "Worst"])
    parser.add_argument("--no-events", action="store_true", help="Bo qua events.csv")
    parser.add_argument("--dataset-dir", type=str, default=str(DATASET_DIR))
    args = parser.parse_args()

    payload = build_dashboard_payload(
        scenario=args.scenario,
        include_events=not args.no_events,
        dataset_dir=Path(args.dataset_dir),
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
