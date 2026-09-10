"""
test_pipeline.py (v2 - khop voi run_simulation.py ban da sua)
==============================================================
3 test case theo yeu cau tuan nay:
    1. Normal load  -> run_simulation()+build_result_table() chay duoc
    2. Bottleneck    -> phat hien dung diem nghen (Worst/checkout)
    3. Chuyen lich   -> sau khi doi lich 1 lop, khong xung dot phong

Chay: python3 test_pipeline.py
"""

import sys
import pandas as pd

from run_simulation import load_data, run_simulation, build_result_table

VN_COLS = {
    "Ngày": "day", "Ca học": "shift", "Bãi đỗ xe": "lot",
    "Nhu cầu để xe": "demand", "Trạng thái": "status",
}


def _english(result: pd.DataFrame) -> pd.DataFrame:
    return result.rename(columns=VN_COLS)


def test_normal_load():
    demand, capacity_df = run_simulation(scenario="Normal")
    result = build_result_table(demand, capacity_df, direction="checkin")
    result = _english(result)

    assert isinstance(result, pd.DataFrame), "phai tra ve DataFrame"
    assert len(result) > 0, "Ket qua khong duoc rong voi du lieu Normal"
    required = {"day", "shift", "lot", "demand", "status"}
    missing = required - set(result.columns)
    assert not missing, f"Thieu cot: {missing}"
    assert (result["demand"] >= 0).all(), "Demand khong duoc am"
    print("[PASS] test_normal_load")


def test_bottleneck_detection():
    """Worst + checkout la kich ban nang nhat (giam cong, tang thoi
    gian xu ly gio tan tam) -> phai co it nhat 1 BOTTLENECK."""
    demand, capacity_df = run_simulation(scenario="Worst")
    result = build_result_table(demand, capacity_df, direction="checkout")
    result = _english(result)

    bottlenecks = result[result["status"] == "BOTTLENECK"]
    assert len(bottlenecks) > 0, "Kich ban Worst/checkout phai co it nhat 1 bottleneck"

    worst = result.loc[result["demand"].idxmax()] if "utilization_pct" not in result.columns else None
    print(f"[PASS] test_bottleneck_detection ({len(bottlenecks)} dong bottleneck, "
          f"vi du: {bottlenecks.iloc[0]['lot']} {bottlenecks.iloc[0]['day']}/{bottlenecks.iloc[0]['shift']})")


def move_class_session(schedule: pd.DataFrame, schedule_id: str, new_day: str, new_shift: str) -> pd.DataFrame:
    """STUB tam thoi cho toi khi Optimization Engineer co recommend_best_move() that."""
    updated = schedule.copy()
    mask = updated["schedule_id"] == schedule_id
    assert mask.any(), f"schedule_id {schedule_id} khong ton tai"
    updated.loc[mask, "day_of_week"] = new_day
    updated.loc[mask, "shift"] = new_shift
    return updated


def find_room_conflicts(schedule: pd.DataFrame):
    grouped = schedule.groupby(["day_of_week", "shift", "room_id"])["schedule_id"].nunique()
    return grouped[grouped > 1]


def test_schedule_move_no_conflict():
    schedule, _parking = load_data()

    conflicts_before = find_room_conflicts(schedule)
    assert len(conflicts_before) == 0, "Du lieu goc dang co xung dot phong, chay validate_data.py truoc"

    sample_id = schedule.iloc[0]["schedule_id"]
    original_room = schedule.iloc[0]["room_id"]

    free_slot = None
    for day in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]:
        for shift in ["Ca1", "Ca2", "Ca3", "Ca4"]:
            clash = schedule[
                (schedule["day_of_week"] == day)
                & (schedule["shift"] == shift)
                & (schedule["room_id"] == original_room)
            ]
            if clash.empty:
                free_slot = (day, shift)
                break
        if free_slot:
            break
    assert free_slot is not None, "Khong tim duoc khung gio trong de test"

    moved = move_class_session(schedule, sample_id, *free_slot)
    conflicts_after = find_room_conflicts(moved)
    assert len(conflicts_after) == 0, f"Chuyen lich tao ra xung dot moi: {conflicts_after}"
    print(f"[PASS] test_schedule_move_no_conflict (moved {sample_id} -> {free_slot}, 0 conflict)")


if __name__ == "__main__":
    tests = [test_normal_load, test_bottleneck_detection, test_schedule_move_no_conflict]
    failed = 0
    for t in tests:
        try:
            t()
        except AssertionError as e:
            failed += 1
            print(f"[FAIL] {t.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"[ERROR] {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} test(s) passed")
    sys.exit(1 if failed else 0)
