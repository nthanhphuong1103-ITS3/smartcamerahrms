import sys, re
sys.stdout.reconfigure(encoding='utf-8')

with open('kiosk_portal.py', 'r', encoding='utf-8') as f:
    kiosk_code = f.read()

print("=== CHECKING kiosk_portal.py ===")
# Find lines with potential issues, accents, or reverse text
for line_no, line in enumerate(kiosk_code.splitlines(), 1):
    if any(k in line.lower() for k in ['chấm công', 'khuôn mặt', 'ảnh', 'vị trí', 'phòng ban', 'lịch sử', 'giả mạo', 'thông báo', 'ngược', 'font']):
        if len(line.strip()) < 120 and not line.strip().startswith('//') and not line.strip().startswith('/*'):
            # sample interesting lines
            pass

# Let's inspect all Vietnamese text in kiosk_portal.py:
pattern = re.compile(r'["\']([^"\']*[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđÀÁẠẢÃÂẦẤẬẨẪĂẰẮẶẲẴÈÉẸẺẼÊỀẾỆỂỄÌÍỊỈĨÒÓỌỎÕÔỒỐỘỔỖƠỜỚỢỞỠÙÚỤỦŨƯỪỨỰỬỮỲÝỴỶỸĐ][^"\']*)["\']')
matches = pattern.findall(kiosk_code)
print(f"Total Vietnamese string literals found in kiosk_portal.py: {len(matches)}")
for m in sorted(set(matches)):
    if len(m) < 100:
        print(f"  - {m}")
