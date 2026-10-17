package com.hrms.kiosk.camera

import android.content.Context
import android.util.Size
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.core.content.ContextCompat
import androidx.lifecycle.LifecycleOwner
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors

/**
 * Trợ lý khởi tạo và quản lý vòng đời CameraX
 */
@Suppress("DEPRECATION")
class CameraHelper(
    private val context: Context,
    private val lifecycleOwner: LifecycleOwner,
    private val previewView: PreviewView,
    private val analyzer: CameraFaceAnalyzer
) {

    private var cameraExecutor: ExecutorService = Executors.newSingleThreadExecutor()
    private var cameraProvider: ProcessCameraProvider? = null
    var isFrontCamera: Boolean = true
        private set

    fun startCamera(useFrontCamera: Boolean = true, onReady: (() -> Unit)? = null) {
        this.isFrontCamera = useFrontCamera
        val cameraProviderFuture = ProcessCameraProvider.getInstance(context)

        cameraProviderFuture.addListener({
            cameraProvider = cameraProviderFuture.get()

            val windowManager = context.getSystemService(Context.WINDOW_SERVICE) as? android.view.WindowManager
            @Suppress("DEPRECATION")
            val rotation = previewView.display?.rotation
                ?: windowManager?.defaultDisplay?.rotation
                ?: android.view.Surface.ROTATION_0
            previewView.scaleType = PreviewView.ScaleType.FILL_CENTER

            // 1. Luồng xem trực tiếp (Preview hiển thị sắc nét)
            val preview = Preview.Builder()
                .setTargetResolution(Size(960, 540))
                .setTargetRotation(rotation)
                .build()
                .also {
                    it.setSurfaceProvider(previewView.surfaceProvider)
                }

            // 2. Luồng phân tích AI cục bộ (ImageAnalysis chuẩn vàng 640x480 siêu tốc độ)
            val imageAnalysis = ImageAnalysis.Builder()
                .setTargetResolution(Size(640, 480))
                .setTargetRotation(rotation)
                .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                .setOutputImageFormat(ImageAnalysis.OUTPUT_IMAGE_FORMAT_YUV_420_888)
                .build()
                .also {
                    it.setAnalyzer(cameraExecutor, analyzer)
                }

            // 3. Chọn hướng camera
            val cameraSelector = if (useFrontCamera) {
                CameraSelector.DEFAULT_FRONT_CAMERA
            } else {
                CameraSelector.DEFAULT_BACK_CAMERA
            }

            try {
                cameraProvider?.unbindAll()
                cameraProvider?.bindToLifecycle(
                    lifecycleOwner,
                    cameraSelector,
                    preview,
                    imageAnalysis
                )
                onReady?.invoke()
            } catch (exc: Exception) {
                exc.printStackTrace()
            }

        }, ContextCompat.getMainExecutor(context))
    }

    fun stopCamera() {
        try {
            cameraProvider?.unbindAll()
        } catch (e: Exception) {
            e.printStackTrace()
        }
    }

    fun shutdown() {
        stopCamera()
        if (!cameraExecutor.isShutdown) {
            cameraExecutor.shutdown()
        }
    }
}
