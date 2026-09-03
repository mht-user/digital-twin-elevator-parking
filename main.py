from simulation.parking_simulation import run_simulation

df = run_simulation(
    classes_file="data/classes.csv",
    schedule_file="data/schedule.csv",
    parking_file="data/parking.csv",
    scenario="Normal"
)

print(df)

print("\n===== SUMMARY =====")

print(
    "Peak occupancy:",
    df["Occupancy"].max()
)

print(
    "Capacity:",
    df["Capacity"].iloc[0]
)

if (
    df["Occupancy"].max()
    > df["Capacity"].iloc[0]
):
    print("Parking overload detected")
else:
    print("Parking capacity OK")