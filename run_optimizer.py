from typing import List

def optimize_schedule(
    schedule: List[dict],
    events: List[dict],
    parking: List[dict],
    scenario: str = "Normal",
) -> List[dict]:
    return [dict(row) for row in schedule]

if __name__ == "__main__":
    from run_simulation import load_dataset, run_simulation_from_data

    data = load_dataset()
    before = run_simulation_from_data(data["schedule"], data["events"], data["parking"], scenario="Normal")
    schedule_after = optimize_schedule(data["schedule"], data["events"], data["parking"], scenario="Normal")
    after = run_simulation_from_data(schedule_after, data["events"], data["parking"], scenario="Normal")

    n_before = sum(1 for r in before if r["status"] == "BOTTLENECK")
    n_after = sum(1 for r in after if r["status"] == "BOTTLENECK")
    print(f"[STUB] optimize_schedule: {len(schedule_after)} dong, "
          f"BOTTLENECK {n_before} -> {n_after} (stub = khong doi vi tri gi)")
