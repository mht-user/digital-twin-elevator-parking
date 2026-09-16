"""
run_optimizer.py (STUB - de OE thay the)
=========================================================================
Day la BAN GIA de test_pipeline.py chay duoc end-to-end truoc khi OE
xong code that. Hien tai no CHI COPY nguyen schedule dau vao, khong toi
uu gi ca -> objective sau = truoc, luon dat muc "khong te hon" ma
test_oe_integration / test_full_pipeline yeu cau.

Dieu kien day du OE phai thoa: xem OE_optimizer_checklist.md.

OE: khi code xong, GHI DE truc tiep len file nay (giu nguyen ten file
`run_optimizer.py` va ten ham `optimize_schedule`, cung tham so) - KHONG
can sua test_pipeline.py.
=========================================================================
"""

from typing import List


def optimize_schedule(
    schedule: List[dict],
    events: List[dict],
    parking: List[dict],
    scenario: str = "Normal",
) -> List[dict]:
    """STUB: khong toi uu gi, chi tra ve BAN SAO cua schedule dau vao.

    - Copy tung dong (dict(row)) chu KHONG tra ve chinh list `schedule`
      duoc truyen vao - xem muc "khong sua in-place" trong checklist.
    - Giu nguyen 100% schedule_id/class_id/room_id/day_of_week/shift nen
      objective sau toi uu se BANG objective truoc - du de cac test OE
      chay va PASS trong luc cho code that.
    """
    return [dict(row) for row in schedule]


if __name__ == "__main__":
    # Chay thu doc lap: python3 run_optimizer.py (dung cho OE tu kiem tra
    # nhanh truoc khi cam vao pipeline day du).
    from run_simulation import load_dataset, run_simulation_from_data

    data = load_dataset()
    before = run_simulation_from_data(data["schedule"], data["events"], data["parking"], scenario="Normal")
    schedule_after = optimize_schedule(data["schedule"], data["events"], data["parking"], scenario="Normal")
    after = run_simulation_from_data(schedule_after, data["events"], data["parking"], scenario="Normal")

    n_before = sum(1 for r in before if r["status"] == "BOTTLENECK")
    n_after = sum(1 for r in after if r["status"] == "BOTTLENECK")
    print(f"[STUB] optimize_schedule: {len(schedule_after)} dong, "
          f"BOTTLENECK {n_before} -> {n_after} (stub = khong doi vi tri gi)")
