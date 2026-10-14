"""
=============================================================================
TÀI LIỆU & CODE MẪU TÍCH HỢP DÀNH CHO DEVELOPER HRMS / PHẦN MỀM BÊN NGOÀI
HỆ THỐNG ĐIỂM DANH KHUÔN MẶT AI (SMART FACE ATTENDANCE SYSTEM)
=============================================================================
Mục đích:
    File mẫu này hướng dẫn Developer phía HRMS cách gọi API để kéo toàn bộ
    dữ liệu chấm công từ Hệ thống Camera AI về máy chủ HRMS.

Thông tin kết nối API:
    - Base URL: http://<IP_SERVER_CAMERA>:5055
      (Ví dụ nội bộ: http://192.168.5.99:5055 hoặc http://localhost:5055)
    - Endpoint danh sách : GET /api/v1/attendance/records (hoặc /api/v1/attendance/logs)
    - Endpoint mới nhất  : GET /api/v1/attendance/latest
    - Token bảo mật      : smart@things!2020@HRMS*** (truyền qua query ?token=... hoặc Header)

Cách chạy thử file này:
    python client_hrms_attendance_sample.py
    python client_hrms_attendance_sample.py 2026-10-12
    python client_hrms_attendance_sample.py 2026-10-12 NV3539
=============================================================================
"""

import os
import sys
import json
import base64
import requests
from datetime import datetime

# Cấu hình UTF-8 cho console Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# =============================================================================
# 1. CẤU HÌNH THÔNG SỐ KẾT NỐI (HRMS DEV CẬP NHẬT IP TẠI ĐÂY)
# =============================================================================
CAMERA_SERVER_IP = "192.168.5.99"   # Đổi thành IP máy chủ Camera của bạn (hoặc localhost)
CAMERA_SERVER_PORT = "5055"
BASE_API_URL = f"http://{CAMERA_SERVER_IP}:{CAMERA_SERVER_PORT}"

# Mã bảo mật (Trùng khớp với cấu hình hệ thống)
API_SECURITY_TOKEN = "smart@things!2020@HRMS***"

# Thư mục lưu ảnh snapshot chấm công khi tải về (tùy chọn)
DOWNLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hrms_downloaded_snapshots")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)


