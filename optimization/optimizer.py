from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from statistics import pstdev
from typing import Dict, List, Optional, Tuple

from se_bridge import SimulationEngineerBridge


DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
SHIFTS = ["Ca1", "Ca2", "Ca3", "Ca4"]

DAY_VN = {
    "Mon": "Thu 2",
    "Tue": "Thu 3",
    "Wed": "Thu 4",
    "Thu": "Thu 5",
    "Fri": "Thu 6",
    "Sat": "Thu 7",
}

TIME_FIELDS = [
    "start_time",
    "end_time",
    "arrival_window_start",
    "arrival_window_end",
    "departure_window_start",
    "departure_window_end",
]


@dataclass
class MultiMoveOptimizationResult:
    scenario: str
    include_events: bool
    max_moves: int
    stop_reason: str
    baseline_results: List[dict]
    final_results: List[dict]
    baseline_metrics: dict
    final_metrics: dict
    moves: List[dict]
    candidate_history: List[dict]
    optimized_schedule: List[dict]
    total_evaluated_candidates: int
    total_improving_candidates: int


def _f(value) -> float:
    return float(value)


def _i(value) -> int:
    return int(float(value))


def _shift_templates(schedule: List[dict]) -> Dict[str, dict]:
    templates: Dict[str, dict] = {}
    for row in schedule:
        shift = row["shift"]
        if shift not in templates:
            templates[shift] = {field: row[field] for field in TIME_FIELDS}

    missing = [shift for shift in SHIFTS if shift not in templates]
    if missing:
        raise ValueError(f"Missing shift templates: {missing}")

    return templates


def _occupied_rooms(schedule: List[dict]) -> Dict[Tuple[str, str], set]:
    occupied: Dict[Tuple[str, str], set] = {}
    for row in schedule:
        occupied.setdefault(
            (row["day_of_week"], row["shift"]), set()
        ).add(row["room_id"])
    return occupied


def _find_free_room(
    rooms: List[dict],
    occupied: Dict[Tuple[str, str], set],
    building: str,
    day: str,
    shift: str,
    num_students: int,
) -> Optional[dict]:
    used = occupied.get((day, shift), set())

    feasible = [
        room
        for room in rooms
        if room["building"] == building
        and _i(room["room_capacity"]) >= num_students
        and room["room_id"] not in used
    ]

    if not feasible:
        return None

    # Smallest adequate room; room_id is a deterministic tie-breaker.
    feasible.sort(
        key=lambda room: (
            _i(room["room_capacity"]) - num_students,
            room["room_id"],
        )
    )
    return feasible[0]


def _find_schedule_row(
    schedule: List[dict], schedule_id: str
) -> Tuple[int, dict]:
    matches = [
        (idx, row)
        for idx, row in enumerate(schedule)
        if row["schedule_id"] == schedule_id
    ]
    if len(matches) != 1:
        raise ValueError(
            f"schedule_id={schedule_id} must appear exactly once; "
            f"found {len(matches)}"
        )
    return matches[0]


def apply_move(
    schedule: List[dict],
    rooms: List[dict],
    schedule_id: str,
    target_day: str,
    target_shift: str,
) -> Tuple[List[dict], dict]:
    """
    Apply one feasible MOVE.

    Constraints used by OE:
    - keep the same building;
    - target room must exist and have enough capacity;
    - no room conflict;
    - the same class cannot already have another session in the target slot.

    The move also updates the target shift's time and arrival/departure windows,
    which is required by the current SE flow-slot simulation.
    """
    idx, source = _find_schedule_row(schedule, schedule_id)

    if target_day not in DAYS or target_shift not in SHIFTS:
        raise ValueError(f"Invalid target slot: {target_day}/{target_shift}")

    if (
        source["day_of_week"] == target_day
        and source["shift"] == target_shift
    ):
        raise ValueError("Target slot equals current slot")

    for row in schedule:
        if (
            row["schedule_id"] != schedule_id
            and row["class_id"] == source["class_id"]
            and row["day_of_week"] == target_day
            and row["shift"] == target_shift
        ):
            raise ValueError("Same class already has a session in target slot")

    room = _find_free_room(
        rooms=rooms,
        occupied=_occupied_rooms(schedule),
        building=source["building"],
        day=target_day,
        shift=target_shift,
        num_students=_i(source["num_students"]),
    )
    if room is None:
        raise ValueError("No free adequate room in the same building")

    templates = _shift_templates(schedule)
    updated = deepcopy(schedule)
    row = updated[idx]

    row["day_of_week"] = target_day
    row["day_vn"] = DAY_VN[target_day]
    row["shift"] = target_shift

    row["room_id"] = room["room_id"]
    row["building"] = room["building"]
    row["floor"] = str(room["floor"])
    row["room_capacity"] = str(room["room_capacity"])

    for field in TIME_FIELDS:
        row[field] = templates[target_shift][field]

    return updated, room


