"""
=============================================================================
HỆ THỐNG ĐIỂM DANH & NHẬN DIỆN KHUÔN MẶT QUA CAMERA (AI FACE ATTENDANCE)
Công nghệ: OpenCV Deep Learning (YuNet Face Detector + SFace Face Recognizer)
Tự động quét ảnh nhân viên từ thư mục: luxand/Release/Image User
=============================================================================
"""

import os
import cv2
import glob
import time
import threading
import numpy as np
from datetime import datetime

# Bật tăng tốc OpenCL toàn cục cho GPU Intel (xử lý ma trận, resize ảnh)
cv2.ocl.setUseOpenCL(True)

# Cấu hình RTSP dùng giao thức TCP để chống vỡ hình và giải mã phần cứng D3D11VA trên GPU
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|hwaccel;d3d11va"

# Đường dẫn thư mục và mô hình AI
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGE_USER_DIR = os.path.join(BASE_DIR, "luxand", "Release", "Image User")
MODEL_DIR = os.path.join(BASE_DIR, "models")
YUNET_PATH = os.path.join(MODEL_DIR, "face_detection_yunet.onnx")
SFACE_PATH = os.path.join(MODEL_DIR, "face_recognition_sface.onnx")
LOG_CSV_PATH = os.path.join(BASE_DIR, "attendance_log.csv")

# Cấu hình danh sách các Camera giám sát điểm danh (Smart PSS Multi-Cam)
CAMERA_SOURCES = [
    {
        "id": 1,
        "name": "CAM 01 - PHONG GPL",
        "url": "rtsp://admin:1234Admin@192.168.100.4:554/cam/realmonitor?channel=1&subtype=0"
    },
    {
        "id": 2,
        "name": "CAM 02 - NHA AN 1",
        "url": "rtsp://admin:1234admin@192.168.100.154:554/cam/realmonitor?channel=1&subtype=0"
    },
    {
        "id": 3,
        "name": "CAM 03 - LOI DI CAU THANG NHA AN",
        "url": "rtsp://admin:1234Admin@192.168.100.127:554/cam/realmonitor?channel=1&subtype=0"
    }
]

# Nguồn mặc định (Camera Nhà ăn 1)
DEFAULT_CAMERA_SOURCE = "rtsp://admin:1234admin@192.168.100.154:554/cam/realmonitor?channel=1&subtype=0"

# Ngưỡng nhận diện (Cosine Similarity Threshold của SFace: 0.47 tương đương >= 75.0% độ chính xác)
MATCH_THRESHOLD = 0.47
ATTENDANCE_COOLDOWN_SEC = 60  # Sau 60 giây mới ghi nhận lần chấm công tiếp theo cho cùng 1 người


class RTSPCapture:
    """
    Luồng chuyên đọc frame RTSP ngầm (Background Thread)
    Giúp triệt tiêu 100% độ trễ (Zero Latency) và đồng bộ đúng tốc độ của Camera (~25 FPS)
    """
    def __init__(self, src, name="Camera"):
        self.src = src
        self.name = name
        self.cap = cv2.VideoCapture(self.src)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.grabbed, self.frame = self.cap.read()
        self.running = True
        self.lock = threading.Lock()
        self.new_frame_event = threading.Event()
        if self.grabbed:
            self.new_frame_event.set()
        self.thread = threading.Thread(target=self._update, daemon=True)
        self.thread.start()

    def _update(self):
        while self.running:
            if not self.cap.isOpened():
                time.sleep(0.05)
                continue
            try:
                grabbed, frame = self.cap.read()
            except Exception:
                break
            if grabbed:
                with self.lock:
                    self.grabbed = grabbed
                    self.frame = frame
                self.new_frame_event.set()  # Đánh thức main thread khi có frame MỚI từ camera
            else:
                time.sleep(0.01)

    def read(self, timeout=0.5):
        """Chờ khung hình mới từ camera, giải phóng 100% CPU trong thời gian chờ (khóa đúng ~25 FPS)"""
        # Chờ camera gửi frame mới (tự động ngủ, 0% CPU lúc chờ)
        self.new_frame_event.wait(timeout=timeout)
        self.new_frame_event.clear()

        with self.lock:
            if self.frame is not None:
                return self.grabbed, self.frame.copy()
            return False, None

    def read_latest(self):
        """Lấy ngay khung hình mới nhất hiện tại không chờ (dùng cho chế độ đa camera)"""
        with self.lock:
            if self.frame is not None:
                return self.grabbed, self.frame.copy()
            return False, None

    def isOpened(self):
        return self.cap.isOpened()

    def set(self, prop_id, value):
        return self.cap.set(prop_id, value)

    def release(self):
        self.running = False
        self.new_frame_event.set()  # Đánh thức nếu đang chờ để thoát an toàn
        if self.thread.is_alive():
            self.thread.join(timeout=0.5)
        self.cap.release()



