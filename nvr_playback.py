"""
=============================================================================
MODULE XỬ LÝ PLAYBACK TỪ ĐẦU GHI NVR DAHUA (NVR PLAYBACK ENGINE)
Hỗ trợ xem lại video từ ổ cứng NVR qua RTSP và trích xuất đoạn video ngắn (MP4)
Thiết kế độc lập 100% - KHÔNG ẢNH HƯỞNG ĐẾN LUỒNG NHẬN DIỆN KHUÔN MẶT CỦA AI
=============================================================================
"""

import os
import sys
import re
import cv2
import time
import json
import socket
import urllib.parse
from datetime import datetime, timedelta
import numpy as np

try:
    sys.stdout.reconfigure(encoding='utf-8')
except:
    pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
NVR_CONFIG_PATH = os.path.join(BASE_DIR, "nvr_config.json")
PLAYBACK_CLIPS_DIR = os.path.join(BASE_DIR, "playback_clips")
os.makedirs(PLAYBACK_CLIPS_DIR, exist_ok=True)

DEFAULT_NVR_CONFIG = {
    "enabled": True,
    "brand": "dahua",
    "ip": "192.168.100.200",
    "port": 554,
    "http_port": 80,
    "username": "admin",
    "password": "Gpg@2026@",
    "channels": {
        "1": 19,
        "2": 77,
        "3": 86,
        "4": 37
    },
    "channel_names": {
        "19": "CAM 01 - PHÒNG GPL (Tang 4 P. GPL)",
        "77": "CAM 02 - NHÀ ĂN 1 (IPC)",
        "86": "CAM 03 - LỐI ĐI CẦU THANG NHÀ ĂN (IPC)",
        "37": "CAM 04 - NHÀ ĂN 2 (Nha an)"
    }
}