def _load_balance_metrics(schedule: List[dict]) -> Tuple[float, float]:
    daily = {day: 0.0 for day in DAYS}
    day_shift = {
        (day, shift): 0.0
        for day in DAYS
        for shift in SHIFTS
    }

    for row in schedule:
        day = row["day_of_week"]
        shift = row["shift"]
        if day not in daily or shift not in SHIFTS:
            continue

        n_students = _f(row["num_students"])
        daily[day] += n_students
        day_shift[(day, shift)] += n_students

    return (
        pstdev(daily[day] for day in DAYS),
        pstdev(
            day_shift[(day, shift)]
            for day in DAYS
            for shift in SHIFTS
        ),
    )


def calculate_metrics(
    schedule: List[dict],
    simulation_results: List[dict],
) -> dict:
    worst_utils = [_f(row["worst_util"]) for row in simulation_results]
    daily_std, day_shift_std = _load_balance_metrics(schedule)

    return {
        "bottleneck_points": sum(
            row["status"] == "BOTTLENECK"
            for row in simulation_results
        ),
        # PEAK is informational. It is NOT a primary optimization objective because
        # BOTTLENECK -> PEAK is an improvement even though peak count can rise.
        "peak_points": sum(
            row["status"] == "PEAK"
            for row in simulation_results
        ),
        "total_overload_excess": sum(
            max(util - 1.0, 0.0)
            for util in worst_utils
        ),
        "max_worst_util": max(worst_utils, default=0.0),
        "daily_load_std": daily_std,
        "day_shift_load_std": day_shift_std,
    }


def objective_tuple(metrics: dict) -> tuple:
    """
    Lexicographic optimization objective.

    Priority:
    1. lower total overload severity;
    2. lower worst utilization;
    3. fewer bottleneck points;
    4. better day balance;
    5. better day/shift balance.

    peak_points is deliberately excluded from the ranking.
    """
    return (
        metrics["total_overload_excess"],
        metrics["max_worst_util"],
        metrics["bottleneck_points"],
        metrics["daily_load_std"],
        metrics["day_shift_load_std"],
    )


def find_worst_bottleneck(
    simulation_results: List[dict],
) -> Optional[dict]:
    bottlenecks = [
        row
        for row in simulation_results
        if row["status"] == "BOTTLENECK"
    ]
    if not bottlenecks:
        return None

    return max(
        bottlenecks,
        key=lambda row: _f(row["worst_util"]),
    )


def _find_same_point(
    simulation_results: List[dict],
    point: dict,
) -> Optional[dict]:
    for row in simulation_results:
        if (
            row["day"] == point["day"]
            and row["slot"] == point["slot"]
            and row["lot_id"] == point["lot_id"]
        ):
            return row
    return None


def _session_contribution_to_bottleneck(
    bridge: SimulationEngineerBridge,
    schedule: List[dict],
    row: dict,
    point: dict,
    distance_weights: Dict[str, Dict[str, float]],
) -> float:
    """
    Determine whether this session contributes to the current SE bottleneck.

    For a Checkin bottleneck, a session contributes if its ARRIVAL maps to
    the bottleneck slot.
    For Checkout, its DEPARTURE must map to that slot.
    For Both, either flow is counted.
    """
    if row["day_of_week"] != point["day"]:
        return 0.0

    arrival_slot, departure_slot = bridge.row_flow_slots(schedule, row)

    total_motorbikes = (
        _f(row["num_students"])
        * _f(row["motorbike_ratio"])
    )
    lot_share = distance_weights[row["building"]][point["lot_id"]]
    allocated = total_motorbikes * lot_share

    direction = point["bottleneck_direction"]
    contribution = 0.0

    if direction in ("Checkin", "Both") and arrival_slot == point["slot"]:
        contribution += allocated

    if direction in ("Checkout", "Both") and departure_slot == point["slot"]:
        contribution += allocated

    return contribution


def _candidate_record(
    move_no: int,
    source: dict,
    target_room: dict,
    target_day: str,
    target_shift: str,
    contribution: float,
    metrics: dict,
) -> dict:
    return {
        "move_no": move_no,
        "schedule_id": source["schedule_id"],
        "class_id": source["class_id"],
        "num_students": _i(source["num_students"]),
        "building": source["building"],
        "from_day": source["day_of_week"],
        "from_shift": source["shift"],
        "from_room": source["room_id"],
        "to_day": target_day,
        "to_shift": target_shift,
        "to_room": target_room["room_id"],
        "contribution_to_source_bottleneck": contribution,
        **metrics,
    }


