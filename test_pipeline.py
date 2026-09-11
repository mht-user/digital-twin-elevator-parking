"""
test_pipeline.py (v3)
=========================================================================
3 test case theo yeu cau tuan nay:
    1. Normal load  -> run_simulation() chay duoc, output dung cau truc
    2. Bottleneck    -> phat hien dung diem nghen (checkout la nghen cau
                         truc, xay ra ngay ca o Normal - xem SRS Phu luc 8.3)
    3. Chuyen lich   -> dung make_what_if_schedule() that (khong con stub
                         gia), so sanh Before/After bang compare_before_after()

Chay: python3 test_pipeline.py
"""

import sys
from collections import Counter

from run_simulation import (
    load_dataset,
    run_simulation_from_data,
    make_what_if_schedule,
    compare_before_after,
)


def test_normal_load():
    data = load_dataset()
    results = run_simulation_from_data(data["schedule"], data["events"], data["parking"], scenario="Normal")

    assert isinstance(results, list), "phai tra ve list[dict]"
    assert len(results) > 0, "Ket qua khong duoc rong voi du lieu Normal"
    required = {"day", "shift", "lot_id", "incoming", "outgoing",
                "checkin_capacity", "checkout_capacity", "checkin_util",
                "checkout_util", "worst_util", "bottleneck_direction", "status"}
    missing = required - set(results[0].keys())
    assert not missing, f"Thieu truong: {missing}"
    assert all(r["incoming"] >= 0 and r["outgoing"] >= 0 for r in results), "incoming/outgoing khong duoc am"
    print(f"[PASS] test_normal_load ({len(results)} dong ket qua)")


def test_bottleneck_detection():
    """Theo SRS (Phu luc 8.3): checkout la diem nghen CAU TRUC, xay ra
    ngay ca o scenario Normal (khong can Worst) do checkout_capacity chi
    bang ~30% checkin_capacity o moi nha xe. Test nay xac nhan dieu do."""
    data = load_dataset()
    results = run_simulation_from_data(data["schedule"], data["events"], data["parking"], scenario="Normal")

    bottlenecks = [r for r in results if r["status"] == "BOTTLENECK"]
    assert len(bottlenecks) > 0, "Scenario Normal phai co it nhat 1 BOTTLENECK (nghen cau truc o checkout)"
    assert all(r["bottleneck_direction"] == "Checkout" for r in bottlenecks), (
        "Moi diem BOTTLENECK o Normal deu phai la Checkout (dung du doan SRS Phu luc 8.3), "
        f"nhung co dong voi direction khac: {[r for r in bottlenecks if r['bottleneck_direction'] != 'Checkout']}"
    )

    # Worst phai nghen NANG HON Normal (khong duoc nhe hon)
    results_worst = run_simulation_from_data(data["schedule"], data["events"], data["parking"], scenario="Worst")
    max_normal = max(r["worst_util"] for r in results)
    max_worst = max(r["worst_util"] for r in results_worst)
    assert max_worst >= max_normal, "Worst phai nghen bang hoac nang hon Normal"

    print(f"[PASS] test_bottleneck_detection ({len(bottlenecks)}/{len(results)} dong BOTTLENECK o Normal, "
          f"toan bo deu la Checkout; Worst max_util={max_worst:.0%} >= Normal max_util={max_normal:.0%})")


def find_room_conflicts(schedule: list):
    """Tra ve list (day, shift, room_id) bi > 1 class_id dat cung luc."""
    seen = {}
    conflicts = []
    for row in schedule:
        key = (row["day_of_week"], row["shift"], row["room_id"])
        if key in seen and seen[key] != row["class_id"]:
            conflicts.append(key)
        else:
            seen[key] = row["class_id"]
    return conflicts


def test_schedule_move_no_conflict():
    """Dung thang make_what_if_schedule() that (khong con stub gia),
    va compare_before_after() de lay ca 2 bo ket qua Before/After."""
    data = load_dataset()
    schedule, events, parking = data["schedule"], data["events"], data["parking"]

    conflicts_before = find_room_conflicts(schedule)
    assert len(conflicts_before) == 0, "Du lieu goc dang co xung dot phong, chay validate_data.py truoc"

    class_counts = Counter(r["class_id"] for r in schedule)
    sample_class_id, _ = class_counts.most_common(1)[0]
    sample_row = next(r for r in schedule if r["class_id"] == sample_class_id)
    day, shift = sample_row["day_of_week"], sample_row["shift"]

    schedule_after = make_what_if_schedule(
        schedule, day_of_week=day, shift=shift,
        building=sample_row["building"], remove_class_ids=[sample_class_id],
    )

    conflicts_after = find_room_conflicts(schedule_after)
    assert len(conflicts_after) == 0, f"make_what_if_schedule() tao ra xung dot moi: {conflicts_after}"
    assert len(schedule_after) == len(schedule) - 1, "Phai giam dung 1 dong sau khi bo 1 lop"

    results_before, results_after = compare_before_after(schedule, schedule_after, events, parking, scenario="Normal")
    assert len(results_before) > 0 and len(results_after) > 0, "compare_before_after() phai tra ve ket qua cho ca 2 ban"

    print(f"[PASS] test_schedule_move_no_conflict (bo lop {sample_class_id} khoi {day}/{shift}, "
          f"0 xung dot, compare_before_after() chay duoc)")


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
