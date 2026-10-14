"""
=============================================================================
CHƯƠNG TRÌNH KIỂM TEST NHẬN DIỆN KHUÔN MẶT TỪ FILE VIDEO RECORD (OFFLINE)
Đánh giá: Góc camera, kích thước mặt (Pixel), độ nhạy & độ chính xác nhận diện.
Tự động quét CSDL nhân viên từ thư mục: luxand/Release/Image User
File video lưu trữ tại: videos/
=============================================================================
"""

import os
import cv2
import sys
import glob
import time
import numpy as np
from datetime import datetime

# Bật tăng tốc OpenCL cho GPU Intel
cv2.ocl.setUseOpenCL(True)

# Import module hệ thống nhận diện khuôn mặt sẵn có
from camera_face_attendance import FaceAttendanceSystem, BASE_DIR, IMAGE_USER_DIR, LOG_CSV_PATH

VIDEOS_DIR = os.path.join(BASE_DIR, "videos")
TEST_OUTPUT_DIR = os.path.join(BASE_DIR, "video_test_results")
TEST_CSV_LOG = os.path.join(BASE_DIR, "video_attendance_test.csv")


def find_video_files():
    """Tìm tất cả các file video trong thư mục videos/"""
    if not os.path.exists(VIDEOS_DIR):
        os.makedirs(VIDEOS_DIR, exist_ok=True)
        return []
    
    extensions = ("*.mp4", "*.dav", "*.avi", "*.mkv", "*.mov", "*.flv", "*.wmv")
    video_files = []
    for ext in extensions:
        video_files.extend(glob.glob(os.path.join(VIDEOS_DIR, ext)))
    return sorted(video_files, key=os.path.getmtime, reverse=True)