def _best_single_step(
    bridge: SimulationEngineerBridge,
    schedule: List[dict],
    rooms: List[dict],
    parking: List[dict],
    events: List[dict],
    scenario: str,
    include_events: bool,
    move_no: int,
    locked_schedule_ids: set,
    top_k: int,
) -> dict:
    """
    Search one iteration of the multi-move optimizer.
    """
    baseline_results = bridge.simulate(
        schedule,
        events,
        parking,
        scenario,
        include_events,
    )
    baseline_metrics = calculate_metrics(schedule, baseline_results)
    bottleneck = find_worst_bottleneck(baseline_results)

    if bottleneck is None:
        return {
            "status": "NO_BOTTLENECK",
            "baseline_results": baseline_results,
            "baseline_metrics": baseline_metrics,
            "evaluated_candidates": 0,
            "improving_candidates": 0,
            "top_candidates": [],
        }

    weights = bridge.distance_weights(parking, scenario)

    source_sessions = []
    for row in schedule:
        if row["schedule_id"] in locked_schedule_ids:
            continue

        contribution = _session_contribution_to_bottleneck(
            bridge,
            schedule,
            row,
            bottleneck,
            weights,
        )
        if contribution > 1e-12:
            source_sessions.append((contribution, row))

    source_sessions.sort(
        key=lambda item: (
            -item[0],
            item[1]["schedule_id"],
        )
    )

    candidate_rows: List[dict] = []
    evaluated = 0

    for contribution, source in source_sessions:
        for target_day in DAYS:
            for target_shift in SHIFTS:
                if (
                    target_day == source["day_of_week"]
                    and target_shift == source["shift"]
                ):
                    continue

                try:
                    candidate_schedule, room = apply_move(
                        schedule=schedule,
                        rooms=rooms,
                        schedule_id=source["schedule_id"],
                        target_day=target_day,
                        target_shift=target_shift,
                    )
                except ValueError:
                    continue

                candidate_results = bridge.simulate(
                    candidate_schedule,
                    events,
                    parking,
                    scenario,
                    include_events,
                )
                candidate_metrics = calculate_metrics(
                    candidate_schedule,
                    candidate_results,
                )
                evaluated += 1

                if objective_tuple(candidate_metrics) >= objective_tuple(
                    baseline_metrics
                ):
                    continue

                candidate_rows.append(
                    {
                        "_schedule": candidate_schedule,
                        "_room": room,
                        "_results": candidate_results,
                        "_source": source,
                        "_metrics": candidate_metrics,
                        "_contribution": contribution,
                        "record": _candidate_record(
                            move_no=move_no,
                            source=source,
                            target_room=room,
                            target_day=target_day,
                            target_shift=target_shift,
                            contribution=contribution,
                            metrics=candidate_metrics,
                        ),
                    }
                )

    if not candidate_rows:
        return {
            "status": "NO_IMPROVING_CANDIDATE",
            "baseline_results": baseline_results,
            "baseline_metrics": baseline_metrics,
            "bottleneck": bottleneck,
            "evaluated_candidates": evaluated,
            "improving_candidates": 0,
            "top_candidates": [],
        }

    candidate_rows.sort(
        key=lambda item: (
            objective_tuple(item["_metrics"]),
            item["record"]["schedule_id"],
            item["record"]["to_day"],
            item["record"]["to_shift"],
            item["record"]["to_room"],
        )
    )

    best = candidate_rows[0]

    # Re-run the selected schedule through the official SE for final step
    # verification instead of trusting only the stored candidate result.
    verified_results = bridge.simulate(
        best["_schedule"],
        events,
        parking,
        scenario,
        include_events,
    )
    verified_metrics = calculate_metrics(
        best["_schedule"],
        verified_results,
    )

    source_after = _find_same_point(
        verified_results,
        bottleneck,
    )

    top_candidates = [
        item["record"]
        for item in candidate_rows[:top_k]
    ]

    return {
        "status": "MOVE_FOUND",
        "baseline_results": baseline_results,
        "baseline_metrics": baseline_metrics,
        "bottleneck": bottleneck,
        "candidate_schedule": best["_schedule"],
        "candidate_results": verified_results,
        "candidate_metrics": verified_metrics,
        "source": best["_source"],
        "target_room": best["_room"],
        "contribution": best["_contribution"],
        "source_bottleneck_after": source_after,
        "evaluated_candidates": evaluated,
        "improving_candidates": len(candidate_rows),
        "top_candidates": top_candidates,
    }


