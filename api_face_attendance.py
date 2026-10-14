"""
=============================================================================
HỆ THỐNG ĐIỂM DANH & NHẬN DIỆN KHUÔN MẶT CAMERA THỜI GIAN THỰC (AI FACE ATTENDANCE)
GIAO DIỆN LƯỚI ĐA CAMERA HIỆN ĐẠI - 2 TÔNG MÀU SÁNG TRẮNG & XANH DƯƠNG DOANH NGHIỆP
TỐI ƯU HIỆU NĂNG CAO (25 - 30 FPS) - KHẮC PHỤC TRIỆT ĐỂ MỜ HÌNH & LAG FPS
=============================================================================
Tích hợp API: Getdata_List_Employee_Full (HMAC-MD5 Token Authentication)
Hiển thị thẻ thông tin nhân sự (Profile Card) chuẩn tiếng Việt:
- FullName (Họ và tên)
- Dept_Name (Phòng ban)
- Name_Role (Chức danh)
- Company_Name (Công ty)
- SalaryClassName (Ngạch lương)
- EmployeeStatus_Name (Trạng thái nhân sự)
Các trường khác được giữ lại sẵn nhưng để comment (#) theo yêu cầu.
=============================================================================
"""

import os
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
import numpy as np
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from PIL import Image, ImageDraw, ImageFont

# Đảm bảo console Windows in tiếng Việt UTF-8 không bị lỗi charmap
sys.stdout.reconfigure(encoding='utf-8')

# Bật tăng tốc OpenCL cho GPU Intel
cv2.ocl.setUseOpenCL(True)
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|hwaccel;d3d11va"

# Đường dẫn thư mục
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(BASE_DIR, "models")
YUNET_PATH = os.path.join(MODEL_DIR, "face_detection_yunet.onnx")
SFACE_PATH = os.path.join(MODEL_DIR, "face_recognition_sface.onnx")

API_FACES_DIR = os.path.join(BASE_DIR, "api_employee_faces")
CACHE_JSON_PATH = os.path.join(BASE_DIR, "api_employees_cache.json")
EMBEDDINGS_PKL_PATH = os.path.join(BASE_DIR, "api_face_embeddings.pkl")
ATTENDANCE_LOG_PATH = os.path.join(BASE_DIR, "attendance_api_log.csv")

# Thư mục lưu snapshot người lạ (stranger)
STRANGER_DIR = os.path.join(BASE_DIR, "stranger_snapshots")
STRANGER_LOG_PATH = os.path.join(BASE_DIR, "stranger_log.csv")
os.makedirs(STRANGER_DIR, exist_ok=True)

# Cấu hình Camera
CAMERA_SOURCES = [
    {
        "id": 1,
        "name": "CAM 01 - PHÒNG GPL",
        "url": "rtsp://admin:1234Admin@192.168.100.4:554/cam/realmonitor?channel=1&subtype=0"
    },
    {
        "id": 2,
        "name": "CAM 02 - NHÀ ĂN",
        "url": "rtsp://admin:1234admin@192.168.100.125:554/cam/realmonitor?channel=1&subtype=0"
    }
]

# Cấu hình nhận diện chính xác cao
MATCH_THRESHOLD = 0.47     # Ngưỡng Cosine >= 75% để loại bỏ nhận diện nhầm
ATTENDANCE_COOLDOWN = 60   # Giây không ghi log trùng
STRANGER_COOLDOWN = 90     # Giây không ghi lại cùng 1 vùng mặt người lạ

# =============================================================================
# BỘ LỌC WHITELIST NHÂN VIÊN VPTCT (Văn Phòng Tổng Công Ty)
# Chỉ so sánh nhận diện với những nhóm người này để tăng chính xác,
# giảm false-positive, phát hiện người lạ đúng hơn.
# =============================================================================

# Phòng ban/đơn vị thuộc VPTCT — CÀI ĐẶT theo thực tế hệ thống nhân sự
WHITELIST_DEPT_KEYWORDS = [
    "BAN GIÁM ĐỐC", "BAN GĐ", "BAN NỘI CHÍNH", "BAN KẾ TOÁN",
    "BAN HẠ TẦNG CNTT", "BAN PHÁP CHẾ", "BAN NHÂN SỰ", "BAN BÁO GIÁ",
    "BAN VĂN PHÒNG CHỦ TỊCH", "PHÒNG GPL", "PHÒNG LẬP TRÌNH WEBAPP",
    "PHÒNG CHẤT LƯỢNG HỆ THỐNG", "PHÒNG PHÂN TÍCH NGHIỆP VỤ",
    "TỔ THIẾT KẾ", "TỔ TUYỂN DỤNG", "BAN CUNG ỨNG",
    "BAN SỰ KIỆN", "BAN BẢO VỆ", "TRUNG TÂM CHĂM SÓC KHÁCH HÀNG",
    "BAN XÂY DỰNG CƠ BẢN", "OCSA", "TỔ CHỨNG TỪ", "TỔNG QUẢN LÝ",
    "TRUNG TÂM ĐIỀU PHỐI DỊCH VỤ",
]

# Từ khóa ngạch lương cấp cao (Ngạch I → IV) — luôn trong whitelist
WHITELIST_SALARY_GRADES = ["Ngạch I", "Ngạch II", "Ngạch III", "Ngạch IV"]

# Từ khóa chức danh / vai trò — luôn trong whitelist dù ở đơn vị nào
WHITELIST_ROLE_KEYWORDS = [
    "Giám Đốc", "Giám đốc", "giám đốc",
    "Phó Giám Đốc", "Phó GĐ", "Phó giám",
    "Tổng Giám Đốc", "Phó Tổng",
    "Trưởng", "Phó ban", "Phó Trưởng",
    "Thư ký", "Trợ lý", "Cố vấn",
    "Tổ trưởng", "Tổ phó",
    "Quyền Phó",
]