class VideoRecordTester:
    def __init__(self, video_path=None):
        self.system = FaceAttendanceSystem()
        if not video_path:
            v_files = find_video_files()
            self.video_path = v_files[0] if v_files else None
        else:
            self.video_path = video_path
        os.makedirs(TEST_OUTPUT_DIR, exist_ok=True)
        
        # Ngưỡng phát hiện mặt: cho phép phát hiện mặt từ 40px trở lên trong video 2K
        self.min_face_size = 40
        self.det_width = 640  # Độ phân giải quét AI tối ưu hiệu năng GPU Intel (~15ms)
        
        # Thống kê đánh giá
        self.current_sec = 0.0
        self.stats = {
            "total_frames_processed": 0,
            "detected_faces_count": 0,
            "recognized_events": {},  # { "MSNV": count }
            "unknown_faces_count": 0
        }
        self.logged_cooldown = {} # Tránh spam lưu ảnh liên tục cùng 1 người trong video

    def process_frame(self, frame, video_time_str):
        """
        Phân tích AI chi tiết cho 1 khung hình từ file video record.
        Trả về: (annotated_frame, list_of_detections)
        """
        h, w, _ = frame.shape
        detections = []

        # Tối ưu kích thước quét cho AI
        if w > self.det_width:
            scale = float(self.det_width) / w
            det_w, det_h = self.det_width, int(h * scale)
            det_frame = cv2.resize(frame, (det_w, det_h), interpolation=cv2.INTER_LINEAR)
        else:
            scale = 1.0
            det_w, det_h = w, h
            det_frame = frame

        self.system.detector.setInputSize((det_w, det_h))
        _, faces = self.system.detector.detect(det_frame)

        if faces is not None:
            if scale != 1.0:
                faces_orig = faces.copy()
                faces_orig[:, :14] /= scale
            else:
                faces_orig = faces

            for face in faces_orig:
                bbox = face[:4].astype(int)
                x, y, bw, bh = bbox
                score_det = float(face[14])

                # 1. BƯỚC LỌC 1: Bỏ qua khuôn mặt quá nhỏ ở bàn xa (tránh chạy AI nhận diện lãng phí)
                if bw < self.min_face_size or bh < self.min_face_size:
                    label = f"Nho ({bw}x{bh}px)"
                    self.draw_detection_box(frame, x, y, bw, bh, (80, 80, 180), label, False)
                    continue

                # 2. BƯỚC LỌC 2: Kiểm tra hướng mặt (quay gáy, cúi đầu ăn, góc nghiêng gắt > 60 độ)
                is_facing, angle_reason = self.system.is_facing_camera(face)
                if not is_facing:
                    label = f"Goc nghieng ({bw}x{bh}px)"
                    self.draw_detection_box(frame, x, y, bw, bh, (120, 120, 120), label, False)
                    continue

                # 3. CHỈ KHI MẶT HỢP LỆ (Hướng thẳng + đủ nét) MỚI CHẠY SFACE:
                # Giúp giảm tải từ 15 lần chạy xuống còn 1-2 lần/frame -> FPS tăng vọt từ 5 lên 25-30 FPS!
                aligned_face = self.system.recognizer.alignCrop(frame, face)
                feat = self.system.recognizer.feature(aligned_face)
                emp_id, rec_score = self.system.recognize_face(feat)

                confidence_pct = min(100.0, (rec_score / 0.70) * 100.0) if rec_score > 0 else 0

                det_info = {
                    "bbox": (x, y, bw, bh),
                    "size": (bw, bh),
                    "is_facing": is_facing,
                    "angle_reason": angle_reason,
                    "emp_id": emp_id,
                    "rec_score": rec_score,
                    "confidence_pct": confidence_pct,
                    "det_score": score_det
                }
                detections.append(det_info)

                # Quyết định màu sắc hiển thị
                if emp_id is not None:
                    color = (0, 235, 120)  # Xanh ngọc neon: Nhận diện thành công
                    label = f"MSNV: {emp_id} ({confidence_pct:.0f}%) | {bw}x{bh}px"
                    self.stats["recognized_events"][emp_id] = self.stats["recognized_events"].get(emp_id, 0) + 1
                    
                    # Tự động ghi nhật ký và chụp ảnh kiểm test (cách nhau 5 giây video mỗi người)
                    last_save = self.logged_cooldown.get(emp_id, -999)
                    if self.current_sec - last_save >= 5.0:
                        self.logged_cooldown[emp_id] = self.current_sec
                        self.save_test_detection(frame, face, emp_id, confidence_pct, bw, bh, video_time_str)
                else:
                    color = (0, 140, 255)   # Cam: Người lạ / Chưa đăng ký
                    label = f"Chua dang ky ({confidence_pct:.0f}%) | {bw}x{bh}px"
                    self.stats["unknown_faces_count"] += 1

                # Vẽ khung viền trực quan
                self.draw_detection_box(frame, x, y, bw, bh, color, label, is_facing)

        return frame, detections

    def draw_detection_box(self, img, x, y, w, h, color, label, is_facing):
        """Vẽ bounding box kèm thông số kỹ thuật (Kích thước Pixel, Độ chính xác)"""
        # Giới hạn tọa độ trong khung hình
        img_h, img_w, _ = img.shape
        x1 = max(0, min(x, img_w - 1))
        y1 = max(0, min(y, img_h - 1))
        x2 = max(0, min(x + w, img_w - 1))
        y2 = max(0, min(y + h, img_h - 1))

        # Khung viền góc
        line_len = int(min(w, h) * 0.25)
        thickness = 2
        corner_thickness = 4

        cv2.rectangle(img, (x1, y1), (x2, y2), color, thickness)
        
        # Góc bo công nghệ
        cv2.line(img, (x1, y1), (x1 + line_len, y1), color, corner_thickness)
        cv2.line(img, (x1, y1), (x1, y1 + line_len), color, corner_thickness)
        cv2.line(img, (x2, y1), (x2 - line_len, y1), color, corner_thickness)
        cv2.line(img, (x2, y1), (x2, y1 + line_len), color, corner_thickness)
        cv2.line(img, (x1, y2), (x1 + line_len, y2), color, corner_thickness)
        cv2.line(img, (x1, y2), (x1, y2 - line_len), color, corner_thickness)
        cv2.line(img, (x2, y2), (x2 - line_len, y2), color, corner_thickness)
        cv2.line(img, (x2, y2), (x2, y2 - line_len), color, corner_thickness)

        # Badge thông tin
        font = cv2.FONT_HERSHEY_DUPLEX
        font_scale = 0.65
        (lw, lh), _ = cv2.getTextSize(label, font, font_scale, 1)
        badge_y = max(y1 - 10, lh + 10)
        
        cv2.rectangle(img, (x1, badge_y - lh - 6), (x1 + lw + 14, badge_y + 4), color, -1)
        cv2.putText(img, label, (x1 + 7, badge_y - 2), font, font_scale, (15, 15, 15), 2, cv2.LINE_AA)

    def save_test_detection(self, frame, face, emp_id, confidence, bw, bh, time_str):
        """Lưu bằng chứng nhận diện thành công vào file và CSV để nghiệm thu"""
        time_clean = time_str.split('/')[0].strip().replace(":", "-")
        crop_name = f"test_{emp_id}_{time_clean}_{bw}x{bh}.jpg"
        crop_path = os.path.join(TEST_OUTPUT_DIR, crop_name)

        # Cắt khuôn mặt (kèm padding 20%)
        ih, iw, _ = frame.shape
        x, y, w, h = face[:4].astype(int)
        px = int(w * 0.2)
        py = int(h * 0.2)
        x1 = max(0, x - px)
        y1 = max(0, y - py)
        x2 = min(iw, x + w + px)
        y2 = min(ih, y + h + py)
        
        crop_img = frame[y1:y2, x1:x2]
        if crop_img.size > 0:
            cv2.imwrite(crop_path, crop_img)

        # Ghi log CSV
        write_header = not os.path.exists(TEST_CSV_LOG)
        with open(TEST_CSV_LOG, "a", encoding="utf-8") as f:
            if write_header:
                f.write("ThoiGianVideo,MSNV,DoTinCay,KichThuocKhuonMat,FileAnhBangChung,VideoGoc\n")
            f.write(f"{time_str},{emp_id},{confidence:.1f}%,{bw}x{bh}px,{crop_name},{os.path.basename(self.video_path)}\n")

        print(f"[+] [TEST PASS] Video {time_str} -> Phat hien MSNV [{emp_id}] ({confidence:.1f}%) | Kich thuoc: {bw}x{bh}px | Da luu: {crop_name}")

    def run(self, start_sec=0):
        # 1. Tìm file video
        if not self.video_path or not os.path.exists(self.video_path):
            videos = find_video_files()
            if not videos:
                print(f"[!] Khong tim thay file video nao trong thu muc: {VIDEOS_DIR}")
                print(f"    Vui long chep file record (.mp4, .dav, ...) vao thu muc tren roi chay lai!")
                return
            self.video_path = videos[0]

        print("=" * 70)
        print("  KHOI DONG TRINH PHAN TICH RECORD VIDEO DANH GIA GOC CAMERA")
        print(f"  - File video: {os.path.basename(self.video_path)}")
        print(f"  - Thu muc luu ket qua test: {TEST_OUTPUT_DIR}")
        print(f"  - File log danh gia: {TEST_CSV_LOG}")
        print("=" * 70)

        cap = cv2.VideoCapture(self.video_path)
        if not cap.isOpened():
            print(f"[!] Khong the mo file video: {self.video_path}")
            return

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        total_seconds = total_frames / fps
        orig_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        orig_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        print(f"[*] Do phan giai goc: {orig_w} x {orig_h}")
        print(f"[*] Tong so frame: {total_frames} ({fps:.1f} FPS) -> Thoi luong: {int(total_seconds//60)} phut {int(total_seconds%60)} giay")

        window_name = f"AI Video Record Test - [{os.path.basename(self.video_path)}]"
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(window_name, 1280, 720)

        # Nhảy tới thời điểm bắt đầu nếu có chỉ định
        if start_sec > 0:
            start_f = min(total_frames - 1, int(start_sec * fps))
            cap.set(cv2.CAP_PROP_POS_FRAMES, start_f)
            m_s, s_s = divmod(int(start_sec), 60)
            print(f"[*] Bat dau phat tu moc thoi gian: {m_s:02d}:{s_s:02d} (Frame {start_f})")

        # Tạo thanh trượt (Trackbar) điều hướng tua video
        def on_trackbar(val):
            target_frame = int((val / 1000.0) * total_frames)
            cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)

        cv2.createTrackbar("Vi tri Video", window_name, 0, 1000, on_trackbar)
        if start_sec > 0 and total_frames > 0:
            init_pos = int((min(total_frames - 1, int(start_sec * fps)) / total_frames) * 1000)
            cv2.setTrackbarPos("Vi tri Video", window_name, init_pos)

        is_paused = False
        speed_multiplier = 1.0  # 1x, 2x, 4x
        self.current_sec = float(start_sec)

        print("\n" + "=" * 70)
        print("  CAC PHIM DIEU KHIEN KHI XEM & TEST VIDEO:")
        print("  - [SPACE]: Tam dung (Pause) / Tiep tuc (Resume)")
        print("  - [D] hoac [->]: Tua toi +5 giay (hoac tien 1 frame khi Pause)")
        print("  - [A] hoac [<-]: Tua lui -5 giay")
        print("  - [F]: Chuyen toc do phat (1x -> 2x -> 4x -> 1x)")
        print("  - [S]: Chup anh man hinh luu vao captures/")
        print("  - [Thanh truot chuot]: Keo de nhay den bat ky phut nao")
        print("  - [Q] hoac [ESC]: Ket thuc va xem bao cao tong ket")
        print("=" * 70 + "\n")

        prev_time = time.time()
        fps_display = 0.0

        while True:
            if not is_paused:
                # Tua nhanh 2x, 4x: nhảy cóc frame bằng cap.grab() để video tăng tốc mượt mà, không nghẽn AI
                if speed_multiplier > 1.0:
                    skip_count = int(speed_multiplier) - 1
                    for _ in range(skip_count):
                        cap.grab()

                ret, frame = cap.read()
                if not ret:
                    print("\n[*] Da doc het toan bo noi dung video!")
                    break

                curr_frame_idx = int(cap.get(cv2.CAP_PROP_POS_FRAMES))
                self.current_sec = curr_frame_idx / fps
                self.stats["total_frames_processed"] += 1

                # Cập nhật thanh trượt Trackbar (khoảng 25 frames một lần để mượt)
                if curr_frame_idx % 25 == 0 and total_frames > 0:
                    track_pos = int((curr_frame_idx / total_frames) * 1000)
                    cv2.setTrackbarPos("Vi tri Video", window_name, track_pos)

                # Chuỗi thời gian video: MM:SS / Total MM:SS
                m, s = divmod(int(self.current_sec), 60)
                tot_m, tot_s = divmod(int(total_seconds), 60)
                time_str = f"{m:02d}:{s:02d} / {tot_m:02d}:{tot_s:02d}"

                # Phân tích khuôn mặt AI
                processed_frame, detections = self.process_frame(frame, time_str)
                display_img = processed_frame.copy()
            else:
                # Đang Pause: giữ nguyên khung hình hiện tại
                m, s = divmod(int(self.current_sec), 60)
                tot_m, tot_s = divmod(int(total_seconds), 60)
                time_str = f"{m:02d}:{s:02d} / {tot_m:02d}:{tot_s:02d} [DANG TAM DUNG]"

            # Tính FPS hiển thị
            t_now = time.time()
            fps_display = 0.9 * fps_display + 0.1 * (1.0 / (t_now - prev_time + 1e-6))
            prev_time = t_now

            # Thu nhỏ để hiển thị vừa vặn màn hình (1280x720)
            dh, dw = 720, 1280
            canvas = cv2.resize(display_img, (dw, dh), interpolation=cv2.INTER_LINEAR)

            # Vẽ thanh trạng thái Header
            cv2.rectangle(canvas, (0, 0), (dw, 46), (25, 25, 30), -1)
            cv2.line(canvas, (0, 46), (dw, 46), (0, 200, 100), 2)
            cv2.putText(canvas, f"VIDEO TEST: {os.path.basename(self.video_path)}", (16, 30),
                        cv2.FONT_HERSHEY_DUPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)

            state_info = f"Thoi gian: {time_str} | Toc do: {speed_multiplier:.0f}x | FPS: {fps_display:.0f}"
            (sw, _), _ = cv2.getTextSize(state_info, cv2.FONT_HERSHEY_DUPLEX, 0.52, 1)
            cv2.putText(canvas, state_info, (dw - sw - 16, 30), cv2.FONT_HERSHEY_DUPLEX, 0.52, (200, 220, 200), 1, cv2.LINE_AA)

            # Vẽ thanh điều khiển Footer
            cv2.rectangle(canvas, (0, dh - 30), (dw, dh), (20, 20, 25), -1)
            cv2.line(canvas, (0, dh - 30), (dw, dh - 30), (60, 60, 70), 1)
            help_str = "[SPACE] Dung/Chay | [D / ->] +5s | [A / <-] -5s | [F] Toc do (1x/2x/4x) | [S] Chup | [Q] Thoat"
            cv2.putText(canvas, help_str, (16, dh - 9), cv2.FONT_HERSHEY_DUPLEX, 0.42, (180, 180, 180), 1, cv2.LINE_AA)

            cv2.imshow(window_name, canvas)

            # Độ trễ hiển thị mượt mà (~25-30 FPS)
            wait_delay = int(max(1, 1000.0 / fps)) if not is_paused else 30
            key = cv2.waitKey(wait_delay) & 0xFF

            if key in (ord('q'), ord('Q'), 27):
                print("\n[*] Nguoi dung dung trinh kiem test.")
                break
            elif key == ord(' '):  # Phím SPACE
                is_paused = not is_paused
                state_lbl = "TAM DUNG" if is_paused else "TIEP TUC CHAY"
                print(f"[*] {state_lbl} tai giay thu {self.current_sec:.1f}")
            elif key in (ord('d'), ord('D'), 83):  # 83 = Mũi tên phải
                if is_paused:
                    # Tiến 1 frame
                    ret, frame = cap.read()
                    if ret:
                        curr_frame_idx = int(cap.get(cv2.CAP_PROP_POS_FRAMES))
                        self.current_sec = curr_frame_idx / fps
                        m, s = divmod(int(self.current_sec), 60)
                        tot_m, tot_s = divmod(int(total_seconds), 60)
                        time_str = f"{m:02d}:{s:02d} / {tot_m:02d}:{tot_s:02d}"
                        processed_frame, _ = self.process_frame(frame, time_str)
                        display_img = processed_frame.copy()
                else:
                    # Tua tới +5s
                    target_f = min(total_frames - 1, int(cap.get(cv2.CAP_PROP_POS_FRAMES) + fps * 5))
                    cap.set(cv2.CAP_PROP_POS_FRAMES, target_f)
                    print(f"[*] Tua toi +5s -> {int(target_f/fps)}s")
            elif key in (ord('a'), ord('A'), 81):  # 81 = Mũi tên trái
                target_f = max(0, int(cap.get(cv2.CAP_PROP_POS_FRAMES) - fps * 5))
                cap.set(cv2.CAP_PROP_POS_FRAMES, target_f)
                print(f"[*] Tua lui -5s -> {int(target_f/fps)}s")
            elif key in (ord('f'), ord('F')):
                if speed_multiplier == 1.0:
                    speed_multiplier = 2.0
                elif speed_multiplier == 2.0:
                    speed_multiplier = 4.0
                else:
                    speed_multiplier = 1.0
                print(f"[*] Thay doi toc do phat: {speed_multiplier:.0f}x")
            elif key in (ord('s'), ord('S')):
                os.makedirs("captures", exist_ok=True)
                cap_f = os.path.join("captures", f"video_snap_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg")
                cv2.imwrite(cap_f, display_img)
                print(f"[+] Da chup luu anh: {cap_f}")

        cap.release()
        cv2.destroyAllWindows()

        # In báo cáo tổng kết nghiệm thu
        self.print_summary_report()

    def run_fast_scan(self, step_frames=10):
        """
        Quét thần tốc toàn bộ video không hiển thị GUI để đạt tốc độ tối đa (60-100 FPS trên GPU Intel).
        Tự động nhận diện, lưu ảnh bằng chứng và xuất báo cáo CSV hoàn chỉnh.
        """
        if not self.video_path or not os.path.exists(self.video_path):
            videos = find_video_files()
            if not videos:
                print(f"[!] Khong tim thay file video nao trong: {VIDEOS_DIR}")
                return
            self.video_path = videos[0]

        cap = cv2.VideoCapture(self.video_path)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        total_sec = total_frames / fps

        print("=" * 70)
        print("  CHE DO QUET SIEU TOC TOAN BO VIDEO (FAST AUTO-SCAN)")
        print(f"  - Video: {os.path.basename(self.video_path)}")
        print(f"  - Tong so frame: {total_frames} (~{int(total_sec//60)} phut) | Buoc nhay: {step_frames} frame/lan")
        print(f"  - Thu muc luu anh: {TEST_OUTPUT_DIR}")
        print(f"  - File CSV ket qua: {TEST_CSV_LOG}")
        print("=" * 70)

        frame_idx = 0
        t0 = time.time()
        proc_fps = 0.0

        while frame_idx < total_frames:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            if not ret:
                break

            self.current_sec = frame_idx / fps
            self.stats["total_frames_processed"] += 1

            m, s = divmod(int(self.current_sec), 60)
            tot_m, tot_s = divmod(int(total_sec), 60)
            time_str = f"{m:02d}:{s:02d} / {tot_m:02d}:{tot_s:02d}"

            # Phân tích AI
            _, dets = self.process_frame(frame, time_str)

            pct = (frame_idx / total_frames) * 100.0
            elapsed = time.time() - t0
            proc_fps = self.stats["total_frames_processed"] / (elapsed + 1e-6)

            if self.stats["total_frames_processed"] % 15 == 0:
                sys.stdout.write(f"\r[*] Tien do: {pct:.1f}% ({time_str}) | Toc do: {proc_fps:.1f} FPS | Nhan dien: {len(self.stats['recognized_events'])} NV   ")
                sys.stdout.flush()

            frame_idx += step_frames

        cap.release()
        self.print_summary_report(elapsed_sec=time.time() - t0, proc_fps=proc_fps)

    def print_summary_report(self, elapsed_sec=None, proc_fps=None):
        print("\n" + "=" * 70)
        print("           BAO CAO TONG KET KIEM TEST VIDEO RECORD")
        print("=" * 70)
        print(f"  - Tong so frame da phan tich : {self.stats['total_frames_processed']}")
        if elapsed_sec is not None:
            print(f"  - Thoi gian xu ly            : {int(elapsed_sec)} giay ({proc_fps:.1f} FPS)")
        print(f"  - Nhan vien duoc nhan dien   :")
        if self.stats["recognized_events"]:
            for emp, count in self.stats["recognized_events"].items():
                print(f"      + MSNV [{emp}]: xuat hien va nhan dien {count} lan")
        else:
            print("      (Chua co nhan vien nao trong CSDL xuat hien hoac goc camera chua du ro)")
        print(f"  - So lan phat hien nguoi la   : {self.stats['unknown_faces_count']}")
        print(f"  - Danh sach anh chup bang chung: {TEST_OUTPUT_DIR}")
        print(f"  - File nhat ky CSV chi tiet   : {TEST_CSV_LOG}")
        print("=" * 70 + "\n")


def parse_time_str(time_str):
    if not time_str:
        return 0
    s = str(time_str).strip()
    if ":" in s:
        parts = s.split(":")
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        elif len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    try:
        return float(s)
    except Exception:
        return 0


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="AI Face Recognition - Video Record Analyzer")
    parser.add_argument("video", nargs="?", default=None, help="Duong dan toi file video")
    parser.add_argument("--fast", action="store_true", help="Chay che do quet sieu toc khong mo GUI")
    parser.add_argument("--step", type=int, default=10, help="Buoc nhay frame cho che do fast (mac dinh 10)")
    parser.add_argument("--start", type=str, default="0", help="Thoi diem bat dau (vd: 12:00 hoac so giay)")
    args = parser.parse_args()

    start_sec = parse_time_str(args.start)
    tester = VideoRecordTester(args.video)
    if args.fast:
        tester.run_fast_scan(step_frames=args.step)
    else:
        tester.run(start_sec=start_sec)