def optimize_multi_move(
    bridge: SimulationEngineerBridge,
    schedule: List[dict],
    rooms: List[dict],
    parking: List[dict],
    events: List[dict],
    scenario: str = "Normal",
    include_events: bool = False,
    max_moves: int = 3,
    top_k: int = 10,
) -> MultiMoveOptimizationResult:
    """
    Iterative Iterative optimizer:

    SE -> worst bottleneck -> best feasible MOVE -> SE -> repeat

    Stop when:
    - no bottleneck remains;
    - no improving candidate exists;
    - max_moves is reached.
    """
    if max_moves < 1:
        raise ValueError("max_moves must be >= 1")

    current_schedule = deepcopy(schedule)
    locked_schedule_ids = set()
    moves: List[dict] = []
    candidate_history: List[dict] = []

    baseline_results = bridge.simulate(
        current_schedule,
        events,
        parking,
        scenario,
        include_events,
    )
    baseline_metrics = calculate_metrics(
        current_schedule,
        baseline_results,
    )

    total_evaluated = 0
    total_improving = 0
    stop_reason = "MAX_MOVES"

    for move_no in range(1, max_moves + 1):
        step = _best_single_step(
            bridge=bridge,
            schedule=current_schedule,
            rooms=rooms,
            parking=parking,
            events=events,
            scenario=scenario,
            include_events=include_events,
            move_no=move_no,
            locked_schedule_ids=locked_schedule_ids,
            top_k=top_k,
        )

        total_evaluated += step["evaluated_candidates"]
        total_improving += step["improving_candidates"]

        if step["status"] == "NO_BOTTLENECK":
            stop_reason = "NO_BOTTLENECK"
            break

        if step["status"] == "NO_IMPROVING_CANDIDATE":
            stop_reason = "NO_IMPROVING_CANDIDATE"
            break

        for rank, record in enumerate(step["top_candidates"], start=1):
            candidate_history.append(
                {
                    "move_no": move_no,
                    "rank": rank,
                    **record,
                }
            )

        source = step["source"]
        room = step["target_room"]
        point = step["bottleneck"]
        point_after = step["source_bottleneck_after"]
        before_metrics = step["baseline_metrics"]
        after_metrics = step["candidate_metrics"]

        move_record = {
            "move_no": move_no,
            "schedule_id": source["schedule_id"],
            "class_id": source["class_id"],
            "num_students": _i(source["num_students"]),
            "building": source["building"],
            "from_day": source["day_of_week"],
            "from_shift": source["shift"],
            "from_room": source["room_id"],
            "to_day": step["top_candidates"][0]["to_day"],
            "to_shift": step["top_candidates"][0]["to_shift"],
            "to_room": room["room_id"],
            "source_bottleneck_day": point["day"],
            "source_bottleneck_slot": point["slot"],
            "source_bottleneck_lot": point["lot_id"],
            "source_bottleneck_direction": point["bottleneck_direction"],
            "source_worst_util_before": _f(point["worst_util"]),
            "source_worst_util_after": (
                _f(point_after["worst_util"])
                if point_after is not None
                else 0.0
            ),
            "total_overload_before": before_metrics["total_overload_excess"],
            "total_overload_after": after_metrics["total_overload_excess"],
            "max_worst_util_before": before_metrics["max_worst_util"],
            "max_worst_util_after": after_metrics["max_worst_util"],
            "bottleneck_points_before": before_metrics["bottleneck_points"],
            "bottleneck_points_after": after_metrics["bottleneck_points"],
            "peak_points_before": before_metrics["peak_points"],
            "peak_points_after": after_metrics["peak_points"],
            "evaluated_candidates": step["evaluated_candidates"],
            "improving_candidates": step["improving_candidates"],
        }
        moves.append(move_record)

        current_schedule = step["candidate_schedule"]
        locked_schedule_ids.add(source["schedule_id"])

    final_results = bridge.simulate(
        current_schedule,
        events,
        parking,
        scenario,
        include_events,
    )
    final_metrics = calculate_metrics(
        current_schedule,
        final_results,
    )

    return MultiMoveOptimizationResult(
        scenario=scenario,
        include_events=include_events,
        max_moves=max_moves,
        stop_reason=stop_reason,
        baseline_results=baseline_results,
        final_results=final_results,
        baseline_metrics=baseline_metrics,
        final_metrics=final_metrics,
        moves=moves,
        candidate_history=candidate_history,
        optimized_schedule=current_schedule,
        total_evaluated_candidates=total_evaluated,
        total_improving_candidates=total_improving,
    )