def load_nvr_config():
    """Tải cấu hình NVR từ file JSON"""
    if os.path.exists(NVR_CONFIG_PATH):
        try:
            with open(NVR_CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Đảm bảo đầy đủ các key mặc định
                for k, v in DEFAULT_NVR_CONFIG.items():
                    if k not in data:
                        data[k] = v
                return data
        except Exception as e:
            print(f"[!] Lỗi đọc nvr_config.json: {e}")
    # Nếu chưa có thì lưu file mặc định
    save_nvr_config(DEFAULT_NVR_CONFIG)
    return DEFAULT_NVR_CONFIG


def save_nvr_config(config):
    """Lưu cấu hình NVR vào file JSON"""
    try:
        with open(NVR_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"[!] Lỗi ghi nvr_config.json: {e}")
        return False


def get_nvr_channel_for_cam(cam_id=None, cam_name=None, url=None):
    """
    Ánh xạ từ Camera ID / Tên / IP sang Channel tương ứng trên Đầu ghi NVR Dahua:
    - CAM 01 (192.168.100.4)   -> Channel 19
    - CAM 02 (192.168.100.154) -> Channel 77
    - CAM 03 (192.168.100.127) -> Channel 86
    - CAM 04 (192.168.100.5)   -> Channel 37
    """
    cfg = load_nvr_config()
    channels_map = cfg.get("channels", {})

    # 1. Kiểm tra trực tiếp theo cam_id (str hoặc int)
    if cam_id is not None:
        sid = str(cam_id)
        if sid in channels_map:
            return int(channels_map[sid])
        # Nếu truyền trực tiếp channel lớn (ví dụ 19, 77, 86, 37)
        try:
            iid = int(cam_id)
            if iid in [19, 77, 86, 37] or str(iid) in cfg.get("channel_names", {}):
                return iid
        except:
            pass

    # 2. Kiểm tra theo IP nếu có trong url
    if url:
        u_str = str(url)
        if "192.168.100.4" in u_str:
            return 19
        if "192.168.100.154" in u_str:
            return 77
        if "192.168.100.127" in u_str:
            return 86
        if "192.168.100.5" in u_str:
            return 37

    # 3. Kiểm tra theo tên camera
    if cam_name:
        cn = str(cam_name).upper()
        if "CAM 01" in cn or "GPL" in cn:
            return 19
        if "CAM 02" in cn or "NHÀ ĂN 1" in cn or "NHA AN 1" in cn:
            return 77
        if "CAM 03" in cn or "CẦU THANG" in cn or "CAU THANG" in cn:
            return 86
        if "CAM 04" in cn or "NHÀ ĂN 2" in cn or "NHA AN 2" in cn or "LỬNG" in cn:
            return 37

    # Mặc định trả về kênh 77 (Nhà ăn 1)
    return 77


def parse_datetime(dt_input):
    """Chuyển đổi linh hoạt mọi định dạng thời gian về đối tượng datetime"""
    if isinstance(dt_input, datetime):
        return dt_input
    if isinstance(dt_input, (int, float)):
        return datetime.fromtimestamp(dt_input)
    if isinstance(dt_input, str):
        dt_str = dt_input.strip()
        # Thay thế ký tự T trong chuẩn ISO
        dt_str = dt_str.replace("T", " ")
        formats = [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y/%m/%d %H:%M:%S",
            "%Y_%m_%d_%H_%M_%S",
            "%d/%m/%Y %H:%M:%S",
            "%Y-%m-%d"
        ]
        for fmt in formats:
            try:
                return datetime.strptime(dt_str, fmt)
            except ValueError:
                continue
    # Nếu không parse được, trả về thời điểm hiện tại
    return datetime.now()


def build_playback_rtsp_url(nvr_channel, start_dt, end_dt):
    """
    Tạo đường dẫn RTSP Playback chuẩn hãng Dahua:
    rtsp://admin:Gpg%402026%40@192.168.100.200:554/cam/playback?channel={ch}&starttime={start}&endtime={end}
    Chú ý: Mật khẩu có ký tự '@' phải được mã hóa thành '%40'
    """
    cfg = load_nvr_config()
    user = urllib.parse.quote(str(cfg.get("username", "admin")), safe="")
    raw_pass = str(cfg.get("password", "Gpg@2026@"))
    pwd = urllib.parse.quote(raw_pass, safe="")

    ip = cfg.get("ip", "192.168.100.200")
    port = cfg.get("port", 554)

    s_dt = parse_datetime(start_dt)
    e_dt = parse_datetime(end_dt)
    if s_dt > e_dt:
        s_dt, e_dt = e_dt, s_dt

    s_str = s_dt.strftime("%Y_%m_%d_%H_%M_%S")
    e_str = e_dt.strftime("%Y_%m_%d_%H_%M_%S")

    url = f"rtsp://{user}:{pwd}@{ip}:{port}/cam/playback?channel={nvr_channel}&starttime={s_str}&endtime={e_str}"
    return url, s_dt, e_dt


def create_playback_placeholder_jpeg(title="THÔNG BÁO PLAYBACK", subtitle="Không tìm thấy bản ghi hình trên NVR", width=960, height=540):
    """Tạo ảnh tĩnh thông báo chuyên nghiệp khi luồng playback kết thúc hoặc không có dữ liệu"""
    img = np.zeros((height, width, 3), dtype=np.uint8)
    img[:] = (20, 24, 33)  # Slate dark background

    # Khung viền
    cv2.rectangle(img, (20, 20), (width - 20, height - 20), (51, 65, 85), 1)

    # Icon Playback / Film
    cx, cy = width // 2, height // 2 - 30
    cv2.circle(img, (cx, cy), 38, (59, 130, 246), 2)
    # Tam giác Play
    pts = np.array([[cx - 10, cy - 16], [cx - 10, cy + 16], [cx + 16, cy]], np.int32)
    cv2.fillPoly(img, [pts], (59, 130, 246))

    # Text tiêu đề
    cv2.putText(img, title, (cx - 160, cy + 70), cv2.FONT_HERSHEY_DUPLEX, 0.7, (255, 255, 255), 1, cv2.LINE_AA)
    cv2.putText(img, subtitle, (cx - 240, cy + 105), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (148, 163, 184), 1, cv2.LINE_AA)
    cv2.putText(img, "Dahua NVR 192.168.100.200 • Vui long kiem tra khung gio hoac kenh ghi", (cx - 250, cy + 140), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (100, 116, 139), 1, cv2.LINE_AA)

    _, jpeg = cv2.imencode('.jpg', img, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
    return jpeg.tobytes()


def generate_playback_mjpeg(cam_id=None, start_dt=None, end_dt=None, max_fps=20, target_width=1280):
    """
    Generator tạo luồng MJPEG phát lại từ ổ cứng NVR:
    - cam_id: ID camera nội bộ (1, 2, 3, 4) hoặc kênh NVR (19, 77, 86, 37)
    - start_dt, end_dt: Thời gian bắt đầu và kết thúc
    - Tự động giới hạn FPS để tiết kiệm CPU và băng thông mạng
    - Thiết kế hoàn toàn độc lập, giải phóng tài nguyên ngay khi kết thúc
    """
    nvr_channel = get_nvr_channel_for_cam(cam_id)
    url, s_dt, e_dt = build_playback_rtsp_url(nvr_channel, start_dt, end_dt)

    cfg = load_nvr_config()
    ch_names = cfg.get("channel_names", {})
    cam_title = ch_names.get(str(nvr_channel), f"NVR Kênh {nvr_channel}")

    print(f"[>] [NVR Playback] Khởi tạo luồng Kênh {nvr_channel}: {s_dt.strftime('%H:%M:%S')} -> {e_dt.strftime('%H:%M:%S')}")

    cap = None
    try:
        # Tùy chọn FFMPEG tối ưu RTSP TCP
        cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        if not cap.isOpened():
            print(f"[!] [NVR Playback] Không thể mở luồng RTSP Playback Kênh {nvr_channel}")
            placeholder = create_playback_placeholder_jpeg(
                title=f"KHÔNG CÓ DỮ LIỆU: KÊNH {nvr_channel}",
                subtitle=f"Thời gian: {s_dt.strftime('%d/%m %H:%M:%S')} - {e_dt.strftime('%H:%M:%S')}"
            )
            for _ in range(5):
                yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + placeholder + b'\r\n')
                time.sleep(1.0)
            return

        frame_duration = 1.0 / max(5, min(30, max_fps))
        consecutive_fails = 0

        while True:
            t0 = time.time()
            ret, frame = cap.read()
            if not ret or frame is None:
                consecutive_fails += 1
                if consecutive_fails > 15:
                    print(f"[*] [NVR Playback] Đã kết thúc đoạn video ghi hình Kênh {nvr_channel}")
                    placeholder = create_playback_placeholder_jpeg(
                        title="ĐÃ KẾT THÚC ĐOẠN VIDEO",
                        subtitle=f"Kênh {nvr_channel} • Hoàn tất phát lại {s_dt.strftime('%H:%M:%S')} - {e_dt.strftime('%H:%M:%S')}"
                    )
                    yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + placeholder + b'\r\n')
                    break
                time.sleep(0.05)
                continue

            consecutive_fails = 0

            # Giảm tải độ phân giải xuống kích thước tối ưu cho Web nếu cần
            h, w = frame.shape[:2]
            if target_width and w > target_width:
                scale = target_width / float(w)
                target_height = int(h * scale)
                frame = cv2.resize(frame, (target_width, target_height), interpolation=cv2.INTER_AREA)
                h, w = target_height, target_width

            # Watermark hiển thị thông tin Playback chuyên nghiệp
            bar_h = 32
            cv2.rectangle(frame, (0, 0), (w, bar_h), (15, 23, 42), -1)
            # Dấu đỏ REC Playback
            cv2.circle(frame, (16, bar_h // 2), 6, (0, 0, 230), -1)
            # Chuẩn hóa nhãn tiếng Việt không dấu cho OpenCV text
            import unicodedata
            clean_title = "".join([c for c in unicodedata.normalize('NFKD', cam_title) if not unicodedata.combining(c)]).replace('đ', 'd').replace('Đ', 'D')
            label = f"NVR PLAYBACK [REC] | {clean_title} | {s_dt.strftime('%d/%m/%Y %H:%M:%S')} -> {e_dt.strftime('%H:%M:%S')}"
            cv2.putText(frame, label, (32, bar_h // 2 + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)

            # Nén JPEG gửi về client
            ret_enc, jpeg = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 72])
            if ret_enc:
                yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')

            # Khống chế tốc độ phát chuẩn 20-25 FPS
            elapsed = time.time() - t0
            sleep_time = frame_duration - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    except Exception as e:
        print(f"[!] [NVR Playback] Ngoại lệ khi phát luồng: {e}")
    finally:
        if cap is not None:
            try:
                cap.release()
            except:
                pass
        print(f"[-] [NVR Playback] Đã đóng tài nguyên luồng Kênh {nvr_channel}")


def export_playback_clip(cam_id=None, start_dt=None, end_dt=None, max_seconds=300):
    """
    Trích xuất một đoạn video ngắn từ ổ cứng NVR và xuất ra tệp MP4 tải về:
    - Trả về tuple: (success: bool, result: dict hoặc error message)
    """
    nvr_channel = get_nvr_channel_for_cam(cam_id)
    url, s_dt, e_dt = build_playback_rtsp_url(nvr_channel, start_dt, end_dt)

    diff_sec = (e_dt - s_dt).total_seconds()
    if diff_sec > max_seconds:
        e_dt = s_dt + timedelta(seconds=max_seconds)

    timestamp_str = f"{s_dt.strftime('%Y%m%d_%H%M%S')}_{e_dt.strftime('%H%M%S')}"
    filename = f"nvr_clip_cam{nvr_channel}_{timestamp_str}.mp4"
    filepath = os.path.join(PLAYBACK_CLIPS_DIR, filename)

    # Nếu file đã tồn tại và kích thước hợp lệ thì dùng lại
    if os.path.exists(filepath) and os.path.getsize(filepath) > 10000:
        return True, {
            "filename": filename,
            "filepath": filepath,
            "download_url": f"/playback_clips/{filename}",
            "file_size": os.path.getsize(filepath),
            "file_size_mb": round(os.path.getsize(filepath) / (1024 * 1024), 2),
            "channel": nvr_channel,
            "start_time": s_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "end_time": e_dt.strftime("%Y-%m-%d %H:%M:%S")
        }

    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    if not cap.isOpened():
        return False, f"Không thể kết nối đến luồng Playback Kênh {nvr_channel} trên NVR (Khung giờ: {s_dt.strftime('%H:%M:%S')} - {e_dt.strftime('%H:%M:%S')})"

    ret, first_frame = cap.read()
    if not ret or first_frame is None:
        cap.release()
        return False, f"Đầu ghi NVR không có dữ liệu ghi hình cho Kênh {nvr_channel} tại khung giờ yêu cầu."

    orig_h, orig_w = first_frame.shape[:2]
    # Chuẩn hóa kích thước video MP4 xuống 1280x720 để tải nhanh
    target_w, target_h = 1280, 720
    if orig_w < target_w:
        target_w, target_h = orig_w, orig_h

    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(filepath, fourcc, 20.0, (target_w, target_h))

    frames_written = 0
    t0 = time.time()
    # Giới hạn tối đa frames (20 fps * số giây)
    max_frames = int(max(20, min(max_seconds, diff_sec + 2)) * 25)

    try:
        small_f = cv2.resize(first_frame, (target_w, target_h))
        out.write(small_f)
        frames_written += 1

        consec_fail = 0
        while frames_written < max_frames:
            ret, frame = cap.read()
            if not ret or frame is None:
                consec_fail += 1
                if consec_fail > 15:
                    break
                time.sleep(0.01)
                continue
            consec_fail = 0
            if frame.shape[1] != target_w or frame.shape[0] != target_h:
                frame = cv2.resize(frame, (target_w, target_h))
            out.write(frame)
            frames_written += 1

    finally:
        out.release()
        cap.release()

    if frames_written == 0 or not os.path.exists(filepath) or os.path.getsize(filepath) < 5000:
        if os.path.exists(filepath):
            try: os.remove(filepath)
            except: pass
        return False, "Không trích xuất được khung hình nào từ đầu ghi NVR."

    file_size = os.path.getsize(filepath)
    duration_est = round(frames_written / 20.0, 1)

    return True, {
        "filename": filename,
        "filepath": filepath,
        "download_url": f"/playback_clips/{filename}",
        "file_size": file_size,
        "file_size_mb": round(file_size / (1024 * 1024), 2),
        "channel": nvr_channel,
        "frames_count": frames_written,
        "duration_sec": duration_est,
        "start_time": s_dt.strftime("%Y-%m-%d %H:%M:%S"),
        "end_time": e_dt.strftime("%Y-%m-%d %H:%M:%S")
    }


def test_nvr_connection():
    """Kiểm tra tình trạng kết nối tới Đầu ghi Dahua NVR"""
    cfg = load_nvr_config()
    ip = cfg.get("ip", "192.168.100.200")
    rtsp_port = cfg.get("port", 554)
    http_port = cfg.get("http_port", 80)

    results = {
        "ip": ip,
        "brand": cfg.get("brand", "dahua"),
        "rtsp_port": rtsp_port,
        "http_port": http_port,
        "rtsp_online": False,
        "http_online": False,
        "channels": cfg.get("channels", {}),
        "channel_names": cfg.get("channel_names", {})
    }

    # Test TCP RTSP Port
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2.0)
        s.connect((ip, rtsp_port))
        s.close()
        results["rtsp_online"] = True
    except:
        results["rtsp_online"] = False

    # Test HTTP Port
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2.0)
        s.connect((ip, http_port))
        s.close()
        results["http_online"] = True
    except:
        results["http_online"] = False

    return results


if __name__ == "__main__":
    print("=== KIỂM TRA MODULE NVR PLAYBACK ===")
    status = test_nvr_connection()
    print("Kết nối NVR:", status)
    ch = get_nvr_channel_for_cam(2)
    print("Camera 2 -> NVR Channel:", ch)
