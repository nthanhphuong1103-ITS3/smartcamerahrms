"""Verify cac thay doi trong web_face_attendance.py"""
import ast, sys, re
sys.stdout.reconfigure(encoding='utf-8')

with open('web_face_attendance.py', 'r', encoding='utf-8') as f:
    src = f.read()

# Kiem tra syntax
try:
    ast.parse(src)
    print('[OK] Syntax hop le - khong co loi')
except SyntaxError as e:
    print(f'[LOI] Dong {e.lineno}: {e.msg}')
    sys.exit(1)

# Verify hang so
min_acc = re.search(r'MIN_ACCURACY_THRESHOLD\s*=\s*([\d.]+)', src)
cos_rej = re.search(r'UNKNOWN_COSINE_THRESHOLD\s*=\s*([\d.]+)', src)
pitch   = re.search(r'pitch_ratio < ([\d.]+) or pitch_ratio > ([\d.]+)', src)
streak  = re.search(r'track\.streak >= (\d+)', src)
instant = re.search(r'conf_pct >= ([\d.]+)\) and not track\.attendance_logged', src)

print()
print('Kiem tra cac thong so sau khi cap nhat:')
print('-' * 50)
v = min_acc.group(1) if min_acc else 'KHONG TIM THAY'
print(f'  MIN_ACCURACY_THRESHOLD   : {v}%  (mong doi: 80.0%)')

v = cos_rej.group(1) if cos_rej else 'KHONG TIM THAY'
print(f'  UNKNOWN_COSINE_THRESHOLD : {v}   (mong doi: 0.50)')

if pitch:
    print(f'  Pitch angle range        : [{pitch.group(1)} - {pitch.group(2)}]  (mong doi: [0.30 - 3.0])')
else:
    print('  Pitch angle: KHONG TIM THAY')

v = streak.group(1) if streak else '?'
print(f'  Streak trigger           : >= {v}  (mong doi: >= 2)')

v = instant.group(1) if instant else '?'
print(f'  Instant trigger          : >= {v}%  (mong doi: >= 90.0%)')

print()
# Kiem tra dung so lan xuat hien (tranh bi trung lap)
min_acc_all = re.findall(r'MIN_ACCURACY_THRESHOLD\s*=\s*([\d.]+)', src)
cos_rej_all = re.findall(r'UNKNOWN_COSINE_THRESHOLD\s*=\s*([\d.]+)', src)
print(f'  So lan dinh nghia MIN_ACCURACY_THRESHOLD  : {len(min_acc_all)} (nen = 1)')
print(f'  So lan dinh nghia UNKNOWN_COSINE_THRESHOLD: {len(cos_rej_all)} (nen = 1)')
