import pandas as pd


def run_simulation(
        classes_file,
        schedule_file,
        parking_file,
        scenario="Normal"
):
    # =====================
    # Load data
    # =====================

    classes = pd.read_csv(classes_file)
    schedule = pd.read_csv(schedule_file)
    parking = pd.read_csv(parking_file)

    # Chọn scenario
    classes = classes[classes["scenario"] == scenario]
    schedule = schedule[schedule["scenario"] == scenario]
    parking = parking[parking["scenario"] == scenario]

    # =====================
    # Total students
    # =====================

    total_students = classes["num_students"].sum()

    # =====================
    # Motorbike ratio
    # =====================

    motorbike_ratio = schedule[
        "motorbike_modal_share"
    ].iloc[0]

    total_bikes = int(
        total_students * motorbike_ratio
    )

    # =====================
    # Parking capacity
    # =====================

    capacity = parking[
        "effective_capacity"
    ].sum()

    # =====================
    # Arrival simulation
    # =====================

    occupancy = 0

    result = []

    for _, row in schedule.iterrows():

        time_label = row["bucket_start"]

        fraction = row["fraction_within_window"]

        arriving_students = int(
            total_students * fraction
        )

        arriving_bikes = int(
            total_bikes * fraction
        )

        occupancy += arriving_bikes

        overload = (
            "Yes"
            if occupancy > capacity
            else "No"
        )

        result.append(
            {
                "Time": time_label,
                "Students": arriving_students,
                "Motorbikes": arriving_bikes,
                "Occupancy": occupancy,
                "Capacity": capacity,
                "Overload": overload,
            }
        )

    return pd.DataFrame(result)