"""
Công cụ tra cứu thông tin 1 nhân sự và tải ảnh hồ sơ từ API / Cache
Cách dùng:
    python get_employee.py NV0005
    python get_employee.py 1081407382
    python get_employee.py "Tuấn"
"""

import os
import sys
import json
import requests
import time
import hmac
import hashlib

# Cấu hình UTF-8 cho console Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(BASE_DIR, "api_employees_cache.json")
LOCAL_FACES_DIR = os.path.join(BASE_DIR, "api_faces")

def call_hrms_api():
    """Gọi trực tiếp API Smart HRMS với HMAC-MD5 nếu cần dữ liệu tươi nhất từ máy chủ"""
    api_url = "https://i-officeapi.ltacv.com/api/data/process/Getdata_List_Employee_Full"
    sec_code = "smart@things!2020@HRMS***"
    code_name = "Getdata_List_Employee_Full"
    username = "noname"

    reqtime = int(time.time() * 1000)
    data_payload = {}
    json_string = json.dumps(data_payload, separators=(',', ':')).replace(' ', '').replace('\r', '').replace('\n', '').replace('"', "'")
    datastring = f"{json_string}#{username}#{code_name}#{reqtime}"
    token = hmac.new(sec_code.encode('utf-8'), datastring.encode('utf-8'), hashlib.md5).hexdigest()

    body = {"token": token, "reqtime": reqtime, "data": data_payload}
    headers = {'Content-Type': 'application/json'}
    resp = requests.post(api_url, json=body, headers=headers, timeout=12)
    if resp.status_code == 200:
        return resp.json().get("data", [])
    return []

def find_employee(query):
    query_clean = str(query).strip().upper()
    employees = {}

    # 1. Đọc từ cache trước (tốc độ tức thì)
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                employees = json.load(f)
        except Exception:
            pass

    # Tìm kiếm theo ID, Mã nhân viên (EmployeeCode) hoặc Tên (FullName)
    matched = []
    for emp_id, emp in employees.items():
        code = str(emp.get("EmployeeCode", "")).strip().upper()
        name = str(emp.get("FullName", "")).strip().upper()
        eid = str(emp_id).strip().upper()

        if query_clean == code or query_clean == eid:
            return [emp]  # Khớp chính xác tuyệt đối
        elif query_clean in code or query_clean in name:
            matched.append(emp)

    return matched

def main():
    if len(sys.argv) < 2:
        print("=" * 60)
        print("CÁCH SỬ DỤNG:")
        print("  python get_employee.py <MÃ_NV hoặc TÊN hoặc ID>")
        print("Ví dụ:")
        print("  python get_employee.py NV0005")
        print("  python get_employee.py 1081407382")
        print("  python get_employee.py \"Lê Thanh Tuấn\"")
        print("=" * 60)
        return

    query = sys.argv[1]
    results = find_employee(query)

    if not results:
        print(f"[!] Không tìm thấy nhân sự phù hợp với từ khóa: '{query}'")
        return

    for idx, emp in enumerate(results[:5]):
        emp_id = emp.get("ID")
        code = emp.get("EmployeeCode", "--")
        name = emp.get("FullName", "--")
        role = emp.get("Name_Role", "--")
        dept = emp.get("Dept_Name", "--")
        company = emp.get("Company_Name", "--")
        salary = emp.get("SalaryClassName", "--")
        status = emp.get("EmployeeStatus_Name", "--")
        img_url = emp.get("Image_Url", "")

        print("=" * 60)
        print(f"THÔNG TIN NHÂN SỰ [{idx + 1}/{len(results)}]")
        print(f"  • ID Hệ Thống   : {emp_id}")
        print(f"  • Mã Nhân Viên  : {code}")
        print(f"  • Họ và Tên     : {name}")
        print(f"  • Chức Danh     : {role}")
        print(f"  • Phòng Ban     : {dept}")
        print(f"  • Công Ty       : {company}")
        print(f"  • Ngạch Lương   : {salary}")
        print(f"  • Trạng Thái    : {status}")
        print(f"  • URL Ảnh Gốc   : {img_url or 'Chưa có'}")

        # Tải / Xuất ảnh
        saved_img_name = f"{code}_{emp_id}.jpg"
        saved_img_path = os.path.join(BASE_DIR, saved_img_name)

        # Kiểm tra ảnh cục bộ có sẵn không
        local_path = os.path.join(LOCAL_FACES_DIR, f"{emp_id}.jpg")
        if os.path.exists(local_path):
            with open(local_path, "rb") as rf, open(saved_img_path, "wb") as wf:
                wf.write(rf.read())
            print(f"  [+] Đã lấy ảnh thẻ thành công từ thư mục local: {saved_img_name}")
        elif img_url:
            print(f"  [*] Đang tải ảnh trực tiếp từ API URL...")
            try:
                r = requests.get(img_url, timeout=10)
                if r.status_code == 200:
                    with open(saved_img_path, "wb") as wf:
                        wf.write(r.content)
                    print(f"  [+] Đã tải và lưu ảnh về file: {saved_img_name}")
                else:
                    print(f"  [!] Lỗi tải ảnh, mã phản hồi: {r.status_code}")
            except Exception as e:
                print(f"  [!] Lỗi tải ảnh từ URL: {e}")
        else:
            print("  [!] Nhân viên này không có ảnh trên hệ thống.")

    print("=" * 60)

if __name__ == "__main__":
    main()
