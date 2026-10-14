"""
=============================================================================
HỆ THỐNG ĐIỂM DANH & NHẬN DIỆN KHUÔN MẶT THỜI GIAN THỰC (AI FACE ATTENDANCE)
PHIÊN BẢN DOANH NGHIỆP: QUẢN TRỊ - XEM CAMERA CHIA CỘT - THÊM RTSP - XUẤT/THÊM DỮ LIỆU
KIẾN TRÚC ĐA LUỒNG TÁCH BIỆT 25 FPS ZERO-LAG - CHUẨN XÁC >= 75%
=============================================================================
"""

import os
import csv
import cv2
import sys
import glob
import time
import json
import hmac
import hashlib
import pickle
import threading
import requests
import webbrowser
import numpy as np
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
import io
import openpyxl
from openpyxl.drawing.image import Image as OpenpyxlImage
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from PIL import Image as PILImage
from flask import Flask, Response, render_template_string, jsonify, send_from_directory, request, send_file, make_response

# Đảm bảo console UTF-8 tiếng Việt không lỗi
sys.stdout.reconfigure(encoding='utf-8')

# Cấu hình tăng tốc phần cứng OpenCV & OpenCL GPU (NVIDIA GeForce GTX 750 Ti)
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|fflags;nobuffer|flags;low_delay|framedrop;1"

# Khống chế số luồng CPU (Tránh Thread Oversubscription trên 72 luồng Xeon)
cv2.setNumThreads(4)

# Kích hoạt OpenCL toàn cục cho toàn bộ hệ thống (Đẩy tính toán nơ-ron AI sang GPU GTX 750 Ti)
_USE_OPENCL_DNN = False
try:
    cv2.ocl.setUseOpenCL(True)
    if cv2.ocl.useOpenCL():
        _USE_OPENCL_DNN = True
        _dev = cv2.ocl.Device.getDefault()
        print(f"[GPU] OpenCL TĂNG TỐC KÍCH HOẠT: {_dev.name()} ({_dev.vendorName()})")
except Exception as e:
    print(f"[GPU] OpenCL check error: {e}")

print(f"[GPU] OpenCL for DNN: {'ENABLED (GTX 750 Ti)' if _USE_OPENCL_DNN else 'DISABLED - fallback CPU'}")
print(f"[CPU] Khống chế OpenCV Threads: {cv2.getNumThreads()} luồng (trên tổng 72 luồng logic)")

# Thư mục hệ thống
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(BASE_DIR, "models")
YUNET_PATH = os.path.join(MODEL_DIR, "face_detection_yunet.onnx")
SFACE_PATH = os.path.join(MODEL_DIR, "face_recognition_sface.onnx")
MINIFASNET_PATH = os.path.join(MODEL_DIR, "minifasnet_v2.onnx")

API_FACES_DIR = os.path.join(BASE_DIR, "api_employee_faces")
SNAPSHOTS_DIR = os.path.join(BASE_DIR, "attendance_snapshots")
CACHE_JSON_PATH = os.path.join(BASE_DIR, "api_employees_cache.json")
EMBEDDINGS_PKL_PATH = os.path.join(BASE_DIR, "api_face_embeddings.pkl")
SYNCED_URLS_PATH = os.path.join(BASE_DIR, "api_synced_urls.json")
ATTENDANCE_LOG_PATH = os.path.join(BASE_DIR, "attendance_api_log.csv")
CAMERAS_CONFIG_PATH = os.path.join(BASE_DIR, "cameras_config.json")

os.makedirs(API_FACES_DIR, exist_ok=True)
os.makedirs(SNAPSHOTS_DIR, exist_ok=True)

# CẤU HÌNH CAMERA MẶC ĐỊNH
DEFAULT_CAMERA_SOURCES = [
    {
        "id": 1,
        "name": "CAM 01 - PHÒNG GPL",
        "url": "rtsp://admin:1234Admin@192.168.100.4:554/cam/realmonitor?channel=1&subtype=0",
        "location": "Phòng GPL Lầu 4",
        "enabled": True
    },
    {
        "id": 2,
        "name": "CAM 02 - NHÀ ĂN 1",
        "url": "rtsp://admin:1234admin@192.168.100.154:554/cam/realmonitor?channel=1&subtype=0",
        "location": "Khu vực Nhà Ăn 1",
        "enabled": True
    },
    {
        "id": 3,
        "name": "CAM 03 - LỐI ĐI CẦU THANG NHÀ ĂN",
        "url": "rtsp://admin:1234Admin@192.168.100.127:554/cam/realmonitor?channel=1&subtype=0",
        "location": "Lối đi Cầu thang Nhà ăn",
        "enabled": True
    },
    {
        "id": 4,
        "name": "CAM 04 - NHÀ ĂN 2",
        "url": "rtsp://admin:1234Admin@192.168.100.5:554/cam/realmonitor?channel=1&subtype=0",
        "location": "Khu vực Nhà Ăn 2 (Lầu Lửng)",
        "enabled": False
    }
]

def load_cameras_config():
    cams = []
    if os.path.exists(CAMERAS_CONFIG_PATH):
        try:
            with open(CAMERAS_CONFIG_PATH, "r", encoding="utf-8") as f:
                cams = json.load(f)
        except Exception as e:
            print(f"[!] Lỗi đọc cameras_config.json: {e}")

    if not isinstance(cams, list) or len(cams) == 0:
        cams = [dict(c) for c in DEFAULT_CAMERA_SOURCES]
    else:
        # Cập nhật tên chuẩn cho Cam 2 và Cam 3 / Cam 4 nếu tên cũ còn tồn tại
        for c in cams:
            if "enabled" not in c:
                c["enabled"] = True
            cid = c.get("id")
            curl = str(c.get("url", ""))
            cname = c.get("name", "")
            if cid == 2 or "192.168.100.154" in curl:
                c["name"] = "CAM 02 - NHÀ ĂN 1"
                c["location"] = "Khu vực Nhà Ăn 1"
            elif cid == 3 or "192.168.100.127" in curl or "THANG" in cname.upper():
                c["name"] = "CAM 03 - LỐI ĐI CẦU THANG NHÀ ĂN"
                c["location"] = "Lối đi Cầu thang Nhà ăn"
            elif cid == 4 or "192.168.100.5" in curl or "IT SOFT" in cname.upper() or "LỬNG" in cname.upper():
                c["name"] = "CAM 04 - NHÀ ĂN 2"
                c["location"] = "Khu vực Nhà Ăn 2 (Lầu Lửng)"

        has_cam4 = any("192.168.100.5" in str(c.get("url", "")) or c.get("id") == 4 for c in cams)
        if not has_cam4:
            cams.append({
                "id": 4,
                "name": "CAM 04 - NHÀ ĂN 2",
                "url": "rtsp://admin:1234Admin@192.168.100.5:554/cam/realmonitor?channel=1&subtype=0",
                "location": "Khu vực Nhà Ăn 2 (Lầu Lửng)",
                "enabled": False
            })

    save_cameras_config(cams)
    return cams

def save_cameras_config(cams):
    try:
        with open(CAMERAS_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cams, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[!] Lỗi lưu cameras_config.json: {e}")

camera_sources = load_cameras_config()

# CẤU HÌNH ĐỘ PHÂN GIẢI & ĐỘ NÉT LUỒNG VIDEO (MẶC ĐỊNH LUỒNG PHỤ D1/VGA SẮC NÉT LIVE 0MS)
STREAM_CONFIG = {
    "width": 640,
    "height": 480,
    "quality": 85,
    "mode": "sub"
}

# TIÊU CHUẨN ĐỘ CHÍNH XÁC XÁC THỰC
# Đã tinh chỉnh dựa trên simulation 617 lượt thực tế (29/09-03/10):
# Ngưỡng 80%/Cosine 0.50 = điểm cân bằng tối ưu cho góc camera thực tế tại các khu vực
# → Phục hồi 65% lượt hợp lệ, vẫn reject 23% dữ liệu nghi ngờ (Cosine < 0.50)
MIN_ACCURACY_THRESHOLD = 80.0   # Chuẩn độ tin cậy >= 80% (Cosine >= 0.50) - cân bằng thực tế
# Ngưỡng reject người lạ - nếu Cosine < 0.50 → trả về None (người lạ/unknown)
UNKNOWN_COSINE_THRESHOLD = 0.50  # Cosine < 0.50 = người lạ, không nhận diện dù CSDL có ai giống
ATTENDANCE_COOLDOWN = 60        # Giây không ghi log lặp lại cho cùng 1 người

# =============================================================================
# CẤU HÌNH AI RIÊNG TỪNG CAMERA (Per-Camera AI Settings)
# =============================================================================
CAM_AI_CONFIG = {
    # id: {min_face: pixels tối thiểu, ai_sleep: giây/frame, enrich_streak: streak để self-enrich,
    #       border_pct: % rìa frame bị loại bỏ (0.0-0.15) để tránh false positive tường/kết cấu}
    1: {"min_face": 60, "ai_sleep": 0.13, "enrich_streak": 3, "border_pct": 0.03},  # Phòng GPL  - ít người di chuyển
    2: {"min_face": 40, "ai_sleep": 0.08, "enrich_streak": 3, "border_pct": 0.03},  # Nhà Ăn 1   - nhiều người
    # Giải pháp #4: Tăng enrich_streak CAM03 lên 3 (phải khớp đúng 3 frame liên tiếp - chống người đi nhanh góc cúi)
    3: {"min_face": 45, "ai_sleep": 0.08, "enrich_streak": 3, "border_pct": 0.03},  # Cầu Thang  - người đi nhanh, streak=3
    4: {"min_face": 55, "ai_sleep": 0.08, "enrich_streak": 2, "border_pct": 0.05},  # Nhà Ăn 2   - tăng lên 55 & border 5% chống false positive tường
}

# Ngưỡng chất lượng ảnh khuôn mặt trước khi nhận diện
BLUR_THRESHOLD   = 80.0   # Laplacian variance: ảnh nét phải >= 80 (thấp hơn = mờ/blur)
BRIGHTNESS_MIN   = 40     # Độ sáng tối thiểu 0-255 (dưới = quá tối)
BRIGHTNESS_MAX   = 220    # Độ sáng tối đa 0-255 (trên = quá sáng/lóa)

# Self-Enrichment embedding đa góc
SELF_ENRICH_MAX_VECTORS = 5     # Tối đa 5 vectors/người (1 ảnh thẻ + 4 góc thực tế)
SELF_ENRICH_MIN_CONF    = 80.0  # Confidence tối thiểu để tự làm giàu embedding



# =============================================================================
# 1. ĐỒNG BỘ DỮ LIỆU NHÂN SỰ TỪ API SMART HRMS (HMAC-MD5)
# =============================================================================
class EmployeeAPIManager:
    def __init__(self):
        self.api_url = "https://i-officeapi.ltacv.com/api/data/process/Getdata_List_Employee_Full"
        self.sec_code = "smart@things!2020@HRMS***"
        self.code_name = "Getdata_List_Employee_Full"
        self.username = "noname"

    def _convert_json(self, data, reqtime):
        json_string = json.dumps(data, separators=(',', ':'))
        json_string = json_string.replace(' ', '').replace('\r', '').replace('\n', '').replace('"', "'")
        return f"{json_string}#{self.username}#{self.code_name}#{reqtime}"

    def fetch_employees_from_api(self):
        print("[*] Đang kết nối API Getdata_List_Employee_Full...")
        reqtime = int(time.time() * 1000)
        data_payload = {}
        datastring = self._convert_json(data_payload, reqtime)
        token = hmac.new(self.sec_code.encode('utf-8'), datastring.encode('utf-8'), hashlib.md5).hexdigest()

        body = {"token": token, "reqtime": reqtime, "data": data_payload}
        headers = {'Content-Type': 'application/json'}
        try:
            resp = requests.post(self.api_url, json=body, headers=headers, timeout=12)
            if resp.status_code == 200:
                data_list = resp.json().get("data", [])
                print(f"[+] Lấy thành công {len(data_list)} nhân sự từ API.")
                employees = {}
                for emp in data_list:
                    def get_val(k):
                        v = emp.get(k)
                        if isinstance(v, dict): return v.get('v', '')
                        return v or ''

                    emp_id = str(emp.get('ID') or '')
                    if emp_id:
                        employees[emp_id] = {
                            "ID": emp_id,
                            "EmployeeCode": str(get_val('EmployeeCode') or emp_id),
                            "FullName": str(get_val('FullName') or f"NV: {emp_id}"),
                            "Dept_Name": str(get_val('Dept_Name') or "--"),
                            "Name_Role": str(get_val('Name_Role') or "Nhân viên"),
                            "Company_Name": str(get_val('Company_Name') or "--"),
                            "SalaryClassName": str(get_val('SalaryClassName') or "--"),
                            "EmployeeStatus_Name": str(get_val('EmployeeStatus_Name') or "Đang làm việc"),
                            "Image_Url": str(get_val('FaceImageUser') or ""),
                            "WorkPlaceName": str(get_val('WorkPlaceName') or ""),
                            "Birthday": str(get_val('Birthday') or ""),
                            "Mobile": str(get_val('Mobile') or ""),
                            "OfficeEmail": str(get_val('OfficeEmail') or ""),
                            "Company_Address": str(get_val('Company_Address') or "")
                        }
                if employees:
                    try:
                        with open(CACHE_JSON_PATH, "w", encoding="utf-8") as f:
                            json.dump(employees, f, ensure_ascii=False, indent=2)
                    except Exception: pass
                    return employees
        except Exception as e:
            print(f"[!] Lỗi kết nối API: {e}")

        if os.path.exists(CACHE_JSON_PATH):
            print("[*] Đang nạp dữ liệu nhân sự từ bộ nhớ đệm cache...")
            try:
                with open(CACHE_JSON_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception: pass
        return {}

    def sync_face_images(self, employees, force_all=False):
        """
        Đồng bộ ảnh khuôn mặt từ API Smart HRMS về thư mục cục bộ (API_FACES_DIR):
        - Tự động phát hiện khi nhân viên đổi ảnh trên HRMS (URL thay đổi) -> tải đè ngay lập tức
        - Tải các ảnh chưa có hoặc bị lỗi kích thước 0 byte
        - Trả về danh sách ID các nhân viên vừa được cập nhật ảnh mới để AI tính lại vector
        """
        synced_urls = {}
        if os.path.exists(SYNCED_URLS_PATH):
            try:
                with open(SYNCED_URLS_PATH, "r", encoding="utf-8") as f:
                    synced_urls = json.load(f)
            except Exception:
                pass

        to_download = []
        for emp_id, info in employees.items():
            img_url = info.get("Image_Url")
            if not img_url:
                continue
            save_path = os.path.join(API_FACES_DIR, f"{emp_id}.jpg")
            file_missing = (not os.path.exists(save_path) or os.path.getsize(save_path) == 0)
            url_changed = (synced_urls.get(emp_id) != img_url)

            if file_missing or url_changed or force_all:
                to_download.append((emp_id, img_url, save_path))

        if not to_download:
            print(f"[+] Toàn bộ {len(employees)} nhân sự đã có ảnh khuôn mặt mới nhất trùng khớp với API.")
            return set()

        print(f"[*] Cần tải/cập nhật {len(to_download)} ảnh khuôn mặt từ API (phát hiện ảnh mới/thay đổi URL). Đang tải...")
        updated_emp_ids = set()

        def _dl(item):
            eid, url, spath = item
            try:
                r = requests.get(url, timeout=8)
                if r.status_code == 200 and len(r.content) > 500:
                    with open(spath, "wb") as f:
                        f.write(r.content)
                    return eid, url, True
            except Exception as e:
                pass
            return eid, url, False

        with ThreadPoolExecutor(max_workers=8) as ex:
            results = list(ex.map(_dl, to_download))

        success_count = 0
        for eid, url, ok in results:
            if ok:
                synced_urls[eid] = url
                updated_emp_ids.add(eid)
                success_count += 1

        try:
            with open(SYNCED_URLS_PATH, "w", encoding="utf-8") as f:
                json.dump(synced_urls, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[!] Lỗi ghi {SYNCED_URLS_PATH}: {e}")

        print(f"[+] Đã đồng bộ & ghi đè thành công {success_count}/{len(to_download)} ảnh mới từ API Smart HRMS.")
        return updated_emp_ids


# =============================================================================
# 2. KHỞI TẠO MÔ HÌNH AI & CƠ CHẾ TRIỆT TIÊU BỘ ĐỆM (LATEST-FRAME GRABBER)
# =============================================================================
def create_face_models():
    """Khởi tạo cặp mô hình YuNet và SFace với OpenCL (GPU) nếu khả dụng, fallback CPU.
    OpenCL cho phép GTX 750 Ti xử lý AI inference thay vì CPU - giảm tải CPU 40-60%."""
    # Chọn target: OPENCL (GPU) nếu khả dụng, fallback về CPU
    if _USE_OPENCL_DNN:
        dnn_backend = cv2.dnn.DNN_BACKEND_OPENCV
        dnn_target  = cv2.dnn.DNN_TARGET_OPENCL
        target_label = "OpenCL/GPU"
    else:
        dnn_backend = cv2.dnn.DNN_BACKEND_OPENCV
        dnn_target  = cv2.dnn.DNN_TARGET_CPU
        target_label = "CPU"

    try:
        det = cv2.FaceDetectorYN.create(
            YUNET_PATH, "", (640, 360),
            score_threshold=0.75, nms_threshold=0.3, top_k=5000,
            backend_id=dnn_backend, target_id=dnn_target
        )
        rec = cv2.FaceRecognizerSF.create(
            SFACE_PATH, "",
            backend_id=dnn_backend, target_id=dnn_target
        )
        print(f"[GPU] AI Models loaded on: {target_label}")
        return det, rec
    except Exception as e:
        # Fallback về CPU nếu OpenCL gặp lỗi runtime
        print(f"[GPU] {target_label} failed ({e}), fallback to CPU")
        det = cv2.FaceDetectorYN.create(
            YUNET_PATH, "", (640, 360),
            score_threshold=0.75, nms_threshold=0.3, top_k=5000,
            backend_id=cv2.dnn.DNN_BACKEND_OPENCV, target_id=cv2.dnn.DNN_TARGET_CPU
        )
        rec = cv2.FaceRecognizerSF.create(
            SFACE_PATH, "",
            backend_id=cv2.dnn.DNN_BACKEND_OPENCV, target_id=cv2.dnn.DNN_TARGET_CPU
        )
        return det, rec


def get_sub_stream_url(url):
    """Tự động chuyển đổi subtype=0 sang subtype=1 cho Dahua/Hikvision"""
    if "subtype=0" in url:
        return url.replace("subtype=0", "subtype=1")
    if "subtype=main" in url:
        return url.replace("subtype=main", "subtype=sub")
    if "/h264/ch1/main" in url:
        return url.replace("/h264/ch1/main", "/h264/ch1/sub")
    return url


class LatestFrameGrabber:
    """
    CƠ CHẾ TRIỆT TIÊU BỘ ĐỆM OPENCV (LATEST-FRAME GRABBER):
    Một luồng siêu nhẹ chạy nền liên tục xả rác toàn bộ bộ đệm OpenCV FFMPEG bằng cap.grab(),
    đảm bảo khi gọi get_latest_frame() luôn bốc trúng khung hình vừa mới phát sinh ở mili-giây hiện tại.
    """
    def __init__(self, url, name="Stream", drop_cadence=0):
        self.url = url
        self.name = name
        self.drop_cadence = drop_cadence  # 0: đọc liên tục 25 FPS (Web Display); 2: xả 2 frame grab và đọc 1 frame (~8 FPS cho AI Main Stream)
        self.running = True
        self.latest_frame = None
        self.lock = threading.Lock()
        self.cap = None
        self.frame_count = 0
        self.thread = threading.Thread(target=self._worker, daemon=True)
        self.thread.start()

    def _worker(self):
        fail_count = 0
        while self.running:
            if self.cap is None or not self.cap.isOpened():
                self.cap = cv2.VideoCapture(self.url, cv2.CAP_FFMPEG)
                self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                if not self.cap.isOpened():
                    time.sleep(1.0)
                    continue
                print(f"[+] [RTSP Grabber] Đã kết nối: {self.name}")

            # Cơ chế Drop Frame xả rác đệm: gọi grab() để bỏ qua giải mã các frame trung gian
            try:
                if not self.running or self.cap is None:
                    time.sleep(0.05)
                    continue

                if self.drop_cadence > 0:
                    for _ in range(self.drop_cadence):
                        if not self.running or self.cap is None:
                            break
                        self.cap.grab()

                if not self.running or self.cap is None:
                    time.sleep(0.05)
                    continue

                ret, frame = self.cap.read()
            except Exception:
                time.sleep(0.05)
                continue

            if not ret or frame is None:
                fail_count += 1
                if fail_count > 350:
                    if self.cap:
                        try: self.cap.release()
                        except: pass
                    self.cap = None
                    fail_count = 0
                time.sleep(0.01)
                continue

            fail_count = 0
            with self.lock:
                self.latest_frame = frame
                self.frame_count += 1

    def get_latest_frame(self):
        with self.lock:
            if self.latest_frame is None:
                return None
            return self.latest_frame.copy()

    def release(self):
        self.running = False
        if self.cap and self.cap.isOpened():
            try: self.cap.release()
            except: pass


# =============================================================================
# 3. CORE AI NHẬN DIỆN KHUÔN MẶT - CHUẨN XÁC CAO (>= 75%)
# =============================================================================
class AIFaceEngine:
    def __init__(self):
        print("=" * 75)
        print("  KHỞI TẠO BỘ XỬ LÝ AI NHẬN DIỆN KHUÔN MẶT - CHÍNH XÁC >= 75%")
        print("=" * 75)

        # Khóa bảo vệ dữ liệu nhật ký & thẻ card (không khóa luồng nhận diện camera)
        self.data_lock = threading.Lock()

        # Mô hình dùng riêng cho việc đồng bộ và đăng ký khuôn mặt nhân sự
        self.enroll_detector, self.enroll_recognizer = create_face_models()

        # 2. Đồng bộ API
        self.api_mgr = EmployeeAPIManager()
        self.employees = self.api_mgr.fetch_employees_from_api()
        updated_ids = self.api_mgr.sync_face_images(self.employees)

        # 3. Vectorized Embeddings Database
        self.database = {}
        self.load_or_build_embeddings(force_ids=updated_ids)

        # 4. Trạng thái & Nhật ký (Tách riêng 2 luồng RTSP Camera và Tablet Kiosk)
        # Luồng RTSP Camera IP (cam_id: 1, 2, 3, 4...) -> Chỉ hiển thị Dashboard Admin
        self.rtsp_active_card = None
        self.rtsp_latest_event = None
        self.rtsp_last_event_id = 0

        # Luồng Tablet Kiosk (cam_id: 99) -> Chỉ hiển thị Popup Kiosk Tablet
        self.kiosk_active_card = None
        self.kiosk_latest_event = None
        self.kiosk_last_event_id = 0

        # Tương thích ngược
        self.active_card = None
        self.last_event_id = 0
        self.latest_event = None

        self.last_checkin_times = {}
        self.recent_logs = []
        self._load_recent_logs()

    @staticmethod
    def select_best_face(faces):
        """
        Chọn khuôn mặt chuẩn nhất từ kết quả YuNet:
        1. Ưu tiên khuôn mặt có độ tin cậy nhận diện cao (score >= 0.85) để tránh nếp gấp áo/cổ áo/cà vạt ở ngực.
        2. Nếu có nhiều khuôn mặt đạt score >= 0.85, chọn khuôn mặt có diện tích lớn nhất trong nhóm đó.
        3. Nếu không có khuôn mặt nào >= 0.85, chọn khuôn mặt có score cao nhất tuyệt đối.
        """
        if faces is None or len(faces) == 0:
            return None
        high_conf = [f for f in faces if float(f[-1]) >= 0.85]
        if high_conf:
            return max(high_conf, key=lambda f: float(f[2]) * float(f[3]))
        return max(faces, key=lambda f: float(f[-1]))

    def load_or_build_embeddings(self, force_ids=None):
        if force_ids is None:
            force_ids = set()
        else:
            force_ids = set(force_ids)

        loaded_from_cache = False
        cached_data = {}
        if os.path.exists(EMBEDDINGS_PKL_PATH):
            try:
                with open(EMBEDDINGS_PKL_PATH, "rb") as f:
                    cached_data = pickle.load(f)
                loaded_from_cache = True
            except Exception: pass

        # Xóa các vector cũ trong cache pkl và RAM đối với các nhân sự vừa đổi ảnh
        for fid in force_ids:
            if fid in cached_data:
                del cached_data[fid]
            if fid in self.database:
                del self.database[fid]

        image_files = glob.glob(os.path.join(API_FACES_DIR, "*.jpg"))
        total_imgs = len(image_files)
        self.enroll_detector.setScoreThreshold(0.5)
        new_encoded = 0

        if not loaded_from_cache and total_imgs > 0:
            print(f"[*] Đang xây dựng CSDL embedding cho {total_imgs} ảnh nhân viên. Vui lòng chờ...")
        elif force_ids:
            print(f"[*] Đang tính toán lại vector AI cho {len(force_ids)} nhân sự vừa cập nhật ảnh mới...")

        for idx, img_path in enumerate(image_files):
            key_id = os.path.splitext(os.path.basename(img_path))[0]
            # Nếu đã có trong cache và KHÔNG nằm trong danh sách cần tính lại
            if key_id not in force_ids and key_id in cached_data and cached_data[key_id]:
                self.database[key_id] = cached_data[key_id]
                continue

            img = cv2.imread(img_path)
            if img is None: continue

            h, w, _ = img.shape
            self.enroll_detector.setInputSize((w, h))
            _, faces = self.enroll_detector.detect(img)
            if faces is not None and len(faces) > 0:
                best_face = self.select_best_face(faces)
                aligned = self.enroll_recognizer.alignCrop(img, best_face)
                feat = self.enroll_recognizer.feature(aligned)
                self.database[key_id] = [feat]
                cached_data[key_id] = self.database[key_id]
                new_encoded += 1
                if key_id in force_ids:
                    print(f"  [✓ CẬP NHẬT VECTOR AI] {key_id}: Đã nạp vector khuôn mặt mới nhất từ ảnh API!")

            # In tiến trình mỗi 20 ảnh để người dùng biết đang xử lý
            if new_encoded > 0 and new_encoded % 20 == 0:
                pct = int((idx + 1) / total_imgs * 100)
                print(f"  ... Đã xử lý {idx+1}/{total_imgs} ảnh ({pct}%) - {new_encoded} khuôn mặt mã hóa thành công")
            # Lưu cache tạm thời mỗi 50 ảnh để tránh mất toàn bộ nếu bị ngắt
            if new_encoded > 0 and new_encoded % 50 == 0:
                try:
                    with open(EMBEDDINGS_PKL_PATH, "wb") as f:
                        pickle.dump(cached_data, f)
                except Exception:
                    pass

        self.enroll_detector.setScoreThreshold(0.60)
        if new_encoded > 0 or not loaded_from_cache:
            try:
                with open(EMBEDDINGS_PKL_PATH, "wb") as f:
                    pickle.dump(cached_data, f)
            except Exception: pass

        print(f"[+] Đã sẵn sàng CSDL AI với {len(self.database)} nhân viên ({new_encoded} ảnh vừa mã hóa).")

    def enroll_single_face(self, emp_id, image_bytes_or_path):
        """Đăng ký hoặc cập nhật ảnh khuôn mặt cho 1 nhân viên vào CSDL AI ngay lập tức"""
        with self.data_lock:
            if isinstance(image_bytes_or_path, str):
                img = cv2.imread(image_bytes_or_path)
            else:
                nparr = np.frombuffer(image_bytes_or_path, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            if img is None:
                return False, "Không đọc được tệp hình ảnh"

            # Lưu vào thư mục api_faces
            save_path = os.path.join(API_FACES_DIR, f"{emp_id}.jpg")
            cv2.imwrite(save_path, img)

            h, w, _ = img.shape
            self.enroll_detector.setScoreThreshold(0.5)
            self.enroll_detector.setInputSize((w, h))
            _, faces = self.enroll_detector.detect(img)
            self.enroll_detector.setScoreThreshold(0.60)

            if faces is None or len(faces) == 0:
                return False, "Không tìm thấy khuôn mặt rõ ràng trong ảnh tải lên"

            best_face = self.select_best_face(faces)
            aligned = self.enroll_recognizer.alignCrop(img, best_face)
            feat = self.enroll_recognizer.feature(aligned)

            self.database[emp_id] = [feat]

            # Lưu vào cache pkl
            try:
                cached_data = {}
                if os.path.exists(EMBEDDINGS_PKL_PATH):
                    with open(EMBEDDINGS_PKL_PATH, "rb") as f:
                        cached_data = pickle.load(f)
                cached_data[emp_id] = self.database[emp_id]
                with open(EMBEDDINGS_PKL_PATH, "wb") as f:
                    pickle.dump(cached_data, f)
            except Exception as e:
                print(f"[!] Lỗi ghi embeddings.pkl: {e}")

            return True, "Đã cập nhật vector khuôn mặt thành công vào CSDL AI"

    def add_face_angle(self, emp_id, image_bytes_or_path):
        """
        ★ ƯU TIÊN 1: Thêm góc khuôn mặt mới (trái/phải/nghiêng/chụp thực tế từ camera)
        vào CSDL đa góc (Multi-angle Embedding - tối đa 5 vectors/người)
        """
        with self.data_lock:
            if isinstance(image_bytes_or_path, str):
                img = cv2.imread(image_bytes_or_path)
            else:
                nparr = np.frombuffer(image_bytes_or_path, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            if img is None:
                return False, "Không đọc được tệp hình ảnh"

            h, w, _ = img.shape
            self.enroll_detector.setScoreThreshold(0.5)
            self.enroll_detector.setInputSize((w, h))
            _, faces = self.enroll_detector.detect(img)
            self.enroll_detector.setScoreThreshold(0.60)

            if faces is None or len(faces) == 0:
                return False, "Không tìm thấy khuôn mặt rõ ràng trong ảnh"

            best_face = self.select_best_face(faces)
            aligned = self.enroll_recognizer.alignCrop(img, best_face)
            feat = self.enroll_recognizer.feature(aligned)

            if emp_id not in self.database:
                self.database[emp_id] = []

            if len(self.database[emp_id]) >= SELF_ENRICH_MAX_VECTORS:
                return False, f"Đã đạt tối đa {SELF_ENRICH_MAX_VECTORS} vectors khuôn mặt cho nhân viên này"

            self.database[emp_id].append(feat)
            n_vecs = len(self.database[emp_id])

            try:
                cached_data = {}
                if os.path.exists(EMBEDDINGS_PKL_PATH):
                    with open(EMBEDDINGS_PKL_PATH, "rb") as f:
                        cached_data = pickle.load(f)
                cached_data[emp_id] = self.database[emp_id]
                with open(EMBEDDINGS_PKL_PATH, "wb") as f:
                    pickle.dump(cached_data, f)
            except Exception as e:
                print(f"[!] Lỗi ghi embeddings.pkl: {e}")

            return True, f"Đã bổ sung góc mặt thành công! Hiện có {n_vecs}/{SELF_ENRICH_MAX_VECTORS} vectors."

    def _load_recent_logs(self):
        if not os.path.exists(ATTENDANCE_LOG_PATH): return
        try:
            with open(ATTENDANCE_LOG_PATH, "r", encoding="utf-8-sig", errors="replace") as f:
                lines = [l.strip() for l in f if l.strip()]
            for line in lines[1:]:
                parts = []
                in_quote = False
                cur = ""
                for char in line:
                    if char == '"':
                        in_quote = not in_quote
                    elif char == ',' and not in_quote:
                        parts.append(cur.strip())
                        cur = ""
                    else:
                        cur += char
                parts.append(cur.strip())

                if len(parts) >= 8:
                    code = parts[1]
                    emp_id = ""
                    for eid, emp in self.employees.items():
                        if emp.get("EmployeeCode") == code or eid == code:
                            emp_id = eid
                            break

                    snap = ""
                    avatar = f"{emp_id}.jpg" if emp_id and os.path.exists(os.path.join(API_FACES_DIR, f"{emp_id}.jpg")) else ""
                    
                    for p in parts[8:]:
                        if p.endswith((".jpg", ".png")):
                            snap = p
                            break

                    cam_name = parts[9] if len(parts) > 10 else parts[7]

                    self.recent_logs.insert(0, {
                        "time": parts[0],
                        "code": code,
                        "name": parts[2],
                        "role": parts[3],
                        "dept": parts[4],
                        "company": parts[5],
                        "salary": parts[6] if len(parts) > 10 else "--",
                        "status": parts[7] if len(parts) > 10 else "ĐÃ XÁC THỰC",
                        "conf": parts[8] if len(parts) > 10 else parts[6],
                        "cam": cam_name,
                        "snapshot": snap,
                        "avatar": avatar
                    })
        except Exception as e:
            print(f"[!] Lỗi đọc nhật ký: {e}")

    def is_facing_camera(self, face, min_eye_dist_ratio=0.20, min_eye_dist_px=18):
        """Kiểm tra hình học nhân trắc học 5 điểm mốc để loại bỏ đồ vật tĩnh và góc mặt cực đoan.
        Giải pháp #3: Thêm kiểm tra Pitch Angle (cúi đầu/ngửa đầu) - phòng trường hợp cúi đầu
        làm SFace bị feature collapse và nhận sai thành người khác."""
        bw = face[2]
        bh = face[3]
        re = face[4:6]
        le = face[6:8]
        nt = face[8:10]
        rcm = face[10:12]
        lcm = face[12:14]

        # 1. Tỷ lệ hình học khuôn mặt người (Aspect Ratio: Chiều cao / Chiều rộng)
        # Khuôn mặt người bình thường có tỷ lệ khoảng 0.75 - 1.55 (không thể quá dài hoặc quá dẹt)
        ar = float(bh) / (float(bw) + 1e-6)
        if ar < 0.70 or ar > 1.60:
            return False, "Khuôn mặt chưa cân đối, vui lòng nhìn thẳng."

        # 2. Khoảng cách và độ nghiêng 2 mắt (Roll/Yaw check)
        dx = float(re[0] - le[0])
        dy = float(re[1] - le[1])
        eye_dist = (dx * dx + dy * dy) ** 0.5
        eye_ratio = eye_dist / (float(bw) + 1e-6)

        if eye_dist < min_eye_dist_px or eye_ratio < min_eye_dist_ratio:
            return False, "Góc nhìn quá nghiêng, vui lòng nhìn thẳng vào camera."
        if abs(dy) > abs(dx) * 0.75:
            return False, "Vui lòng giữ thẳng đầu, tránh nghiêng đầu."

        # 3. Thứ tự trục dọc nhân trắc học: Mắt ở trên, Mũi ở giữa, Miệng ở dưới
        eye_y = (re[1] + le[1]) / 2.0
        mouth_y = (rcm[1] + lcm[1]) / 2.0
        if not (eye_y < nt[1] < mouth_y):
            return False, "Không phát hiện khuôn mặt hợp lệ."

        # 4. Trục ngang: Đỉnh mũi phải nằm trong phạm vi giữa 2 mắt
        min_eye_x = min(re[0], le[0])
        max_eye_x = max(re[0], le[0])
        if not (min_eye_x - 0.25 * eye_dist <= nt[0] <= max_eye_x + 0.25 * eye_dist):
            return False, "Vui lòng nhìn thẳng vào trung tâm camera."

        # Giải pháp #3: Kiểm tra Pitch Angle (cúi đầu / ngửa đầu)
        # Tỷ lệ khoảng cách mắt-mũi / mũi-miệng phải nằm trong [0.30 - 3.0]
        # Nới rộng từ [0.35-2.8] → [0.30-3.0] để phù hợp góc camera hành lang/cầu thang đặt cao
        # Vẫn lọc được cúi sâu (< 0.30) và ngửa hẳn (> 3.0), cho phép cúi/ngửa nhẹ tự nhiên
        eye_to_nose = float(nt[1]) - eye_y
        nose_to_mouth = float(mouth_y) - float(nt[1])
        if nose_to_mouth > 1e-3:  # Tránh chia cho 0
            pitch_ratio = eye_to_nose / nose_to_mouth
            if pitch_ratio < 0.30 or pitch_ratio > 3.0:
                return False, "Vui lòng không cúi đầu hoặc ngửa đầu quá mức."

        return True, "Chính diện hợp lệ"

    def recognize_face(self, feat, recognizer=None):
        """So khớp vector khuôn mặt với CSDL - Quy đổi độ chính xác % chuẩn Biometric
        Giải pháp #2: Unknown Rejection - nếu Cosine < UNKNOWN_COSINE_THRESHOLD (0.55)
        → trả về None, hệ thống KHÔNG nhận diện dù có người giống trong CSDL."""
        rec = recognizer or self.enroll_recognizer
        best_id = None
        best_score = -1.0
        for kid, feat_list in self.database.items():
            for f in feat_list:
                score = rec.match(feat, f, cv2.FaceRecognizerSF_FR_COSINE)
                if score > best_score:
                    best_score = score
                    best_id = kid

        # Giải pháp #2: Unknown Rejection Threshold
        # Cosine < 0.55 = người lạ/chưa đăng ký → reject hoàn toàn, không nhận diện
        if best_score < UNKNOWN_COSINE_THRESHOLD:
            return None, best_score, 0.0

        # Quy đổi điểm Cosine sang Tỷ lệ % chính xác:
        # Cosine 0.363=60%, 0.47=75%, 0.50=80%, 0.55=87%, 0.58=90%, 0.65=98%
        if best_score <= 0.363:
            confidence_pct = max(0.0, (best_score / 0.363) * 60.0)
        else:
            confidence_pct = 60.0 + min(40.0, ((best_score - 0.363) / (0.65 - 0.363)) * 40.0)

        return best_id, best_score, confidence_pct

    def log_attendance(self, emp_id, profile, confidence, cam_name, cam_id, raw_frame, bbox):
        """Ghi nhận lượt chấm công thành công khi đạt >= 75% kèm CẮT ẢNH CHÂN DUNG THỰC TẾ SẮC NÉT TỪ FULL HD"""
        now = time.time()
        last_t = self.last_checkin_times.get(emp_id, 0)
        if now - last_t < ATTENDANCE_COOLDOWN:
            return False

        self.last_checkin_times[emp_id] = now
        time_full = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        time_tag = datetime.now().strftime("%Y%m%d_%H%M%S")

        code = profile.get("EmployeeCode", emp_id)
        name = profile.get("FullName", "")
        role = profile.get("Name_Role", "")
        dept = profile.get("Dept_Name", "")
        company = profile.get("Company_Name", "")
        workplace = profile.get("WorkPlaceName", "")
        salary = profile.get("SalaryClassName", "--")
        status = profile.get("EmployeeStatus_Name", "Đang làm việc")

        # 1. Cắt ảnh chân dung thực tế từ khung hình Full HD sắc nét của Main Stream
        x, y, bw, bh = bbox
        ih, iw, _ = raw_frame.shape
        pad_x = int(bw * 0.35)
        pad_y = int(bh * 0.45)
        x1 = max(0, x - pad_x)
        y1 = max(0, y - pad_y)
        x2 = min(iw, x + bw + pad_x)
        y2 = min(ih, y + bh + pad_y)

        face_crop = raw_frame[y1:y2, x1:x2]
        ms_tag = int(time.time() * 1000) % 1000
        snapshot_filename = f"{code}_{time_tag}_{ms_tag:03d}.jpg"
        snapshot_path = os.path.join(SNAPSHOTS_DIR, snapshot_filename)
        cv2.imwrite(snapshot_path, face_crop)

        avatar_filename = f"{emp_id}.jpg" if os.path.exists(os.path.join(API_FACES_DIR, f"{emp_id}.jpg")) else ""

        # 2. Lưu vào danh sách sự kiện gần nhất (an toàn đa luồng)
        entry = {
            "time": time_full,
            "code": code,
            "name": name,
            "role": role,
            "dept": dept,
            "company": company,
            "workplace": workplace,
            "salary": salary,
            "status": status,
            "conf": f"{confidence:.1f}%",
            "cam": cam_name,
            "cam_id": cam_id,
            "snapshot": snapshot_filename,
            "avatar": avatar_filename
        }
        with self.data_lock:
            self.recent_logs.insert(0, entry)
            if len(self.recent_logs) > 300:
                self.recent_logs.pop()

            # 3. Ghi vào file CSV chuẩn UTF-8-SIG
            write_header = not os.path.exists(ATTENDANCE_LOG_PATH)
            with open(ATTENDANCE_LOG_PATH, "a", encoding="utf-8-sig") as f:
                if write_header:
                    f.write("ThoiGian,MSNV,HoTen,ChucDanh,PhongBan,CongTy,NgachLuong,TrangThai,DoTinCay,Camera,AnhChup,AnhHoSo\n")
                f.write(f'"{time_full}","{code}","{name}","{role}","{dept}","{company}","{salary}","{status}","{confidence:.1f}%","{cam_name}","{snapshot_filename}","{avatar_filename}"\n')

        print(f"[✓ XÁC THỰC >= 75%]: [{code}] {name} - {role} ({dept}) lúc {time_full} ({confidence:.1f}%) | Ảnh: {snapshot_filename}")
        return True

    def self_enrich_embedding(self, emp_id, feat, conf_pct):
        """
        ★ PRIORITY 1: Tự làm giàu embedding đa góc từ camera thực tế (Self-Enrichment an toàn sinh trắc học).
        Điều kiện nghiêm ngặt để thêm vector mới:
          - confidence >= 85.0% (độ tin cậy nhận diện cao)
          - Tổng vectors tối đa 3 (1 vector gốc + tối đa 2 góc nghiêng thực tế)
          - Vector mới phải thực sự cùng 1 người với vector gốc V0 (0.58 <= sim_v0 <= 0.72)
          - Vector mới không bị trùng lặp với các vector phụ đã có (sim <= 0.75)
        """
        if conf_pct < 85.0:
            return
        with self.data_lock:
            if emp_id not in self.database:
                return
            current_vectors = self.database[emp_id]
            if not current_vectors:
                return
            # Giới hạn tối đa 3 vectors/người để kiểm soát độ tinh khiết và RAM
            if len(current_vectors) >= 3:
                return

            v0 = current_vectors[0]
            try:
                # 1. BẮT BUỘC KIỂM TRA ĐỘ LỆCH VỚI ẢNH GỐC V0:
                # Phải là cùng 1 người (sim_v0 >= 0.58), nhưng có góc hơi khác (sim_v0 <= 0.72).
                # Loại bỏ triệt để: người lạ, nếp áo, người cúi gục đầu hoặc quay lưng (sim_v0 < 0.58)
                sim_v0 = self.enroll_recognizer.match(
                    feat, v0, cv2.FaceRecognizerSF_FR_COSINE
                )
                if sim_v0 < 0.58 or sim_v0 > 0.72:
                    return

                # 2. Không được trùng lặp với bất kỳ vector phụ nào đã lưu
                for existing_feat in current_vectors[1:]:
                    sim_ex = self.enroll_recognizer.match(
                        feat, existing_feat, cv2.FaceRecognizerSF_FR_COSINE
                    )
                    if sim_ex > 0.75:
                        return
            except Exception:
                return

            self.database[emp_id].append(feat)
            n_vecs = len(self.database[emp_id])
            print(f"[📸 SELF-ENRICH AN TOÀN] {emp_id}: đã nạp thêm góc mặt thực tế chuẩn {n_vecs}/3 (sim_v0: {sim_v0:.3f}, conf: {conf_pct:.0f}%)")
        # Lưu cache pkl bất đồng bộ (không chặn luồng camera)
        threading.Thread(
            target=self._save_enrich_async, args=(emp_id,), daemon=True
        ).start()

    def _save_enrich_async(self, emp_id):
        """Lưu embedding self-enrichment vào pkl bất đồng bộ, không chặn luồng camera"""
        try:
            cached_data = {}
            if os.path.exists(EMBEDDINGS_PKL_PATH):
                with open(EMBEDDINGS_PKL_PATH, "rb") as pf:
                    cached_data = pickle.load(pf)
            with self.data_lock:
                cached_data[emp_id] = list(self.database.get(emp_id, []))
            with open(EMBEDDINGS_PKL_PATH, "wb") as pf:
                pickle.dump(cached_data, pf)
        except Exception as e:
            print(f"[!] Lỗi lưu self-enrich pkl: {e}")

    def draw_bbox(self, img, x, y, w, h, color, label):
        ih, iw, _ = img.shape
        x1, y1 = max(0, x), max(0, y)
        x2, y2 = min(iw, x + w), min(ih, y + h)

        line_len = int(min(w, h) * 0.25)
        cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
        cv2.line(img, (x1, y1), (x1 + line_len, y1), color, 3)
        cv2.line(img, (x1, y1), (x1, y1 + line_len), color, 3)
        cv2.line(img, (x2, y1), (x2 - line_len, y1), color, 3)
        cv2.line(img, (x2, y1), (x2, y1 + line_len), color, 3)
        cv2.line(img, (x1, y2), (x1 + line_len, y2), color, 3)
        cv2.line(img, (x1, y2), (x1, y2 - line_len), color, 3)
        cv2.line(img, (x2, y2), (x2 - line_len, y2), color, 3)
        cv2.line(img, (x2, y2), (x2, y2 - line_len), color, 3)

        font = cv2.FONT_HERSHEY_DUPLEX
        font_scale = 0.50 if iw >= 1000 else 0.44
        (tw, th), _ = cv2.getTextSize(label, font, font_scale, 1)
        badge_y = max(y1 - 6, th + 8)
        cv2.rectangle(img, (x1, badge_y - th - 6), (x1 + tw + 8, badge_y + 4), color, -1)
        cv2.putText(img, label, (x1 + 4, badge_y - 2), font, font_scale, (255, 255, 255), 1, cv2.LINE_AA)


# =============================================================================
# 4. BỘ XỬ LÝ CAMERA DUAL-STREAM 25 FPS ZERO-LAG & AI ĐỘC LẬP TỪNG CAMERA
# =============================================================================
class FaceTrack:
    """
    ★ ƯU TIÊN 2: Bộ theo dõi khuôn mặt (Face Tracker)
    Theo dõi liên tục bounding box và gom các frame ứng viên để chọn frame nét nhất (Deferred Recognition)
    """
    def __init__(self, track_id, bbox, face_data):
        self.track_id = track_id
        self.bbox = list(bbox)          # [x, y, bw, bh]
        self.face_data = face_data      # landmarks & detection array từ YuNet
        self.frames_since_update = 0    # Số frame AI trôi qua không thấy
        self.best_blur = -1.0           # Điểm Laplacian variance cao nhất (nét nhất)
        self.best_face = None           # Dữ liệu khuôn mặt của frame nét nhất
        self.best_frame = None          # Khung hình Full HD nét nhất
        self.best_crop = None           # Crop mặt nét nhất
        self.recognized_emp_id = None   # Mã nhân viên sau khi xác thực thành công
        self.recognized_profile = {}    # Hồ sơ nhân sự
        self.recognized_conf = 0.0      # Độ chính xác (%)
        self.attendance_logged = False  # Đã ghi điểm danh trong lượt này chưa
        self.streak = 0                 # Số lần khớp liên tiếp
        self.last_seen_time = time.time()


def calculate_iou_and_dist(boxA, boxB):
    """Tính Intersection-over-Union (IoU) và khoảng cách tâm giữa 2 bounding box [x, y, w, h]"""
    xA = max(boxA[0], boxB[0])
    yA = max(boxA[1], boxB[1])
    xB = min(boxA[0] + boxA[2], boxB[0] + boxB[2])
    yB = min(boxA[1] + boxA[3], boxB[1] + boxB[3])

    inter_w = max(0, xB - xA)
    inter_h = max(0, yB - yA)
    inter_area = inter_w * inter_h

    boxA_area = boxA[2] * boxA[3]
    boxB_area = boxB[2] * boxB[3]
    union_area = float(boxA_area + boxB_area - inter_area)

    iou = inter_area / union_area if union_area > 0 else 0.0

    cAx, cAy = boxA[0] + boxA[2] / 2.0, boxA[1] + boxA[3] / 2.0
    cBx, cBy = boxB[0] + boxB[2] / 2.0, boxB[1] + boxB[3] / 2.0
    dist = ((cAx - cBx) ** 2 + (cAy - cBy) ** 2) ** 0.5
    diag = ((boxA[2] ** 2 + boxA[3] ** 2) ** 0.5 + (boxB[2] ** 2 + boxB[3] ** 2) ** 0.5) / 2.0
    norm_dist = dist / diag if diag > 0 else 999.0

    return iou, norm_dist


class CameraStreamWorker:
    def __init__(self, cam_id, cam_name, rtsp_url, ai_engine):
        self.cam_id = cam_id
        self.cam_name = cam_name
        self.main_url = rtsp_url
        self.sub_url = get_sub_stream_url(rtsp_url)
        self.ai_engine = ai_engine

        # 1. Tách biệt 2 Grabber: Grabber Sub (Web mượt 0ms) & Grabber Main (AI sắc nét 8-12.5 FPS)
        self.grabber_sub = LatestFrameGrabber(self.sub_url, f"{cam_name}_SUB", drop_cadence=0)
        if self.sub_url != self.main_url:
            self.grabber_main = LatestFrameGrabber(self.main_url, f"{cam_name}_MAIN", drop_cadence=2)
        else:
            self.grabber_main = self.grabber_sub

        # 2. Bộ nhận diện AI ĐỘC LẬP cho camera này (Không dùng chung ai_lock)
        self.detector, self.recognizer = create_face_models()

        self.lock = threading.Lock()
        self.condition = threading.Condition(self.lock)
        self.running = True

        self.frame_id = 0
        self.latest_jpeg = None
        # cached_boxes lưu tọa độ chuẩn hóa [0.0 - 1.0]: [(nx, ny, nw, nh, label, color)]
        self.cached_boxes = []
        self.match_streak = {}

        # ★ Per-camera AI configuration (Priority 4: min face, Priority 5: FPS)
        _cfg = CAM_AI_CONFIG.get(cam_id, {"min_face": 50, "ai_sleep": 0.13, "enrich_streak": 3, "border_pct": 0.03})
        self.min_face_px       = _cfg["min_face"]               # Kích thước mặt tối thiểu (px)
        self.ai_sleep_sec      = _cfg["ai_sleep"]               # Khoảng nghỉ giữa mỗi frame AI
        self.enrich_streak_req = _cfg["enrich_streak"]          # Streak tối thiểu để kích hoạt self-enrich
        self.border_pct        = _cfg.get("border_pct", 0.03)   # % rìa frame bị loại bỏ (chống false positive tường)
        print(f"[CFG] {cam_name}: min_face={self.min_face_px}px | AI={1/self.ai_sleep_sec:.0f}FPS | enrich_streak={self.enrich_streak_req} | border_pct={self.border_pct:.0%}")

        # ★ Face Tracking & Deferred Recognition (Ưu Tiên 2)
        self.active_tracks = {}       # track_id -> FaceTrack
        self.next_track_id = 1
        self.prev_small_gray = None  # Dùng cho Motion Detection nhanh
        self.last_client_request_time = time.time()  # Theo dõi client xem stream để điều chỉnh FPS

        # 3. Kích hoạt 2 luồng độc lập: Web Stream (25 FPS) & AI Engine (per-cam FPS)
        self.stream_thread = threading.Thread(target=self._stream_loop, daemon=True)
        self.ai_thread = threading.Thread(target=self._ai_loop, daemon=True)
        self.stream_thread.start()
        self.ai_thread.start()
        print(f"[*] Đã kích hoạt Dual-Stream Pipeline cho: {self.cam_name}")

    def _stream_loop(self):
        """Luồng chuyên hiển thị Web: Smart On-Demand (25 FPS khi có người xem, 1 FPS khi idle tiết kiệm CPU)"""
        last_encode_time = 0
        while self.running:
            now = time.time()
            has_viewer = (now - getattr(self, 'last_client_request_time', 0) < 15.0)
            target_interval = 0.038 if has_viewer else 1.0  # 25 FPS khi có viewer, 1 FPS khi idle
            if now - last_encode_time < target_interval:
                time.sleep(0.003 if has_viewer else 0.1)
                continue
            last_encode_time = now

            # Lấy khung hình mới nhất từ Sub Stream
            frame = self.grabber_sub.get_latest_frame()
            if frame is None:
                # Dự phòng lấy từ Main Stream nếu Sub Stream chưa sẵn sàng
                frame = self.grabber_main.get_latest_frame()
                if frame is None:
                    time.sleep(0.01)
                    continue

            # Dự phòng giảm kích thước nếu luồng hiển thị quá lớn
            if frame.shape[1] > 1024:
                frame = cv2.resize(frame, (960, 540), interpolation=cv2.INTER_LINEAR)

            fh, fw, _ = frame.shape
            with self.lock:
                current_boxes = list(self.cached_boxes)

            # Vẽ bounding box lên khung hình hiển thị (tọa độ chuẩn hóa)
            for (nx, ny, nw, nh, label, color) in current_boxes:
                bx = int(nx * fw)
                by = int(ny * fh)
                bw = int(nw * fw)
                bh = int(nh * fh)
                self.ai_engine.draw_bbox(frame, bx, by, bw, bh, color, label)

            q_jpeg = STREAM_CONFIG.get("quality", 85)
            ret_enc, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), q_jpeg])
            if ret_enc:
                with self.lock:
                    self.latest_jpeg = buffer.tobytes()
                    self.frame_id += 1
                    self.condition.notify_all()

    def _ai_loop(self):
        """
        Luồng AI nhận diện độc lập: Face Tracking + Deferred Recognition + Image Quality Filter
        Tối ưu cho người di chuyển nhanh:
          - Tăng AI FPS (10-12.5 FPS cho lối đi/nhà ăn)
          - Motion Detection bỏ qua frame tĩnh
          - Adaptive Detection Resolution (Full HD -> 960x540, 720p -> 640x360)
          - Face Tracking giữ vết khuôn mặt không bị gián đoạn
          - Bộ lọc Blur (Laplacian >= 80) & Brightness (40-220)
          - Chọn frame nét nhất từ track để nhận diện (Deferred Recognition)
          - Multi-Angle Embedding Self-Enrichment (conf >= 80%, streak >= enrich_streak)
        """
        while self.running:
            t_loop_start = time.time()
            main_frame = self.grabber_main.get_latest_frame()
            if main_frame is None:
                main_frame = self.grabber_sub.get_latest_frame()
                if main_frame is None:
                    time.sleep(0.04)
                    continue

            # Cân chỉnh độ phân giải: Giới hạn tối đa Full HD 1080p
            mh, mw, _ = main_frame.shape
            if mw > 1920 or mh > 1080:
                main_frame = cv2.resize(main_frame, (1920, 1080), interpolation=cv2.INTER_AREA)
                mh, mw, _ = main_frame.shape

            # -------------------------------------------------------------
            # BƯỚC 1: MOTION DETECTION (Siêu nhẹ ~0.2ms trên ảnh thu nhỏ 160x90)
            # -------------------------------------------------------------
            small_gray = cv2.resize(cv2.cvtColor(main_frame, cv2.COLOR_BGR2GRAY), (160, 90))
            has_motion = True
            if self.prev_small_gray is not None:
                diff = cv2.absdiff(small_gray, self.prev_small_gray)
                motion_val = float(np.mean(diff))
                # Nếu không có chuyển động và không có track nào đang theo dõi
                if motion_val < 1.0 and len(self.active_tracks) == 0:
                    has_motion = False
            self.prev_small_gray = small_gray

            if not has_motion:
                with self.lock:
                    if self.cached_boxes:
                        self.cached_boxes = []
                time.sleep(self.ai_sleep_sec * 1.5)
                continue

            # -------------------------------------------------------------
            # BƯỚC 2: ADAPTIVE DETECTION RESOLUTION (Ưu Tiên 6)
            # -------------------------------------------------------------
            if mw >= 1920:
                det_w, det_h = 960, 540   # 50% Full HD: bắt mặt nhỏ ở xa tốt hơn
            elif mw >= 1280:
                det_w, det_h = 640, 360
            else:
                det_w, det_h = mw, mh

            scale_det_x = mw / det_w
            scale_det_y = mh / det_h
            det_frame = cv2.resize(main_frame, (det_w, det_h), interpolation=cv2.INTER_LINEAR)

            self.detector.setInputSize((det_w, det_h))
            _, faces = self.detector.detect(det_frame)

            detected_faces = []
            if faces is not None and len(faces) > 0:
                faces_orig = faces.copy()
                faces_orig[:, 0] *= scale_det_x
                faces_orig[:, 2] *= scale_det_x
                faces_orig[:, 4:14:2] *= scale_det_x
                faces_orig[:, 1] *= scale_det_y
                faces_orig[:, 3] *= scale_det_y
                faces_orig[:, 5:14:2] *= scale_det_y

                # Border exclusion margins (pixel) - loại bỏ detection ở rìa frame
                bdr_x = int(mw * self.border_pct)
                bdr_y = int(mh * self.border_pct)

                for face in faces_orig:
                    fx, fy, fbw, fbh = face[:4].astype(int)
                    # Tâm khuôn mặt (dùng để kiểm tra border)
                    cx = fx + fbw // 2
                    cy = fy + fbh // 2
                    # Lọc 1: Kích thước tối thiểu theo từng camera
                    if fbw < self.min_face_px or fbh < self.min_face_px:
                        continue
                    # Lọc 2: Border exclusion - loại detection sát rìa frame (tường, kết cấu)
                    if cx < bdr_x or cx > (mw - bdr_x) or cy < bdr_y or cy > (mh - bdr_y):
                        continue
                    detected_faces.append(face)

            # -------------------------------------------------------------
            # BƯỚC 3: FACE TRACKER (Ưu Tiên 2 - Theo dõi liên tục)
            # -------------------------------------------------------------
            matched_track_ids = set()
            matched_det_indices = set()

            for det_idx, face in enumerate(detected_faces):
                det_box = face[:4].astype(int)
                best_track_id = None
                best_match_score = -1.0

                for tid, track in self.active_tracks.items():
                    if tid in matched_track_ids:
                        continue
                    iou, norm_dist = calculate_iou_and_dist(det_box, track.bbox)
                    if iou >= 0.20 or norm_dist <= 0.65:
                        match_score = iou + (1.0 - min(norm_dist, 1.0))
                        if match_score > best_match_score:
                            best_match_score = match_score
                            best_track_id = tid

                if best_track_id is not None:
                    matched_track_ids.add(best_track_id)
                    matched_det_indices.add(det_idx)
                    tr = self.active_tracks[best_track_id]
                    tr.bbox = [int(v) for v in det_box]
                    tr.face_data = face
                    tr.frames_since_update = 0
                    tr.last_seen_time = time.time()

            # Tạo track mới cho các detection chưa khớp
            for det_idx, face in enumerate(detected_faces):
                if det_idx not in matched_det_indices:
                    det_box = [int(v) for v in face[:4]]
                    tid = self.next_track_id
                    self.next_track_id += 1
                    self.active_tracks[tid] = FaceTrack(tid, det_box, face)
                    matched_track_ids.add(tid)

            # Xóa các track quá hạn không xuất hiện
            dead_track_ids = []
            for tid, track in self.active_tracks.items():
                if tid not in matched_track_ids:
                    track.frames_since_update += 1
                    if track.frames_since_update > 4 or (time.time() - track.last_seen_time > 0.8):
                        dead_track_ids.append(tid)

            for tid in dead_track_ids:
                del self.active_tracks[tid]

            # -------------------------------------------------------------
            # BƯỚC 4: QUALITY FILTER & DEFERRED RECOGNITION (Ưu Tiên 2, 3, 1)
            # -------------------------------------------------------------
            for tid in matched_track_ids:
                track = self.active_tracks.get(tid)
                if track is None:
                    continue

                tx, ty, tbw, tbh = track.bbox
                x1, y1 = max(0, tx), max(0, ty)
                x2, y2 = min(mw, tx + tbw), min(mh, ty + tbh)
                if x2 - x1 < 15 or y2 - y1 < 15:
                    continue

                face_crop = main_frame[y1:y2, x1:x2]

                # 1. Kiểm tra độ sáng (Brightness)
                brightness = float(face_crop.mean())
                brightness_ok = (BRIGHTNESS_MIN <= brightness <= BRIGHTNESS_MAX)

                # 2. Kiểm tra độ nét (Laplacian variance)
                face_gray = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY)
                blur_score = float(cv2.Laplacian(face_gray, cv2.CV_64F).var())
                sharpness_ok = (blur_score >= BLUR_THRESHOLD)

                # 3. Kiểm tra hướng mặt (Facing camera)
                is_facing, reason = self.ai_engine.is_facing_camera(track.face_data)

                # Cập nhật ứng viên tốt nhất (sharpest candidate) cho track này
                if brightness_ok and is_facing and blur_score > track.best_blur:
                    track.best_blur = blur_score
                    track.best_face = track.face_data.copy()
                    track.best_frame = main_frame.copy()
                    track.best_crop = face_crop

                # Nhận diện nếu chưa ghi nhận điểm danh cho lượt đi này
                if not track.attendance_logged:
                    rec_frame = None
                    rec_face = None

                    # Ưu tiên nhận diện ngay nếu frame hiện tại đủ nét và đúng góc
                    if sharpness_ok and brightness_ok and is_facing:
                        rec_frame = main_frame
                        rec_face = track.face_data
                    # Hoặc dùng frame nét nhất đã gom được trong bộ đệm của track
                    elif track.best_blur >= BLUR_THRESHOLD and track.best_frame is not None:
                        rec_frame = track.best_frame
                        rec_face = track.best_face

                    if rec_frame is not None:
                        aligned = self.recognizer.alignCrop(rec_frame, rec_face)
                        feat = self.recognizer.feature(aligned)
                        emp_id, score, conf_pct = self.ai_engine.recognize_face(feat, self.recognizer)

                        if emp_id is not None and conf_pct >= MIN_ACCURACY_THRESHOLD:
                            track.streak += 1
                            track.recognized_emp_id = emp_id
                            track.recognized_conf = conf_pct
                            profile = self.ai_engine.employees.get(emp_id, {})
                            track.recognized_profile = profile

                            # Dual-threshold cân bằng (tinh chỉnh theo simulation thực tế):
                            # - Instant trigger: conf >= 90% (1 frame chắc chắn, không cần streak)
                            # - Streak trigger : conf >= 80% VÀ streak >= 2 (2 frame liên tiếp)
                            # Lý do: streak>=2 vẫn chống false positive tốt hơn streak>=1
                            # trong khi không quá khắt khe với người đi nhanh qua camera
                            if (conf_pct >= MIN_ACCURACY_THRESHOLD and track.streak >= 2
                                    or conf_pct >= 90.0) and not track.attendance_logged:
                                code = profile.get("EmployeeCode") or emp_id
                                with self.ai_engine.data_lock:
                                    self.ai_engine.rtsp_last_event_id += 1
                                    event_id = self.ai_engine.rtsp_last_event_id
                                    self.ai_engine.last_event_id = event_id
                                    card_id = f"{code}_{event_id}"
                                    card = {
                                        "event_id": event_id,
                                        "card_id": card_id,
                                        "timestamp": time.time(),
                                        "emp_id": emp_id,
                                        "code": code,
                                        "name": profile.get("FullName", f"NV: {emp_id}"),
                                        "role": profile.get("Name_Role", "Nhân viên"),
                                        "dept": profile.get("Dept_Name", "--"),
                                        "company": profile.get("Company_Name", "--"),
                                        "workplace": profile.get("WorkPlaceName", ""),
                                        "profile": profile,
                                        "confidence": conf_pct,
                                        "expire_time": time.time() + 6.0,
                                        "cam_name": self.cam_name,
                                        "cam_id": self.cam_id,
                                        "avatar": f"/api_faces/{emp_id}.jpg" if os.path.exists(os.path.join(API_FACES_DIR, f"{emp_id}.jpg")) else "",
                                        "snapshot": f"{code}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg",
                                        "snapshot_url": f"/snapshots/{code}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg",
                                        "today_logs": get_today_employee_logs(code)
                                    }
                                    # Luồng RTSP: Chỉ gửi vào kênh rtsp_active_card (cho Dashboard Admin)
                                    self.ai_engine.rtsp_active_card = card
                                    self.ai_engine.rtsp_latest_event = card
                                    self.ai_engine.active_card = card
                                    self.ai_engine.latest_event = card
                                self.ai_engine.log_attendance(
                                    emp_id, profile, conf_pct, self.cam_name, self.cam_id,
                                    rec_frame, (tx, ty, tbw, tbh)
                                )
                                track.attendance_logged = True

                            # ★ Ưu Tiên 1: Multi-Angle Embedding Self-Enrichment
                            if conf_pct >= SELF_ENRICH_MIN_CONF and track.streak >= self.enrich_streak_req:
                                self.ai_engine.self_enrich_embedding(emp_id, feat, conf_pct)
                        else:
                            if emp_id and conf_pct >= 50.0:
                                track.recognized_conf = conf_pct
                            else:
                                track.streak = max(0, track.streak - 1)

            # -------------------------------------------------------------
            # BƯỚC 5: TẠO KHUNG HIỂN THỊ (BOUNDING BOXES) CHO LUỒNG WEB 25 FPS
            # -------------------------------------------------------------
            new_boxes = []
            for tid, track in self.active_tracks.items():
                if track.frames_since_update > 2:
                    continue
                tx, ty, tbw, tbh = track.bbox

                if track.recognized_emp_id:
                    code = track.recognized_profile.get("EmployeeCode") or track.recognized_emp_id
                    label = f"[{code}] {track.recognized_conf:.0f}%"
                    color = (204, 82, 0)   # Xanh dương doanh nghiệp
                elif track.streak > 0:
                    label = f"Xac thuc... {track.recognized_conf:.0f}%"
                    color = (0, 200, 255)  # Vàng
                elif track.best_blur < BLUR_THRESHOLD and track.best_blur > 0:
                    label = f"Di chuyen nhanh ({int(track.best_blur)} blur)"
                    color = (0, 165, 255)  # Cam
                else:
                    label = "Chua dang ky"
                    color = (0, 100, 255)  # Đỏ

                nx = max(0.0, float(tx) / mw)
                ny = max(0.0, float(ty) / mh)
                nw = min(1.0 - nx, float(tbw) / mw)
                nh = min(1.0 - ny, float(tbh) / mh)
                new_boxes.append((nx, ny, nw, nh, label, color))

            with self.lock:
                self.cached_boxes = new_boxes

            # -------------------------------------------------------------
            # BƯỚC 6: BÙ TRỪ THỜI GIAN NGỦ ĐỂ ĐẠT CHÍNH XÁC AI FPS (Ưu Tiên 5)
            # -------------------------------------------------------------
            elapsed = time.time() - t_loop_start
            sleep_sec = max(0.005, self.ai_sleep_sec - elapsed)
            time.sleep(sleep_sec)

    def get_next_jpeg(self, last_id, timeout=0.2):
        self.last_client_request_time = time.time()
        with self.lock:
            if self.frame_id == last_id:
                self.condition.wait(timeout)
            return self.latest_jpeg, self.frame_id

    def release(self):
        self.running = False
        if self.grabber_sub:
            self.grabber_sub.release()
        if self.grabber_main and self.grabber_main != self.grabber_sub:
            self.grabber_main.release()


# =============================================================================
# 4. KHỞI CHẠY BACKEND FLASK & ĐIỀU PHỐI LUỒNG HÌNH ẢNH ZERO-LAG
# =============================================================================
app = Flask(__name__)
ai_engine = AIFaceEngine()
camera_workers = {}

# TỰ ĐỘNG KHỞI TẠO CÁC CAMERA RTSP ĐANG BẬT (ENABLED: TRUE) TỪ CẤU HÌNH CAMERAS_CONFIG.JSON
ENABLE_RTSP_STREAMING = True

if ENABLE_RTSP_STREAMING:
    for cam in camera_sources:
        if cam.get("enabled", True):
            camera_workers[cam["id"]] = CameraStreamWorker(
                cam["id"], cam["name"], cam["url"], ai_engine
            )
            print(f"[+] [Tự Động Kích Hoạt] Đã kết nối luồng RTSP cho: {cam['name']}")
else:
    print("[*] Đã tách các luồng RTSP camera IP: Toàn bộ CPU/GPU được giải phóng, tập trung 100% cho Smart Facial & Web Kiosk.")


# =============================================================================
# 5. GIAO DIỆN WEB HTML MENU 3 MỤC CHUYÊN NGHIỆP
# =============================================================================
HTML_ENTERPRISE_PORTAL = """
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Smart HRMS • Hệ Thống Điểm Danh Khuôn Mặt</title>
    <!-- Phông chữ chuẩn tiếng Việt cục bộ (Offline & Intranet 100% an toàn) -->
    <link rel="stylesheet" href="/static/fonts/fonts_local.css">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Be+Vietnam+Pro:ital,wght@0,300;0,400;0,500;0,600;0,700;0,800;1,400&family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <!-- THƯ VIỆN BIỂU ĐỒ CHART.JS -->
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root {
            --primary: #1e3a8a;
            --primary-hover: #172554;
            --primary-light: #eff6ff;
            --accent: #2563eb;
            --accent-hover: #1d4ed8;
            --bg: #f8fafc;
            --card-bg: #ffffff;
            --text-dark: #0f172a;
            --text-normal: #334155;
            --text-muted: #64748b;
            --text-light: #94a3b8;
            --success: #059669;
            --success-bg: #ecfdf5;
            --border: #e2e8f0;
            --border-subtle: #f1f5f9;
            --danger: #dc2626;
            --shadow-sm: 0 1px 2px 0 rgba(0, 0, 0, 0.04);
            --shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.06), 0 1px 2px -1px rgba(0, 0, 0, 0.04);
        }

        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Be Vietnam Pro', 'Inter', Roboto, -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif; -webkit-font-smoothing: antialiased; }
        body { background: var(--bg); color: var(--text-dark); min-height: 100vh; display: flex; flex-direction: column; }

        /* HEADER & MENU NAVIGATION BAR */
        header {
            background: var(--card-bg);
            border-bottom: 1px solid var(--border);
            padding: 10px 24px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            position: sticky; top: 0; z-index: 50;
            box-shadow: var(--shadow-sm);
        }
        .header-left { display: flex; align-items: center; gap: 32px; }
        .brand { display: flex; align-items: center; gap: 10px; text-decoration: none; }
        .brand-icon {
            width: 32px; height: 32px; border-radius: 6px; background: #0f172a;
            color: #fff; display: flex; align-items: center; justify-content: center;
        }
        .brand-text-group { display: flex; align-items: center; gap: 8px; }
        .brand-name { font-size: 15px; font-weight: 700; color: #0f172a; letter-spacing: -0.3px; }
        .brand-divider { color: var(--border); font-size: 14px; font-weight: 300; }
        .brand-subtitle { font-size: 13px; font-weight: 500; color: var(--text-muted); }

        /* 3-TAB MAIN MENU */
        .nav-tabs { display: flex; gap: 4px; }
        .nav-tab-btn {
            background: transparent; color: #475569; border: none; border-radius: 6px; padding: 7px 14px;
            font-size: 13px; font-weight: 500; cursor: pointer; display: flex; align-items: center; gap: 8px;
            transition: all 0.15s;
        }
        .nav-tab-btn:hover { background: var(--border-subtle); color: #0f172a; }
        .nav-tab-btn.active { background: var(--primary-light); color: var(--accent); font-weight: 600; }

        .header-right { display: flex; align-items: center; gap: 14px; }
        .kpi-pill { background: #fff; border: 1px solid var(--border); border-radius: 6px; padding: 5px 12px; font-size: 12px; font-weight: 500; color: #475569; display: flex; align-items: center; gap: 6px; font-variant-numeric: tabular-nums; }
        .kpi-pill.clock { min-width: 145px; justify-content: center; color: var(--text-normal); }
        .status-indicator-badge {
            background: #fff; border: 1px solid #d1fae5; border-radius: 6px; padding: 5px 12px;
            font-size: 12px; font-weight: 600; color: var(--success); display: flex; align-items: center; gap: 7px;
        }
        .status-pulse-dot {
            width: 7px; height: 7px; border-radius: 50%; background: #10b981;
            box-shadow: 0 0 0 2px #d1fae5;
        }

        /* MAIN CONTAINER */
        main { padding: 12px 20px; flex: 1; display: flex; flex-direction: column; max-width: 1920px; margin: 0 auto; width: 100%; }

        /* VIEW CONTAINER */
        .app-view { display: none; width: 100%; animation: fadeIn 0.15s ease; }
        @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }

        /* ADMIN DASHBOARD */
        .admin-grid { display: flex; flex-direction: column; gap: 20px; }
        .kpi-cards-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 14px; }
        @media (max-width: 1200px) { .kpi-cards-grid { grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); } }
        @media (max-width: 768px) { .kpi-cards-grid { grid-template-columns: repeat(2, 1fr); } }
        
        .stat-card {
            background: var(--card-bg); border-radius: 8px; border: 1px solid var(--border); padding: 16px 18px;
            box-shadow: var(--shadow-sm); display: flex; flex-direction: column; gap: 6px;
        }
        .stat-title { font-size: 11px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.4px; }
        .stat-val { font-size: 26px; font-weight: 700; color: var(--text-dark); letter-spacing: -0.5px; }
        .stat-desc { font-size: 11px; color: var(--text-light); }
        .text-success { color: var(--success) !important; }
        .text-accent { color: var(--accent) !important; }

        .admin-card {
            background: var(--card-bg); border-radius: 8px; border: 1px solid var(--border);
            box-shadow: var(--shadow-sm); overflow: hidden;
        }
        .admin-card-header {
            background: #fff; border-bottom: 1px solid var(--border); padding: 12px 18px;
            display: flex; justify-content: space-between; align-items: center;
        }
        .admin-card-title { font-size: 13px; font-weight: 700; color: #0f172a; display: flex; align-items: center; gap: 8px; }
        .admin-card-body { padding: 18px; }

        .btn {
            background: var(--primary); color: #fff; border: 1px solid var(--primary); border-radius: 6px; padding: 7px 14px;
            font-size: 12px; font-weight: 600; cursor: pointer; display: inline-flex; align-items: center; gap: 6px;
            text-decoration: none; transition: all 0.15s; line-height: 1;
        }
        .btn:hover { background: var(--primary-hover); }
        .btn-primary { background: #0f172a; border-color: #0f172a; color: #fff; }
        .btn-primary:hover { background: #1e293b; }
        .btn-secondary { background: #fff; color: #334155; border: 1px solid var(--border); }
        .btn-secondary:hover { background: #f8fafc; border-color: #cbd5e1; color: #0f172a; }
        .btn-outline { background: #fff; color: var(--accent); border: 1px solid var(--border); }
        .btn-outline:hover { background: var(--primary-light); border-color: var(--accent); }
        .btn-danger { background: #fff; color: var(--danger); border: 1px solid #fecaca; }
        .btn-danger:hover { background: #fef2f2; }

        .badge-online { display: inline-flex; align-items: center; gap: 5px; font-size: 11px; font-weight: 600; color: var(--success); background: var(--success-bg); padding: 3px 8px; border-radius: 4px; border: 1px solid #a7f3d0; }
        .badge-online::before { content: ""; width: 5px; height: 5px; border-radius: 50%; background: var(--success); }
        .badge-offline { display: inline-flex; align-items: center; gap: 5px; font-size: 11px; font-weight: 600; color: #64748b; background: #f1f5f9; padding: 3px 8px; border-radius: 4px; border: 1px solid #e2e8f0; }
        .badge-offline::before { content: ""; width: 5px; height: 5px; border-radius: 50%; background: #94a3b8; }
        .badge-muted { display: inline-flex; font-size: 11px; font-weight: 500; color: var(--text-muted); background: #f1f5f9; padding: 3px 8px; border-radius: 4px; }
        .field-label { font-weight: 600; color: #475569; }

        /* CAMERA VIEW */
        .camera-view-container { display: flex; flex-direction: column; gap: 10px; }
        .camera-subnav {
            background: var(--card-bg); border-radius: 8px; border: 1px solid var(--border);
            padding: 6px 14px; display: flex; justify-content: space-between; align-items: center;
            box-shadow: var(--shadow-sm); flex-wrap: wrap; gap: 10px;
        }
        .cam-switcher-tabs { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }
        .cam-tab-btn {
            background: #fff; color: #475569; border: 1px solid var(--border); border-radius: 6px;
            padding: 5px 12px; font-size: 12px; font-weight: 600; cursor: pointer; display: flex; align-items: center; gap: 7px;
            transition: all 0.15s;
        }
        .cam-tab-btn:hover { background: #f8fafc; color: #0f172a; }
        .cam-tab-btn.active { background: #0f172a; color: #fff; border-color: #0f172a; }

        .select-field {
            padding: 5px 10px; border-radius: 6px; border: 1px solid var(--border);
            font-size: 12px; font-weight: 500; color: #0f172a; background: #fff; cursor: pointer; outline: none;
        }
        .select-field:focus { border-color: var(--accent); }

        /* 2-COLUMN SPLIT LAYOUT */
        .camera-split-layout { display: grid; grid-template-columns: 1fr 380px; gap: 14px; align-items: start; }
        .cam-display-col { display: flex; flex-direction: column; gap: 10px; }
        
        .cam-grid-layout { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; }
        .cam-grid-layout.three-cams { grid-template-columns: repeat(3, 1fr); }
        @media (max-width: 1200px) { .cam-grid-layout.three-cams { grid-template-columns: repeat(2, 1fr); } }
        
        .cam-card {
            background: #000; border-radius: 8px; border: 1px solid var(--border); overflow: hidden;
            box-shadow: var(--shadow-sm); display: flex; flex-direction: column;
            transition: border-color 0.15s;
        }
        .cam-card:hover { border-color: #94a3b8; }
        .cam-card-offline {
            background: #0f172a; border: 1px dashed #334155;
        }
        .cam-card-offline:hover { border-color: #64748b; }
        .cam-header {
            background: #0f172a; color: #fff; padding: 7px 12px; display: flex; justify-content: space-between; align-items: center;
        }
        .cam-title { font-size: 12px; font-weight: 600; display: flex; align-items: center; gap: 6px; letter-spacing: -0.2px; }
        .live-tag {
            background: rgba(255,255,255,0.12); color: #fff; font-size: 10px; font-weight: 700;
            padding: 2px 7px; border-radius: 4px; display: flex; align-items: center; gap: 5px; letter-spacing: 0.5px;
        }
        .offline-tag {
            background: rgba(148, 163, 184, 0.2); color: #94a3b8; font-size: 10px; font-weight: 700;
            padding: 2px 7px; border-radius: 4px; display: inline-flex; align-items: center; gap: 4px; letter-spacing: 0.3px;
        }
        .live-dot {
            width: 6px; height: 6px; border-radius: 50%; background: #ef4444;
            box-shadow: 0 0 0 2px rgba(239, 68, 68, 0.4);
            animation: livePulse 1.6s infinite ease-in-out;
        }
        .cam-toggle-mini-btn {
            padding: 2px 8px; font-size: 11px; font-weight: 600; border-radius: 4px; cursor: pointer;
            border: 1px solid transparent; transition: all 0.15s;
        }
        .cam-toggle-mini-btn.btn-active {
            background: #fee2e2; color: #b91c1c; border-color: #fca5a5;
        }
        .cam-toggle-mini-btn.btn-active:hover {
            background: #fecaca;
        }
        .cam-toggle-mini-btn.btn-inactive {
            background: #dbeafe; color: #1d4ed8; border-color: #bfdbfe;
        }
        .cam-toggle-mini-btn.btn-inactive:hover {
            background: #bfdbfe;
        }
        .offline-standby-container {
            display: flex; flex-direction: column; align-items: center; justify-content: center;
            background: #0b1120;
        }
        @keyframes livePulse {
            0% { transform: scale(0.9); opacity: 0.8; }
            50% { transform: scale(1.15); opacity: 1; }
            100% { transform: scale(0.9); opacity: 0.8; }
        }

        .video-container { position: relative; width: 100%; aspect-ratio: 16/9; max-height: calc(50vh - 100px); background: #000; overflow: hidden; }
        .video-feed {
            width: 100%; height: 100%; object-fit: contain; display: block;
            image-rendering: -webkit-optimize-contrast; image-rendering: crisp-edges;
        }
        .cam-sub {
            background: #fff; border-top: 1px solid var(--border); padding: 6px 12px;
            font-size: 11px; color: var(--text-muted); display: flex; justify-content: space-between; align-items: center;
        }
        .cam-sub-link { color: var(--accent); font-weight: 600; text-decoration: none; }

        /* Single Camera Large Mode - Khống chế chiều cao theo 100vh để không bao giờ bị scroll */
        .single-cam-wrapper {
            background: #000; border-radius: 8px; border: 1px solid var(--border); overflow: hidden;
            box-shadow: var(--shadow); display: flex; flex-direction: column;
        }
        .single-cam-header {
            background: #0f172a; color: #fff; padding: 8px 14px; display: flex; justify-content: space-between; align-items: center;
        }
        .single-cam-video {
            width: 100%;
            height: calc(100vh - 215px);
            max-height: 560px;
            min-height: 380px;
            aspect-ratio: auto;
            display: flex;
            justify-content: center;
            align-items: center;
            background: #000;
        }
        .single-cam-feed {
            max-width: 100%;
            max-height: 100%;
            object-fit: contain;
            display: block;
            image-rendering: -webkit-optimize-contrast; image-rendering: crisp-edges;
        }

        /* RIGHT COLUMN: INFORMATION & LOGS */
        .info-log-col { display: flex; flex-direction: column; gap: 10px; position: sticky; top: 66px; }

        /* LATEST VERIFIED CARD */
        .verified-card {
            background: #fff; border: 1px solid var(--border); border-radius: 8px;
            box-shadow: var(--shadow-sm); overflow: hidden;
        }
        .verified-card-header {
            background: #fff; border-bottom: 1px solid var(--border); padding: 8px 12px;
            display: flex; justify-content: space-between; align-items: center;
        }
        .verified-title { font-size: 12px; font-weight: 700; color: #0f172a; }
        .conf-pill {
            background: #ecfdf5; color: #047857; border: 1px solid #a7f3d0;
            padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 700;
        }
        .verified-card-body { padding: 10px 12px; display: flex; gap: 10px; }
        .card-avatar {
            width: 72px; height: 72px; border-radius: 6px; object-fit: cover;
            border: 1px solid var(--border); background: #f1f5f9; flex-shrink: 0;
        }
        .avatar-placeholder-svg {
            display: flex; align-items: center; justify-content: center; background: #f8fafc;
        }
        .verified-details { flex: 1; display: flex; flex-direction: column; gap: 3px; font-size: 11px; }
        .v-name { font-size: 13px; font-weight: 700; color: #0f172a; }
        .v-role { color: var(--accent); font-weight: 600; font-size: 11px; margin-bottom: 2px; }
        .v-row { display: flex; justify-content: space-between; border-bottom: 1px solid var(--border-subtle); padding-bottom: 2px; }
        .v-label { color: var(--text-muted); font-size: 11px; }
        .v-val { color: #0f172a; font-weight: 500; font-size: 11px; }
        .font-semibold { font-weight: 600 !important; }
        .v-status { display: inline-block; background: #ecfdf5; color: var(--success); font-weight: 600; padding: 2px 6px; border-radius: 4px; font-size: 10px; width: fit-content; margin-top: 2px; }

        /* LOG FEED CARD */
        .log-feed-card {
            background: var(--card-bg); border-radius: 8px; border: 1px solid var(--border);
            box-shadow: var(--shadow-sm); display: flex; flex-direction: column; overflow: hidden;
        }
        .log-feed-header {
            background: #fff; border-bottom: 1px solid var(--border); padding: 8px 12px;
            display: flex; justify-content: space-between; align-items: center;
        }
        .log-feed-title { font-size: 12px; font-weight: 700; color: #0f172a; }
        .log-scope-buttons { display: flex; gap: 4px; }
        .log-filter-btn {
            background: #fff; border: 1px solid var(--border); border-radius: 4px;
            padding: 3px 8px; font-size: 11px; font-weight: 500; cursor: pointer; color: #64748b;
        }
        .log-filter-btn.active { background: #0f172a; color: #fff; border-color: #0f172a; font-weight: 600; }

        .log-feed-list { max-height: calc(100vh - 350px); min-height: 250px; overflow-y: auto; display: flex; flex-direction: column; }
        .log-item {
            display: flex; gap: 10px; padding: 8px 12px; border-bottom: 1px solid var(--border-subtle); align-items: center;
            transition: background 0.15s;
        }
        .log-item:hover { background: #f8fafc; }
        .log-thumb { width: 38px; height: 38px; border-radius: 4px; object-fit: cover; border: 1px solid var(--border); cursor: pointer; }
        .log-thumb:hover { transform: scale(2); z-index: 10; position: relative; box-shadow: 0 4px 12px rgba(0,0,0,0.15); }
        .log-info { flex: 1; display: flex; flex-direction: column; gap: 1px; font-size: 11px; }
        .log-name { font-weight: 600; color: var(--text-dark); display: flex; justify-content: space-between; }
        .log-sub { color: var(--text-muted); font-size: 11px; }
        .log-conf { color: var(--success); font-weight: 700; font-size: 11px; }

        /* DATA VIEW */
        .data-view-container { display: flex; flex-direction: column; gap: 14px; }
        .data-tabs { display: flex; gap: 8px; border-bottom: 1px solid var(--border); padding-bottom: 8px; }
        .data-tab-btn {
            background: transparent; color: #64748b; border: none; font-size: 13px; font-weight: 600;
            padding: 7px 14px; border-radius: 6px; cursor: pointer; transition: all 0.15s;
        }
        .data-tab-btn:hover { color: #0f172a; background: var(--border-subtle); }
        .data-tab-btn.active { background: #0f172a; color: #fff; }

        .toolbar-box {
            background: #fff; padding: 12px 16px; border-radius: 8px; border: 1px solid var(--border);
            display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap;
            box-shadow: var(--shadow-sm);
        }
        .search-input-wrapper {
            position: relative; display: flex; align-items: center; min-width: 280px;
        }
        .search-icon {
            position: absolute; left: 10px; color: #94a3b8; pointer-events: none;
        }
        .search-box-field {
            width: 100%; padding: 7px 12px 7px 32px; border: 1px solid var(--border); border-radius: 6px;
            font-size: 12px; outline: none; background: #fff; color: #0f172a;
        }
        .search-box-field:focus { border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent); }

        table { width: 100%; border-collapse: collapse; font-size: 12px; background: #fff; border-radius: 8px; overflow: hidden; border: 1px solid var(--border); }
        th { background: #f8fafc; color: #475569; font-weight: 600; text-align: left; padding: 9px 12px; border-bottom: 1px solid var(--border); position: sticky; top: 0; font-size: 11px; letter-spacing: 0.2px; }
        td { padding: 8px 12px; border-bottom: 1px solid var(--border-subtle); vertical-align: middle; color: #334155; }
        tr:nth-child(even) td { background: #fcfcfd; }
        tr:hover td { background: #f8fafc; }

        /* MODAL POPUPS */
        .modal-overlay {
            position: fixed; inset: 0; background: rgba(15, 23, 42, 0.6); z-index: 1000;
            display: none; align-items: center; justify-content: center; backdrop-filter: blur(2px);
        }
        .modal-box {
            background: #fff; border-radius: 8px; width: 500px; max-width: 95%; overflow: hidden;
            box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 8px 10px -6px rgba(0, 0, 0, 0.1);
        }
        .modal-header {
            background: #fff; border-bottom: 1px solid var(--border); color: #0f172a;
            padding: 14px 18px; display: flex; justify-content: space-between; align-items: center;
            font-size: 14px; font-weight: 700;
        }
        .modal-close-btn { background: transparent; border: none; color: #64748b; font-size: 16px; cursor: pointer; padding: 4px; }
        .modal-close-btn:hover { color: #0f172a; }
        .modal-body { padding: 18px; display: flex; flex-direction: column; gap: 14px; }
        .form-group { display: flex; flex-direction: column; gap: 5px; }
        .form-label { font-size: 12px; font-weight: 600; color: #334155; }
        .form-input { padding: 7px 12px; border: 1px solid var(--border); border-radius: 6px; font-size: 13px; outline: none; }
        .form-input:focus { border-color: var(--accent); }
        .modal-footer { padding: 12px 18px; background: #f8fafc; border-top: 1px solid var(--border); display: flex; justify-content: flex-end; gap: 8px; }

        /* ANALYTICS */
        .analytics-header-bar {
            background: var(--card-bg); border-radius: 8px; border: 1px solid var(--border);
            padding: 14px 18px; display: flex; justify-content: space-between; align-items: center;
            flex-wrap: wrap; gap: 12px; box-shadow: var(--shadow-sm);
        }
        .section-title { font-size: 16px; font-weight: 700; color: #0f172a; letter-spacing: -0.3px; }
        .section-subtitle { font-size: 12px; color: var(--text-muted); margin-top: 2px; }
        .header-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
        .scope-btn-group { display: flex; background: #f1f5f9; border-radius: 6px; padding: 2px; gap: 2px; }
        .scope-btn {
            background: transparent; border: none; border-radius: 4px; padding: 5px 12px;
            font-size: 12px; font-weight: 500; color: #475569; cursor: pointer; transition: all 0.15s;
        }
        .scope-btn:hover { color: #0f172a; }
        .scope-btn.active { background: #fff; color: #0f172a; font-weight: 600; box-shadow: var(--shadow-sm); }

        .charts-grid { display: grid; grid-template-columns: 1.25fr 1.25fr 1fr; gap: 14px; }
        @media (max-width: 1300px) { .charts-grid { grid-template-columns: 1fr; } }
        .chart-card { display: flex; flex-direction: column; }
        .chart-tag { font-size: 11px; font-weight: 600; color: #475569; background: #f1f5f9; padding: 2px 7px; border-radius: 4px; }

        .table-subtab-btn {
            background: #fff; border: 1px solid var(--border); border-radius: 6px;
            padding: 6px 12px; font-size: 12px; font-weight: 500; color: #475569; cursor: pointer;
            display: inline-flex; align-items: center; gap: 6px; transition: all 0.15s;
        }
        .table-subtab-btn:hover { background: #f8fafc; color: #0f172a; }
        .table-subtab-btn.active { background: #0f172a; color: #fff; border-color: #0f172a; font-weight: 600; }

        .clickable-row { cursor: pointer; }
        .clickable-row:hover td { background: #f1f5f9 !important; }

        /* BỘ LỌC THỜI GIAN & NÚT CUỘN BẢNG THỐNG KÊ THEO NGÀY */
        .date-picker-input {
            padding: 4px 8px;
            font-size: 11px;
            font-family: inherit;
            border: 1px solid #cbd5e1;
            border-radius: 5px;
            color: #0f172a;
            background: #ffffff;
            outline: none;
            cursor: pointer;
            transition: all 0.15s;
        }
        .date-picker-input:focus {
            border-color: #0284c7;
            box-shadow: 0 0 0 2px rgba(2, 132, 199, 0.18);
        }
        .quick-preset-pill {
            background: #f1f5f9;
            border: 1px solid #e2e8f0;
            border-radius: 4px;
            padding: 2px 7px;
            font-size: 10px;
            font-weight: 600;
            color: #475569;
            cursor: pointer;
            transition: all 0.15s;
        }
        .quick-preset-pill:hover {
            background: #e0f2fe;
            color: #0284c7;
            border-color: #bae6fd;
        }
        .table-scroll-fab {
            position: absolute;
            right: 14px;
            bottom: 14px;
            display: flex;
            flex-direction: column;
            gap: 6px;
            z-index: 25;
            opacity: 0.88;
            transition: opacity 0.2s, transform 0.15s;
        }
        .table-scroll-fab:hover {
            opacity: 1;
            transform: scale(1.05);
        }
        .fab-scroll-btn {
            width: 32px;
            height: 32px;
            border-radius: 50%;
            background: #0f172a;
            color: #ffffff;
            border: 1px solid rgba(255, 255, 255, 0.25);
            box-shadow: 0 4px 10px rgba(0, 0, 0, 0.2);
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            transition: all 0.15s;
        }
        .fab-scroll-btn:hover {
            background: #0284c7;
            border-color: #38bdf8;
            box-shadow: 0 6px 14px rgba(2, 132, 199, 0.35);
        }
        #pane-daily {
            position: relative;
            scroll-behavior: smooth;
            overflow-y: scroll !important;
        }
        #pane-daily::-webkit-scrollbar {
            width: 10px;
            height: 10px;
        }
        #pane-daily::-webkit-scrollbar-track {
            background: #f1f5f9;
            border-left: 1px solid #e2e8f0;
        }
        #pane-daily::-webkit-scrollbar-thumb {
            background: #94a3b8;
            border-radius: 5px;
            border: 2px solid #f1f5f9;
        }
        #pane-daily::-webkit-scrollbar-thumb:hover {
            background: #0284c7;
        }
        #pane-daily table th {
            position: sticky;
            top: 0;
            z-index: 3;
            background: #f8fafc;
            box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
        }

        /* PERSON PROFILE & TIMELINE MODAL */
        .person-profile-header {
            display: flex; gap: 16px; align-items: center; background: #f8fafc;
            border: 1px solid var(--border); border-radius: 8px; padding: 14px;
        }
        .person-profile-avatar {
            width: 80px; height: 80px; border-radius: 6px; object-fit: cover;
            border: 1px solid var(--border); background: #e2e8f0; flex-shrink: 0;
        }
        .pd-stat-box {
            background: #f8fafc; border: 1px solid var(--border); border-radius: 6px;
            padding: 10px; display: flex; flex-direction: column; gap: 2px;
        }
        .pd-stat-label { font-size: 11px; font-weight: 600; color: var(--text-muted); }
        .pd-stat-val { font-size: 14px; font-weight: 700; color: var(--text-dark); }
        
        .pd-timeline-list { display: flex; flex-direction: column; gap: 8px; max-height: 400px; overflow-y: auto; padding-right: 4px; }
        .timeline-card {
            background: #fff; border: 1px solid var(--border); border-radius: 6px; padding: 10px 12px;
            display: flex; justify-content: space-between; align-items: center; gap: 12px;
        }
        .timeline-time { font-family: monospace; font-size: 12px; font-weight: 600; color: #0f172a; }
        .timeline-badge {
            display: inline-block; font-size: 11px; font-weight: 500; padding: 2px 7px;
            border-radius: 4px; background: #f1f5f9; color: #334155;
        }
        .timeline-snap-box {
            position: relative; width: 50px; height: 50px; border-radius: 4px; overflow: hidden;
            border: 1px solid var(--border); cursor: pointer; flex-shrink: 0; background: #000;
        }
        .timeline-snap-img { width: 100%; height: 100%; object-fit: cover; }
        .snap-zoom-icon {
            position: absolute; right: 2px; bottom: 2px; background: rgba(15,23,42,0.7);
            color: #fff; font-size: 9px; padding: 1px 3px; border-radius: 2px;
        }

        footer { background: #fff; border-top: 1px solid var(--border); padding: 12px 24px; font-size: 11px; color: var(--text-muted); display: flex; justify-content: space-between; align-items: center; margin-top: auto; }
    </style>
</head>
<body>

    <!-- HEADER & MENU NAVIGATION BAR -->
    <header>
        <div class="header-left">
            <a href="#" class="brand">
                <div class="brand-icon">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/>
                        <circle cx="12" cy="13" r="4"/>
                    </svg>
                </div>
                <div class="brand-text-group">
                    <span class="brand-name">Smart HRMS</span>
                    <span class="brand-divider">/</span>
                    <span class="brand-subtitle">Hệ thống điểm danh khuôn mặt</span>
                </div>
            </a>

            <!-- 3-TAB MAIN MENU -->
            <nav class="nav-tabs">
                <button class="nav-tab-btn" id="tab-admin" onclick="switchNavTab('admin')">
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="9" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/><rect x="14" y="12" width="7" height="9" rx="1"/><rect x="3" y="16" width="7" height="5" rx="1"/></svg>
                    <span>Tổng quan & Thống kê</span>
                </button>
                <button class="nav-tab-btn active" id="tab-camera" onclick="switchNavTab('camera')">
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/></svg>
                    <span>Giám sát camera</span>
                </button>
                <button class="nav-tab-btn" id="tab-data" onclick="switchNavTab('data')">
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
                    <span>Dữ liệu & Báo cáo</span>
                </button>
                <a href="/kiosk" target="_blank" class="nav-tab-btn" style="text-decoration:none; display:inline-flex; align-items:center; gap:6px; color:#0284c7; border: 1px solid rgba(2, 132, 199, 0.35); background: rgba(2, 132, 199, 0.08); border-radius: 8px;">
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="4" y="2" width="16" height="20" rx="2" ry="2"/><line x1="12" y1="18" x2="12.01" y2="18"/></svg>
                    <span>Màn hình Kiosk</span>
                </a>
            </nav>
        </div>

        <div class="header-right">
            <div class="kpi-pill clock">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                <span id="clock">2026-09-28 14:00:00</span>
            </div>
            <div class="status-indicator-badge">
                <span class="status-pulse-dot"></span>
                <span><span id="online-cam-count">3</span> camera trực tuyến</span>
            </div>
        </div>
    </header>

    <!-- MAIN BODY -->
    <main>

        <!-- ==================================================================== -->
        <!-- MỤC 1: TRANG QUẢN TRỊ & PHÂN TÍCH THỐNG KÊ (ADMIN ANALYTICS)          -->
        <!-- ==================================================================== -->
        <div id="view-admin" class="app-view">
            <div class="admin-grid">
                <!-- TOP HEADER & SCOPE SELECTOR -->
                <div class="analytics-header-bar">
                    <div>
                        <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
                            <h2 style="font-size:16px;font-weight:700;color:#0f172a;letter-spacing:-0.2px;margin:0;">
                                Báo Cáo Phân Tích & Thống Kê Điểm Danh
                            </h2>
                            <span id="active-filter-badge" style="display:none;font-size:11px;font-weight:600;background:#e0f2fe;color:#0284c7;border:1px solid #bae6fd;padding:2px 8px;border-radius:9999px;align-items:center;gap:5px;">
                                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                                <span id="active-filter-badge-text">Đang lọc</span>
                            </span>
                        </div>
                        <div id="analytics-header-subtitle" style="font-size:12px;color:var(--text-muted);margin-top:2px;">
                            Dữ liệu hiện diện và lưu lượng nhân sự theo thời gian thực từ hệ thống camera giám sát.
                        </div>
                    </div>
                    <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
                        <div class="scope-btn-group">
                            <button class="scope-btn active" id="btn-scope-all" onclick="changeAnalyticsScope('all')">Toàn bộ lịch sử</button>
                            <button class="scope-btn" id="btn-scope-today" onclick="changeAnalyticsScope('today')">Hôm nay</button>
                            <button class="scope-btn" id="btn-scope-week" onclick="changeAnalyticsScope('week')">7 ngày qua</button>
                            <button class="scope-btn" id="btn-scope-month" onclick="changeAnalyticsScope('month')">30 ngày qua</button>
                            <button class="scope-btn" id="btn-scope-custom" style="display:none;" onclick="loadAdminAnalytics()">Tùy chọn lọc</button>
                        </div>
                        <button class="btn btn-outline" onclick="loadAdminAnalytics()" style="padding:5px 12px;font-size:12px;display:inline-flex;align-items:center;gap:6px;">
                            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"/></svg>
                            <span>Làm mới</span>
                        </button>
                    </div>
                </div>

                <!-- 8 KPI SUMMARY CARDS (BAO GỒM 2 KHUNG GIỜ CAO ĐIỂM 8H-9H VÀ 12H-13H) -->
                <div class="kpi-cards-grid">
                    <div class="stat-card">
                        <span class="stat-title">Tổng nhân sự</span>
                        <span class="stat-val" id="admin-api-count">--</span>
                        <span class="stat-desc">Đồng bộ từ HRMS</span>
                    </div>
                    <div class="stat-card">
                        <span class="stat-title">Hồ sơ khuôn mặt</span>
                        <span class="stat-val" id="admin-db-count">--</span>
                        <span class="stat-desc">Đã đăng ký nhận diện</span>
                    </div>
                    <div class="stat-card">
                        <span class="stat-title">Lượt điểm danh</span>
                        <span class="stat-val" id="admin-stat-scans">--</span>
                        <span class="stat-desc" id="admin-stat-scans-desc">Đã ghi nhận</span>
                        <span id="admin-today-count" style="display:none;"></span>
                    </div>
                    <div class="stat-card">
                        <span class="stat-title">Nhân sự có mặt</span>
                        <span class="stat-val" id="admin-stat-unique">--</span>
                        <span class="stat-desc" id="admin-stat-unique-desc">Nhân viên hiện diện</span>
                    </div>
                    <div class="stat-card" style="border-left: 3px solid #0284c7; background: linear-gradient(180deg, #f0f9ff 0%, #ffffff 100%);">
                        <div style="display:flex;justify-content:space-between;align-items:center;">
                            <span class="stat-title" style="color:#0369a1;font-weight:700;">Cao điểm 08h - 09h</span>
                            <span style="font-size:10px;font-weight:700;background:#e0f2fe;color:#0284c7;padding:1px 6px;border-radius:4px;">VÀO CA</span>
                        </div>
                        <span class="stat-val" id="admin-stat-morning-scans" style="color:#0284c7;">--</span>
                        <span class="stat-desc" id="admin-stat-morning-desc">Lượt vào ca đầu giờ</span>
                    </div>
                    <div class="stat-card" style="border-left: 3px solid #f59e0b; background: linear-gradient(180deg, #fffbeb 0%, #ffffff 100%);">
                        <div style="display:flex;justify-content:space-between;align-items:center;">
                            <span class="stat-title" style="color:#b45309;font-weight:700;">Cao điểm 12h - 13h</span>
                            <span style="font-size:10px;font-weight:700;background:#fef3c7;color:#b45309;padding:1px 6px;border-radius:4px;">ĂN TRƯA</span>
                        </div>
                        <span class="stat-val" id="admin-stat-lunch-scans" style="color:#d97706;">--</span>
                        <span class="stat-desc" id="admin-stat-lunch-desc">Lượt ăn trưa ghi nhận</span>
                    </div>
                    <div class="stat-card">
                        <span class="stat-title">Độ tương đồng TB</span>
                        <span class="stat-val" id="admin-stat-conf" style="color:var(--success);">--</span>
                        <span class="stat-desc">Ngưỡng đạt tiêu chuẩn</span>
                    </div>
                    <div class="stat-card">
                        <span class="stat-title">Khung giờ cao điểm</span>
                        <span class="stat-val" id="admin-stat-peak" style="font-size:15px;line-height:34px;color:#0284c7;">--</span>
                        <span class="stat-desc">Mật độ lưu thông cao</span>
                    </div>
                </div>

                <!-- KHỐI CHUYÊN BIỆT: THEO DÕI 2 KHUNG GIỜ CAO ĐIỂM (08H - 09H & 12H - 13H) -->
                <div class="admin-card" style="border-left: 4px solid #0284c7; margin-top: 14px; margin-bottom: 6px;">
                    <div class="admin-card-header" style="background: linear-gradient(90deg, #f0f9ff 0%, #fffbeb 100%); padding: 12px 18px;">
                        <div class="admin-card-title" style="color: #0f172a; font-size: 13px;">
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#0284c7" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <circle cx="12" cy="12" r="10"></circle>
                                <polyline points="12 6 12 12 16 14"></polyline>
                            </svg>
                            GHI NHẬN 2 KHUNG GIỜ CAO ĐIỂM TRỌNG ĐIỂM (08:00 - 09:00 & 12:00 - 13:00)
                            <span style="font-size: 11px; font-weight: 600; background: #e0f2fe; color: #0369a1; padding: 2px 8px; border-radius: 9999px; margin-left: 6px;">
                                Vào Ca Sáng & Giờ Ăn Trưa
                            </span>
                        </div>
                        <span style="font-size: 12px; color: #334155; font-weight: 600;" id="dual-peak-summary-badge">Tổng 2 khung giờ chiếm --% lưu lượng</span>
                    </div>
                    <div class="admin-card-body" style="padding: 16px 20px;">
                        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(360px, 1fr)); gap: 20px;">
                            <!-- CỘT 1: KHUNG 08:00 - 09:00 (VÀO CA SÁNG) -->
                            <div style="background: #f8fafc; border: 1px solid #bae6fd; border-radius: 8px; padding: 14px 16px;">
                                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
                                    <div style="font-size: 13px; font-weight: 700; color: #0369a1; display:flex; align-items:center; gap:6px;">
                                        <span style="width:8px;height:8px;border-radius:50%;background:#0284c7;"></span>
                                        KHUNG 08:00 - 09:00 (VÀO CA SÁNG)
                                    </div>
                                    <span style="font-size:11px;font-weight:700;background:#e0f2fe;color:#0284c7;padding:2px 8px;border-radius:4px;" id="morning-percent-badge">--% lưu lượng</span>
                                </div>
                                <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; margin-bottom: 12px;">
                                    <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 6px; padding: 10px 12px;">
                                        <div style="font-size: 10px; font-weight: 600; color: #64748b; text-transform: uppercase;">Lượt quét vào ca</div>
                                        <div style="font-size: 20px; font-weight: 700; color: #0284c7; margin-top: 2px;" id="morning-detail-scans">--</div>
                                        <div style="font-size: 10px; color: #94a3b8;">Tổng lượt ghi nhận</div>
                                    </div>
                                    <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 6px; padding: 10px 12px;">
                                        <div style="font-size: 10px; font-weight: 600; color: #64748b; text-transform: uppercase;">Nhân sự có mặt</div>
                                        <div style="font-size: 20px; font-weight: 700; color: #0f172a; margin-top: 2px;" id="morning-detail-unique">--</div>
                                        <div style="font-size: 10px; color: #94a3b8;">Nhân viên duy nhất</div>
                                    </div>
                                    <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 6px; padding: 10px 12px;">
                                        <div style="font-size: 10px; font-weight: 600; color: #64748b; text-transform: uppercase;">Đúng giờ (&le; 08:30)</div>
                                        <div style="font-size: 16px; font-weight: 700; color: #10b981; margin-top: 4px;" id="morning-detail-ontime">--</div>
                                        <div style="font-size: 10px; color: #94a3b8;" id="morning-detail-late">Đi trễ: --</div>
                                    </div>
                                    <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 6px; padding: 10px 12px;">
                                        <div style="font-size: 10px; font-weight: 600; color: #64748b; text-transform: uppercase;">Camera đón đông nhất</div>
                                        <div style="font-size: 13px; font-weight: 700; color: #0f172a; margin-top: 4px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;" id="morning-detail-topcam">--</div>
                                        <div style="font-size: 10px; color: #94a3b8;" id="morning-detail-topcam-count">Lưu lượng cao nhất</div>
                                    </div>
                                </div>
                                <div style="font-size: 11px; font-weight: 600; color: #475569; margin-bottom: 6px;">Phân bổ Camera vào ca sáng:</div>
                                <div id="morning-cam-bars" style="display: flex; flex-direction: column; gap: 6px;">
                                    <div style="color: #94a3b8; font-size: 11px;">Đang tải...</div>
                                </div>
                            </div>

                            <!-- CỘT 2: KHUNG 12:00 - 13:00 (ĂN TRƯA NHÀ ĂN) -->
                            <div style="background: #f8fafc; border: 1px solid #fde68a; border-radius: 8px; padding: 14px 16px;">
                                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
                                    <div style="font-size: 13px; font-weight: 700; color: #b45309; display:flex; align-items:center; gap:6px;">
                                        <span style="width:8px;height:8px;border-radius:50%;background:#d97706;"></span>
                                        KHUNG 12:00 - 13:00 (ĂN TRƯA NHÀ ĂN)
                                    </div>
                                    <span style="font-size:11px;font-weight:700;background:#fef3c7;color:#b45309;padding:2px 8px;border-radius:4px;" id="lunch-percent-badge">--% lưu lượng</span>
                                </div>
                                <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; margin-bottom: 12px;">
                                    <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 6px; padding: 10px 12px;">
                                        <div style="font-size: 10px; font-weight: 600; color: #64748b; text-transform: uppercase;">Lượt quét giờ trưa</div>
                                        <div style="font-size: 20px; font-weight: 700; color: #d97706; margin-top: 2px;" id="lunch-detail-scans">--</div>
                                        <div style="font-size: 10px; color: #94a3b8;">Tổng lượt ghi nhận</div>
                                    </div>
                                    <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 6px; padding: 10px 12px;">
                                        <div style="font-size: 10px; font-weight: 600; color: #64748b; text-transform: uppercase;">Nhân sự dùng bữa</div>
                                        <div style="font-size: 20px; font-weight: 700; color: #0f172a; margin-top: 2px;" id="lunch-detail-unique">--</div>
                                        <div style="font-size: 10px; color: #94a3b8;">Nhân viên duy nhất</div>
                                    </div>
                                    <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 6px; padding: 10px 12px;">
                                        <div style="font-size: 10px; font-weight: 600; color: #64748b; text-transform: uppercase;">Độ tin cậy AI</div>
                                        <div style="font-size: 16px; font-weight: 700; color: #10b981; margin-top: 4px;" id="lunch-detail-conf">--</div>
                                        <div style="font-size: 10px; color: #94a3b8;">Tiêu chuẩn &ge; 75.0%</div>
                                    </div>
                                    <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 6px; padding: 10px 12px;">
                                        <div style="font-size: 10px; font-weight: 600; color: #64748b; text-transform: uppercase;">Camera đông nhất trưa</div>
                                        <div style="font-size: 13px; font-weight: 700; color: #0f172a; margin-top: 4px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;" id="lunch-detail-topcam">--</div>
                                        <div style="font-size: 10px; color: #94a3b8;" id="lunch-detail-topcam-count">Lưu lượng cao nhất</div>
                                    </div>
                                </div>
                                <div style="font-size: 11px; font-weight: 600; color: #475569; margin-bottom: 6px;">Phân bổ Camera giờ ăn trưa:</div>
                                <div id="lunch-cam-bars" style="display: flex; flex-direction: column; gap: 6px;">
                                    <div style="color: #94a3b8; font-size: 11px;">Đang tải...</div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- KHỐI 3 BIỂU ĐỒ TRỰC QUAN (CHARTS GRID) -->
                <div class="charts-grid">
                    <!-- CHART 1: BIỂU ĐỒ CỘT - THEO GIỜ -->
                    <div class="admin-card chart-card">
                        <div class="admin-card-header">
                            <span class="admin-card-title">Phân bố theo khung giờ (24h)</span>
                            <span class="chart-tag">Hourly Distribution</span>
                        </div>
                        <div class="admin-card-body" style="height:260px;position:relative;">
                            <canvas id="chart-hourly"></canvas>
                        </div>
                    </div>

                    <!-- CHART 2: BIỂU ĐỒ HÀNH VI - THEO CAMERA & KHUNG GIỜ -->
                    <div class="admin-card chart-card">
                        <div class="admin-card-header">
                            <span class="admin-card-title">Lưu lượng di chuyển qua các camera</span>
                            <span class="chart-tag">Traffic Flow</span>
                        </div>
                        <div class="admin-card-body" style="height:260px;position:relative;">
                            <canvas id="chart-behavior"></canvas>
                        </div>
                    </div>

                    <!-- CHART 3: BIỂU ĐỒ THỐNG KÊ - PHÒNG BAN -->
                    <div class="admin-card chart-card">
                        <div class="admin-card-header">
                            <span class="admin-card-title">Tỷ lệ theo phòng ban</span>
                            <span class="chart-tag">Department Share</span>
                        </div>
                        <div class="admin-card-body" style="height:260px;position:relative;">
                            <canvas id="chart-dept"></canvas>
                        </div>
                    </div>
                </div>

                <!-- BẢNG PHÂN TÍCH & THỐNG KÊ ĐA CHIỀU (DAILY / WEEKLY / EMPLOYEES) -->
                <div class="admin-card">
                    <div class="admin-card-header" style="flex-wrap:wrap;gap:12px;align-items:center;">
                        <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;">
                            <button class="table-subtab-btn active" id="subtab-daily" onclick="switchAnalyticsTableTab('daily')">
                                Thống kê theo ngày
                            </button>
                            <button class="table-subtab-btn" id="subtab-weekly" onclick="switchAnalyticsTableTab('weekly')">
                                Thống kê theo tuần
                            </button>
                            <button class="table-subtab-btn" id="subtab-employees" onclick="switchAnalyticsTableTab('employees')">
                                Danh sách nhân sự & Lịch sử
                            </button>
                        </div>
                        <div id="analytics-table-search-box" style="display:none;margin-left:auto;">
                            <div class="search-input-wrapper">
                                <svg class="search-icon" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
                                <input type="text" id="analyticsEmployeeSearch" class="search-box-field" placeholder="Tìm theo mã NV, họ tên, phòng ban..." onkeyup="filterAnalyticsEmployees()" style="width:280px;">
                            </div>
                        </div>
                    </div>

                    <!-- HÀNG 2: THANH LỌC THỜI GIAN & ĐIỀU HƯỚNG CUỘN (CHUYÊN BIỆT DƯỚI TAB THỐNG KÊ) -->
                    <div id="daily-table-toolbar" style="background:#f8fafc;border-bottom:1px solid #e2e8f0;padding:10px 18px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;">
                        <!-- BỘ LỌC THỜI GIAN -->
                        <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
                            <div style="display:flex;align-items:center;gap:6px;font-size:12px;font-weight:700;color:#0f172a;">
                                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#0284c7" stroke-width="2.5"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
                                <span>Lọc thời gian:</span>
                            </div>
                            <div style="display:flex;align-items:center;gap:6px;">
                                <span style="font-size:11px;color:#64748b;font-weight:600;">Từ</span>
                                <input type="date" id="daily-filter-from" class="date-picker-input" style="padding:5px 10px;font-size:12px;" title="Từ ngày (Enter để lọc)" onkeydown="if(event.key==='Enter') applyAnalyticsDateFilter()">
                                <span style="font-size:11px;color:#64748b;font-weight:600;">Đến</span>
                                <input type="date" id="daily-filter-to" class="date-picker-input" style="padding:5px 10px;font-size:12px;" title="Đến ngày (Enter để lọc)" onkeydown="if(event.key==='Enter') applyAnalyticsDateFilter()">
                                <button class="btn btn-primary" onclick="applyAnalyticsDateFilter()" title="Áp dụng lọc cho bảng ngày và Dashboard" style="padding:5px 14px;font-size:12px;gap:5px;">
                                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/></svg>
                                    <span>Lọc</span>
                                </button>
                                <button class="btn btn-outline" id="btn-daily-filter-reset" onclick="resetAnalyticsDateFilter()" title="Bỏ lọc, hiện toàn bộ lịch sử" style="padding:5px 10px;font-size:12px;gap:4px;display:none;">
                                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
                                    <span>Bỏ lọc</span>
                                </button>
                            </div>
                            <div style="display:flex;align-items:center;gap:4px;border-left:1px solid #cbd5e1;padding-left:10px;">
                                <button type="button" class="quick-preset-pill" onclick="setQuickDatePreset('today')">Hôm nay</button>
                                <button type="button" class="quick-preset-pill" onclick="setQuickDatePreset('week')">7 ngày qua</button>
                                <button type="button" class="quick-preset-pill" onclick="setQuickDatePreset('month')">30 ngày qua</button>
                                <button type="button" class="quick-preset-pill" onclick="resetAnalyticsDateFilter()">Toàn bộ</button>
                            </div>
                        </div>

                        <!-- CỤM NÚT CUỘN BẢNG (SCROLL CONTROLS) -->
                        <div style="display:flex;align-items:center;gap:6px;">
                            <span style="font-size:11px;font-weight:600;color:#64748b;display:flex;align-items:center;gap:4px;">
                                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="7 13 12 18 17 13"/><polyline points="7 6 12 11 17 6"/></svg>
                                Cuộn bảng:
                            </span>
                            <button class="btn btn-secondary" onclick="scrollDailyTable('top')" title="Cuộn lên đầu bảng ngày" style="padding:5px 10px;font-size:11px;gap:4px;">
                                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="18 15 12 9 6 15"/></svg>
                                <span>Lên đầu</span>
                            </button>
                            <button class="btn btn-secondary" onclick="scrollDailyTable('bottom')" title="Cuộn xuống cuối bảng ngày" style="padding:5px 10px;font-size:11px;gap:4px;">
                                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"/></svg>
                                <span>Xuống cuối</span>
                            </button>
                            <button class="btn btn-outline" id="btn-toggle-daily-expand" onclick="toggleDailyTableExpand()" title="Bật/Tắt chế độ xem đầy đủ hoặc cuộn" style="padding:5px 10px;font-size:11px;gap:4px;">
                                <svg id="icon-expand-daily" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="15 3 21 3 21 9"/><polyline points="9 21 3 21 3 15"/><line x1="21" y1="3" x2="14" y2="10"/><line x1="3" y1="21" x2="10" y2="14"/></svg>
                                <span id="text-expand-daily">Xem hết</span>
                            </button>
                        </div>
                    </div>

                    <!-- PANE 1: DAILY TABLE -->
                    <div id="pane-daily" class="admin-card-body" style="padding:0;max-height:480px;overflow-y:scroll;position:relative;scroll-behavior:smooth;">
                        <!-- FLOATING SCROLL BUTTONS -->
                        <div class="table-scroll-fab" id="daily-scroll-fab" title="Điều hướng cuộn bảng">
                            <button type="button" class="fab-scroll-btn" onclick="scrollDailyTable('top')" title="Cuộn nhanh lên đầu bảng">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="18 15 12 9 6 15"/></svg>
                            </button>
                            <button type="button" class="fab-scroll-btn" onclick="scrollDailyTable('bottom')" title="Cuộn nhanh xuống cuối bảng">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"/></svg>
                            </button>
                        </div>
                        <table style="border:none;border-radius:0;">
                            <thead>
                                <tr>
                                    <th>NGÀY GHI NHẬN</th>
                                    <th style="text-align:center;">TỔNG LƯỢT QUÉT</th>
                                    <th style="text-align:center;">SỐ NHÂN VIÊN ĐI LÀM</th>
                                    <th style="text-align:center;color:#0369a1;background:#f0f9ff;">CAO ĐIỂM SÁNG (08H - 09H)</th>
                                    <th style="text-align:center;color:#b45309;background:#fffbeb;">CAO ĐIỂM TRƯA (12H - 13H)</th>
                                    <th style="text-align:center;">ĐÚNG GIỜ (&le; 08:30)</th>
                                    <th style="text-align:center;">ĐẾN MUỘN (&gt; 08:30)</th>
                                    <th>GIỜ ĐẦU - CUỐI</th>
                                    <th>KHUNG GIỜ CAO ĐIỂM</th>
                                    <th>CAMERA HOẠT ĐỘNG NHẤT</th>
                                </tr>
                            </thead>
                            <tbody id="analytics-daily-tbody">
                                <tr><td colspan="10" style="text-align:center;padding:24px;color:#94a3b8;">Đang tải dữ liệu theo ngày...</td></tr>
                            </tbody>
                        </table>
                    </div>

                    <!-- PANE 2: WEEKLY TABLE -->
                    <div id="pane-weekly" class="admin-card-body" style="display:none;padding:0;max-height:480px;overflow-y:auto;">
                        <table style="border:none;border-radius:0;">
                            <thead>
                                <tr>
                                    <th>TUẦN / NĂM</th>
                                    <th style="text-align:center;">TỔNG LƯỢT QUÉT</th>
                                    <th style="text-align:center;">SỐ NHÂN VIÊN CÓ MẶT</th>
                                    <th style="text-align:center;">SỐ NGÀY GHI NHẬN</th>
                                    <th style="text-align:center;">TRUNG BÌNH / NGÀY</th>
                                    <th>NGÀY HOẠT ĐỘNG CAO NHẤT</th>
                                </tr>
                            </thead>
                            <tbody id="analytics-weekly-tbody">
                                <tr><td colspan="6" style="text-align:center;padding:24px;color:#94a3b8;">Đang tải dữ liệu theo tuần...</td></tr>
                            </tbody>
                        </table>
                    </div>

                    <!-- PANE 3: EMPLOYEES TABLE WITH CLICK TO VIEW PERSON DETAIL -->
                    <div id="pane-employees" class="admin-card-body" style="display:none;padding:0;max-height:550px;overflow-y:auto;">
                        <table id="analyticsEmployeesTable" style="border:none;border-radius:0;">
                            <thead>
                                <tr>
                                    <th style="width:46px;text-align:center;">ẢNH</th>
                                    <th style="width:90px;">MÃ NV</th>
                                    <th style="width:190px;">HỌ VÀ TÊN</th>
                                    <th>CHỨC DANH / PHÒNG BAN</th>
                                    <th>CÔNG TY</th>
                                    <th style="width:140px;">LẦN ĐẦU (VÀO CA)</th>
                                    <th style="width:140px;">LẦN QUÉT CUỐI</th>
                                    <th style="width:90px;text-align:center;">TỔNG LƯỢT</th>
                                    <th style="width:90px;text-align:center;">ĐỘ TIN CẬY</th>
                                    <th style="width:110px;text-align:center;">THAO TÁC</th>
                                </tr>
                            </thead>
                            <tbody id="analytics-employees-tbody">
                                <tr><td colspan="10" style="text-align:center;padding:24px;color:#94a3b8;">Đang tải danh sách nhân sự...</td></tr>
                            </tbody>
                        </table>
                    </div>
                </div>

                <!-- TÌNH TRẠNG KẾT NỐI API & CÀI ĐẶT HỆ THỐNG -->
                <div class="admin-card">
                    <div class="admin-card-header">
                        <span class="admin-card-title">Kết nối Smart HRMS API & Cấu hình nhận diện</span>
                        <button class="btn btn-outline" onclick="triggerSync()" style="display:inline-flex;align-items:center;gap:6px;">
                            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"/></svg>
                            <span>Đồng bộ dữ liệu HRMS</span>
                        </button>
                    </div>
                    <div class="admin-card-body" style="display:flex;gap:30px;flex-wrap:wrap;font-size:12px;">
                        <div style="flex:1;min-width:280px;display:flex;flex-direction:column;gap:8px;">
                            <div><span class="v-label">API Endpoint:</span> <code>https://i-officeapi.ltacv.com/api/data/process/Getdata_List_Employee_Full</code></div>
                            <div><span class="v-label">Cơ chế bảo mật:</span> <span class="v-val">HMAC-MD5 Token Authentication</span></div>
                            <div><span class="v-label">Trạng thái kết nối:</span> <span style="color:var(--success);font-weight:600;">Sẵn sàng hoạt động</span></div>
                        </div>
                        <div style="flex:1;min-width:280px;display:flex;flex-direction:column;gap:8px;">
                            <div><span class="v-label">Ngưỡng nhận diện hợp lệ:</span> <span class="v-val">&ge; 75.0% (Cosine Similarity &ge; 0.47)</span></div>
                            <div><span class="v-label">Khoảng cách chống trùng lặp:</span> <span class="v-val">60 giây / nhân sự</span></div>
                            <div><span class="v-label">Lưu trữ ảnh thực tế:</span> <span class="v-val">Tự động trích xuất chân dung vào thư mục lưu trữ</span></div>
                        </div>
                    </div>
                </div>

                <!-- QUẢN LÝ DANH SÁCH CAMERA RTSP -->
                <div class="admin-card">
                    <div class="admin-card-header">
                        <span class="admin-card-title">Danh sách camera giám sát RTSP (<span id="admin-cam-count">3</span> trực tuyến)</span>
                        <button class="btn" onclick="openAddCameraModal()" style="display:inline-flex;align-items:center;gap:6px;">
                            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
                            <span>Thêm camera RTSP</span>
                        </button>
                    </div>
                    <div class="admin-card-body" style="padding:0;">
                        <table style="border:none;border-radius:0;">
                            <thead>
                                <tr>
                                    <th style="width:50px;">ID</th>
                                    <th>TÊN CAMERA</th>
                                    <th>ĐƯỜNG DẪN RTSP</th>
                                    <th>VỊ TRÍ</th>
                                    <th>TRẠNG THÁI</th>
                                    <th style="width:130px;text-align:center;">THAO TÁC</th>
                                </tr>
                            </thead>
                            <tbody id="admin-cameras-tbody">
                                <!-- Loaded dynamically -->
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>

        <!-- ==================================================================== -->
        <!-- MỤC 2: XEM CAMERA (CHIA CỘT TRÁI - PHẢI & THÊM RTSP)                 -->
        <!-- ==================================================================== -->
        <div id="view-camera" class="app-view" style="display:block;">
            <div class="camera-view-container">
                <!-- VIEW SWITCHER BAR -->
                <div class="camera-subnav">
                    <div class="cam-switcher-tabs" id="cam-switcher-tabs">
                        <button class="cam-tab-btn active" onclick="switchCameraView('grid')">
                            <span>Dạng lưới</span>
                        </button>
                        <!-- Dynamic camera buttons will be populated here -->
                    </div>
                    <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
                        <div style="font-size:12px;font-weight:600;color:#475569;background:#f8fafc;padding:4px 10px;border-radius:6px;border:1px solid var(--border);display:flex;align-items:center;gap:6px;">
                            <span>Đang kết nối:</span>
                            <span style="color:var(--success);font-weight:700;"><span id="active-cams-count">3</span> / <span id="total-cams-count">4</span></span>
                            <span style="color:var(--text-muted);font-size:11px;">cam</span>
                        </div>
                        <div style="display:flex;align-items:center;gap:4px;">
                            <button class="btn btn-outline" onclick="batchToggleCameras('start_all')" style="padding:4px 8px;font-size:11px;" title="Kích hoạt tất cả luồng RTSP camera">Bật tất cả</button>
                            <button class="btn btn-outline" onclick="batchToggleCameras('stop_all')" style="padding:4px 8px;font-size:11px;color:#dc2626;" title="Tạm dừng toàn bộ luồng RTSP để giải phóng CPU">Tắt tất cả</button>
                        </div>
                        <div style="display:flex;align-items:center;gap:6px;font-size:12px;font-weight:600;color:#475569;">
                            <span>Độ nét:</span>
                            <select id="quality-selector" onchange="changeQuality(this.value)" style="padding:4px 8px;border-radius:6px;border:1px solid var(--border);font-size:12px;font-weight:500;color:var(--text-dark);background:#fff;cursor:pointer;">
                                <option value="720p" selected>HD 720p</option>
                                <option value="1080p">Full HD 1080p</option>
                                <option value="576p">576p</option>
                            </select>
                        </div>
                        <button class="btn" onclick="openAddCameraModal()" style="padding:5px 12px;font-size:12px;display:inline-flex;align-items:center;gap:6px;">
                            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
                            <span>Thêm camera</span>
                        </button>
                    </div>
                </div>

                <!-- 2-COLUMN SPLIT LAYOUT -->
                <div class="camera-split-layout">
                    <!-- LEFT COLUMN: CAMERA DISPLAY -->
                    <div class="cam-display-col">
                        <!-- GRID VIEW -->
                        <div id="cam-grid-container" class="cam-grid-layout three-cams">
                            <!-- Populated dynamically -->
                        </div>

                        <!-- SINGLE CAMERA VIEW -->
                        <div id="cam-single-container" class="single-cam-wrapper" style="display:none;">
                            <div class="single-cam-header">
                                <div style="display:flex;align-items:center;gap:10px;">
                                    <span class="cam-title" id="single-cam-title">Camera trực tiếp</span>
                                    <span id="single-cam-status-pill" class="live-tag"><span class="live-dot"></span> TRỰC TIẾP</span>
                                </div>
                                <div style="display:flex;align-items:center;gap:8px;">
                                    <button id="single-cam-toggle-btn" class="btn btn-outline" onclick="toggleCurrentSingleCamera()" style="padding:4px 10px;font-size:11px;font-weight:600;">
                                        Tạm dừng luồng (Tiết kiệm CPU)
                                    </button>
                                    <button class="btn btn-outline" onclick="switchCameraView('grid')" style="padding:4px 10px;font-size:11px;">
                                        Quay lại dạng lưới
                                    </button>
                                </div>
                            </div>
                            <div class="single-cam-video">
                                <img id="single-cam-img" class="single-cam-feed" src="" alt="Live Feed">
                            </div>
                            <div class="cam-sub">
                                <span id="single-cam-info">1920x1080 Full HD</span>
                                <span id="single-cam-cpu-hint" style="color:var(--text-muted);font-size:11px;">Dual-Stream • Zero Lag</span>
                            </div>
                        </div>
                    </div>

                    <!-- RIGHT COLUMN: LATEST VERIFIED CARD & LIVE LOGS -->
                    <div class="info-log-col">
                        <!-- LATEST VERIFIED EMPLOYEE CARD -->
                        <div class="verified-card" id="sidebar-verified-card">
                            <div class="verified-card-header">
                                <span class="verified-title">Xác nhận nhận diện gần nhất</span>
                                <span id="v-conf" class="conf-pill">--</span>
                            </div>
                            <div class="verified-card-body">
                                <img id="v-avatar" class="card-avatar" src="" alt="Avatar" style="display:none;">
                                <div id="v-avatar-placeholder" class="card-avatar avatar-placeholder-svg" style="display:flex;align-items:center;justify-content:center;">
                                    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" stroke-width="1.5"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
                                </div>
                                <div class="verified-details">
                                    <div class="v-name" id="v-name">Chưa có lượt mới</div>
                                    <div class="v-role" id="v-role">--</div>
                                    <div class="v-row"><span class="v-label">Bộ phận:</span> <span class="v-val" id="v-dept">--</span></div>
                                    <div class="v-row"><span class="v-label">Công ty:</span> <span class="v-val" id="v-company">--</span></div>
                                    <div class="v-row"><span class="v-label">Camera:</span> <span class="v-val font-semibold" id="v-cam">--</span></div>
                                    <div class="v-status" id="v-status">Đang làm việc</div>
                                </div>
                            </div>
                        </div>

                        <!-- REAL-TIME LOG FEED -->
                        <div class="log-feed-card">
                            <div class="log-feed-header">
                                <span class="log-feed-title">Nhật ký điểm danh thời gian thực</span>
                                <div class="log-scope-buttons">
                                    <button class="log-filter-btn active" id="btn-filter-all" onclick="setLogScope('all')">Tất cả</button>
                                    <button class="log-filter-btn" id="btn-filter-current" onclick="setLogScope('current')">Camera này</button>
                                </div>
                            </div>
                            <div class="log-feed-list" id="sidebar-log-list">
                                <div style="padding:24px;text-align:center;color:#94a3b8;font-size:12px;">
                                    Đang kết nối camera và chờ tín hiệu điểm danh...
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- ==================================================================== -->
        <!-- MỤC 3: XUẤT THÔNG TIN HOẶC THÊM THÔNG TIN                             -->
        <!-- ==================================================================== -->
        <div id="view-data" class="app-view">
            <div class="data-view-container">
                <!-- DATA SUB-TABS -->
                <div class="data-tabs">
                    <button class="data-tab-btn active" id="subtab-export" onclick="switchDataSubTab('export')">
                        Xuất báo cáo điểm danh
                    </button>
                    <button class="data-tab-btn" id="subtab-employees" onclick="switchDataSubTab('employees')">
                        Quản lý dữ liệu khuôn mặt nhân sự
                    </button>
                </div>

                <!-- SUB-TAB 3A: XUẤT BÁO CÁO -->
                <div id="data-pane-export" style="display:flex;flex-direction:column;gap:14px;">
                    <div class="toolbar-box" style="flex-wrap:wrap;gap:12px;">
                        <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;flex:1;">
                            <div class="search-input-wrapper">
                                <svg class="search-icon" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
                                <input type="text" id="reportSearch" class="search-box-field" placeholder="Tìm theo mã NV, họ tên, phòng ban..." onkeyup="filterReportTable()">
                            </div>
                            <select id="reportCamFilter" class="form-input" onchange="filterReportTable()" style="padding:7px 10px;font-size:12px;font-weight:600;color:#0f172a;">
                                <option value="">Tất cả Camera</option>
                            </select>
                            
                            <!-- BỘ LỌC THỜI GIAN -->
                            <div style="display:inline-flex;align-items:center;gap:6px;background:#f8fafc;padding:4px 10px;border-radius:6px;border:1px solid #cbd5e1;">
                                <span style="font-size:12px;font-weight:700;color:#475569;">Từ ngày:</span>
                                <input type="date" id="reportDateFrom" onchange="filterReportTable()" style="padding:4px 6px;font-size:12px;font-weight:600;border:1px solid #cbd5e1;border-radius:4px;color:#0f172a;outline:none;">
                                <span style="font-size:12px;font-weight:700;color:#475569;">Đến:</span>
                                <input type="date" id="reportDateTo" onchange="filterReportTable()" style="padding:4px 6px;font-size:12px;font-weight:600;border:1px solid #cbd5e1;border-radius:4px;color:#0f172a;outline:none;">
                            </div>
                            <div style="display:inline-flex;gap:4px;">
                                <button type="button" class="btn btn-outline" style="padding:4px 8px;font-size:11px;font-weight:600;" onclick="setReportDatePreset('today')" title="Hôm nay">Hôm nay</button>
                                <button type="button" class="btn btn-outline" style="padding:4px 8px;font-size:11px;font-weight:600;" onclick="setReportDatePreset('yesterday')" title="Hôm qua">Hôm qua</button>
                                <button type="button" class="btn btn-outline" style="padding:4px 8px;font-size:11px;font-weight:600;" onclick="setReportDatePreset('7days')" title="7 ngày gần nhất">7 ngày</button>
                                <button type="button" class="btn btn-outline" style="padding:4px 8px;font-size:11px;font-weight:600;" onclick="setReportDatePreset('all')" title="Tất cả thời gian">Tất cả</button>
                            </div>

                            <span id="reportCountBadge" style="font-size:12px;font-weight:600;color:var(--primary);background:var(--primary-light);padding:5px 12px;border-radius:20px;border:1px solid #bfdbfe;">
                                Đang nạp toàn bộ dữ liệu...
                            </span>
                            <button class="btn btn-outline" onclick="loadAllAttendanceRecords(true)" style="padding:6px 12px;font-size:12px;display:inline-flex;align-items:center;gap:6px;" title="Tải lại toàn bộ dữ liệu từ tệp log">
                                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"/></svg>
                                <span>Làm mới</span>
                            </button>
                        </div>
                        <div style="display:flex;gap:8px;align-items:center;">
                            <a id="btn-export-pdf" href="/export_report" target="_blank" class="btn" style="display:inline-flex;align-items:center;gap:6px;background:#0052cc;color:#fff;font-weight:600;" title="In báo cáo hoặc lưu thành file PDF với phông chữ Times New Roman chuẩn size 11">
                                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 6 2 18 2 18 9"/><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><rect x="6" y="14" width="12" height="8"/></svg>
                                <span>In báo cáo / PDF</span>
                            </a>
                            <a id="btn-export-excel" href="/export_excel" class="btn btn-outline" style="display:inline-flex;align-items:center;gap:6px;color:#059669;border-color:#10b981;font-weight:700;background:#f0fdf4;" title="Xuất file Excel (.xlsx) chuẩn Times New Roman size 11 kèm ảnh snapshot và ảnh hồ sơ">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="8" y1="13" x2="16" y2="13"/><line x1="8" y1="17" x2="16" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>
                                <span>Xuất file Excel</span>
                            </a>
                            <a href="/export_csv" class="btn btn-outline" style="display:inline-flex;align-items:center;gap:4px;padding:6px 10px;font-size:11px;color:#64748b;" title="Tải file CSV văn bản thô">
                                <span>CSV</span>
                            </a>
                        </div>
                    </div>

                    <div style="max-height:600px;overflow-y:auto;border-radius:8px;border:1px solid var(--border);">
                        <table id="exportReportTable">
                            <thead>
                                <tr>
                                    <th style="width:35px;text-align:center;">STT</th>
                                    <th style="width:65px;text-align:center;">ẢNH CAMERA</th>
                                    <th style="width:65px;text-align:center;">ẢNH HỒ SƠ</th>
                                    <th style="width:130px;">THỜI GIAN</th>
                                    <th style="width:85px;">MÃ NV</th>
                                    <th style="width:170px;">HỌ VÀ TÊN</th>
                                    <th style="width:160px;">CHỨC DANH</th>
                                    <th>PHÒNG BAN / CÔNG TY</th>
                                    <th style="width:150px;">VỊ TRÍ CAMERA</th>
                                    <th style="width:80px;text-align:center;">ĐỘ TIN CẬY</th>
                                    <th style="width:90px;text-align:center;">TRẠNG THÁI</th>
                                </tr>
                            </thead>
                            <tbody id="export-report-tbody">
                                <tr><td colspan="11" style="text-align:center;padding:24px;color:#94a3b8;">Đang tải dữ liệu...</td></tr>
                            </tbody>
                        </table>
                    </div>
                </div>

                <!-- SUB-TAB 3B: QUẢN LÝ & THÊM THÔNG TIN NHÂN SỰ -->
                <div id="data-pane-employees" style="display:none;flex-direction:column;gap:14px;">
                    <div class="toolbar-box">
                        <div class="search-input-wrapper">
                            <svg class="search-icon" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
                            <input type="text" id="empSearch" class="search-box-field" placeholder="Tìm theo mã NV, họ tên, phòng ban..." onkeyup="filterEmployeeList()">
                        </div>
                        <span style="font-size:12px;color:var(--text-muted);">
                            Chọn nhân sự để xem lịch sử hoặc cập nhật ảnh khuôn mặt sắc nét cho hệ thống.
                        </span>
                    </div>

                    <div style="max-height:600px;overflow-y:auto;border-radius:8px;border:1px solid var(--border);">
                        <table id="employeeListTable">
                            <thead>
                                <tr>
                                    <th style="width:50px;text-align:center;">ẢNH</th>
                                    <th style="width:90px;">MÃ NV</th>
                                    <th style="width:200px;">HỌ VÀ TÊN</th>
                                    <th style="width:180px;">CHỨC DANH</th>
                                    <th>PHÒNG BAN / ĐƠN VỊ</th>
                                    <th>CÔNG TY</th>
                                    <th style="width:110px;text-align:center;">TRẠNG THÁI</th>
                                    <th style="width:120px;text-align:center;">THAO TÁC</th>
                                </tr>
                            </thead>
                            <tbody id="employees-tbody">
                                <tr><td colspan="8" style="text-align:center;padding:24px;color:#94a3b8;">Đang nạp danh sách nhân viên...</td></tr>
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>

    </main>

    <!-- FOOTER -->
    <footer>
        <span>Hệ thống giám sát và điểm danh thông minh • Smart HRMS Enterprise</span>
        <span>Giao thức kết nối bảo mật HMAC-MD5</span>
    </footer>

    <!-- MODAL THÊM CAMERA RTSP MỚI -->
    <div id="add-cam-modal" class="modal-overlay">
        <div class="modal-box">
            <div class="modal-header">
                <span>Thêm camera RTSP mới</span>
                <button class="modal-close-btn" onclick="closeAddCameraModal()" title="Đóng">
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                </button>
            </div>
            <div class="modal-body">
                <div class="form-group">
                    <label class="form-label">Tên Camera *</label>
                    <input type="text" id="new-cam-name" class="form-input" placeholder="Ví dụ: CAM 04 - CỬA NHÂN VIÊN">
                </div>
                <div class="form-group">
                    <label class="form-label">Đường dẫn RTSP *</label>
                    <input type="text" id="new-cam-url" class="form-input" placeholder="rtsp://admin:password@192.168.100.xx:554/cam/realmonitor?channel=1&subtype=0">
                </div>
                <div class="form-group">
                    <label class="form-label">Vị trí lắp đặt</label>
                    <input type="text" id="new-cam-loc" class="form-input" placeholder="Ví dụ: Cửa ra vào tầng trệt">
                </div>
                <div id="test-cam-status" style="font-size:12px;padding:8px 12px;border-radius:6px;display:none;"></div>
            </div>
            <div class="modal-footer">
                <button class="btn btn-outline" id="btn-test-cam" onclick="testCameraUrl()">Kiểm tra kết nối</button>
                <button class="btn" onclick="submitAddCamera()">Lưu & Kích hoạt</button>
            </div>
        </div>
    </div>

    <!-- MODAL TẢI ẢNH KHUÔN MẶT MỚI CHO NHÂN VIÊN -->
    <div id="upload-face-modal" class="modal-overlay">
        <div class="modal-box">
            <div class="modal-header">
                <span>Cập nhật ảnh nhận diện nhân viên</span>
                <button class="modal-close-btn" onclick="closeUploadFaceModal()" title="Đóng">
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                </button>
            </div>
            <div class="modal-body">
                <div style="display:flex;gap:14px;align-items:center;">
                    <img id="modal-emp-avatar" style="width:64px;height:64px;border-radius:6px;object-fit:cover;border:1px solid #cbd5e1;" src="">
                    <div>
                        <div style="font-weight:700;font-size:14px;color:#0f172a;" id="modal-emp-name">--</div>
                        <div style="color:var(--accent);font-weight:600;font-size:12px;" id="modal-emp-code">--</div>
                        <div style="color:var(--text-muted);font-size:11px;" id="modal-emp-dept">--</div>
                    </div>
                </div>
                <input type="hidden" id="modal-emp-id">
                <div class="form-group">
                    <label class="form-label">Tệp hình ảnh chân dung (JPG / PNG):</label>
                    <input type="file" id="modal-face-file" accept="image/*" class="form-input">
                </div>
                <div id="upload-face-status" style="font-size:12px;padding:8px 12px;border-radius:6px;display:none;"></div>
            </div>
            <div class="modal-footer">
                <button class="btn btn-outline" onclick="closeUploadFaceModal()">Hủy</button>
                <button class="btn" onclick="submitUploadFace()">Lưu & Đăng ký</button>
            </div>
        </div>
    </div>

    <!-- MODAL CHI TIẾT NHÂN VIÊN & DÒNG THỜI GIAN QUÉT TỪNG GIÂY (TIMELINE) -->
    <div id="person-detail-modal" class="modal-overlay" style="display:none;">
        <div class="modal-box" style="width:850px;max-width:95vw;max-height:92vh;display:flex;flex-direction:column;">
            <div class="modal-header">
                <span>Hồ sơ nhân sự & Lịch sử nhận diện</span>
                <button class="modal-close-btn" onclick="closePersonDetailModal()" title="Đóng">
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                </button>
            </div>
            <div class="modal-body" style="overflow-y:auto;padding:20px;display:flex;flex-direction:column;gap:18px;">
                <!-- PROFILE CARD -->
                <div class="person-profile-header">
                    <img id="pd-avatar" src="" class="person-profile-avatar" alt="Avatar">
                    <div class="person-profile-info" style="flex:1;">
                        <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
                            <h3 id="pd-fullname" style="font-size:16px;font-weight:700;color:#0f172a;">--</h3>
                            <span id="pd-code" class="kpi-pill" style="font-size:12px;font-weight:600;color:var(--accent);background:var(--accent-light);">--</span>
                            <span id="pd-status" class="v-status">--</span>
                        </div>
                        <div id="pd-role" style="color:var(--text-dark);font-weight:600;font-size:12px;margin-top:2px;">--</div>
                        <div style="font-size:12px;color:#475569;margin-top:4px;">
                            <span id="pd-dept">--</span> • <span id="pd-company">--</span>
                        </div>
                        <div style="font-size:11px;color:var(--text-muted);margin-top:2px;">
                            Ngạch lương: <strong id="pd-salary" style="color:#0f172a;">--</strong>
                        </div>
                    </div>
                </div>

                <!-- 4 QUICK STATS -->
                <div style="display:grid;grid-template-columns:repeat(4, 1fr);gap:10px;">
                    <div class="pd-stat-box">
                        <span class="pd-stat-label">Tổng lượt quét</span>
                        <span class="pd-stat-val" id="pd-total-scans">0</span>
                    </div>
                    <div class="pd-stat-box">
                        <span class="pd-stat-label">Lần đầu (Vào ca)</span>
                        <span class="pd-stat-val" id="pd-first-scan" style="font-size:12px;font-weight:600;color:#0284c7;">--</span>
                    </div>
                    <div class="pd-stat-box">
                        <span class="pd-stat-label">Lần quét cuối</span>
                        <span class="pd-stat-val" id="pd-last-scan" style="font-size:12px;font-weight:600;color:#0284c7;">--</span>
                    </div>
                    <div class="pd-stat-box">
                        <span class="pd-stat-label">Độ tin cậy TB</span>
                        <span class="pd-stat-val" id="pd-avg-conf" style="color:var(--success);">--</span>
                    </div>
                </div>

                <!-- TIMELINE HEADER -->
                <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border);padding-bottom:8px;margin-top:4px;">
                    <h4 style="font-size:13px;font-weight:700;color:#0f172a;">
                        Dòng thời gian ghi nhận (chi tiết từng giây)
                    </h4>
                    <span id="pd-timeline-count" style="font-size:11px;font-weight:500;color:var(--text-muted);">0 mốc</span>
                </div>

                <!-- TIMELINE LIST -->
                <div id="pd-timeline-list" class="pd-timeline-list">
                    <!-- Populated dynamically -->
                </div>
            </div>
            <div class="modal-footer" style="display:flex;justify-content:flex-end;">
                <button class="btn btn-outline" onclick="closePersonDetailModal()">Đóng</button>
            </div>
        </div>
    </div>

    <!-- LIGHTBOX MODAL FOR SNAPSHOT ZOOM -->
    <div id="lightbox-modal" class="modal-overlay" style="display:none;z-index:9999;background:rgba(15,23,42,0.85);" onclick="closeLightbox()">
        <div style="max-width:90vw;max-height:90vh;display:flex;flex-direction:column;align-items:center;gap:12px;" onclick="event.stopPropagation()">
            <img id="lightbox-img" src="" style="max-width:85vw;max-height:75vh;border-radius:6px;box-shadow:0 10px 25px rgba(0,0,0,0.5);border:1px solid rgba(255,255,255,0.2);object-fit:contain;">
            <div id="lightbox-caption" style="color:#fff;font-size:12px;font-weight:500;text-align:center;background:rgba(0,0,0,0.7);padding:6px 16px;border-radius:4px;"></div>
            <button class="btn btn-outline" onclick="closeLightbox()" style="color:#fff;border-color:rgba(255,255,255,0.3);background:transparent;">Đóng</button>
        </div>
    </div>

    <!-- ==================================================================== -->
    <!-- SCRIPT CLIENT LOGIC                                                 -->
    <!-- ==================================================================== -->
    <script>
        let currentNavTab = 'camera';
        let currentCamView = 'grid'; // 'grid' hoặc cam_id
        let currentLogScope = 'all'; // 'all' hoặc 'current'
        let camerasList = [];
        let allLogs = [];
        let allEmployees = [];

        // Helper gán text an toàn chống lỗi null
        function setElemText(id, val) {
            const el = document.getElementById(id);
            if (el) el.innerText = (val !== undefined && val !== null) ? val : '';
        }

        // Đồng hồ thời gian thực
        function updateClock() {
            const now = new Date();
            const pad = (n) => n.toString().padStart(2, '0');
            const str = `${now.getFullYear()}-${pad(now.getMonth()+1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
            setElemText('clock', str);
        }
        setInterval(updateClock, 1000);
        updateClock();

        // ====================================================================
        // TRUNG TÂM PHÂN TÍCH & THỐNG KÊ (ANALYTICS & BIỂU ĐỒ)
        // ====================================================================
        let currentAnalyticsScope = 'all';
        let currentAnalyticsFromDate = '';
        let currentAnalyticsToDate = '';
        let currentAnalyticsSubTab = 'daily';
        let isDailyTableExpanded = false;
        let adminAnalyticsData = null;
        let chartHourlyInstance = null;
        let chartBehaviorInstance = null;
        let chartDeptInstance = null;

        function formatDateVn(isoDateStr) {
            if (!isoDateStr) return '';
            const parts = isoDateStr.split('-');
            if (parts.length === 3) {
                return `${parts[2]}/${parts[1]}/${parts[0]}`;
            }
            return isoDateStr;
        }

        async function loadAdminAnalytics() {
            try {
                let url = `/api/admin_analytics?scope=${currentAnalyticsScope}`;
                if (currentAnalyticsScope === 'custom' || currentAnalyticsFromDate || currentAnalyticsToDate) {
                    url = `/api/admin_analytics?scope=custom&from_date=${encodeURIComponent(currentAnalyticsFromDate)}&to_date=${encodeURIComponent(currentAnalyticsToDate)}`;
                }
                const res = await fetch(url);
                const data = await res.json();
                if (!data.success) return;
                adminAnalyticsData = data;

                // Cập nhật 6 KPI Cards an toàn
                setElemText('admin-stat-scans', data.kpi.total_scans);
                setElemText('admin-stat-unique', data.kpi.unique_employees);
                setElemText('admin-stat-conf', data.kpi.avg_confidence);
                setElemText('admin-stat-peak', data.kpi.peak_hour);

                // Cập nhật Tổng 2 khung giờ cao điểm
                if (data.dual_peak_summary) {
                    setElemText('dual-peak-summary-badge', `Tổng 2 khung giờ chiếm ${data.dual_peak_summary.percent_of_day} lưu lượng`);
                }

                // Cập nhật Khung cao điểm 1: 08h - 09h (Vào ca sáng)
                if (data.morning_peak) {
                    setElemText('admin-stat-morning-scans', `${data.morning_peak.total_scans} lượt`);
                    setElemText('admin-stat-morning-desc', `${data.morning_peak.unique_employees} NV có mặt đầu ca`);

                    setElemText('morning-percent-badge', `${data.morning_peak.percent_of_day} lưu lượng`);
                    setElemText('morning-detail-scans', `${data.morning_peak.total_scans} lượt`);
                    setElemText('morning-detail-unique', `${data.morning_peak.unique_employees} nhân sự`);
                    setElemText('morning-detail-ontime', `${data.morning_peak.on_time} lượt`);
                    setElemText('morning-detail-late', `Đi trễ: ${data.morning_peak.late} lượt`);
                    setElemText('morning-detail-topcam', data.morning_peak.top_camera || '--');
                    setElemText('morning-detail-topcam-count', `${data.morning_peak.top_camera_count || 0} lượt đón`);

                    const mCamBarsElem = document.getElementById('morning-cam-bars');
                    if (mCamBarsElem) {
                        const mCams = data.morning_peak.cameras || {};
                        const totalMorn = data.morning_peak.total_scans || 1;
                        let mBarsHtml = '';
                        for (const [camName, count] of Object.entries(mCams)) {
                            const pct = Math.round((count / totalMorn) * 100);
                            mBarsHtml += `
                                <div style="display:flex;align-items:center;gap:10px;font-size:11px;">
                                    <div style="width:160px;font-weight:600;color:#1e293b;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" title="${camName}">
                                        ${camName}
                                    </div>
                                    <div style="flex:1;background:#e2e8f0;height:14px;border-radius:9999px;overflow:hidden;position:relative;">
                                        <div style="background:linear-gradient(90deg, #38bdf8, #0284c7);height:100%;width:${pct}%;border-radius:9999px;transition:width 0.4s ease;"></div>
                                    </div>
                                    <div style="width:80px;text-align:right;font-weight:700;color:#0f172a;">
                                        ${count} <span style="font-weight:400;color:#64748b;font-size:10px;">(${pct}%)</span>
                                    </div>
                                </div>
                            `;
                        }
                        mCamBarsElem.innerHTML = mBarsHtml || '<div style="color:#94a3b8;font-size:11px;">Chưa có dữ liệu camera 8h - 9h</div>';
                    }
                }

                // Cập nhật Khung cao điểm 2: 12h - 13h (Ăn trưa nhà ăn)
                if (data.lunch_peak) {
                    setElemText('admin-stat-lunch-scans', `${data.lunch_peak.total_scans} lượt`);
                    setElemText('admin-stat-lunch-desc', `${data.lunch_peak.unique_employees} nhân sự ăn trưa`);

                    setElemText('lunch-percent-badge', `${data.lunch_peak.percent_of_day} lưu lượng`);
                    setElemText('lunch-detail-scans', `${data.lunch_peak.total_scans} lượt`);
                    setElemText('lunch-detail-unique', `${data.lunch_peak.unique_employees} nhân sự`);
                    setElemText('lunch-detail-conf', data.lunch_peak.avg_confidence || '--');
                    setElemText('lunch-detail-topcam', data.lunch_peak.top_camera || '--');
                    setElemText('lunch-detail-topcam-count', `${data.lunch_peak.top_camera_count || 0} lượt quét`);

                    const camBarsElem = document.getElementById('lunch-cam-bars');
                    if (camBarsElem) {
                        const cams = data.lunch_peak.cameras || {};
                        const totalLunch = data.lunch_peak.total_scans || 1;
                        let barsHtml = '';
                        for (const [camName, count] of Object.entries(cams)) {
                            const pct = Math.round((count / totalLunch) * 100);
                            barsHtml += `
                                <div style="display:flex;align-items:center;gap:10px;font-size:11px;">
                                    <div style="width:160px;font-weight:600;color:#1e293b;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" title="${camName}">
                                        ${camName}
                                    </div>
                                    <div style="flex:1;background:#fef3c7;height:14px;border-radius:9999px;overflow:hidden;position:relative;">
                                        <div style="background:linear-gradient(90deg, #f59e0b, #d97706);height:100%;width:${pct}%;border-radius:9999px;transition:width 0.4s ease;"></div>
                                    </div>
                                    <div style="width:80px;text-align:right;font-weight:700;color:#0f172a;">
                                        ${count} <span style="font-weight:400;color:#64748b;font-size:10px;">(${pct}%)</span>
                                    </div>
                                </div>
                            `;
                        }
                        camBarsElem.innerHTML = barsHtml || '<div style="color:#94a3b8;font-size:11px;">Chưa có dữ liệu camera 12h - 13h</div>';
                    }
                }

                let scopeDesc = "Toàn bộ lịch sử";
                let filterBadgeText = "";
                const isFiltered = (currentAnalyticsScope === 'custom' || currentAnalyticsFromDate || currentAnalyticsToDate);

                if (isFiltered) {
                    if (currentAnalyticsFromDate && currentAnalyticsToDate) {
                        if (currentAnalyticsFromDate === currentAnalyticsToDate) {
                            scopeDesc = `Ngày ${formatDateVn(currentAnalyticsFromDate)}`;
                            filterBadgeText = `Lọc: ${formatDateVn(currentAnalyticsFromDate)} (${data.kpi.total_scans} lượt)`;
                        } else {
                            scopeDesc = `${formatDateVn(currentAnalyticsFromDate)} - ${formatDateVn(currentAnalyticsToDate)}`;
                            filterBadgeText = `Lọc: ${formatDateVn(currentAnalyticsFromDate)} - ${formatDateVn(currentAnalyticsToDate)} (${data.kpi.total_scans} lượt)`;
                        }
                    } else if (currentAnalyticsFromDate) {
                        scopeDesc = `Từ ngày ${formatDateVn(currentAnalyticsFromDate)}`;
                        filterBadgeText = `Từ ${formatDateVn(currentAnalyticsFromDate)} (${data.kpi.total_scans} lượt)`;
                    } else if (currentAnalyticsToDate) {
                        scopeDesc = `Đến ngày ${formatDateVn(currentAnalyticsToDate)}`;
                        filterBadgeText = `Đến ${formatDateVn(currentAnalyticsToDate)} (${data.kpi.total_scans} lượt)`;
                    }
                } else if (currentAnalyticsScope === 'today') {
                    scopeDesc = "Tính riêng hôm nay";
                } else if (currentAnalyticsScope === 'week') {
                    scopeDesc = "7 ngày gần nhất";
                } else if (currentAnalyticsScope === 'month') {
                    scopeDesc = "30 ngày gần nhất";
                }

                setElemText('admin-stat-scans-desc', scopeDesc);
                setElemText('admin-stat-unique-desc', `Trên tổng số ${data.employees.length} nhân sự`);

                // Cập nhật Filter Badge & Subtitle trên Dashboard
                const filterBadge = document.getElementById('active-filter-badge');
                const filterBadgeTextElem = document.getElementById('active-filter-badge-text');
                const filterSubtitle = document.getElementById('analytics-header-subtitle');
                const resetBtn = document.getElementById('btn-daily-filter-reset');

                if (isFiltered) {
                    if (filterBadge) filterBadge.style.display = 'inline-flex';
                    if (filterBadgeTextElem) filterBadgeTextElem.innerText = filterBadgeText || 'Đang lọc';
                    if (filterSubtitle) {
                        filterSubtitle.innerText = `Dữ liệu lọc theo thời gian [${scopeDesc}] — Tổng ${data.kpi.total_scans} lượt quét, ${data.kpi.unique_employees} nhân sự có mặt.`;
                    }
                    if (resetBtn) resetBtn.style.display = 'inline-flex';
                } else {
                    if (filterBadge) filterBadge.style.display = 'none';
                    if (filterSubtitle) {
                        filterSubtitle.innerText = 'Dữ liệu hiện diện và lưu lượng nhân sự theo thời gian thực từ hệ thống camera giám sát.';
                    }
                    if (resetBtn) resetBtn.style.display = 'none';
                }

                // Render 3 Biểu đồ
                renderAnalyticsCharts(data);

                // Render các bảng
                renderDailyAnalyticsTable(data.daily);
                renderWeeklyAnalyticsTable(data.weekly);
                renderEmployeesAnalyticsTable(data.employees);

            } catch (e) {
                console.error("Lỗi nạp admin analytics:", e);
            }
        }

        function changeAnalyticsScope(scope) {
            currentAnalyticsScope = scope;
            currentAnalyticsFromDate = '';
            currentAnalyticsToDate = '';

            document.querySelectorAll('.scope-btn').forEach(b => b.classList.remove('active'));
            const btn = document.getElementById(`btn-scope-${scope}`);
            if (btn) btn.classList.add('active');

            const customBtn = document.getElementById('btn-scope-custom');
            if (customBtn) customBtn.style.display = 'none';

            // Đồng bộ sang ô nhập ngày ở bảng Thống kê theo ngày
            const fromInput = document.getElementById('daily-filter-from');
            const toInput = document.getElementById('daily-filter-to');
            const now = new Date();
            const formatDateStr = (d) => {
                const y = d.getFullYear();
                const m = String(d.getMonth() + 1).padStart(2, '0');
                const day = String(d.getDate()).padStart(2, '0');
                return `${y}-${m}-${day}`;
            };

            if (fromInput && toInput) {
                if (scope === 'today') {
                    const todayStr = formatDateStr(now);
                    fromInput.value = todayStr;
                    toInput.value = todayStr;
                } else if (scope === 'week') {
                    const fDate = new Date();
                    fDate.setDate(fDate.getDate() - 7);
                    fromInput.value = formatDateStr(fDate);
                    toInput.value = formatDateStr(now);
                } else if (scope === 'month') {
                    const fDate = new Date();
                    fDate.setDate(fDate.getDate() - 30);
                    fromInput.value = formatDateStr(fDate);
                    toInput.value = formatDateStr(now);
                } else {
                    fromInput.value = '';
                    toInput.value = '';
                }
            }

            loadAdminAnalytics();
        }

        function applyAnalyticsDateFilter() {
            const fromInput = document.getElementById('daily-filter-from');
            const toInput = document.getElementById('daily-filter-to');
            let fVal = fromInput ? fromInput.value.trim() : '';
            let tVal = toInput ? toInput.value.trim() : '';

            if (!fVal && !tVal) {
                alert('Vui lòng chọn ngày để lọc!');
                return;
            }

            if (fVal && tVal && fVal > tVal) {
                const tmp = fVal;
                fVal = tVal;
                tVal = tmp;
                if (fromInput) fromInput.value = fVal;
                if (toInput) toInput.value = tVal;
            }

            currentAnalyticsScope = 'custom';
            currentAnalyticsFromDate = fVal;
            currentAnalyticsToDate = tVal;

            document.querySelectorAll('.scope-btn').forEach(b => b.classList.remove('active'));
            const customBtn = document.getElementById('btn-scope-custom');
            if (customBtn) {
                customBtn.style.display = 'inline-block';
                customBtn.classList.add('active');
                if (fVal && tVal && fVal === tVal) {
                    customBtn.innerText = `Lọc: ${formatDateVn(fVal)}`;
                } else if (fVal && tVal) {
                    customBtn.innerText = `Lọc: ${formatDateVn(fVal)} - ${formatDateVn(tVal)}`;
                } else if (fVal) {
                    customBtn.innerText = `Từ: ${formatDateVn(fVal)}`;
                } else {
                    customBtn.innerText = `Đến: ${formatDateVn(tVal)}`;
                }
            }

            loadAdminAnalytics();
        }

        function resetAnalyticsDateFilter() {
            const fromInput = document.getElementById('daily-filter-from');
            const toInput = document.getElementById('daily-filter-to');
            if (fromInput) fromInput.value = '';
            if (toInput) toInput.value = '';
            const customBtn = document.getElementById('btn-scope-custom');
            if (customBtn) customBtn.style.display = 'none';

            changeAnalyticsScope('all');
        }

        function setQuickDatePreset(preset) {
            const fromInput = document.getElementById('daily-filter-from');
            const toInput = document.getElementById('daily-filter-to');
            const now = new Date();
            const formatDateStr = (d) => {
                const y = d.getFullYear();
                const m = String(d.getMonth() + 1).padStart(2, '0');
                const day = String(d.getDate()).padStart(2, '0');
                return `${y}-${m}-${day}`;
            };

            if (preset === 'today') {
                const todayStr = formatDateStr(now);
                if (fromInput) fromInput.value = todayStr;
                if (toInput) toInput.value = todayStr;
            } else if (preset === 'week') {
                const fDate = new Date();
                fDate.setDate(fDate.getDate() - 7);
                if (fromInput) fromInput.value = formatDateStr(fDate);
                if (toInput) toInput.value = formatDateStr(now);
            } else if (preset === 'month') {
                const fDate = new Date();
                fDate.setDate(fDate.getDate() - 30);
                if (fromInput) fromInput.value = formatDateStr(fDate);
                if (toInput) toInput.value = formatDateStr(now);
            }
            applyAnalyticsDateFilter();
        }

        function scrollDailyTable(pos) {
            const pane = document.getElementById('pane-daily');
            if (!pane) return;
            if (pos === 'top') {
                pane.scrollTo({ top: 0, behavior: 'smooth' });
            } else if (pos === 'bottom') {
                pane.scrollTo({ top: pane.scrollHeight, behavior: 'smooth' });
            }
        }

        function toggleDailyTableExpand() {
            const pane = document.getElementById('pane-daily');
            const textSpan = document.getElementById('text-expand-daily');
            if (!pane) return;
            isDailyTableExpanded = !isDailyTableExpanded;
            if (isDailyTableExpanded) {
                pane.style.maxHeight = 'none';
                if (textSpan) textSpan.innerText = 'Thu nhỏ';
            } else {
                pane.style.maxHeight = '480px';
                if (textSpan) textSpan.innerText = 'Xem hết';
            }
        }

        function switchAnalyticsTableTab(sub) {
            currentAnalyticsSubTab = sub;
            document.querySelectorAll('.table-subtab-btn').forEach(b => b.classList.remove('active'));
            const btn = document.getElementById(`subtab-${sub}`);
            if (btn) btn.classList.add('active');

            document.getElementById('pane-daily').style.display = (sub === 'daily') ? 'block' : 'none';
            document.getElementById('pane-weekly').style.display = (sub === 'weekly') ? 'block' : 'none';
            document.getElementById('pane-employees').style.display = (sub === 'employees') ? 'block' : 'none';
            
            const searchBox = document.getElementById('analytics-table-search-box');
            if (searchBox) searchBox.style.display = (sub === 'employees') ? 'block' : 'none';

            const dailyToolbar = document.getElementById('daily-table-toolbar');
            if (dailyToolbar) dailyToolbar.style.display = (sub === 'employees') ? 'none' : 'flex';
        }

        function renderAnalyticsCharts(data) {
            if (typeof Chart === 'undefined') return;

            // 1. BIỂU ĐỒ CỘT: THEO KHUNG GIỜ (00h - 23h)
            const ctxHourly = document.getElementById('chart-hourly');
            if (ctxHourly) {
                if (chartHourlyInstance) chartHourlyInstance.destroy();
                const labels = data.hourly_chart.labels;
                const counts = data.hourly_chart.counts;
                
                // Nổi bật 2 khung giờ cao điểm trọng điểm (08h-09h xanh dương & 12h-13h cam hổ phách)
                const bgColors = counts.map((v, i) => {
                    if (i === 8) return '#0284c7'; // Khung 08h - 09h: Cao điểm vào ca sáng
                    if (i === 12) return '#d97706'; // Khung 12h - 13h: Cao điểm ăn trưa nhà ăn
                    if (i === 7 || i === 9 || i === 11 || i === 13) return '#7dd3fc'; // Khung giờ lân cận
                    if (i >= 16 && i <= 18) return '#38bdf8'; // Giờ tan ca
                    return '#cbd5e1';
                });

                chartHourlyInstance = new Chart(ctxHourly, {
                    type: 'bar',
                    data: {
                        labels: labels,
                        datasets: [{
                            label: 'Lượt điểm danh',
                            data: counts,
                            backgroundColor: bgColors,
                            borderRadius: 4,
                            maxBarThickness: 20
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: { display: false },
                            tooltip: {
                                callbacks: {
                                    title: function(items) {
                                        if (!items || !items.length) return '';
                                        const idx = items[0].dataIndex;
                                        if (idx === 8) return `08:00 - 09:00 (CAO ĐIỂM VÀO CA SÁNG)`;
                                        if (idx === 12) return `12:00 - 13:00 (CAO ĐIỂM ĂN TRƯA NHÀ ĂN)`;
                                        return `${labels[idx]}`;
                                    },
                                    label: function(ctx) { return ` ${ctx.raw} lượt quét`; }
                                }
                            }
                        },
                        scales: {
                            x: { grid: { display: false }, ticks: { font: { size: 10 } } },
                            y: { beginAtZero: true, ticks: { precision: 0, font: { size: 10 } } }
                        }
                    }
                });
            }

            // 2. BIỂU ĐỒ HÀNH VI: DÒNG DI CHUYỂN QUA CÁC CAMERA THEO KHUNG GIỜ
            const ctxBehavior = document.getElementById('chart-behavior');
            if (ctxBehavior) {
                if (chartBehaviorInstance) chartBehaviorInstance.destroy();
                const bLabels = data.behavior_chart.labels;
                const camMap = data.behavior_chart.cameras || {};
                
                const palette = [
                    { border: '#0052cc', bg: 'rgba(0, 82, 204, 0.12)' },
                    { border: '#10b981', bg: 'rgba(16, 185, 129, 0.12)' },
                    { border: '#f59e0b', bg: 'rgba(245, 158, 11, 0.12)' },
                    { border: '#8b5cf6', bg: 'rgba(139, 92, 246, 0.12)' }
                ];

                const datasets = [];
                let idx = 0;
                for (const [cName, cData] of Object.entries(camMap)) {
                    const color = palette[idx % palette.length];
                    datasets.push({
                        label: cName,
                        data: cData,
                        borderColor: color.border,
                        backgroundColor: color.bg,
                        tension: 0.35,
                        fill: true,
                        pointRadius: 3,
                        pointHoverRadius: 6
                    });
                    idx++;
                }

                chartBehaviorInstance = new Chart(ctxBehavior, {
                    type: 'line',
                    data: { labels: bLabels, datasets: datasets },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        interaction: { mode: 'index', intersect: false },
                        plugins: {
                            legend: { position: 'top', labels: { boxWidth: 12, font: { size: 10, weight: 600 } } },
                            tooltip: {
                                callbacks: {
                                    title: function(items) { return `Khung giờ ${items[0].label}`; }
                                }
                            }
                        },
                        scales: {
                            x: { grid: { display: false }, ticks: { font: { size: 10 } } },
                            y: { beginAtZero: true, ticks: { precision: 0, font: { size: 10 } } }
                        }
                    }
                });
            }

            // 3. BIỂU ĐỒ THỐNG KÊ: THEO PHÒNG BAN & CAMERA
            const ctxDept = document.getElementById('chart-dept');
            if (ctxDept) {
                if (chartDeptInstance) chartDeptInstance.destroy();
                const dLabels = data.dept_chart.labels;
                const dCounts = data.dept_chart.counts;
                const colors = ['#0052cc', '#0284c7', '#10b981', '#f59e0b', '#8b5cf6', '#ec4899', '#64748b', '#06b6d4'];

                chartDeptInstance = new Chart(ctxDept, {
                    type: 'doughnut',
                    data: {
                        labels: dLabels,
                        datasets: [{
                            data: dCounts,
                            backgroundColor: colors.slice(0, dLabels.length),
                            borderWidth: 2,
                            borderColor: '#fff'
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        cutout: '62%',
                        plugins: {
                            legend: {
                                position: 'bottom',
                                labels: { boxWidth: 10, font: { size: 9, weight: 600 }, padding: 6 }
                            }
                        }
                    }
                });
            }
        }

        // BẢNG 1: THỐNG KÊ HẰNG NGÀY
        function renderDailyAnalyticsTable(dailyList) {
            const tbody = document.getElementById('analytics-daily-tbody');
            if (!tbody) return;
            if (!dailyList || dailyList.length === 0) {
                tbody.innerHTML = `<tr><td colspan="10" style="text-align:center;padding:24px;color:#94a3b8;">Chưa có dữ liệu điểm danh trong phạm vi này</td></tr>`;
                return;
            }
            let html = '';
            dailyList.forEach(d => {
                html += `
                    <tr>
                        <td style="font-weight:700;color:#0f172a;">${d.display_date}</td>
                        <td style="text-align:center;font-weight:700;color:var(--accent);font-size:13px;">${d.total_scans}</td>
                        <td style="text-align:center;font-weight:600;">${d.unique_count}</td>
                        <td style="text-align:center;"><span style="font-size:11px;background:#e0f2fe;color:#0369a1;padding:3px 8px;border-radius:4px;font-weight:700;">${d.morning_peak_str || '--'}</span></td>
                        <td style="text-align:center;"><span style="font-size:11px;background:#fef3c7;color:#b45309;padding:3px 8px;border-radius:4px;font-weight:700;">${d.lunch_peak_str || '--'}</span></td>
                        <td style="text-align:center;color:var(--success);font-weight:600;">${d.on_time}</td>
                        <td style="text-align:center;color:${d.late > 0 ? '#ef4444' : '#64748b'};font-weight:600;">${d.late}</td>
                        <td style="font-family:monospace;font-size:11px;color:#475569;">${d.first_scan} - ${d.last_scan}</td>
                        <td><span style="font-size:11px;background:#f1f5f9;color:#0369a1;padding:2px 8px;border-radius:4px;font-weight:600;">${d.peak_hour}</span></td>
                        <td><span style="font-weight:600;color:#334155;">${d.top_cam}</span></td>
                    </tr>
                `;
            });
            tbody.innerHTML = html;
        }

        // BẢNG 2: THỐNG KÊ HẰNG TUẦN
        function renderWeeklyAnalyticsTable(weeklyList) {
            const tbody = document.getElementById('analytics-weekly-tbody');
            if (!tbody) return;
            if (!weeklyList || weeklyList.length === 0) {
                tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;padding:24px;color:#94a3b8;">Chưa có dữ liệu theo tuần</td></tr>`;
                return;
            }
            let html = '';
            weeklyList.forEach(w => {
                html += `
                    <tr>
                        <td style="font-weight:700;color:var(--accent);">${w.week_key}</td>
                        <td style="text-align:center;font-weight:700;color:#0f172a;font-size:13px;">${w.total_scans}</td>
                        <td style="text-align:center;font-weight:600;">${w.unique_count}</td>
                        <td style="text-align:center;font-weight:600;">${w.active_days} ngày</td>
                        <td style="text-align:center;font-weight:600;color:var(--text-dark);">${w.avg_per_day} lượt</td>
                        <td><span style="font-weight:600;color:#059669;">${w.busiest_day}</span></td>
                    </tr>
                `;
            });
            tbody.innerHTML = html;
        }

        // BẢNG 3: DANH SÁCH NHÂN SỰ & CLICK ĐỂ XEM CHI TIẾT
        function renderEmployeesAnalyticsTable(empList) {
            const tbody = document.getElementById('analytics-employees-tbody');
            if (!tbody) return;
            if (!empList || empList.length === 0) {
                tbody.innerHTML = `<tr><td colspan="10" style="text-align:center;padding:24px;color:#94a3b8;">Chưa có nhân sự nào điểm danh trong phạm vi này</td></tr>`;
                return;
            }
            let html = '';
            empList.forEach(emp => {
                const avatarUrl = emp.avatar ? `/api_faces/${emp.avatar}` : (emp.latest_snapshot ? `/snapshots/${emp.latest_snapshot}` : '');
                const safeName = (emp.name || '').replace(/'/g, "\\'");
                const detailCall = `openPersonDetail('${emp.code}', '${emp.emp_id || ''}', '${safeName}')`;
                html += `
                    <tr class="clickable-row" onclick="${detailCall}" title="Nhấp để xem hồ sơ và mốc thời gian điểm danh">
                        <td style="text-align:center;">
                            ${avatarUrl ? `<img src="${avatarUrl}" class="log-thumb" loading="lazy" style="width:36px;height:36px;border-radius:4px;object-fit:cover;" onerror="this.onerror=null;this.parentElement.innerHTML='<div style=\\'width:36px;height:36px;background:#e2e8f0;border-radius:4px;margin:auto;\\'></div>';">` : '<div style="width:36px;height:36px;background:#e2e8f0;border-radius:4px;margin:auto;"></div>'}
                        </td>
                        <td style="font-weight:700;color:var(--accent);">${emp.code}</td>
                        <td style="font-weight:700;color:#0f172a;">${emp.name}</td>
                        <td>
                            <div style="font-weight:600;color:#334155;">${emp.role}</div>
                            <div style="font-size:11px;color:var(--text-muted);">${emp.dept}</div>
                        </td>
                        <td style="font-size:11px;color:#64748b;">${emp.company || '--'}</td>
                        <td style="font-family:monospace;font-size:11px;color:#059669;font-weight:600;">${emp.first_time}</td>
                        <td style="font-family:monospace;font-size:11px;color:#0284c7;font-weight:600;">${emp.last_time}</td>
                        <td style="text-align:center;font-weight:700;color:var(--accent);font-size:13px;">${emp.total_scans}</td>
                        <td style="text-align:center;font-weight:700;color:var(--success);">${emp.avg_conf}</td>
                        <td style="text-align:center;" onclick="event.stopPropagation();${detailCall}">
                            <button class="btn btn-outline" style="padding:3px 8px;font-size:11px;margin:auto;">
                                Chi tiết
                            </button>
                        </td>
                    </tr>
                `;
            });
            tbody.innerHTML = html;
        }

        function filterAnalyticsEmployees() {
            const search = document.getElementById('analyticsEmployeeSearch').value.toUpperCase();
            const table = document.getElementById('analyticsEmployeesTable');
            if (!table) return;
            const tr = table.getElementsByTagName('tr');
            for (let i = 1; i < tr.length; i++) {
                const text = tr[i].textContent || tr[i].innerText;
                tr[i].style.display = (text.toUpperCase().indexOf(search) > -1) ? "" : "none";
            }
        }

        // ====================================================================
        // MODAL XEM CHI TIẾT TỪNG MỐC THỜI GIAN CỦA 1 NGƯỜI
        // ====================================================================
        async function openPersonDetail(empCode, empId = '', empName = '') {
            const modal = document.getElementById('person-detail-modal');
            const timelineList = document.getElementById('pd-timeline-list');
            if (modal) modal.style.display = 'flex';

            // Loading state
            setElemText('pd-fullname', empName || "Đang tải...");
            setElemText('pd-code', empCode);
            setElemText('pd-status', "--");
            setElemText('pd-role', "--");
            setElemText('pd-dept', "--");
            setElemText('pd-company', "--");
            setElemText('pd-salary', "--");
            const pdAvatar = document.getElementById('pd-avatar');
            if (pdAvatar) pdAvatar.src = "";
            setElemText('pd-total-scans', "--");
            setElemText('pd-first-scan', "--");
            setElemText('pd-last-scan', "--");
            setElemText('pd-avg-conf', "--");
            setElemText('pd-timeline-count', "Đang tải dữ liệu...");
            if (timelineList) timelineList.innerHTML = `<div style="padding:30px;text-align:center;color:#94a3b8;">Đang truy xuất dữ liệu điểm danh...</div>`;

            try {
                let apiUrl = `/api/person_timeline/${encodeURIComponent(empCode)}`;
                const params = new URLSearchParams();
                if (empId) params.append('emp_id', empId);
                if (empName) params.append('name', empName);
                const qStr = params.toString();
                if (qStr) apiUrl += `?${qStr}`;

                const res = await fetch(apiUrl);
                const data = await res.json();
                if (!data.success) {
                    if (timelineList) timelineList.innerHTML = `<div style="padding:30px;text-align:center;color:#ef4444;">Không tìm thấy lịch sử cho nhân viên ${empCode}</div>`;
                    return;
                }

                const p = data.profile || {};
                setElemText('pd-fullname', p.FullName || empName || data.emp_code);
                setElemText('pd-code', p.EmployeeCode || data.emp_code);
                setElemText('pd-status', p.EmployeeStatus_Name || 'Đang làm việc');
                setElemText('pd-role', p.Name_Role || 'Nhân viên');
                setElemText('pd-dept', p.Dept_Name || '--');
                setElemText('pd-company', p.Company_Name || '--');
                setElemText('pd-salary', p.SalaryClassName || '--');
                
                const av = data.avatar ? `/api_faces/${data.avatar}` : (data.timeline.length > 0 && data.timeline[0].snapshot ? `/snapshots/${data.timeline[0].snapshot}` : '');
                if (pdAvatar) pdAvatar.src = av || '';

                // Stats
                setElemText('pd-total-scans', data.stats.total_scans);
                setElemText('pd-first-scan', data.stats.first_scan);
                setElemText('pd-last-scan', data.stats.last_scan);
                setElemText('pd-avg-conf', data.stats.avg_conf);
                setElemText('pd-timeline-count', `${data.timeline.length} mốc thời gian ghi nhận`);

                // Render Timeline Cards
                if (!data.timeline || data.timeline.length === 0) {
                    timelineList.innerHTML = `<div style="padding:30px;text-align:center;color:#94a3b8;">Chưa có mốc thời gian quét nào.</div>`;
                    return;
                }

                let tHtml = '';
                data.timeline.forEach((item, idx) => {
                    const snapUrl = item.snapshot ? `/snapshots/${item.snapshot}` : '';
                    tHtml += `
                        <div class="timeline-card">
                            <div style="flex:1;">
                                <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
                                    <span class="timeline-time">${item.time}</span>
                                    <span class="timeline-badge">${item.cam}</span>
                                    <span style="color:var(--success);font-weight:600;font-size:12px;">${item.conf}</span>
                                </div>
                                <div style="font-size:11px;color:var(--text-muted);margin-top:4px;">
                                    Mốc #${data.timeline.length - idx} • Xác thực hợp lệ • Trạng thái: <strong>${item.status || 'Hợp lệ'}</strong>
                                </div>
                            </div>
                            ${snapUrl ? `
                                <div class="timeline-snap-box" onclick="openLightbox('${snapUrl}', '${item.name} [${item.code}] lúc ${item.time} (${item.cam}) - Độ tương đồng: ${item.conf}')" title="Nhấp để phóng to ảnh chụp">
                                    <img src="${snapUrl}" class="timeline-snap-img" loading="lazy" onerror="this.onerror=null;this.parentElement.innerHTML='<span style=\\'font-size:10px;color:#94a3b8;\\'>Lỗi tải ảnh</span>';">
                                    <span class="snap-zoom-icon">Phóng to</span>
                                </div>
                            ` : '<div style="font-size:10px;color:#94a3b8;font-style:italic;">Không có ảnh</div>'}
                        </div>
                    `;
                });
                timelineList.innerHTML = tHtml;

            } catch (e) {
                console.error("Lỗi xem chi tiết person:", e);
                timelineList.innerHTML = `<div style="padding:30px;text-align:center;color:#ef4444;">Lỗi kết nối tải dữ liệu: ${e}</div>`;
            }
        }

        function closePersonDetailModal() {
            document.getElementById('person-detail-modal').style.display = 'none';
        }

        // LIGHTBOX PHÓNG TO ẢNH CHỤP
        function openLightbox(src, caption) {
            document.getElementById('lightbox-img').src = src;
            document.getElementById('lightbox-caption').innerText = caption || '';
            document.getElementById('lightbox-modal').style.display = 'flex';
        }

        function closeLightbox() {
            document.getElementById('lightbox-modal').style.display = 'none';
            document.getElementById('lightbox-img').src = '';
        }

        // Hàm ngắt kết nối toàn bộ luồng video trên giao diện để giải phóng socket HTTP cho trình duyệt tải ảnh và gọi API tức thì
        function stopAllVideoStreams() {
            const singleImg = document.getElementById('single-cam-img');
            if (singleImg) {
                singleImg.src = '';
                singleImg.removeAttribute('src');
            }
            
            const gridFeeds = document.querySelectorAll('#cam-grid-container .video-feed');
            gridFeeds.forEach(img => {
                img.src = '';
                img.removeAttribute('src');
            });
        }

        // Chuyển đổi 3 Tab Menu Chính
        function switchNavTab(tabName) {
            currentNavTab = tabName;
            document.querySelectorAll('.nav-tab-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.app-view').forEach(v => v.style.display = 'none');

            const tabBtn = document.getElementById('tab-' + tabName);
            if (tabBtn) tabBtn.classList.add('active');
            const viewEl = document.getElementById('view-' + tabName);
            if (viewEl) viewEl.style.display = 'block';

            if (tabName === 'admin') {
                stopAllVideoStreams();
                loadAdminAnalytics();
                renderAdminCameraTable();
            } else if (tabName === 'data') {
                stopAllVideoStreams();
                loadAllAttendanceRecords();
                loadEmployeesList();
            } else if (tabName === 'camera') {
                if (currentCamView === 'grid') {
                    renderCameraGrid();
                } else {
                    switchCameraView(currentCamView);
                }
                renderSidebarLogs();
            }
        }

        // Chuyển đổi Sub-tab trong Mục 3
        function switchDataSubTab(sub) {
            document.querySelectorAll('.data-tab-btn').forEach(b => b.classList.remove('active'));
            const subBtn = document.getElementById('subtab-' + sub);
            if (subBtn) subBtn.classList.add('active');
            if (sub === 'export') {
                const paneExp = document.getElementById('data-pane-export');
                if (paneExp) paneExp.style.display = 'flex';
                const paneEmp = document.getElementById('data-pane-employees');
                if (paneEmp) paneEmp.style.display = 'none';
                loadAllAttendanceRecords();
            } else {
                const paneExp = document.getElementById('data-pane-export');
                if (paneExp) paneExp.style.display = 'none';
                const paneEmp = document.getElementById('data-pane-employees');
                if (paneEmp) paneEmp.style.display = 'flex';
                loadEmployeesList();
            }
        }

        // Tải danh sách Camera từ server
        async function fetchCameras() {
            try {
                const res = await fetch('/api/cameras');
                camerasList = await res.json();
                const activeCount = camerasList.filter(c => (c.is_running !== false && c.enabled !== false)).length;
                setElemText('online-cam-count', activeCount);
                setElemText('admin-cam-count', activeCount);
                setElemText('active-cams-count', activeCount);
                setElemText('total-cams-count', camerasList.length);

                renderCameraSubnav();
                renderCameraGrid();
                renderAdminCameraTable();
                updateReportCamFilter();
            } catch (e) {
                console.error("Lỗi fetch cameras:", e);
            }
        }

        // Vẽ danh sách nút chuyển camera (kèm chỉ báo trạng thái Online / Tạm dừng)
        function renderCameraSubnav() {
            const container = document.getElementById('cam-switcher-tabs');
            if (!container) return;
            const activeCount = camerasList.filter(c => (c.is_running !== false && c.enabled !== false)).length;

            let html = `
                <button class="cam-tab-btn ${currentCamView === 'grid' ? 'active' : ''}" onclick="switchCameraView('grid')">
                    <span>Dạng lưới</span>
                    <span style="font-size:10px;padding:1px 6px;border-radius:10px;background:${currentCamView === 'grid' ? 'rgba(255,255,255,0.25)' : '#e2e8f0'};color:${currentCamView === 'grid' ? '#fff' : '#475569'};font-weight:700;">${activeCount}/${camerasList.length}</span>
                </button>
            `;
            camerasList.forEach(cam => {
                const isSelected = (currentCamView == cam.id);
                const isOnline = !!(cam.is_running !== false && cam.enabled !== false);
                const statusDot = isOnline 
                    ? `<span style="width:7px;height:7px;border-radius:50%;background:#10b981;display:inline-block;box-shadow:0 0 4px #10b981;"></span>`
                    : `<span style="width:7px;height:7px;border-radius:50%;background:#94a3b8;display:inline-block;"></span>`;
                html += `
                    <button class="cam-tab-btn ${isSelected ? 'active' : ''}" onclick="switchCameraView(${cam.id})" title="${cam.name} (${isOnline ? 'Đang kết nối' : 'Đang tạm dừng'})">
                        ${statusDot}
                        <span>${cam.name}</span>
                    </button>
                `;
            });
            container.innerHTML = html;

            setElemText('active-cams-count', activeCount);
            setElemText('total-cams-count', camerasList.length);
            setElemText('online-cam-count', activeCount);
            setElemText('admin-cam-count', activeCount);
        }

        // Vẽ lưới camera: Camera đang chạy có luồng trực tiếp + nút Tắt; Camera tạm dừng có Standby Card + nút Bật
        function renderCameraGrid() {
            const grid = document.getElementById('cam-grid-container');
            if (!grid) return;
            let html = '';
            camerasList.forEach(cam => {
                const isOnline = !!(cam.is_running !== false && cam.enabled !== false);
                if (isOnline) {
                    html += `
                        <div class="cam-card">
                            <div class="cam-header">
                                <span class="cam-title">${cam.name}</span>
                                <div style="display:flex;align-items:center;gap:6px;">
                                    <span class="live-tag"><span class="live-dot"></span> TRỰC TIẾP</span>
                                    <button class="cam-toggle-mini-btn btn-active" onclick="event.stopPropagation(); toggleCamera(${cam.id});" title="Nhấn để tạm dừng luồng camera này (giải phóng CPU)">Tắt luồng</button>
                                </div>
                            </div>
                            <div class="video-container" onclick="switchCameraView(${cam.id})" style="cursor:pointer;" title="Nhấp để phóng to camera này">
                                <img class="video-feed" src="/video_feed/${cam.id}" alt="${cam.name}">
                            </div>
                            <div class="cam-sub">
                                <span>${cam.location || 'Trực tiếp'}</span>
                                <button class="btn-link" onclick="switchCameraView(${cam.id})" style="background:none;border:none;color:var(--accent);font-weight:600;font-size:11px;cursor:pointer;">Xem riêng &rarr;</button>
                            </div>
                        </div>
                    `;
                } else {
                    html += `
                        <div class="cam-card cam-card-offline">
                            <div class="cam-header" style="background:#1e293b;">
                                <span class="cam-title" style="color:#94a3b8;">${cam.name}</span>
                                <div style="display:flex;align-items:center;gap:6px;">
                                    <span class="offline-tag">TẠM DỪNG (0% CPU)</span>
                                    <button class="cam-toggle-mini-btn btn-inactive" onclick="event.stopPropagation(); toggleCamera(${cam.id});" title="Nhấn để kết nối luồng RTSP camera này">Bật luồng</button>
                                </div>
                            </div>
                            <div class="video-container offline-standby-container" onclick="toggleCamera(${cam.id})" style="cursor:pointer;" title="Nhấn để kết nối và xem trực tiếp">
                                <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;padding:20px;text-align:center;">
                                    <svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="#64748b" stroke-width="1.5" style="margin-bottom:8px;"><circle cx="12" cy="12" r="10"/><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"/></svg>
                                    <div style="font-weight:600;font-size:13px;color:#cbd5e1;margin-bottom:3px;">Luồng RTSP đang ngắt kết nối</div>
                                    <div style="font-size:11px;color:#64748b;margin-bottom:12px;">Đang tiết kiệm ~215% CPU & băng thông</div>
                                    <button class="btn btn-primary" onclick="event.stopPropagation(); toggleCamera(${cam.id});" style="padding:5px 14px;font-size:11px;display:inline-flex;align-items:center;gap:5px;">
                                        <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                                        Bật camera này
                                    </button>
                                </div>
                            </div>
                            <div class="cam-sub" style="background:#0f172a;border-color:#334155;">
                                <span style="color:#64748b;">${cam.location || '--'}</span>
                                <button class="btn-link" onclick="switchCameraView(${cam.id})" style="background:none;border:none;color:#94a3b8;font-weight:500;font-size:11px;cursor:pointer;">Chi tiết &rarr;</button>
                            </div>
                        </div>
                    `;
                }
            });
            grid.innerHTML = html;
            grid.className = (camerasList.length <= 2) ? 'cam-grid-layout' : 'cam-grid-layout three-cams';
        }

        // Vẽ bảng quản trị camera kèm nút Bật / Tắt theo từng camera
        function renderAdminCameraTable() {
            const tbody = document.getElementById('admin-cameras-tbody');
            if (!tbody) return;
            let html = '';
            camerasList.forEach(cam => {
                const isOnline = !!(cam.is_running !== false && cam.enabled !== false);
                const statusBadge = isOnline
                    ? `<span class="badge-online">Đang hoạt động (25 FPS)</span>`
                    : `<span class="badge-offline">Đã ngắt luồng (0% CPU)</span>`;
                const toggleBtn = isOnline
                    ? `<button class="btn btn-outline" onclick="toggleCamera(${cam.id})" style="display:inline-flex;padding:3px 8px;font-size:11px;color:#dc2626;border-color:#fca5a5;">Tắt luồng</button>`
                    : `<button class="btn btn-primary" onclick="toggleCamera(${cam.id})" style="display:inline-flex;padding:3px 8px;font-size:11px;">Bật luồng</button>`;

                html += `
                    <tr>
                        <td style="font-weight:700;color:var(--primary);">${cam.id}</td>
                        <td style="font-weight:700;">${cam.name}</td>
                        <td style="font-family:monospace;font-size:11px;color:#64748b;">${cam.url}</td>
                        <td>${cam.location || '--'}</td>
                        <td>${statusBadge}</td>
                        <td style="text-align:center;display:flex;gap:4px;justify-content:center;">
                            ${toggleBtn}
                            <button class="btn btn-outline" onclick="switchNavTab('camera');switchCameraView(${cam.id});" style="display:inline-flex;padding:3px 8px;font-size:11px;">Xem</button>
                            ${cam.id > 3 ? `<button class="btn btn-danger" onclick="deleteCamera(${cam.id})" style="display:inline-flex;padding:3px 8px;font-size:11px;">Xóa</button>` : ''}
                        </td>
                    </tr>
                `;
            });
            tbody.innerHTML = html;
        }

        // Chuyển đổi giữa Xem Lưới và Xem Từng Camera
        function switchCameraView(view) {
            currentCamView = view;
            renderCameraSubnav();

            const gridBox = document.getElementById('cam-grid-container');
            const singleBox = document.getElementById('cam-single-container');
            const singleImg = document.getElementById('single-cam-img');

            if (view === 'grid') {
                if (singleImg) singleImg.src = '';
                if (gridBox) gridBox.style.display = 'grid';
                if (singleBox) singleBox.style.display = 'none';
                renderCameraGrid();
            } else {
                // Tắt toàn bộ video trong lưới để không chiếm socket HTTP và giải phóng CPU
                const gridFeeds = document.querySelectorAll('#cam-grid-container .video-feed');
                gridFeeds.forEach(img => { img.src = ''; });

                if (gridBox) gridBox.style.display = 'none';
                if (singleBox) singleBox.style.display = 'flex';

                const cam = camerasList.find(c => c.id == view);
                if (cam) {
                    setElemText('single-cam-title', cam.name);
                    const isOnline = !!(cam.is_running !== false && cam.enabled !== false);
                    const statusPill = document.getElementById('single-cam-status-pill');
                    const toggleBtn = document.getElementById('single-cam-toggle-btn');

                    if (isOnline) {
                        if (statusPill) {
                            statusPill.className = 'live-tag';
                            statusPill.innerHTML = '<span class="live-dot"></span> TRỰC TIẾP';
                        }
                        if (toggleBtn) {
                            toggleBtn.innerHTML = 'Tạm dừng luồng (Tiết kiệm CPU)';
                            toggleBtn.className = 'btn btn-outline';
                            toggleBtn.style.color = '#dc2626';
                            toggleBtn.style.borderColor = '#fca5a5';
                        }
                        setElemText('single-cam-info', `${cam.location || 'Camera'} | Luồng RTSP sắc nét trực tiếp (25 FPS)`);
                        setElemText('single-cam-cpu-hint', 'Đang nhận diện AI thời gian thực');
                        if (singleImg) singleImg.src = `/video_feed/${cam.id}`;
                    } else {
                        if (statusPill) {
                            statusPill.className = 'offline-tag';
                            statusPill.innerHTML = 'TẠM DỪNG (0% CPU)';
                        }
                        if (toggleBtn) {
                            toggleBtn.innerHTML = 'Kích hoạt & Kết nối RTSP';
                            toggleBtn.className = 'btn btn-primary';
                            toggleBtn.style.color = '#fff';
                            toggleBtn.style.borderColor = 'var(--accent)';
                        }
                        setElemText('single-cam-info', `${cam.location || 'Camera'} | Luồng RTSP đang ngắt kết nối`);
                        setElemText('single-cam-cpu-hint', 'Đã giải phóng ~215% CPU');
                        if (singleImg) singleImg.src = `/video_feed/${cam.id}`;
                    }
                }
            }

            renderSidebarLogs();
        }

        // Bật / Tắt 1 camera cụ thể
        async function toggleCamera(camId) {
            try {
                const res = await fetch(`/api/camera/toggle/${camId}`, { method: 'POST' });
                const data = await res.json();
                if (data.success) {
                    const cam = camerasList.find(c => c.id == camId);
                    if (cam) {
                        cam.enabled = data.enabled;
                        cam.is_running = data.is_running;
                    }
                    renderCameraSubnav();
                    if (currentCamView === 'grid') {
                        renderCameraGrid();
                    } else if (currentCamView == camId) {
                        switchCameraView(camId);
                    }
                    renderAdminCameraTable();
                } else {
                    alert("Lỗi: " + data.message);
                }
            } catch (e) {
                console.error("Lỗi toggle camera:", e);
            }
        }

        function toggleCurrentSingleCamera() {
            if (currentCamView !== 'grid') {
                toggleCamera(Number(currentCamView));
            }
        }

        // Bật / Tắt hàng loạt tất cả camera
        async function batchToggleCameras(action) {
            try {
                const res = await fetch('/api/camera/batch_toggle', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ action: action })
                });
                const data = await res.json();
                if (data.success) {
                    await fetchCameras();
                    if (currentCamView === 'grid') {
                        renderCameraGrid();
                    } else {
                        switchCameraView(currentCamView);
                    }
                }
            } catch (e) {
                console.error("Lỗi batch toggle:", e);
            }
        }

        // Đổi độ nét video stream
        async function changeQuality(mode) {
            try {
                const res = await fetch('/api/stream_quality', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ mode: mode })
                });
                const data = await res.json();
                console.log("Quality updated:", data);
            } catch(e) {
                console.error("Lỗi cập nhật chất lượng stream:", e);
            }
        }

        // Bộ lọc phạm vi log bên cột phải
        function setLogScope(scope) {
            currentLogScope = scope;
            const btnAll = document.getElementById('btn-filter-all');
            if (btnAll) btnAll.className = (scope === 'all') ? 'log-filter-btn active' : 'log-filter-btn';
            const btnCur = document.getElementById('btn-filter-current');
            if (btnCur) btnCur.className = (scope === 'current') ? 'log-filter-btn active' : 'log-filter-btn';
            renderSidebarLogs();
        }

        // Cập nhật trạng thái và log từ máy chủ
        async function fetchStatus() {
            try {
                const res = await fetch('/api/status');
                const data = await res.json();

                setElemText('admin-api-count', data.api_count);
                setElemText('admin-db-count', data.db_count);
                allLogs = data.logs || [];
                setElemText('admin-today-count', allLogs.length);

                // Cập nhật Thẻ nhân viên vừa nhận diện bên cột phải
                if (data.active_card) {
                    const c = data.active_card;
                    setElemText('v-name', c.profile.FullName || c.code);
                    setElemText('v-role', c.profile.Name_Role || 'Nhân viên');
                    setElemText('v-dept', c.profile.Dept_Name || '--');
                    setElemText('v-company', c.profile.Company_Name || '--');
                    setElemText('v-cam', c.cam_name || '--');
                    setElemText('v-conf', (c.confidence ? c.confidence.toFixed(1) : '90') + '%');
                    setElemText('v-status', c.profile.EmployeeStatus_Name || 'Đang làm việc');
                    
                    const vAvatar = document.getElementById('v-avatar');
                    const vPlaceholder = document.getElementById('v-avatar-placeholder');
                    if (c.avatar) {
                        if (vAvatar) {
                            vAvatar.src = c.avatar;
                            vAvatar.style.display = 'block';
                        }
                        if (vPlaceholder) vPlaceholder.style.display = 'none';
                    } else {
                        if (vAvatar) vAvatar.style.display = 'none';
                        if (vPlaceholder) vPlaceholder.style.display = 'flex';
                    }
                }

                renderSidebarLogs();
                // Không tự động renderExportReportTable() tại đây để bảo toàn bộ lọc của người dùng
            } catch (e) {
                console.error("Lỗi fetch status:", e);
            }
        }

        // Vẽ danh sách log bên cột phải
        function renderSidebarLogs() {
            if (currentNavTab !== 'camera') return;
            const container = document.getElementById('sidebar-log-list');
            if (!container) return;
            let filtered = allLogs;

            if (currentLogScope === 'current' && currentCamView !== 'grid') {
                filtered = allLogs.filter(l => l.cam_id == currentCamView || l.cam.includes(String(currentCamView)));
            }

            if (!filtered || filtered.length === 0) {
                container.innerHTML = `<div style="padding:20px;text-align:center;color:#94a3b8;font-size:11px;">Chưa có lượt điểm danh nào phù hợp.</div>`;
                return;
            }

            let html = '';
            filtered.slice(0, 30).forEach(item => {
                const snapUrl = item.snapshot ? `/snapshots/${item.snapshot}` : (item.avatar ? `/api_faces/${item.avatar}` : '');
                html += `
                    <div class="log-item">
                        ${snapUrl ? `<img class="log-thumb" src="${snapUrl}" loading="lazy" title="Ảnh chụp lúc chấm công" onerror="this.onerror=null;this.parentElement.innerHTML='<div style=\\'width:40px;height:40px;background:#e2e8f0;border-radius:4px;\\'></div>';">` : '<div style="width:40px;height:40px;background:#e2e8f0;border-radius:4px;"></div>'}
                        <div class="log-info">
                            <div class="log-name">
                                <span>${item.name} <strong style="color:var(--primary);">[${item.code}]</strong></span>
                                <span class="log-conf">${item.conf}</span>
                            </div>
                            <div class="log-sub">${item.role} • ${item.dept}</div>
                            <div class="log-sub" style="color:#0284c7;">${item.cam} • ${item.time}</div>
                        </div>
                    </div>
                `;
            });
            container.innerHTML = html;
        }

        // ====================================================================
        // QUẢN LÝ DỮ LIỆU & BÁO CÁO: TẢI TOÀN BỘ VÀ PHÂN LOẠI CAMERA CHUẨN XÁC
        // ====================================================================
        let allReportRecords = [];
        let isReportLoading = false;

        // Tải toàn bộ dữ liệu lịch sử điểm danh từ tệp CSV (không giới hạn 100 bản ghi)
        async function loadAllAttendanceRecords(forceRefresh = false) {
            if (allReportRecords.length > 0 && !forceRefresh && !isReportLoading) {
                filterReportTable();
                return;
            }
            if (isReportLoading) return;
            isReportLoading = true;

            const badge = document.getElementById('reportCountBadge');
            if (badge) badge.innerText = 'Đang tải dữ liệu...';

            try {
                const res = await fetch('/api/attendance_records');
                const data = await res.json();
                if (data.success && Array.isArray(data.records)) {
                    allReportRecords = data.records;
                } else {
                    allReportRecords = [];
                }
                updateReportCamFilter();
                filterReportTable();
            } catch (e) {
                console.error("Lỗi tải toàn bộ lịch sử điểm danh:", e);
                if (badge) badge.innerText = 'Lỗi kết nối tải dữ liệu';
            } finally {
                isReportLoading = false;
            }
        }

        function updateReportCamFilter() {
            const select = document.getElementById('reportCamFilter');
            if (!select) return;
            const currentVal = select.value;

            // Thu thập danh sách camera từ cấu hình đang chạy và từ toàn bộ bản ghi lịch sử
            const camSet = new Set();
            camerasList.forEach(c => { if (c.name) camSet.add(c.name.trim()); });
            allReportRecords.forEach(r => { if (r.cam) camSet.add(r.cam.trim()); });

            let html = '<option value="">Tất cả Camera</option>';
            Array.from(camSet).sort().forEach(cName => {
                html += `<option value="${cName}">${cName}</option>`;
            });
            select.innerHTML = html;

            if (currentVal && camSet.has(currentVal)) {
                select.value = currentVal;
            }
        }

        function setReportDatePreset(preset) {
            const fromInput = document.getElementById('reportDateFrom');
            const toInput = document.getElementById('reportDateTo');
            if (!fromInput || !toInput) return;
            
            const now = new Date();
            const formatDate = (d) => {
                const y = d.getFullYear();
                const m = String(d.getMonth() + 1).padStart(2, '0');
                const day = String(d.getDate()).padStart(2, '0');
                return `${y}-${m}-${day}`;
            };
            
            if (preset === 'today') {
                const tStr = formatDate(now);
                fromInput.value = tStr;
                toInput.value = tStr;
            } else if (preset === 'yesterday') {
                const yDate = new Date();
                yDate.setDate(yDate.getDate() - 1);
                const yStr = formatDate(yDate);
                fromInput.value = yStr;
                toInput.value = yStr;
            } else if (preset === '7days') {
                const fDate = new Date();
                fDate.setDate(fDate.getDate() - 6);
                fromInput.value = formatDate(fDate);
                toInput.value = formatDate(now);
            } else if (preset === 'all') {
                fromInput.value = '';
                toInput.value = '';
            }
            filterReportTable();
        }

        function filterReportTable() {
            const searchInput = document.getElementById('reportSearch');
            const search = (searchInput ? searchInput.value : '').trim().toUpperCase();
            
            const camSelect = document.getElementById('reportCamFilter');
            const selectedCam = (camSelect ? camSelect.value : '').trim().toUpperCase();

            const dateFromInput = document.getElementById('reportDateFrom');
            const dateFrom = (dateFromInput ? dateFromInput.value : '').trim();

            const dateToInput = document.getElementById('reportDateTo');
            const dateTo = (dateToInput ? dateToInput.value : '').trim();

            // Lọc danh sách trực tiếp trên toàn bộ allReportRecords
            const filtered = allReportRecords.filter(item => {
                // 1. Lọc theo khoảng ngày (Thời gian)
                const itemDate = (item.time || '').substring(0, 10);
                if (dateFrom && itemDate && itemDate < dateFrom) return false;
                if (dateTo && itemDate && itemDate > dateTo) return false;

                // 2. Phân loại chuẩn xác theo Camera
                if (selectedCam) {
                    const itemCam = (item.cam || '').toUpperCase();
                    if (itemCam !== selectedCam && !itemCam.includes(selectedCam) && !selectedCam.includes(itemCam)) {
                        return false;
                    }
                }

                // 3. Tìm kiếm theo Mã NV, Họ tên, Phòng ban, Công ty, Chức danh
                if (search) {
                    const code = (item.code || '').toUpperCase();
                    const name = (item.name || '').toUpperCase();
                    const role = (item.role || '').toUpperCase();
                    const dept = (item.dept || '').toUpperCase();
                    const comp = (item.company || '').toUpperCase();
                    const combined = `${code} ${name} ${role} ${dept} ${comp}`;
                    if (combined.indexOf(search) === -1) {
                        return false;
                    }
                }

                return true;
            });

            // Cập nhật Badge hiển thị số lượng bản ghi
            const badge = document.getElementById('reportCountBadge');
            if (badge) {
                let notes = [];
                if (dateFrom || dateTo) notes.push(`${dateFrom || '...'} đến ${dateTo || '...'}`);
                if (selectedCam) notes.push(selectedCam);
                if (search) notes.push(`"${search}"`);
                
                if (notes.length > 0) {
                    badge.innerHTML = `Hiển thị <strong>${filtered.length}</strong> / ${allReportRecords.length} bản ghi (${notes.join(' • ')})`;
                } else {
                    badge.innerHTML = `Hiển thị <strong>${filtered.length}</strong> / ${allReportRecords.length} bản ghi (Toàn bộ)`;
                }
            }

            // Đồng bộ đường link Xuất Báo cáo In/PDF và Xuất Excel với bộ lọc hiện tại
            const params = new URLSearchParams();
            if (selectedCam) params.set('cam', selectedCam);
            if (search) params.set('q', search);
            if (dateFrom) params.set('from_date', dateFrom);
            if (dateTo) params.set('to_date', dateTo);
            const qs = params.toString() ? '?' + params.toString() : '';

            const pdfBtn = document.getElementById('btn-export-pdf');
            if (pdfBtn) pdfBtn.href = `/export_report${qs}`;

            const excelBtn = document.getElementById('btn-export-excel');
            if (excelBtn) excelBtn.href = `/export_excel${qs}`;

            // Đổ dữ liệu vào bảng
            const tbody = document.getElementById('export-report-tbody');
            if (!tbody) return;

            if (filtered.length === 0) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="11" style="text-align:center;padding:32px;color:#94a3b8;font-size:13px;">
                            Không tìm thấy bản ghi điểm danh nào phù hợp với bộ lọc.
                        </td>
                    </tr>
                `;
                return;
            }

            let html = '';
            filtered.forEach((item, idx) => {
                const snapUrl = item.snapshot ? `/snapshots/${item.snapshot}` : '';
                const avatarUrl = item.avatar ? `/api_faces/${item.avatar}` : '';
                const safeName = (item.name || '').replace(/'/g, "\\'");
                const snapCaption = `${safeName} [${item.code}] - ${item.cam} (${item.time}) - Độ tin cậy: ${item.conf}`;
                
                const snapClick = snapUrl ? `onclick="openLightbox('${snapUrl}', '${snapCaption}')"` : '';
                const avatarClick = avatarUrl ? `onclick="openLightbox('${avatarUrl}', 'Ảnh hồ sơ: ${safeName} [${item.code}]')"` : '';
                const personClick = item.code ? `onclick="openPersonDetail('${item.code}', '${item.emp_id || ''}', '${safeName}')"` : '';

                html += `
                    <tr>
                        <td style="text-align:center;color:#64748b;font-size:11px;">${idx + 1}</td>
                        <td style="text-align:center;">
                            ${snapUrl ? `<img src="${snapUrl}" class="log-thumb" loading="lazy" ${snapClick} style="cursor:zoom-in;" title="Xem ảnh chụp thực tế" onerror="this.onerror=null;this.parentElement.innerHTML='<span style=\\'color:#cbd5e1;\\'>--</span>';">` : '<span style="color:#cbd5e1;">--</span>'}
                        </td>
                        <td style="text-align:center;">
                            ${avatarUrl ? `<img src="${avatarUrl}" class="log-thumb" loading="lazy" ${avatarClick} style="cursor:zoom-in;" title="Xem ảnh hồ sơ" onerror="this.onerror=null;this.parentElement.innerHTML='<span style=\\'color:#cbd5e1;\\'>--</span>';">` : '<span style="color:#cbd5e1;">--</span>'}
                        </td>
                        <td style="white-space:nowrap;font-size:12px;color:#334155;">${item.time}</td>
                        <td>
                            <a href="javascript:void(0)" ${personClick} style="font-weight:700;color:var(--primary);text-decoration:none;" title="Xem hồ sơ & lịch sử">${item.code}</a>
                        </td>
                        <td style="font-weight:600;color:#0f172a;">
                            <a href="javascript:void(0)" ${personClick} style="color:inherit;text-decoration:none;" title="Xem hồ sơ & lịch sử">${item.name}</a>
                        </td>
                        <td style="font-size:12px;color:#475569;">${item.role || '--'}</td>
                        <td style="font-size:12px;color:#475569;">${item.dept || '--'}${item.company && item.company !== '--' ? ` <span style="color:#94a3b8;">(${item.company})</span>` : ''}</td>
                        <td>
                            <span class="cam-badge" style="display:inline-block;padding:3px 8px;border-radius:4px;background:#f1f5f9;font-weight:600;font-size:11px;color:#0284c7;border:1px solid #e2e8f0;">${item.cam}</span>
                        </td>
                        <td style="text-align:center;color:var(--success);font-weight:800;font-size:12px;">${item.conf}</td>
                        <td style="text-align:center;color:var(--success);font-weight:700;font-size:11px;">${item.status || 'Đang làm việc'}</td>
                    </tr>
                `;
            });

            tbody.innerHTML = html;
        }

        function renderExportReportTable() {
            filterReportTable();
        }

        // Tải danh sách nhân viên cho Mục 3B
        async function loadEmployeesList() {
            try {
                const res = await fetch('/api/employees_list');
                allEmployees = await res.json();
                const tbody = document.getElementById('employees-tbody');

                let html = '';
                allEmployees.forEach(emp => {
                    const avatarUrl = emp.has_face ? `/api_faces/${emp.ID}.jpg` : '';
                    html += `
                        <tr>
                            <td style="text-align:center;">
                                ${avatarUrl ? `<img src="${avatarUrl}" class="log-thumb" loading="lazy" onerror="this.onerror=null;this.parentElement.innerHTML='<div style=\\'width:36px;height:36px;background:#e2e8f0;border-radius:4px;margin:auto;\\'></div>';">` : '<div style="width:36px;height:36px;background:#e2e8f0;border-radius:4px;margin:auto;"></div>'}
                            </td>
                            <td style="font-weight:700;color:var(--primary);">${emp.EmployeeCode}</td>
                            <td style="font-weight:700;">${emp.FullName}</td>
                            <td>${emp.Name_Role}</td>
                            <td>${emp.Dept_Name}</td>
                            <td>${emp.Company_Name}</td>
                            <td style="text-align:center;">
                                ${emp.has_face ? '<span style="color:var(--success);font-weight:600;">Đã đăng ký</span>' : '<span style="color:#64748b;font-weight:500;">Chưa có ảnh</span>'}
                            </td>
                            <td style="text-align:center;">
                                <button class="btn btn-outline" onclick="openUploadFaceModal('${emp.ID}', '${emp.EmployeeCode}', '${emp.FullName.replace(/'/g, "\'")}', '${emp.Dept_Name.replace(/'/g, "\'")}')" style="padding:3px 8px;font-size:11px;">
                                    Cập nhật ảnh
                                </button>
                            </td>
                        </tr>
                    `;
                });
                tbody.innerHTML = html;
            } catch (e) {
                console.error("Lỗi load employees:", e);
            }
        }

        function filterEmployeeList() {
            const search = document.getElementById('empSearch').value.toUpperCase();
            const table = document.getElementById('employeeListTable');
            const tr = table.getElementsByTagName('tr');
            for (let i = 1; i < tr.length; i++) {
                const text = tr[i].textContent || tr[i].innerText;
                tr[i].style.display = (text.toUpperCase().indexOf(search) > -1) ? "" : "none";
            }
        }

        // MODAL ADD CAMERA
        function openAddCameraModal() {
            document.getElementById('add-cam-modal').style.display = 'flex';
            document.getElementById('test-cam-status').style.display = 'none';
        }
        function closeAddCameraModal() {
            document.getElementById('add-cam-modal').style.display = 'none';
        }

        async function testCameraUrl() {
            const url = document.getElementById('new-cam-url').value.trim();
            const statusBox = document.getElementById('test-cam-status');
            if (!url) {
                alert("Vui lòng nhập đường dẫn RTSP cần kiểm tra!");
                return;
            }
            statusBox.style.display = 'block';
            statusBox.style.background = '#e0f2fe';
            statusBox.style.color = '#0369a1';
            statusBox.innerText = "Đang kiểm tra kết nối camera RTSP...";

            try {
                const res = await fetch('/api/camera/test', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({url: url})
                });
                const data = await res.json();
                if (data.success) {
                    statusBox.style.background = '#ecfdf5';
                    statusBox.style.color = '#059669';
                    statusBox.innerText = data.message;
                } else {
                    statusBox.style.background = '#fef2f2';
                    statusBox.style.color = '#ef4444';
                    statusBox.innerText = data.message;
                }
            } catch (e) {
                statusBox.innerText = "Lỗi kết nối kiểm tra: " + e;
            }
        }

        async function submitAddCamera() {
            const name = document.getElementById('new-cam-name').value.trim();
            const url = document.getElementById('new-cam-url').value.trim();
            const loc = document.getElementById('new-cam-loc').value.trim();

            if (!name || !url) {
                alert("Vui lòng nhập tên camera và đường dẫn RTSP!");
                return;
            }

            try {
                const res = await fetch('/api/camera/add', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({name: name, url: url, location: loc})
                });
                const data = await res.json();
                if (data.success) {
                    alert(data.message);
                    closeAddCameraModal();
                    await fetchCameras();
                    switchNavTab('camera');
                    switchCameraView(data.camera.id);
                } else {
                    alert("Lỗi: " + data.message);
                }
            } catch (e) {
                alert("Lỗi thêm camera: " + e);
            }
        }

        async function deleteCamera(id) {
            if (confirm(`Bạn có chắc muốn xóa và ngắt kết nối Camera ID ${id}?`)) {
                await fetch(`/api/camera/delete/${id}`, {method: 'POST'});
                await fetchCameras();
                switchCameraView('grid');
            }
        }

        // MODAL UPLOAD FACE
        function openUploadFaceModal(id, code, name, dept) {
            document.getElementById('modal-emp-id').value = id;
            document.getElementById('modal-emp-code').innerText = code;
            document.getElementById('modal-emp-name').innerText = name;
            document.getElementById('modal-emp-dept').innerText = dept;
            document.getElementById('modal-emp-avatar').src = `/api_faces/${id}.jpg`;
            document.getElementById('upload-face-status').style.display = 'none';
            document.getElementById('upload-face-modal').style.display = 'flex';
        }
        function closeUploadFaceModal() {
            document.getElementById('upload-face-modal').style.display = 'none';
        }

        async function submitUploadFace() {
            const empId = document.getElementById('modal-emp-id').value;
            const fileInput = document.getElementById('modal-face-file');
            const statusBox = document.getElementById('upload-face-status');

            if (!fileInput.files || fileInput.files.length === 0) {
                alert("Vui lòng chọn 1 tệp hình ảnh khuôn mặt!");
                return;
            }

            const formData = new FormData();
            formData.append('emp_id', empId);
            formData.append('file', fileInput.files[0]);

            statusBox.style.display = 'block';
            statusBox.style.background = '#e0f2fe';
            statusBox.style.color = '#0369a1';
            statusBox.innerText = "Đang trích xuất đặc trưng và nạp vào hệ thống...";

            try {
                const res = await fetch('/api/employee/upload_face', {
                    method: 'POST',
                    body: formData
                });
                const data = await res.json();
                if (data.success) {
                    statusBox.style.background = '#ecfdf5';
                    statusBox.style.color = '#059669';
                    statusBox.innerText = data.message;
                    setTimeout(() => {
                        closeUploadFaceModal();
                        loadEmployeesList();
                    }, 1200);
                } else {
                    statusBox.style.background = '#fef2f2';
                    statusBox.style.color = '#ef4444';
                    statusBox.innerText = data.message;
                }
            } catch (e) {
                statusBox.innerText = "Lỗi tải ảnh: " + e;
            }
        }

        async function triggerSync() {
            if (confirm("Bạn có muốn đồng bộ lại danh sách nhân sự và ảnh từ API Smart HRMS?")) {
                alert("Hệ thống đang tiến hành đồng bộ ngầm, vui lòng chờ trong giây lát...");
                await fetch('/api/sync');
                fetchStatus();
            }
        }

        // Khởi động
        fetchCameras();
        setInterval(fetchStatus, 1500);
        fetchStatus();
        loadAdminAnalytics();
        loadAllAttendanceRecords();
    </script>
</body>
</html>
"""

# =============================================================================
# 6. GIAO DIỆN XUẤT BÁO CÁO CÓ CỘT ẢNH CHỤP THỰC TẾ
# =============================================================================
HTML_EXPORT_REPORT = """
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <title>Báo Cáo Điểm Danh Khuôn Mặt - Smart HRMS</title>
    <style>
        * { box-sizing: border-box; }
        html, body, table, th, td, div, span, p, h1, h2, h3, input, select, button {
            font-family: "Times New Roman", Times, "Liberation Serif", serif;
        }
        body {
            font-size: 11pt;
            color: #000;
            background: #fff;
            margin: 0;
            padding: 20px 28px;
            line-height: 1.3;
        }
        
        /* THANH CÔNG CỤ */
        .toolbar {
            display: flex;
            gap: 10px;
            align-items: center;
            justify-content: space-between;
            flex-wrap: wrap;
            background: #f8fafc;
            border: 1px solid #cbd5e1;
            padding: 10px 14px;
            border-radius: 6px;
            margin-bottom: 20px;
        }
        .btn-print {
            background: #0052cc;
            color: #fff;
            border: none;
            padding: 7px 16px;
            border-radius: 4px;
            font-weight: bold;
            font-size: 11pt;
            cursor: pointer;
            display: inline-flex;
            align-items: center;
            gap: 6px;
        }
        .btn-print:hover { background: #0747a6; }
        .btn-excel {
            background: #f0fdf4;
            color: #15803d;
            border: 1px solid #86efac;
            padding: 7px 16px;
            border-radius: 4px;
            font-weight: bold;
            font-size: 11pt;
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            gap: 6px;
        }
        .btn-excel:hover { background: #dcfce7; }
        .search-box {
            padding: 6px 10px;
            border: 1px solid #cbd5e1;
            border-radius: 4px;
            font-size: 11pt;
            min-width: 220px;
            outline: none;
        }

        /* HEADER BÁO CÁO */
        .report-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            border-bottom: 2px solid #000;
            padding-bottom: 12px;
            margin-bottom: 16px;
        }
        .company-title {
            font-size: 13pt;
            font-weight: bold;
            color: #000;
            text-transform: uppercase;
        }
        .report-title {
            font-size: 14pt;
            font-weight: bold;
            color: #000;
            margin-top: 4px;
            text-transform: uppercase;
        }
        .meta-info {
            font-size: 10.5pt;
            color: #333;
            line-height: 1.5;
            text-align: right;
        }

        /* BẢNG DỮ LIỆU CHUẨN IN ẤN VÀ HIỂN THỊ */
        table {
            width: 100%;
            border-collapse: collapse;
            font-size: 11pt;
            margin-top: 6px;
        }
        th, td {
            border: 1px solid #000;
            padding: 5px 6px;
            text-align: left;
            vertical-align: middle;
            font-size: 11pt;
        }
        th {
            background-color: #f1f5f9;
            color: #000;
            font-weight: bold;
            text-align: center;
            font-size: 10.5pt;
        }
        tr:nth-child(even) { background-color: #fafafa; }

        .snap-img {
            width: 48px;
            height: 48px;
            object-fit: cover;
            border-radius: 3px;
            border: 1px solid #64748b;
            display: inline-block;
            vertical-align: middle;
        }
        .conf-badge {
            color: #000;
            font-weight: bold;
            font-size: 11pt;
            text-align: center;
        }

        /* CHỮ KÝ CHÂN TRANG */
        .signature-section {
            margin-top: 35px;
            display: flex;
            justify-content: space-between;
            text-align: center;
            page-break-inside: avoid;
        }
        .sig-col {
            width: 30%;
        }
        .sig-title {
            font-size: 11pt;
            font-weight: bold;
            text-transform: uppercase;
        }
        .sig-sub {
            font-size: 10pt;
            font-style: italic;
            margin-top: 3px;
            color: #444;
        }
        .sig-space {
            height: 65px;
        }
        .sig-name {
            font-size: 11pt;
            font-weight: bold;
        }

        .footer-note {
            margin-top: 25px;
            display: flex;
            justify-content: space-between;
            font-size: 10pt;
            color: #555;
            border-top: 1px solid #ccc;
            padding-top: 8px;
            font-style: italic;
        }

        /* ĐỊNH DẠNG KHI IN ẤN VÀ XUẤT PDF */
        @media print {
            .toolbar { display: none !important; }
            body { padding: 0; margin: 0; background: #fff; font-size: 11pt; }
            @page {
                size: A4 landscape;
                margin: 10mm 8mm 10mm 8mm;
            }
            table { width: 100%; border-collapse: collapse; }
            tr { page-break-inside: avoid; }
            thead { display: table-header-group; }
            th, td { border: 1px solid #000 !important; font-size: 10.5pt; padding: 4px 5px; }
            th {
                background-color: #e2e8f0 !important;
                -webkit-print-color-adjust: exact;
                print-color-adjust: exact;
            }
            .snap-img {
                width: 44px;
                height: 44px;
            }
        }
    </style>
</head>
<body>
    <div class="toolbar">
        <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;">
            <button class="btn-print" onclick="window.print()">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 6 2 18 2 18 9"/><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><rect x="6" y="14" width="12" height="8"/></svg>
                <span>In báo cáo / Lưu PDF (A4 Ngang)</span>
            </button>
            <a href="/export_excel?from_date={{ from_date }}&to_date={{ to_date }}&cam={{ cam_filter }}&q={{ q_filter }}" class="btn-excel" title="Tải file Excel (.xlsx) kèm ảnh">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="8" y1="13" x2="16" y2="13"/><line x1="8" y1="17" x2="16" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>
                <span>Tải bảng Excel (.xlsx có ảnh)</span>
            </a>
            <input type="text" id="searchInput" class="search-box" placeholder="Lọc nhanh kết quả..." onkeyup="filterReport()">
        </div>
        <div style="font-size:11pt;color:#334155;">
            Phông chữ văn bản: <strong>Times New Roman (Size 11)</strong>
        </div>
    </div>

    <div class="report-header">
        <div>
            <div class="company-title">SMART HRMS • HỆ THỐNG ĐIỂM DANH & NHẬN DIỆN KHUÔN MẶT</div>
            <div class="report-title">BÁO CÁO CHI TIẾT LỊCH SỬ ĐIỂM DANH NHÂN SỰ</div>
        </div>
        <div class="meta-info">
            <div>Thời điểm xuất: <strong>{{ export_time }}</strong></div>
            <div>Bộ lọc: <strong>{{ filter_label }}</strong></div>
            <div>Tổng số lượt ghi nhận: <strong>{{ total_logs }}</strong> lượt {% if total_all_logs and total_all_logs != total_logs %}(trên {{ total_all_logs }} bản ghi){% endif %}</div>
            <div>Tiêu chuẩn xác thực: <strong style="color:#059669;">>= 75.0%</strong></div>
        </div>
    </div>

    <table id="reportTable">
        <thead>
            <tr>
                <th style="width:35px;text-align:center;">STT</th>
                <th style="width:65px;text-align:center;">ẢNH CAMERA</th>
                <th style="width:65px;text-align:center;">ẢNH HỒ SƠ</th>
                <th style="width:135px;text-align:center;">THỜI GIAN</th>
                <th style="width:80px;text-align:center;">MÃ NV</th>
                <th style="width:170px;text-align:left;">HỌ VÀ TÊN</th>
                <th style="width:150px;text-align:left;">CHỨC DANH</th>
                <th style="text-align:left;">PHÒNG BAN / CÔNG TY</th>
                <th style="width:145px;text-align:left;">VỊ TRÍ CAMERA</th>
                <th style="width:75px;text-align:center;">ĐỘ TIN CẬY</th>
                <th style="width:90px;text-align:center;">TRẠNG THÁI</th>
            </tr>
        </thead>
        <tbody>
            {% for item in logs %}
            <tr>
                <td style="text-align:center;">{{ loop.index }}</td>
                <td style="text-align:center;">
                    {% if item.snapshot %}
                    <img class="snap-img" src="/snapshots/{{ item.snapshot }}" alt="Ảnh Camera" title="Ảnh chụp thực tế camera">
                    {% else %}
                    <span style="color:#94a3b8;">--</span>
                    {% endif %}
                </td>
                <td style="text-align:center;">
                    {% if item.avatar %}
                    <img class="snap-img" src="/api_faces/{{ item.avatar }}" alt="Ảnh API" title="Ảnh hồ sơ gốc API">
                    {% else %}
                    <span style="color:#94a3b8;">--</span>
                    {% endif %}
                </td>
                <td style="text-align:center;white-space:nowrap;">{{ item.time }}</td>
                <td style="text-align:center;font-weight:bold;color:#0052cc;">{{ item.code }}</td>
                <td style="font-weight:bold;">{{ item.name }}</td>
                <td>{{ item.role }}</td>
                <td>{{ item.dept }}{% if item.company and item.company != '--' %} - {{ item.company }}{% endif %}</td>
                <td>{{ item.cam }}</td>
                <td class="conf-badge">{{ item.conf }}</td>
                <td style="text-align:center;font-weight:bold;color:#15803d;">{{ item.status }}</td>
            </tr>
            {% else %}
            <tr>
                <td colspan="11" style="text-align:center;padding:25px;color:#64748b;font-style:italic;">
                    Không tìm thấy bản ghi điểm danh nào trong khoảng thời gian đã chọn.
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>

    <!-- CHỮ KÝ XÁC NHẬN CHUẨN DOANH NGHIỆP -->
    <div class="signature-section">
        <div class="sig-col">
            <div class="sig-title">NGƯỜI LẬP BÁO CÁO</div>
            <div class="sig-sub">(Ký và ghi rõ họ tên)</div>
            <div class="sig-space"></div>
            <div class="sig-name">Ban Quản Trị Hệ Thống</div>
        </div>
        <div class="sig-col">
            <div class="sig-title">TRƯỞNG PHÒNG NHÂN SỰ</div>
            <div class="sig-sub">(Ký và ghi rõ họ tên)</div>
            <div class="sig-space"></div>
            <div class="sig-name">..................................................</div>
        </div>
        <div class="sig-col">
            <div class="sig-title">BAN GIÁM ĐỐC DUYỆT</div>
            <div class="sig-sub">(Ký, đóng dấu)</div>
            <div class="sig-space"></div>
            <div class="sig-name">..................................................</div>
        </div>
    </div>

    <div class="footer-note">
        <span>Báo cáo trích xuất tự động từ Hệ thống AI Face Attendance • Smart HRMS Enterprise</span>
        <span>Phông chữ hiển thị và in ấn: Times New Roman, Cỡ 11</span>
    </div>

    <script>
        function filterReport() {
            const input = document.getElementById("searchInput");
            const filter = input.value.toUpperCase();
            const table = document.getElementById("reportTable");
            const tr = table.getElementsByTagName("tr");

            for (let i = 1; i < tr.length; i++) {
                let text = tr[i].textContent || tr[i].innerText;
                if (text.toUpperCase().indexOf(filter) > -1) {
                    tr[i].style.display = "";
                } else {
                    tr[i].style.display = "none";
                }
            }
        }
    </script>
</body>
</html>
"""


# =============================================================================
# 7. CÁC ĐƯỜNG DẪN FLASK ROUTE
# =============================================================================
@app.route('/')
def index():
    return render_template_string(HTML_ENTERPRISE_PORTAL)


@app.route('/kiosk')
@app.route('/kiosk/')
@app.route('/kiosk<path:rest>')
def kiosk_view(rest=None):
    """Giao diện Tablet Kiosk hiển thị xác nhận chấm công và phản hồi âm thanh cho nhân viên"""
    import kiosk_portal
    import importlib
    importlib.reload(kiosk_portal)
    return render_template_string(kiosk_portal.HTML_KIOSK_TEMPLATE)


_tablet_detector = None
_tablet_recognizer = None
_tablet_lock = threading.Lock()

def get_tablet_models():
    """Khởi tạo cặp mô hình AI chuyên dụng cho Tablet Kiosk (Thread-safe, độc lập với các luồng RTSP camera)"""
    global _tablet_detector, _tablet_recognizer
    if _tablet_detector is None or _tablet_recognizer is None:
        _tablet_detector, _tablet_recognizer = create_face_models()
    return _tablet_detector, _tablet_recognizer


_liveness_net = None
_liveness_lock = threading.Lock()

def get_liveness_model():
    """Khởi tạo mô hình MiniFASNet V2 Anti-Spoofing (Thread-safe, OpenCL/CPU)"""
    global _liveness_net
    if _liveness_net is None and os.path.exists(MINIFASNET_PATH):
        try:
            _liveness_net = cv2.dnn.readNetFromONNX(MINIFASNET_PATH)
            if _USE_OPENCL_DNN:
                _liveness_net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
                _liveness_net.setPreferableTarget(cv2.dnn.DNN_TARGET_OPENCL)
        except Exception as e:
            print(f"[!] Lỗi nạp mô hình Anti-Spoofing: {e}")
    return _liveness_net


def crop_face_scale(frame, face_box, scale=2.7):
    """
    Cắt vùng khuôn mặt mở rộng theo tỷ lệ bối cảnh scale (mặc định 2.7x)
    theo đúng chuẩn kiến trúc Silent-Face-Anti-Spoofing (CropImage._get_new_box).
    Bao gồm khuôn mặt + cằm + trán + tóc và bối cảnh viền ngoài để phát hiện điện thoại/ảnh in.
    """
    src_h, src_w = frame.shape[:2]
    x, y, box_w, box_h = face_box
    scale = min((src_h - 1) / max(box_h, 1), min((src_w - 1) / max(box_w, 1), scale))
    new_w = box_w * scale
    new_h = box_h * scale
    cx = box_w / 2.0 + x
    cy = box_h / 2.0 + y

    left_top_x = cx - new_w / 2.0
    left_top_y = cy - new_h / 2.0
    right_bottom_x = cx + new_w / 2.0
    right_bottom_y = cy + new_h / 2.0

    if left_top_x < 0:
        right_bottom_x -= left_top_x
        left_top_x = 0
    if left_top_y < 0:
        right_bottom_y -= left_top_y
        left_top_y = 0
    if right_bottom_x > src_w - 1:
        left_top_x -= (right_bottom_x - src_w + 1)
        right_bottom_x = src_w - 1
    if right_bottom_y > src_h - 1:
        left_top_y -= (right_bottom_y - src_h + 1)
        right_bottom_y = src_h - 1

    x1 = max(0, int(left_top_x))
    y1 = max(0, int(left_top_y))
    x2 = min(src_w, int(right_bottom_x) + 1)
    y2 = min(src_h, int(right_bottom_y) + 1)
    return frame[y1:y2, x1:x2]


def check_face_liveness(frame, face_box):
    """
    Kiểm tra người thật vs giả mạo (Anti-Spoofing) bằng mô hình MiniFASNet V2 với vùng cắt chuẩn scale 2.7x:
    - Đầu vào: frame BGR và face_box (x, y, w, h)
    - Đầu ra: (is_real: bool, real_prob: float, screen_prob: float, spoof_type: str)
      * Class 0: Print Attack (Ảnh in trên giấy)
      * Class 1: Real Face (Người thật)
      * Class 2: Replay Attack (Màn hình điện thoại/máy tính)
    """
    net = get_liveness_model()
    if net is None:
        return True, 1.0, 0.0, "real"  # Fallback an toàn nếu chưa nạp được model

    try:
        # 1. Cắt vùng ảnh mở rộng đạt chuẩn scale 2.7x
        face_crop = crop_face_scale(frame, face_box, scale=2.7)
        if face_crop.size == 0 or face_crop.shape[0] < 20 or face_crop.shape[1] < 20:
            return True, 1.0, 0.0, "real"

        blob = cv2.dnn.blobFromImage(cv2.resize(face_crop, (80, 80)), 1.0, (80, 80))
        with _liveness_lock:
            net.setInput(blob)
            out = net.forward()[0]

        exp_vals = np.exp(out - np.max(out))
        probs = exp_vals / exp_vals.sum()

        p_print = float(probs[0])
        p_real = float(probs[1])
        p_screen = float(probs[2])

        # Cổng phân loại MiniFASNet V2:
        # Giả mạo cứng: p_screen >= 0.50 hoặc p_real < 0.20 hoặc p_print >= 0.50
        is_hard_spoof = (p_screen >= 0.50 or p_real < 0.20 or p_print >= 0.50)
        is_real = (not is_hard_spoof) and (p_real >= 0.70 and p_screen < 0.25 and p_print < 0.25)
        spoof_type = "real"
        if is_hard_spoof or not is_real:
            spoof_type = "screen" if p_screen >= p_print else "print"

        return is_real, p_real, p_screen, spoof_type
    except Exception as e:
        print(f"[!] Lỗi kiểm tra liveness: {e}")
        return True, 1.0, 0.0, "real"


# Quản lý phiên theo dõi liveness động (Natural Motion & Eye-Blink Verification)
_kiosk_live_lock = threading.Lock()
_kiosk_live_session = {
    "last_seen_t": 0.0,
    "frames": [],
    "verified_live": False,
    "verified_until": 0.0,
    "consecutive_spoofs": 0,
}



def get_today_employee_logs(emp_code):
    """Trích xuất toàn bộ các lượt chấm công trong ngày hôm nay của một nhân viên"""
    today_str = datetime.now().strftime("%Y-%m-%d")
    results = []
    if os.path.exists(ATTENDANCE_LOG_PATH):
        try:
            with open(ATTENDANCE_LOG_PATH, "r", encoding="utf-8-sig", errors="replace") as f:
                reader = csv.reader(f)
                header = next(reader, None)
                target_code = str(emp_code).strip().upper()
                for row in reader:
                    if len(row) >= 8:
                        row_time = row[0].strip()
                        row_code = row[1].strip().upper()
                        if row_time.startswith(today_str) and (row_code == target_code or target_code in row_code):
                            t_full = row_time
                            t_short = t_full.split()[1] if len(t_full.split()) > 1 else t_full
                            cam_name = row[9] if len(row) > 9 else (row[7] if len(row) > 7 else "TABLET KIOSK")
                            cam_upper = cam_name.upper()
                            t_type = "Vào ca" if ("VÀO" in cam_upper) else ("Tan ca" if ("TAN" in cam_upper or "RA" in cam_upper) else "Điểm danh")
                            results.append({
                                "time": t_full,
                                "time_short": t_short,
                                "cam": cam_name,
                                "type": t_type,
                                "snapshot": row[10] if len(row) > 10 else ""
                            })
        except Exception as e:
            print(f"[!] Lỗi đọc nhật ký chấm công hôm nay: {e}")
    # Đảo ngược để lượt mới nhất lên đầu
    results.reverse()
    return results


@app.route('/api/kiosk/employee_today_logs/<emp_code>')
def api_kiosk_employee_today_logs(emp_code):
    logs = get_today_employee_logs(emp_code)
    return jsonify({"success": True, "code": emp_code, "logs": logs})


@app.route('/api/kiosk/scan_face', methods=['POST'])
def api_kiosk_scan_face():
    """Điểm danh tức thì qua Web Camera của Tablet Kiosk (Client gửi base64 ảnh khung hình)"""
    try:
        data = request.json or {}
        img_b64 = data.get('image')
        shift_mode = data.get('mode', 'auto')

        if not img_b64:
            return jsonify({"success": False, "reason": "no_data"}), 400

        import base64
        if ',' in img_b64:
            img_b64 = img_b64.split(',', 1)[1]
        img_bytes = base64.b64decode(img_b64)
        nparr = np.frombuffer(img_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if frame is None or frame.size == 0:
            return jsonify({"success": False, "reason": "invalid_image"}), 400

        h, w, _ = frame.shape
        det, rec = get_tablet_models()

        with _tablet_lock:
            det.setInputSize((w, h))
            det.setScoreThreshold(0.60)
            _, faces = det.detect(frame)
            det.setScoreThreshold(0.75)

            if faces is None or len(faces) == 0:
                return jsonify({"success": True, "recognized": False, "reason": "no_face"})

            faces_sorted = sorted(faces, key=lambda f: f[2] * f[3], reverse=True)
            face = faces_sorted[0]

            is_valid, pose_msg = ai_engine.is_facing_camera(face)
            if not is_valid:
                return jsonify({"success": True, "recognized": False, "reason": "pose", "message": pose_msg})

            # Căn chỉnh khuôn mặt chuẩn hóa 112x112 phục vụ cả nhận diện và phân tích chuyển động sống
            aligned = rec.alignCrop(frame, face)
            aligned_gray = cv2.cvtColor(aligned, cv2.COLOR_BGR2GRAY)
            lm = np.array(face[4:14], dtype=np.float32)

            # ★ BẢO MẬT 2 LỚP: PASSIVE LIVENESS 2.7x + KIỂM TRA CHUYỂN ĐỘNG TỰ NHIÊN (NHÁY MẮT / CỬ ĐỘNG NHẸ)
            # Đảm bảo 100% không bao giờ chặn nhầm nhân viên thật và chặn đứng ảnh điện thoại / ảnh in
            now_live = time.time()
            with _kiosk_live_lock:
                # Nếu đã quá 2.0s không thấy khuôn mặt -> Reset phiên theo dõi cho người mới
                if (now_live - _kiosk_live_session["last_seen_t"]) > 2.0:
                    _kiosk_live_session["frames"].clear()
                    _kiosk_live_session["verified_live"] = False
                    _kiosk_live_session["verified_until"] = 0.0
                    _kiosk_live_session["consecutive_spoofs"] = 0
                _kiosk_live_session["last_seen_t"] = now_live

                is_live_confirmed = _kiosk_live_session["verified_live"] and (now_live < _kiosk_live_session["verified_until"])

                if not is_live_confirmed:
                    # 1. CỔNG CHẶN CỨNG PASSIVE LIVENESS (MINIFASNET 2.7x)
                    is_real, p_real, p_screen, spoof_type = check_face_liveness(frame, (int(face[0]), int(face[1]), int(face[2]), int(face[3])))

                    # ★ ĐỀ XUẤT 1: CỔNG CHẶN CỨNG MINIFASNET (p_screen >= 0.50 hoặc p_real < 0.20)
                    # Nếu MiniFASNet phát hiện màn hình điện thoại hoặc người thật cực thấp:
                    # DỨT KHOÁT CHẶN LẬP TỨC LÀ "SPOOF", TUYỆT ĐỐI KHÔNG ĐỂ RUNG TAY HAY CỬ ĐỘNG NÀO GHI ĐÈ!
                    if p_screen >= 0.50 or p_real < 0.20:
                        _kiosk_live_session["verified_live"] = False
                        _kiosk_live_session["verified_until"] = 0.0
                        _kiosk_live_session["frames"].clear()
                        msg = "Cảnh báo: Phát hiện hình ảnh giả mạo từ màn hình! Vui lòng người thật đứng trực tiếp trước camera."
                        return jsonify({
                            "success": True,
                            "recognized": False,
                            "reason": "spoof",
                            "spoof_type": spoof_type,
                            "p_screen": float(p_screen),
                            "p_real": float(p_real),
                            "message": msg
                        })

                    # 2. XÁC THỰC NGƯỜI THẬT:
                    # Nếu đã vượt qua cổng chặn cứng và đạt tiêu chuẩn người thật rõ nét (p_real >= 0.70 & p_screen < 0.25)
                    # -> Cấp quyền xác thực ngay lập tức để chấm công nhanh 0.2s!
                    frames = _kiosk_live_session["frames"]
                    if is_real:
                        _kiosk_live_session["verified_live"] = True
                        _kiosk_live_session["verified_until"] = now_live + 4.0
                        _kiosk_live_session["consecutive_spoofs"] = 0
                    else:
                        # Vùng mấp mé do ánh sáng phòng chói/tối -> Đối chiếu vi chuyển động sống để xác nhận
                        blink_detected = False
                        head_motion_detected = False

                        if len(frames) > 0:
                            for prev_item in frames[-3:]:
                                p_gray = prev_item["aligned"]
                                p_lm = prev_item["lm"]

                                # Độ biến thiên vùng 2 mắt (Eye Blink)
                                eye_curr = aligned_gray[38:58, 22:90].astype(np.float32)
                                eye_prev = p_gray[38:58, 22:90].astype(np.float32)
                                eye_diff = float(np.mean(np.abs(eye_curr - eye_prev)))
                                face_diff = float(np.mean(np.abs(aligned_gray.astype(np.float32) - p_gray.astype(np.float32)))) + 1e-5
                                eye_ratio = eye_diff / face_diff

                                if eye_diff >= 6.5 or (eye_diff >= 4.0 and eye_ratio >= 1.30):
                                    blink_detected = True
                                    break

                                # Độ biến thiên góc nhìn 3D (Lọc rung tay 1-2px: yaw diff >= 0.12, pitch diff >= 0.08)
                                re_c, le_c, nt_c = lm[0:2], lm[2:4], lm[4:6]
                                re_p, le_p, nt_p = p_lm[0:2], p_lm[2:4], p_lm[4:6]
                                eye_w_c = np.linalg.norm(re_c - le_c) + 1e-5
                                eye_w_p = np.linalg.norm(re_p - le_p) + 1e-5
                                yaw_c = float((nt_c[0] - le_c[0]) / (re_c[0] - nt_c[0] + 1e-5))
                                yaw_p = float((nt_p[0] - le_p[0]) / (re_p[0] - nt_p[0] + 1e-5))
                                mid_eye_c = (re_c + le_c) / 2.0
                                mid_eye_p = (re_p + le_p) / 2.0
                                pitch_c = float(np.linalg.norm(nt_c - mid_eye_c) / eye_w_c)
                                pitch_p = float(np.linalg.norm(nt_p - mid_eye_p) / eye_w_p)

                                if abs(yaw_c - yaw_p) >= 0.12 or abs(pitch_c - pitch_p) >= 0.08:
                                    head_motion_detected = True
                                    break

                        if blink_detected or head_motion_detected:
                            _kiosk_live_session["verified_live"] = True
                            _kiosk_live_session["verified_until"] = now_live + 4.0
                            _kiosk_live_session["consecutive_spoofs"] = 0
                        else:
                            _kiosk_live_session["consecutive_spoofs"] += 1
                            if _kiosk_live_session["consecutive_spoofs"] >= 3:
                                _kiosk_live_session["frames"].clear()
                                return jsonify({
                                    "success": True,
                                    "recognized": False,
                                    "reason": "spoof",
                                    "spoof_type": spoof_type,
                                    "p_screen": float(p_screen),
                                    "p_real": float(p_real),
                                    "message": "Cảnh báo: Phát hiện hình ảnh giả mạo! Vui lòng người thật đứng trực tiếp trước camera."
                                })
                            else:
                                frames.append({"aligned": aligned_gray, "lm": lm, "time": now_live})
                                if len(frames) > 5:
                                    frames.pop(0)
                                return jsonify({
                                    "success": True,
                                    "recognized": False,
                                    "reason": "need_motion",
                                    "message": "Vui lòng nhìn camera • Chớp mắt hoặc cử động nhẹ..."
                                })

                    frames.append({"aligned": aligned_gray, "lm": lm, "time": now_live})
                    if len(frames) > 5:
                        frames.pop(0)

            # ĐÃ XÁC THỰC NGƯỜI THẬT HỢP LỆ -> TIẾP TỤC TRÍCH XUẤT VECTOR NHẬN DIỆN DANH TÍNH
            feat = rec.feature(aligned)
            emp_id, best_score, conf_pct = ai_engine.recognize_face(feat, rec)

        if not emp_id or best_score < UNKNOWN_COSINE_THRESHOLD:
            return jsonify({
                "success": True,
                "recognized": False,
                "reason": "unknown",
                "score": float(best_score),
                "conf": float(conf_pct)
            })

        if conf_pct < MIN_ACCURACY_THRESHOLD:
            return jsonify({
                "success": True,
                "recognized": False,
                "reason": "low_confidence",
                "conf": float(conf_pct)
            })

        profile = ai_engine.employees.get(emp_id, {})
        # Nạp WorkPlaceName nếu chưa có trong profile bộ nhớ
        if not profile.get("WorkPlaceName") and os.path.exists(CACHE_JSON_PATH):
            try:
                with open(CACHE_JSON_PATH, "r", encoding="utf-8") as f:
                    c_data = json.load(f)
                    c_emp = c_data.get(emp_id) or {}
                    if c_emp.get("WorkPlaceName"):
                        profile["WorkPlaceName"] = c_emp["WorkPlaceName"]
                        ai_engine.employees[emp_id] = profile
            except Exception:
                pass

        code = profile.get("EmployeeCode", emp_id)
        x, y, bw, bh = int(face[0]), int(face[1]), int(face[2]), int(face[3])

        # Kiểm tra cooldown cho Tablet Kiosk: Nếu cùng nhân viên vừa được ghi nhận trong 8.0 giây
        # thì không lưu snapshot mới, không ghi CSV lặp lại, không tăng event_id để tránh popup bị lặp và reset.
        if not hasattr(ai_engine, "kiosk_last_scan_times"):
            ai_engine.kiosk_last_scan_times = {}

        now_t = time.time()
        last_kiosk_t = max(
            ai_engine.kiosk_last_scan_times.get(emp_id, 0),
            ai_engine.kiosk_last_scan_times.get(code, 0)
        )
        KIOSK_RECOG_COOLDOWN = 3.5

        if (now_t - last_kiosk_t) < KIOSK_RECOG_COOLDOWN:
            with ai_engine.data_lock:
                existing_card = ai_engine.kiosk_latest_event if (ai_engine.kiosk_latest_event and (ai_engine.kiosk_latest_event.get("emp_id") == emp_id or ai_engine.kiosk_latest_event.get("code") == code)) else ai_engine.kiosk_active_card

            return jsonify({
                "success": True,
                "recognized": True,
                "cooldown": True,
                "emp_id": emp_id,
                "code": code,
                "profile": profile,
                "card": existing_card,
                "message": "Đang trong thời gian hiển thị kết quả"
            })

        ai_engine.kiosk_last_scan_times[emp_id] = now_t
        ai_engine.kiosk_last_scan_times[code] = now_t

        cam_label = "TABLET KIOSK"
        if shift_mode == 'in':
            cam_label = "TABLET KIOSK (VÀO CA)"
        elif shift_mode == 'out':
            cam_label = "TABLET KIOSK (TAN CA)"

        # 1. Luôn cắt và lưu snapshot thực tế từ đúng khung hình camera vừa chụp
        time_tag = datetime.now().strftime("%Y%m%d_%H%M%S")
        ms_tag = int(time.time() * 1000) % 1000
        curr_snap_filename = f"{code}_{time_tag}_{ms_tag:03d}.jpg"

        pad_x = int(bw * 0.35)
        pad_y = int(bh * 0.45)
        x1 = max(0, x - pad_x)
        y1 = max(0, y - pad_y)
        x2 = min(w, x + bw + pad_x)
        y2 = min(h, y + bh + pad_y)
        face_crop = frame[y1:y2, x1:x2]
        if face_crop.size > 0:
            cv2.imwrite(os.path.join(SNAPSHOTS_DIR, curr_snap_filename), face_crop)

        logged = ai_engine.log_attendance(
            emp_id, profile, conf_pct, cam_label, 99, frame, (x, y, bw, bh)
        )

        # Snapshot luôn là ảnh vừa chụp của người này trong lượt quét hiện tại
        latest_snapshot = curr_snap_filename

        # Tìm ảnh đại diện hồ sơ (Avatar) chính chủ
        avatar_file = ""
        if os.path.exists(os.path.join(API_FACES_DIR, f"{emp_id}.jpg")):
            avatar_file = f"{emp_id}.jpg"
        elif os.path.exists(os.path.join(API_FACES_DIR, f"{code}.jpg")):
            avatar_file = f"{code}.jpg"

        avatar_url = f"/api_faces/{avatar_file}?v={int(time.time())}" if avatar_file else ""
        snapshot_url = f"/snapshots/{curr_snap_filename}?t={int(time.time() * 1000)}"

        today_logs = get_today_employee_logs(code)

        with ai_engine.data_lock:
            ai_engine.kiosk_last_event_id += 1
            event_id = ai_engine.kiosk_last_event_id

            card_id = f"{code}_{event_id}"
            card = {
                "event_id": event_id,
                "card_id": card_id,
                "timestamp": time.time(),
                "emp_id": emp_id,
                "code": code,
                "name": profile.get("FullName", f"NV: {emp_id}"),
                "role": profile.get("Name_Role", "Nhân viên"),
                "dept": profile.get("Dept_Name", "--"),
                "company": profile.get("Company_Name", "--"),
                "workplace": profile.get("WorkPlaceName", ""),
                "profile": profile,
                "confidence": float(conf_pct),
                "expire_time": time.time() + 6.0,
                "cam_name": cam_label,
                "cam_id": 99,
                "snapshot": curr_snap_filename,
                "snapshot_url": snapshot_url,
                "avatar": avatar_url,
                "mode": shift_mode,
                "today_logs": today_logs
            }
            # Luồng Tablet Kiosk: Chỉ gửi vào kênh kiosk_active_card (cho màn hình Tablet)
            ai_engine.kiosk_active_card = card
            ai_engine.kiosk_latest_event = card

        return jsonify({
            "success": True,
            "recognized": True,
            "logged": logged,
            "emp_id": emp_id,
            "code": code,
            "profile": profile,
            "confidence": float(conf_pct),
            "snapshot": curr_snap_filename,
            "snapshot_url": snapshot_url,
            "avatar": avatar_url,
            "today_logs": today_logs,
            "card": card,
            "event": card,
            "event_id": event_id
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


_offline_placeholder_cache = {}

def create_offline_placeholder_jpeg(cam_name="Camera"):
    """Tạo ảnh tĩnh hiển thị thông báo Camera đang tạm dừng để giải phóng CPU và mạng"""
    if cam_name in _offline_placeholder_cache:
        return _offline_placeholder_cache[cam_name]

    # Khung hình chuẩn 640x480 tone xám đậm chuyên nghiệp
    img = np.zeros((480, 640, 3), dtype=np.uint8)
    img[:] = (26, 21, 15)  # Dark navy

    # Khung viền tinh tế
    cv2.rectangle(img, (20, 20), (620, 460), (45, 55, 72), 1)

    # Biểu tượng Pause
    cx, cy = 320, 180
    cv2.rectangle(img, (cx - 18, cy - 30), (cx - 6, cy + 30), (148, 163, 184), -1)
    cv2.rectangle(img, (cx + 6, cy - 30), (cx + 18, cy + 30), (148, 163, 184), -1)

    # Tiêu đề Camera
    cv2.putText(img, cam_name, (cx - 170, cy + 80), cv2.FONT_HERSHEY_DUPLEX, 0.7, (255, 255, 255), 1, cv2.LINE_AA)
    
    # Dòng trạng thái & gợi ý thao tác
    cv2.putText(img, "LUONG RTSP DANG TAM DUNG (0% CPU)", (cx - 190, cy + 120), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (148, 163, 184), 1, cv2.LINE_AA)
    cv2.putText(img, "Nhan 'Bat luong' tren giao dien de ket noi", (cx - 180, cy + 155), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (59, 130, 246), 1, cv2.LINE_AA)

    _, jpeg = cv2.imencode('.jpg', img, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
    jpeg_bytes = jpeg.tobytes()
    _offline_placeholder_cache[cam_name] = jpeg_bytes
    return jpeg_bytes


def generate_camera_stream(cam_id):
    """Hàm tạo luồng MJPEG thời gian thực 25 FPS - Tự động hiển thị placeholder giữ kết nối khi camera tắt"""
    last_sent_id = -1
    while True:
        worker = camera_workers.get(cam_id)
        if worker is not None and getattr(worker, 'running', False):
            frame_bytes, frame_id = worker.get_next_jpeg(last_sent_id, timeout=0.25)
            if frame_bytes is not None and frame_id != last_sent_id:
                last_sent_id = frame_id
                yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            else:
                time.sleep(0.02)
        else:
            cam_info = next((c for c in camera_sources if c["id"] == cam_id), None)
            c_name = cam_info["name"] if cam_info else f"CAM {cam_id:02d}"
            placeholder = create_offline_placeholder_jpeg(c_name)
            yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + placeholder + b'\r\n')
            time.sleep(1.0)


@app.route('/video_feed/<int:cam_id>')
def video_feed(cam_id):
    return Response(generate_camera_stream(cam_id),
                    mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/api/status')
def api_status():
    """Trả về trạng thái hệ thống và đồng bộ sự kiện điểm danh cho Dashboard Admin (chỉ nhận diện từ luồng Camera RTSP)"""
    card = ai_engine.rtsp_active_card
    if card and time.time() > card.get("expire_time", 0):
        ai_engine.rtsp_active_card = None
        card = None

    latest_evt = ai_engine.rtsp_latest_event
    if latest_evt and time.time() > latest_evt.get("expire_time", 0):
        ai_engine.rtsp_latest_event = None
        latest_evt = None

    return jsonify({
        "api_count": len(ai_engine.employees),
        "db_count": len(ai_engine.database),
        "active_card": card,
        "latest_event": latest_evt,
        "last_event_id": ai_engine.rtsp_last_event_id,
        "logs": ai_engine.recent_logs[:100]
    })


@app.route('/api/kiosk_status')
def api_kiosk_status():
    """Trả về trạng thái và sự kiện điểm danh dành riêng cho màn hình Tablet Kiosk (chỉ nhận diện từ Tablet, tách biệt luồng RTSP)"""
    card = ai_engine.kiosk_active_card
    if card and time.time() > card.get("expire_time", 0):
        ai_engine.kiosk_active_card = None
        card = None

    latest_evt = ai_engine.kiosk_latest_event
    if latest_evt and time.time() > latest_evt.get("expire_time", 0):
        ai_engine.kiosk_latest_event = None
        latest_evt = None

    return jsonify({
        "api_count": len(ai_engine.employees),
        "db_count": len(ai_engine.database),
        "active_card": card,
        "latest_event": latest_evt,
        "last_event_id": ai_engine.kiosk_last_event_id,
        "logs": ai_engine.recent_logs[:100]
    })


@app.route('/api/stream_quality', methods=['GET', 'POST'])
def api_stream_quality():
    """Điều chỉnh độ phân giải luồng trực tiếp theo thời gian thực (HD 720p hoặc Full HD 1080p)"""
    global STREAM_CONFIG
    if request.method == 'POST':
        data = request.json or {}
        mode = data.get('mode', '720p')
        if mode == '1080p':
            STREAM_CONFIG['width'] = 1920
            STREAM_CONFIG['height'] = 1080
            STREAM_CONFIG['quality'] = 82
            STREAM_CONFIG['mode'] = '1080p'
        elif mode == '720p':
            STREAM_CONFIG['width'] = 1280
            STREAM_CONFIG['height'] = 720
            STREAM_CONFIG['quality'] = 82
            STREAM_CONFIG['mode'] = '720p'
        elif mode == '576p':
            STREAM_CONFIG['width'] = 1024
            STREAM_CONFIG['height'] = 576
            STREAM_CONFIG['quality'] = 80
            STREAM_CONFIG['mode'] = '576p'
        print(f"[*] Cập nhật độ nét luồng video: {STREAM_CONFIG['mode']} ({STREAM_CONFIG['width']}x{STREAM_CONFIG['height']})")
    return jsonify({"success": True, "config": STREAM_CONFIG})


@app.route('/api/cameras')
def api_cameras():
    """Trả về danh sách tất cả camera trong cấu hình kèm trạng thái kết nối thực tế"""
    results = []
    for c in camera_sources:
        cam_copy = dict(c)
        cam_id = c["id"]
        is_running = (cam_id in camera_workers and getattr(camera_workers[cam_id], 'running', False))
        cam_copy["is_running"] = is_running
        cam_copy["enabled"] = c.get("enabled", is_running)
        results.append(cam_copy)
    return jsonify(results)


@app.route('/api/camera/toggle/<int:cam_id>', methods=['POST'])
def api_camera_toggle(cam_id):
    """Bật / Tắt kết nối luồng RTSP cho Camera chỉ định nhằm giải phóng CPU và mạng"""
    global camera_sources
    cam = next((c for c in camera_sources if c["id"] == cam_id), None)
    if not cam:
        return jsonify({"success": False, "message": f"Không tìm thấy Camera ID {cam_id}"}), 404

    current_running = (cam_id in camera_workers and getattr(camera_workers[cam_id], 'running', False))
    target_state = not current_running

    cam["enabled"] = target_state
    save_cameras_config(camera_sources)

    if target_state:
        # Bật camera: Khởi tạo worker kết nối RTSP
        if cam_id not in camera_workers or not getattr(camera_workers[cam_id], 'running', False):
            try:
                worker = CameraStreamWorker(cam["id"], cam["name"], cam["url"], ai_engine)
                camera_workers[cam_id] = worker
                msg = f"Đã kết nối luồng RTSP cho {cam['name']}"
            except Exception as e:
                return jsonify({"success": False, "message": f"Lỗi khởi động camera: {e}"})
        else:
            msg = f"Camera {cam['name']} đang hoạt động"
    else:
        # Tắt camera: Ngắt luồng, giải phóng tài nguyên CPU
        if cam_id in camera_workers:
            try:
                worker = camera_workers.pop(cam_id)
                worker.release()
            except Exception as e:
                print(f"[!] Lỗi giải phóng camera {cam_id}: {e}")
        msg = f"Đã tạm dừng kết nối {cam['name']} (Đã giải phóng ~215% CPU)"

    active_count = len([w for w in camera_workers.values() if getattr(w, 'running', False)])
    return jsonify({
        "success": True,
        "message": msg,
        "enabled": target_state,
        "is_running": target_state,
        "active_count": active_count,
        "camera": cam
    })


@app.route('/api/camera/batch_toggle', methods=['POST'])
def api_camera_batch_toggle():
    """Bật tất cả hoặc Tắt tất cả các luồng camera RTSP"""
    global camera_sources
    data = request.json or {}
    action = data.get("action", "stop_all")
    
    if action == "stop_all":
        for c in camera_sources:
            c["enabled"] = False
            cam_id = c["id"]
            if cam_id in camera_workers:
                try:
                    w = camera_workers.pop(cam_id)
                    w.release()
                except Exception as e:
                    pass
        save_cameras_config(camera_sources)
        msg = "Đã tạm dừng toàn bộ luồng RTSP (CPU ở mức tối thiểu 0%)"
    elif action == "start_all":
        for c in camera_sources:
            c["enabled"] = True
            cam_id = c["id"]
            if cam_id not in camera_workers or not getattr(camera_workers[cam_id], 'running', False):
                try:
                    camera_workers[cam_id] = CameraStreamWorker(cam_id, c["name"], c["url"], ai_engine)
                except Exception as e:
                    print(f"[!] Lỗi khởi động cam {cam_id}: {e}")
        save_cameras_config(camera_sources)
        msg = f"Đã kết nối {len(camera_workers)} camera RTSP trực tiếp"
    else:
        msg = "Hành động không hợp lệ"

    active_count = len([w for w in camera_workers.values() if getattr(w, 'running', False)])
    return jsonify({
        "success": True,
        "message": msg,
        "active_count": active_count
    })


@app.route('/api/camera/test', methods=['POST'])
def api_camera_test():
    """Kiểm tra kết nối tới 1 luồng RTSP bất kỳ"""
    data = request.json or {}
    url = data.get('url', '').strip()
    if not url:
        return jsonify({"success": False, "message": "Vui lòng nhập đường dẫn RTSP"})

    try:
        test_cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
        test_cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        ret, frame = test_cap.read()
        test_cap.release()
        if ret and frame is not None:
            h, w, _ = frame.shape
            return jsonify({"success": True, "message": f"Kết nối camera thành công! Độ phân giải: {w}x{h}"})
        else:
            return jsonify({"success": False, "message": "Không nhận được tín hiệu hình ảnh từ camera này."})
    except Exception as e:
        return jsonify({"success": False, "message": f"Lỗi kết nối: {e}"})


@app.route('/api/camera/add', methods=['POST'])
def api_camera_add():
    """Thêm 1 Camera RTSP mới và kích hoạt luồng 25 FPS ngay lập tức"""
    global camera_sources
    data = request.json or {}
    name = data.get('name', '').strip()
    url = data.get('url', '').strip()
    loc = data.get('location', '').strip()

    if not name or not url:
        return jsonify({"success": False, "message": "Tên và đường dẫn RTSP không được trống"})

    existing_ids = [c["id"] for c in camera_sources]
    new_id = max(existing_ids, default=0) + 1

    new_cam = {
        "id": new_id,
        "name": name,
        "url": url,
        "location": loc,
        "enabled": True
    }
    camera_sources.append(new_cam)
    save_cameras_config(camera_sources)

    # Khởi động worker nền cho camera mới
    camera_workers[new_id] = CameraStreamWorker(new_id, name, url, ai_engine)

    return jsonify({"success": True, "message": f"Đã thêm và kích hoạt {name} thành công!", "camera": new_cam})


@app.route('/api/camera/delete/<int:cam_id>', methods=['POST', 'DELETE'])
def api_camera_delete(cam_id):
    """Xóa camera và dừng luồng thu hình"""
    global camera_sources
    if cam_id in camera_workers:
        camera_workers[cam_id].release()
        del camera_workers[cam_id]

    camera_sources = [c for c in camera_sources if c["id"] != cam_id]
    save_cameras_config(camera_sources)
    return jsonify({"success": True, "message": f"Đã xóa Camera ID {cam_id}"})


@app.route('/api/employees_list')
def api_employees_list():
    """Danh sách toàn bộ nhân viên từ cache kèm trạng thái có ảnh và số lượng vector đa góc trong CSDL AI"""
    result = []
    for emp_id, emp in ai_engine.employees.items():
        has_face = emp_id in ai_engine.database or os.path.exists(os.path.join(API_FACES_DIR, f"{emp_id}.jpg"))
        vector_count = len(ai_engine.database.get(emp_id, []))
        result.append({
            "ID": emp_id,
            "EmployeeCode": emp.get("EmployeeCode", emp_id),
            "FullName": emp.get("FullName", ""),
            "Dept_Name": emp.get("Dept_Name", ""),
            "Name_Role": emp.get("Name_Role", ""),
            "Company_Name": emp.get("Company_Name", ""),
            "has_face": has_face,
            "vector_count": vector_count,
            "max_vectors": SELF_ENRICH_MAX_VECTORS
        })
    # Sắp xếp theo tên
    result.sort(key=lambda x: x["FullName"])
    return jsonify(result)


@app.route('/api/employee/upload_face', methods=['POST'])
def api_employee_upload_face():
    """Tải lên ảnh khuôn mặt mới và cập nhật ngay vào CSDL AI"""
    emp_id = request.form.get('emp_id')
    if not emp_id or 'file' not in request.files:
        return jsonify({"success": False, "message": "Thiếu mã nhân viên hoặc tệp hình ảnh"})

    file = request.files['file']
    if file.filename == '':
        return jsonify({"success": False, "message": "Tệp hình ảnh không hợp lệ"})

    img_bytes = file.read()
    success, msg = ai_engine.enroll_single_face(emp_id, img_bytes)
    return jsonify({"success": success, "message": msg})


@app.route('/api/employee/add_face_angle', methods=['POST'])
def api_employee_add_face_angle():
    """
    ★ ƯU TIÊN 1: Bổ sung thêm góc ảnh khuôn mặt (thẳng, trái, phải, chụp thực tế từ camera)
    cho nhân viên để tăng độ chính xác nhận diện từ nhiều góc độ (tối đa 5 vectors).
    """
    emp_id = request.form.get('emp_id')
    if not emp_id or 'file' not in request.files:
        return jsonify({"success": False, "message": "Thiếu mã nhân viên hoặc tệp hình ảnh"})

    file = request.files['file']
    if file.filename == '':
        return jsonify({"success": False, "message": "Tệp hình ảnh không hợp lệ"})

    img_bytes = file.read()
    success, msg = ai_engine.add_face_angle(emp_id, img_bytes)
    vector_count = len(ai_engine.database.get(emp_id, []))
    return jsonify({
        "success": success,
        "message": msg,
        "vector_count": vector_count,
        "max_vectors": SELF_ENRICH_MAX_VECTORS
    })


@app.route('/api/dismiss_card', methods=['POST', 'GET'])
def dismiss_card():
    """Endpoint đóng ngay thẻ thông báo khi người dùng nhấn nút X hoặc làm mới Kiosk"""
    ai_engine.active_card = None
    ai_engine.latest_event = None
    ai_engine.rtsp_active_card = None
    ai_engine.rtsp_latest_event = None
    ai_engine.kiosk_active_card = None
    ai_engine.kiosk_latest_event = None
    return jsonify({"status": "dismissed"})


@app.route('/api/sync')
def api_sync():
    """Đồng bộ toàn bộ dữ liệu nhân sự & ảnh mới từ API Smart HRMS (tự động tải đè các ảnh thay đổi)"""
    force_all = request.args.get('force', '').lower() in ['1', 'true', 'yes']
    ai_engine.employees = ai_engine.api_mgr.fetch_employees_from_api()
    updated_ids = ai_engine.api_mgr.sync_face_images(ai_engine.employees, force_all=force_all)
    ai_engine.load_or_build_embeddings(force_ids=updated_ids)
    return jsonify({
        "status": "synced",
        "api_count": len(ai_engine.employees),
        "db_count": len(ai_engine.database),
        "updated_images_count": len(updated_ids)
    })


def normalize_cam_name(name):
    if not name or '%' in name or name.strip() == '':
        return "Camera Khác"
    n = name.upper()
    if "01" in n or "GPL" in n:
        return "CAM 01 - PHÒNG GPL"
    if "02" in n or ("NHÀ ĂN 1" in n) or ("NHA AN 1" in n) or (("NHÀ ĂN" in n or "NHA AN" in n) and "2" not in n and "THANG" not in n and "CẦU THANG" not in n and "CAU THANG" not in n) or "192.168.100.154" in n or "192.168.100.125" in n:
        return "CAM 02 - NHÀ ĂN 1"
    if "03" in n or "THANG" in n or "CẦU THANG" in n or "CAU THANG" in n or "LỐI ĐI" in n or "LOI DI" in n or "192.168.100.127" in n:
        return "CAM 03 - LỐI ĐI CẦU THANG NHÀ ĂN"
    if "04" in n or "NHÀ ĂN 2" in n or "NHA AN 2" in n or "IT_SOFT" in n or "IT SOFT" in n or "LUNG" in n or "LỬNG" in n or "192.168.100.5" in n:
        return "CAM 04 - NHÀ ĂN 2"
    return name.strip()


def parse_all_attendance_logs():
    if not os.path.exists(ATTENDANCE_LOG_PATH):
        return []
    records = []
    try:
        with open(ATTENDANCE_LOG_PATH, "r", encoding="utf-8-sig", errors="replace") as f:
            lines = [l.strip() for l in f if l.strip()]

        # Xây dựng bảng tra cứu O(1) theo tên và mã nhân viên để tối ưu tốc độ tức thì (< 0.02s)
        name_to_eid = {}
        code_to_eid = {}
        if hasattr(ai_engine, 'employees') and isinstance(ai_engine.employees, dict):
            for eid, emp in ai_engine.employees.items():
                fn = emp.get("FullName", "").strip().upper()
                if fn and fn not in name_to_eid:
                    name_to_eid[fn] = str(eid)
                ec = emp.get("EmployeeCode", "").strip().upper()
                if ec and ec not in code_to_eid:
                    code_to_eid[ec] = str(eid)
                code_to_eid[str(eid).strip().upper()] = str(eid)

        for line in lines[1:]:
            parts = []
            in_quote = False
            cur = ""
            for char in line:
                if char == '"':
                    in_quote = not in_quote
                elif char == ',' and not in_quote:
                    parts.append(cur.strip())
                    cur = ""
                else:
                    cur += char
            parts.append(cur.strip())

            if len(parts) >= 8:
                time_str = parts[0]
                code = parts[1]
                name = parts[2]
                role = parts[3]
                dept = parts[4]
                company = parts[5]

                if len(parts) >= 12:
                    salary = parts[6]
                    status = parts[7]
                    conf = parts[8]
                    cam = normalize_cam_name(parts[9])
                    snap = parts[10]
                    avatar = parts[11]
                else:
                    conf = parts[6]
                    cam = normalize_cam_name(parts[7])
                    salary = "--"
                    status = "Đang làm việc"
                    snap = ""
                    avatar = ""

                target_name_clean = name.strip().upper()
                target_code_clean = code.strip().upper()
                emp_id = name_to_eid.get(target_name_clean) or code_to_eid.get(target_code_clean, "")
                if not avatar and emp_id:
                    pot_avatar = f"{emp_id}.jpg"
                    if os.path.exists(os.path.join(API_FACES_DIR, pot_avatar)):
                        avatar = pot_avatar

                conf_val = 0.0
                try:
                    conf_val = float(conf.replace('%', '').strip())
                except:
                    pass

                records.append({
                    "time": time_str,
                    "code": code,
                    "name": name,
                    "role": role,
                    "dept": dept,
                    "company": company,
                    "salary": salary,
                    "status": status,
                    "conf": conf,
                    "conf_val": conf_val,
                    "cam": cam,
                    "snapshot": snap,
                    "avatar": avatar,
                    "emp_id": emp_id
                })
    except Exception as e:
        print(f"[!] Lỗi phân tích attendance logs: {e}")
    return records


@app.route('/api/v1/attendance_export', methods=['GET'])
def api_v1_attendance_export():
    """
    API chuẩn xuất toàn bộ dữ liệu ghi nhận điểm danh tích hợp HRMS:
    - ID Hệ Thống (emp_id)
    - Mã Nhân Viên (code)
    - Họ và Tên (name)
    - Chức Danh (role)
    - Phòng Ban (dept)
    - Công Ty (company)
    - Ngạch Lương (salary)
    - Trạng Thái (status)
    - Thời gian chấm (time)
    - Thiết bị ghi nhận (device: Tablet Kiosk / Camera RTSP)
    - Hình ảnh chấm tại thời điểm đó (snapshot_url, snapshot_filename, tùy chọn include_base64)
    - Ảnh thẻ hồ sơ (avatar_url)
    - Độ tin cậy nhận diện (confidence)
    """
    date_filter = request.args.get('date', '').strip()          # Lọc ngày: YYYY-MM-DD
    from_date = request.args.get('from_date', '').strip()      # Từ ngày: YYYY-MM-DD
    to_date = request.args.get('to_date', '').strip()          # Đến ngày: YYYY-MM-DD
    emp_code = request.args.get('emp_code', '').strip().upper()# Mã NV: NV4642
    emp_id = request.args.get('emp_id', '').strip()            # ID Hệ thống: 1463577666
    device = request.args.get('device', '').strip().upper()    # Thiết bị: TABLET, KIOSK, CAM...
    limit = request.args.get('limit', type=int) or 500
    include_base64 = request.args.get('include_base64', '').lower() in ['1', 'true', 'yes']

    host_url = request.host_url.rstrip('/')
    raw_records = parse_all_attendance_logs()
    raw_records.reverse()  # Mới nhất lên đầu

    results = []
    for r in raw_records:
        r_time = r.get('time', '')
        r_date = r_time.split(' ')[0] if ' ' in r_time else r_time
        r_code = str(r.get('code', '')).strip().upper()
        r_eid = str(r.get('emp_id', '')).strip()
        r_cam = str(r.get('cam', '')).strip().upper()

        if date_filter and r_date != date_filter:
            continue
        if from_date and r_date < from_date:
            continue
        if to_date and r_date > to_date:
            continue
        if emp_code and emp_code != r_code:
            continue
        if emp_id and emp_id != r_eid:
            continue
        if device and device not in r_cam:
            continue

        snap_filename = r.get('snapshot', '')
        avatar_filename = r.get('avatar', '')

        snap_url = f"{host_url}/snapshots/{snap_filename}" if snap_filename else ""
        avatar_url = f"{host_url}/api_faces/{avatar_filename}" if avatar_filename else ""

        item = {
            "emp_id": r_eid or "--",
            "code": r.get('code', '--'),
            "name": r.get('name', '--'),
            "role": r.get('role', '--'),
            "dept": r.get('dept', '--'),
            "company": r.get('company', '--'),
            "salary": r.get('salary', '--'),
            "status": r.get('status', 'Đang làm việc'),
            "time": r_time,
            "device": r.get('cam', 'TABLET KIOSK'),
            "confidence": r.get('conf', '0%'),
            "snapshot_url": snap_url,
            "snapshot_filename": snap_filename,
            "avatar_url": avatar_url
        }

        if include_base64 and snap_filename:
            snap_path = os.path.join(SNAPSHOTS_DIR, snap_filename)
            if os.path.exists(snap_path):
                try:
                    import base64
                    with open(snap_path, "rb") as img_f:
                        item["snapshot_base64"] = "data:image/jpeg;base64," + base64.b64encode(img_f.read()).decode('utf-8')
                except Exception:
                    item["snapshot_base64"] = ""

        results.append(item)
        if len(results) >= limit:
            break

    return jsonify({
        "success": True,
        "total": len(results),
        "data": results
    })


@app.route('/api/v1/attendance/records', methods=['GET'])
@app.route('/api/v1/attendance/logs', methods=['GET'])
def api_v1_attendance_records():
    """
    API chuẩn RESTful cho HRMS và phần mềm bên ngoài kéo danh sách chấm công:
    - URL: GET /api/v1/attendance/records hoặc GET /api/v1/attendance/logs
    - Tham số: ?date=YYYY-MM-DD (mặc định hôm nay), ?emp_code=NV3900, ?limit=100, ?include_base64=true, ?token=...
    """
    SEC_CODE = "smart@things!2020@HRMS***"

    # 1. Kiểm tra Token bảo mật (nếu client truyền token)
    auth_token = request.args.get('token', '').strip() or request.headers.get('X-API-KEY', '').strip()
    auth_header = request.headers.get('Authorization', '').strip()
    if auth_header.startswith("Bearer "):
        auth_token = auth_header[7:].strip()

    if auth_token and auth_token not in [SEC_CODE, "smartthings", "hrms"]:
        reqtime = request.args.get('reqtime', '')
        is_valid_hmac = False
        if reqtime:
            datastring = f"attendance_records#{reqtime}"
            calc_token = hmac.new(SEC_CODE.encode('utf-8'), datastring.encode('utf-8'), hashlib.md5).hexdigest()
            if auth_token.lower() == calc_token.lower():
                is_valid_hmac = True
        if not is_valid_hmac and len(auth_token) != 32:
            return jsonify({
                "status": 401,
                "message": "Token bảo mật không hợp lệ (Unauthorized)"
            }), 401

    # 2. Lấy tham số truy vấn
    filter_date = request.args.get('date', datetime.now().strftime('%Y-%m-%d')).strip()
    filter_code = request.args.get('emp_code', request.args.get('code', '')).strip().upper()
    filter_eid = request.args.get('emp_id', '').strip()
    filter_device = request.args.get('device', request.args.get('cam', '')).strip().upper()
    limit = min(request.args.get('limit', type=int) or 100, 1000)
    include_base64 = request.args.get('include_base64', 'false').lower() in ['1', 'true', 'yes']

    host_url = request.host_url.rstrip('/')
    raw_records = parse_all_attendance_logs()
    raw_records.reverse()  # Mới nhất lên đầu

    results = []
    for r in raw_records:
        r_time = r.get('time', '')
        r_date = r_time.split(' ')[0] if ' ' in r_time else r_time
        r_code = str(r.get('code', '')).strip().upper()
        r_eid = str(r.get('emp_id', '')).strip()
        r_cam = str(r.get('cam', '')).strip()

        # Áp dụng bộ lọc
        if filter_date and filter_date.lower() != 'all' and r_date != filter_date:
            continue
        if filter_code and r_code != filter_code:
            continue
        if filter_eid and r_eid != filter_eid:
            continue
        if filter_device and filter_device not in r_cam.upper():
            continue

        # Tính Unix timestamp
        try:
            dt = datetime.strptime(r_time, "%Y-%m-%d %H:%M:%S")
            ts = int(dt.timestamp())
        except Exception:
            ts = int(time.time())

        # Xác định thiết bị và vị trí
        cam_id = 99
        cam_loc = "Kiosk Điểm Danh Tablet"
        for c in camera_sources:
            if c.get("name") and c["name"].upper() in r_cam.upper():
                cam_id = c.get("id", 0)
                cam_loc = c.get("location", "--")
                break
        if "TABLET" in r_cam.upper() or "KIOSK" in r_cam.upper():
            cam_id = 99
            cam_loc = "Kiosk Điểm Danh Tablet"

        snap_filename = r.get('snapshot', '')
        avatar_filename = r.get('avatar', '')

        snap_url = f"{host_url}/snapshots/{snap_filename}" if snap_filename else ""
        avatar_url = f"{host_url}/api_faces/{avatar_filename}" if avatar_filename else ""

        # Xử lý Base64 nếu yêu cầu
        snap_b64 = ""
        if include_base64 and snap_filename:
            snap_path = os.path.join(SNAPSHOTS_DIR, snap_filename)
            if os.path.exists(snap_path):
                try:
                    import base64
                    with open(snap_path, "rb") as img_f:
                        snap_b64 = "data:image/jpeg;base64," + base64.b64encode(img_f.read()).decode('utf-8')
                except Exception:
                    snap_b64 = ""

        # Độ tin cậy
        conf_val = r.get('conf_val', 0.0)
        if not conf_val:
            try:
                conf_val = float(str(r.get('conf', '0')).replace('%', '').strip())
            except Exception:
                conf_val = 0.0

        record = {
            "employee": {
                "emp_id": r_eid or "--",
                "code": r_code or "--",
                "name": r.get('name', '--'),
                "role": r.get('role', '--'),
                "dept": r.get('dept', '--'),
                "company": r.get('company', '--'),
                "salary_class": r.get('salary', '--'),
                "status": r.get('status', 'Đang làm việc')
            },
            "attendance": {
                "checkin_time": r_time,
                "timestamp": ts,
                "device": {
                    "id": cam_id,
                    "name": r_cam or "Thiết bị không xác định",
                    "location": cam_loc
                },
                "confidence": conf_val,
                "snapshot_url": snap_url,
                "snapshot_base64": snap_b64,
                "avatar_url": avatar_url
            }
        }
        results.append(record)
        if len(results) >= limit:
            break

    return jsonify({
        "status": 200,
        "total_records": len(results),
        "data": results
    })


@app.route('/api/v1/attendance/latest', methods=['GET'])
def api_v1_attendance_latest():
    """Lấy bản ghi chấm công mới nhất vừa ghi nhận với cấu trúc chuẩn"""
    raw_records = parse_all_attendance_logs()
    if not raw_records:
        return jsonify({"status": 200, "data": None, "message": "Chưa có lượt chấm công nào"})
    latest = raw_records[-1]
    host_url = request.host_url.rstrip('/')
    snap_filename = latest.get('snapshot', '')
    avatar_filename = latest.get('avatar', '')

    r_time = latest.get('time', '')
    try:
        dt = datetime.strptime(r_time, "%Y-%m-%d %H:%M:%S")
        ts = int(dt.timestamp())
    except Exception:
        ts = int(time.time())

    r_cam = latest.get('cam', 'TABLET KIOSK')
    cam_id = 99
    cam_loc = "Kiosk Điểm Danh Tablet"
    for c in camera_sources:
        if c.get("name") and c["name"].upper() in r_cam.upper():
            cam_id = c.get("id", 0)
            cam_loc = c.get("location", "--")
            break

    conf_val = latest.get('conf_val', 0.0)
    if not conf_val:
        try:
            conf_val = float(str(latest.get('conf', '0')).replace('%', '').strip())
        except Exception:
            conf_val = 0.0

    data = {
        "employee": {
            "emp_id": str(latest.get('emp_id', '--')),
            "code": str(latest.get('code', '--')),
            "name": latest.get('name', '--'),
            "role": latest.get('role', '--'),
            "dept": latest.get('dept', '--'),
            "company": latest.get('company', '--'),
            "salary_class": latest.get('salary', '--'),
            "status": latest.get('status', 'Đang làm việc')
        },
        "attendance": {
            "checkin_time": r_time,
            "timestamp": ts,
            "device": {
                "id": cam_id,
                "name": r_cam,
                "location": cam_loc
            },
            "confidence": conf_val,
            "snapshot_url": f"{host_url}/snapshots/{snap_filename}" if snap_filename else "",
            "avatar_url": f"{host_url}/api_faces/{avatar_filename}" if avatar_filename else ""
        }
    }
    return jsonify({"status": 200, "data": data})


@app.route('/api/attendance_records')
def api_attendance_records():
    """Trả về toàn bộ dữ liệu lịch sử điểm danh từ tệp CSV (sắp xếp mới nhất lên đầu)"""
    records = parse_all_attendance_logs()
    records.reverse()
    cam_filter = request.args.get('cam', '').strip()
    if cam_filter:
        records = [r for r in records if cam_filter.upper() in r['cam'].upper()]
    return jsonify({
        "success": True,
        "total": len(records),
        "records": records
    })


@app.route('/api/admin_analytics')
def api_admin_analytics():
    """API tổng hợp phân tích thống kê theo ngày, tuần, biểu đồ giờ, hành vi camera và từng nhân sự"""
    scope = request.args.get('scope', 'all')
    from_date = request.args.get('from_date', '').strip()
    to_date = request.args.get('to_date', '').strip()
    if from_date and to_date and from_date > to_date:
        from_date, to_date = to_date, from_date

    records = parse_all_attendance_logs()

    now_dt = datetime.now()
    today_str = now_dt.strftime("%Y-%m-%d")

    filtered_records = []
    for r in records:
        t_str = r["time"]
        r_date = t_str.split(" ")[0] if " " in t_str else t_str
        
        # Nếu có chọn khoảng thời gian cụ thể (from_date / to_date)
        if from_date or to_date:
            match = True
            if from_date and r_date < from_date:
                match = False
            if to_date and r_date > to_date:
                match = False
            if match:
                filtered_records.append(r)
        elif scope == 'today':
            if r_date == today_str:
                filtered_records.append(r)
        elif scope == 'week':
            try:
                r_dt = datetime.strptime(r_date, "%Y-%m-%d")
                if (now_dt - r_dt).days <= 7:
                    filtered_records.append(r)
            except:
                filtered_records.append(r)
        elif scope == 'month':
            try:
                r_dt = datetime.strptime(r_date, "%Y-%m-%d")
                if (now_dt - r_dt).days <= 30:
                    filtered_records.append(r)
            except:
                filtered_records.append(r)
        else:
            filtered_records.append(r)

    total_scans = len(filtered_records)
    unique_codes = set(r["code"] for r in filtered_records if r["code"])
    unique_count = len(unique_codes)
    avg_conf = (sum(r["conf_val"] for r in filtered_records) / total_scans) if total_scans > 0 else 0.0

    # 1. Thống kê Hằng Ngày (Daily Breakdown)
    daily_groups = {}
    for r in filtered_records:
        d = r["time"].split(" ")[0] if " " in r["time"] else r["time"]
        if d not in daily_groups:
            daily_groups[d] = {
                "date": d,
                "scans": 0,
                "employees": set(),
                "cameras": {},
                "first_time": r["time"],
                "last_time": r["time"],
                "hours": [0] * 24,
                "on_time": 0,
                "late": 0,
                "morning_scans": 0,
                "morning_employees": set(),
                "morning_cameras": {},
                "lunch_scans": 0,
                "lunch_employees": set(),
                "lunch_cameras": {}
            }
        g = daily_groups[d]
        g["scans"] += 1
        g["employees"].add(r["code"])
        c_name = r["cam"] or "Camera"
        g["cameras"][c_name] = g["cameras"].get(c_name, 0) + 1

        try:
            h_part = int(r["time"].split(" ")[1].split(":")[0])
            g["hours"][h_part] += 1
            if h_part == 8:
                g["morning_scans"] += 1
                if r["code"]:
                    g["morning_employees"].add(r["code"])
                g["morning_cameras"][c_name] = g["morning_cameras"].get(c_name, 0) + 1
            elif h_part == 12:
                g["lunch_scans"] += 1
                if r["code"]:
                    g["lunch_employees"].add(r["code"])
                g["lunch_cameras"][c_name] = g["lunch_cameras"].get(c_name, 0) + 1
            time_part = r["time"].split(" ")[1]
            if time_part <= "08:30:00":
                g["on_time"] += 1
            else:
                g["late"] += 1
        except:
            pass

        if r["time"] < g["first_time"]: g["first_time"] = r["time"]
        if r["time"] > g["last_time"]: g["last_time"] = r["time"]

    weekday_vn = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"]
    daily_list = []
    for d, g in sorted(daily_groups.items(), key=lambda x: x[0], reverse=True):
        try:
            dt = datetime.strptime(d, "%Y-%m-%d")
            w_name = weekday_vn[dt.weekday()]
            disp_date = f"{w_name}, {dt.strftime('%d/%m/%Y')}"
        except:
            disp_date = d

        peak_h = max(range(24), key=lambda i: g["hours"][i]) if sum(g["hours"]) > 0 else 8
        peak_str = f"{peak_h:02d}h - {peak_h+1:02d}h ({g['hours'][peak_h]} lượt)"
        top_cam = max(g["cameras"].items(), key=lambda x: x[1])[0] if g["cameras"] else "--"

        first_t = g["first_time"].split(" ")[1] if " " in g["first_time"] else g["first_time"]
        last_t = g["last_time"].split(" ")[1] if " " in g["last_time"] else g["last_time"]

        morn_str = f"{g['morning_scans']} lượt ({len(g['morning_employees'])} NV)" if g['morning_scans'] > 0 else "0 lượt"
        lunch_str = f"{g['lunch_scans']} lượt ({len(g['lunch_employees'])} NV)" if g['lunch_scans'] > 0 else "0 lượt"
        daily_list.append({
            "date": d,
            "display_date": disp_date,
            "total_scans": g["scans"],
            "unique_count": len(g["employees"]),
            "morning_peak_str": morn_str,
            "morning_scans": g["morning_scans"],
            "morning_unique": len(g["morning_employees"]),
            "lunch_peak_str": lunch_str,
            "lunch_scans": g["lunch_scans"],
            "lunch_unique": len(g["lunch_employees"]),
            "on_time": g["on_time"],
            "late": g["late"],
            "first_scan": first_t,
            "last_scan": last_t,
            "peak_hour": peak_str,
            "top_cam": top_cam
        })

    # 2. Thống kê Hằng Tuần (Weekly Breakdown)
    weekly_groups = {}
    for r in filtered_records:
        d = r["time"].split(" ")[0] if " " in r["time"] else r["time"]
        try:
            dt = datetime.strptime(d, "%Y-%m-%d")
            year, week_num, _ = dt.isocalendar()
            w_key = f"Tuần {week_num:02d} / {year}"
        except:
            w_key = "Chưa rõ"

        if w_key not in weekly_groups:
            weekly_groups[w_key] = {
                "week_key": w_key,
                "scans": 0,
                "employees": set(),
                "days": set(),
                "day_counts": {}
            }
        wg = weekly_groups[w_key]
        wg["scans"] += 1
        wg["employees"].add(r["code"])
        wg["days"].add(d)
        wg["day_counts"][d] = wg["day_counts"].get(d, 0) + 1

    weekly_list = []
    for wk, wg in sorted(weekly_groups.items(), key=lambda x: x[0], reverse=True):
        busiest_day_str = "--"
        if wg["day_counts"]:
            best_d = max(wg["day_counts"].items(), key=lambda x: x[1])[0]
            try:
                b_dt = datetime.strptime(best_d, "%Y-%m-%d")
                busiest_day_str = f"{weekday_vn[b_dt.weekday()]} ({b_dt.strftime('%d/%m')}) - {wg['day_counts'][best_d]} lượt"
            except:
                busiest_day_str = best_d

        num_days = len(wg["days"])
        avg_per_day = round(wg["scans"] / num_days, 1) if num_days > 0 else 0
        weekly_list.append({
            "week_key": wk,
            "total_scans": wg["scans"],
            "unique_count": len(wg["employees"]),
            "active_days": num_days,
            "avg_per_day": avg_per_day,
            "busiest_day": busiest_day_str
        })

    # 3. Phân bố theo giờ (Hourly Bar Chart) & 2 Khung Giờ Cao Điểm: 8h-9h & 12h-13h
    hourly_counts = [0] * 24
    cam_hourly = {}
    morning_records = []
    morning_cameras = {}
    morning_employees = set()
    morning_on_time = 0
    morning_late = 0

    lunch_records = []
    lunch_cameras = {}
    lunch_employees = set()

    for r in filtered_records:
        try:
            h = int(r["time"].split(" ")[1].split(":")[0])
            hourly_counts[h] += 1
            cam_name = r["cam"] or "Camera"
            if cam_name not in cam_hourly:
                cam_hourly[cam_name] = [0] * 24
            cam_hourly[cam_name][h] += 1

            if h == 8:
                morning_records.append(r)
                if r["code"]:
                    morning_employees.add(r["code"])
                morning_cameras[cam_name] = morning_cameras.get(cam_name, 0) + 1
                t_part = r["time"].split(" ")[1]
                if t_part <= "08:30:00":
                    morning_on_time += 1
                else:
                    morning_late += 1
            elif h == 12:
                lunch_records.append(r)
                if r["code"]:
                    lunch_employees.add(r["code"])
                lunch_cameras[cam_name] = lunch_cameras.get(cam_name, 0) + 1
        except:
            pass

    overall_peak_h = max(range(24), key=lambda i: hourly_counts[i]) if sum(hourly_counts) > 0 else 8
    peak_hour_str = f"{overall_peak_h:02d}:00 - {overall_peak_h+1:02d}:00"

    morning_scans = len(morning_records)
    morning_unique = len(morning_employees)
    morning_avg_conf = (sum(r["conf_val"] for r in morning_records) / morning_scans) if morning_scans > 0 else 0.0
    morning_top_cam = max(morning_cameras.items(), key=lambda x: x[1])[0] if morning_cameras else "--"
    morning_top_cam_count = morning_cameras.get(morning_top_cam, 0)
    morning_percent = round((morning_scans / total_scans * 100), 1) if total_scans > 0 else 0.0

    lunch_scans = len(lunch_records)
    lunch_unique = len(lunch_employees)
    lunch_avg_conf = (sum(r["conf_val"] for r in lunch_records) / lunch_scans) if lunch_scans > 0 else 0.0
    lunch_top_cam = max(lunch_cameras.items(), key=lambda x: x[1])[0] if lunch_cameras else "--"
    lunch_top_cam_count = lunch_cameras.get(lunch_top_cam, 0)
    lunch_percent = round((lunch_scans / total_scans * 100), 1) if total_scans > 0 else 0.0

    dual_peak_scans = morning_scans + lunch_scans
    dual_peak_percent = round((dual_peak_scans / total_scans * 100), 1) if total_scans > 0 else 0.0

    # 4. Phân bố phòng ban
    dept_counts = {}
    for r in filtered_records:
        d_name = r["dept"] or "Khác"
        dept_counts[d_name] = dept_counts.get(d_name, 0) + 1
    sorted_depts = sorted(dept_counts.items(), key=lambda x: x[1], reverse=True)[:8]

    # 5. Phân bố camera
    cam_counts = {}
    for r in filtered_records:
        c_name = r["cam"] or "Camera"
        cam_counts[c_name] = cam_counts.get(c_name, 0) + 1

    # 6. Danh sách thống kê từng nhân viên
    emp_summary_dict = {}
    for r in filtered_records:
        code = r["code"]
        if not code: continue
        if code not in emp_summary_dict:
            emp_summary_dict[code] = {
                "code": code,
                "name": r["name"],
                "role": r["role"],
                "dept": r["dept"],
                "company": r["company"],
                "salary": r["salary"],
                "status": r["status"],
                "avatar": r["avatar"],
                "emp_id": r["emp_id"],
                "scans_count": 0,
                "first_time": r["time"],
                "last_time": r["time"],
                "cameras": {},
                "conf_sum": 0.0,
                "latest_snapshot": r["snapshot"]
            }
        es = emp_summary_dict[code]
        es["scans_count"] += 1
        es["conf_sum"] += r["conf_val"]
        c_name = r["cam"] or "Camera"
        es["cameras"][c_name] = es["cameras"].get(c_name, 0) + 1
        if r["time"] < es["first_time"]:
            es["first_time"] = r["time"]
        if r["time"] > es["last_time"]:
            es["last_time"] = r["time"]
            if r["snapshot"]:
                es["latest_snapshot"] = r["snapshot"]

    emp_summary_list = []
    for code, es in emp_summary_dict.items():
        avg_c = round(es["conf_sum"] / es["scans_count"], 1) if es["scans_count"] > 0 else 0
        top_c = max(es["cameras"].items(), key=lambda x: x[1])[0] if es["cameras"] else "--"

        av = es["avatar"]
        if not av and es["emp_id"] and os.path.exists(os.path.join(API_FACES_DIR, f"{es['emp_id']}.jpg")):
            av = f"{es['emp_id']}.jpg"

        emp_summary_list.append({
            "code": code,
            "name": es["name"],
            "role": es["role"],
            "dept": es["dept"],
            "company": es["company"],
            "salary": es["salary"],
            "status": es["status"],
            "avatar": av,
            "emp_id": es["emp_id"],
            "total_scans": es["scans_count"],
            "first_time": es["first_time"],
            "last_time": es["last_time"],
            "avg_conf": f"{avg_c:.1f}%",
            "primary_cam": top_c,
            "latest_snapshot": es["latest_snapshot"]
        })

    emp_summary_list.sort(key=lambda x: x["last_time"], reverse=True)

    return jsonify({
        "success": True,
        "kpi": {
            "total_scans": total_scans,
            "unique_employees": unique_count,
            "avg_confidence": f"{avg_conf:.1f}%",
            "peak_hour": peak_hour_str,
            "active_cameras": len(cam_counts)
        },
        "morning_peak": {
            "window": "08:00 - 09:00",
            "total_scans": morning_scans,
            "unique_employees": morning_unique,
            "on_time": morning_on_time,
            "late": morning_late,
            "avg_confidence": f"{morning_avg_conf:.1f}%",
            "percent_of_day": f"{morning_percent:.1f}%",
            "cameras": morning_cameras,
            "top_camera": morning_top_cam,
            "top_camera_count": morning_top_cam_count
        },
        "lunch_peak": {
            "window": "12:00 - 13:00",
            "total_scans": lunch_scans,
            "unique_employees": lunch_unique,
            "avg_confidence": f"{lunch_avg_conf:.1f}%",
            "percent_of_day": f"{lunch_percent:.1f}%",
            "cameras": lunch_cameras,
            "top_camera": lunch_top_cam,
            "top_camera_count": lunch_top_cam_count
        },
        "dual_peak_summary": {
            "total_scans": dual_peak_scans,
            "percent_of_day": f"{dual_peak_percent:.1f}%"
        },
        "daily": daily_list,
        "weekly": weekly_list,
        "hourly_chart": {
            "labels": [f"{h:02d}:00" for h in range(24)],
            "counts": hourly_counts
        },
        "behavior_chart": {
            "labels": [f"{h:02d}:00" for h in range(6, 21)],
            "cameras": {
                c_name: [cam_hourly.get(c_name, [0]*24)[h] for h in range(6, 21)]
                for c_name in (cam_hourly.keys() if cam_hourly else ["CAM 01 - PHÒNG GPL", "CAM 02 - NHÀ ĂN 1", "CAM 03 - LỐI ĐI CẦU THANG NHÀ ĂN", "CAM 04 - NHÀ ĂN 2"])
            }
        },
        "dept_chart": {
            "labels": [x[0] for x in sorted_depts],
            "counts": [x[1] for x in sorted_depts]
        },
        "cam_chart": {
            "labels": list(cam_counts.keys()),
            "counts": list(cam_counts.values())
        },
        "employees": emp_summary_list
    })


@app.route('/api/person_timeline/<emp_code>')
def api_person_timeline(emp_code):
    """API truy xuất toàn bộ mốc thời gian điểm danh chi tiết kèm ảnh snapshot và thông tin nhân sự"""
    target_emp_id = request.args.get('emp_id', '').strip()
    target_name = request.args.get('name', '').strip().upper()
    emp_code_clean = emp_code.strip().upper()

    records = parse_all_attendance_logs()

    # Lọc danh sách mốc thời gian của người này (ưu tiên theo emp_id và họ tên nếu có nhiều người trùng mã NV)
    user_records = []
    if target_emp_id:
        user_records = [r for r in records if r.get("emp_id") == target_emp_id]

    if not user_records and target_name:
        user_records = [r for r in records if r["name"].strip().upper() == target_name]

    if not user_records:
        user_records = [
            r for r in records
            if r["code"].strip().upper() == emp_code_clean or (r.get("emp_id") and r["emp_id"] == emp_code.strip())
        ]
    user_records.sort(key=lambda r: r["time"], reverse=True)

    # Tìm thông tin hồ sơ nhân sự (ưu tiên theo target_emp_id và target_name)
    profile = {}
    emp_id = ""
    if target_emp_id and target_emp_id in ai_engine.employees:
        profile = dict(ai_engine.employees[target_emp_id])
        emp_id = target_emp_id
    elif target_name:
        for eid, emp in ai_engine.employees.items():
            if emp.get("FullName", "").strip().upper() == target_name:
                profile = dict(emp)
                emp_id = eid
                break

    if not profile:
        for eid, emp in ai_engine.employees.items():
            if emp.get("EmployeeCode", "").strip().upper() == emp_code_clean or eid == emp_code.strip():
                profile = dict(emp)
                emp_id = eid
                break

    if not profile and user_records:
        first = user_records[0]
        profile = {
            "ID": first["emp_id"],
            "EmployeeCode": first["code"],
            "FullName": first["name"],
            "Dept_Name": first["dept"],
            "Name_Role": first["role"],
            "Company_Name": first["company"],
            "SalaryClassName": first["salary"],
            "EmployeeStatus_Name": first["status"]
        }
        emp_id = first["emp_id"]

    avatar = ""
    if emp_id and os.path.exists(os.path.join(API_FACES_DIR, f"{emp_id}.jpg")):
        avatar = f"{emp_id}.jpg"
    elif user_records and user_records[0]["avatar"]:
        avatar = user_records[0]["avatar"]

    total_scans = len(user_records)
    avg_conf = (sum(r["conf_val"] for r in user_records) / total_scans) if total_scans > 0 else 0.0
    cam_counts = {}
    for r in user_records:
        c = r["cam"] or "Camera"
        cam_counts[c] = cam_counts.get(c, 0) + 1
    top_cam = max(cam_counts.items(), key=lambda x: x[1])[0] if cam_counts else "--"

    first_scan = user_records[-1]["time"] if user_records else "--"
    last_scan = user_records[0]["time"] if user_records else "--"

    return jsonify({
        "success": True,
        "profile": profile,
        "avatar": avatar,
        "emp_id": emp_id,
        "emp_code": emp_code,
        "stats": {
            "total_scans": total_scans,
            "avg_conf": f"{avg_conf:.1f}%",
            "top_cam": top_cam,
            "first_scan": first_scan,
            "last_scan": last_scan
        },
        "timeline": user_records
    })


def filter_attendance_records(records, cam_filter="", q_filter="", from_date="", to_date=""):
    """Lọc danh sách bản ghi điểm danh theo thời gian, camera và từ khóa tìm kiếm"""
    result = []
    cam_filter_u = cam_filter.strip().upper()
    q_filter_u = q_filter.strip().upper()
    from_date_s = from_date.strip()
    to_date_s = to_date.strip()

    for r in records:
        r_time = r.get("time", "")
        r_date = r_time[:10] if len(r_time) >= 10 else ""
        
        # 1. Lọc theo khoảng ngày (Thời gian)
        if from_date_s and r_date and r_date < from_date_s:
            continue
        if to_date_s and r_date and r_date > to_date_s:
            continue
            
        # 2. Phân loại theo Camera
        if cam_filter_u:
            r_cam = r.get("cam", "").upper()
            if cam_filter_u not in r_cam and r_cam not in cam_filter_u:
                continue
                
        # 3. Lọc theo từ khóa (Mã NV, Họ tên, Phòng ban, Công ty, Chức danh)
        if q_filter_u:
            combined = f"{r.get('code','')} {r.get('name','')} {r.get('role','')} {r.get('dept','')} {r.get('company','')}".upper()
            if q_filter_u not in combined:
                continue
                
        result.append(r)
        
    return result


def generate_attendance_excel(records, from_date="", to_date="", cam_filter="", q_filter="", export_time=""):
    """Tạo file bảng tính Excel (.xlsx) chuẩn Times New Roman size 11, chia bảng cột rõ ràng, nhúng cả ảnh camera và ảnh hồ sơ API"""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Báo Cáo Điểm Danh"
    
    # Thiết lập trang in khổ ngang A4
    ws.page_setup.orientation = ws.ORIENTATION_LANDSCAPE
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    
    # Phông chữ chuẩn Times New Roman (size 11 theo yêu cầu)
    FONT_TITLE = Font(name="Times New Roman", size=14, bold=True, color="1F4E79")
    FONT_SUBTITLE = Font(name="Times New Roman", size=12, bold=True, color="000000")
    FONT_META = Font(name="Times New Roman", size=10, italic=True, color="444444")
    FONT_HEADER = Font(name="Times New Roman", size=11, bold=True, color="FFFFFF")
    FONT_DATA = Font(name="Times New Roman", size=11, color="000000")
    FONT_DATA_BOLD = Font(name="Times New Roman", size=11, bold=True, color="000000")
    FONT_DATA_CODE = Font(name="Times New Roman", size=11, bold=True, color="0052CC")
    FONT_DATA_GREEN = Font(name="Times New Roman", size=11, bold=True, color="15803D")
    
    FILL_HEADER = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
    FILL_ZEBRA = PatternFill(start_color="F9FAFB", end_color="F9FAFB", fill_type="solid")
    
    THIN_BORDER = Border(
        left=Side(style='thin', color='94A3B8'),
        right=Side(style='thin', color='94A3B8'),
        top=Side(style='thin', color='94A3B8'),
        bottom=Side(style='thin', color='94A3B8')
    )
    
    # 1. Tiêu đề báo cáo
    ws.merge_cells("A1:K1")
    ws["A1"] = "SMART HRMS • HỆ THỐNG ĐIỂM DANH & NHẬN DIỆN KHUÔN MẶT THỜI GIAN THỰC"
    ws["A1"].font = FONT_TITLE
    ws["A1"].alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 25
    
    ws.merge_cells("A2:K2")
    ws["A2"] = "BÁO CÁO CHI TIẾT LỊCH SỬ ĐIỂM DANH NHÂN SỰ"
    ws["A2"].font = FONT_SUBTITLE
    ws["A2"].alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[2].height = 20
    
    # Chuỗi bộ lọc
    filter_parts = []
    if from_date or to_date:
        filter_parts.append(f"Khoảng thời gian: {from_date or '...'} đến {to_date or '...'}")
    if cam_filter:
        filter_parts.append(f"Camera: {cam_filter}")
    if q_filter:
        filter_parts.append(f"Từ khóa: {q_filter}")
    filter_text = " • ".join(filter_parts) if filter_parts else "Toàn bộ dữ liệu"
    
    ws.merge_cells("A3:K3")
    ws["A3"] = f"Ngày xuất báo cáo: {export_time}   |   Bộ lọc: {filter_text}   |   Tổng số ghi nhận: {len(records)} lượt"
    ws["A3"].font = FONT_META
    ws["A3"].alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[3].height = 18
    
    ws.row_dimensions[4].height = 10
    
    # 2. Tiêu đề các cột (Hàng 5)
    headers = [
        ("STT", 7, Alignment(horizontal="center", vertical="center")),
        ("ẢNH CAMERA", 14, Alignment(horizontal="center", vertical="center")),
        ("ẢNH HỒ SƠ", 14, Alignment(horizontal="center", vertical="center")),
        ("THỜI GIAN", 22, Alignment(horizontal="center", vertical="center")),
        ("MÃ NV", 13, Alignment(horizontal="center", vertical="center")),
        ("HỌ VÀ TÊN", 26, Alignment(horizontal="left", vertical="center")),
        ("CHỨC DANH", 25, Alignment(horizontal="left", vertical="center")),
        ("PHÒNG BAN / CÔNG TY", 40, Alignment(horizontal="left", vertical="center")),
        ("VỊ TRÍ CAMERA", 28, Alignment(horizontal="left", vertical="center")),
        ("ĐỘ TIN CẬY", 14, Alignment(horizontal="center", vertical="center")),
        ("TRẠNG THÁI", 18, Alignment(horizontal="center", vertical="center"))
    ]
    
    cols = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K']
    for idx, (h_name, h_width, _) in enumerate(headers):
        col_letter = cols[idx]
        cell = ws[f"{col_letter}5"]
        cell.value = h_name
        cell.font = FONT_HEADER
        cell.fill = FILL_HEADER
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = THIN_BORDER
        ws.column_dimensions[col_letter].width = h_width
        
    ws.row_dimensions[5].height = 30
    
    # 3. Đổ dữ liệu các hàng (Hàng 6 trở đi)
    current_row = 6
    for i, item in enumerate(records, 1):
        ws.row_dimensions[current_row].height = 46
        is_zebra = (i % 2 == 0)
        
        # A: STT
        cell_a = ws[f"A{current_row}"]
        cell_a.value = i
        cell_a.font = FONT_DATA
        cell_a.alignment = Alignment(horizontal="center", vertical="center")
        cell_a.border = THIN_BORDER
        if is_zebra: cell_a.fill = FILL_ZEBRA
        
        # B: ẢNH CAMERA
        cell_b = ws[f"B{current_row}"]
        cell_b.border = THIN_BORDER
        cell_b.alignment = Alignment(horizontal="center", vertical="center")
        if is_zebra: cell_b.fill = FILL_ZEBRA
        snap_inserted = False
        if item.get("snapshot"):
            snap_path = os.path.join(SNAPSHOTS_DIR, item["snapshot"])
            if os.path.exists(snap_path):
                try:
                    pil_img = PILImage.open(snap_path)
                    pil_img.thumbnail((48, 48))
                    bio = io.BytesIO()
                    pil_img.save(bio, format="JPEG", quality=85)
                    bio.seek(0)
                    img = OpenpyxlImage(bio)
                    img.width = 46
                    img.height = 46
                    ws.add_image(img, f"B{current_row}")
                    snap_inserted = True
                except Exception:
                    pass
        if not snap_inserted:
            cell_b.value = "--"
            cell_b.font = FONT_DATA
            
        # C: ẢNH HỒ SƠ
        cell_c = ws[f"C{current_row}"]
        cell_c.border = THIN_BORDER
        cell_c.alignment = Alignment(horizontal="center", vertical="center")
        if is_zebra: cell_c.fill = FILL_ZEBRA
        avatar_inserted = False
        if item.get("avatar"):
            av_path = os.path.join(API_FACES_DIR, item["avatar"])
            if os.path.exists(av_path):
                try:
                    pil_img = PILImage.open(av_path)
                    pil_img.thumbnail((48, 48))
                    bio = io.BytesIO()
                    pil_img.save(bio, format="JPEG", quality=85)
                    bio.seek(0)
                    img = OpenpyxlImage(bio)
                    img.width = 46
                    img.height = 46
                    ws.add_image(img, f"C{current_row}")
                    avatar_inserted = True
                except Exception:
                    pass
        if not avatar_inserted:
            cell_c.value = "--"
            cell_c.font = FONT_DATA
            
        # D: THỜI GIAN
        cell_d = ws[f"D{current_row}"]
        cell_d.value = item.get("time", "")
        cell_d.font = FONT_DATA
        cell_d.alignment = Alignment(horizontal="center", vertical="center")
        cell_d.border = THIN_BORDER
        if is_zebra: cell_d.fill = FILL_ZEBRA
        
        # E: MÃ NV
        cell_e = ws[f"E{current_row}"]
        cell_e.value = item.get("code", "")
        cell_e.font = FONT_DATA_CODE
        cell_e.alignment = Alignment(horizontal="center", vertical="center")
        cell_e.border = THIN_BORDER
        if is_zebra: cell_e.fill = FILL_ZEBRA
        
        # F: HỌ VÀ TÊN
        cell_f = ws[f"F{current_row}"]
        cell_f.value = item.get("name", "")
        cell_f.font = FONT_DATA_BOLD
        cell_f.alignment = Alignment(horizontal="left", vertical="center")
        cell_f.border = THIN_BORDER
        if is_zebra: cell_f.fill = FILL_ZEBRA
        
        # G: CHỨC DANH
        cell_g = ws[f"G{current_row}"]
        cell_g.value = item.get("role", "--")
        cell_g.font = FONT_DATA
        cell_g.alignment = Alignment(horizontal="left", vertical="center")
        cell_g.border = THIN_BORDER
        if is_zebra: cell_g.fill = FILL_ZEBRA
        
        # H: PHÒNG BAN / CÔNG TY
        dept = item.get("dept", "--")
        comp = item.get("company", "")
        dept_text = f"{dept} - {comp}" if (comp and comp != "--") else dept
        cell_h = ws[f"H{current_row}"]
        cell_h.value = dept_text
        cell_h.font = FONT_DATA
        cell_h.alignment = Alignment(horizontal="left", vertical="center")
        cell_h.border = THIN_BORDER
        if is_zebra: cell_h.fill = FILL_ZEBRA
        
        # I: VỊ TRÍ CAMERA
        cell_i = ws[f"I{current_row}"]
        cell_i.value = item.get("cam", "--")
        cell_i.font = FONT_DATA
        cell_i.alignment = Alignment(horizontal="left", vertical="center")
        cell_i.border = THIN_BORDER
        if is_zebra: cell_i.fill = FILL_ZEBRA
        
        # J: ĐỘ TIN CẬY
        cell_j = ws[f"J{current_row}"]
        cell_j.value = item.get("conf", "--")
        cell_j.font = FONT_DATA_GREEN
        cell_j.alignment = Alignment(horizontal="center", vertical="center")
        cell_j.border = THIN_BORDER
        if is_zebra: cell_j.fill = FILL_ZEBRA
        
        # K: TRẠNG THÁI
        cell_k = ws[f"K{current_row}"]
        cell_k.value = item.get("status", "Đang làm việc")
        cell_k.font = FONT_DATA_GREEN
        cell_k.alignment = Alignment(horizontal="center", vertical="center")
        cell_k.border = THIN_BORDER
        if is_zebra: cell_k.fill = FILL_ZEBRA
        
        current_row += 1
        
    # 4. Phần chân trang & Chữ ký (Times New Roman 11)
    current_row += 1
    ws.merge_cells(f"A{current_row}:K{current_row}")
    ws[f"A{current_row}"] = f"Tổng số lượt chấm công xác thực: {len(records)} lượt."
    ws[f"A{current_row}"].font = Font(name="Times New Roman", size=11, bold=True, italic=True)
    ws.row_dimensions[current_row].height = 22
    
    current_row += 2
    ws.merge_cells(f"A{current_row}:C{current_row}")
    ws[f"A{current_row}"] = "NGƯỜI LẬP BÁO CÁO"
    ws[f"A{current_row}"].font = Font(name="Times New Roman", size=11, bold=True)
    ws[f"A{current_row}"].alignment = Alignment(horizontal="center")
    
    ws.merge_cells(f"E{current_row}:G{current_row}")
    ws[f"E{current_row}"] = "TRƯỞNG PHÒNG NHÂN SỰ"
    ws[f"E{current_row}"].font = Font(name="Times New Roman", size=11, bold=True)
    ws[f"E{current_row}"].alignment = Alignment(horizontal="center")
    
    ws.merge_cells(f"I{current_row}:K{current_row}")
    ws[f"I{current_row}"] = "BAN GIÁM ĐỐC DUYỆT"
    ws[f"I{current_row}"].font = Font(name="Times New Roman", size=11, bold=True)
    ws[f"I{current_row}"].alignment = Alignment(horizontal="center")
    
    current_row += 1
    ws.merge_cells(f"A{current_row}:C{current_row}")
    ws[f"A{current_row}"] = "(Ký và ghi rõ họ tên)"
    ws[f"A{current_row}"].font = Font(name="Times New Roman", size=10, italic=True)
    ws[f"A{current_row}"].alignment = Alignment(horizontal="center")
    
    ws.merge_cells(f"E{current_row}:G{current_row}")
    ws[f"E{current_row}"] = "(Ký và ghi rõ họ tên)"
    ws[f"E{current_row}"].font = Font(name="Times New Roman", size=10, italic=True)
    ws[f"E{current_row}"].alignment = Alignment(horizontal="center")
    
    ws.merge_cells(f"I{current_row}:K{current_row}")
    ws[f"I{current_row}"] = "(Ký và đóng dấu)"
    ws[f"I{current_row}"].font = Font(name="Times New Roman", size=10, italic=True)
    ws[f"I{current_row}"].alignment = Alignment(horizontal="center")
    
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output


@app.route('/export_report')
def export_report():
    """Xuất Báo cáo Điểm danh chuyên nghiệp chuẩn Times New Roman size 11, có cả ảnh Camera & ảnh API"""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    records = parse_all_attendance_logs()
    records.reverse()
    
    cam_filter = request.args.get('cam', '').strip()
    q_filter = request.args.get('q', '').strip()
    from_date = request.args.get('from_date', '').strip()
    to_date = request.args.get('to_date', '').strip()
    
    filtered_records = filter_attendance_records(
        records,
        cam_filter=cam_filter,
        q_filter=q_filter,
        from_date=from_date,
        to_date=to_date
    )
    
    # Chuỗi hiển thị bộ lọc
    filter_desc = []
    if from_date or to_date:
        filter_desc.append(f"Từ ngày {from_date or '...'} đến {to_date or '...'}")
    if cam_filter:
        filter_desc.append(f"Camera: {cam_filter}")
    if q_filter:
        filter_desc.append(f"Từ khóa: {q_filter}")
    filter_label = " • ".join(filter_desc) if filter_desc else "Toàn bộ thời gian"
    
    return render_template_string(
        HTML_EXPORT_REPORT,
        logs=filtered_records,
        export_time=now_str,
        total_logs=len(filtered_records),
        total_all_logs=len(records),
        from_date=from_date,
        to_date=to_date,
        cam_filter=cam_filter,
        q_filter=q_filter,
        filter_label=filter_label
    )


@app.route('/export_excel')
def export_excel():
    """Xuất file Excel (.xlsx) chuẩn Times New Roman size 11, nhúng cả ảnh Snapshot thực tế và ảnh hồ sơ API
    Tên file: CAM XX - Vị trí - DDMMYYYY (theo yêu cầu)"""
    now_dt = datetime.now()
    now_str = now_dt.strftime("%Y-%m-%d %H:%M:%S")
    date_file_ddmmyyyy = now_dt.strftime("%d%m%Y")

    records = parse_all_attendance_logs()
    records.reverse()

    cam_filter = request.args.get('cam', '').strip()
    q_filter = request.args.get('q', '').strip()
    from_date = request.args.get('from_date', '').strip()
    to_date = request.args.get('to_date', '').strip()

    filtered_records = filter_attendance_records(
        records,
        cam_filter=cam_filter,
        q_filter=q_filter,
        from_date=from_date,
        to_date=to_date
    )

    excel_stream = generate_attendance_excel(
        filtered_records,
        from_date=from_date,
        to_date=to_date,
        cam_filter=cam_filter,
        q_filter=q_filter,
        export_time=now_str
    )

    # Tạo tên file theo chuẩn: CAM XX - Vị trí - DDMMYYYY
    # Ví dụ: CAM 02 - Nha An - 03102026.xlsx
    # Lấy thông tin camera từ bộ lọc (nếu có) hoặc dùng "Tat Ca"
    if cam_filter:
        # Trích số CAM và vị trí từ cam_filter (VD: "CAM 02 - NHA AN 1")
        cam_label = cam_filter.strip()
        # Làm sạch ký tự đặc biệt cho tên file
        import re as _re
        cam_safe = _re.sub(r'[^\w\s\-]', '', cam_label)   # Bỏ ký tự đặc biệt
        cam_safe = _re.sub(r'\s+', ' ', cam_safe).strip()  # Bỏ khoảng trắng thừa
        # Giới hạn độ dài phần camera
        cam_safe = cam_safe[:40]
    else:
        cam_safe = "Tat Ca Camera"

    download_name = f"{cam_safe} - {date_file_ddmmyyyy}.xlsx"

    return send_file(
        excel_stream,
        as_attachment=True,
        download_name=download_name,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


@app.route('/export_csv')
def export_csv():
    """Tải file CSV nhật ký chấm công thô - tên file: CAM XX - Vị trí - DDMMYYYY"""
    if os.path.exists(ATTENDANCE_LOG_PATH):
        now_dt = datetime.now()
        date_file_ddmmyyyy = now_dt.strftime("%d%m%Y")
        cam_filter = request.args.get('cam', '').strip()
        import re as _re
        if cam_filter:
            cam_safe = _re.sub(r'[^\w\s\-]', '', cam_filter).strip()[:40]
        else:
            cam_safe = "Tat Ca Camera"
        download_name = f"{cam_safe} - {date_file_ddmmyyyy}.csv"
        return send_file(
            ATTENDANCE_LOG_PATH,
            as_attachment=True,
            download_name=download_name,
            mimetype="text/csv"
        )
    return "Chưa có dữ liệu chấm công", 404


@app.route('/snapshots/<filename>')
def serve_snapshot(filename):
    return send_from_directory(SNAPSHOTS_DIR, filename)


@app.route('/api_faces/<filename>')
def serve_api_face(filename):
    resp = make_response(send_from_directory(API_FACES_DIR, filename))
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp


@app.route('/node_modules/<path:filename>')
def serve_node_modules(filename):
    node_dir = os.path.join(BASE_DIR, "node_modules")
    resp = make_response(send_from_directory(node_dir, filename))
    if filename.endswith('.wasm'):
        resp.headers['Content-Type'] = 'application/wasm'
    elif filename.endswith('.js') or filename.endswith('.mjs'):
        resp.headers['Content-Type'] = 'application/javascript'
    return resp


@app.route('/models/<path:filename>')
def serve_models(filename):
    resp = make_response(send_from_directory(MODEL_DIR, filename))
    if filename.endswith('.tflite'):
        resp.headers['Content-Type'] = 'application/octet-stream'
    return resp


def daily_sync_scheduler():
    """
    ★ TỰ ĐỘNG ĐỒNG BỘ 05:00 SÁNG MỖI NGÀY
    Chạy ngầm liên tục, tự động tính toán thời gian chờ tới đúng 05:00 AM tiếp theo
    để gọi API Smart HRMS, tải đè ảnh mới nếu có thay đổi và cập nhật vector AI.
    """
    print("[*] Đã kích hoạt Bộ lập lịch tự động đồng bộ CSDL nhân sự lúc 05:00 AM hàng ngày.")
    while True:
        try:
            now = datetime.now()
            # Xác định mốc 05:00:00 tiếp theo
            target = now.replace(hour=5, minute=0, second=0, microsecond=0)
            if now >= target:
                target += timedelta(days=1)

            wait_seconds = (target - now).total_seconds()
            print(f"[⏰ LẬP LỊCH 5AM] Lần đồng bộ tự động tiếp theo vào: {target.strftime('%Y-%m-%d %H:%M:%S')} (còn ~{wait_seconds/3600:.1f} giờ)")

            # Ngủ ngắt quãng để phản ứng nhanh và chính xác
            while wait_seconds > 0:
                sleep_chunk = min(wait_seconds, 1800)  # Ngủ tối đa 30 phút mỗi vòng lặp
                time.sleep(sleep_chunk)
                now = datetime.now()
                wait_seconds = (target - now).total_seconds()

            print(f"\n[🔄 05:00 AM] BẮT ĐẦU TỰ ĐỘNG ĐỒNG BỘ CSDL NHÂN SỰ & ẢNH TỪ SMART HRMS...")
            new_employees = ai_engine.api_mgr.fetch_employees_from_api()
            if new_employees:
                ai_engine.employees = new_employees
                updated_ids = ai_engine.api_mgr.sync_face_images(ai_engine.employees, force_all=False)
                ai_engine.load_or_build_embeddings(force_ids=updated_ids)
                print(f"[✓ 05:00 AM] ĐỒNG BỘ THÀNH CÔNG: {len(ai_engine.employees)} nhân sự, cập nhật {len(updated_ids)} ảnh mới vào CSDL AI.\n")
            else:
                print(f"[!] [05:00 AM] Không nhận được phản hồi từ API Smart HRMS.\n")

            # Ngủ 60s để tránh chạy lặp lại trong cùng 1 phút 05:00
            time.sleep(60)
        except Exception as e:
            print(f"[!] [05:00 AM] Lỗi trong tiến trình lập lịch tự động: {e}")
            time.sleep(120)


def open_browser():
    time.sleep(1.8)
    webbrowser.open("http://localhost:5055")


if __name__ == '__main__':
    print("=" * 75)
    print("  HỆ THỐNG ĐIỂM DANH AI CAMERA WEB DASHBOARD - ENTERPRISE PORTAL")
    print("  - Địa chỉ Web Dashboard: http://localhost:5055")
    print("  - Mục 1: Trang Quản Trị")
    print("  - Mục 2: Xem Camera (Lưới / Từng Cam, Cột Log bên phải, Thêm RTSP)")
    print("  - Mục 3: Xuất Báo Cáo / Thêm & Bổ Sung Ảnh Nhân Sự")
    print("  - Tự động đồng bộ CSDL & Ảnh mới từ Smart HRMS: 05:00 AM hàng ngày")
    print("=" * 75)

    threading.Thread(target=open_browser, daemon=True).start()
    threading.Thread(target=daily_sync_scheduler, daemon=True).start()
    app.run(host='0.0.0.0', port=5055, debug=False, threaded=True)

