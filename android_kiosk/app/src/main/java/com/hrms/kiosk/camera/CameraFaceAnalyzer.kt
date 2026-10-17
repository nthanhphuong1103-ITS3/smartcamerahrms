package com.hrms.kiosk.camera

import android.graphics.Bitmap
import android.graphics.Matrix
import android.graphics.RectF
import android.util.Base64
import androidx.annotation.OptIn
import androidx.camera.core.ExperimentalGetImage
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.face.FaceDetection
import com.google.mlkit.vision.face.FaceDetectorOptions
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import java.io.ByteArrayOutputStream
import kotlin.math.abs

/**
 * Bộ phân tích khung hình CameraX + Google ML Kit Face Detection Offline
 * Chuẩn 1:1 theo kiosk_portal.py:
 * - Vòng lặp bám khuôn mặt mượt mà 60 FPS
 * - Ngưỡng kích thước khuôn mặt: faceRatio >= 0.10 (tối thiểu 10% chiều rộng khung hình)
 * - Nếu ở quá xa: báo "Vui lòng lại gần camera hơn", không gửi server (0 KB/s tải mạng)
 * - Tần số gửi server chuẩn 250ms/lần (SCAN_INTERVAL_MS = 250) với khóa non-blocking
 * - Ảnh chụp nén JPEG chuẩn 85%, độ phân giải tối đa 640x480
 */