# =============================================================================
# 2. HÀM KÉO DANH SÁCH BẢN GHI CHẤM CÔNG (THEO NGÀY / MÃ NHÂN VIÊN)
# =============================================================================
def fetch_attendance_logs(date=None, emp_code=None, limit=100, include_base64=False):
    """
    Gọi API lấy danh sách các lượt chấm công từ máy chủ Camera AI.
    
    Tham số:
        date (str): Ngày cần lấy định dạng 'YYYY-MM-DD' (mặc định là hôm nay, truyền 'all' nếu lấy tất cả)
        emp_code (str): Mã nhân viên cần lọc (ví dụ: 'NV3539'), None nếu lấy toàn bộ
        limit (int): Số lượng bản ghi tối đa (mặc định 100, tối đa 1000)
        include_base64 (bool): True nếu muốn nhận kèm chuỗi ảnh Base64
    
    Trả về:
        list: Danh sách các bản ghi chấm công chuẩn
    """
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")

    endpoint = f"{BASE_API_URL}/api/v1/attendance/records"
    params = {
        "date": date,
        "token": API_SECURITY_TOKEN,
        "limit": limit,
        "include_base64": "true" if include_base64 else "false"
    }
    if emp_code:
        params["emp_code"] = emp_code.strip().upper()

    print(f"[*] Đang gọi API: {endpoint}")
    print(f"[*] Tham số: {params}\n")

    try:
        response = requests.get(endpoint, params=params, timeout=15)
        if response.status_code == 200:
            result = response.json()
            total = result.get("total_records", 0)
            data = result.get("data", [])
            print(f"[✓] Gọi API thành công! Nhận được: {len(data)} / tổng số {total} bản ghi.")
            return data
        elif response.status_code == 401:
            print("[!] Lỗi 401: Sai Token bảo mật (Unauthorized).")
        else:
            print(f"[!] Lỗi kết nối API, HTTP Status: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"[!] Lỗi ngoại lệ khi gọi API: {e}")

    return []


# =============================================================================
# 3. HÀM KÉO BẢN GHI CHẤM CÔNG MỚI NHẤT (POLLING REAL-TIME)
# =============================================================================
def fetch_latest_attendance():
    """
    Gọi API lấy 1 sự kiện chấm công vừa mới xảy ra tức thì (thích hợp làm màn hình hiển thị hoặc đồng bộ thời gian thực).
    """
    endpoint = f"{BASE_API_URL}/api/v1/attendance/latest"
    try:
        response = requests.get(endpoint, timeout=5)
        if response.status_code == 200:
            result = response.json()
            return result.get("data")
    except Exception as e:
        print(f"[!] Lỗi gọi latest event: {e}")
    return None


# =============================================================================
# 4. HÀM LƯU ẢNH CHẤM CÔNG VỀ MÁY CHỦ HRMS
# =============================================================================
def save_snapshot_image(record):
    """
    Lưu ảnh chụp lúc chấm công của nhân viên về thư mục cục bộ hoặc Database HRMS.
    """
    emp = record.get("employee", {})
    att = record.get("attendance", {})
    code = emp.get("code", "UNKNOWN")
    ts = att.get("timestamp", 0)
    save_filename = f"checkin_{code}_{ts}.jpg"
    save_path = os.path.join(DOWNLOAD_DIR, save_filename)

    # Cách A: Lưu từ Base64 (nếu có yêu cầu include_base64=True)
    b64_data = att.get("snapshot_base64", "")
    if b64_data:
        try:
            if "base64," in b64_data:
                b64_data = b64_data.split("base64,")[1]
            with open(save_path, "wb") as f:
                f.write(base64.b64decode(b64_data))
            return save_path
        except Exception as e:
            print(f"  [!] Lỗi giải mã Base64: {e}")

    # Cách B: Tải trực tiếp qua URL ảnh (snapshot_url)
    snap_url = att.get("snapshot_url", "")
    if snap_url:
        try:
            r = requests.get(snap_url, timeout=10)
            if r.status_code == 200:
                with open(save_path, "wb") as f:
                    f.write(r.content)
                return save_path
        except Exception as e:
            print(f"  [!] Lỗi tải ảnh qua URL: {e}")

    return None


# =============================================================================
# 5. CHƯƠNG TRÌNH CHÍNH (DEMO TEST TRỰC QUAN)
# =============================================================================
def main():
    # Nhận tham số ngày và mã nhân viên từ dòng lệnh (nếu có)
    target_date = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime("%Y-%m-%d")
    target_code = sys.argv[2] if len(sys.argv) > 2 else None

    print("=" * 70)
    print("DEMO KÉO DỮ LIỆU ĐIỂM DANH TỪ CAMERA AI VỀ HỆ THỐNG HRMS")
    print(f"  - Ngày kiểm tra   : {target_date}")
    print(f"  - Mã NV cần lọc   : {target_code or 'Tất cả'}")
    print("=" * 70)

    # 1. Gọi API lấy dữ liệu (kèm Base64 để lưu ảnh)
    records = fetch_attendance_logs(
        date=target_date,
        emp_code=target_code,
        limit=10,
        include_base64=True
    )

    if not records:
        print("[!] Không có dữ liệu chấm công phù hợp.")
        return

    # 2. Xử lý và hiển thị từng bản ghi dữ liệu
    for idx, item in enumerate(records):
        emp = item["employee"]
        att = item["attendance"]
        dev = att["device"]

        print(f"\n--- BẢN GHI #{idx + 1} ---")
        print(f"  • ID Hệ Thống     : {emp['emp_id']}")
        print(f"  • Mã Nhân Viên    : {emp['code']}")
        print(f"  • Họ và Tên       : {emp['name']}")
        print(f"  • Chức Danh       : {emp['role']}")
        print(f"  • Phòng Ban       : {emp['dept']}")
        print(f"  • Công Ty         : {emp['company']}")
        print(f"  • Ngạch Lương     : {emp['salary_class']}")
        print(f"  • Trạng Thái      : {emp['status']}")
        print(f"  -------------------------------------------------------")
        print(f"  • Thời Gian Chấm  : {att['checkin_time']} (Unix: {att['timestamp']})")
        print(f"  • Thiết Bị Chấm   : {dev['name']} [Vị trí: {dev['location']}] (ID: {dev['id']})")
        print(f"  • Độ Tin Cậy AI   : {att['confidence']}%")
        print(f"  • URL Ảnh Chấm    : {att['snapshot_url']}")
        print(f"  • URL Ảnh Hồ Sơ   : {att['avatar_url']}")

        # 3. Tải và lưu ảnh snapshot về máy HRMS
        saved_file = save_snapshot_image(item)
        if saved_file:
            print(f"  [+] Đã lưu ảnh khuôn mặt thực tế vào: {os.path.basename(saved_file)}")

    print("\n" + "=" * 70)
    print(f"[✓] HOÀN TẤT ĐỒNG BỘ: Đã xử lý thành công {len(records)} lượt chấm công.")
    print("=" * 70)


if __name__ == "__main__":
    main()
