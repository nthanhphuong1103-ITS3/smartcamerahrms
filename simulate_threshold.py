"""
Simulation: Kiem tra anh huong cua cac nguong khac nhau tren du lieu thuc te
KHONG sua code - chi mo phong va phan tich
"""
import csv, sys
from datetime import datetime
from collections import defaultdict
sys.stdout.reconfigure(encoding='utf-8')

# ============================================================
# Doc du lieu log thuc te
# ============================================================
LOG_PATH = 'attendance_api_log.csv'
with open(LOG_PATH, 'r', encoding='utf-8-sig') as f:
    rows = list(csv.reader(f))

records = []
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
    cam = row[9].strip('"') if len(row) > 9 else 'Unknown'
    day = dt.strftime('%Y-%m-%d')
    records.append({'dt': dt, 'conf': conf, 'cam': cam, 'day': day})

# ============================================================
# Dinh nghia cac kich ban nguong
# Luu y: du lieu log chi co conf%, KHONG co cosine raw hay streak rieng biet.
# => Dung conf% de uoc tinh:
#    Cosine ~0.47 = 75%,  0.50 = 80%,  0.55 = 87%,  0.58 = 90%,  0.65 = 98%
#    Cong thuc: cosine = 0.363 + (conf% - 60) / 40 * (0.65 - 0.363)  khi conf >= 60%
#
# Uoc tinh cosine tu conf%:
def conf_to_cosine(conf_pct):
    if conf_pct <= 60.0:
        return (conf_pct / 60.0) * 0.363
    else:
        return 0.363 + ((conf_pct - 60.0) / 40.0) * (0.65 - 0.363)

# ============================================================
# Cac kich ban kiem tra
# ============================================================
scenarios = {
    'A - Hien tai (code moi, qua chat)': {
        'min_acc': 87.0,
        'cosine_reject': 0.55,
        'streak_needed': 3,
        'instant_trigger': 93.0,
    },
    'B - De xuat nguoi dung (80%/0.50)': {
        'min_acc': 80.0,
        'cosine_reject': 0.50,
        'streak_needed': 2,
        'instant_trigger': 90.0,
    },
    'C - Trung binh (82%/0.52)': {
        'min_acc': 82.0,
        'cosine_reject': 0.52,
        'streak_needed': 2,
        'instant_trigger': 90.0,
    },
    'D - Code cu (75% khong reject)': {
        'min_acc': 75.0,
        'cosine_reject': 0.00,  # Khong reject (code cu)
        'streak_needed': 2,
        'instant_trigger': 80.0,
    },
}

# ============================================================
# Tinh toan cho tung kich ban tren du lieu TRUOC khi sua (29/09 - 03/10 truoc 12h)
# Day la du lieu "thuc te" cua nguoi that - ghi nhan boi code cu
# ============================================================
baseline_days = ['2026-09-29', '2026-09-30', '2026-10-01', '2026-10-02']
oct3_morning  = [r for r in records if r['day'] == '2026-10-03' and r['dt'].hour < 12]
baseline_recs = [r for r in records if r['day'] in baseline_days and 6 <= r['dt'].hour < 11]
baseline_recs += oct3_morning

print('=' * 80)
print('SIMULATION: UONG NGUONG PHAN TICH TREN DU LIEU THUC TE (code cu, nguoi that)')
print(f'Du lieu: {len(baseline_recs)} luot cham cong thuc te (29/09-03/10 sang, 6-11h)')
print('=' * 80)

for sc_name, sc in scenarios.items():
    min_acc      = sc['min_acc']
    cosine_rej   = sc['cosine_reject']
    streak_needed= sc['streak_needed']
    instant_trig = sc['instant_trigger']

    accepted = 0
    rejected_cosine = 0  # Bi reject vi cosine < nguong (coi la nguoi la)
    rejected_acc    = 0  # Bi reject vi conf < min_acc
    rejected_streak = 0  # Bi reject vi can streak nhung chi co 1 frame (uoc tinh)

    for r in baseline_recs:
        cosine = conf_to_cosine(r['conf'])

        # Buoc 1: Unknown rejection (cosine thap -> nguoi la)
        if cosine < cosine_rej:
            rejected_cosine += 1
            continue

        # Buoc 2: Kiem tra nguong chinh
        if r['conf'] < min_acc:
            rejected_acc += 1
            continue

        # Buoc 3: Dual-threshold - uoc tinh streak
        # Gia dinh: 60% truong hop dat du streak (cam nha an chuyen dong cham)
        #           40% truong hop chi co 1-2 frame (cam cau thang, nguoi di nhanh)
        if r['conf'] >= instant_trig:
            # Instant trigger - khong can streak
            accepted += 1
        else:
            # Can streak - uoc tinh 60% dat duoc streak can thiet
            # (dua tren ti le cam nha an vs cau thang tu du lieu)
            cam_lower = r['cam'].lower()
            if 'cau thang' in cam_lower or 'loi di' in cam_lower:
                # Cam cau thang: nguoi di nhanh, streak kho dat
                # streak>=3: chi ~30% dat duoc
                # streak>=2: chi ~60% dat duoc
                streak_prob = 0.30 if streak_needed >= 3 else 0.60
            else:
                # Cam nha an / phong: nguoi dung lau, streak de dat
                # streak>=3: ~70% dat duoc
                # streak>=2: ~85% dat duoc
                streak_prob = 0.70 if streak_needed >= 3 else 0.85

            import random
            # Dung xac suat uoc tinh (deterministic bang hash)
            seed = hash((r['dt'].isoformat(), r['conf'])) % 1000
            if seed < streak_prob * 1000:
                accepted += 1
            else:
                rejected_streak += 1

    total = len(baseline_recs)
    acc_pct = accepted / total * 100 if total > 0 else 0
    print(f'\nKich ban {sc_name}')
    print(f'  Nguong chap nhan : min_acc={min_acc}% | cosine_reject={cosine_rej} | streak>={streak_needed} | instant>={instant_trig}%')
    print(f'  Tong du lieu goc : {total:>5} luot')
    print(f'  Duoc chap nhan   : {accepted:>5} luot  ({acc_pct:.1f}%)')
    print(f'  Bi reject cosine : {rejected_cosine:>5} luot  ({rejected_cosine/total*100:.1f}%) <- Phat hien nguoi la')
    print(f'  Bi reject acc%   : {rejected_acc:>5} luot  ({rejected_acc/total*100:.1f}%) <- Conf qua thap')
    print(f'  Bi reject streak : {rejected_streak:>5} luot  ({rejected_streak/total*100:.1f}%) <- Di nhanh, it frame')