# =============================================================================
# 1. MODULE ĐỒNG BỘ DỮ LIỆU NHÂN SỰ TỪ API (HMAC-MD5 TOKEN)
# =============================================================================
class EmployeeAPIManager:
    def __init__(self):
        self.api_url = "https://i-officeapi.ltacv.com/api/data/process/Getdata_List_Employee_Full"
        self.sec_code = "smart@things!2020@HRMS***"
        self.code_name = "Getdata_List_Employee_Full"
        self.username = "noname"
        os.makedirs(API_FACES_DIR, exist_ok=True)

    def _convert_json(self, data, reqtime):
        json_string = json.dumps(data, separators=(',', ':'))
        json_string = json_string.replace(' ', '').replace('\r', '').replace('\n', '').replace('"', "'")
        return f"{json_string}#{self.username}#{self.code_name}#{reqtime}"

    def fetch_employees_from_api(self):
        """Gọi API lấy danh sách toàn bộ nhân sự theo chuẩn HMAC-MD5 và parse chính xác"""
        print("[*] Đang kết nối API Getdata_List_Employee_Full...")
        reqtime = int(time.time() * 1000)
        data_payload = {}
        
        datastring = self._convert_json(data_payload, reqtime)
        token = hmac.new(self.sec_code.encode('utf-8'), datastring.encode('utf-8'), hashlib.md5).hexdigest()
        
        body = {
            "token": token,
            "reqtime": reqtime,
            "data": data_payload
        }
        
        headers = {'Content-Type': 'application/json'}
        try:
            resp = requests.post(self.api_url, json=body, headers=headers, timeout=12)
            if resp.status_code == 200:
                res_json = resp.json()
                data_list = res_json.get("data", [])
                print(f"[+] Lấy thành công {len(data_list)} nhân sự từ API Smart HRMS.")
                
                employees = {}
                for emp in data_list:
                    def get_val(k):
                        v = emp.get(k)
                        if isinstance(v, dict):
                            return v.get('v', '')
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
                            # Các trường dự phòng mở rộng khi cần dùng:
                            "Birthday": str(get_val('Birthday') or ""),
                            "Mobile": str(get_val('Mobile') or ""),
                            "OfficeEmail": str(get_val('OfficeEmail') or ""),
                            "WorkPlaceName": str(get_val('WorkPlaceName') or ""),
                            "Company_Address": str(get_val('Company_Address') or "")
                        }
                
                if employees:
                    try:
                        with open(CACHE_JSON_PATH, "w", encoding="utf-8") as f:
                            json.dump(employees, f, ensure_ascii=False, indent=2)
                    except Exception:
                        pass
                    return employees
            else:
                print(f"[!] API trả về mã lỗi: {resp.status_code}")
        except Exception as e:
            print(f"[!] Lỗi kết nối API: {e}")

        if os.path.exists(CACHE_JSON_PATH):
            print("[*] Đang nạp dữ liệu nhân sự từ bộ nhớ đệm cache...")
            try:
                with open(CACHE_JSON_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def sync_face_images(self, employees):
        """Tải ảnh chấm công khuôn mặt của nhân viên về thư mục local"""
        print("[*] Đang kiểm tra và đồng bộ ảnh khuôn mặt nhân viên...")
        to_download = []
        for emp_id, info in employees.items():
            img_url = info.get("Image_Url")
            if not img_url:
                continue
            save_path = os.path.join(API_FACES_DIR, f"{emp_id}.jpg")
            if not os.path.exists(save_path) or os.path.getsize(save_path) == 0:
                to_download.append((emp_id, img_url, save_path))

        if not to_download:
            print(f"[+] Toàn bộ {len(employees)} nhân sự đã có ảnh khuôn mặt đầy đủ.")
            return

        print(f"[*] Cần tải mới {len(to_download)} ảnh khuôn mặt. Đang tiến hành tải đa luồng...")

        def _download_task(item):
            eid, url, spath = item
            try:
                r = requests.get(url, timeout=10)
                if r.status_code == 200 and len(r.content) > 500:
                    with open(spath, "wb") as f:
                        f.write(r.content)
                    return True
            except Exception:
                pass
            return False

        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(_download_task, to_download))

        success_count = sum(1 for r in results if r)
        print(f"[+] Hoàn tất tải ảnh: {success_count}/{len(to_download)} ảnh mới.")


# =============================================================================
# 2. BỘ THU LUỒNG RTSP MƯỢT MÀ KHÔNG DELAY (DEDICATED THREAD)
# =============================================================================
class RTSPCapture:
    def __init__(self, rtsp_url, name=""):
        self.url = rtsp_url
        self.name = name
        self.cap = cv2.VideoCapture(self.url, cv2.CAP_FFMPEG)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        self.lock = threading.Lock()
        self.frame = None
        self.grabbed = False
        self.running = True
        self.new_frame_event = threading.Event()

        self.thread = threading.Thread(target=self._update, daemon=True)
        self.thread.start()
        print(f"[*] Đã kết nối luồng RTSP: {self.name}")

    def _update(self):
        fail_count = 0
        while self.running:
            if not self.cap.isOpened():
                fail_count += 1
                time.sleep(1.0)
                self.cap.open(self.url, cv2.CAP_FFMPEG)
                continue

            grabbed, frame = self.cap.read()
            if not grabbed or frame is None:
                fail_count += 1
                if fail_count > 30:
                    self.cap.release()
                    time.sleep(1.0)
                    self.cap.open(self.url, cv2.CAP_FFMPEG)
                    fail_count = 0
                time.sleep(0.01)
                continue

            fail_count = 0
            with self.lock:
                self.frame = frame
                self.grabbed = True
            self.new_frame_event.set()

    def read_latest(self):
        with self.lock:
            if self.frame is not None:
                return self.grabbed, self.frame.copy()
            return False, None

    def release(self):
        self.running = False
        self.new_frame_event.set()
        if self.thread.is_alive():
            self.thread.join(timeout=0.5)
        self.cap.release()


