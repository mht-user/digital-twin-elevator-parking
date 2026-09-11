from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

# Cau hinh chung

BASE_DIR = Path(__file__).resolve().parent
DATASET_DIR = BASE_DIR / "Dataset"

BUILDINGS = ["A2", "B", "C", "D"]
PARKING_LOTS = ["P1", "P2", "P3", "P4"]

# Thu tu hien thi ngay trong tuan
DAY_ORDER = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
SHIFT_ORDER = ["Ca1", "Ca2", "Ca3", "Ca4"]

PEAK_THRESHOLD = 0.90       # >=90% va <=100% -> PEAK
BOTTLENECK_THRESHOLD = 1.0  # > 100% -> BOTTLENECK

# Doc du lieu tu CSV (hoan toan tach rieng khoi core simulation)

def read_csv(path: Path) -> List[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def load_dataset(dataset_dir: Path = DATASET_DIR) -> Dict[str, List[dict]]:
    return {
        "classes": read_csv(dataset_dir / "classes.csv"),
        "schedule": read_csv(dataset_dir / "schedule.csv"),
        "rooms": read_csv(dataset_dir / "rooms.csv"),
        "parking": read_csv(dataset_dir / "parking.csv"),
        "events": read_csv(dataset_dir / "events.csv"),
    }

# Gop nhu cau xe theo (Ngay, Ca, Toa)

def build_building_demand(
    schedule: List[dict],
    events: List[dict],
    include_events: bool = True,
) -> Dict[Tuple[str, str, str], float]:
    demand: Dict[Tuple[str, str, str], float] = defaultdict(float)

    for row in schedule:
        key = (row["day_of_week"], row["shift"], row["building"])
        num_students = float(row["num_students"])
        motorbike_ratio = float(row["motorbike_ratio"])
        demand[key] += num_students * motorbike_ratio

    if include_events:
        for row in events:
            key = (row["day_of_week"], row["shift"], row["building"])
            num_students = float(row["num_students"])
            motorbike_ratio = float(row["motorbike_ratio"])
            demand[key] += num_students * motorbike_ratio

    return demand

# Trong so khoang cach & phan bo xe ve P1..P4

def get_distance_weights(
    parking_rows: List[dict], scenario: str
) -> Dict[str, Dict[str, float]]:
    weights: Dict[str, Dict[str, float]] = {}

    lots = [r for r in parking_rows if r["scenario"] == scenario]
    if len(lots) != len(PARKING_LOTS):
        raise ValueError(
            f"Khong tim thay du {len(PARKING_LOTS)} bai xe cho scenario "
            f"'{scenario}' trong parking.csv"
        )

    for building in BUILDINGS:
        col = f"dist_from_{building}_m"
        inv_distances = {}
        for lot in lots:
            dist = float(lot[col])
            if dist <= 0:
                raise ValueError(
                    f"Khoang cach khong hop le ({col}={dist}) cho bai "
                    f"{lot['parking_lot_id']}"
                )
            inv_distances[lot["parking_lot_id"]] = 1.0 / dist

        s = sum(inv_distances.values())  # s = tong 1/khoang_cach
        weights[building] = {lot_id: inv_d / s for lot_id, inv_d in inv_distances.items()}

    return weights


def distribute_vehicles_to_lots(
    building_demand: Dict[Tuple[str, str, str], float],
    distance_weights: Dict[str, Dict[str, float]],
) -> Dict[Tuple[str, str, str], float]:
    lot_demand: Dict[Tuple[str, str, str], float] = defaultdict(float)

    for (day, shift, building), total_motorbikes in building_demand.items():
        weights = distance_weights[building]
        for lot_id, w in weights.items():
            lot_demand[(day, shift, lot_id)] += total_motorbikes * w

    return lot_demand

# Nang luc xu ly TAI CONG (checkin / checkout throughput)

def get_gate_capacity(
    parking_rows: List[dict], scenario: str
) -> Dict[str, Dict[str, int]]:
    return {
        r["parking_lot_id"]: {
            "checkin": int(r["max_checkin_throughput_veh_per_30min"]),
            "checkout": int(r["max_checkout_throughput_veh_per_30min"]),
        }
        for r in parking_rows
        if r["scenario"] == scenario
    }


def classify_status(worst_ratio: float) -> str:
    if worst_ratio > BOTTLENECK_THRESHOLD:
        return "BOTTLENECK"
    if worst_ratio >= PEAK_THRESHOLD:
        return "PEAK"
    return "OK"


def get_bottleneck_direction(checkin_ratio: float, checkout_ratio: float) -> str:
    if max(checkin_ratio, checkout_ratio) < PEAK_THRESHOLD:
        return "-"
    if checkin_ratio == checkout_ratio:
        return "Both"
    return "Checkin" if checkin_ratio > checkout_ratio else "Checkout"

# CORE SIMULATION - nhan schedule/events/parking lam INPUT

def run_simulation_from_data(
    schedule: List[dict],
    events: List[dict],
    parking: List[dict],
    scenario: str = "Normal",
    include_events: bool = True,
) -> List[dict]:
    if scenario not in ("Normal", "Worst"):
        raise ValueError("scenario phai la 'Normal' hoac 'Worst'")

    # 1) nhu cau xe theo (ngay, ca, toa)
    building_demand = build_building_demand(schedule, events, include_events=include_events)

    # 2) trong so khoang cach + phan bo xe ve tung bai
    distance_weights = get_distance_weights(parking, scenario)
    lot_demand = distribute_vehicles_to_lots(building_demand, distance_weights)

    # 3) nang luc xu ly tai cong (checkin + checkout) theo scenario
    gate_capacity = get_gate_capacity(parking, scenario)

    # 4) ghep ket qua: tinh rieng checkin_util va checkout_util
    results = []
    for (day, shift, lot_id), demand in lot_demand.items():
        cap = gate_capacity[lot_id]
        checkin_capacity = cap["checkin"]
        checkout_capacity = cap["checkout"]

        incoming = demand
        outgoing = demand

        checkin_util = incoming / checkin_capacity if checkin_capacity else float("inf")
        checkout_util = outgoing / checkout_capacity if checkout_capacity else float("inf")
        worst_util = max(checkin_util, checkout_util)

        results.append(
            {
                "day": day,
                "shift": shift,
                "lot_id": lot_id,
                "incoming": round(incoming),
                "outgoing": round(outgoing),
                "checkin_capacity": checkin_capacity,
                "checkout_capacity": checkout_capacity,
                "checkin_util": checkin_util,
                "checkout_util": checkout_util,
                "worst_util": worst_util,
                "bottleneck_direction": get_bottleneck_direction(checkin_util, checkout_util),
                "status": classify_status(worst_util),
            }
        )

    results.sort(key=_sort_key)
    return results


def run_simulation(
    dataset_dir: Path = DATASET_DIR,
    scenario: str = "Normal",
    include_events: bool = True,
) -> List[dict]:
    data = load_dataset(dataset_dir)
    return run_simulation_from_data(
        schedule=data["schedule"],
        events=data["events"],
        parking=data["parking"],
        scenario=scenario,
        include_events=include_events,
    )


def run_scenarios(
    schedules: Dict[str, List[dict]],
    events: List[dict],
    parking: List[dict],
    scenario: str = "Normal",
    include_events: bool = True,
) -> Dict[str, List[dict]]:
    return {
        name: run_simulation_from_data(sched, events, parking, scenario, include_events)
        for name, sched in schedules.items()
    }


def compare_before_after(
    schedule_before: List[dict],
    schedule_after: List[dict],
    events: List[dict],
    parking: List[dict],
    scenario: str = "Normal",
    include_events: bool = True,
) -> Tuple[List[dict], List[dict]]:
    results = run_scenarios(
        {"before": schedule_before, "after": schedule_after},
        events, parking, scenario, include_events,
    )
    return results["before"], results["after"]


def make_what_if_schedule(
    schedule: List[dict],
    day_of_week: str,
    shift: str,
    building: Optional[str] = None,
    remove_class_ids: Optional[Iterable[str]] = None,
    add_rows: Optional[List[dict]] = None,
) -> List[dict]:
    remove_ids = set(remove_class_ids or [])

    def _should_drop(row: dict) -> bool:
        if row["day_of_week"] != day_of_week or row["shift"] != shift:
            return False
        if building is not None and row["building"] != building:
            return False
        return row["class_id"] in remove_ids

    new_schedule = [dict(row) for row in schedule if not _should_drop(row)]
    if add_rows:
        new_schedule.extend(dict(r) for r in add_rows)
    return new_schedule


def _sort_key(row: dict):
    day_idx = DAY_ORDER.index(row["day"]) if row["day"] in DAY_ORDER else 99
    shift_idx = SHIFT_ORDER.index(row["shift"]) if row["shift"] in SHIFT_ORDER else 99
    lot_idx = PARKING_LOTS.index(row["lot_id"]) if row["lot_id"] in PARKING_LOTS else 99
    return (day_idx, shift_idx, lot_idx)

# In / xuat ket qua

COLUMN_HEADERS = [
    "Day",
    "Shift",
    "Lot",
    "Incoming",
    "Outgoing",
    "Checkin Throughput",
    "Checkout Throughput",
    "Checkin Util",
    "Checkout Util",
    "Worst Util",
    "Bottleneck Direction",
    "Status",
]

# Canh le cho tung cot
COLUMN_ALIGN = ["<", "<", "<", ">", ">", ">", ">", ">", ">", ">", "<", "<"]


def format_shift(shift: str) -> str:
    if shift.startswith("Ca") and shift[2:].isdigit():
        return f"Ca {shift[2:]}"
    return shift


def result_to_row(r: dict) -> List[str]:
    return [
        r["day"],
        format_shift(r["shift"]),
        r["lot_id"],
        str(r["incoming"]),
        str(r["outgoing"]),
        str(r["checkin_capacity"]),
        str(r["checkout_capacity"]),
        f"{r['checkin_util'] * 100:.0f}%",
        f"{r['checkout_util'] * 100:.0f}%",
        f"{r['worst_util'] * 100:.0f}%",
        r["bottleneck_direction"],
        r["status"],
    ]


def render_table(headers: List[str], rows: List[List[str]]) -> List[str]:
    n_cols = len(headers)
    widths = [len(h) for h in headers]
    for row in rows:
        for i in range(n_cols):
            widths[i] = max(widths[i], len(row[i]))

    def fmt_row(cells: List[str]) -> str:
        parts = [f"{cell:{COLUMN_ALIGN[i]}{widths[i]}}" for i, cell in enumerate(cells)]
        return " | ".join(parts)

    lines = [fmt_row(headers)]
    lines.append("-+-".join("-" * w for w in widths))
    for row in rows:
        lines.append(fmt_row(row))
    return lines


def print_report(results: List[dict], scenario: str) -> None:
    print("Output")
    print(f"(Scenario: {scenario})")
    rows = [result_to_row(r) for r in results]
    for line in render_table(COLUMN_HEADERS, rows):
        print(line)


def save_csv(results: List[dict], out_path: Path, scenario: str) -> None:
    with out_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Kịch bản"] + COLUMN_HEADERS)
        for r in results:
            writer.writerow([scenario] + result_to_row(r))

# CLI

def main():
    parser = argparse.ArgumentParser(description="Digital Twin Lite - Vehicle demand simulation")
    parser.add_argument(
        "--scenario", choices=["Normal", "Worst", "Both"], default="Both",
        help="Kich ban van hanh nha xe (mac dinh: Both - chay ca 2)",
    )
    parser.add_argument(
        "--no-events", action="store_true",
        help="Bo qua events.csv (mac dinh la CO tinh events.csv)",
    )
    parser.add_argument(
        "--dataset-dir", type=str, default=str(DATASET_DIR),
        help="Duong dan toi thu muc chua cac file csv (mac dinh: ./Dataset)",
    )
    parser.add_argument(
        "--out", type=str, default=None,
        help="Duong dan file CSV de luu ket qua (khong bat buoc)",
    )
    parser.add_argument(
        "--only-bottleneck", action="store_true",
        help="Chi in cac dong co trang thai BOTTLENECK hoac PEAK",
    )
    args = parser.parse_args()

    scenarios = ["Normal", "Worst"] if args.scenario == "Both" else [args.scenario]
    dataset_dir = Path(args.dataset_dir)

    all_results = []
    for scenario in scenarios:
        results = run_simulation(
            dataset_dir=dataset_dir,
            scenario=scenario,
            include_events=not args.no_events,
        )
        if args.only_bottleneck:
            results = [r for r in results if r["status"] in ("PEAK", "BOTTLENECK")]

        print_report(results, scenario)
        print()

        for r in results:
            all_results.append({**r, "scenario": scenario})

    if args.out:
        out_path = Path(args.out)
        # Neu chay Both, gop chung 1 file voi cot "Kich ban" de phan biet
        with out_path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Kịch bản"] + COLUMN_HEADERS)
            for r in all_results:
                writer.writerow([r["scenario"]] + result_to_row(r))
        print(f"Da luu ket qua vao: {out_path}")


if __name__ == "__main__":
    main()