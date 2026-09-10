import pandas as pd
import numpy as np

DATA_DIR = "DE"          # thư mục chứa dữ liệu DE 
BUILDINGS = ["A2", "B", "C", "D"]
DAY_ORDER = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}
SHIFT_ORDER = {"Ca1": 0, "Ca2": 1, "Ca3": 2, "Ca4": 3}

# Đọc dữ liệu

def load_data(data_dir: str = DATA_DIR):

    schedule = pd.read_csv(f"{data_dir}/schedule.csv")
    events = pd.read_csv(f"{data_dir}/events.csv")
    parking = pd.read_csv(f"{data_dir}/parking.csv")
    return schedule, events, parking

# Tính trọng số phân bổ xe theo khoảng cách (công thức trong slide)
# w[toà][bãi] = (1/khoảng cách) / tổng(1/khoảng cách tới mọi bãi từ toà đó)

def build_distance_weights(parking: pd.DataFrame) -> dict:
    
    parking_normal = parking[parking["scenario"] == "Normal"]

    weights = {}
    for building in BUILDINGS:
        dist_col = f"dist_from_{building}_m"
        inv_dist = {
            lot: 1 / d
            for lot, d in zip(parking_normal["parking_lot_id"], parking_normal[dist_col])
        }
        s = sum(inv_dist.values())
        weights[building] = {lot: v / s for lot, v in inv_dist.items()}
    return weights

# Tính tổng số xe máy cần gửi theo (ngày, ca, toà)
# Gộp cả lịch học thường (schedule.csv) và sự kiện phát sinh (events.csv)

def demand_by_building(schedule: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    schedule = schedule.copy()
    schedule["motorbikes"] = schedule["num_students"] * schedule["motorbike_ratio"]
    sched_demand = (
        schedule.groupby(["day_of_week", "day_vn", "shift", "building"])["motorbikes"]
        .sum()
        .reset_index()
    )

    events = events.copy()
    events["motorbikes"] = events["num_students"] * events["motorbike_ratio"]
    evt_demand = (
        events.groupby(["day_of_week", "day_vn", "shift", "building"])["motorbikes"]
        .sum()
        .reset_index()
    )

    combined = pd.concat([sched_demand, evt_demand], ignore_index=True)
    combined = (
        combined.groupby(["day_of_week", "day_vn", "shift", "building"])["motorbikes"]
        .sum()
        .reset_index()
    )
    return combined

# Phân bổ nhu cầu của mỗi toà vào từng bãi xe theo trọng số khoảng cách

def distribute_to_lots(demand_df: pd.DataFrame, weights: dict) -> pd.DataFrame:
    rows = []
    for _, row in demand_df.iterrows():
        b = row["building"]
        if b not in weights:
            continue  # toà không có trong bảng khoảng cách -> bỏ qua (an toàn)
        for lot, w in weights[b].items():
            rows.append(
                {
                    "day_of_week": row["day_of_week"],
                    "day_vn": row["day_vn"],
                    "shift": row["shift"],
                    "parking_lot_id": lot,
                    "demand": row["motorbikes"] * w,
                }
            )
    df = pd.DataFrame(rows)
    lot_demand = (
        df.groupby(["day_of_week", "day_vn", "shift", "parking_lot_id"])["demand"]
        .sum()
        .reset_index()
    )
    lot_demand["demand"] = lot_demand["demand"].round().astype(int)
    return lot_demand

# So sánh nhu cầu với năng lực thông qua thực tế (throughput/30 phút)
# của từng bãi, theo scenario (Normal / Peak / Worst) và chiều (vào/ra)

def run_simulation(
    schedule: pd.DataFrame,
    events: pd.DataFrame,
    parking: pd.DataFrame,
    scenario: str = "Normal",
    direction: str = "checkin",
) -> pd.DataFrame:
    
    weights = build_distance_weights(parking)
    demand_df = demand_by_building(schedule, events)
    lot_demand = distribute_to_lots(demand_df, weights)

    parking_scn = parking[parking["scenario"] == scenario].set_index("parking_lot_id")
    cap_col = (
        "max_checkin_throughput_veh_per_30min"
        if direction == "checkin"
        else "max_checkout_throughput_veh_per_30min"
    )

    lot_demand["capacity"] = lot_demand["parking_lot_id"].map(parking_scn[cap_col])
    lot_demand["fill_pct"] = (
        (lot_demand["demand"] / lot_demand["capacity"] * 100).round(0).astype(int)
    )
    lot_demand["status"] = np.where(
        lot_demand["fill_pct"] > 100,
        "BOTTLENECK",
        np.where(lot_demand["fill_pct"] > 85, "WARNING", "OK"),
    )

    lot_demand["_d"] = lot_demand["day_of_week"].map(DAY_ORDER)
    lot_demand["_s"] = lot_demand["shift"].map(SHIFT_ORDER)
    lot_demand = lot_demand.sort_values(["_d", "_s", "parking_lot_id"]).drop(
        columns=["_d", "_s"]
    )
    return lot_demand.reset_index(drop=True)

# In kết quả ra dạng bảng 

def print_report(result: pd.DataFrame):
    out = result.rename(
        columns={
            "day_vn": "Ngày",
            "shift": "Ca học",
            "parking_lot_id": "Bãi đỗ xe",
            "demand": "Nhu cầu để xe",
            "capacity": "Sức chứa thực tế",
            "fill_pct": "Tỉ lệ fill",
            "status": "Trạng thái",
        }
    )[["Ngày", "Ca học", "Bãi đỗ xe", "Nhu cầu để xe", "Sức chứa thực tế", "Tỉ lệ fill", "Trạng thái"]].copy()


    out["Tỉ lệ fill"] = out["Tỉ lệ fill"].astype(str) + "%"
    out = out.astype(str)
    widths = {col: max(out[col].map(len).max(), len(col)) for col in out.columns}
    header = " | ".join(col.ljust(widths[col]) for col in out.columns)
    print(header)

    for _, row in out.iterrows():
        print(" | ".join(str(row[col]).ljust(widths[col]) for col in out.columns))


if __name__ == "__main__":
    schedule, events, parking = load_data()

    print("=== KỊCH BẢN: Normal - Sinh viên ĐẾN trường (checkin) ===\n")
    result = run_simulation(schedule, events, parking, scenario="Normal", direction="checkin")
    print_report(result)

    print("\n=== CÁC ĐIỂM NGHẼN (BOTTLENECK) ===\n")
    bottlenecks = result[result["status"] == "BOTTLENECK"]
    if len(bottlenecks) == 0:
        print("(Không có điểm nghẽn nào trong kịch bản này)")
    else:
        print_report(bottlenecks)