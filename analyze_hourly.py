"""Phan tich chi tiet theo gio - so sanh truoc va sau khi sua code"""
import csv, sys
from datetime import datetime
from collections import defaultdict
sys.stdout.reconfigure(encoding='utf-8')

with open('attendance_api_log.csv', 'r', encoding='utf-8-sig') as f:
    rows = list(csv.reader(f))

oct3_before = defaultdict(int)
oct3_conf_b = defaultdict(list)
oct3_after  = defaultdict(int)
oct3_conf_a = defaultdict(list)
oct5_hour   = defaultdict(int)
oct5_conf   = defaultdict(list)
oct4_hour   = defaultdict(int)
oct4_conf   = defaultdict(list)

# Phan loai theo tuan truoc (29/09 - 02/10) - buoi sang
prev_week_by_hour = defaultdict(list)  # hour -> list of counts per day

for row in rows:
    if len(row) < 9:
        continue
    try:
        dt = datetime.strptime(row[0].strip('"'), '%Y-%m-%d %H:%M:%S')
    except:
        continue
    conf_str = row[8].strip('"').replace('%', '').strip()
    try:
        conf = float(conf_str)
    except:
        conf = 0.0

    day = dt.strftime('%Y-%m-%d')
    h   = dt.hour

    if day == '2026-10-03':
        if dt.hour < 12:
            oct3_before[h] += 1
            oct3_conf_b[h].append(conf)
        else:
            oct3_after[h] += 1
            oct3_conf_a[h].append(conf)

    if day == '2026-10-04':
        oct4_hour[h] += 1
        oct4_conf[h].append(conf)

    if day == '2026-10-05':
        oct5_hour[h] += 1
        oct5_conf[h].append(conf)

print('=' * 78)
print('NGAY 03/10 BUOI SANG (TRUOC KHI SUA CODE LUC 12h11)')
print('  -> Code cu: MIN_ACCURACY=75%, khong co Unknown rejection, streak>=2')
print('=' * 78)
print(f'{"Gio":>5}  {"So luot":>8}  {"Conf TB":>9}  {">=87%":>6}  {"75-87%":>7}  {"<75%":>5}')
print('-' * 55)
total3b = 0
for h in sorted(oct3_before.keys()):
    confs = oct3_conf_b[h]
    avg   = sum(confs)/len(confs) if confs else 0
    c87   = sum(1 for c in confs if c >= 87)
    c75   = sum(1 for c in confs if 75 <= c < 87)
    clow  = sum(1 for c in confs if c < 75)
    total3b += oct3_before[h]
    print(f'{h:>5}h: {oct3_before[h]:>8}  {avg:>8.1f}%  {c87:>6}  {c75:>7}  {clow:>5}')
print(f'{"TONG":>5}   {total3b:>8}')

print()
print('=' * 78)
print('NGAY 03/10 SAU 12h (SAU KHI SUA CODE)')
print('  -> Code moi: MIN_ACCURACY=87%, Unknown reject Cosine<0.55, streak>=3')
print('=' * 78)
total3a = 0
for h in sorted(oct3_after.keys()):
    confs = oct3_conf_a[h]
    avg   = sum(confs)/len(confs) if confs else 0
    total3a += oct3_after[h]
    print(f'{h:>5}h: {oct3_after[h]:>8}  {avg:>8.1f}%')
print(f'{"TONG":>5}   {total3a:>8}')

print()
print('=' * 78)
print('NGAY 04/10 (CHU NHAT) - CODE MOI')
print('=' * 78)
total4 = 0
for h in sorted(oct4_hour.keys()):
    confs = oct4_conf[h]
    avg   = sum(confs)/len(confs) if confs else 0
    total4 += oct4_hour[h]
    print(f'{h:>5}h: {oct4_hour[h]:>8}  {avg:>8.1f}%')
print(f'{"TONG":>5}   {total4:>8}')

print()
print('=' * 78)
print('NGAY 05/10 SANG NAY - CODE MOI')
print('=' * 78)
print(f'{"Gio":>5}  {"So luot":>8}  {"Conf TB":>9}  {">=93%":>6}  {"87-93%":>7}  {"<87%":>6}')
print('-' * 55)
total5 = 0
for h in sorted(oct5_hour.keys()):
    confs = oct5_conf[h]
    avg   = sum(confs)/len(confs) if confs else 0
    c93   = sum(1 for c in confs if c >= 93)
    c87   = sum(1 for c in confs if 87 <= c < 93)
    clow  = sum(1 for c in confs if c < 87)
    total5 += oct5_hour[h]
    print(f'{h:>5}h: {oct5_hour[h]:>8}  {avg:>8.1f}%  {c93:>6}  {c87:>7}  {clow:>6}')
print(f'{"TONG":>5}   {total5:>8}')

print()
print('=' * 78)
print('KET LUAN SO SANH')
print('=' * 78)
print(f'  Tuan truoc trung binh sang (6-11h): ~100-180 luot/ngay')
print(f'  03/10 sang (code cu):   {total3b} luot')
print(f'  03/10 chieu (code moi): {total3a} luot')
print(f'  05/10 sang hom nay:     {total5} luot (den luc {datetime.now().strftime("%H:%M")})')
