"""Phan tich luot cham cong buoi sang - so sanh theo ngay"""
import csv, sys
from datetime import datetime
from collections import defaultdict
sys.stdout.reconfigure(encoding='utf-8')

LOG_PATH = 'attendance_api_log.csv'

with open(LOG_PATH, 'r', encoding='utf-8-sig') as f:
    rows = list(csv.reader(f))

day_counts   = defaultdict(int)
cam_counts   = defaultdict(lambda: defaultdict(int))
conf_dist    = defaultdict(list)
all_counts   = defaultdict(int)   # toan ngay

for row in rows:
    if len(row) < 9:
        continue
    try:
        dt = datetime.strptime(row[0].strip('"'), '%Y-%m-%d %H:%M:%S')
    except:
        continue

    day  = dt.strftime('%Y-%m-%d')
    dow  = dt.strftime('%A')
    cam  = row[9].strip('"') if len(row) > 9 else 'Unknown'
    conf_str = row[8].strip('"').replace('%', '').strip()
    try:
        conf = float(conf_str)
    except:
        conf = 0.0

    all_counts[day] += 1

    # Chi lay gio sang 6-11h
    if 6 <= dt.hour < 11:
        day_counts[day] += 1
        cam_counts[day][cam] += 1
        conf_dist[day].append(conf)

print('=' * 80)
print('LUOT CHAM CONG BUOI SANG (06:00-11:00) TUNG NGAY')
print('=' * 80)
print(f'{"Ngay":<13} {"Thu":<11} {"Tong sang":>10}  {">=93%":>6}  {"87-93%":>7}  {"75-87%":>7}  {"<75%":>6}  {"Trung binh":>11}')
print('-' * 80)

for day in sorted(day_counts.keys()):
    total = day_counts[day]
    confs = conf_dist[day]
    dow = datetime.strptime(day, '%Y-%m-%d').strftime('%A')
    c93  = sum(1 for c in confs if c >= 93.0)
    c87  = sum(1 for c in confs if 87.0 <= c < 93.0)
    c75  = sum(1 for c in confs if 75.0 <= c < 87.0)
    clow = sum(1 for c in confs if c < 75.0)
    avg  = sum(confs)/len(confs) if confs else 0
    print(f'{day:<13} {dow:<11} {total:>10}  {c93:>6}  {c87:>7}  {c75:>7}  {clow:>6}  {avg:>10.1f}%')

print()
print('=' * 80)
print('PHAN TICH THEO CAMERA (buoi sang 06-11h)')
print('=' * 80)

all_days = sorted(day_counts.keys())
all_cams = sorted(set(cam for day in all_days for cam in cam_counts[day]))
header = f'{"Ngay":<13} ' + ''.join(f'{c[:18]:>20}' for c in all_cams)
print(header)
print('-' * (13 + 20 * len(all_cams)))
for day in all_days:
    row_str = f'{day:<13} ' + ''.join(f'{cam_counts[day].get(c, 0):>20}' for c in all_cams)
    print(row_str)

print()
print('=' * 80)
print('TONG LUOT TOAN NGAY')
print('=' * 80)
for day in sorted(all_counts.keys()):
    dow = datetime.strptime(day, '%Y-%m-%d').strftime('%A')
    print(f'{day} {dow:<11}: {all_counts[day]:>5} luot')
