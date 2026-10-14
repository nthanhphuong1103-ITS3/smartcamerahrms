# Smart Camera HRMS - Hệ Thống Điểm Danh Khuôn Mặt AI

Hệ thống điểm danh nhận diện khuôn mặt tự động tích hợp đa luồng Camera IP RTSP và Tablet Kiosk, đồng bộ CSDL với Smart HRMS.

## 🚀 Tính Năng Chính
- **AI Nhận diện khuôn mặt thời gian thực**: Sử dụng mô hình YuNet (Face Detection) và SFace (Face Recognition) qua OpenCV DNN.
- **Hỗ trợ đa luồng RTSP**: Kết nối trực tiếp nhiều camera IP (Dual-stream 720p/1080p).
- **Phân tách 2 luồng độc lập**:
  - Luồng Camera IP RTSP $\rightarrow$ Hiển thị thông tin lên Web Dashboard Admin.
  - Luồng Camera Tablet/Webcam $\rightarrow$ Popup chào mừng và câu chúc thông minh trên Kiosk.
- **Tablet Kiosk Interactive**: Tự động phát âm thanh, chúc mừng theo buổi sáng/chiều/tối bằng giọng đọc tiếng Việt chuẩn.
- **Tự động đồng bộ CSDL & Ảnh**: Định kỳ đồng bộ danh sách nhân viên và ảnh thẻ từ Smart HRMS API.
- **REST API Endpoint**: Cung cấp API xuất lịch sử điểm danh cho hệ thống ngoài (Smart HRMS, ERP...).

## 🛠️ Cài Đặt & Khởi Chạy
```bash
# Cài đặt thư viện phụ thuộc
pip install flask opencv-python numpy requests

# Khởi chạy hệ thống chính
python web_face_attendance.py
```
- Dashboard Admin: `http://localhost:5055`
- Kiosk Portal: `http://localhost:5055/kiosk`