print()
print('=' * 80)
print('PHAN TICH THEO KHUNG GIO & CAMERA (so sanh kich ban A vs B)')
print('=' * 80)

# Phan tich rieng theo camera
cams_of_interest = sorted(set(r['cam'] for r in baseline_recs))

for cam in cams_of_interest:
    cam_recs = [r for r in baseline_recs if r['cam'] == cam]
    if not cam_recs:
        continue
    print(f'\n  Camera: {cam} ({len(cam_recs)} luot)')

    for sc_name in ['A - Hien tai (code moi, qua chat)', 'B - De xuat nguoi dung (80%/0.50)']:
        sc = scenarios[sc_name]
        min_acc   = sc['min_acc']
        cos_rej   = sc['cosine_reject']
        instant_t = sc['instant_trigger']

        acc = sum(1 for r in cam_recs
                  if conf_to_cosine(r['conf']) >= cos_rej and r['conf'] >= min_acc)
        print(f'    {sc_name[:35]:35}: {acc:>4}/{len(cam_recs)} luot ({acc/len(cam_recs)*100:.0f}%) chap nhan')

print()
print('=' * 80)
print('PHAN BO CONFIDENCE% CUA DU LIEU THUC TE (de chon nguong phu hop)')
print('=' * 80)
buckets = [
    ('<75%',   0,  75),
    ('75-80%', 75, 80),
    ('80-82%', 80, 82),
    ('82-87%', 82, 87),
    ('87-90%', 87, 90),
    ('90-93%', 90, 93),
    ('>=93%',  93, 101),
]
total = len(baseline_recs)
print(f'{"Khoang":>10}  {"So luot":>8}  {"Ti le":>7}  {"Cosine uoc tinh":>16}')
print('-' * 50)
for label, lo, hi in buckets:
    cnt = sum(1 for r in baseline_recs if lo <= r['conf'] < hi)
    cos_lo = f'{conf_to_cosine(lo):.3f}' if lo > 0 else '<0.363'
    cos_hi = f'{conf_to_cosine(hi):.3f}' if hi < 101 else '>0.65'
    print(f'{label:>10}  {cnt:>8}  {cnt/total*100:>6.1f}%  {cos_lo} - {cos_hi}')

print()
print('NHAN XET:')
cosine_050_count = sum(1 for r in baseline_recs if conf_to_cosine(r['conf']) < 0.50)
cosine_055_count = sum(1 for r in baseline_recs if conf_to_cosine(r['conf']) < 0.55)
acc80_count      = sum(1 for r in baseline_recs if r['conf'] >= 80.0)
acc87_count      = sum(1 for r in baseline_recs if r['conf'] >= 87.0)
print(f'  Cosine < 0.50 (bi reject voi nguong B): {cosine_050_count}/{total} = {cosine_050_count/total*100:.1f}%')
print(f'  Cosine < 0.55 (bi reject voi nguong A): {cosine_055_count}/{total} = {cosine_055_count/total*100:.1f}%')
print(f'  Conf >= 80%  (vuot nguong B):           {acc80_count}/{total} = {acc80_count/total*100:.1f}%')
print(f'  Conf >= 87%  (vuot nguong A):           {acc87_count}/{total} = {acc87_count/total*100:.1f}%')
print()
print(f'  => Nguong B (80%/0.50): cho phep {acc80_count/total*100:.0f}% du lieu goc di qua (truoc kiem tra streak/pitch)')
print(f'  => Nguong A (87%/0.55): chi cho phep {acc87_count/total*100:.0f}% du lieu goc di qua')
print(f'  => Du lieu thuc te: {(cosine_055_count-cosine_050_count)/total*100:.1f}% nam trong vung TRANH CAI (0.50-0.55 cosine)')
