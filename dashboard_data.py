"""
dashboard_data.py (v2 - thich nghi voi run_simulation.py ban moi)
==================================================================
Ghep noi run_simulation()/build_result_table() (Simulation Engineer,
ban da sua loi) thanh dung 3 khoi du lieu Front-end can:
    - heatmap      -> "Current Schedule Heatmap"
    - kpi          -> "KPI"
    - parking_view -> "Parking View"


Cach chay:
    python3 dashboard_data.py --scenario Normal --direction checkin
    python3 dashboard_data.py --scenario Worst --direction checkout
"""

import argparse
import json
import re

import pandas as pd

from run_simulation import run_simulation, build_result_table, load_data

VN_TO_EN_COLS = {
    "Ngày": "day",
    "Ca học": "shift",
    "Bãi đỗ xe": "parking_lot",
    "Nhu cầu để xe": "demand",
    "Sức chứa thực tế": "capacity",
    "Tỉ lệ fill": "utilization_pct",
    "Trạng thái": "status",
}

DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
SHIFT_LABELS = ["Ca1", "Ca2", "Ca3", "Ca4"]


def normalize_parking_view(result: pd.DataFrame) -> pd.DataFrame:
    """Doi ten cot tieng Viet -> tieng Anh, va '131%' (str) -> 131 (int),
    de Front-end xu ly duoc bang so, khong phai chuoi co dau %."""
    df = result.rename(columns=VN_TO_EN_COLS).copy()
    df["utilization_pct"] = (
        df["utilization_pct"].astype(str).str.replace("%", "", regex=False).astype(int)
    )
    for col in ["day", "shift", "parking_lot", "status"]:
        if col in df.columns:
            df[col] = df[col].astype(str)
    return df


def build_heatmap(schedule: pd.DataFrame) -> dict:
    totals = schedule.groupby(["day_of_week", "shift"])["num_students"].sum().reset_index()
    heatmap = {day: {shift: 0 for shift in SHIFT_LABELS} for day in DAY_LABELS}
    for _, row in totals.iterrows():
        day, shift = row["day_of_week"], row["shift"]
        if day in heatmap and shift in heatmap[day]:
            heatmap[day][shift] = int(row["num_students"])
    return heatmap


def build_kpi(schedule: pd.DataFrame, parking_view: pd.DataFrame) -> dict:
    total_sessions = int(len(schedule))
    total_students = int(schedule["num_students"].sum())

    demand_by_slot = schedule.groupby(["day_of_week", "shift"])["num_students"].sum().reset_index()
    peak_row = demand_by_slot.loc[demand_by_slot["num_students"].idxmax()]
    peak_demand = {"day": peak_row["day_of_week"], "shift": peak_row["shift"], "value": int(peak_row["num_students"])}

    worst_row = parking_view.loc[parking_view["utilization_pct"].idxmax()]
    worst_parking = {
        "lot": worst_row["parking_lot"],
        "day": worst_row["day"],
        "shift": worst_row["shift"],
        "utilization_pct": int(worst_row["utilization_pct"]),
    }
    worst_day_time = {"day": worst_row["day"], "shift": worst_row["shift"]}

    return {
        "total_sessions": total_sessions,
        "total_students": total_students,
        "peak_demand": peak_demand,
        "worst_parking": worst_parking,
        "worst_day_time": worst_day_time,
    }


def build_dashboard_payload(scenario: str = "Normal", direction: str = "checkin") -> dict:
    schedule, _parking = load_data()
    demand, capacity_df = run_simulation(scenario=scenario)
    result = build_result_table(demand, capacity_df, direction=direction)
    parking_view_df = normalize_parking_view(result)

    return {
        "scenario": scenario,
        "direction": direction,
        "note": "CANH BAO: demand hien chua gom events.csv (xem docstring dau file)",
        "heatmap": build_heatmap(schedule),
        "kpi": build_kpi(schedule, parking_view_df),
        "parking_view": parking_view_df.to_dict(orient="records"),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build dashboard-ready JSON from run_simulation()")
    parser.add_argument("--scenario", default="Normal", choices=["Normal", "Worst"])
    parser.add_argument("--direction", default="checkin", choices=["checkin", "checkout"])
    args = parser.parse_args()

    payload = build_dashboard_payload(args.scenario, args.direction)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
