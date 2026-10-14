"""
=============================================================================
GIAO DIỆN TABLET KIOSK ĐIỂM DANH DOANH NGHIỆP (ENTERPRISE KIOSK UI/UX)
BỐ CỤC 3 CỘT CHUẨN:
  + CỘT 1 (TRÁI): THÔNG TIN CÁ NHÂN (MSNV, Vị trí, Phòng ban, Chấm công hôm nay)
  + CỘT 2 (GIỮA): HỆ THỐNG & CAMERA – Khung vuông lớn + Nút Chụp + Thông báo
  + CỘT 3 (PHẢI): LỊCH SỬ ĐIỂM DANH TỨC THỜI
- GIỮ NGUYÊN 100% CƠ CHẾ NHẬN DIỆN & TỐC ĐỘ
=============================================================================
"""

import os
import json

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_CACHE_FILE = os.path.join(_BASE_DIR, "api_employees_cache.json")

def _get_hrms_cache_dict():
    data = {}
    if os.path.exists(_CACHE_FILE):
        try:
            with open(_CACHE_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
            for eid, emp in raw.items():
                code = str(emp.get("EmployeeCode") or eid).strip().upper()
                item = {
                    "role": str(emp.get("Name_Role") or ""),
                    "workplace": str(emp.get("WorkPlaceName") or ""),
                    "dept": str(emp.get("Dept_Name") or ""),
                    "company": str(emp.get("Company_Name") or ""),
                    "name": str(emp.get("FullName") or "")
                }
                data[str(eid)] = item
                if code:
                    data[code] = item
        except Exception:
            pass
    return data

_RAW_HTML_KIOSK_TEMPLATE = """<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>SMART FACIAL ATTENDANCE KIOSK - HỆ THỐNG CHẤM CÔNG</title>
    
    <!-- Phông chữ chuẩn tiếng Việt cục bộ (Offline & Intranet 100% an toàn) -->
    <link rel="stylesheet" href="/static/fonts/fonts_local.css">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Be+Vietnam+Pro:ital,wght@0,300;0,400;0,500;0,600;0,700;0,800;1,400&family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <!-- MediaPipe Tasks Vision (Google AI Client-Side Detection & Tracking) -->
    <script src="/node_modules/@mediapipe/tasks-vision/vision_bundle.js"></script>
    
    <style>
        /* ==============================================================
           1. BIẾN MÀU & ĐỀ TÀI TỐI (DARK THEME)
           ============================================================== */
        :root {
            --bg-screen: #091322;
            --panel-bg: rgba(14, 24, 41, 0.92);
            --panel-border: rgba(56, 189, 248, 0.18);
            
            --card-bg: #111d2e;
            --card-hover: #16263d;
            --card-border: rgba(255, 255, 255, 0.08);

            --primary-blue: #38bdf8;
            --primary-glow: rgba(56, 189, 248, 0.5);
            --deep-blue: #0284c7;

            --status-green: #22c55e;
            --status-green-glow: rgba(34, 197, 94, 0.4);
            --status-green-bg: rgba(34, 197, 94, 0.12);

            --status-red: #ef4444;
            --status-red-bg: rgba(239, 68, 68, 0.12);

            --status-yellow: #f59e0b;
            --status-yellow-bg: rgba(245, 158, 11, 0.12);

            --text-white: #ffffff;
            --text-light: #e2e8f0;
            --text-muted: #94a3b8;
            --text-dim: #64748b;

            --font-stack: 'Be Vietnam Pro', 'Inter', Roboto, -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            user-select: none;
            -webkit-user-select: none;
        }

        html, body {
            width: 100%;
            height: 100%;
            overflow: hidden;
            background-color: #0b111e;
            font-family: var(--font-stack);
            color: var(--text-white);
            -webkit-font-smoothing: antialiased;
        }

        /* 2. NỀN VĂN PHÒNG & ĐỘ SÂU MÔI TRƯỜNG */
        .office-backdrop {
            width: 100vw;
            height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            background: radial-gradient(circle at 50% 25%, #1e293b 0%, #0f172a 60%, #070c14 100%);
            position: relative;
            padding: 16px 24px 30px;
        }

        .office-backdrop::before {
            content: '';
            position: absolute;
            top: 0; left: 0; right: 0; bottom: 0;
            background: 
                radial-gradient(circle at 10% 40%, rgba(34, 197, 94, 0.07) 0%, transparent 40%),
                radial-gradient(circle at 90% 50%, rgba(56, 189, 248, 0.07) 0%, transparent 45%),
                linear-gradient(90deg, rgba(255, 255, 255, 0.02) 1px, transparent 1px) 0 0 / 60px 60px;
            opacity: 0.7;
            pointer-events: none;
        }

        /* 3. VỎ MÀN HÌNH KIM LOẠI */
        .monitor-wrapper {
            position: relative;
            width: 100%;
            max-width: 1700px;
            height: 100%;
            max-height: 940px;
            display: flex;
            flex-direction: column;
            align-items: center;
            z-index: 10;
        }

        .monitor-bezel {
            position: relative;
            width: 100%;
            flex: 1;
            background: linear-gradient(135deg, #e2e8f0 0%, #cbd5e1 25%, #94a3b8 50%, #cbd5e1 75%, #f1f5f9 100%);
            border-radius: 20px;
            padding: 12px 14px 14px 14px;
            box-shadow: 
                0 25px 60px -10px rgba(0, 0, 0, 0.75),
                0 0 0 1px rgba(255, 255, 255, 0.6) inset,
                0 4px 12px rgba(0, 0, 0, 0.4);
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }

        .bezel-webcam-dot {
            position: absolute;
            top: 5px;
            left: 50%;
            transform: translateX(-50%);
            width: 8px;
            height: 8px;
            background: #090d16;
            border-radius: 50%;
            box-shadow: 0 0 2px rgba(56, 189, 248, 0.8), inset 0 0 1.5px #38bdf8;
            z-index: 20;
        }

        .monitor-neck {
            width: 140px;
            height: 30px;
            background: linear-gradient(180deg, #94a3b8 0%, #cbd5e1 45%, #64748b 100%);
            clip-path: polygon(18% 0%, 82% 0%, 100% 100%, 0% 100%);
            box-shadow: 0 6px 12px rgba(0, 0, 0, 0.4);
            flex-shrink: 0;
        }

        .monitor-base-foot {
            width: 260px;
            height: 10px;
            background: linear-gradient(90deg, #94a3b8 0%, #e2e8f0 50%, #94a3b8 100%);
            border-radius: 4px;
            box-shadow: 0 14px 30px rgba(0, 0, 0, 0.7), inset 0 1px 1px #ffffff;
            flex-shrink: 0;
        }

        /* 4. MÀN HÌNH HIỂN THỊ */
        .screen-display {
            width: 100%;
            height: 100%;
            background-color: var(--bg-screen);
            border-radius: 10px;
            border: 1.5px solid #000000;
            box-shadow: inset 0 0 15px rgba(0, 0, 0, 0.9);
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }

        /* 5. THANH HEADER TRÊN CÙNG */
        .kiosk-header {
            height: 62px;
            background: linear-gradient(180deg, rgba(11, 22, 38, 0.98) 0%, rgba(9, 18, 32, 0.95) 100%);
            border-bottom: 1px solid rgba(56, 189, 248, 0.15);
            padding: 0 22px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-shrink: 0;
        }

        .header-brand {
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .brand-avatar-ring {
            width: 36px;
            height: 36px;
            border-radius: 50%;
            background: linear-gradient(135deg, #0284c7 0%, #0369a1 100%);
            display: flex;
            align-items: center;
            justify-content: center;
            border: 1.5px solid rgba(56, 189, 248, 0.6);
            box-shadow: 0 0 12px rgba(2, 132, 199, 0.4);
        }

        .brand-avatar-ring svg {
            width: 18px;
            height: 18px;
            fill: none;
            stroke: #ffffff;
            stroke-width: 2.2;
            stroke-linecap: round;
            stroke-linejoin: round;
        }

        .brand-titles {
            display: flex;
            flex-direction: column;
        }

        .brand-main {
            font-size: 13.5px;
            font-weight: 800;
            letter-spacing: 0.5px;
            color: var(--text-white);
        }

        .brand-sub {
            font-size: 10px;
            font-weight: 600;
            letter-spacing: 0.8px;
            color: var(--primary-blue);
        }

        .header-clock-center {
            display: flex;
            align-items: center;
            gap: 14px;
        }

        .digital-clock {
            font-size: 26px;
            font-weight: 800;
            color: var(--primary-blue);
            letter-spacing: 1.5px;
            text-shadow: 0 0 16px var(--primary-glow);
            font-variant-numeric: tabular-nums;
        }

        .date-stacked {
            display: flex;
            flex-direction: column;
            text-align: left;
            line-height: 1.3;
        }

        .day-name {
            font-size: 11px;
            font-weight: 600;
            color: var(--text-muted);
        }

        .calendar-date {
            font-size: 11px;
            font-weight: 700;
            color: var(--text-white);
        }

        .header-actions {
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .action-btn {
            width: 36px;
            height: 36px;
            background: rgba(19, 32, 53, 0.85);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 8px;
            color: var(--text-light);
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            transition: all 0.2s ease;
        }

        .action-btn:hover {
            background: rgba(56, 189, 248, 0.2);
            border-color: var(--primary-blue);
            color: var(--primary-blue);
            transform: translateY(-1px);
        }

        .action-btn.active {
            background: rgba(56, 189, 248, 0.25);
            border-color: var(--primary-blue);
            color: var(--primary-blue);
        }

        .action-btn svg {
            width: 17px;
            height: 17px;
            fill: none;
            stroke: currentColor;
            stroke-width: 2;
            stroke-linecap: round;
            stroke-linejoin: round;
        }

        /* 6. BỐ CỤC 2 CỘT CHÍNH: CỘT THÔNG TIN VÀ CỘT HỆ THỐNG CAMERA */
        .kiosk-body-grid {
            flex: 1;
            display: grid;
            grid-template-columns: minmax(370px, 38%) 1fr;
            gap: 16px;
            padding: 16px 20px;
            overflow: hidden;
        }

        /* Ẩn cột lịch sử điểm danh theo yêu cầu, chỉ giữ 2 cột */
        .history-right-col {
            display: none !important;
        }

        .kiosk-col {
            height: 100%;
            display: flex;
            flex-direction: column;
            min-width: 0;
        }

        .panel-card-inner {
            height: 100%;
            background: var(--panel-bg);
            border: 1px solid var(--panel-border);
            border-radius: 14px;
            padding: 16px 18px;
            display: flex;
            flex-direction: column;
            backdrop-filter: blur(16px);
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.35);
            overflow: hidden;
        }

        .col-header-bar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 14px;
            flex-shrink: 0;
        }

        .col-title {
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 13.5px;
            font-weight: 700;
            color: var(--text-white);
        }

        .info-icon {
            width: 16px;
            height: 16px;
            fill: none;
            stroke: var(--primary-blue);
            stroke-width: 2.2;
            flex-shrink: 0;
        }

        .status-pill {
            display: flex;
            align-items: center;
            gap: 5px;
            padding: 3px 10px;
            border-radius: 999px;
            font-size: 11px;
            font-weight: 600;
        }

        .status-ready {
            background: var(--status-green-bg);
            border: 1px solid rgba(34, 197, 94, 0.3);
            color: var(--status-green);
        }

        .pulse-dot {
            width: 6px;
            height: 6px;
            border-radius: 50%;
            background: var(--status-green);
            box-shadow: 0 0 7px var(--status-green);
            animation: dotPulse 2s infinite;
        }

        @keyframes dotPulse {
            0%, 100% { opacity: 1; transform: scale(1); }
            50% { opacity: 0.35; transform: scale(0.8); }
        }

        /* ================================================================
           7. CỘT TRÁI: THÔNG TIN CÁ NHÂN
           ================================================================ */
        .personal-info-col {
            /* cột trái */
        }

        /* Avatar trống */
        .avatar-placeholder-wrap {
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 10px;
            padding: 18px 0 16px;
            flex-shrink: 0;
        }

        .avatar-box {
            width: 110px;
            height: 130px;
            border-radius: 12px;
            background: rgba(14, 26, 45, 0.9);
            border: 2px dashed rgba(56, 189, 248, 0.3);
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            gap: 8px;
            overflow: hidden;
            position: relative;
        }

        .avatar-box img {
            width: 100%;
            height: 100%;
            object-fit: cover;
            object-position: center top;
            display: none;
            position: absolute;
            top: 0; left: 0;
            border-radius: 10px;
        }

        .avatar-box img.has-photo {
            display: block;
        }

        .avatar-placeholder-icon {
            width: 44px;
            height: 44px;
            fill: none;
            stroke: rgba(56, 189, 248, 0.25);
            stroke-width: 1.5;
        }

        .avatar-placeholder-text {
            font-size: 10px;
            color: rgba(56, 189, 248, 0.35);
            font-weight: 500;
            letter-spacing: 0.3px;
        }

        .person-name-display {
            font-size: 15px;
            font-weight: 800;
            color: var(--text-white);
            text-align: center;
            letter-spacing: -0.2px;
            min-height: 20px;
        }

        /* Divider mỏng */
        .thin-divider {
            height: 1px;
            background: rgba(255, 255, 255, 0.07);
            margin: 10px 0;
            flex-shrink: 0;
        }

        /* Danh sách chi tiết cá nhân */
        .info-field-list {
            display: flex;
            flex-direction: column;
            gap: 8px;
            flex-shrink: 0;
        }

        .info-field-row {
            display: flex;
            flex-direction: column;
            gap: 2px;
        }

        .field-label {
            font-size: 10px;
            font-weight: 600;
            color: var(--text-dim);
            letter-spacing: 0.5px;
            text-transform: uppercase;
        }

        .field-value {
            font-size: 12.5px;
            font-weight: 700;
            color: var(--text-white);
            background: rgba(14, 26, 45, 0.6);
            border: 1px solid rgba(255, 255, 255, 0.07);
            border-radius: 7px;
            padding: 6px 10px;
            min-height: 32px;
            display: flex;
            align-items: center;
            word-break: break-word;
        }

        .field-value.empty-placeholder {
            color: var(--text-dim);
            font-weight: 400;
            font-size: 11.5px;
            font-style: italic;
        }

        /* Khu chấm công hôm nay */
        .today-attendance-block {
            margin-top: 10px;
            flex: 1;
            min-height: 0;
            display: flex;
            flex-direction: column;
            gap: 8px;
            overflow: hidden;
        }

        .today-attendance-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-shrink: 0;
            padding: 0 2px;
        }

        .section-label-heading {
            font-size: 11.5px;
            font-weight: 700;
            color: var(--text-muted);
            letter-spacing: 0.5px;
            text-transform: uppercase;
        }

        .today-count-badge {
            font-size: 11px;
            font-weight: 700;
            color: var(--primary-blue);
            background: rgba(56, 189, 248, 0.12);
            border: 1px solid rgba(56, 189, 248, 0.3);
            padding: 2px 8px;
            border-radius: 999px;
            letter-spacing: 0.3px;
            transition: all 0.3s ease;
        }

        .today-count-badge.has-logs {
            color: #4ade80;
            background: rgba(34, 197, 94, 0.15);
            border-color: rgba(34, 197, 94, 0.4);
        }

        .today-logs-container {
            flex: 1;
            min-height: 140px;
            max-height: 300px;
            overflow-y: auto;
            display: flex;
            flex-direction: column;
            gap: 7px;
            padding-right: 4px;
        }

        /* Thanh cuộn siêu gọn */
        .today-logs-container::-webkit-scrollbar {
            width: 4px;
        }
        .today-logs-container::-webkit-scrollbar-track {
            background: rgba(14, 26, 45, 0.4);
            border-radius: 4px;
        }
        .today-logs-container::-webkit-scrollbar-thumb {
            background: rgba(56, 189, 248, 0.3);
            border-radius: 4px;
        }
        .today-logs-container::-webkit-scrollbar-thumb:hover {
            background: rgba(56, 189, 248, 0.6);
        }

        .today-log-empty {
            padding: 16px 10px;
            text-align: center;
            font-size: 11.5px;
            color: var(--text-dim);
            font-style: italic;
            background: rgba(14, 26, 45, 0.4);
            border: 1px dashed rgba(255, 255, 255, 0.08);
            border-radius: 8px;
        }

        .today-log-row {
            background: rgba(14, 26, 45, 0.65);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 8px;
            padding: 6px 10px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 8px;
            transition: all 0.2s ease;
            flex-shrink: 0;
        }

        .today-log-row:hover {
            background: rgba(20, 38, 65, 0.8);
            border-color: rgba(56, 189, 248, 0.3);
        }

        .today-log-row.is-latest {
            border-color: rgba(34, 197, 94, 0.45);
            background: rgba(34, 197, 94, 0.09);
            box-shadow: 0 0 12px rgba(34, 197, 94, 0.12);
        }

        /* Khung ảnh thumbnail snapshot thời điểm chấm công */
        .today-log-thumb-wrap {
            width: 38px;
            height: 38px;
            border-radius: 6px;
            overflow: hidden;
            background: #08111d;
            border: 1.5px solid rgba(56, 189, 248, 0.25);
            flex-shrink: 0;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 2px 6px rgba(0, 0, 0, 0.4);
        }

        .today-log-thumb {
            width: 100%;
            height: 100%;
            object-fit: cover;
            display: block;
        }

        .today-log-thumb-fallback {
            width: 100%;
            height: 100%;
            display: flex;
            align-items: center;
            justify-content: center;
            background: rgba(15, 23, 42, 0.6);
        }

        .today-log-thumb-fallback svg {
            width: 20px;
            height: 20px;
            stroke: #64748b;
            stroke-width: 1.8;
            fill: none;
        }

        .today-log-row.is-latest .today-log-thumb-wrap {
            border-color: #22c55e;
            box-shadow: 0 0 10px rgba(34, 197, 94, 0.4);
        }

        .today-log-left {
            display: flex;
            align-items: center;
            gap: 8px;
            min-width: 0;
        }

        .today-log-idx {
            font-size: 10px;
            font-weight: 800;
            color: var(--text-dim);
            background: rgba(255, 255, 255, 0.06);
            border-radius: 4px;
            padding: 2px 5px;
            min-width: 24px;
            text-align: center;
            flex-shrink: 0;
            font-variant-numeric: tabular-nums;
        }

        .today-log-row.is-latest .today-log-idx {
            color: #4ade80;
            background: rgba(34, 197, 94, 0.22);
            font-weight: 900;
        }

        .today-log-meta {
            display: flex;
            flex-direction: column;
            min-width: 0;
        }

        .today-log-time {
            font-size: 12.5px;
            font-weight: 800;
            color: var(--text-white);
            font-variant-numeric: tabular-nums;
            letter-spacing: 0.3px;
            line-height: 1.2;
        }

        .today-log-row.is-latest .today-log-time {
            color: #86efac;
        }

        .today-log-cam {
            font-size: 9.5px;
            color: var(--text-dim);
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            max-width: 110px;
            line-height: 1.2;
            margin-top: 2px;
        }

        .today-log-right {
            display: flex;
            align-items: center;
            gap: 5px;
            flex-shrink: 0;
        }

        .today-log-tag-latest {
            font-size: 9px;
            font-weight: 700;
            color: #4ade80;
            background: rgba(34, 197, 94, 0.2);
            border: 1px solid rgba(34, 197, 94, 0.35);
            padding: 1px 5px;
            border-radius: 4px;
            text-transform: uppercase;
            letter-spacing: 0.3px;
        }

        .today-log-badge {
            font-size: 10px;
            font-weight: 700;
            padding: 3px 8px;
            border-radius: 5px;
            white-space: nowrap;
        }

        .today-log-badge-in {
            background: var(--status-green-bg);
            color: var(--status-green);
            border: 1px solid rgba(34, 197, 94, 0.35);
        }

        .today-log-badge-out {
            background: var(--status-red-bg);
            color: var(--status-red);
            border: 1px solid rgba(239, 68, 68, 0.35);
        }

        .today-log-badge-check {
            background: rgba(56, 189, 248, 0.15);
            color: #38bdf8;
            border: 1px solid rgba(56, 189, 248, 0.35);
        }

        /* ================================================================
           8. CỘT GIỮA: HỆ THỐNG & CAMERA
           ================================================================ */
        .camera-center-col {
            /* cột giữa */
        }

        /* Khung camera tỷ lệ chuẩn 4:3, mở rộng không gian hiển thị cho bố cục 2 cột */
        .camera-square-wrap {
            position: relative;
            width: 100%;
            aspect-ratio: 4 / 3;
            max-height: 480px;
            background: #000;
            border-radius: 14px;
            border: 2px solid rgba(56, 189, 248, 0.3);
            overflow: hidden;
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.6), 0 0 0 1px rgba(56, 189, 248, 0.08);
            flex-shrink: 0;
            margin-bottom: 12px;
            transition: border-color 0.3s ease, box-shadow 0.3s ease;
        }

        .camera-square-wrap.success-glow {
            border-color: #22c55e !important;
            box-shadow: 0 0 35px rgba(34, 197, 94, 0.75), inset 0 0 20px rgba(34, 197, 94, 0.35) !important;
        }

        .camera-square-wrap.success-glow .detection-bracket {
            border-color: #22c55e !important;
            filter: drop-shadow(0 0 10px #22c55e) !important;
        }

        .camera-square-wrap.spoof-glow {
            border-color: #ef4444 !important;
            box-shadow: 0 0 40px rgba(239, 68, 68, 0.9), inset 0 0 25px rgba(239, 68, 68, 0.45) !important;
            animation: spoofFlash 0.35s ease-in-out infinite alternate;
        }

        @keyframes spoofFlash {
            from { border-color: #ef4444; }
            to { border-color: #f59e0b; }
        }

        .camera-video-stream {
            position: absolute;
            inset: 0;
            width: 100%;
            height: 100%;
            object-fit: cover;
            display: block;
            /* Mặc định trực diện tự nhiên: Chữ trên trang phục, thẻ nhân viên đọc xuôi bình thường */
            transform: none;
            transition: transform 0.2s ease;
        }

        .camera-video-stream.is-mirrored {
            transform: scaleX(-1);
        }

        /* Canvas vẽ Bounding Box theo dõi khuôn mặt thời gian thực MediaPipe */
        .face-tracker-canvas {
            position: absolute;
            inset: 0;
            width: 100%;
            height: 100%;
            object-fit: cover;
            pointer-events: none;
            z-index: 10;
        }

        /* Lớp phủ khi camera tắt */
        .camera-idle-overlay {
            position: absolute;
            inset: 0;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            gap: 12px;
            background: radial-gradient(circle at center, #0d1b2e 0%, #060d18 100%);
        }

        .camera-idle-overlay svg {
            width: 64px;
            height: 64px;
            fill: none;
            stroke: rgba(56, 189, 248, 0.25);
            stroke-width: 1.5;
        }

        .camera-idle-text {
            font-size: 12px;
            color: rgba(56, 189, 248, 0.35);
            font-weight: 500;
            letter-spacing: 0.3px;
        }

        /* Khung nhận diện khuôn mặt */
        .face-detection-overlay {
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            width: 45%;
            height: 45%;
            pointer-events: none;
        }

        .detection-bracket {
            position: absolute;
            width: 22px;
            height: 22px;
            border-color: var(--status-green);
            border-style: solid;
            filter: drop-shadow(0 0 5px var(--status-green));
        }

        .db-tl { top: 0; left: 0; border-width: 2.5px 0 0 2.5px; border-top-left-radius: 4px; }
        .db-tr { top: 0; right: 0; border-width: 2.5px 2.5px 0 0; border-top-right-radius: 4px; }
        .db-bl { bottom: 0; left: 0; border-width: 0 0 2.5px 2.5px; border-bottom-left-radius: 4px; }
        .db-br { bottom: 0; right: 0; border-width: 0 2.5px 2.5px 0; border-bottom-right-radius: 4px; }

        .detection-alignment-laser {
            position: absolute;
            top: 48%;
            left: -20px;
            right: -20px;
            height: 1.5px;
            background: var(--status-green);
            box-shadow: 0 0 8px var(--status-green), 0 0 16px var(--status-green);
            animation: laserScanPulse 2.8s ease-in-out infinite alternate;
        }

        @keyframes laserScanPulse {
            0% { transform: translateY(-8px); opacity: 0.5; }
            50% { opacity: 1; }
            100% { transform: translateY(8px); opacity: 0.5; }
        }

        .camera-scanning-badge {
            position: absolute;
            top: 10px;
            right: 10px;
            background: rgba(34, 197, 94, 0.18);
            border: 1px solid rgba(34, 197, 94, 0.45);
            border-radius: 6px;
            padding: 4px 10px;
            font-size: 10.5px;
            font-weight: 700;
            color: var(--status-green);
            display: none;
            align-items: center;
            gap: 6px;
            letter-spacing: 0.3px;
        }

        .camera-scanning-badge.visible {
            display: inline-flex;
        }

        /* Nút CHỤP */
        .btn-capture-wrap {
            display: flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
            margin-bottom: 12px;
        }

        .btn-capture, .btn-refresh {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 10px;
            background: linear-gradient(135deg, #0284c7 0%, #0369a1 100%);
            border: 1px solid rgba(56, 189, 248, 0.4);
            border-radius: 10px;
            padding: 12px 30px;
            font-family: var(--font-stack);
            font-size: 14px;
            font-weight: 700;
            color: #ffffff;
            cursor: pointer;
            transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
            box-shadow: 0 4px 16px rgba(2, 132, 199, 0.35);
            letter-spacing: 0.2px;
        }

        .btn-capture:hover, .btn-refresh:hover {
            background: linear-gradient(135deg, #0369a1 0%, #0284c7 100%);
            border-color: rgba(56, 189, 248, 0.8);
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(2, 132, 199, 0.5);
        }

        .btn-capture:hover svg, .btn-refresh:hover svg {
            transform: rotate(180deg);
        }

        .btn-capture:active, .btn-refresh:active {
            transform: translateY(0);
        }

        .btn-capture svg, .btn-refresh svg {
            width: 20px;
            height: 20px;
            fill: none;
            stroke: currentColor;
            stroke-width: 2.2;
            stroke-linecap: round;
            stroke-linejoin: round;
            flex-shrink: 0;
            transition: transform 0.4s ease;
        }

        .btn-refresh.is-refreshing svg {
            animation: spinRefresh 0.8s linear infinite;
        }

        @keyframes spinRefresh {
            from { transform: rotate(0deg); }
            to { transform: rotate(360deg); }
        }

        /* Ô thông báo kết quả */
        .result-notification-box {
            flex-shrink: 0;
            border-radius: 10px;
            padding: 12px 16px;
            font-size: 13px;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 10px;
            min-height: 48px;
            background: rgba(14, 26, 45, 0.6);
            border: 1px solid rgba(255, 255, 255, 0.07);
            color: var(--text-muted);
            transition: all 0.3s ease;
            margin-bottom: 12px;
        }

        .result-notification-box.notif-idle {
            background: rgba(14, 26, 45, 0.6);
            border-color: rgba(255, 255, 255, 0.07);
            color: var(--text-muted);
        }

        .result-notification-box.notif-success {
            background: rgba(34, 197, 94, 0.1);
            border-color: rgba(34, 197, 94, 0.4);
            color: var(--status-green);
            box-shadow: 0 0 20px rgba(34, 197, 94, 0.1);
        }

        .result-notification-box.notif-error {
            background: rgba(239, 68, 68, 0.1);
            border-color: rgba(239, 68, 68, 0.4);
            color: var(--status-red);
        }

        .result-notification-box.notif-scanning {
            background: rgba(56, 189, 248, 0.1);
            border-color: rgba(56, 189, 248, 0.4);
            color: var(--primary-blue);
        }

        .result-notification-box svg {
            width: 18px;
            height: 18px;
            fill: none;
            stroke: currentColor;
            stroke-width: 2.2;
            stroke-linecap: round;
            stroke-linejoin: round;
            flex-shrink: 0;
        }

        /* Thẻ trạng thái hệ thống (bên dưới camera) */
        .system-status-mini-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 8px;
            flex: 1;
            align-content: start;
        }

        .mini-stat-card {
            background: rgba(14, 26, 45, 0.6);
            border: 1px solid rgba(255, 255, 255, 0.07);
            border-radius: 9px;
            padding: 9px 12px;
            display: flex;
            align-items: center;
            gap: 8px;
            transition: border-color 0.2s ease;
        }

        .mini-stat-card:hover {
            border-color: rgba(56, 189, 248, 0.3);
        }

        .mini-stat-icon {
            width: 26px;
            height: 26px;
            border-radius: 7px;
            display: flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
        }

        .mini-stat-icon.icon-green { background: rgba(34, 197, 94, 0.12); color: var(--status-green); }
        .mini-stat-icon.icon-blue { background: rgba(56, 189, 248, 0.12); color: var(--primary-blue); }

        .mini-stat-icon svg {
            width: 14px;
            height: 14px;
            fill: none;
            stroke: currentColor;
            stroke-width: 2.2;
            stroke-linecap: round;
            stroke-linejoin: round;
        }

        .mini-stat-label {
            font-size: 11px;
            font-weight: 600;
            color: var(--text-light);
            line-height: 1.3;
        }

        /* ================================================================
           9. CỘT PHẢI: LỊCH SỬ ĐIỂM DANH
           ================================================================ */
        .history-right-col {
            /* cột phải */
        }

        .history-counter-bar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 8px 12px;
            background: rgba(14, 26, 45, 0.6);
            border: 1px solid rgba(255, 255, 255, 0.07);
            border-radius: 8px;
            margin-bottom: 10px;
            flex-shrink: 0;
        }

        .counter-left {
            display: flex;
            align-items: center;
            gap: 5px;
            font-size: 12.5px;
            color: var(--text-white);
            font-weight: 700;
        }

        .counter-val {
            color: var(--primary-blue);
            font-weight: 800;
        }

        .counter-label-right {
            font-size: 11px;
            color: var(--text-muted);
            font-weight: 500;
        }

        .history-scroll-feed {
            flex: 1;
            overflow-y: auto;
            display: flex;
            flex-direction: column;
            gap: 5px;
            padding-right: 3px;
        }

        .history-scroll-feed::-webkit-scrollbar {
            width: 4px;
        }

        .history-scroll-feed::-webkit-scrollbar-track {
            background: transparent;
        }

        .history-scroll-feed::-webkit-scrollbar-thumb {
            background: rgba(56, 189, 248, 0.2);
            border-radius: 999px;
        }

        .history-card-item {
            background: rgba(14, 26, 45, 0.6);
            border: 1px solid rgba(255, 255, 255, 0.06);
            border-radius: 8px;
            padding: 7px 9px;
            display: flex;
            align-items: center;
            gap: 8px;
            transition: all 0.15s ease;
        }

        .history-card-item:hover {
            background: rgba(22, 38, 63, 0.8);
            border-color: rgba(56, 189, 248, 0.25);
        }

        .hist-avatar-circle {
            width: 32px;
            height: 32px;
            border-radius: 50%;
            background: rgba(30, 41, 59, 0.8);
            border: 1px solid rgba(255, 255, 255, 0.12);
            overflow: hidden;
            display: flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
        }

        .hist-avatar-circle img {
            width: 100%;
            height: 100%;
            object-fit: cover;
        }

        .hist-avatar-circle svg {
            width: 17px;
            height: 17px;
            fill: none;
            stroke: #64748b;
            stroke-width: 2;
        }

        .hist-user-meta {
            flex: 1;
            display: flex;
            flex-direction: column;
            min-width: 0;
        }

        .hist-user-name {
            font-size: 11px;
            font-weight: 700;
            color: var(--text-white);
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }

        .hist-user-sub {
            font-size: 9.5px;
            font-weight: 500;
            color: var(--text-muted);
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }

        .hist-badge {
            padding: 2px 8px;
            border-radius: 999px;
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 0.2px;
            flex-shrink: 0;
        }

        .hist-badge-in {
            background: var(--status-green-bg);
            border: 1px solid rgba(34, 197, 94, 0.3);
            color: var(--status-green);
        }

        .hist-badge-out {
            background: var(--status-red-bg);
            border: 1px solid rgba(239, 68, 68, 0.3);
            color: var(--status-red);
        }

        .hist-time-stamp {
            font-size: 10px;
            font-weight: 700;
            color: var(--text-dim);
            letter-spacing: 0.3px;
            flex-shrink: 0;
        }

        /* Responsive */
        @media (max-width: 1100px) {
            .kiosk-body-grid {
                grid-template-columns: 42% 58%;
                gap: 12px;
                padding: 12px;
            }
        }

        @media (max-width: 850px) {
            .office-backdrop { padding: 0; }
            .monitor-bezel { border-radius: 0; padding: 0; }
            .monitor-neck, .monitor-base-foot, .bezel-webcam-dot { display: none; }
            .kiosk-body-grid { grid-template-columns: 1fr; overflow-y: auto; gap: 10px; }
            .kiosk-col { height: auto; }
            .camera-square-wrap { max-height: 260px; }
        }

        /* Animation hiển thị thông báo */
        @keyframes fadeInUp {
            from { opacity: 0; transform: translateY(6px); }
            to { opacity: 1; transform: translateY(0); }
        }

        .anim-in {
            animation: fadeInUp 0.3s ease forwards;
        }

        /* ================================================================
           9. POPUP THÔNG BÁO NHẬN DIỆN GIỮA MÀN HÌNH CHÍNH (MODAL DIALOG)
           ================================================================ */
        .recognition-popup-modal {
            position: fixed;
            inset: 0;
            z-index: 99999;
            background: rgba(4, 9, 20, 0.78);
            backdrop-filter: blur(14px);
            -webkit-backdrop-filter: blur(14px);
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 16px;
            opacity: 0;
            pointer-events: none;
            transition: opacity 0.20s cubic-bezier(0.16, 1, 0.3, 1);
        }

        .recognition-popup-modal.active {
            opacity: 1;
            pointer-events: auto;
        }

        .recognition-popup-card {
            position: relative;
            width: 100%;
            max-width: 520px;
            background: linear-gradient(165deg, rgba(16, 28, 48, 0.96) 0%, rgba(9, 17, 30, 0.98) 100%);
            border: 1.5px solid rgba(56, 189, 248, 0.38);
            border-radius: 22px;
            padding: 24px 26px 20px;
            box-shadow: 
                0 25px 60px -10px rgba(0, 0, 0, 0.85),
                0 0 50px rgba(34, 197, 94, 0.35),
                inset 0 1px 0 rgba(255, 255, 255, 0.15);
            display: flex;
            flex-direction: column;
            align-items: center;
            transform: scale(0.82) translateY(28px);
            transition: transform 0.24s cubic-bezier(0.34, 1.56, 0.64, 1);
        }

        .recognition-popup-modal.active .recognition-popup-card {
            transform: scale(1) translateY(0);
        }

        .popup-close-btn {
            position: absolute;
            top: 14px;
            right: 14px;
            width: 34px;
            height: 34px;
            border-radius: 50%;
            background: rgba(255, 255, 255, 0.06);
            border: 1px solid rgba(255, 255, 255, 0.12);
            color: var(--text-muted);
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            transition: all 0.2s ease;
        }

        .popup-close-btn:hover {
            background: rgba(239, 68, 68, 0.2);
            border-color: rgba(239, 68, 68, 0.4);
            color: #ef4444;
            transform: rotate(90deg);
        }

        .popup-close-btn svg {
            width: 18px;
            height: 18px;
            stroke: currentColor;
            stroke-width: 2.2;
            stroke-linecap: round;
            fill: none;
        }

        .popup-status-badge-wrap {
            display: flex;
            align-items: center;
            gap: 12px;
            background: rgba(34, 197, 94, 0.1);
            border: 1px solid rgba(34, 197, 94, 0.35);
            padding: 8px 18px;
            border-radius: 40px;
            margin-bottom: 20px;
            box-shadow: 0 0 20px rgba(34, 197, 94, 0.2);
        }

        .popup-status-icon-ring {
            width: 28px;
            height: 28px;
            border-radius: 50%;
            background: linear-gradient(135deg, #22c55e 0%, #16a34a 100%);
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 0 12px rgba(34, 197, 94, 0.7);
            flex-shrink: 0;
        }

        .popup-status-icon-ring svg {
            width: 16px;
            height: 16px;
            stroke: #ffffff;
            stroke-width: 3;
            stroke-linecap: round;
            stroke-linejoin: round;
            fill: none;
        }

        .popup-status-text-wrap {
            display: flex;
            flex-direction: column;
        }

        .popup-status-tag {
            font-size: 13.5px;
            font-weight: 800;
            color: #22c55e;
            letter-spacing: 0.8px;
        }

        .popup-status-sub {
            font-size: 11px;
            color: #86efac;
            font-weight: 500;
        }

        .popup-profile-section {
            display: flex;
            flex-direction: column;
            align-items: center;
            margin-bottom: 20px;
            width: 100%;
        }

        /* Khung hiển thị 1 ảnh đại diện duy nhất (gọn gàng, sang trọng, không emoji) */
        .popup-single-avatar-wrap {
            display: flex;
            align-items: center;
            justify-content: center;
            margin-bottom: 14px;
            width: 100%;
        }

        .popup-single-avatar-ring {
            position: relative;
            width: 112px;
            height: 112px;
            border-radius: 50%;
            background: #0b1524;
            border: 3.5px solid #22c55e;
            box-shadow: 0 0 28px rgba(34, 197, 94, 0.45), 0 8px 24px rgba(0, 0, 0, 0.6);
            overflow: visible;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
        }

        .popup-single-avatar-inner {
            width: 100%;
            height: 100%;
            border-radius: 50%;
            overflow: hidden;
            display: flex;
            align-items: center;
            justify-content: center;
            position: relative;
            background: #08111d;
        }

        .popup-single-avatar-inner img {
            width: 100%;
            height: 100%;
            object-fit: cover;
            display: none;
        }

        .popup-single-avatar-inner img.has-photo {
            display: block;
        }

        .popup-avatar-fallback {
            display: flex;
            align-items: center;
            justify-content: center;
        }

        .popup-avatar-fallback svg {
            width: 52px;
            height: 52px;
            stroke: #64748b;
            stroke-width: 1.8;
            fill: none;
        }

        .popup-single-avatar-inner img.has-photo + .popup-avatar-fallback {
            display: none;
        }

        /* Biểu tượng tích xanh xác thực tinh tế ở góc dưới-phải (SVG chuẩn, không emoji) */
        .popup-avatar-verified-badge {
            position: absolute;
            bottom: 2px;
            right: 2px;
            width: 28px;
            height: 28px;
            background: #22c55e;
            border: 2.5px solid #0d1b2e;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.5);
            z-index: 2;
        }

        .popup-avatar-verified-badge svg {
            width: 15px;
            height: 15px;
            stroke: #ffffff;
            stroke-width: 3;
            fill: none;
        }

        .popup-names-wrap {
            text-align: center;
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 6px;
        }

        .popup-fullname {
            font-size: 22px;
            font-weight: 800;
            color: #ffffff;
            letter-spacing: 0.5px;
            margin: 0;
            text-transform: uppercase;
            text-shadow: 0 2px 8px rgba(0, 0, 0, 0.6);
        }

        .popup-code-pill {
            background: rgba(56, 189, 248, 0.12);
            border: 1px solid rgba(56, 189, 248, 0.45);
            color: #38bdf8;
            font-size: 13px;
            font-weight: 800;
            padding: 3px 14px;
            border-radius: 20px;
            letter-spacing: 0.5px;
        }

        .popup-details-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
            width: 100%;
            margin-bottom: 18px;
        }

        .popup-detail-item {
            background: rgba(14, 25, 43, 0.7);
            border: 1px solid rgba(255, 255, 255, 0.07);
            border-radius: 12px;
            padding: 10px 12px;
            display: flex;
            align-items: center;
            gap: 10px;
            min-width: 0;
        }

        .popup-detail-icon {
            width: 32px;
            height: 32px;
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
        }

        .popup-detail-icon svg {
            width: 16px;
            height: 16px;
            stroke-width: 2.2;
            stroke-linecap: round;
            stroke-linejoin: round;
            fill: none;
        }

        .popup-detail-icon.icon-cyan {
            background: rgba(56, 189, 248, 0.15);
            color: #38bdf8;
            stroke: #38bdf8;
        }

        .popup-detail-icon.icon-purple {
            background: rgba(168, 85, 247, 0.15);
            color: #c084fc;
            stroke: #c084fc;
        }

        .popup-detail-icon.icon-emerald {
            background: rgba(34, 197, 94, 0.15);
            color: #22c55e;
            stroke: #22c55e;
        }

        .popup-detail-icon.icon-amber {
            background: rgba(245, 158, 11, 0.15);
            color: #fbbf24;
            stroke: #fbbf24;
        }

        .popup-detail-content {
            display: flex;
            flex-direction: column;
            min-width: 0;
        }

        .popup-detail-label {
            font-size: 10px;
            color: var(--text-muted);
            font-weight: 500;
        }

        .popup-detail-value {
            font-size: 12.5px;
            font-weight: 700;
            color: var(--text-white);
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }

        .popup-detail-value.highlight-green {
            color: #4ade80;
            font-variant-numeric: tabular-nums;
        }

        .popup-detail-value.highlight-blue {
            color: #38bdf8;
        }

        .popup-countdown-bar-wrap {
            width: 100%;
            height: 4px;
            background: rgba(255, 255, 255, 0.08);
            border-radius: 999px;
            overflow: hidden;
            margin-bottom: 8px;
        }

        .popup-countdown-bar {
            height: 100%;
            width: 100%;
            background: linear-gradient(90deg, #22c55e 0%, #38bdf8 100%);
            box-shadow: 0 0 10px rgba(34, 197, 94, 0.8);
            transform-origin: left center;
        }

        .popup-footer-note {
            font-size: 11px;
            color: var(--text-dim);
            font-weight: 500;
            display: flex;
            align-items: center;
            gap: 4px;
        }

        .popup-footer-note strong {
            color: var(--primary-blue);
        }

        @media (max-width: 600px) {
            .recognition-popup-card {
                padding: 18px 16px 16px;
                border-radius: 18px;
            }
            .popup-fullname {
                font-size: 19px;
            }
            .popup-details-grid {
                grid-template-columns: 1fr;
                gap: 8px;
            }
            .popup-avatar-ring {
                width: 90px;
                height: 90px;
            }
        }
    </style>
</head>
<body>

    <div class="office-backdrop">

        <!-- Vỏ màn hình kim loại -->
        <div class="monitor-wrapper">
            <div class="monitor-bezel">
                <div class="bezel-webcam-dot" title="Camera tích hợp"></div>

                <div class="screen-display">

                    <!-- THANH HEADER TRÊN CÙNG -->
                    <header class="kiosk-header">
                        <div class="header-brand">
                            <div class="brand-avatar-ring">
                                <svg viewBox="0 0 24 24"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
                            </div>
                            <div class="brand-titles">
                                <h1 class="brand-main">SMART FACIAL ATTENDANCE KIOSK</h1>
                                <span class="brand-sub">HỆ THỐNG CHẤM CÔNG NHẬN DIỆN KHUÔN MẶT</span>
                            </div>
                        </div>

                        <div class="header-clock-center">
                            <div class="digital-clock" id="digital-clock">00:00:00</div>
                            <div class="date-stacked">
                                <span class="day-name" id="day-name">---</span>
                                <span class="calendar-date" id="calendar-date">--/--/----</span>
                            </div>
                        </div>

                        <div class="header-actions">
                            <button class="action-btn" id="btn-mirror" onclick="toggleMirrorMode()" title="Chế độ camera (Lật gương / Chống ngược chữ)">
                                <svg viewBox="0 0 24 24"><path d="M12 3v18M16 7l4 5-4 5M8 7L4 12l4 5"/></svg>
                            </button>
                            <button class="action-btn" id="btn-sound" onclick="toggleSound()" title="Âm thanh">
                                <svg viewBox="0 0 24 24"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"/></svg>
                            </button>
                            <button class="action-btn" id="btn-fullscreen" onclick="toggleFullScreen()" title="Toàn màn hình">
                                <svg viewBox="0 0 24 24"><path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/></svg>
                            </button>
                        </div>
                    </header>

                    <!-- BA CỘT CHÍNH -->
                    <main class="kiosk-body-grid">

                        <!-- ========== CỘT 1 (TRÁI): THÔNG TIN CÁ NHÂN ========== -->
                        <section class="kiosk-col personal-info-col">
                            <div class="panel-card-inner">
                                <div class="col-header-bar">
                                    <div class="col-title">
                                        <svg class="info-icon" viewBox="0 0 24 24"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
                                        <span>Thông Tin Cá Nhân</span>
                                    </div>
                                </div>

                                <!-- Avatar & Tên -->
                                <div class="avatar-placeholder-wrap">
                                    <div class="avatar-box" id="avatar-box">
                                        <svg class="avatar-placeholder-icon" viewBox="0 0 24 24">
                                            <circle cx="12" cy="8" r="4"/>
                                            <path d="M4 20c0-4 3.6-7 8-7s8 3 8 7"/>
                                        </svg>
                                        <span class="avatar-placeholder-text">Chưa nhận diện</span>
                                        <img id="user-avatar" src="" alt="Ảnh nhân viên">
                                    </div>
                                    <div class="person-name-display" id="user-fullname">---</div>
                                </div>

                                <div class="thin-divider"></div>

                                <!-- Danh sách trường thông tin -->
                                <div class="info-field-list">
                                    <div class="info-field-row">
                                        <span class="field-label">Mã số nhân viên</span>
                                        <div class="field-value empty-placeholder" id="user-empid">Chưa có dữ liệu</div>
                                    </div>
                                    <div class="info-field-row">
                                        <span class="field-label">Vị trí / Chức danh</span>
                                        <div class="field-value empty-placeholder" id="user-position">Chưa có dữ liệu</div>
                                    </div>
                                    <div class="info-field-row">
                                        <span class="field-label">Vị trí làm việc</span>
                                        <div class="field-value empty-placeholder" id="user-workplace">Chưa có dữ liệu</div>
                                    </div>
                                    <div class="info-field-row">
                                        <span class="field-label">Phòng ban</span>
                                        <div class="field-value empty-placeholder" id="user-dept">Chưa có dữ liệu</div>
                                    </div>
                                </div>

                                <div class="thin-divider"></div>

                                <!-- Thông tin chấm công hôm nay (Toàn bộ lượt chấm trong ngày) -->
                                <div class="today-attendance-block">
                                    <div class="today-attendance-header">
                                        <div class="section-label-heading">Chấm công hôm nay</div>
                                        <span class="today-count-badge" id="today-count-badge">0 lượt</span>
                                    </div>
                                    <div class="today-logs-container" id="today-logs-container">
                                        <div class="today-log-empty" id="today-log-empty">Chưa có lượt chấm công hôm nay</div>
                                    </div>
                                </div>

                            </div>
                        </section>

                        <!-- ========== CỘT 2 (GIỮA): HỆ THỐNG & CAMERA ========== -->
                        <section class="kiosk-col camera-center-col">
                            <div class="panel-card-inner">
                                <div class="col-header-bar">
                                    <div class="col-title">
                                        <svg class="info-icon" viewBox="0 0 24 24"><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/></svg>
                                        <span>Hệ Thống Camera</span>
                                    </div>
                                    <div class="status-pill status-ready" id="system-status-pill">
                                        <span class="pulse-dot"></span>
                                        <span id="system-status-text">Sẵn sàng</span>
                                    </div>
                                </div>

                                <!-- Khung camera vuông lớn -->
                                <div class="camera-square-wrap" id="camera-square-wrap">
                                    <!-- Video webcam máy tính / tablet -->
                                    <video class="camera-video-stream" id="tablet-webcam-video"
                                        autoplay playsinline muted style="display: none;"></video>

                                    <!-- Canvas vẽ Bounding Box theo dõi khuôn mặt thời gian thực MediaPipe -->
                                    <canvas class="face-tracker-canvas" id="face-tracker-canvas" style="display: none;"></canvas>

                                    <!-- Trạng thái camera tắt -->
                                    <div class="camera-idle-overlay" id="camera-idle-overlay">
                                        <svg viewBox="0 0 24 24">
                                            <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/>
                                            <circle cx="12" cy="13" r="4"/>
                                        </svg>
                                        <span class="camera-idle-text">Đang kết nối camera tự động...</span>
                                    </div>

                                    <!-- Khung nhận diện khuôn mặt (chỉ hiện khi camera bật) -->
                                    <div class="face-detection-overlay" id="face-detection-overlay" style="display:none;">
                                        <div class="detection-bracket db-tl"></div>
                                        <div class="detection-bracket db-tr"></div>
                                        <div class="detection-bracket db-bl"></div>
                                        <div class="detection-bracket db-br"></div>
                                        <div class="detection-alignment-laser"></div>
                                    </div>

                                    <!-- Badge "Đang quét" -->
                                    <div class="camera-scanning-badge" id="camera-scanning-badge">
                                        <span class="pulse-dot"></span>Đang quét liên tục...
                                    </div>
                                </div>

                                <!-- Nút Làm Mới Hệ Thống (Làm mới sạch sẽ & giữ nguyên chế độ Toàn màn hình) -->
                                <div class="btn-capture-wrap">
                                    <button class="btn-capture btn-refresh" id="btn-refresh" onclick="handleRefreshButton()" title="Làm mới toàn bộ hệ thống (Giữ nguyên toàn màn hình)">
                                        <svg id="btn-refresh-icon" viewBox="0 0 24 24"><path d="M23 4v6h-6M1 20v-6h6"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>
                                        <span id="btn-refresh-label">Làm Mới Hệ Thống</span>
                                    </button>
                                </div>

                                <!-- Ô thông báo kết quả -->
                                <div class="result-notification-box notif-idle" id="result-notification-box">
                                    <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
                                    <span id="result-notification-text">Camera đang tự động quét • Vui lòng nhìn thẳng để điểm danh</span>
                                </div>

                                <!-- Thẻ trạng thái hệ thống mini -->
                                <div class="system-status-mini-grid">
                                    <div class="mini-stat-card">
                                        <div class="mini-stat-icon icon-green">
                                            <svg viewBox="0 0 24 24"><path d="M23 7l-7 5 7 5V7z"/><rect x="1" y="5" width="15" height="14" rx="2" ry="2"/></svg>
                                        </div>
                                        <span class="mini-stat-label">Camera Trực Tuyến</span>
                                    </div>
                                    <div class="mini-stat-card">
                                        <div class="mini-stat-icon icon-green">
                                            <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><path d="M16.2 7.8l-4.2 4.2"/><circle cx="12" cy="12" r="2"/></svg>
                                        </div>
                                        <span class="mini-stat-label">Tốc Độ Quét</span>
                                    </div>
                                    <div class="mini-stat-card">
                                        <div class="mini-stat-icon icon-green">
                                            <svg viewBox="0 0 24 24"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/></svg>
                                        </div>
                                        <span class="mini-stat-label">Phản Hồi Tự Động</span>
                                    </div>
                                    <div class="mini-stat-card">
                                        <div class="mini-stat-icon icon-blue">
                                            <svg viewBox="0 0 24 24"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
                                        </div>
                                        <span class="mini-stat-label">Bảo Mật</span>
                                    </div>
                                </div>

                            </div>
                        </section>

                        <!-- ========== CỘT 3 (PHẢI): LỊCH SỬ ĐIỂM DANH (ĐÃ ẨN THEO YÊU CẦU) ========== -->
                        <section class="kiosk-col history-right-col" style="display: none;">
                            <div class="panel-card-inner">
                                <div class="col-header-bar">
                                    <div class="col-title">
                                        <svg class="info-icon" viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>
                                        <span>Lịch Sử Điểm Danh</span>
                                    </div>
                                </div>

                                <div class="history-counter-bar">
                                    <div class="counter-left">
                                        <span>Tổng lượt chấm hôm nay:</span>
                                        <strong class="counter-val" id="counter-total">0</strong>
                                    </div>
                                    <span class="counter-label-right">lượt</span>
                                </div>

                                <div class="history-scroll-feed" id="history-scroll-feed">
                                    <!-- Dữ liệu sẽ được cập nhật tự động từ server -->
                                    <div style="text-align:center; padding: 30px 10px; color: var(--text-dim); font-size: 12px;">
                                        Chưa có lượt chấm công nào hôm nay
                                    </div>
                                </div>

                            </div>
                        </section>

                    </main>

                </div>
            </div>

            <!-- Chân đế màn hình -->
            <div class="monitor-neck"></div>
            <div class="monitor-base-foot"></div>
        </div>

    <!-- ============================================================== -->
    <!-- POPUP THÔNG BÁO NHẬN DIỆN THÔNG TIN Ở GIỮA MÀN HÌNH CHÍNH      -->
    <!-- ============================================================== -->
    <div id="recognition-popup-modal" class="recognition-popup-modal" onclick="handlePopupBackdropClick(event)">
        <div class="recognition-popup-card" onclick="event.stopPropagation()">
            <!-- Nút đóng nhanh -->
            <button class="popup-close-btn" onclick="closeRecognitionPopup()" title="Đóng" type="button">
                <svg viewBox="0 0 24 24"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
            </button>

            <!-- Huy hiệu thành công phát sáng -->
            <div class="popup-status-badge-wrap">
                <div class="popup-status-icon-ring">
                    <svg viewBox="0 0 24 24">
                        <polyline points="20 6 9 17 4 12"></polyline>
                    </svg>
                </div>
                <div class="popup-status-text-wrap">
                    <span class="popup-status-tag" id="popup-status-tag">CHẤM CÔNG THÀNH CÔNG</span>
                    <span class="popup-status-sub" id="popup-status-sub">Xác thực khuôn mặt hợp lệ</span>
                </div>
            </div>

            <!-- Khu vực thông tin cá nhân & Ảnh đại diện duy nhất -->
            <div class="popup-profile-section">
                <!-- 1 ô Avatar duy nhất trong Popup (gọn gàng, sang trọng, không emoji) -->
                <div class="popup-single-avatar-wrap">
                    <div class="popup-single-avatar-ring">
                        <div class="popup-single-avatar-inner">
                            <img id="popup-avatar-img" src="" alt="Ảnh đại diện" onerror="handlePopupAvatarError(this)">
                            <div class="popup-avatar-fallback">
                                <svg viewBox="0 0 24 24"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
                            </div>
                        </div>
                        <div class="popup-avatar-verified-badge" title="Đã xác thực">
                            <svg viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"></polyline></svg>
                        </div>
                    </div>
                </div>

                <div class="popup-names-wrap">
                    <h2 class="popup-fullname" id="popup-fullname">---</h2>
                    <div class="popup-code-pill" id="popup-empid">---</div>
                </div>
            </div>

            <!-- Bảng thông tin chi tiết -->
            <div class="popup-details-grid">
                <div class="popup-detail-item">
                    <div class="popup-detail-icon icon-cyan">
                        <svg viewBox="0 0 24 24"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
                    </div>
                    <div class="popup-detail-content">
                        <span class="popup-detail-label">Vị trí / Chức danh</span>
                        <strong class="popup-detail-value" id="popup-role">---</strong>
                    </div>
                </div>

                <div class="popup-detail-item">
                    <div class="popup-detail-icon icon-purple">
                        <svg viewBox="0 0 24 24"><rect x="3" y="3" width="7" height="7"></rect><rect x="14" y="3" width="7" height="7"></rect><rect x="14" y="14" width="7" height="7"></rect><rect x="3" y="14" width="7" height="7"></rect></svg>
                    </div>
                    <div class="popup-detail-content">
                        <span class="popup-detail-label">Phòng ban</span>
                        <strong class="popup-detail-value" id="popup-dept">---</strong>
                    </div>
                </div>

                <div class="popup-detail-item">
                    <div class="popup-detail-icon icon-emerald">
                        <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>
                    </div>
                    <div class="popup-detail-content">
                        <span class="popup-detail-label">Thời gian điểm danh</span>
                        <strong class="popup-detail-value highlight-green" id="popup-time">--:--:--</strong>
                    </div>
                </div>

                <div class="popup-detail-item">
                    <div class="popup-detail-icon icon-amber">
                        <svg viewBox="0 0 24 24"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
                    </div>
                    <div class="popup-detail-content">
                        <span class="popup-detail-label">Độ tin cậy</span>
                        <strong class="popup-detail-value highlight-blue" id="popup-confidence">---</strong>
                    </div>
                </div>
            </div>

            <!-- Thanh tiến trình tự động đóng -->
            <div class="popup-countdown-bar-wrap">
                <div class="popup-countdown-bar" id="popup-countdown-bar"></div>
            </div>
            <div class="popup-footer-note">
                <span>Tự động chuyển tiếp sau <strong id="popup-countdown-num">1.5s</strong></span>
            </div>
        </div>
    </div>

    <!-- Canvas ẩn để chụp ảnh từ webcam -->
    <canvas id="webcam-capture-canvas" width="640" height="480" style="display: none;"></canvas>

    <script>
        // =====================================================================
        // CSDL NHÂN SỰ TỪ CACHE SMART HRMS (HMAC-MD5 API)
        // =====================================================================
        const HRMS_CACHE = /* __HRMS_CACHE_DATA__ */ {};

        // =====================================================================
        // BIẾN TOÀN CỤC
        // =====================================================================
        let isSoundEnabled   = true;
        let isWebcamActive   = false;
        let webcamStream     = null;
        let isScanningBusy   = false;
        let audioCtx         = null;
        let lastHandledCardId = null;
        let lastHandledEventId = 0; // ID sự kiện tuần tự từ server để đồng bộ đa trình duyệt chính xác 100%
        let cameraMode       = 'idle';   // 'idle' | 'open' | 'scanning'
        let resultClearTimer = null;

        // =====================================================================
        // 1. ĐỒNG HỒ THỜI GIAN THỰC
        // =====================================================================
        function updateClock() {
            const now = new Date();
            const days = ['Chủ Nhật', 'Thứ Hai', 'Thứ Ba', 'Thứ Tư', 'Thứ Năm', 'Thứ Sáu', 'Thứ Bảy'];
            const dd   = String(now.getDate()).padStart(2, '0');
            const mm   = String(now.getMonth() + 1).padStart(2, '0');
            const yyyy = now.getFullYear();
            const hh   = String(now.getHours()).padStart(2, '0');
            const min  = String(now.getMinutes()).padStart(2, '0');
            const ss   = String(now.getSeconds()).padStart(2, '0');

            const clockEl = document.getElementById('digital-clock');
            const dayEl   = document.getElementById('day-name');
            const dateEl  = document.getElementById('calendar-date');

            if (clockEl) clockEl.textContent = `${hh}:${min}:${ss}`;
            if (dayEl)   dayEl.textContent   = days[now.getDay()];
            if (dateEl)  dateEl.textContent  = `${dd}/${mm}/${yyyy}`;
        }
        setInterval(updateClock, 1000);
        updateClock();

        // =====================================================================
        // 2. ÂM THANH
        // =====================================================================
        function getAudioContext() {
            if (!audioCtx) {
                const AudioContext = window.AudioContext || window.webkitAudioContext;
                audioCtx = new AudioContext();
            }
            if (audioCtx.state === 'suspended') audioCtx.resume();
            return audioCtx;
        }

        function playSuccessSound() {
            if (!isSoundEnabled) return;
            try {
                const ctx = getAudioContext();
                const now = ctx.currentTime;
                [[880, 0], [1100, 0.1], [1320, 0.22]].forEach(([freq, delay]) => {
                    const osc  = ctx.createOscillator();
                    const gain = ctx.createGain();
                    osc.type = 'sine';
                    osc.frequency.setValueAtTime(freq, now + delay);
                    gain.gain.setValueAtTime(0.18, now + delay);
                    gain.gain.exponentialRampToValueAtTime(0.0001, now + delay + 0.6);
                    osc.connect(gain);
                    gain.connect(ctx.destination);
                    osc.start(now + delay);
                    osc.stop(now + delay + 0.6);
                });
            } catch (e) {}
        }

        function playErrorSound() {
            if (!isSoundEnabled) return;
            try {
                const ctx = getAudioContext();
                const now = ctx.currentTime;
                const osc  = ctx.createOscillator();
                const gain = ctx.createGain();
                osc.type = 'sawtooth';
                osc.frequency.setValueAtTime(220, now);
                osc.frequency.linearRampToValueAtTime(160, now + 0.4);
                gain.gain.setValueAtTime(0.12, now);
                gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.5);
                osc.connect(gain);
                gain.connect(ctx.destination);
                osc.start(now);
                osc.stop(now + 0.5);
            } catch (e) {}
        }

        // Hàm chọn giọng đọc tiếng Việt hay nhất (Ưu tiên Google nữ / Microsoft Mai / Natural)
        function getBestVietnameseVoice() {
            const voices = window.speechSynthesis.getVoices();
            return voices.find(v => v.lang === 'vi-VN' && (v.name.includes('Google') || v.name.includes('Mai') || v.name.includes('Natural')))
                || voices.find(v => v.lang === 'vi-VN')
                || null;
        }

        // Hàm phát nhiều câu chúc thông minh theo khung giờ trong ngày
        function speakGreeting(fullName) {
            if (!isSoundEnabled || !('speechSynthesis' in window)) return;
            window.speechSynthesis.cancel();

            const hour = new Date().getHours();
            let wishes = [];

            if (hour < 11) {
                // Buổi sáng
                wishes = [
                    `Chào buổi sáng ${fullName}! Chúc bạn một ngày làm việc tràn đầy năng lượng!`,
                    `Xin chào ${fullName}! Chúc bạn một ngày tốt lành và nhiều niềm vui!`,
                    `Điểm danh thành công! Chúc ${fullName} ngày mới thuận lợi và may mắn!`
                ];
            } else if (hour >= 11 && hour < 17) {
                // Buổi trưa / chiều
                wishes = [
                    `Chào buổi chiều ${fullName}! Chúc bạn hoàn thành xuất sắc công việc!`,
                    `Xin chào ${fullName}! Chúc bạn một buổi chiều làm việc hiệu quả và vui vẻ!`,
                    `Đã ghi nhận điểm danh! Chúc ${fullName} luôn ngập tràn năng lượng!`
                ];
            } else {
                // Buổi tối / Tan ca
                wishes = [
                    `Tạm biệt ${fullName}! Chúc bạn một buổi tối thật ấm áp bên gia đình!`,
                    `Đã ghi nhận tan ca! Cảm ơn ${fullName} đã cống hiến hết mình hôm nay!`,
                    `Chúc ${fullName} buổi tối vui vẻ và nghỉ ngơi thật thoải mái nhé!`
                ];
            }

            // Chọn ngẫu nhiên 1 câu chúc trong danh sách
            const randomWish = wishes[Math.floor(Math.random() * wishes.length)];
            const utterance = new SpeechSynthesisUtterance(randomWish);
            utterance.lang  = 'vi-VN';
            utterance.rate  = 1.0;   // Tốc độ vừa phải, tự nhiên
            utterance.pitch = 1.05;  // Giọng trong trẻo, vui tươi

            const chosenVoice = getBestVietnameseVoice();
            if (chosenVoice) utterance.voice = chosenVoice;

            window.speechSynthesis.speak(utterance);
        }

        // Hàm cảnh báo nhẹ nhàng, lịch sự (không dùng từ "giả mạo")
        function speakWarning(msg) {
            if (!isSoundEnabled || !('speechSynthesis' in window)) return;
            window.speechSynthesis.cancel();

            // Thay thế từ ngữ nặng nề bằng câu hướng dẫn lịch sự
            const politeWarning = 'Vui lòng nhìn thẳng vào camera và thử lại.';
            const utterance = new SpeechSynthesisUtterance(msg || politeWarning);
            utterance.lang  = 'vi-VN';
            utterance.rate  = 1.0;
            utterance.pitch = 1.0;

            const chosenVoice = getBestVietnameseVoice();
            if (chosenVoice) utterance.voice = chosenVoice;

            window.speechSynthesis.speak(utterance);
        }

        function toggleSound() {
            isSoundEnabled = !isSoundEnabled;
            const btn = document.getElementById('btn-sound');
            btn.classList.toggle('active', isSoundEnabled);
            getAudioContext();
        }

        // =====================================================================
        // 3. MEDIAPIPE FACE DETECTOR (CLIENT-SIDE TRIGGER TRÊN TABLET) & SCANNER
        // =====================================================================
        let isScanLoopRunning    = false;
        let isFrameProcessing    = false;
        let scanLoopTimer        = null;
        let scanPauseUntil       = 0;         // Tạm dừng ngắn sau khi nhận diện thành công hoặc cảnh báo spoof
        let lastSuccessEmpId     = null;      // ID nhân sự vừa nhận diện thành công
        let lastSuccessTime      = 0;         // Thời điểm nhận diện thành công gần nhất
        let lastFaceDetectedTime = Date.now();// Thời điểm thấy mặt gần nhất (auto-idle 90s)
        let lastServerCallTime   = 0;         // Thời điểm gửi frame lên server gần nhất
        let isSpoofWarningActive = false;     // Trạng thái đang cảnh báo ảnh giả mạo
        let spoofWarningTimer    = null;      // Bộ đếm thời gian hiệu ứng cảnh báo
        let mpFaceDetector       = null;      // Thể hiện MediaPipe FaceDetector
        let isMpLoading          = false;     // Cờ tải MediaPipe
        const SCAN_INTERVAL_MS   = 250;       // Tần suất gửi server: 250ms (nhạy, mượt mà, độ trễ thấp)
        const RECOG_COOLDOWN_MS  = 3500;      // Chống lặp lại cùng 1 người trong 3.5s khi vẫn đứng trước cam
        const SUCCESS_PAUSE_MS   = 1000;      // Tạm dừng đúng 1.0s khớp thời gian popup để hoàn tất các bước và chuyển chụp mới
        const AUTO_IDLE_TIMEOUT  = 90000;     // Tự động tạm dừng camera sau 90s nếu không có người

        // Chế độ camera: Mặc định trực diện tự nhiên (false) để chữ trên áo/thẻ nhân viên không bị ngược
        let isMirrorMode = false;
        try { isMirrorMode = (localStorage.getItem('kiosk_mirror_mode') === '1'); } catch(e){}

        function toggleMirrorMode() {
            isMirrorMode = !isMirrorMode;
            try { localStorage.setItem('kiosk_mirror_mode', isMirrorMode ? '1' : '0'); } catch(e){}
            applyMirrorMode();
            clearFaceTrackerCanvas();
        }

        function applyMirrorMode() {
            const videoEl = document.getElementById('tablet-webcam-video');
            if (videoEl) {
                videoEl.classList.toggle('is-mirrored', isMirrorMode);
            }
            const btn = document.getElementById('btn-mirror');
            if (btn) {
                btn.classList.toggle('active', isMirrorMode);
                btn.title = isMirrorMode ? 'Chế độ: Gương soi (Bấm để chuyển Trực diện chống ngược chữ)' : 'Chế độ: Trực diện (Chống ngược chữ, bấm để chuyển Gương soi)';
            }
        }

        // Khởi tạo MediaPipe Face Detector trực tiếp trên Browser qua WebAssembly
        async function initMediaPipeFaceDetector() {
            if (mpFaceDetector) return mpFaceDetector;
            if (isMpLoading) return null;
            if (typeof Vision === 'undefined') {
                console.warn('[MediaPipe] Thư viện Vision chưa tải xong.');
                return null;
            }

            try {
                isMpLoading = true;
                const wasmResolver = await Vision.FilesetResolver.forVisionTasks('/node_modules/@mediapipe/tasks-vision/wasm');
                try {
                    mpFaceDetector = await Vision.FaceDetector.createFromOptions(wasmResolver, {
                        baseOptions: {
                            modelAssetPath: '/models/blaze_face_short_range.tflite',
                            delegate: 'GPU'
                        },
                        runningMode: 'VIDEO',
                        minDetectionConfidence: 0.52
                    });
                    console.log('✔ [MediaPipe] Đã sẵn sàng Face Detector (GPU Delegate).');
                } catch (gpuErr) {
                    console.warn('[MediaPipe] Không hỗ trợ GPU, chuyển fallback sang CPU:', gpuErr);
                    mpFaceDetector = await Vision.FaceDetector.createFromOptions(wasmResolver, {
                        baseOptions: {
                            modelAssetPath: '/models/blaze_face_short_range.tflite',
                            delegate: 'CPU'
                        },
                        runningMode: 'VIDEO',
                        minDetectionConfidence: 0.52
                    });
                    console.log('✔ [MediaPipe] Đã sẵn sàng Face Detector (CPU Fallback).');
                }
            } catch (err) {
                console.error('[MediaPipe] Khởi tạo Face Detector thất bại:', err);
            } finally {
                isMpLoading = false;
            }
            return mpFaceDetector;
        }

        // Tự động khởi động camera & chạy quét nhận diện ngay khi mở Kiosk
        async function autoStartScannerOnPageLoad() {
            try {
                applyMirrorMode();
                if (!isWebcamActive) {
                    await startContinuousScanner();
                }
            } catch (err) {
                console.warn('[Kiosk AutoStart]', err);
            }
        }

        // Tự động tải trước MediaPipe & khởi động Camera ngay khi mở trang
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => { 
                applyMirrorMode();
                initMediaPipeFaceDetector();
                setTimeout(autoStartScannerOnPageLoad, 400);
            });
        } else {
            applyMirrorMode();
            initMediaPipeFaceDetector();
            setTimeout(autoStartScannerOnPageLoad, 400);
        }

        // Tự động mở lại camera nếu trang lấy lại tiêu điểm (tab focus / tablet screen wakeup)
        window.addEventListener('focus', () => {
            if (!isWebcamActive) {
                setTimeout(autoStartScannerOnPageLoad, 200);
            }
        });

        // Hỗ trợ nhấn phím F5 trên bàn phím cứng gọi làm mới hệ thống mượt mà
        window.addEventListener('keydown', (e) => {
            if (e.key === 'F5' || (e.ctrlKey && e.key === 'r') || (e.ctrlKey && e.key === 'F5')) {
                e.preventDefault();
                handleRefreshButton();
            }
        });

        // Vẽ khung Bounding Box bám dính khuôn mặt & Laser Bracket thời gian thực
        function drawFaceTrackingOverlay(detections) {
            const canvas = document.getElementById('face-tracker-canvas');
            if (!canvas) return;
            const ctx = canvas.getContext('2d');
            ctx.clearRect(0, 0, canvas.width, canvas.height);

            if (!detections || detections.length === 0) return;

            // Tìm khuôn mặt gần camera nhất (diện tích lớn nhất)
            const primaryDetection = detections.reduce((max, d) => 
                (d.boundingBox.width * d.boundingBox.height > max.boundingBox.width * max.boundingBox.height) ? d : max, 
                detections[0]
            );

            const bbox = primaryDetection.boundingBox;
            const padX = bbox.width * 0.12;
            const padY = bbox.height * 0.14;
            let x;
            if (isMirrorMode) {
                const mirroredX = canvas.width - (bbox.originX + bbox.width);
                x = Math.max(0, mirroredX - padX);
            } else {
                x = Math.max(0, bbox.originX - padX);
            }
            const y = Math.max(0, bbox.originY - padY);
            const w = Math.min(canvas.width - x, bbox.width + padX * 2);
            const h = Math.min(canvas.height - y, bbox.height + padY * 2);

            let mainColor = '#38bdf8'; // Cyan mặc định
            let glowColor = 'rgba(56, 189, 248, 0.45)';
            let statusText = 'AI TRACKING • NHÌN THẲNG';

            if (isSpoofWarningActive) {
                mainColor = '#ef4444'; // Đỏ cảnh báo ảnh giả mạo
                glowColor = 'rgba(239, 68, 68, 0.7)';
                statusText = '⚠️ CẢNH BÁO: ẢNH GIẢ MẠO';
            } else if (Date.now() < scanPauseUntil) {
                mainColor = '#22c55e'; // Xanh lá thành công
                glowColor = 'rgba(34, 197, 94, 0.7)';
                statusText = '✓ ĐÃ XÁC THỰC THÀNH CÔNG';
            }

            ctx.save();
            ctx.strokeStyle = mainColor;
            ctx.fillStyle = mainColor;
            ctx.lineWidth = 3.5;
            ctx.lineCap = 'round';
            ctx.lineJoin = 'round';
            ctx.shadowColor = glowColor;
            ctx.shadowBlur = 12;

            // Vẽ 4 góc ngoặc công nghệ (Corner brackets)
            const cornerLen = Math.min(w, h) * 0.22;

            // Góc trên-trái
            ctx.beginPath();
            ctx.moveTo(x, y + cornerLen);
            ctx.lineTo(x, y);
            ctx.lineTo(x + cornerLen, y);
            ctx.stroke();

            // Góc trên-phải
            ctx.beginPath();
            ctx.moveTo(x + w - cornerLen, y);
            ctx.lineTo(x + w, y);
            ctx.lineTo(x + w, y + cornerLen);
            ctx.stroke();

            // Góc dưới-trái
            ctx.beginPath();
            ctx.moveTo(x, y + h - cornerLen);
            ctx.lineTo(x, y + h);
            ctx.lineTo(x + cornerLen, y + h);
            ctx.stroke();

            // Góc dưới-phải
            ctx.beginPath();
            ctx.moveTo(x + w - cornerLen, y + h);
            ctx.lineTo(x + w, y + h);
            ctx.lineTo(x + w, y + h - cornerLen);
            ctx.stroke();

            // Tia laser quét dọc lên xuống bên trong khung mặt (khi đang quét bình thường)
            if (!isSpoofWarningActive && Date.now() >= scanPauseUntil) {
                const laserProgress = (Math.sin(Date.now() / 200) + 1) / 2; // Dao động 0 .. 1
                const laserY = y + 10 + laserProgress * (h - 20);
                const laserGrad = ctx.createLinearGradient(x, laserY, x + w, laserY);
                laserGrad.addColorStop(0, 'rgba(56, 189, 248, 0)');
                laserGrad.addColorStop(0.5, 'rgba(56, 189, 248, 0.85)');
                laserGrad.addColorStop(1, 'rgba(56, 189, 248, 0)');
                ctx.strokeStyle = laserGrad;
                ctx.lineWidth = 2.0;
                ctx.beginPath();
                ctx.moveTo(x + 4, laserY);
                ctx.lineTo(x + w - 4, laserY);
                ctx.stroke();
            }

            // Tag hiển thị trạng thái phía trên khung (Chữ xuôi chiều tự nhiên, chuẩn font tiếng Việt)
            const tagY = Math.max(26, y - 8);
            ctx.font = '700 11.5px "Be Vietnam Pro", Inter, sans-serif';
            const textMetrics = ctx.measureText(statusText);
            const tagW = textMetrics.width + 18;

            ctx.fillStyle = 'rgba(10, 19, 36, 0.92)';
            ctx.shadowBlur = 8;
            ctx.fillRect(x, tagY - 20, tagW, 22);
            ctx.strokeStyle = mainColor;
            ctx.lineWidth = 1.2;
            ctx.strokeRect(x, tagY - 20, tagW, 22);

            ctx.fillStyle = mainColor;
            ctx.fillText(statusText, x + 9, tagY - 5);

            ctx.restore();
        }

        function clearFaceTrackerCanvas() {
            const canvas = document.getElementById('face-tracker-canvas');
            if (!canvas) return;
            const ctx = canvas.getContext('2d');
            ctx.clearRect(0, 0, canvas.width, canvas.height);
        }

        let isRefreshingInProgress = false;
        let lastKioskRefreshTimestamp = 0;

        async function handleRefreshButton() {
            if (isRefreshingInProgress) return;
            isRefreshingInProgress = true;
            getAudioContext();

            // Đánh dấu thời điểm làm mới hệ thống (chặn hiển thị bất kỳ sự kiện nào xảy ra trước mốc này)
            lastKioskRefreshTimestamp = Date.now() / 1000;

            // Kiểm tra trạng thái toàn màn hình hiện tại
            const doc = document;
            const docEl = doc.documentElement;
            const wasFullscreen = !!(doc.fullscreenElement || doc.webkitFullscreenElement || doc.mozFullScreenElement || doc.msFullscreenElement);

            const btn = document.getElementById('btn-refresh');
            const label = document.getElementById('btn-refresh-label');
            if (btn) {
                btn.disabled = true;
                btn.classList.add('is-refreshing');
            }
            if (label) label.textContent = 'Đang làm mới...';

            setNotification('scanning', 'Đang làm mới toàn bộ hệ thống...');

            try {
                // 1. Đóng ngay popup nhận diện nếu đang hiển thị
                if (typeof closeRecognitionPopup === 'function') {
                    closeRecognitionPopup();
                }

                // 2. XÓA NGAY LẬP TỨC THẺ THÔNG TIN CÁ NHÂN VỀ TRẠNG THÁI TRỐNG
                resetPersonalCard();

                // 3. Gửi lệnh lên máy chủ xóa sạch active_card và sự kiện cũ
                fetch('/api/dismiss_card', { method: 'POST' }).catch(() => {});

                // 4. Tắt sạch luồng camera hiện tại và giải phóng driver phần cứng webcam
                stopContinuousScanner('Đang khởi động lại camera...');

                // 5. Tránh re-trigger lại ngay chính người vừa đứng trước camera (delay 1.8s & chống spam)
                scanPauseUntil = Date.now() + 1800;
                lastSuccessTime = Date.now();
                lastServerCallTime = 0;
                isFirstPoll = false;

                // 6. Nếu đang ở chế độ toàn màn hình, đảm bảo giữ vững toàn màn hình (không bị thoát)
                if (wasFullscreen) {
                    const isStillFs = !!(doc.fullscreenElement || doc.webkitFullscreenElement || doc.mozFullScreenElement || doc.msFullscreenElement);
                    if (!isStillFs) {
                        const req = docEl.requestFullscreen || docEl.webkitRequestFullscreen || docEl.mozRequestFullScreen || docEl.msRequestFullscreen;
                        if (req) {
                            try {
                                const p = req.call(docEl);
                                if (p && p.catch) p.catch(() => {});
                            } catch (e) {}
                        }
                    }
                }

                // 7. Đồng bộ lịch sử bên phải từ máy chủ, đồng thời cập nhật lastHandledEventId để bỏ qua mọi sự kiện trước đó
                try {
                    const res = await fetch('/api/kiosk_status', { cache: 'no-store' });
                    if (res.ok) {
                        const data = await res.json();
                        const sEventId = Number(data.last_event_id || 0);
                        const cEvt = data.latest_event || data.active_card;
                        const cEvtId = Number((cEvt && cEvt.event_id) || 0);
                        lastHandledEventId = Math.max(lastHandledEventId || 0, sEventId, cEvtId);

                        if (data.logs && data.logs.length > 0) {
                            const counterEl = document.getElementById('counter-total');
                            if (counterEl) counterEl.textContent = data.logs.length;
                            renderLiveHistory(data.logs);
                        }
                    }
                } catch (e) {}

                // Đảm bảo ô thông tin cá nhân duy trì trạng thái trống sạch sẽ
                resetPersonalCard();

                // 8. Đợi 250ms cho camera stream giải phóng triệt để trên phần cứng
                await new Promise(resolve => setTimeout(resolve, 250));

                // 9. Tự động bật lại camera và kích hoạt vòng lặp quét nhận diện
                await startContinuousScanner();

                if (label) label.textContent = 'Đã làm mới ✔';

                setTimeout(() => {
                    if (label) label.textContent = 'Làm Mới Hệ Thống';
                    if (btn) {
                        btn.disabled = false;
                        btn.classList.remove('is-refreshing');
                    }
                    isRefreshingInProgress = false;
                    updateFullscreenUI();
                    resetPersonalCard();
                }, 600);

            } catch (err) {
                console.error('[Refresh] Lỗi khi làm mới hệ thống:', err);
                resetPersonalCard();
                if (label) label.textContent = 'Làm Mới Hệ Thống';
                if (btn) {
                    btn.disabled = false;
                    btn.classList.remove('is-refreshing');
                }
                isRefreshingInProgress = false;
                updateFullscreenUI();
            }
        }

        function handleCaptureButton() {
            handleRefreshButton();
        }

        async function startContinuousScanner() {
            setNotification('scanning', 'Đang kết nối camera tablet & tải MediaPipe...');

            try {
                // Khởi tạo MediaPipe nếu chưa sẵn sàng
                if (!mpFaceDetector) {
                    await initMediaPipeFaceDetector();
                }

                const constraints = {
                    video: { facingMode: 'user', width: { ideal: 640 }, height: { ideal: 480 } },
                    audio: false
                };
                webcamStream = await navigator.mediaDevices.getUserMedia(constraints);
                const videoEl = document.getElementById('tablet-webcam-video');
                videoEl.srcObject = webcamStream;
                await videoEl.play();
                applyMirrorMode();

                // Ẩn overlay idle, hiện webcam và canvas tracker
                const idleOverlay = document.getElementById('camera-idle-overlay');
                if (idleOverlay) idleOverlay.style.display = 'none';
                const faceOverlay = document.getElementById('face-detection-overlay');
                if (faceOverlay) faceOverlay.style.display = 'none';
                
                const trackerCanvas = document.getElementById('face-tracker-canvas');
                if (trackerCanvas) {
                    trackerCanvas.style.display = 'block';
                    trackerCanvas.width  = videoEl.videoWidth  || 640;
                    trackerCanvas.height = videoEl.videoHeight || 480;
                }

                videoEl.style.display = 'block';

                isWebcamActive = true;
                cameraMode = 'scanning';
                isScanLoopRunning = true;
                isFrameProcessing = false;
                scanPauseUntil = 0;
                lastFaceDetectedTime = Date.now();
                lastServerCallTime = 0;
                isSpoofWarningActive = false;

                // Hiện badge đang quét
                const badge = document.getElementById('camera-scanning-badge');
                if (badge) {
                    badge.innerHTML = '<span class="pulse-dot"></span>Đang đợi khuôn mặt...';
                    badge.classList.add('visible');
                }

                setNotification('scanning', 'Camera đang mở. Nhìn thẳng vào camera để nhận diện.');

                // Bắt đầu vòng lặp quét tự động liên tục
                runScanLoop();

            } catch (err) {
                console.error('Không thể mở camera:', err);
                setNotification('error', 'Không thể mở camera. Vui lòng cấp quyền truy cập camera hoặc bấm "Làm Mới Hệ Thống".');
            }
        }

        async function runScanLoop() {
            if (!isWebcamActive || !isScanLoopRunning) return;

            // NẾU POPUP ĐANG MỞ HOẶC ĐANG TRONG THỜI GIAN TẠM DỪNG: DỪNG TOÀN BỘ QUÉT VÀ VẼ TRACKER
            if (isPopupShowing || Date.now() < scanPauseUntil) {
                clearFaceTrackerCanvas();
                scanLoopTimer = setTimeout(runScanLoop, 150);
                return;
            }

            const video = document.getElementById('tablet-webcam-video');
            if (!video || video.readyState < 2) {
                scanLoopTimer = setTimeout(runScanLoop, 100);
                return;
            }

            // Đồng bộ kích thước canvas vẽ tracker với video thực tế
            const trackerCanvas = document.getElementById('face-tracker-canvas');
            if (trackerCanvas && video.videoWidth && trackerCanvas.width !== video.videoWidth) {
                trackerCanvas.width  = video.videoWidth;
                trackerCanvas.height = video.videoHeight;
            }

            // 1. PHÁT HIỆN KHUÔN MẶT TRÊN CLIENT BẰNG MEDIAPIPE TASKS VISION (CLIENT-SIDE TRIGGER)
            let detections = [];
            if (mpFaceDetector) {
                try {
                    const mpRes = mpFaceDetector.detectForVideo(video, performance.now());
                    detections = mpRes?.detections || [];
                } catch (e) {
                    console.error('[MediaPipe] Lỗi detectForVideo:', e);
                }
            }

            // 2. VẼ OVERLAY BÁM DÍNH KHUÔN MẶT
            drawFaceTrackingOverlay(detections);

            // 3. NẾU KHÔNG CÓ KHUÔN MẶT
            if (detections.length === 0) {
                // Cập nhật trạng thái badge: Đang đợi người (duy trì quét liên tục 24/7 cho Kiosk)
                const badge = document.getElementById('camera-scanning-badge');
                if (badge && !isSpoofWarningActive) {
                    badge.innerHTML = '<span class="pulse-dot"></span>Đang đợi khuôn mặt...';
                }

                // TUYỆT ĐỐI KHÔNG GỬI REQUEST VỀ SERVER KHI KHÔNG CÓ NGƯỜI -> 0 KB/s, SERVER 0% TẢI!
                scanLoopTimer = setTimeout(runScanLoop, 80);
                return;
            }

            // 4. CÓ KHUÔN MẶT -> CẬP NHẬT THỜI GIAN NHÌN THẤY
            lastFaceDetectedTime = Date.now();

            // Kiểm tra kích thước khuôn mặt: khuôn mặt phải chiếm tối thiểu 10% chiều rộng khung hình
            const maxFaceWidth = Math.max(...detections.map(d => d.boundingBox.width));
            const faceRatio = maxFaceWidth / (video.videoWidth || 640);

            if (faceRatio < 0.10) {
                const badge = document.getElementById('camera-scanning-badge');
                if (badge && !isSpoofWarningActive) {
                    badge.innerHTML = '<span class="pulse-dot" style="background:#f59e0b;"></span>Vui lòng lại gần camera hơn';
                }
                scanLoopTimer = setTimeout(runScanLoop, 120);
                return;
            }

            // Khuôn mặt chuẩn và đủ gần camera!
            const badge = document.getElementById('camera-scanning-badge');
            if (badge && !isSpoofWarningActive) {
                badge.innerHTML = '<span class="pulse-dot" style="background:#22c55e;"></span>Phát hiện khuôn mặt • Đang đối chiếu...';
            }

            // 5. TRIGGER GỬI FRAME LÊN SERVER ĐỐI CHIẾU VECTOR & PASSIVE LIVENESS (MINIFASNET)
            const now = Date.now();
            if (!isFrameProcessing && (now - lastServerCallTime >= SCAN_INTERVAL_MS)) {
                isFrameProcessing = true;
                lastServerCallTime = now;
                try {
                    await captureAndProcessFrame();
                } catch (err) {
                    console.error('Lỗi khi gửi khung hình lên server:', err);
                } finally {
                    isFrameProcessing = false;
                }
            }

            if (isScanLoopRunning && isWebcamActive) {
                scanLoopTimer = setTimeout(runScanLoop, 60);
            }
        }

        async function captureAndProcessFrame() {
            if (isPopupShowing || Date.now() < scanPauseUntil) return;

            const video = document.getElementById('tablet-webcam-video');
            if (!video || video.readyState < 2) return;

            const canvas = document.getElementById('webcam-capture-canvas');
            if (!canvas) return;
            const ctx = canvas.getContext('2d');
            canvas.width  = video.videoWidth  || 640;
            canvas.height = video.videoHeight || 480;
            ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
            const imageBase64 = canvas.toDataURL('image/jpeg', 0.85);

            const res = await fetch('/api/kiosk/scan_face', {
                method:  'POST',
                headers: { 'Content-Type': 'application/json' },
                body:    JSON.stringify({ image: imageBase64 })
            });

            if (!res.ok) return;
            const result = await res.json();

            // Nếu server trả về kết quả đang trong thời gian cooldown
            if (result.cooldown) {
                return;
            }

            // 1. TRƯỜNG HỢP: NHẬN DIỆN THÀNH CÔNG!
            if (result.recognized && result.card) {
                lastFaceDetectedTime = Date.now();
                const card = result.card;
                const empId = String(card.emp_id || card.profile?.ID || card.code || '').trim();
                const now = Date.now();

                // Chống spam: cùng người vừa quét xong trong 8 giây thì không re-trigger
                if (empId && empId === lastSuccessEmpId && (now - lastSuccessTime < RECOG_COOLDOWN_MS)) {
                    return;
                }

                // Ghi nhận thành công người mới!
                lastSuccessEmpId = empId;
                lastSuccessTime = now;
                lastHandledCardId = card.card_id;
                const evtId = Number(result.event_id || card.event_id || 0);
                if (evtId > 0) {
                    lastHandledEventId = evtId;
                }
                scanPauseUntil = Date.now() + SUCCESS_PAUSE_MS; // Tạm dừng 2.5s: 1.5s popup + 1.0s chuyển tiếp
                clearFaceTrackerCanvas();

                // 1. Ảnh camera thực tế: Lấy trực tiếp từ khung hình webcam vừa bắt được (ĐÚNG 100% THỜI ĐIỂM CHỤP)
                card.snapshotUrl = imageBase64;
                if (result.card && result.card.snapshot_url) {
                    card.serverSnapshotUrl = result.card.snapshot_url;
                }

                // 2. Ảnh hồ sơ đăng ký chính chủ (Avatar HRMS)
                card.avatarUrl = (result.card && result.card.avatar) 
                    ? result.card.avatar 
                    : (empId ? `/api_faces/${empId}.jpg?v=${Date.now()}` : '');

                // Kích hoạt đồng bộ điểm danh tức thì
                triggerSyncAttendance(card, true);
                return;
            }

            // 2. TRƯỜNG HỢP: PHÁT HIỆN GIẢ MẠO (PASSIVE LIVENESS / MINIFASNET SPOOFING)
            if (result.reason === 'spoof') {
                isSpoofWarningActive = true;
                scanPauseUntil = Date.now() + 2000; // Tạm dừng quét 2 giây để hiển thị cảnh báo
                
                const spoofMsg = result.message || 'Cảnh báo: Phát hiện ảnh giả mạo! Vui lòng người thật đứng trực tiếp trước camera.';
                setNotification('error', spoofMsg);
                playErrorSound();
                speakWarning('Cảnh báo! Phát hiện hình ảnh giả mạo.');

                const camWrap = document.getElementById('camera-square-wrap');
                if (camWrap) {
                    camWrap.classList.remove('success-glow');
                    camWrap.classList.add('spoof-glow');
                }

                if (spoofWarningTimer) clearTimeout(spoofWarningTimer);
                spoofWarningTimer = setTimeout(() => {
                    isSpoofWarningActive = false;
                    if (camWrap) camWrap.classList.remove('spoof-glow');
                    if (isScanLoopRunning && isWebcamActive) {
                        setNotification('scanning', 'Camera đang mở. Nhìn thẳng vào khung hình để nhận diện.');
                    }
                }, 2000);

                return;
            }

            // 3. TRƯỜNG HỢP: CHƯA ĐẠT GÓC NHÌN HOẶC CHƯA NHẬN DIỆN
            if (result.reason === 'no_face') {
                // Đang chờ người, giữ giao diện êm dịu không giật lắc
            } else if (result.reason === 'pose') {
                setNotification('scanning', result.message || 'Vui lòng nhìn thẳng vào camera.');
            } else if (result.reason === 'need_motion') {
                const badge = document.getElementById('camera-scanning-badge');
                if (badge && !isSpoofWarningActive) {
                    badge.innerHTML = '<span class="pulse-dot" style="background:#06b6d4;"></span>' + (result.message || 'Vui lòng chớp mắt hoặc cử động nhẹ...');
                }
                setNotification('scanning', result.message || 'Vui lòng nhìn camera • Chớp mắt hoặc cử động nhẹ...');
            } else if (result.reason === 'unknown') {
                setNotification('scanning', 'Khuôn mặt chưa được đăng ký trong hệ thống.');
            } else if (result.reason === 'low_confidence') {
                setNotification('scanning', 'Độ khớp thấp. Vui lòng giữ thẳng khuôn mặt và đứng đủ sáng.');
            }
        }

        function stopContinuousScanner(msg) {
            isScanLoopRunning = false;
            isFrameProcessing = false;
            isSpoofWarningActive = false;
            if (spoofWarningTimer) {
                clearTimeout(spoofWarningTimer);
                spoofWarningTimer = null;
            }
            if (scanLoopTimer) {
                clearTimeout(scanLoopTimer);
                scanLoopTimer = null;
            }

            if (webcamStream) {
                webcamStream.getTracks().forEach(t => t.stop());
                webcamStream = null;
            }

            const videoEl = document.getElementById('tablet-webcam-video');
            if (videoEl) {
                videoEl.srcObject = null;
                videoEl.style.display = 'none';
            }

            const trackerCanvas = document.getElementById('face-tracker-canvas');
            if (trackerCanvas) {
                trackerCanvas.style.display = 'none';
                clearFaceTrackerCanvas();
            }

            // Hiện lại overlay idle
            document.getElementById('camera-idle-overlay').style.display = 'flex';
            document.getElementById('face-detection-overlay').style.display = 'none';
            const badge = document.getElementById('camera-scanning-badge');
            if (badge) badge.classList.remove('visible');

            const camWrap = document.getElementById('camera-square-wrap');
            if (camWrap) {
                camWrap.classList.remove('success-glow');
                camWrap.classList.remove('spoof-glow');
            }

            isWebcamActive = false;
            cameraMode = 'idle';

            setNotification('idle', msg || 'Nhấn "Làm Mới Hệ Thống" để khởi động lại camera.');
        }

        // =====================================================================
        // 4. HÀM THÔNG BÁO KẾT QUẢ
        // =====================================================================
        function setNotification(type, message) {
            const box = document.getElementById('result-notification-box');
            const txt = document.getElementById('result-notification-text');

            box.className = 'result-notification-box anim-in';

            const icons = {
                idle:     '<circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>',
                success:  '<polyline points="20 6 9 17 4 12"/>',
                error:    '<circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>',
                scanning: '<circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15 15 0 0 1 4 10 15 15 0 0 1-4 10 15 15 0 0 1-4-10 15 15 0 0 1 4-10z"/>'
            };

            setTimeout(() => {
                box.classList.add(`notif-${type}`);
                box.querySelector('svg').innerHTML = icons[type] || icons.idle;
                if (txt) txt.textContent = message;
            }, 10);
        }

        // =====================================================================
        // 5. CẬP NHẬT & TỰ ĐỘNG LÀM MỚI THẺ THÔNG TIN CÁ NHÂN (SAU 10S TRỐNG)
        // =====================================================================
        let personalCardAutoClearTimer = null;
        const PERSONAL_CARD_TIMEOUT_MS = 10000; // 10 giây tự động xóa thông tin về trạng thái trống

        function resetPersonalCard() {
            if (personalCardAutoClearTimer) {
                clearTimeout(personalCardAutoClearTimer);
                personalCardAutoClearTimer = null;
            }

            // Tên nhân viên
            const nameEl = document.getElementById('user-fullname');
            if (nameEl) nameEl.textContent = '---';

            // Mã số nhân viên
            const empEl = document.getElementById('user-empid');
            if (empEl) {
                empEl.textContent = 'Chưa có dữ liệu';
                empEl.classList.add('empty-placeholder');
            }

            // Vị trí / Chức danh
            const posEl = document.getElementById('user-position');
            if (posEl) {
                posEl.textContent = 'Chưa có dữ liệu';
                posEl.classList.add('empty-placeholder');
            }

            // Vị trí làm việc
            const wpEl = document.getElementById('user-workplace');
            if (wpEl) {
                wpEl.textContent = 'Chưa có dữ liệu';
                wpEl.classList.add('empty-placeholder');
            }

            // Phòng ban
            const deptEl = document.getElementById('user-dept');
            if (deptEl) {
                deptEl.textContent = 'Chưa có dữ liệu';
                deptEl.classList.add('empty-placeholder');
            }

            // Ảnh đại diện cá nhân: Hủy triệt để event handler, ẩn ảnh, reset về icon placeholder
            const avatarImg = document.getElementById('user-avatar');
            if (avatarImg) {
                avatarImg.onload = null;
                avatarImg.onerror = null;
                avatarImg.style.display = 'none';
                avatarImg.classList.remove('has-photo');
                avatarImg.removeAttribute('src');
                avatarImg.src = '';
            }

            // Số lượt chấm công hôm nay
            const badgeEl = document.getElementById('today-count-badge');
            if (badgeEl) badgeEl.textContent = '0 lượt';

            // Danh sách chấm công hôm nay
            const container = document.getElementById('today-logs-container');
            if (container) {
                container.innerHTML = '<div class="today-log-empty" id="today-log-empty">Chưa có lượt chấm công hôm nay</div>';
            }
        }

        function updatePersonalCard(card) {
            if (!card) return;
            const profile   = card.profile || {};
            const empCode   = String(profile.EmployeeCode || card.code || '').trim();
            const empId     = String(card.emp_id || profile.ID || '').trim();
            const cached    = (typeof HRMS_CACHE !== 'undefined') ? (HRMS_CACHE[empCode.toUpperCase()] || HRMS_CACHE[empId] || {}) : {};

            const fullName  = profile.FullName || card.name || cached.name || empCode || '';
            const role      = profile.Name_Role || profile.Role || profile.role || card.role || cached.role || '';
            const workplace = card.workplace || profile.WorkPlaceName || profile.workplace || cached.workplace || '';
            const dept      = profile.Dept_Name || card.dept || cached.dept || '';
            const timeStr   = card.time ? (card.time.split(' ')[1] || card.time) : new Date().toLocaleTimeString('vi-VN');

            // Tên nhân viên
            const nameEl = document.getElementById('user-fullname');
            if (nameEl) nameEl.textContent = fullName ? fullName.toUpperCase() : '---';

            // Mã số nhân viên
            const empEl = document.getElementById('user-empid');
            if (empEl) {
                empEl.textContent = empCode || 'Chưa có dữ liệu';
                empEl.classList.toggle('empty-placeholder', !empCode);
            }

            // Vị trí / Chức danh (Chức danh chuyên môn từ HRMS)
            const posEl = document.getElementById('user-position');
            if (posEl) {
                posEl.textContent = role || 'Chưa có dữ liệu';
                posEl.classList.toggle('empty-placeholder', !role);
            }

            // Vị trí làm việc (Nơi làm việc / Depot / Chi nhánh từ HRMS)
            const wpEl = document.getElementById('user-workplace');
            if (wpEl) {
                wpEl.textContent = workplace || 'Chưa có dữ liệu';
                wpEl.classList.toggle('empty-placeholder', !workplace);
            }

            // Phòng ban
            const deptEl = document.getElementById('user-dept');
            if (deptEl) {
                deptEl.textContent = dept ? dept.toUpperCase() : 'Chưa có dữ liệu';
                deptEl.classList.toggle('empty-placeholder', !dept);
            }

            // Ảnh đại diện cá nhân: ƯU TIÊN SỐ 1 LÀ ẢNH SNAPSHOT TẠI THỜI ĐIỂM CHẤM CÔNG
            const avatarImg = document.getElementById('user-avatar');
            const livePhoto = card.snapshotUrl || (card.snapshot ? `/snapshots/${card.snapshot}?v=${Date.now()}` : '');
            const profileAvatar = card.avatarUrl || card.avatar || (empId ? `/api_faces/${empId}.jpg?v=${Date.now()}` : '');
            const targetUrl = livePhoto || profileAvatar;

            if (avatarImg) {
                // Xóa handler và ảnh cũ ngay lập tức để không bị lưu ảnh người trước đó
                avatarImg.onload = null;
                avatarImg.onerror = null;
                avatarImg.style.display = 'none';
                avatarImg.classList.remove('has-photo');
                avatarImg.removeAttribute('src');
                avatarImg.src = '';

                if (targetUrl) {
                    avatarImg.onload = function() {
                        this.style.display = 'block';
                        this.classList.add('has-photo');
                    };
                    avatarImg.onerror = function() {
                        if (profileAvatar && this.src !== profileAvatar) {
                            this.src = profileAvatar;
                        } else {
                            this.onload = null;
                            this.onerror = null;
                            this.style.display = 'none';
                            this.classList.remove('has-photo');
                            this.removeAttribute('src');
                            this.src = '';
                        }
                    };
                    avatarImg.src = targetUrl;
                }
            }

            // Hiển thị toàn bộ lượt chấm công trong ngày của nhân viên kèm ảnh ghi nhận thời điểm chấm
            renderEmployeeTodayLogs(empCode, card.today_logs, livePhoto);

            // Đặt lịch tự động làm mới thông tin về trạng thái trống sau 10 giây nếu không có ai chấm tiếp
            if (personalCardAutoClearTimer) {
                clearTimeout(personalCardAutoClearTimer);
                personalCardAutoClearTimer = null;
            }
            personalCardAutoClearTimer = setTimeout(() => {
                resetPersonalCard();
            }, PERSONAL_CARD_TIMEOUT_MS);
        }

        async function renderEmployeeTodayLogs(empCode, preloadedLogs, latestSnapshotUrl) {
            const container = document.getElementById('today-logs-container');
            const badgeEl = document.getElementById('today-count-badge');
            if (!container) return;

            let logs = preloadedLogs;
            // Nếu chưa có dữ liệu preloaded hoặc rỗng, gọi API để lấy nhật ký mới nhất
            if (!logs || !Array.isArray(logs) || logs.length === 0) {
                if (empCode) {
                    try {
                        const resp = await fetch(`/api/kiosk/employee_today_logs/${encodeURIComponent(empCode)}`);
                        if (resp.ok) {
                            const data = await resp.json();
                            if (data && Array.isArray(data.logs) && data.logs.length > 0) {
                                logs = data.logs;
                            }
                        }
                    } catch (err) {
                        console.error('Lỗi tải lịch sử chấm công hôm nay:', err);
                    }
                }
            }

            if (!logs || !Array.isArray(logs) || logs.length === 0) {
                container.innerHTML = '<div class="today-log-empty" id="today-log-empty">Chưa có lượt chấm công hôm nay</div>';
                if (badgeEl) {
                    badgeEl.textContent = '0 lượt';
                    badgeEl.classList.remove('has-logs');
                }
                return;
            }

            if (badgeEl) {
                badgeEl.textContent = `${logs.length} lượt`;
                badgeEl.classList.add('has-logs');
            }

            const totalCount = logs.length;
            let html = '';
            logs.forEach((item, idx) => {
                const isLatest = (idx === 0);
                const seqNum = totalCount - idx;
                const timeStr = item.time_short || (item.time ? (item.time.split(' ')[1] || item.time) : '--:--');
                const camName = item.cam || 'TABLET KIOSK';
                const typeStr = item.type || 'Điểm danh';

                // Xác định ảnh snapshot khoảnh khắc ghi nhận tại thời điểm chấm
                let snapUrl = '';
                if (isLatest && latestSnapshotUrl) {
                    snapUrl = latestSnapshotUrl;
                } else if (item.snapshot) {
                    snapUrl = `/snapshots/${item.snapshot}?v=${Date.now()}`;
                } else if (empCode) {
                    snapUrl = `/api_faces/${empCode}.jpg`;
                }

                let badgeClass = 'today-log-badge-check';
                if (typeStr.includes('Vào')) badgeClass = 'today-log-badge-in';
                else if (typeStr.includes('Tan') || typeStr.includes('Ra')) badgeClass = 'today-log-badge-out';

                const imgHtml = snapUrl
                    ? `<img class="today-log-thumb" src="${snapUrl}" alt="Ảnh thời điểm chấm" onerror="this.style.display='none'; if(this.nextElementSibling) this.nextElementSibling.style.display='flex';">
                       <div class="today-log-thumb-fallback" style="display:none;"><svg viewBox="0 0 24 24"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg></div>`
                    : `<div class="today-log-thumb-fallback"><svg viewBox="0 0 24 24"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg></div>`;

                html += `
                    <div class="today-log-row ${isLatest ? 'is-latest' : ''}">
                        <div class="today-log-left">
                            <div class="today-log-thumb-wrap" title="Ảnh ghi nhận tại thời điểm chấm">
                                ${imgHtml}
                            </div>
                            <span class="today-log-idx">#${seqNum}</span>
                            <div class="today-log-meta">
                                <span class="today-log-time">${timeStr}</span>
                                <span class="today-log-cam" title="${camName}">${camName}</span>
                            </div>
                        </div>
                        <div class="today-log-right">
                            ${isLatest ? '<span class="today-log-tag-latest">Mới nhất</span>' : ''}
                            <span class="today-log-badge ${badgeClass}">${typeStr}</span>
                        </div>
                    </div>
                `;
            });

            container.innerHTML = html;
        }

        // =====================================================================
        // 6. THÊM MỤC VÀO LỊCH SỬ
        // =====================================================================
        function addHistoryEntry(card) {
            const container = document.getElementById('history-scroll-feed');
            if (!container) return;

            // Xóa placeholder "chưa có dữ liệu"
            const placeholder = container.querySelector('div[style]');
            if (placeholder) placeholder.remove();

            const profile   = card.profile || {};
            const code      = String(profile.EmployeeCode || card.code || '').trim();
            const empId     = String(card.emp_id || profile.ID || '').trim();
            const cached    = (typeof HRMS_CACHE !== 'undefined') ? (HRMS_CACHE[code.toUpperCase()] || HRMS_CACHE[empId] || {}) : {};
            const name      = profile.FullName || card.name || cached.name || code || 'Nhân viên';
            const dept      = profile.Dept_Name || card.dept || cached.dept || '';
            const role      = profile.Name_Role || card.role || cached.role || '';
            const snapshotUrl = card.snapshotUrl || (card.snapshot ? `/snapshots/${card.snapshot}` : '');
            const profileUrl  = card.avatar || (empId ? `/api_faces/${empId}.jpg` : '');
            const avatarUrl   = snapshotUrl || profileUrl;
            const timeStr   = card.time ? (card.time.split(' ')[1] || card.time) : new Date().toLocaleTimeString('vi-VN', {hour:'2-digit',minute:'2-digit'});

            const subText   = [code, role || dept].filter(Boolean).join(' · ');

            const avatarHtml = avatarUrl
                ? `<img src="${avatarUrl}" alt="" onerror="if (this.src.indexOf('/api_faces/') === -1 && '${profileUrl}') { this.src='${profileUrl}'; } else { this.parentElement.innerHTML='<svg viewBox=\\'0 0 24 24\\' fill=\\'none\\' stroke=\\'%2364748b\\' stroke-width=\\'2\\'><path d=\\'M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2\\'/><circle cx=\\'12\\' cy=\\'7\\' r=\\'4\\'/></svg>'; }">`
                : `<svg viewBox="0 0 24 24" fill="none" stroke="#64748b" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>`;

            const camUpper  = (card.cam_name || card.cam || '').toUpperCase();
            const typeStr   = (card.mode === 'in' || camUpper.includes('VÀO')) ? 'Vào ca' : ((card.mode === 'out' || camUpper.includes('TAN') || camUpper.includes('RA')) ? 'Tan ca' : 'Điểm danh');
            const badgeClass = typeStr === 'Vào ca' ? 'hist-badge-in' : (typeStr === 'Tan ca' ? 'hist-badge-out' : 'hist-badge-check');

            const item = document.createElement('div');
            item.className = 'history-card-item anim-in';
            item.innerHTML = `
                <div class="hist-avatar-circle">${avatarHtml}</div>
                <div class="hist-user-meta">
                    <span class="hist-user-name" title="${name}">${name}</span>
                    <span class="hist-user-sub" title="${subText}">${subText}</span>
                </div>
                <span class="hist-badge ${badgeClass}">${typeStr}</span>
                <span class="hist-time-stamp">${timeStr}</span>`;

            container.insertBefore(item, container.firstChild);

            // Cập nhật đếm
            const counter = document.getElementById('counter-total');
            if (counter) counter.textContent = parseInt(counter.textContent || '0') + 1;
        }

        // =====================================================================
        // 7. ĐIỀU PHỐI ĐỒNG BỘ ĐIỂM DANH & POPUP 1 Ô AVATAR DUY NHẤT
        // =====================================================================
        let isPopupShowing = false;
        let popupAutoCloseTimer = null;
        let popupCountdownInterval = null;
        const POPUP_DURATION_MS = 1000; // 1.0 giây hiển thị chuẩn hoàn tất và chuyển chụp mới

        function triggerSyncAttendance(card, isDirectScanner) {
            if (!card) return;

            const profile = card.profile || {};
            const empCode = String(profile.EmployeeCode || card.code || '').trim();
            const empId   = String(card.emp_id || profile.ID || '').trim();
            const cached  = (typeof HRMS_CACHE !== 'undefined') ? (HRMS_CACHE[empCode.toUpperCase()] || HRMS_CACHE[empId] || {}) : {};
            const fullName = profile.FullName || card.name || cached.name || empCode || 'bạn';

            // 1. Cập nhật thẻ thông tin cá nhân bên trái
            updatePersonalCard(card);

            // 2. Hiển thị popup modal 1 ô avatar duy nhất giữa màn hình
            showRecognitionPopup(card);

            // 3. Thêm mục vào lịch sử bên phải
            addHistoryEntry(card);

            if (isDirectScanner) {
                // Trình duyệt trực tiếp thực hiện quét camera
                setNotification('success', `Chấm công thành công! Xin chào ${fullName}.`);
                playSuccessSound();
                speakGreeting(fullName);

                // Hiệu ứng viền xanh lá phát sáng camera
                const camWrap = document.getElementById('camera-square-wrap');
                if (camWrap) {
                    camWrap.classList.add('success-glow');
                    setTimeout(() => { if (camWrap) camWrap.classList.remove('success-glow'); }, SUCCESS_PAUSE_MS);
                }

                // Sau 1.5s sẵn sàng quét người tiếp theo
                setTimeout(() => {
                    if (isScanLoopRunning && isWebcamActive) {
                        setNotification('scanning', 'Sẵn sàng đón người tiếp theo... Vui lòng nhìn thẳng vào camera.');
                    }
                }, SUCCESS_PAUSE_MS);
            } else {
                // Trình duyệt khác đồng bộ sự kiện qua server polling
                if (cameraMode === 'scanning') {
                    // Nếu camera trên trình duyệt này cũng đang mở quét, tạm hoãn quét 1.5s để xem popup đồng bộ
                    scanPauseUntil = Date.now() + SUCCESS_PAUSE_MS;
                    const camWrap = document.getElementById('camera-square-wrap');
                    if (camWrap) {
                        camWrap.classList.add('success-glow');
                        setTimeout(() => { if (camWrap) camWrap.classList.remove('success-glow'); }, SUCCESS_PAUSE_MS);
                    }
                } else {
                    setNotification('success', `Xác nhận điểm danh: ${fullName} (${empCode || empId})`);
                }
                playSuccessSound();
            }
        }

        function showRecognitionPopup(card) {
            if (!card) return;

            const profile   = card.profile || {};
            const empCode   = String(profile.EmployeeCode || card.code || '').trim();
            const empId     = String(card.emp_id || profile.ID || '').trim();

            const modal  = document.getElementById('recognition-popup-modal');
            const codeEl = document.getElementById('popup-empid');

            // Chống giật & lặp/reset popup: Nếu popup đang hiển thị cho cùng nhân viên này thì giữ nguyên thanh countdown và ảnh
            const curCode = codeEl ? codeEl.textContent.trim() : '';
            if (isPopupShowing && modal && modal.classList.contains('active')) {
                if (curCode && (curCode === empCode || curCode === empId)) {
                    return;
                }
            }

            isPopupShowing = true;
            const cached    = (typeof HRMS_CACHE !== 'undefined') ? (HRMS_CACHE[empCode.toUpperCase()] || HRMS_CACHE[empId] || {}) : {};

            const fullName  = profile.FullName || card.name || cached.name || empCode || 'NHÂN VIÊN';
            const role      = profile.Name_Role || profile.Role || profile.role || card.role || cached.role || 'Nhân viên';
            const dept      = profile.Dept_Name || card.dept || cached.dept || '---';
            const timeStr   = card.time ? (card.time.split(' ')[1] || card.time) : new Date().toLocaleTimeString('vi-VN');

            let confDisplay = 'Chuẩn xác';
            if (card.confidence) {
                const cVal = typeof card.confidence === 'number' ? card.confidence.toFixed(1) : parseFloat(card.confidence);
                confDisplay = `${cVal}% (Đạt)`;
            }

            // Gán dữ liệu vào popup
            const nameEl = document.getElementById('popup-fullname');
            const roleEl = document.getElementById('popup-role');
            const deptEl = document.getElementById('popup-dept');
            const timeEl = document.getElementById('popup-time');
            const confEl = document.getElementById('popup-confidence');
            const barEl  = document.getElementById('popup-countdown-bar');
            const numEl  = document.getElementById('popup-countdown-num');

            if (nameEl) nameEl.textContent = fullName.toUpperCase();
            if (codeEl) codeEl.textContent = empCode || empId || '---';
            if (roleEl) roleEl.textContent = role;
            if (deptEl) deptEl.textContent = dept;
            if (timeEl) timeEl.textContent = timeStr;
            if (confEl) confEl.textContent = confDisplay;

            // 1 ô Avatar duy nhất trong Popup (gọn gàng, chuẩn doanh nghiệp, không emoji)
            const avatarImg = document.getElementById('popup-avatar-img');
            if (avatarImg) {
                // Xóa và ẩn ảnh trước đó ngay lập tức để không bị hiện nhầm ảnh người cũ
                avatarImg.style.display = 'none';
                avatarImg.classList.remove('has-photo');
                avatarImg.src = '';

                // Xác định nguồn ảnh: ƯU TIÊN SỐ 1 LÀ ẢNH SNAPSHOT KHOẢNH KHẮC VỪA CHỤP TẠI THỜI ĐIỂM CHẤM
                const livePhotoUrl     = card.snapshotUrl || (card.snapshot ? `/snapshots/${card.snapshot}?v=${Date.now()}` : '');
                const profileAvatarUrl = card.avatarUrl || card.avatar || (empId ? `/api_faces/${empId}.jpg?v=${Date.now()}` : '');
                const targetUrl        = livePhotoUrl || profileAvatarUrl;

                if (targetUrl) {
                    avatarImg.onload = function() {
                        this.style.display = 'block';
                        this.classList.add('has-photo');
                    };
                    avatarImg.onerror = function() {
                        if (profileAvatarUrl && this.src !== profileAvatarUrl) {
                            this.src = profileAvatarUrl;
                        } else {
                            this.style.display = 'none';
                            this.classList.remove('has-photo');
                        }
                    };
                    avatarImg.src = targetUrl;
                }
            }

            // Reset timer cũ nếu có
            if (popupAutoCloseTimer) clearTimeout(popupAutoCloseTimer);
            if (popupCountdownInterval) clearInterval(popupCountdownInterval);

            // Bật animation thanh progress bar
            if (barEl) {
                barEl.style.transition = 'none';
                barEl.style.width = '100%';
                void barEl.offsetWidth; // Force reflow
                barEl.style.transition = `width ${POPUP_DURATION_MS}ms linear`;
                barEl.style.width = '0%';
            }

            if (numEl) numEl.textContent = '1.0s';

            // Kích hoạt hiển thị modal
            if (modal) modal.classList.add('active');

            // Tự động đóng sau 1.5 giây
            popupAutoCloseTimer = setTimeout(() => {
                closeRecognitionPopup();
            }, POPUP_DURATION_MS);
        }

        function closeRecognitionPopup() {
            const modal = document.getElementById('recognition-popup-modal');
            if (modal) modal.classList.remove('active');
            isPopupShowing = false;
            if (popupAutoCloseTimer) {
                clearTimeout(popupAutoCloseTimer);
                popupAutoCloseTimer = null;
            }
            if (popupCountdownInterval) {
                clearInterval(popupCountdownInterval);
                popupCountdownInterval = null;
            }
            const avatarImg = document.getElementById('popup-avatar-img');
            if (avatarImg) {
                avatarImg.style.display = 'none';
                avatarImg.classList.remove('has-photo');
                avatarImg.src = '';
            }
        }

        function handlePopupBackdropClick(event) {
            if (event.target && event.target.id === 'recognition-popup-modal') {
                closeRecognitionPopup();
            }
        }

        function handlePopupAvatarError(img) {
            if (img) {
                img.classList.remove('has-photo');
                img.src = '';
            }
        }

        // =====================================================================
        // 8. POLLING SERVER & ĐỒNG BỘ ĐA TRÌNH DUYỆT (SEQUENCE EVENT ID)
        // =====================================================================
        let isFirstPoll = true;
        async function pollStatus() {
            try {
                const res = await fetch('/api/kiosk_status', { cache: 'no-store' });
                if (!res.ok) return;
                const data = await res.json();

                const serverLastEventId = Number(data.last_event_id || 0);
                const evt = data.latest_event || data.active_card;
                const currentEvtId = Number((evt && evt.event_id) || 0);

                if (isFirstPoll) {
                    isFirstPoll = false;
                    // Bỏ qua sự kiện cũ xảy ra trước khi mở trang này để không hiện popup người cũ
                    lastHandledEventId = Math.max(serverLastEventId, currentEvtId);
                    if (evt) {
                        const evtAgeSec = (Date.now() / 1000) - Number(evt.timestamp || 0);
                        const evtTs = Number(evt.timestamp || 0);
                        // Chỉ hiển thị nếu sự kiện xảy ra trong vòng 10 giây qua VÀ sau thời điểm làm mới
                        if (evtAgeSec >= 0 && evtAgeSec < 10 && evtTs > lastKioskRefreshTimestamp) {
                            updatePersonalCard(evt);
                            if (personalCardAutoClearTimer) clearTimeout(personalCardAutoClearTimer);
                            const remainingMs = Math.max(1000, (10 - evtAgeSec) * 1000);
                            personalCardAutoClearTimer = setTimeout(() => {
                                resetPersonalCard();
                            }, remainingMs);
                        } else {
                            resetPersonalCard();
                        }
                    } else {
                        resetPersonalCard();
                    }
                } else {
                    // Nếu server khởi động lại (ID bị reset về nhỏ hơn)
                    if (serverLastEventId > 0 && serverLastEventId < (lastHandledEventId - 5)) {
                        lastHandledEventId = serverLastEventId;
                    }

                    // Đồng bộ điểm danh: Chỉ hiển thị khi có sự kiện MỚI (event_id tăng dần VÀ sau thời điểm làm mới)
                    const evtTs = Number((evt && evt.timestamp) || 0);
                    if (evt && currentEvtId > lastHandledEventId && evtTs > lastKioskRefreshTimestamp) {
                        lastHandledEventId = currentEvtId;
                        triggerSyncAttendance(evt, false);
                    }
                }

                if (data.logs && data.logs.length > 0) {
                    const counterEl = document.getElementById('counter-total');
                    if (counterEl) counterEl.textContent = data.logs.length;
                    renderLiveHistory(data.logs);
                }
            } catch (err) {}
        }
        setInterval(pollStatus, 400);

        function renderLiveHistory(logs) {
            if (!logs || logs.length === 0) return;
            const container = document.getElementById('history-scroll-feed');

            const html = logs.slice(0, 25).map(item => {
                const timeOnly = (item.time || '').split(' ')[1] || item.time || '';
                const code     = String(item.code || '').trim();
                const cached   = (typeof HRMS_CACHE !== 'undefined') ? (HRMS_CACHE[code.toUpperCase()] || {}) : {};
                const name     = item.name || cached.name || 'Nhân viên';
                const dept     = item.dept || cached.dept || '';
                const role     = item.role || cached.role || '';
                const subText  = [code, role || dept].filter(Boolean).join(' · ');
                const snapshotUrl = item.snapshot ? `/snapshots/${item.snapshot}` : '';
                const profileUrl  = item.avatar ? `/api_faces/${item.avatar}` : '';
                const avatarUrl   = snapshotUrl || profileUrl;

                const camUpper    = (item.cam || '').toUpperCase();
                let typeStr       = 'Điểm danh';
                let badgeClass    = 'hist-badge-check';
                if (camUpper.includes('VÀO')) {
                    typeStr = 'Vào ca';
                    badgeClass = 'hist-badge-in';
                } else if (camUpper.includes('TAN') || camUpper.includes('RA')) {
                    typeStr = 'Tan ca';
                    badgeClass = 'hist-badge-out';
                }

                const avatarHtml = avatarUrl
                    ? `<img src="${avatarUrl}" alt="" onerror="if (this.src.indexOf('/api_faces/') === -1 && '${profileUrl}') { this.src='${profileUrl}'; } else { this.style.display='none'; }">`
                    : `<svg viewBox="0 0 24 24" fill="none" stroke="#64748b" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>`;

                return `
                    <div class="history-card-item">
                        <div class="hist-avatar-circle">${avatarHtml}</div>
                        <div class="hist-user-meta">
                            <span class="hist-user-name" title="${name}">${name}</span>
                            <span class="hist-user-sub" title="${subText}">${subText}</span>
                        </div>
                        <span class="hist-badge ${badgeClass}">${typeStr}</span>
                        <span class="hist-time-stamp">${timeOnly}</span>
                    </div>`;
            }).join('');

            container.innerHTML = html;
        }

        // =====================================================================
        // 8. TIỆN ÍCH
        // =====================================================================
        function toggleFullScreen() {
            getAudioContext();
            const doc = document;
            const docEl = doc.documentElement;
            const isFs = !!(doc.fullscreenElement || doc.webkitFullscreenElement || doc.mozFullScreenElement || doc.msFullscreenElement);

            if (!isFs) {
                const req = docEl.requestFullscreen || docEl.webkitRequestFullscreen || docEl.mozRequestFullScreen || docEl.msRequestFullscreen;
                if (req) {
                    try {
                        const p = req.call(docEl);
                        if (p && p.catch) p.catch(() => {});
                    } catch(e) {}
                }
            } else {
                const exit = doc.exitFullscreen || doc.webkitExitFullscreen || doc.mozCancelFullScreen || doc.msExitFullscreen;
                if (exit) {
                    try {
                        const p = exit.call(doc);
                        if (p && p.catch) p.catch(() => {});
                    } catch(e) {}
                }
            }
            setTimeout(updateFullscreenUI, 100);
        }

        function updateFullscreenUI() {
            const doc = document;
            const isFs = !!(doc.fullscreenElement || doc.webkitFullscreenElement || doc.mozFullScreenElement || doc.msFullscreenElement);
            const btn = document.getElementById('btn-fullscreen');
            if (btn) {
                btn.classList.toggle('active', isFs);
                btn.title = isFs ? 'Thu nhỏ màn hình (Esc)' : 'Toàn màn hình';
                const svg = btn.querySelector('svg');
                if (svg) {
                    svg.innerHTML = isFs 
                        ? '<path d="M8 3v3a2 2 0 0 1-2 2H3m18 0h-3a2 2 0 0 1-2-2V3m0 18v-3a2 2 0 0 1 2-2h3M3 16h3a2 2 0 0 1 2 2v3"/>'
                        : '<path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/>';
                }
            }
        }

        ['fullscreenchange', 'webkitfullscreenchange', 'mozfullscreenchange', 'MSFullscreenChange'].forEach(evt => {
            document.addEventListener(evt, updateFullscreenUI);
        });
    </script>
</body>
</html>
"""

_hrms_cache_json = json.dumps(_get_hrms_cache_dict(), ensure_ascii=False)
HTML_KIOSK_TEMPLATE = _RAW_HTML_KIOSK_TEMPLATE.replace('/* __HRMS_CACHE_DATA__ */ {}', _hrms_cache_json)

