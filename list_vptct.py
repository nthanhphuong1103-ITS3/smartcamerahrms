"""
=============================================================================
CÔNG CỤ TRA CỨU & XUẤT DANH SÁCH NHÂN SỰ VĂN PHÒNG TỔNG CÔNG TY (VPTCT)
Dữ liệu gọi trực tiếp từ API Smart HRMS (kèm cơ chế dự phòng Cache)
=============================================================================
Cách sử dụng:
    python list_vptct.py              # Xem toàn bộ 128 nhân sự trên màn hình
    python list_vptct.py --csv        # Xuất file Excel/CSV: danh_sach_vptct.csv
    python list_vptct.py --find "Hằng"# Tìm kiếm nhân sự trong VPTCT
=============================================================================
"""

import os
import sys
import json
import csv
from datetime import datetime

# Cấu hình UTF-8 console Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(BASE_DIR, "api_employees_cache.json")

# Import hàm gọi API từ get_employee
try:
    from get_employee import call_hrms_api
except ImportError:
    call_hrms_api = None


def extract_val(field):
    if isinstance(field, dict):
        return str(field.get('v') or field.get('r') or '').strip()
    return str(field or '').strip()


def get_all_employees():
    """Lấy dữ liệu từ API Smart HRMS, nếu mất mạng tự động đọc từ Cache"""
    data = []
    if call_hrms_api:
        try:
            data = call_hrms_api()
        except Exception as e:
            print(f"[!] Không thể kết nối API trực tiếp ({e}), chuyển sang đọc cache...")

    if not data and os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                cached = json.load(f)
                data = list(cached.values()) if isinstance(cached, dict) else cached
        except Exception:
            pass

    return data


def get_vptct_employees(employees_data):
    """Lọc danh sách nhân viên có nơi làm việc là VĂN PHÒNG TỔNG CÔNG TY"""
    vptct = []
    for emp in employees_data:
        wp = extract_val(emp.get('WorkPlaceName')).upper()
        if 'VĂN PHÒNG TỔNG CÔNG TY' in wp or wp == 'VPTCT':
            vptct.append({
                "id": extract_val(emp.get("ID")),
                "code": extract_val(emp.get("EmployeeCode")),
                "name": extract_val(emp.get("FullName")),
                "role": extract_val(emp.get("Name_Role")) or "--",
                "dept": extract_val(emp.get("Dept_Name")) or "--",
                "company": extract_val(emp.get("Company_Name")) or "--",
                "status": extract_val(emp.get("EmployeeStatus_Name")) or "Đang làm việc",
                "email": extract_val(emp.get("OfficeEmail")) or "--",
                "mobile": extract_val(emp.get("Mobile")) or "--",
                "workplace": extract_val(emp.get("WorkPlaceName"))
            })

    # Sắp xếp theo mã nhân viên
    vptct.sort(key=lambda x: x["code"])
    return vptct


def export_to_csv(vptct_list, filename="danh_sach_vptct.csv"):
    """Xuất danh sách ra file CSV chuẩn UTF-8-SIG (mở trực tiếp bằng Excel không lỗi font)"""
    filepath = os.path.join(BASE_DIR, filename)
    headers = ["STT", "Mã NV", "Họ và Tên", "Chức Danh", "Phòng Ban", "Công Ty", "Trạng Thái", "Email", "Điện Thoại", "Nơi Làm Việc"]
    
    with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for idx, emp in enumerate(vptct_list, 1):
            writer.writerow([
                idx,
                emp["code"],
                emp["name"],
                emp["role"],
                emp["dept"],
                emp["company"],
                emp["status"],
                emp["email"],
                emp["mobile"],
                emp["workplace"]
            ])

    print(f"\n[✓] ĐÃ XUẤT FILE EXCEL/CSV THÀNH CÔNG: {filepath}")
    print(f"    Tổng số: {len(vptct_list)} nhân sự VPTCT.")


def main():
    print("=" * 85)
    print("  ĐANG KẾT NỐI VÀ LẤY DỮ LIỆU NHÂN SỰ TỪ SMART HRMS...")
    print("=" * 85)

    data = get_all_employees()
    vptct = get_vptct_employees(data)

    if not vptct:
        print("[!] Không tìm thấy nhân sự nào thuộc Văn phòng Tổng công ty.")
        return

    # Kiểm tra cờ tham số dòng lệnh
    args = sys.argv[1:]
    
    if "--csv" in args or "-c" in args:
        export_to_csv(vptct)
        return

    find_keyword = None
    for i, a in enumerate(args):
        if a in ("--find", "-f") and i + 1 < len(args):
            find_keyword = args[i + 1].strip().upper()
            break

    if find_keyword:
        filtered = [
            e for e in vptct
            if find_keyword in e["code"].upper()
            or find_keyword in e["name"].upper()
            or find_keyword in e["role"].upper()
            or find_keyword in e["dept"].upper()
        ]
        display_list = filtered
        print(f"[*] Kết quả tìm kiếm với từ khóa '{find_keyword}': {len(filtered)} nhân sự")
    else:
        display_list = vptct
        print(f"[*] TỔNG CỘNG: {len(vptct)} NHÂN SỰ THUỘC VĂN PHÒNG TỔNG CÔNG TY")

    print("-" * 105)
    print(f"{'STT':<4} | {'MÃ NV':<7} | {'HỌ VÀ TÊN':<26} | {'CHỨC DANH':<28} | {'TRẠNG THÁI':<12}")
    print("-" * 105)

    for idx, e in enumerate(display_list, 1):
        print(f"{idx:<4} | {e['code']:<7} | {e['name']:<26} | {e['role'][:28]:<28} | {e['status']:<12}")

    print("-" * 105)
    print(f"[✓] Tổng số hiển thị: {len(display_list)} nhân viên.")
    print("=" * 105)
    print("GỢI Ý CÂU LỆNH:")
    print("  - Xuất ra file Excel:  python list_vptct.py --csv")
    print("  - Tìm kiếm nhân sự:   python list_vptct.py --find <Tên/Mã NV>")
    print("=" * 105)


if __name__ == '__main__':
    main()
