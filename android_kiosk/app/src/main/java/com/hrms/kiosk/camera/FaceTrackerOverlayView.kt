package com.hrms.kiosk.camera

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.LinearGradient
import android.graphics.Paint
import android.graphics.Path
import android.graphics.RectF
import android.graphics.Shader
import android.util.AttributeSet
import android.view.View

/**
 * Custom View vẽ khung theo dõi khuôn mặt chuẩn 1:1 Kiosk Web (kiosk_portal.py):
 * - 4 góc ngoặc công nghệ (Corner Brackets 22%)
 * - Tia laser quét dọc dao động hình sin mượt mà 60 FPS
 * - Thẻ tag trạng thái nổi (Floating Status Pill Tag)
 * - Tự động nội suy vị trí LERP bám dính siêu êm, không rung giật
 */
class FaceTrackerOverlayView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
    defStyleAttr: Int = 0
) : View(context, attrs, defStyleAttr) {

    enum class TrackerState {
        IDLE,           // Đang chờ người
        DETECTING,      // Đang phát hiện mặt, quét bình thường (Cyan Neon)
        SUCCESS,        // Nhận diện thành công (Xanh lục Emerald)
        SPOOF,          // Cảnh báo giả mạo màn hình (Đỏ rực)
        NEED_MOTION,    // Cần cử động hoặc lại gần (Vàng cam)
        TOO_FAR         // Ở quá xa camera (Vàng cam)
    }

    private var state: TrackerState = TrackerState.IDLE
    private var targetBounds: RectF? = null
    private var smoothedBounds: RectF? = null
    private var statusMessage: String? = null
    private var isFrontCamera: Boolean = true

    // Kích thước khung hình phân tích từ CameraX
    private var previewWidth: Int = 1
    private var previewHeight: Int = 1

    private val density: Float = resources.displayMetrics.density

    // Paint vẽ 4 góc ngoặc công nghệ
    private val cornerPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = 3.5f * density
        strokeCap = Paint.Cap.ROUND
        strokeJoin = Paint.Join.ROUND
    }

    // Paint vẽ nền phát sáng mờ phía sau góc
    private val glowPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.FILL
    }

    // Paint vẽ tia laser quét dọc
    private val laserPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = 2.2f * density
        strokeCap = Paint.Cap.ROUND
    }

    // Paint vẽ nền thẻ tag trạng thái nổi
    private val tagBgPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.FILL
        color = Color.parseColor("#EB0A1324") // rgba(10, 19, 36, 0.92) chuẩn web
    }

    // Paint vẽ viền thẻ tag trạng thái nổi
    private val tagBorderPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = 1.2f * density
    }

    // Paint vẽ chữ trạng thái
    private val tagTextPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        textSize = 12f * density
        isFakeBoldText = true
        textAlign = Paint.Align.LEFT
    }

    private val cornerPath = Path()

    fun updateFace(
        bounds: RectF?,
        currentState: TrackerState,
        message: String? = null,
        srcWidth: Int = previewWidth,
        srcHeight: Int = previewHeight,
        frontCam: Boolean = true
    ) {
        this.targetBounds = bounds
        this.state = currentState
        this.statusMessage = message
        this.previewWidth = if (srcWidth > 0) srcWidth else 1
        this.previewHeight = if (srcHeight > 0) srcHeight else 1
        this.isFrontCamera = frontCam

        // Nếu mới thấy mặt lần đầu, khởi tạo ngay tọa độ smoothed
        if (bounds != null && smoothedBounds == null) {
            smoothedBounds = RectF(bounds)
        }

        postInvalidateOnAnimation()
    }

    fun clear() {
        this.targetBounds = null
        this.smoothedBounds = null
        this.statusMessage = null
        this.state = TrackerState.IDLE
        postInvalidate()
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)

        val target = targetBounds
        if (target == null) {
            smoothedBounds = null
            return
        }

        if (width <= 0 || height <= 0) return

        // 1. Tính toán tỉ lệ scale từ CameraX sang kích thước View màn hình
        val scaleX = width.toFloat() / previewWidth.toFloat()
        val scaleY = height.toFloat() / previewHeight.toFloat()
        val scale = maxOf(scaleX, scaleY)

        val offsetX = (width - previewWidth * scale) / 2f
        val offsetY = (height - previewHeight * scale) / 2f

        // Map tọa độ thô
        var rawLeft = target.left * scale + offsetX
        var rawRight = target.right * scale + offsetX
        val rawTop = target.top * scale + offsetY
        val rawBottom = target.bottom * scale + offsetY

        // Nếu là camera trước: lật gương (Mirror mode)
        if (isFrontCamera) {
            val flippedLeft = width - rawRight
            val flippedRight = width - rawLeft
            rawLeft = flippedLeft
            rawRight = flippedRight
        }

        // Mở rộng viền padding bao quanh mặt (padX = 12%, padY = 14% chuẩn bản Web)
        val faceW = rawRight - rawLeft
        val faceH = rawBottom - rawTop
        val padX = faceW * 0.12f
        val padY = faceH * 0.14f

        val targetLeft = maxOf(0f, rawLeft - padX)
        val targetTop = maxOf(0f, rawTop - padY)
        val targetRight = minOf(width.toFloat(), rawRight + padX)
        val targetBottom = minOf(height.toFloat(), rawBottom + padY)

        // 2. Nội suy vị trí mượt mà (LERP Factor 0.38) giúp khung mặt bám dính cực êm
        val current = smoothedBounds ?: RectF(targetLeft, targetTop, targetRight, targetBottom)
        val lerpFactor = 0.38f
        val curLeft = current.left + (targetLeft - current.left) * lerpFactor
        val curTop = current.top + (targetTop - current.top) * lerpFactor
        val curRight = current.right + (targetRight - current.right) * lerpFactor
        val curBottom = current.bottom + (targetBottom - current.bottom) * lerpFactor
        current.set(curLeft, curTop, curRight, curBottom)
        smoothedBounds = current

        val drawRect = current
        val w = drawRect.width()
        val h = drawRect.height()

        // 3. Màu sắc chuẩn xác từ hệ màu Dark Theme của kiosk_portal.py
        val (mainColor, glowColor, defaultStatusText) = when (state) {
            TrackerState.IDLE, TrackerState.DETECTING -> Triple(
                Color.parseColor("#38BDF8"), // Cyan Neon
                Color.parseColor("#3338BDF8"),
                "AI TRACKING • NHÌN THẲNG"
            )
            TrackerState.SUCCESS -> Triple(
                Color.parseColor("#22C55E"), // Emerald Green
                Color.parseColor("#4422C55E"),
                "✓ ĐÃ XÁC THỰC THÀNH CÔNG"
            )
            TrackerState.SPOOF -> Triple(
                Color.parseColor("#EF4444"), // Red Warning
                Color.parseColor("#44EF4444"),
                "⚠️ CẢNH BÁO: ẢNH GIẢ MẠO"
            )
            TrackerState.NEED_MOTION -> Triple(
                Color.parseColor("#F59E0B"), // Amber
                Color.parseColor("#33F59E0B"),
                "VUI LÒNG CHỚP MẮT HOẶC CỬ ĐỘNG NHẸ"
            )
            TrackerState.TOO_FAR -> Triple(
                Color.parseColor("#F59E0B"),
                Color.parseColor("#33F59E0B"),
                "VUI LÒNG LẠI GẦN CAMERA HƠN"
            )
        }

        cornerPaint.color = mainColor
        glowPaint.color = glowColor
        tagBorderPaint.color = mainColor
        tagTextPaint.color = mainColor

        // 4. Vẽ nền sáng mờ bên trong khung mặt (Subtle ambient glow)
        canvas.drawRoundRect(drawRect, 16f * density, 16f * density, glowPaint)

        // 5. Vẽ 4 góc ngoặc công nghệ (Corner Brackets 22% chuẩn bản Web)
        val cornerLen = minOf(w, h) * 0.22f

        // Góc trên - trái
        cornerPath.reset()
        cornerPath.moveTo(drawRect.left, drawRect.top + cornerLen)
        cornerPath.lineTo(drawRect.left, drawRect.top)
        cornerPath.lineTo(drawRect.left + cornerLen, drawRect.top)
        canvas.drawPath(cornerPath, cornerPaint)

        // Góc trên - phải
        cornerPath.reset()
        cornerPath.moveTo(drawRect.right - cornerLen, drawRect.top)
        cornerPath.lineTo(drawRect.right, drawRect.top)
        cornerPath.lineTo(drawRect.right, drawRect.top + cornerLen)
        canvas.drawPath(cornerPath, cornerPaint)

        // Góc dưới - phải
        cornerPath.reset()
        cornerPath.moveTo(drawRect.right, drawRect.bottom - cornerLen)
        cornerPath.lineTo(drawRect.right, drawRect.bottom)
        cornerPath.lineTo(drawRect.right - cornerLen, drawRect.bottom)
        canvas.drawPath(cornerPath, cornerPaint)

        // Góc dưới - trái
        cornerPath.reset()
        cornerPath.moveTo(drawRect.left + cornerLen, drawRect.bottom)
        cornerPath.lineTo(drawRect.left, drawRect.bottom)
        cornerPath.lineTo(drawRect.left, drawRect.bottom - cornerLen)
        canvas.drawPath(cornerPath, cornerPaint)

        // 6. Vẽ tia Laser quét dọc dao động hình sin liên tục (khi đang quét bình thường)
        if (state == TrackerState.DETECTING) {
            val now = System.currentTimeMillis()
            val laserProgress = ((Math.sin(now / 200.0) + 1.0) / 2.0).toFloat() // Dao động 0 .. 1
            val laserY = drawRect.top + 10f * density + laserProgress * (h - 20f * density)

            val laserGradient = LinearGradient(
                drawRect.left, laserY,
                drawRect.right, laserY,
                intArrayOf(
                    Color.TRANSPARENT,
                    mainColor,
                    Color.TRANSPARENT
                ),
                floatArrayOf(0.0f, 0.5f, 1.0f),
                Shader.TileMode.CLAMP
            )
            laserPaint.shader = laserGradient
            canvas.drawLine(drawRect.left + 4f * density, laserY, drawRect.right - 4f * density, laserY, laserPaint)
        }

        // 7. Thẻ trạng thái nổi trên khung mặt (Floating Status Pill Tag)
        val statusText = statusMessage ?: defaultStatusText
        if (statusText.isNotEmpty()) {
            val textWidth = tagTextPaint.measureText(statusText)
            val paddingH = 10f * density
            val tagHeight = 24f * density
            val tagWidth = textWidth + paddingH * 2

            // Đặt tag ngay mép trên của khung mặt
            val tagY = maxOf(tagHeight + 6f * density, drawRect.top - 8f * density)
            val tagTop = tagY - tagHeight
            val tagLeft = maxOf(8f * density, minOf(drawRect.left, width - tagWidth - 8f * density))
            val tagRight = tagLeft + tagWidth

            val tagRect = RectF(tagLeft, tagTop, tagRight, tagY)

            // Vẽ nền đen mờ bo góc
            canvas.drawRoundRect(tagRect, 6f * density, 6f * density, tagBgPaint)
            // Vẽ viền trạng thái
            canvas.drawRoundRect(tagRect, 6f * density, 6f * density, tagBorderPaint)

            // Vẽ chữ căn giữa trong tag
            val fontMetrics = tagTextPaint.fontMetrics
            val baseline = tagTop + (tagHeight - fontMetrics.bottom + fontMetrics.top) / 2f - fontMetrics.top
            canvas.drawText(statusText, tagLeft + paddingH, baseline, tagTextPaint)
        }

        // Tiếp tục vẽ ở frame kế tiếp để tia laser và LERP chuyển động mượt 60 FPS
        postInvalidateOnAnimation()
    }
}