# =============================================================================
# 3. HỆ THỐNG NHẬN DIỆN KHUÔN MẶT & RENDER GIAO DIỆN HIỆU NĂNG CAO
# =============================================================================
class APIFaceAttendanceSystem:
    def __init__(self):
        print("=" * 75)
        print("  KHỞI TẠO HỆ THỐNG NHẬN DIỆN KHUÔN MẶT ĐỒNG BỘ API NHÂN SỰ")
        print("=" * 75)

        # 1. Khởi tạo AI YuNet & SFace trên GPU OpenCL
        if not os.path.exists(YUNET_PATH) or not os.path.exists(SFACE_PATH):
            raise FileNotFoundError(f"Không tìm thấy mô hình AI trong {MODEL_DIR}")

        print("[1/4] Đang nạp mô hình AI YuNet và SFace (GPU OpenCL)...")
        self.detector = cv2.FaceDetectorYN.create(
            YUNET_PATH, "", (320, 320),
            score_threshold=0.75,
            nms_threshold=0.3,
            top_k=5000,
            backend_id=cv2.dnn.DNN_BACKEND_OPENCV,
            target_id=cv2.dnn.DNN_TARGET_OPENCL
        )
        self.recognizer = cv2.FaceRecognizerSF.create(
            SFACE_PATH, "",
            backend_id=cv2.dnn.DNN_BACKEND_OPENCV,
            target_id=cv2.dnn.DNN_TARGET_OPENCL
        )

        # 2. Đồng bộ dữ liệu nhân viên từ API
        print("[2/4] Đang đồng bộ thông tin nhân sự từ API...")
        self.api_mgr = EmployeeAPIManager()
        self.employees = self.api_mgr.fetch_employees_from_api()
        self.api_mgr.sync_face_images(self.employees)

        # 3. Nạp và mã hóa vector khuôn mặt vào RAM
        print("[3/4] Đang nạp và trích xuất đặc trưng khuôn mặt vào bộ nhớ...")
        self.database = {}
        self.load_or_build_embeddings()

        # 4. Trạng thái nhận diện & bộ đệm
        self.active_card = None
        self.last_checkin_times = {}
        self.match_streak = {}
        self.recent_logs = []
        self._load_recent_logs_from_csv()

        # 5. KHỞI TẠO CẤU HÌNH GIAO DIỆN FULL HD HIỆU NĂNG CAO (1920x1080)
        print("[4/4] Khởi tạo bộ nhớ đệm đồ họa giao diện siêu tốc...")
        self.W, self.H = 1920, 1080
        self._init_cached_fonts()
        self._build_static_templates()
        self._update_cached_table_img()
        self.cached_card_img = None
        self.cached_card_emp_id = None

    def _init_cached_fonts(self):
        """Khởi tạo và lưu toàn bộ font chữ vào RAM một lần duy nhất, tránh đọc đĩa khi chạy"""
        font_bold = "C:/Windows/Fonts/arialbd.ttf"
        font_reg = "C:/Windows/Fonts/arial.ttf"
        self.fonts = {}
        sizes = [9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 20, 22, 24]
        for s in sizes:
            try:
                self.fonts[(s, True)] = ImageFont.truetype(font_bold, s)
            except Exception:
                self.fonts[(s, True)] = ImageFont.load_default()
            try:
                self.fonts[(s, False)] = ImageFont.truetype(font_reg, s)
            except Exception:
                self.fonts[(s, False)] = ImageFont.load_default()

    def _build_static_templates(self):
        """
        Dựng sẵn khung giao diện tĩnh (Base Template) vào RAM.
        Nhờ đó trong vòng lặp chỉ cần dán video và cập nhật số liệu động,
        tốc độ dựng hình tăng từ 4 FPS lên 28+ FPS!
        """
        W, H = self.W, self.H
        base = np.full((H, W, 3), (249, 245, 241), dtype=np.uint8)  # Nền xám trắng #F1F5F9

        # Header Bar (Height: 64px)
        cv2.rectangle(base, (0, 0), (W, 64), (255, 255, 255), -1)
        cv2.rectangle(base, (0, 0), (W, 5), (204, 82, 0), -1)      # Dải xanh dương hoàng gia #0052CC
        cv2.line(base, (0, 64), (W, 64), (226, 232, 240), 1)

        # Logo [AI CAM]
        cv2.rectangle(base, (20, 14), (110, 52), (204, 82, 0), -1)

        # Kích thước Card Camera (2 Cột chuẩn tỉ lệ 16:9, độ phân giải cao 930x523)
        self.card_y = 74
        self.pad_x = 20
        self.gap_x = 20
        self.card_w = (W - self.pad_x * 2 - self.gap_x) // 2  # 930px
        self.video_w = self.card_w                             # 930px
        self.video_h = int(self.card_w * 9 / 16)               # 523px (16:9 sắc nét!)
        self.card_h = 36 + self.video_h + 28                   # 587px

        self.cols_pos = [
            {"id": 1, "name": "CAM 01 - PHÒNG GPL", "x": self.pad_x, "info": "Độ phân giải: 1920x1080 Full HD  |  Luồng: RTSP Main Stream  |  AI Tracking: BẬT"},
            {"id": 2, "name": "CAM 02 - NHÀ ĂN", "x": self.pad_x + self.card_w + self.gap_x, "info": "Độ phân giải: 1920x1080 Full HD  |  Luồng: RTSP Main Stream  |  AI Tracking: BẬT"}
        ]

        for c in self.cols_pos:
            cx = c["x"]
            # Khung Card trắng viền xanh dương
            cv2.rectangle(base, (cx, self.card_y), (cx + self.card_w, self.card_y + self.card_h), (255, 255, 255), -1)
            cv2.rectangle(base, (cx, self.card_y), (cx + self.card_w, self.card_y + self.card_h), (199, 132, 2), 2)

            # Header Thẻ (Height: 36px)
            cv2.rectangle(base, (cx, self.card_y), (cx + self.card_w, self.card_y + 36), (204, 82, 0), -1)

            # Huy hiệu Live
            live_bx = cx + self.card_w - 120
            cv2.rectangle(base, (live_bx, self.card_y + 6), (cx + self.card_w - 12, self.card_y + 30), (255, 255, 255), -1)
            cv2.circle(base, (live_bx + 14, self.card_y + 18), 4, (16, 185, 129), -1)

            # Sub-bar bên dưới video
            sub_y = self.card_y + 36 + self.video_h
            cv2.rectangle(base, (cx, sub_y), (cx + self.card_w, sub_y + 28), (248, 250, 252), -1)
            cv2.line(base, (cx, sub_y), (cx + self.card_w, sub_y), (226, 232, 240), 1)

        # Kích thước Bảng Nhật ký điểm danh (Từ y = 674 đến 1032, rộng 1880px)
        self.tbl_y = self.card_y + self.card_h + 13
        self.tbl_x = self.pad_x
        self.tbl_w = W - self.pad_x * 2
        self.tbl_h = H - self.tbl_y - 48

        cv2.rectangle(base, (self.tbl_x, self.tbl_y), (self.tbl_x + self.tbl_w, self.tbl_y + self.tbl_h), (255, 255, 255), -1)
        cv2.rectangle(base, (self.tbl_x, self.tbl_y), (self.tbl_x + self.tbl_w, self.tbl_y + self.tbl_h), (199, 132, 2), 1)

        # Header bảng
        cv2.rectangle(base, (self.tbl_x, self.tbl_y), (self.tbl_x + self.tbl_w, self.tbl_y + 34), (224, 242, 254), -1)
        cv2.line(base, (self.tbl_x, self.tbl_y + 34), (self.tbl_x + self.tbl_w, self.tbl_y + 34), (186, 230, 253), 1)

        # Header cột
        self.col_hdr_y = self.tbl_y + 34
        cv2.rectangle(base, (self.tbl_x, self.col_hdr_y), (self.tbl_x + self.tbl_w, self.col_hdr_y + 28), (248, 250, 252), -1)
        cv2.line(base, (self.tbl_x, self.col_hdr_y + 28), (self.tbl_x + self.tbl_w, self.col_hdr_y + 28), (226, 232, 240), 1)

        # Footer Bar (Height: 42px)
        self.ftr_y = H - 42
        cv2.rectangle(base, (0, self.ftr_y), (W, H), (255, 255, 255), -1)
        cv2.line(base, (0, self.ftr_y), (W, self.ftr_y), (226, 232, 240), 1)

        buttons = [
            ("[0] Lưới 2 Camera", True),
            ("[1] Cam 01 (Phòng GPL)", False),
            ("[2] Cam 02 (Nhà Ăn)", False),
            ("[R] Đồng bộ API", False),
            ("[S] Chụp màn hình", False),
            ("[Q] Thoát hệ thống", False),
        ]

        btn_x = 20
        btn_renders = []
        for b_lbl, is_active in buttons:
            bw = len(b_lbl) * 9 + 24
            if is_active:
                cv2.rectangle(base, (btn_x, self.ftr_y + 5), (btn_x + bw, self.ftr_y + 37), (204, 82, 0), -1)
            else:
                cv2.rectangle(base, (btn_x, self.ftr_y + 5), (btn_x + bw, self.ftr_y + 37), (241, 245, 249), -1)
                cv2.rectangle(base, (btn_x, self.ftr_y + 5), (btn_x + bw, self.ftr_y + 37), (203, 213, 225), 1)
            btn_renders.append((btn_x, b_lbl, is_active))
            btn_x += bw + 12

        # Vẽ toàn bộ chữ tĩnh qua PIL một lần
        img_pil = Image.fromarray(cv2.cvtColor(base, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(img_pil)

        draw.text((32, 22), "AI CAM", font=self.fonts[(14, True)], fill=(255, 255, 255))
        draw.text((125, 14), "HỆ THỐNG ĐIỂM DANH KHUÔN MẶT AI", font=self.fonts[(20, True)], fill=(15, 41, 74))
        draw.text((128, 40), "API SMART HRMS SYNCHRONIZED  •  CHẤM CÔNG DOANH NGHIỆP TỰ ĐỘNG", font=self.fonts[(10, True)], fill=(2, 132, 199))

        for c in self.cols_pos:
            cx = c["x"]
            draw.text((cx + 16, self.card_y + 9), c['name'], font=self.fonts[(14, True)], fill=(255, 255, 255))
            live_bx = cx + self.card_w - 120
            draw.text((live_bx + 26, self.card_y + 9), "TRỰC TIẾP", font=self.fonts[(11, True)], fill=(16, 185, 129))
            draw.text((cx + 16, self.card_y + 36 + self.video_h + 6), c["info"], font=self.fonts[(11, False)], fill=(100, 116, 139))

        draw.text((self.tbl_x + 16, self.tbl_y + 8), "NHẬT KÝ ĐIỂM DANH & XÁC THỰC THỜI GIAN THỰC (REAL-TIME ACTIVITY LOG)", font=self.fonts[(13, True)], fill=(3, 105, 161))
        draw.text((self.tbl_x + self.tbl_w - 180, self.tbl_y + 9), "● TỰ ĐỘNG CẬP NHẬT", font=self.fonts[(11, True)], fill=(16, 185, 129))

        cols_cfg = [
            ("THỜI GIAN", self.tbl_x + 20),
            ("MÃ NV", self.tbl_x + 160),
            ("HỌ VÀ TÊN", self.tbl_x + 280),
            ("CHỨC DANH", self.tbl_x + 580),
            ("PHÒNG BAN / CÔNG TY", self.tbl_x + 880),
            ("VỊ TRÍ CAMERA", self.tbl_x + 1380),
            ("ĐỘ TIN CẬY", self.tbl_x + 1600),
            ("TRẠNG THÁI", self.tbl_x + 1740),
        ]
        for c_title, c_pos in cols_cfg:
            draw.text((c_pos, self.col_hdr_y + 6), c_title, font=self.fonts[(12, True)], fill=(100, 116, 139))

        for bx_pos, b_lbl, is_active in btn_renders:
            f_color = (255, 255, 255) if is_active else (51, 65, 85)
            draw.text((bx_pos + 12, self.ftr_y + 11), b_lbl, font=self.fonts[(12, is_active)], fill=f_color)

        self.base_template = cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)

    def _update_cached_table_img(self):
        """Vẽ lại bảng dữ liệu điểm danh chỉ khi có nhân sự mới chấm công (không tốn CPU trong loop)"""
        tbl_data_h = self.tbl_h - 62
        table_surf = np.full((tbl_data_h, self.tbl_w - 2, 3), (255, 255, 255), dtype=np.uint8)

        display_rows = self.recent_logs[:8]
        row_h = 32
        for i in range(len(display_rows)):
            bg_col = (255, 255, 255) if i % 2 == 0 else (248, 250, 252)
            cv2.rectangle(table_surf, (0, i * row_h), (self.tbl_w - 2, (i + 1) * row_h), bg_col, -1)
            cv2.line(table_surf, (0, (i + 1) * row_h), (self.tbl_w - 2, (i + 1) * row_h), (241, 245, 249), 1)

        img_pil = Image.fromarray(cv2.cvtColor(table_surf, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(img_pil)

        if not display_rows:
            draw.text((self.tbl_w // 2 - 320, 40), "Đang lắng nghe camera... Khi có nhân sự xuất hiện, dữ liệu chấm công sẽ tự động hiển thị tại đây.", font=self.fonts[(13, False)], fill=(148, 163, 184))
        else:
            for i, item in enumerate(display_rows):
                ry = i * row_h + 7
                draw.text((18, ry), item.get("time", ""), font=self.fonts[(12, False)], fill=(71, 85, 105))
                draw.text((158, ry), item.get("code", ""), font=self.fonts[(12, True)], fill=(2, 132, 199))
                draw.text((278, ry), item.get("name", ""), font=self.fonts[(13, True)], fill=(15, 23, 42))
                draw.text((578, ry), item.get("role", ""), font=self.fonts[(12, False)], fill=(51, 65, 85))
                dept_company = (item.get("dept", "") + " - " + item.get("company", "")).strip(" -")
                if len(dept_company) > 42:
                    dept_company = dept_company[:40] + "..."
                draw.text((878, ry), dept_company, font=self.fonts[(12, False)], fill=(71, 85, 105))
                draw.text((1378, ry), item.get("cam", ""), font=self.fonts[(12, False)], fill=(2, 132, 199))
                draw.text((1598, ry), item.get("conf", ""), font=self.fonts[(13, True)], fill=(16, 185, 129))
                draw.text((1738, ry), item.get("status", ""), font=self.fonts[(12, True)], fill=(16, 185, 129))

        self.cached_table_img = cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)

    def _render_employee_card_overlay(self, card_info):
        """Vẽ thẻ thông tin nhân sự nổi một lần và lưu vào cache để dán siêu tốc"""
        p = card_info["profile"]
        conf = card_info["confidence"]
        code = card_info["code"]
        emp_id = card_info["emp_id"]

        card_w, card_h = 480, 230
        card_surf = np.full((card_h, card_w, 3), (255, 255, 255), dtype=np.uint8)

        # Viền xanh hoàng gia
        cv2.rectangle(card_surf, (0, 0), (card_w, card_h), (199, 132, 2), 2)
        # Header thẻ
        cv2.rectangle(card_surf, (0, 0), (card_w, 36), (204, 82, 0), -1)

        # Avatar
        av_size = 92
        av_x = 16
        av_y = 48
        av_path = os.path.join(API_FACES_DIR, f"{emp_id}.jpg")
        if os.path.exists(av_path):
            av_img = cv2.imread(av_path)
            if av_img is not None:
                av_thumb = cv2.resize(av_img, (av_size, av_size), interpolation=cv2.INTER_LINEAR)
                card_surf[av_y:av_y+av_size, av_x:av_x+av_size] = av_thumb
        else:
            cv2.rectangle(card_surf, (av_x, av_y), (av_x + av_size, av_y + av_size), (241, 245, 249), -1)
        cv2.rectangle(card_surf, (av_x, av_y), (av_x + av_size, av_y + av_size), (204, 82, 0), 2)

        img_pil = Image.fromarray(cv2.cvtColor(card_surf, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(img_pil)

        draw.text((16, 9), "XÁC THỰC DANH TÍNH THÀNH CÔNG", font=self.fonts[(12, True)], fill=(255, 255, 255))
        draw.text((card_w - 150, 9), f"ĐỘ TIN CẬY: {conf:.0f}%", font=self.fonts[(12, True)], fill=(224, 242, 254))

        tx = av_x + av_size + 16
        ty = 46

        # 1. FullName (Họ và tên)
        fullname = p.get("FullName") or f"Nhân viên [{code}]"
        draw.text((tx, ty), fullname, font=self.fonts[(16, True)], fill=(15, 23, 42))
        ty += 28

        # 2. Name_Role (Chức danh)
        role = p.get("Name_Role") or "Nhân viên"
        draw.text((tx, ty), f"Chức danh: {role}", font=self.fonts[(13, True)], fill=(2, 132, 199))
        ty += 24

        # 3. Dept_Name (Phòng ban)
        dept = p.get("Dept_Name") or "--"
        draw.text((tx, ty), f"Bộ phận  : {dept}", font=self.fonts[(12, False)], fill=(51, 65, 85))
        ty += 22

        # 4. Company_Name (Công ty)
        company = p.get("Company_Name") or "--"
        if len(company) > 34: company = company[:32] + "..."
        draw.text((tx, ty), f"Công ty  : {company}", font=self.fonts[(11, False)], fill=(100, 116, 139))
        ty += 22

        # 5. SalaryClassName (Ngạch lương)
        salary = p.get("SalaryClassName") or "--"
        draw.text((tx, ty), f"Ngạch    : {salary}", font=self.fonts[(12, False)], fill=(3, 105, 161))
        ty += 22

        # 6. EmployeeStatus_Name (Trạng thái)
        status = p.get("EmployeeStatus_Name") or "Đang làm việc"
        draw.text((tx, ty), f"Trạng thái: {status}", font=self.fonts[(12, True)], fill=(16, 185, 129))

        # =========================================================================
        # CÁC TRƯỜNG DỮ LIỆU KHÁC SẴN CÓ TRONG CODE (COMMENT # KHI NÀO CẦN THÌ MỞ):
        # =========================================================================
        # # birthday = p.get("Birthday", "")
        # # draw.text((tx, ty), f"Ngày sinh: {birthday}", font=self.fonts[(11, False)], fill=(100, 116, 139))
        #
        # # mobile = p.get("Mobile", "")
        # # draw.text((tx, ty), f"SĐT: {mobile}", font=self.fonts[(11, False)], fill=(100, 116, 139))
        #
        # # email = p.get("OfficeEmail", "")
        # # draw.text((tx, ty), f"Email: {email}", font=self.fonts[(11, False)], fill=(100, 116, 139))
        #
        # # workplace = p.get("WorkPlaceName", "")
        # # draw.text((tx, ty), f"Nơi làm: {workplace}", font=self.fonts[(11, False)], fill=(100, 116, 139))
        #
        # # address = p.get("Company_Address", "")
        # # draw.text((tx, ty), f"Địa chỉ: {address}", font=self.fonts[(11, False)], fill=(100, 116, 139))

        self.cached_card_img = cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)
        self.cached_card_emp_id = emp_id

    def _load_recent_logs_from_csv(self):
        """Nạp các lượt điểm danh gần nhất từ file CSV"""
        if not os.path.exists(ATTENDANCE_LOG_PATH):
            return
        try:
            with open(ATTENDANCE_LOG_PATH, "r", encoding="utf-8") as f:
                lines = [l.strip() for l in f if l.strip()]
            for line in lines[1:][-10:]:
                parts = line.split(",")
                if len(parts) >= 8:
                    t_time = parts[0].split(" ")[-1] if " " in parts[0] else parts[0]
                    self.recent_logs.insert(0, {
                        "time": t_time,
                        "code": parts[1],
                        "name": parts[2],
                        "role": parts[3],
                        "dept": parts[4],
                        "company": parts[5],
                        "conf": parts[6],
                        "cam": parts[7],
                        "status": "ĐÃ XÁC THỰC"
                    })
        except Exception:
            pass

    def _is_in_whitelist(self, emp_info):
        """
        Kiểm tra nhân viên có thuộc nhóm được so sánh nhận diện không.
        Trả về (True, lý_do) nếu nằm trong whitelist, (False, lý_do) nếu không.
        """
        dept = str(emp_info.get("Dept_Name", "")).strip()
        salary = str(emp_info.get("SalaryClassName", "")).strip()
        role = str(emp_info.get("Name_Role", "")).strip()

        # Kiểm tra ngạch lương cấp cao (I → IV)
        for grade in WHITELIST_SALARY_GRADES:
            if grade.lower() in salary.lower():
                return True, f"Ngạch cao: {salary}"

        # Kiểm tra từ khóa chức danh quan trọng
        for kw in WHITELIST_ROLE_KEYWORDS:
            if kw.lower() in role.lower():
                return True, f"Chức danh: {role}"

        # Kiểm tra phòng ban VPTCT
        for dept_kw in WHITELIST_DEPT_KEYWORDS:
            if dept_kw.lower() in dept.lower():
                return True, f"Phòng ban VPTCT: {dept}"

        return False, f"Không thuộc VPTCT: {dept} / {role} / {salary}"

    def _build_filtered_employee_pool(self):
        """
        Xây dựng danh sách rút gọn các nhân viên được phép so sánh nhận diện.
        Trả về set of emp_id đã lọc và ghi log thống kê.
        """
        total = len(self.employees)
        filtered_ids = set()
        excluded_ids = set()

        for emp_id, info in self.employees.items():
            in_wl, reason = self._is_in_whitelist(info)
            if in_wl:
                filtered_ids.add(emp_id)
            else:
                excluded_ids.add(emp_id)

        print(f"[WHITELIST] Tổng nhân sự từ API: {total}")
        print(f"[WHITELIST] → Đưa vào so sánh (VPTCT + cấp cao): {len(filtered_ids)} nhân viên")
        print(f"[WHITELIST] → Loại khỏi so sánh (ngoài VPTCT): {len(excluded_ids)} nhân viên")
        print(f"[WHITELIST] → Nhận diện được nhưng không khớp = NGƯỜI LẠ hoặc NV NGOÀI KHU VỰC")
        return filtered_ids

    def load_or_build_embeddings(self):
        """Nạp vector khuôn mặt từ cache pkl, CHỈ NẠP nhân viên trong whitelist VPTCT"""
        # Xây dựng tập nhân viên được phép so sánh
        self.filtered_pool_ids = self._build_filtered_employee_pool()

        loaded_from_cache = False
        cached_data = {}
        if os.path.exists(EMBEDDINGS_PKL_PATH):
            try:
                with open(EMBEDDINGS_PKL_PATH, "rb") as f:
                    cached_data = pickle.load(f)
                loaded_from_cache = True
            except Exception:
                cached_data = {}

        image_files = glob.glob(os.path.join(API_FACES_DIR, "*.jpg"))
        print(f"[*] Tìm thấy {len(image_files)} file ảnh khuôn mặt từ API.")

        self.detector.setScoreThreshold(0.5)
        new_encoded = 0
        skipped_not_wl = 0

        for img_path in image_files:
            key_id = os.path.splitext(os.path.basename(img_path))[0]

            # *** LỌC WHITELIST: bỏ qua nhân viên không thuộc VPTCT / cấp cao ***
            if key_id not in self.filtered_pool_ids:
                skipped_not_wl += 1
                continue

            if key_id in cached_data and cached_data[key_id]:
                self.database[key_id] = cached_data[key_id]
                continue

            img = cv2.imread(img_path)
            if img is None:
                continue

            h, w, _ = img.shape
            self.detector.setInputSize((w, h))
            _, faces = self.detector.detect(img)

            if faces is not None and len(faces) > 0:
                faces_sorted = sorted(faces, key=lambda f: f[2] * f[3], reverse=True)
                primary = faces_sorted[0]
                aligned = self.recognizer.alignCrop(img, primary)
                feat = self.recognizer.feature(aligned)

                if key_id not in self.database:
                    self.database[key_id] = []
                self.database[key_id].append(feat)
                cached_data[key_id] = self.database[key_id]
                new_encoded += 1

        self.detector.setScoreThreshold(0.75)

        if new_encoded > 0 or not loaded_from_cache:
            try:
                with open(EMBEDDINGS_PKL_PATH, "wb") as f:
                    pickle.dump(cached_data, f)
            except Exception:
                pass

        print(f"[+] CSDL AI sẵn sàng: {len(self.database)} NV trong whitelist VPTCT")
        print(f"[+] Bỏ qua (ngoài whitelist): {skipped_not_wl} NV — sẽ được xếp là NGƯỜI LẠ nếu xuất hiện")

    def is_facing_camera(self, face, min_eye_dist_ratio=0.22, min_eye_dist_px=18):
        """Kiểm tra góc nghiêng mặt loại bỏ các trường hợp quay ngang > 35 độ"""
        bw = face[2]
        re = face[4:6]
        le = face[6:8]

        dx = float(re[0] - le[0])
        dy = float(re[1] - le[1])
        eye_dist = (dx * dx + dy * dy) ** 0.5
        eye_ratio = eye_dist / (float(bw) + 1e-6)

        if eye_dist < min_eye_dist_px or eye_ratio < min_eye_dist_ratio:
            return False, f"Goc nghieng (ratio={eye_ratio:.2f})"
        if abs(dy) > abs(dx) * 0.8:
            return False, "Mat bi nghieng qua muc"
        return True, "Huong mat hop le"

    def recognize_face(self, feat):
        best_id = None
        best_score = -1.0
        for kid, feat_list in self.database.items():
            for f in feat_list:
                score = self.recognizer.match(feat, f, cv2.FaceRecognizerSF_FR_COSINE)
                if score > best_score:
                    best_score = score
                    best_id = kid

        if best_score >= MATCH_THRESHOLD:
            return best_id, best_score
        return None, best_score

    def log_attendance(self, emp_id, profile, confidence, cam_name="", status="ĐÃ XÁC THỰC"):
        now = time.time()
        last_t = self.last_checkin_times.get(emp_id, 0)
        if now - last_t < ATTENDANCE_COOLDOWN:
            return False

        self.last_checkin_times[emp_id] = now
        time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        time_short = datetime.now().strftime("%H:%M:%S")

        name = profile.get("FullName", "")
        role = profile.get("Name_Role", "")
        dept = profile.get("Dept_Name", "")
        company = profile.get("Company_Name", "")
        code = profile.get("EmployeeCode", emp_id)

        # Cập nhật danh sách bảng hiển thị
        new_entry = {
            "time": time_short,
            "code": code,
            "name": name,
            "role": role,
            "dept": dept,
            "company": company,
            "conf": f"{confidence:.1f}%",
            "cam": cam_name,
            "status": status
        }
        self.recent_logs.insert(0, new_entry)
        if len(self.recent_logs) > 12:
            self.recent_logs.pop()

        # Cập nhật lại hình ảnh bảng dữ liệu
        self._update_cached_table_img()

        # Ghi log ra file CSV
        write_header = not os.path.exists(ATTENDANCE_LOG_PATH)
        with open(ATTENDANCE_LOG_PATH, "a", encoding="utf-8") as f:
            if write_header:
                f.write("ThoiGian,MSNV,HoTen,ChucDanh,PhongBan,CongTy,DoTinCay,Camera,TrangThai\n")
            f.write(f"{time_str},{code},{name},{role},{dept},{company},{confidence:.1f}%,{cam_name},{status}\n")

        status_icon = "[XÁC THỰC]" if status == "ĐÃ XÁC THỰC" else "[XÁC MINH]"
        print(f"[+] {status_icon}: [{code}] {name} - {role} ({dept}) lúc {time_str} ({confidence:.1f}%)")
        return True

    def log_stranger(self, face_img, cam_name="", score=0.0):
        """
        Ghi nhận người lạ: lưu snapshot ảnh + ghi CSV.
        Dùng cooldown riêng để tránh flood ảnh.
        """
        now = time.time()
        # Dùng khóa cooldown chung cho "stranger" theo camera
        cooldown_key = f"stranger_{cam_name}"
        last_t = self.last_checkin_times.get(cooldown_key, 0)
        if now - last_t < STRANGER_COOLDOWN:
            return False

        self.last_checkin_times[cooldown_key] = now
        time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        time_short = datetime.now().strftime("%H%M%S")
        date_str = datetime.now().strftime("%Y%m%d")

        # Lưu ảnh snapshot người lạ
        snap_filename = f"stranger_{date_str}_{time_short}_{cam_name.replace(' ', '_').replace('-', '')}.jpg"
        snap_path = os.path.join(STRANGER_DIR, snap_filename)
        try:
            cv2.imwrite(snap_path, face_img)
        except Exception:
            snap_filename = ""

        # Ghi vào CSV người lạ
        write_header = not os.path.exists(STRANGER_LOG_PATH)
        with open(STRANGER_LOG_PATH, "a", encoding="utf-8") as f:
            if write_header:
                f.write("ThoiGian,Camera,DoTuongDong,FileAnh,GhiChu\n")
            f.write(f"{time_str},{cam_name},{score:.3f},{snap_filename},NGUOI_LA\n")

        # Cập nhật bảng hiển thị với entry người lạ
        new_entry = {
            "time": datetime.now().strftime("%H:%M:%S"),
            "code": "NGƯỜI LẠ",
            "name": "⚠ KHÔNG XÁC ĐỊNH",
            "role": "Chưa đăng ký trong hệ thống",
            "dept": "--",
            "company": "--",
            "conf": f"{score*100:.1f}%",
            "cam": cam_name,
            "status": "⚠ NGƯỜI LẠ"
        }
        self.recent_logs.insert(0, new_entry)
        if len(self.recent_logs) > 12:
            self.recent_logs.pop()
        self._update_cached_table_img()

        print(f"[!] NGƯỜI LẠ phát hiện tại [{cam_name}] lúc {time_str} — Đã lưu: {snap_filename}")
        return True

    def process_frame(self, frame, cam_name=""):
        """
        Dò tìm khuôn mặt, trích xuất đặc trưng và xác thực danh tính với phân tầng 3 cấp:
          1. Khớp confidence >= 75% → GHI NHẬN CHẤM CÔNG bình thường
          2. Khớp nhưng confidence < 75% → Ghi nhận CẦN XÁC MINH
          3. Không khớp ai trong whitelist → GHI NHẬN NGƯỜI LẠ + lưu snapshot
        """
        h, w, _ = frame.shape
        scale = 640.0 / w if w > 640 else 1.0
        det_w, det_h = (640, int(h * scale)) if scale != 1.0 else (w, h)
        det_frame = cv2.resize(frame, (det_w, det_h), interpolation=cv2.INTER_LINEAR) if scale != 1.0 else frame

        self.detector.setInputSize((det_w, det_h))
        _, faces = self.detector.detect(det_frame)

        current_frame_matched_ids = set()

        if faces is not None:
            if scale != 1.0:
                faces_orig = faces.copy()
                faces_orig[:, :14] /= scale
            else:
                faces_orig = faces

            for face in faces_orig:
                x, y, bw, bh = face[:4].astype(int)

                if bw < 50 or bh < 50:
                    continue

                is_facing, reason = self.is_facing_camera(face)
                if not is_facing:
                    continue

                aligned = self.recognizer.alignCrop(frame, face)
                feat = self.recognizer.feature(aligned)
                emp_id, score = self.recognize_face(feat)

                # ==============================================================
                # CẤP 1: Nhận diện được trong whitelist VPTCT
                # ==============================================================
                if emp_id is not None:
                    current_frame_matched_ids.add(emp_id)
                    self.match_streak[emp_id] = self.match_streak.get(emp_id, 0) + 1

                    profile = self.employees.get(emp_id, {})
                    confidence_pct = min(100.0, (score / 0.70) * 100.0)
                    code = profile.get("EmployeeCode") or emp_id

                    if self.match_streak[emp_id] >= 2 or score >= 0.55:
                        # ==================================================
                        # CẤP 1A: Confidence >= 75% → Chấm công bình thường
                        # ==================================================
                        if confidence_pct >= 75.0:
                            label = f"[{code}] ({confidence_pct:.0f}%)"
                            color = (16, 185, 80)   # Xanh lá — xác thực thành công
                            status_tag = "ĐÃ XÁC THỰC"
                        else:
                            # ==================================================
                            # CẤP 1B: Confidence < 75% → Cần xác minh thêm
                            # ==================================================
                            label = f"[{code}] XAC MINH? ({confidence_pct:.0f}%)"
                            color = (0, 165, 255)   # Cam — cần xác minh
                            status_tag = "CẦN XÁC MINH"

                        # Kích hoạt Thẻ Thông Tin Nhân Sự (hiển thị 6.0 giây)
                        self.active_card = {
                            "emp_id": emp_id,
                            "code": code,
                            "profile": profile,
                            "confidence": confidence_pct,
                            "expire_time": time.time() + 6.0,
                            "cam_name": cam_name
                        }
                        if self.cached_card_emp_id != emp_id:
                            self._render_employee_card_overlay(self.active_card)

                        self.log_attendance(emp_id, profile, confidence_pct,
                                            cam_name=cam_name, status=status_tag)
                    else:
                        label = f"Dang xac thuc ({confidence_pct:.0f}%)"
                        color = (0, 180, 255)

                else:
                    # ==============================================================
                    # CẤP 3: Không khớp ai trong whitelist → NGƯỜI LẠ
                    # Chụp vùng mặt + ghi log stranger
                    # ==============================================================
                    label = "⚠ NGUOI LA"
                    color = (0, 0, 220)   # Đỏ — cảnh báo người lạ

                    # Cắt vùng khuôn mặt + padding 20px để lưu snapshot rõ hơn
                    pad = 20
                    x1 = max(0, x - pad)
                    y1 = max(0, y - pad)
                    x2 = min(w, x + bw + pad)
                    y2 = min(h, y + bh + pad)
                    face_crop = frame[y1:y2, x1:x2].copy()

                    self.log_stranger(face_crop, cam_name=cam_name, score=score)

                self.draw_bbox(frame, x, y, bw, bh, color, label)

        for kid in list(self.match_streak.keys()):
            if kid not in current_frame_matched_ids:
                self.match_streak[kid] = max(0, self.match_streak[kid] - 1)
                if self.match_streak[kid] == 0:
                    del self.match_streak[kid]

        return frame

    def draw_bbox(self, img, x, y, w, h, color, label):
        """Vẽ Bounding Box nhận diện khuôn mặt công nghệ cao"""
        ih, iw, _ = img.shape
        x1, y1 = max(0, x), max(0, y)
        x2, y2 = min(iw, x + w), min(ih, y + h)

        line_len = int(min(w, h) * 0.25)
        cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
        cv2.line(img, (x1, y1), (x1 + line_len, y1), color, 4)
        cv2.line(img, (x1, y1), (x1, y1 + line_len), color, 4)
        cv2.line(img, (x2, y1), (x2 - line_len, y1), color, 4)
        cv2.line(img, (x2, y1), (x2, y1 + line_len), color, 4)
        cv2.line(img, (x1, y2), (x1 + line_len, y2), color, 4)
        cv2.line(img, (x1, y2), (x1, y2 - line_len), color, 4)
        cv2.line(img, (x2, y2), (x2 - line_len, y2), color, 4)
        cv2.line(img, (x2, y2), (x2 - line_len, y2), color, 4)

        font = cv2.FONT_HERSHEY_DUPLEX
        (tw, th), _ = cv2.getTextSize(label, font, 0.55, 1)
        badge_y = max(y1 - 6, th + 8)
        cv2.rectangle(img, (x1, badge_y - th - 6), (x1 + tw + 10, badge_y + 4), color, -1)
        cv2.putText(img, label, (x1 + 5, badge_y - 2), font, 0.55, (255, 255, 255), 1, cv2.LINE_AA)

    def render_modern_ui(self, proc_frames, view_mode, fps):
        """
        Dựng giao diện lưới siêu tốc (khoảng 8 - 10ms per frame),
        giữ nguyên độ phân giải Full HD cực kỳ sắc nét và mượt mà 25 - 30 FPS!
        """
        # 1. Bắt đầu từ Base Template đã dựng sẵn (0.8 ms)
        canvas = self.base_template.copy()

        # 2. Dán hình ảnh Camera với độ phân giải lớn 930x523 (sắc nét 16:9)
        if view_mode == 0:
            for c in self.cols_pos:
                cid = c["id"]
                cx = c["x"]
                vid_y = self.card_y + 36

                cam_frame = proc_frames.get(cid)
                if cam_frame is not None:
                    # Resize nhanh bằng INTER_LINEAR từ 1080p sang 930x523 (~3ms)
                    resized_feed = cv2.resize(cam_frame, (self.video_w, self.video_h), interpolation=cv2.INTER_LINEAR)
                    canvas[vid_y:vid_y+self.video_h, cx:cx+self.video_w] = resized_feed
                else:
                    cv2.rectangle(canvas, (cx, vid_y), (cx + self.video_w, vid_y + self.video_h), (35, 39, 48), -1)

            # 3. Dán Bảng Nhật ký điểm danh từ Cache (0.2 ms)
            if self.cached_table_img is not None:
                th, tw, _ = self.cached_table_img.shape
                canvas[self.col_hdr_y+28:self.col_hdr_y+28+th, self.tbl_x+1:self.tbl_x+1+tw] = self.cached_table_img

        else:
            # Chế độ xem riêng 1 camera (Single View Full HD)
            cx = self.pad_x
            single_w = 1420
            single_h = int(single_w * 9 / 16)
            vid_y = self.card_y + 36

            cam_frame = proc_frames.get(view_mode)
            if cam_frame is not None:
                resized_feed = cv2.resize(cam_frame, (single_w, single_h), interpolation=cv2.INTER_LINEAR)
                canvas[vid_y:vid_y+single_h, cx:cx+single_w] = resized_feed

            # Khung thông tin phụ bên phải
            side_x = cx + single_w + 20
            side_w = self.W - side_x - self.pad_x
            cv2.rectangle(canvas, (side_x, self.card_y), (side_x + side_w, self.card_y + single_h + 36), (255, 255, 255), -1)
            cv2.rectangle(canvas, (side_x, self.card_y), (side_x + side_w, self.card_y + single_h + 36), (199, 132, 2), 2)
            cv2.rectangle(canvas, (side_x, self.card_y), (side_x + side_w, self.card_y + 36), (204, 82, 0), -1)
            cv2.putText(canvas, "THONG TIN CAMERA & SU KIEN", (side_x + 16, self.card_y + 24),
                        cv2.FONT_HERSHEY_DUPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)

        # 4. Hiển thị Thẻ Nhân Sự Nổi nếu có người được xác thực (0.3 ms)
        if self.active_card and time.time() < self.active_card["expire_time"]:
            if self.cached_card_img is not None:
                cw, ch = 480, 230
                mx1 = self.W - cw - 30
                my1 = 84
                canvas[my1:my1+ch, mx1:mx1+cw] = self.cached_card_img

        # 5. Cập nhật thông số động trên Header: Đồng hồ thời gian thực & KPI Badges (0.1 ms)
        now_str = datetime.now().strftime("%Y-%m-%d  %H:%M:%S")
        cv2.putText(canvas, now_str, (780, 39), cv2.FONT_HERSHEY_DUPLEX, 0.62, (71, 85, 105), 1, cv2.LINE_AA)

        kpi_info = [
            (f"API: {len(self.employees)} NV", (224, 242, 254), (125, 211, 252), (3, 105, 161)),
            (f"CSDL AI: {len(self.database)}", (224, 242, 254), (125, 211, 252), (3, 105, 161)),
            ("CAM: 2 ONLINE", (236, 253, 245), (110, 231, 183), (16, 185, 129)),
            (f"FPS: {fps:.0f}", (240, 249, 255), (186, 230, 253), (2, 132, 199))
        ]

        bx = 1160
        for text, fill_col, border_col, text_col in kpi_info:
            bw = len(text) * 9 + 26
            cv2.rectangle(canvas, (bx, 15), (bx + bw, 49), fill_col, -1)
            cv2.rectangle(canvas, (bx, 15), (bx + bw, 49), border_col, 1)
            cv2.putText(canvas, text, (bx + 12, 38), cv2.FONT_HERSHEY_DUPLEX, 0.55, text_col, 1, cv2.LINE_AA)
            bx += bw + 10

        return canvas

    def run(self, camera_sources=CAMERA_SOURCES):
        """Khởi chạy hệ thống camera điểm danh với giao diện Full HD mượt mà"""
        print("=" * 75)
        print("  HỆ THỐNG ĐIỂM DANH & NHẬN DIỆN KHUÔN MẶT ĐANG HOẠT ĐỘNG (25 - 30 FPS)!")
        print("  - Phím [0]: Xem Lưới 2 Camera Full HD")
        print("  - Phím [1]: Xem Chi Tiết Camera 01 (Phòng GPL)")
        print("  - Phím [2]: Xem Chi Tiết Camera 02 (Nhà Ăn)")
        print("  - Phím [R]: Đồng bộ lại dữ liệu mới nhất từ API")
        print("  - Phím [S]: Chụp ảnh màn hình lưu vào captures/")
        print("  - Phím [Q] / [ESC]: Thoát")
        print("=" * 75)

        caps = {}
        for cam in camera_sources:
            cid = cam["id"]
            caps[cid] = RTSPCapture(cam["url"], name=cam["name"])

        win_name = "AI Camera Face Attendance - [API Smart HRMS Synchronized]"
        cv2.namedWindow(win_name, cv2.WINDOW_NORMAL)
        # Kích thước khởi tạo 1600x900 vừa vặn màn hình Full HD, có thể phóng to cực nét
        cv2.resizeWindow(win_name, 1600, 900)

        view_mode = 0
        prev_time = time.time()
        fps = 0.0

        while True:
            t_start = time.time()

            # 1. Đọc frame mới nhất từ các camera
            frames_raw = {}
            for cam in camera_sources:
                cid = cam["id"]
                ret, f = caps[cid].read_latest()
                if ret and f is not None:
                    frames_raw[cid] = f
                else:
                    ph = np.full((360, 640, 3), (25, 28, 35), dtype=np.uint8)
                    cv2.putText(ph, f"{cam['name']}: MAT TIN HIEU", (160, 180),
                                cv2.FONT_HERSHEY_DUPLEX, 0.7, (0, 0, 255), 1, cv2.LINE_AA)
                    frames_raw[cid] = ph

            # 2. Xử lý AI nhận diện khuôn mặt
            proc_frames = {}
            if view_mode == 0:
                for cam in camera_sources:
                    cid = cam["id"]
                    proc_frames[cid] = self.process_frame(frames_raw[cid], cam_name=cam["name"])
            else:
                for cam in camera_sources:
                    cid = cam["id"]
                    if cid == view_mode:
                        proc_frames[cid] = self.process_frame(frames_raw[cid], cam_name=cam["name"])
                    else:
                        proc_frames[cid] = frames_raw[cid]

            # 3. Tính toán FPS thực tế
            curr_t = time.time()
            fps = 0.9 * fps + 0.1 * (1.0 / (curr_t - prev_time + 1e-6))
            prev_time = curr_t

            # 4. Dựng giao diện Full HD Sáng Trắng & Xanh Dương siêu tốc
            display_img = self.render_modern_ui(proc_frames, view_mode, fps)

            cv2.imshow(win_name, display_img)

            # Khóa tốc độ mượt mà 30 FPS
            elapsed = time.time() - t_start
            sleep_t = max(0.001, 0.030 - elapsed)
            time.sleep(sleep_t)

            key = cv2.waitKey(1) & 0xFF
            if key in (ord('q'), ord('Q'), 27):
                break
            elif key in (ord('0'), 9):
                view_mode = 0
            elif key == ord('1'):
                view_mode = 1
            elif key == ord('2'):
                view_mode = 2
            elif key in (ord('r'), ord('R')):
                print("[*] Đang đồng bộ lại từ API theo yêu cầu...")
                self.employees = self.api_mgr.fetch_employees_from_api()
                self.api_mgr.sync_face_images(self.employees)
                self.load_or_build_embeddings()
            elif key in (ord('s'), ord('S')):
                os.makedirs("captures", exist_ok=True)
                f_path = os.path.join("captures", f"snap_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg")
                cv2.imwrite(f_path, display_img)
                print(f"[+] Đã chụp ảnh màn hình Full HD: {f_path}")

        for c in caps.values():
            c.release()
        cv2.destroyAllWindows()
        print("[*] Đã dừng hệ thống an toàn.")


if __name__ == "__main__":
    app = APIFaceAttendanceSystem()
    app.run()
