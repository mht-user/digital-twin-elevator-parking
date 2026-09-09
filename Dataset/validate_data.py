from pathlib import Path
import csv
from collections import Counter, defaultdict

BASE = Path(__file__).resolve().parent
errors = []
warnings = []

def read_csv(name):
    with (BASE / name).open('r', encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))

def err(msg):
    errors.append(msg)

def check_unique(rows, key, file):
    c = Counter(r[key] for r in rows)
    dup = [k for k,v in c.items() if v > 1]
    if dup:
        err(f'{file}: duplicate {key}: {dup[:10]}')

classes = read_csv('classes.csv')
schedule = read_csv('schedule.csv')
rooms = read_csv('rooms.csv')
parking = read_csv('parking.csv')
events = read_csv('events.csv')

check_unique(classes, 'class_id', 'classes.csv')
check_unique(schedule, 'schedule_id', 'schedule.csv')
check_unique(rooms, 'room_id', 'rooms.csv')
check_unique(events, 'event_id', 'events.csv')

class_map = {r['class_id']: r for r in classes}
room_map = {r['room_id']: r for r in rooms}

# Schedule FK + copied-field consistency + capacity
for r in schedule:
    sid = r['schedule_id']
    if r['class_id'] not in class_map:
        err(f'{sid}: class_id {r["class_id"]} not found in classes.csv')
        continue
    if r['room_id'] not in room_map:
        err(f'{sid}: room_id {r["room_id"]} not found in rooms.csv')
        continue
    c = class_map[r['class_id']]
    rm = room_map[r['room_id']]
    if r['building'] != rm['building']:
        err(f'{sid}: building mismatch schedule={r["building"]}, room={rm["building"]}')
    if str(r['floor']) != str(rm['floor']):
        err(f'{sid}: floor mismatch schedule={r["floor"]}, room={rm["floor"]}')
    if str(r['room_capacity']) != str(rm['room_capacity']):
        err(f'{sid}: room_capacity mismatch schedule={r["room_capacity"]}, room={rm["room_capacity"]}')
    if int(r['num_students']) > int(r['room_capacity']):
        err(f'{sid}: num_students > room_capacity')
    if str(r['num_students']) != str(c['num_students']):
        err(f'{sid}: num_students differs from classes.csv')
    if abs(float(r['motorbike_ratio']) - float(c['motorbike_ratio'])) > 1e-9:
        err(f'{sid}: motorbike_ratio differs from classes.csv')
    if abs(float(r['dorm_ratio']) - float(c['dorm_ratio'])) > 1e-9:
        err(f'{sid}: dorm_ratio differs from classes.csv')

# No room conflict
seen = {}
for r in schedule:
    key = (r['day_of_week'], r['shift'], r['room_id'])
    if key in seen:
        err(f'Room conflict {key}: {seen[key]} and {r["schedule_id"]}')
    else:
        seen[key] = r['schedule_id']

# sessions_per_week matches actual schedule rows
actual = Counter(r['class_id'] for r in schedule)
for c in classes:
    expected = int(c['sessions_per_week'])
    if actual[c['class_id']] != expected:
        err(f'{c["class_id"]}: sessions_per_week={expected}, actual={actual[c["class_id"]]}')

# Parking schema/content
required_parking_cols = {
    'scenario','parking_lot_id','capacity_slots','checkin_gates_open','checkout_gates_open',
    'checkin_sec_per_vehicle','checkout_sec_per_vehicle','max_checkin_throughput_veh_per_30min',
    'max_checkout_throughput_veh_per_30min','dist_from_A2_m','dist_from_B_m','dist_from_C_m','dist_from_D_m'
}
if parking:
    missing = required_parking_cols - set(parking[0].keys())
    if missing:
        err(f'parking.csv missing columns: {sorted(missing)}')

scen_lots = defaultdict(set)
for r in parking:
    scen_lots[r['scenario']].add(r['parking_lot_id'])
    for col in ['dist_from_A2_m','dist_from_B_m','dist_from_C_m','dist_from_D_m']:
        if int(r[col]) <= 0:
            err(f'parking {r["scenario"]}/{r["parking_lot_id"]}: {col} must be > 0')
    ci = int(round(int(r['checkin_gates_open']) * 1800 / float(r['checkin_sec_per_vehicle'])))
    co = int(round(int(r['checkout_gates_open']) * 1800 / float(r['checkout_sec_per_vehicle'])))
    if ci != int(r['max_checkin_throughput_veh_per_30min']):
        err(f'parking {r["scenario"]}/{r["parking_lot_id"]}: checkin throughput inconsistent')
    if co != int(r['max_checkout_throughput_veh_per_30min']):
        err(f'parking {r["scenario"]}/{r["parking_lot_id"]}: checkout throughput inconsistent')

if set(scen_lots) != {'Normal','Worst'}:
    err(f'parking.csv scenarios must be exactly Normal and Worst, got {sorted(scen_lots)}')
for scenario in ['Normal','Worst']:
    if scen_lots.get(scenario) != {'P1','P2','P3'}:
        err(f'{scenario}: parking lots must be P1/P2/P3')

# Event basic validation
valid_buildings = {'A2','B','C','D'}
valid_days = {'Mon','Tue','Wed','Thu','Fri','Sat'}
valid_shifts = {'Ca1','Ca2','Ca3','Ca4'}
for r in events:
    if r['building'] not in valid_buildings:
        err(f'event {r["event_id"]}: invalid building')
    if r['day_of_week'] not in valid_days:
        err(f'event {r["event_id"]}: invalid day')
    if r['shift'] not in valid_shifts:
        err(f'event {r["event_id"]}: invalid shift')
    if not (0 <= float(r['motorbike_ratio']) <= 1):
        err(f'event {r["event_id"]}: invalid motorbike_ratio')

print('DATASET VALIDATION — Digital Twin Lite v1.0')
print('-' * 52)
print(f'classes : {len(classes)}')
print(f'schedule: {len(schedule)}')
print(f'rooms   : {len(rooms)}')
print(f'parking : {len(parking)}')
print(f'events  : {len(events)}')
print('-' * 52)
if errors:
    for e in errors:
        print('ERROR:', e)
    print(f'\nSTATUS: FAIL ({len(errors)} error(s))')
    raise SystemExit(1)
else:
    print('Duplicate IDs             : 0')
    print('Invalid class/room FK      : 0')
    print('Building/floor/cap mismatch: 0')
    print('Room capacity violations   : 0')
    print('Room conflicts             : 0')
    print('Sessions/week mismatch     : 0')
    print('Parking schema/formula err : 0')
    print('Event validation errors    : 0')
    print('\nSTATUS: PASS')
