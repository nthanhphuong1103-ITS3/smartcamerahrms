"""
ĐỒNG BỘ THỜI GIAN CAMERA IP VỚI MÁY CHỦ (SERVER PC)
=====================================================
Kịch bản đồng bộ thời gian tức thì cho tất cả camera Dahua trong cameras_config.json.
Sử dụng Dahua CGI API: /cgi-bin/global.cgi?action=setCurrentTime&time=YYYY-MM-DD%20HH:MM:SS
"""

import os
import re
import sys
import json
import requests
from requests.auth import HTTPDigestAuth
from datetime import datetime

# Đảm bảo in tiếng Việt chuẩn trên Windows terminal
sys.stdout.reconfigure(encoding='utf-8')

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cameras_config.json")

def sync_all_cameras():
    if not os.path.exists(CONFIG_PATH):
        print(f"[ERROR] Không tìm thấy file cấu hình: {CONFIG_PATH}")
        return

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cameras = json.load(f)

    print("==================================================================")
    print("   TIẾN TRÌNH ĐỒNG BỘ THỜI GIAN TOÀN BỘ CAMERA VỚI MÁY CHỦ")
    print("==================================================================")

    results = []

    for cam in cameras:
        cid = cam.get("id")
        name = cam.get("name")
        url = cam.get("url", "")
        location = cam.get("location", "")
        enabled = cam.get("enabled", True)

        m = re.match(r'rtsp://([^:]+):([^@]+)@([^:]+):', url)
        if not m:
            print(f"[-] [CAM {cid:02d}] {name}: Không thể phân tích RTSP URL!")
            results.append({"id": cid, "name": name, "status": "Lỗi URL", "diff": "--"})
            continue

        user, pwd, ip = m.groups()

        # 1. Lấy giờ máy chủ tại thời điểm gửi lệnh
        now = datetime.now()
        now_str = now.strftime("%Y-%m-%d %H:%M:%S")

        # 2. Gửi lệnh cập nhật giờ
        set_url = f"http://{ip}/cgi-bin/global.cgi?action=setCurrentTime&time={now_str}"
        try:
            r = requests.get(set_url, auth=HTTPDigestAuth(user, pwd), timeout=4)
            if r.status_code == 200 and "OK" in r.text:
                # 3. Đọc lại giờ thực tế trên camera để xác thực
                get_url = f"http://{ip}/cgi-bin/global.cgi?action=getCurrentTime"
                r_verify = requests.get(get_url, auth=HTTPDigestAuth(user, pwd), timeout=3)
                verified_time = r_verify.text.strip().replace("result=", "").strip()

                server_verify = datetime.now()
                try:
                    cam_dt = datetime.strptime(verified_time, "%Y-%m-%d %H:%M:%S")
                    diff = (cam_dt - server_verify).total_seconds()
                    diff_text = f"{diff:+.1f}s"
                except Exception:
                    diff_text = "OK"

                print(f"[✓] [CAM {cid:02d}] {name} ({ip}): ĐỒNG BỘ THÀNH CÔNG")
                print(f"    - Giờ máy chủ: {now_str}")
                print(f"    - Giờ camera:  {verified_time} (Lệch: {diff_text})")
                results.append({"id": cid, "name": name, "ip": ip, "status": "Thành công", "cam_time": verified_time, "diff": diff_text})
            else:
                print(f"[x] [CAM {cid:02d}] {name} ({ip}): Thất bại (HTTP {r.status_code} - {r.text.strip()})")
                results.append({"id": cid, "name": name, "ip": ip, "status": f"Lỗi ({r.status_code})", "diff": "--"})
        except Exception as e:
            print(f"[x] [CAM {cid:02d}] {name} ({ip}): Lỗi kết nối ({e})")
            results.append({"id": cid, "name": name, "ip": ip, "status": f"Mất kết nối", "diff": "--"})

    print("==================================================================")
    print("                      KẾT QUẢ ĐỒNG BỘ")
    print("==================================================================")
    print(f"{'CAM':<8} | {'TÊN CAMERA':<30} | {'IP':<15} | {'TRẠNG THÁI':<15} | {'LỆCH'}")
    print("-" * 75)
    for res in results:
        print(f"CAM {res['id']:02d}   | {res['name'][:28]:<30} | {res.get('ip', '--'):<15} | {res['status']:<15} | {res['diff']}")
    print("==================================================================")

if __name__ == "__main__":
    sync_all_cameras()