class CameraFaceAnalyzer(
    private val onFaceDetected: (bounds: RectF?, state: FaceTrackerOverlayView.TrackerState, message: String?, srcW: Int, srcH: Int) -> Unit,
    private val onCaptureReady: (base64Image: String) -> Unit
) : ImageAnalysis.Analyzer {

    // Scope coroutine nền xử lý nén ảnh phi khóa
    private val processingScope = CoroutineScope(Dispatchers.Default)

    // Cấu hình ML Kit: bắt mặt từ xa (10% khung hình), chạy chế độ nhanh Fast Mode
    private val detector = FaceDetection.getClient(
        FaceDetectorOptions.Builder()
            .setPerformanceMode(FaceDetectorOptions.PERFORMANCE_MODE_FAST)
            .setLandmarkMode(FaceDetectorOptions.LANDMARK_MODE_NONE)
            .setClassificationMode(FaceDetectorOptions.CLASSIFICATION_MODE_NONE)
            .setMinFaceSize(0.10f)
            .build()
    )

    @Volatile
    var isEnabled: Boolean = true

    @Volatile
    var isRequestInFlight: Boolean = false

    @Volatile
    private var requestStartTime: Long = 0L

    @Volatile
    private var pauseUntilTime: Long = 0L

    // Nhịp gửi API: 250ms/lần (chuẩn hệt bản Web kiosk_portal.py)
    private var lastSendTime: Long = 0L
    private val minSendIntervalMs: Long = 250L

    fun pauseScanning(durationMs: Long) {
        pauseUntilTime = System.currentTimeMillis() + durationMs
        isRequestInFlight = false
        requestStartTime = 0L
    }

    fun resumeScanning() {
        pauseUntilTime = 0L
        isRequestInFlight = false
        requestStartTime = 0L
    }

    fun startRequest() {
        isRequestInFlight = true
        requestStartTime = System.currentTimeMillis()
    }

    fun finishRequest() {
        isRequestInFlight = false
        requestStartTime = 0L
    }

    @OptIn(ExperimentalGetImage::class)
    override fun analyze(imageProxy: ImageProxy) {
        val now = System.currentTimeMillis()

        // Tự phục hồi: Nếu request mạng bị timeout quá 2.5 giây, tự reset để tiếp tục quét
        if (isRequestInFlight && (now - requestStartTime > 2500L)) {
            isRequestInFlight = false
            requestStartTime = 0L
        }

        // Nếu đang tạm dừng quét (sau khi chấm công xong 2.5s) hoặc đang đợi API phản hồi
        if (!isEnabled || isRequestInFlight || now < pauseUntilTime) {
            imageProxy.close()
            return
        }

        val mediaImage = imageProxy.image
        if (mediaImage == null) {
            imageProxy.close()
            return
        }

        val rotationDegrees = imageProxy.imageInfo.rotationDegrees
        val inputImage = InputImage.fromMediaImage(mediaImage, rotationDegrees)

        val rotatedWidth = if (rotationDegrees == 90 || rotationDegrees == 270) imageProxy.height else imageProxy.width
        val rotatedHeight = if (rotationDegrees == 90 || rotationDegrees == 270) imageProxy.width else imageProxy.height

        detector.process(inputImage)
            .addOnSuccessListener { faces ->
                // 1. Không phát hiện khuôn mặt: Xóa tracker, không gửi request (0 KB/s, 0% CPU server)
                if (faces.isEmpty()) {
                    onFaceDetected(null, FaceTrackerOverlayView.TrackerState.IDLE, null, rotatedWidth, rotatedHeight)
                    return@addOnSuccessListener
                }

                // 2. Tìm khuôn mặt gần camera nhất (diện tích lớn nhất như bản Web)
                val primaryFace = faces.maxByOrNull { it.boundingBox.width() * it.boundingBox.height() } ?: return@addOnSuccessListener
                val bounds = RectF(primaryFace.boundingBox)

                // 3. Kiểm tra kích thước khuôn mặt: phải chiếm tối thiểu 10% chiều rộng khung hình (faceRatio >= 0.10)
                val faceW = primaryFace.boundingBox.width()
                val faceRatio = faceW.toFloat() / rotatedWidth.toFloat()

                if (faceRatio < 0.10f) {
                    onFaceDetected(
                        bounds,
                        FaceTrackerOverlayView.TrackerState.TOO_FAR,
                        "VUI LÒNG LẠI GẦN CAMERA HƠN",
                        rotatedWidth,
                        rotatedHeight
                    )
                    return@addOnSuccessListener
                }

                // 4. Kiểm tra góc quay mặt (Yaw <= 28°, Pitch <= 25°)
                val yaw = primaryFace.headEulerAngleY
                val pitch = primaryFace.headEulerAngleX
                val isFacingCamera = abs(yaw) <= 28f && abs(pitch) <= 25f

                if (!isFacingCamera) {
                    onFaceDetected(
                        bounds,
                        FaceTrackerOverlayView.TrackerState.DETECTING,
                        "VUI LÒNG NHÌN THẲNG",
                        rotatedWidth,
                        rotatedHeight
                    )
                    return@addOnSuccessListener
                }

                // 5. Khuôn mặt chuẩn và đủ gần camera! Hiện khung Neon Cyan và dòng chữ công nghệ
                onFaceDetected(
                    bounds,
                    FaceTrackerOverlayView.TrackerState.DETECTING,
                    "AI TRACKING • NHÌN THẲNG",
                    rotatedWidth,
                    rotatedHeight
                )

                // 6. Trigger gửi frame lên server theo nhịp 250ms (SCAN_INTERVAL_MS)
                if (now - lastSendTime >= minSendIntervalMs && !isRequestInFlight) {
                    lastSendTime = now
                    startRequest()

                    try {
                        val rawBitmap = imageProxy.toBitmap()

                        processingScope.launch {
                            try {
                                val rotatedBitmap = if (rotationDegrees != 0) {
                                    val matrix = Matrix().apply { postRotate(rotationDegrees.toFloat()) }
                                    Bitmap.createBitmap(rawBitmap, 0, 0, rawBitmap.width, rawBitmap.height, matrix, true)
                                } else {
                                    rawBitmap
                                }

                                // Giới hạn kích thước tối đa 640px chuẩn vàng Kiosk Web
                                val finalBitmap = if (rotatedBitmap.width > 640 || rotatedBitmap.height > 640) {
                                    val scale = 640f / maxOf(rotatedBitmap.width, rotatedBitmap.height)
                                    val targetW = (rotatedBitmap.width * scale).toInt()
                                    val targetH = (rotatedBitmap.height * scale).toInt()
                                    Bitmap.createScaledBitmap(rotatedBitmap, targetW, targetH, true)
                                } else {
                                    rotatedBitmap
                                }

                                // Nén JPEG chất lượng 85% (chuẩn 1:1 với toDataURL('image/jpeg', 0.85) trên Web)
                                val outputStream = ByteArrayOutputStream()
                                finalBitmap.compress(Bitmap.CompressFormat.JPEG, 85, outputStream)
                                val bytes = outputStream.toByteArray()
                                val base64Image = Base64.encodeToString(bytes, Base64.NO_WRAP)

                                onCaptureReady(base64Image)
                            } catch (e: Exception) {
                                e.printStackTrace()
                                finishRequest()
                            }
                        }
                    } catch (e: Exception) {
                        e.printStackTrace()
                        finishRequest()
                    }
                }
            }
            .addOnFailureListener {
                // Bỏ qua nếu có lỗi cục bộ
            }
            .addOnCompleteListener {
                // Luôn giải phóng ImageProxy để Camera duy trì 60 FPS mượt mà
                imageProxy.close()
            }
    }
}