class FaceAttendanceSystem:
    def __init__(self):
        print("=" * 65)
        print("  KHOI TAO HE THONG NHAN DIEN KHUON MAT CHAM CONG (AI CAMERA)")
        print("=" * 65)

        # 1. Khởi tạo bộ phát hiện và nhận diện khuôn mặt AI
        if not os.path.exists(YUNET_PATH) or not os.path.exists(SFACE_PATH):
            raise FileNotFoundError(f"Khong tim thay mo hinh AI trong: {MODEL_DIR}")

        print("[1/3] Dang nap mo hinh AI YuNet va SFace...")
        self.detector = cv2.FaceDetectorYN.create(
            YUNET_PATH, "", (320, 320),
            score_threshold=0.75,
            nms_threshold=0.3,
            top_k=5000,
            backend_id=cv2.dnn.DNN_BACKEND_OPENCV,
            target_id=cv2.dnn.DNN_TARGET_OPENCL  
        )
        self.recognizer = cv2.FaceRecognizerSF.create(SFACE_PATH, "",
            backend_id=cv2.dnn.DNN_BACKEND_OPENCV,
            target_id=cv2.dnn.DNN_TARGET_OPENCL )

        # 2. CSDL vector khuôn mặt nhân viên trong RAM: { "MSNV": [vector1, vector2, ...] }
        self.database = {}
        self.last_checkin_times = {}  # { "MSNV": timestamp }

        # 3. Nạp ảnh nhân viên
        self.load_known_faces()

    def extract_employee_id(self, filename):
        """
        Trích xuất MSNV từ tên file ảnh:
        Ví dụ: '4642.jpg' -> '4642', '4642(1).png' -> '4642', 'NV_4642_front.jpg' -> '4642'
        """
        base = os.path.splitext(os.path.basename(filename))[0]
        # Lấy phần trước dấu ngoặc đơn hoặc dấu gạch dưới nếu có
        clean_id = ""
        for char in base:
            if char in ('.', '(', '_', '-'):
                break
            clean_id += char
        clean_id = clean_id.strip()
        return clean_id if clean_id else base

    def load_known_faces(self):
        """Tự động quét thư mục Image User và nạp các vector khuôn mặt vào bộ nhớ"""
        print(f"[2/3] Dang quet thu muc anh nhan vien: {IMAGE_USER_DIR}")
        self.database.clear()

        if not os.path.exists(IMAGE_USER_DIR):
            os.makedirs(IMAGE_USER_DIR, exist_ok=True)
            print(f"[!] Da tao thu muc '{IMAGE_USER_DIR}'. Vui long tha anh nhan vien vao day!")
            return

        supported_exts = ("*.jpg", "*.jpeg", "*.png", "*.bmp")
        image_files = []
        for ext in supported_exts:
            image_files.extend(glob.glob(os.path.join(IMAGE_USER_DIR, ext)))

        if not image_files:
            print("[!] Chua co anh nao trong thu muc Image User.")
            return

        print(f"[*] Tim thay tong cong {len(image_files)} anh. Bat dau trich xuat dac trung...")

        # Hạ ngưỡng tạm thời về 0.5 để nạp đủ ảnh chân dung nhân viên trong thư mục
        self.detector.setScoreThreshold(0.5)

        loaded_counts = {}
        for img_path in image_files:
            emp_id = self.extract_employee_id(img_path)
            img = cv2.imread(img_path)
            if img is None:
                continue

            h, w, _ = img.shape
            self.detector.setInputSize((w, h))
            _, faces = self.detector.detect(img)

            if faces is not None and len(faces) > 0:
                # Chọn khuôn mặt lớn nhất trong ảnh làm mẫu
                faces_sorted = sorted(faces, key=lambda f: f[2] * f[3], reverse=True)
                primary_face = faces_sorted[0]

                aligned_face = self.recognizer.alignCrop(img, primary_face)
                feature = self.recognizer.feature(aligned_face)

                if emp_id not in self.database:
                    self.database[emp_id] = []
                self.database[emp_id].append(feature)
                loaded_counts[emp_id] = loaded_counts.get(emp_id, 0) + 1
                print(f"  [OK] Da nap anh: {os.path.basename(img_path)} -> MSNV: [{emp_id}]")
            else:
                print(f"  [CANH BAO] Khong tim thay mat trong anh: {os.path.basename(img_path)}")

        # Khôi phục ngưỡng nghiêm ngặt 0.75 cho luồng camera thời gian thực để chống bắt nhầm
        self.detector.setScoreThreshold(0.75)

        print("-" * 65)
        print(f"[+] KET QUA: Da dang ky thanh cong {len(self.database)} nhan vien:")
        for emp_id, count in loaded_counts.items():
            print(f"    - MSNV [{emp_id}]: {count} anh mau")
        print("-" * 65)

    def is_facing_camera(self, face, min_eye_dist_ratio=0.22, min_eye_dist_px=18):
        """
        Kiểm tra hướng mặt (Face Facing Check) dựa trên 5 điểm mốc landmarks (face[4:14]):
        - face[4:6]: mắt phải
        - face[6:8]: mắt trái
        - face[8:10]: mũi
        Loại bỏ các trường hợp: quay gáy, nhìn từ sau, góc nghiêng mặt quá gắt (> 60 độ)
        """
        bw = face[2]
        re = face[4:6]  # Mắt phải
        le = face[6:8]  # Mắt trái

        # Khoảng cách hình học giữa 2 mắt
        dx = float(re[0] - le[0])
        dy = float(re[1] - le[1])
        eye_dist = (dx * dx + dy * dy) ** 0.5

        # Tỉ lệ khoảng cách 2 mắt so với chiều rộng khuôn mặt
        eye_ratio = eye_dist / (float(bw) + 1e-6)

        # 1. Nếu 2 mắt quá sát nhau hoặc chập lại (quay nghiêng gắt hoặc quay gáy)
        if eye_dist < min_eye_dist_px or eye_ratio < min_eye_dist_ratio:
            return False, f"Goc nghieng gat (ratio={eye_ratio:.2f})"

        # 2. Kiểm tra độ nghiêng đầu (Roll angle): Nếu góc nghiêng mắt quá dốc (> 45 độ)
        if abs(dy) > abs(dx) * 1.0:
            return False, "Mat bi nghieng qua muc"

        return True, "Huong mat hop le"

    def recognize_face(self, feature):
        """So khớp vector khuôn mặt phát hiện từ camera với CSDL"""
        best_match_id = None
        best_score = -1.0

        for emp_id, feature_list in self.database.items():
            for known_feature in feature_list:
                score = self.recognizer.match(feature, known_feature, cv2.FaceRecognizerSF_FR_COSINE)
                if score > best_score:
                    best_score = score
                    best_match_id = emp_id

        if best_score >= MATCH_THRESHOLD:
            return best_match_id, best_score
        return None, best_score

    def log_attendance(self, emp_id, confidence, cam_name=""):
        """Ghi nhận log chấm công vào file CSV nếu quá thời gian cooldown"""
        now = time.time()
        last_time = self.last_checkin_times.get(emp_id, 0)

        if now - last_time < ATTENDANCE_COOLDOWN_SEC:
            return False  # Đang trong thời gian cooldown, không ghi log trùng

        self.last_checkin_times[emp_id] = now
        timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Ghi vào file CSV
        write_header = not os.path.exists(LOG_CSV_PATH)
        with open(LOG_CSV_PATH, "a", encoding="utf-8") as f:
            if write_header:
                f.write("ThoiGian,MSNV,TrangThai,DoTinCay,Camera\n")
            f.write(f"{timestamp_str},{emp_id},Check-in,{confidence:.1f}%,{cam_name}\n")

        cam_info = f" tai [{cam_name}]" if cam_name else ""
        print(f"[*] >>> GHI NHAN DIEM DANH: MSNV [{emp_id}]{cam_info} luc {timestamp_str} (Do tin cay: {confidence:.1f}%) <<<")
        return True

    def process_camera_frame(self, frame, cam_name=""):
        """
        Dò tìm khuôn mặt, nhận diện danh tính và vẽ bounding box trên một khung hình
        Trả về: (frame, active_person_id, notification_msg)
        """
        h, w, _ = frame.shape
        active_person_id = None
        notif_msg = None

        # Tối ưu hóa hiệu năng: Thu nhỏ về độ rộng 640px cho bộ dò mặt AI YuNet (<15ms trên GPU Intel)
        if w > 640:
            scale = 640.0 / w
            det_w, det_h = 640, int(h * scale)
            det_frame = cv2.resize(frame, (det_w, det_h), interpolation=cv2.INTER_LINEAR)
        else:
            scale = 1.0
            det_w, det_h = w, h
            det_frame = frame

        self.detector.setInputSize((det_w, det_h))
        _, faces = self.detector.detect(det_frame)

        if faces is not None:
            if scale != 1.0:
                faces_orig = faces.copy()
                faces_orig[:, :14] /= scale
            else:
                faces_orig = faces

            for face in faces_orig:
                bbox = face[:4].astype(int)
                x, y, bw, bh = bbox

                # 1. Bỏ qua khuôn mặt quá nhỏ
                if bw < 45 or bh < 45:
                    continue

                # 2. Bổ sung kiểm tra hướng mặt
                is_facing, _ = self.is_facing_camera(face)
                if not is_facing:
                    continue

                # Cắt và trích xuất đặc trưng với SFace
                aligned_face = self.recognizer.alignCrop(frame, face)
                feat = self.recognizer.feature(aligned_face)

                emp_id, score = self.recognize_face(feat)

                if emp_id is not None:
                    confidence_pct = min(100.0, (score / 0.70) * 100.0)
                    label = f"MSNV: {emp_id} ({confidence_pct:.0f}%)"
                    color = (0, 235, 120)  # Xanh ngọc neon
                    active_person_id = emp_id

                    # Tự động ghi nhận điểm danh kèm camera
                    if self.log_attendance(emp_id, confidence_pct, cam_name=cam_name):
                        notif_msg = f"DIEM DANH: MSNV [{emp_id}] tai {cam_name}!"
                else:
                    label = "Chua dang ky"
                    color = (0, 140, 255)  # Cam neon

                self.draw_modern_bbox(frame, x, y, bw, bh, color, label)

        return frame, active_person_id, notif_msg

    def run(self, camera_sources=CAMERA_SOURCES):
        """Khởi động hệ thống Đa Camera phong cách Smart PSS (Xem Lưới & Chọn Xem Từng Camera)"""
        print("=" * 65)
        print("  KHOI TAO HE THONG DA CAMERA SMART PSS MULTI-VIEW")
        print("=" * 65)

        if isinstance(camera_sources, str):
            camera_sources = [{"id": 1, "name": "CAMERA", "url": camera_sources}]

        # Khởi tạo luồng ngầm cho từng camera
        caps = {}
        for cam in camera_sources:
            cid = cam["id"]
            cname = cam["name"]
            curl = cam["url"]
            print(f"[*] Dang ket noi [{cname}] tai: {curl}...")
            caps[cid] = RTSPCapture(curl, name=cname)

        window_name = "AI Camera Attendance System - [Smart PSS Multi-View]"
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(window_name, 1280, 720)

        # Trạng thái hiển thị: 0 = Lưới đa camera, 1 = Cam 1, 2 = Cam 2
        view_state = {"mode": 0, "win_w": 1280, "win_h": 720}

        def on_mouse(event, x, y, flags, param):
            if event == cv2.EVENT_LBUTTONDOWN:
                if view_state["mode"] == 0:
                    half_w = view_state["win_w"] // 2
                    if x < half_w:
                        view_state["mode"] = 1
                        print("[*] Chuot: Chuyen sang xem toan man hinh CAM 01")
                    else:
                        view_state["mode"] = 2
                        print("[*] Chuot: Chuyen sang xem toan man hinh CAM 02")
            elif event == cv2.EVENT_LBUTTONDBLCLK:
                view_state["mode"] = 0
                print("[*] Chuot (Click dup): Quay lai che do Xem Luoi (Grid View)")

        cv2.setMouseCallback(window_name, on_mouse)

        prev_time = time.time()
        fps = 0.0
        notification_text = ""
        notification_end_time = 0

        print("=" * 65)
        print("  HE THONG DA CAMERA DANG HOAT DONG!")
        print("  - Phim [0] hoac [Tab]: Xem Luoi 2 Camera")
        print("  - Phim [1]: Xem Toan man hinh CAM 01 (Phong GPL)")
        print("  - Phim [2]: Xem Toan man hinh CAM 02 (Nha An)")
        print("  - Click chuot: Chon xem camera | Click dup: Quay lai xem Luoi")
        print("  - Phim [Q] hoac [ESC]: Thoat chuong trinh")
        print("=" * 65)

        while True:
            t_start = time.time()
            curr_mode = view_state["mode"]

            # 1. Thu thập khung hình từ các camera
            frames_raw = {}
            for cam in camera_sources:
                cid = cam["id"]
                ret, f = caps[cid].read_latest()
                if ret and f is not None:
                    frames_raw[cid] = f
                else:
                    ph = np.zeros((720, 1280, 3), dtype=np.uint8)
                    cv2.putText(ph, f"{cam['name']}: MAT TIN HIEU", (380, 360),
                                cv2.FONT_HERSHEY_DUPLEX, 0.9, (0, 0, 255), 2, cv2.LINE_AA)
                    frames_raw[cid] = ph

            # 2. Xử lý AI nhận diện khuôn mặt
            active_detected_person = None
            processed_frames = {}

            if curr_mode == 0:
                # Chế độ lưới: quét AI trên cả 2 camera
                for cam in camera_sources:
                    cid = cam["id"]
                    f_proc, det_p, notif_m = self.process_camera_frame(frames_raw[cid], cam_name=cam["name"])
                    processed_frames[cid] = f_proc
                    if det_p: active_detected_person = det_p
                    if notif_m:
                        notification_text = notif_m
                        notification_end_time = time.time() + 4.0
            else:
                # Chế độ đơn camera: quét AI trên camera đang xem
                for cam in camera_sources:
                    cid = cam["id"]
                    if cid == curr_mode:
                        f_proc, det_p, notif_m = self.process_camera_frame(frames_raw[cid], cam_name=cam["name"])
                        processed_frames[cid] = f_proc
                        if det_p: active_detected_person = det_p
                        if notif_m:
                            notification_text = notif_m
                            notification_end_time = time.time() + 4.0
                    else:
                        processed_frames[cid] = frames_raw[cid]

            # 3. Kết hợp khung hình hiển thị (Canvas Layout)
            if curr_mode == 0:
                # Lưới chia đôi: mỗi ô kích thước 640x360
                cell_w, cell_h = 640, 360
                cells = []
                for cam in camera_sources:
                    cid = cam["id"]
                    f_cell = cv2.resize(processed_frames[cid], (cell_w, cell_h), interpolation=cv2.INTER_LINEAR)

                    # Vẽ nhãn tên camera ở góc trên mỗi ô
                    cv2.rectangle(f_cell, (0, 0), (280, 32), (20, 20, 25), -1)
                    cv2.circle(f_cell, (16, 16), 5, (0, 220, 100), -1)
                    cv2.putText(f_cell, f"{cam['name']} [LIVE]", (28, 22),
                                cv2.FONT_HERSHEY_DUPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)
                    cv2.rectangle(f_cell, (0, 0), (cell_w, cell_h), (50, 50, 60), 1)
                    cells.append(f_cell)

                display_img = np.hstack(cells)

            elif curr_mode == 1:
                display_img = cv2.resize(processed_frames[1], (1280, 720), interpolation=cv2.INTER_LINEAR)
                cv2.rectangle(display_img, (0, 0), (380, 34), (20, 20, 25), -1)
                cv2.circle(display_img, (16, 17), 5, (0, 220, 100), -1)
                cv2.putText(display_img, "CAM 01 - PHONG GPL [Nhan 0 de ve Luoi]", (28, 23),
                            cv2.FONT_HERSHEY_DUPLEX, 0.48, (255, 255, 255), 1, cv2.LINE_AA)

            elif curr_mode == 2:
                display_img = cv2.resize(processed_frames[2], (1280, 720), interpolation=cv2.INTER_LINEAR)
                cv2.rectangle(display_img, (0, 0), (380, 34), (20, 20, 25), -1)
                cv2.circle(display_img, (16, 17), 5, (0, 220, 100), -1)
                cv2.putText(display_img, "CAM 02 - NHA AN [Nhan 0 de ve Luoi]", (28, 23),
                            cv2.FONT_HERSHEY_DUPLEX, 0.48, (255, 255, 255), 1, cv2.LINE_AA)

            dh, dw, _ = display_img.shape
            view_state["win_w"] = dw
            view_state["win_h"] = dh

            # Tính FPS
            curr_time = time.time()
            fps = 0.9 * fps + 0.1 * (1.0 / (curr_time - prev_time + 1e-6))
            prev_time = curr_time

            # 4. Vẽ thanh HUD Header trên cùng
            self.draw_hud(display_img, fps, len(self.database), active_detected_person, notification_text, notification_end_time)

            # 5. Vẽ thanh điều khiển ở dưới đáy màn hình
            footer_h = 28
            cv2.rectangle(display_img, (0, dh - footer_h), (dw, dh), (20, 20, 25), -1)
            cv2.line(display_img, (0, dh - footer_h), (dw, dh - footer_h), (60, 60, 70), 1)
            ctrl_text = "Dieu khien: [0 / Tab] Xem Luoi 2 Cam  |  [1] Cam 01 (Phong GPL)  |  [2] Cam 02 (Nha An)  |  [S] Chup anh  |  [Q] Thoat"
            cv2.putText(display_img, ctrl_text, (16, dh - 8), cv2.FONT_HERSHEY_DUPLEX, 0.42, (180, 180, 180), 1, cv2.LINE_AA)

            cv2.imshow(window_name, display_img)

            # 6. Điều tiết tốc độ vòng lặp (~25-30 FPS) bảo vệ CPU
            elapsed = time.time() - t_start
            sleep_time = max(0.001, 0.033 - elapsed)
            time.sleep(sleep_time)

            # Bắt phím điều khiển
            key = cv2.waitKey(1) & 0xFF
            if key in (ord('q'), ord('Q'), 27):
                print("[*] Nguoi dung yeu cau thoat.")
                break
            elif key in (ord('0'), ord('g'), ord('G'), 9):  # 9 = Phím Tab
                view_state["mode"] = 0
                print("[*] Chuyen che do: Xem Luoi 2 Camera")
            elif key == ord('1'):
                view_state["mode"] = 1
                print("[*] Chuyen che do: Toan man hinh CAM 01")
            elif key == ord('2'):
                view_state["mode"] = 2
                print("[*] Chuyen che do: Toan man hinh CAM 02")
            elif key in (ord('r'), ord('R')):
                print("[*] Dang nap lai CSDL tu Image User...")
                self.load_known_faces()
                notification_text = "Da nap lai CSDL anh nhan vien!"
                notification_end_time = time.time() + 3.0
            elif key in (ord('s'), ord('S')):
                os.makedirs("captures", exist_ok=True)
                cap_path = os.path.join("captures", f"capture_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg")
                cv2.imwrite(cap_path, display_img)
                print(f"[+] Da luu anh chup: {cap_path}")
                notification_text = f"Da luu anh: {os.path.basename(cap_path)}"
                notification_end_time = time.time() + 3.0

        for cam in camera_sources:
            caps[cam["id"]].release()
        cv2.destroyAllWindows()
        print("[*] Da dong toan bo Camera va ket thuc chuong trinh an toan.")

    def draw_modern_bbox(self, img, x, y, w, h, color, label):
        """Vẽ khung nhận diện khuôn mặt phong cách bo góc công nghệ cao"""
        line_len = int(min(w, h) * 0.25)
        thickness = 2
        corner_thickness = 4

        # Khung viền mỏng
        cv2.rectangle(img, (x, y), (x + w, y + h), color, thickness)

        # 4 góc dày nổi bật
        # Top-Left
        cv2.line(img, (x, y), (x + line_len, y), color, corner_thickness)
        cv2.line(img, (x, y), (x, y + line_len), color, corner_thickness)
        # Top-Right
        cv2.line(img, (x + w, y), (x + w - line_len, y), color, corner_thickness)
        cv2.line(img, (x + w, y), (x + w, y + line_len), color, corner_thickness)
        # Bottom-Left
        cv2.line(img, (x, y + h), (x + line_len, y + h), color, corner_thickness)
        cv2.line(img, (x, y + h), (x, y + h - line_len), color, corner_thickness)
        # Bottom-Right
        cv2.line(img, (x + w, y + h), (x + w - line_len, y + h), color, corner_thickness)
        cv2.line(img, (x + w, y + h), (x + w, y + h - line_len), color, corner_thickness)

        # Thẻ nhãn tên (Badge)
        font = cv2.FONT_HERSHEY_DUPLEX
        font_scale = 0.6
        (label_w, label_h), _ = cv2.getTextSize(label, font, font_scale, 1)

        badge_y = max(y - 10, label_h + 10)
        cv2.rectangle(img, (x, badge_y - label_h - 6), (x + label_w + 14, badge_y + 4), color, -1)
        cv2.putText(img, label, (x + 7, badge_y - 2), font, font_scale, (15, 15, 15), 2, cv2.LINE_AA)

    def draw_hud(self, img, fps, db_count, detected_person, notif_text, notif_end_time):
        """Vẽ thanh thông tin trạng thái Header phía trên cùng (tối ưu ROI siêu nhẹ CPU)"""
        h, w, _ = img.shape

        # Thanh Header tối màu trong suốt nhẹ (chỉ hòa trộn vùng 46px trên cùng)
        header_h = 46
        header_roi = img[0:header_h, 0:w]
        header_overlay = np.full_like(header_roi, (25, 25, 30))
        cv2.addWeighted(header_overlay, 0.85, header_roi, 0.15, 0, header_roi)
        img[0:header_h, 0:w] = header_roi
        cv2.line(img, (0, header_h), (w, header_h), (0, 200, 100), 2)

        # Thông tin Header
        font = cv2.FONT_HERSHEY_DUPLEX
        cv2.putText(img, "SMART CAMERA ATTENDANCE SYSTEM", (16, 30), font, 0.65, (255, 255, 255), 1, cv2.LINE_AA)
        
        status_text = f"CSDL: {db_count} NV  |  FPS: {fps:.0f}"
        (sw, _), _ = cv2.getTextSize(status_text, font, 0.55, 1)
        cv2.putText(img, status_text, (w - sw - 16, 30), font, 0.55, (200, 200, 200), 1, cv2.LINE_AA)

        # Banner thông báo điểm danh thành công
        if time.time() < notif_end_time and notif_text:
            banner_h = 42
            banner_y = h - 60
            banner_w = int(w * 0.75)
            bx1 = int((w - banner_w) / 2)
            bx2 = bx1 + banner_w

            # Nền banner xanh neon (chỉ hòa trộn vùng banner để siêu nhẹ CPU)
            banner_roi = img[banner_y:banner_y + banner_h, bx1:bx2]
            banner_overlay = np.full_like(banner_roi, (0, 180, 80))
            cv2.addWeighted(banner_overlay, 0.90, banner_roi, 0.10, 0, banner_roi)
            img[banner_y:banner_y + banner_h, bx1:bx2] = banner_roi
            cv2.rectangle(img, (bx1, banner_y), (bx2, banner_y + banner_h), (255, 255, 255), 2)

            (nw, _), _ = cv2.getTextSize(notif_text, font, 0.65, 2)
            nx = bx1 + int((banner_w - nw) / 2)
            cv2.putText(img, notif_text, (nx, banner_y + 28), font, 0.65, (255, 255, 255), 2, cv2.LINE_AA)


if __name__ == "__main__":
    try:
        app = FaceAttendanceSystem()
        app.run()
    except Exception as e:
        print(f"\n[!] LOI HE THONG: {e}")
        input("\nNhan Enter de thoat...")
