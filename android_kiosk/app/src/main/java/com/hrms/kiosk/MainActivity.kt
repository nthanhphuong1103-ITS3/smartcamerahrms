package com.hrms.kiosk

import android.Manifest
import android.animation.ValueAnimator
import android.content.pm.PackageManager
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.View
import android.view.WindowManager
import android.view.animation.LinearInterpolator
import android.widget.Button
import android.widget.EditText
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import com.bumptech.glide.Glide
import com.bumptech.glide.load.engine.DiskCacheStrategy
import com.hrms.kiosk.audio.AudioHelper
import com.hrms.kiosk.camera.CameraFaceAnalyzer
import com.hrms.kiosk.camera.CameraHelper
import com.hrms.kiosk.camera.FaceTrackerOverlayView
import com.hrms.kiosk.data.api.ApiClient
import com.hrms.kiosk.data.model.AttendanceLogItem
import com.hrms.kiosk.data.model.KioskCard
import com.hrms.kiosk.data.model.ScanFaceRequest
import com.hrms.kiosk.databinding.ActivityMainBinding
import com.hrms.kiosk.ui.AttendanceLogAdapter
import com.hrms.kiosk.ui.EmployeeTodayLogAdapter
import com.hrms.kiosk.util.AppPreferences
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private lateinit var prefs: AppPreferences
    private lateinit var audioHelper: AudioHelper
    private lateinit var cameraHelper: CameraHelper
    private lateinit var faceAnalyzer: CameraFaceAnalyzer
    private lateinit var logAdapter: AttendanceLogAdapter
    private lateinit var employeeTodayLogAdapter: EmployeeTodayLogAdapter

    // Bộ hẹn giờ tự động xóa thông tin cá nhân về trạng thái trống (10 giây sau khi nhận diện, chuẩn Web Kiosk)
    private val personalCardClearHandler = Handler(Looper.getMainLooper())
    private var personalCardClearRunnable: Runnable? = null
    private val PERSONAL_CARD_TIMEOUT_MS = 10000L

    // Đồng hồ thời gian thực
    private val clockHandler = Handler(Looper.getMainLooper())
    private val clockRunnable = object : Runnable {
        override fun run() {
            updateDigitalClock()
            clockHandler.postDelayed(this, 1000)
        }
    }

    // Đếm số lần nhấn logo để mở màn hình Quản trị (Admin)
    private var logoTapCount = 0
    private var lastLogoTapTime = 0L

    // Popup kết quả
    private var popupAnimator: ValueAnimator? = null
    private val popupHideHandler = Handler(Looper.getMainLooper())

    private val cameraPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { isGranted ->
        if (isGranted) {
            initCamera()
        } else {
            Toast.makeText(this, "Cần cấp quyền Camera để nhận diện khuôn mặt!", Toast.LENGTH_LONG).show()
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        prefs = AppPreferences(this)
        audioHelper = AudioHelper(this)

        setupKioskWindow()
        setupRecyclerView()
        setupUI()
        setupShiftModeButtons()

        // Khởi tạo Camera & ML Kit Analyzer
        setupCameraAnalyzer()

        // Bắt đầu đồng hồ
        clockHandler.post(clockRunnable)

        // Kiểm tra quyền và mở Camera
        checkPermissionsAndStartCamera()

        // Tải lịch sử chấm công từ Server
        fetchKioskStatus()
    }

    /**
     * 1. Cấu hình Kiosk Mode: Giữ màn hình luôn sáng và ẩn thanh điều hướng
     */
    private fun setupKioskWindow() {
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        val controller = WindowCompat.getInsetsController(window, window.decorView)
        controller.systemBarsBehavior = WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
        controller.hide(WindowInsetsCompat.Type.systemBars())
    }

    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (hasFocus) {
            setupKioskWindow()
        }
    }

    /**
     * 2. Cài đặt các sự kiện giao diện
     */
    private fun setupUI() {
        binding.tvServerIpBadge.visibility = View.GONE
        resetPersonalCard()

        // Nhấp 5 lần vào Logo để mở màn hình Admin cấu hình IP
        binding.layoutLogoAdmin.setOnClickListener {
            val now = System.currentTimeMillis()
            if (now - lastLogoTapTime > 2000) {
                logoTapCount = 0
            }
            lastLogoTapTime = now
            logoTapCount++

            if (logoTapCount >= 5) {
                logoTapCount = 0
                showAdminPinDialog()
            }
        }

        // Nút làm mới: Làm mới sạch sẽ hoàn toàn Dashboard về trạng thái trống, hủy active card trên Server
        binding.btnRefresh.setOnClickListener {
            resetPersonalCard()
            lastSuccessEmpId = ""
            lastSuccessTime = 0L
            faceAnalyzer.resumeScanning()
            lifecycleScope.launch(Dispatchers.IO) {
                try {
                    ApiClient.getService(this@MainActivity).dismissCard()
                } catch (e: Exception) {}
            }
            Toast.makeText(this, "Đã làm mới hệ thống Kiosk", Toast.LENGTH_SHORT).show()
        }
    }

    /**
     * 3. Cài đặt danh sách cuộn Lịch sử hôm nay (RecyclerView)
     */
    private fun setupRecyclerView() {
        // Lịch sử toàn đơn vị (Cột 3)
        logAdapter = AttendanceLogAdapter(prefs.getBaseUrl())
        binding.rvTodayLogs.layoutManager = LinearLayoutManager(this)
        binding.rvTodayLogs.adapter = logAdapter

        // Lịch sử ca trong ngày của riêng nhân viên (Cột 1)
        employeeTodayLogAdapter = EmployeeTodayLogAdapter(prefs.getBaseUrl())
        binding.rvEmployeeTodayLogs.layoutManager = LinearLayoutManager(this)
        binding.rvEmployeeTodayLogs.adapter = employeeTodayLogAdapter
    }

    /**
     * 4. Cài đặt chế độ Ca làm việc (Mặc định: Tự động - 3 nút đã ẩn khỏi giao diện)
     */
    private fun setupShiftModeButtons() {
        prefs.shiftMode = "auto"
    }

    /**
     * 5. Khởi tạo CameraFaceAnalyzer và xử lý phản hồi từ Server
     */
    private fun setupCameraAnalyzer() {
        faceAnalyzer = CameraFaceAnalyzer(
            onFaceDetected = { bounds, state, message, srcW, srcH ->
                runOnUiThread {
                    binding.faceOverlayView.updateFace(
                        bounds,
                        state,
                        message,
                        srcW,
                        srcH,
                        cameraHelper.isFrontCamera
                    )
                    if (message != null && binding.layoutPopupResult.visibility != View.VISIBLE) {
                        binding.tvCameraStatus.text = message
                    }
                }
            },
            onCaptureReady = { base64Image ->
                handleScanFace(base64Image)
            }
        )

        cameraHelper = CameraHelper(
            this,
            this,
            binding.cameraPreviewView,
            faceAnalyzer
        )
    }

    private fun checkPermissionsAndStartCamera() {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) {
            initCamera()
        } else {
            cameraPermissionLauncher.launch(Manifest.permission.CAMERA)
        }
    }

    private fun initCamera() {
        val useFront = (prefs.cameraFacing == "front")
        cameraHelper.startCamera(useFront) {
            binding.tvCameraStatus.text = "Camera đã sẵn sàng • Nhìn thẳng vào khung hình"
        }
    }

    // Chống spam: ghi nhớ người vừa điểm danh gần nhất (8 giây chuẩn Web RECOG_COOLDOWN_MS)
    private var lastSuccessEmpId: String = ""
    private var lastSuccessTime: Long = 0L

    /**
     * 6. Gửi khung hình Base64 lên Server Python và xử lý phản hồi AI liên tục (SCAN_INTERVAL_MS = 250ms)
     */
    private fun handleScanFace(base64Image: String) {
        lifecycleScope.launch(Dispatchers.IO) {
            try {
                val api = ApiClient.getService(this@MainActivity)
                val request = ScanFaceRequest(image = base64Image, mode = prefs.shiftMode)
                val response = api.scanFace(request)

                withContext(Dispatchers.Main) {
                    binding.dotOnlineStatus.backgroundTintList = ContextCompat.getColorStateList(this@MainActivity, R.color.neon_green)

                    if (!response.isSuccessful || response.body() == null) {
                        faceAnalyzer.finishRequest()
                        return@withContext
                    }

                    val result = response.body()!!

                    // A. THÀNH CÔNG NHẬN DIỆN VÀ ĐIỂM DANH!
                    if (result.recognized && result.card != null) {
                        val card = result.card
                        handleRecognitionSuccess(card)
                        faceAnalyzer.finishRequest()
                        return@withContext
                    }

                    // Nếu server trả về kết quả đang trong thời gian cooldown
                    if (result.cooldown) {
                        faceAnalyzer.finishRequest()
                        return@withContext
                    }

                    // B. PHÁT HIỆN GIẢ MẠO MÀN HÌNH / ẢNH CHỤP (PASSIVE LIVENESS)
                    if (result.reason == "spoof") {
                        val msg = result.message ?: "⚠️ CẢNH BÁO: ẢNH GIẢ MẠO"
                        binding.faceOverlayView.updateFace(null, FaceTrackerOverlayView.TrackerState.SPOOF, msg)
                        binding.tvCameraStatus.text = msg
                        audioHelper.playWarningBeep()
                        audioHelper.speakWarning()
                        faceAnalyzer.pauseScanning(2000L) // Tạm dừng 2 giây như Web
                        faceAnalyzer.finishRequest()
                        return@withContext
                    }

                    // C. NHẮC CHỚP MẮT HOẶC CỬ ĐỘNG NHẸ
                    if (result.reason == "need_motion") {
                        val msg = result.message ?: "VUI LÒNG CHỚP MẮT HOẶC CỬ ĐỘNG NHẸ"
                        binding.faceOverlayView.updateFace(null, FaceTrackerOverlayView.TrackerState.NEED_MOTION, msg)
                        binding.tvCameraStatus.text = msg
                        faceAnalyzer.finishRequest()
                        return@withContext
                    }

                    // D. GÓC NHÌN NGHIÊNG / CHƯA ĐẠT
                    if (result.reason == "pose") {
                        binding.tvCameraStatus.text = "Vui lòng nhìn thẳng vào camera"
                        faceAnalyzer.finishRequest()
                        return@withContext
                    }

                    if (result.reason == "unknown") {
                        binding.tvCameraStatus.text = "Khuôn mặt chưa được đăng ký trong hệ thống"
                        faceAnalyzer.finishRequest()
                        return@withContext
                    }

                    faceAnalyzer.finishRequest()
                }
            } catch (e: Exception) {
                withContext(Dispatchers.Main) {
                    binding.dotOnlineStatus.backgroundTintList = ContextCompat.getColorStateList(this@MainActivity, R.color.neon_red)
                    binding.tvCameraStatus.text = "Mất kết nối máy chủ (${prefs.serverIp})"
                    faceAnalyzer.finishRequest()
                }
            }
        }
    }

    /**
     * 7. Xử lý khi nhận diện thành công: Cập nhật thẻ trái + Popup 1.0s + Âm thanh + Đọc TTS
     */
    private fun handleRecognitionSuccess(card: KioskCard) {
        val fullName = card.name ?: card.profile?.fullName ?: "Nhân viên"
        val code = card.code ?: card.empId ?: ""
        val dept = card.dept ?: card.profile?.deptName ?: ""
        val role = card.role ?: card.profile?.nameRole ?: ""
        val timeNow = SimpleDateFormat("HH:mm:ss", Locale.getDefault()).format(Date())
        val confText = if (card.confidence != null) String.format(Locale.US, "%.1f%% (Đạt)", card.confidence) else "100% (Đạt)"

        // Chống spam: cùng người vừa nhận diện trong vòng 8 giây (RECOG_COOLDOWN_MS = 8000L) thì bỏ qua
        val now = System.currentTimeMillis()
        if (code.isNotEmpty() && code == lastSuccessEmpId && (now - lastSuccessTime < 8000L)) {
            faceAnalyzer.pauseScanning(1500L)
            return
        }

        lastSuccessEmpId = code
        lastSuccessTime = now

        // Tạm dừng quét 2.5 giây (SUCCESS_PAUSE_MS = 2500ms: 1.0s popup + 1.5s chuyển tiếp)
        faceAnalyzer.pauseScanning(2500L)

        // Báo trạng thái tracker thành công
        binding.faceOverlayView.updateFace(null, FaceTrackerOverlayView.TrackerState.SUCCESS, "✓ ĐÃ XÁC THỰC THÀNH CÔNG")

        val workplace = card.workplace ?: card.profile?.workPlaceName ?: ""

        // 1. Cập nhật Thẻ hồ sơ bên trái (Cột 1)
        binding.tvPersonalName.text = fullName.uppercase()
        binding.tvPersonalCode.text = if (code.isNotEmpty()) code else "---"
        binding.tvPersonalPosition.text = if (role.isNotEmpty()) role else "---"
        binding.tvPersonalWorkplace.text = if (workplace.isNotEmpty()) workplace else "---"
        binding.tvPersonalDept.text = if (dept.isNotEmpty()) dept.uppercase() else "---"
        binding.tvPersonalTime.text = timeNow
        binding.tvPersonalConfidence.text = confText

        // Đặt lịch tự động làm mới thẻ thông tin về trống sau 10 giây (PERSONAL_CARD_TIMEOUT_MS = 10000L)
        personalCardClearRunnable?.let { personalCardClearHandler.removeCallbacks(it) }
        personalCardClearRunnable = Runnable { resetPersonalCard() }
        personalCardClearHandler.postDelayed(personalCardClearRunnable!!, PERSONAL_CARD_TIMEOUT_MS)

        // Tải lịch sử các lượt chấm công hôm nay của riêng nhân viên này (Bảo mật thông tin cá nhân)
        if (card.todayLogs.isNotEmpty()) {
            employeeTodayLogAdapter.submitList(card.todayLogs)
            binding.tvTodayCountBadge.text = "${card.todayLogs.size} lượt"
            binding.tvTodayEmptyLogs.visibility = View.GONE
            binding.rvEmployeeTodayLogs.visibility = View.VISIBLE
        }

        if (code.isNotEmpty()) {
            lifecycleScope.launch(Dispatchers.IO) {
                try {
                    val api = ApiClient.getService(this@MainActivity)
                    val resp = api.getEmployeeLogs(code)
                    if (resp.isSuccessful && resp.body()?.logs?.isNotEmpty() == true) {
                        val shiftLogs = resp.body()!!.logs
                        withContext(Dispatchers.Main) {
                            employeeTodayLogAdapter.submitList(shiftLogs)
                            binding.tvTodayCountBadge.text = "${shiftLogs.size} lượt"
                            binding.tvTodayEmptyLogs.visibility = View.GONE
                            binding.rvEmployeeTodayLogs.visibility = View.VISIBLE
                        }
                    }
                } catch (e: Exception) {
                    // Không làm ảnh hưởng luồng chấm công nếu mạng phụ tải logs trễ
                }
            }
        }

        // Tải ảnh đại diện (Ưu tiên ảnh snapshot vừa chụp)
        val cleanBase = prefs.getBaseUrl().removeSuffix("/")
        val avatarUrl = when {
            !card.snapshot.isNullOrEmpty() -> "$cleanBase/snapshots/${card.snapshot}"
            !card.avatar.isNullOrEmpty() -> "$cleanBase${if (card.avatar.startsWith("/")) "" else "/"}${card.avatar}"
            code.isNotEmpty() -> "$cleanBase/api_faces/$code.jpg"
            else -> ""
        }

        Glide.with(this)
            .load(avatarUrl)
            .diskCacheStrategy(DiskCacheStrategy.ALL)
            .placeholder(R.mipmap.ic_launcher_round)
            .into(binding.imgPersonalAvatar)

        // 2. Hiển thị Popup chúc mừng hoàn tất trong 1.0 giây (chuẩn Phần 5)
        showSuccessPopup(
            fullName = fullName,
            code = code,
            role = role,
            dept = dept,
            time = timeNow,
            conf = confText,
            avatarUrl = avatarUrl
        )

        // 3. Phát âm thanh Ting và Đọc giọng nói Tiếng Việt ngắn gọn trong 1s
        audioHelper.playSuccessTing()
        audioHelper.speakGreeting(fullName)
    }

    /**
     * Tự động xóa thẻ thông tin cá nhân về trạng thái trống sau 10 giây (chuẩn resetPersonalCard() trên Web)
     */
    private fun resetPersonalCard() {
        personalCardClearRunnable?.let { personalCardClearHandler.removeCallbacks(it) }
        binding.tvPersonalName.text = "---"
        binding.tvPersonalCode.text = "---"
        binding.tvPersonalPosition.text = "---"
        binding.tvPersonalWorkplace.text = "---"
        binding.tvPersonalDept.text = "---"
        binding.tvPersonalTime.text = "--:--:--"
        binding.tvPersonalConfidence.text = "---"
        binding.imgPersonalAvatar.setImageResource(R.mipmap.ic_launcher_round)
        binding.tvTodayCountBadge.text = "0 lượt"
        binding.tvTodayEmptyLogs.visibility = View.VISIBLE
        binding.rvEmployeeTodayLogs.visibility = View.GONE
        if (::employeeTodayLogAdapter.isInitialized) {
            employeeTodayLogAdapter.clear()
        }
    }

    /**
     * 8. Hiển thị Popup 1 ô Avatar trung tâm kèm huy hiệu tích xanh, 4 ô chi tiết và thanh đếm ngược tự tắt sau 1.0 giây (POPUP_DURATION_MS = 1000)
     */
    private fun showSuccessPopup(
        fullName: String,
        code: String,
        role: String,
        dept: String,
        time: String,
        conf: String,
        avatarUrl: String
    ) {
        popupHideHandler.removeCallbacksAndMessages(null)
        popupAnimator?.cancel()

        binding.tvPopupName.text = fullName.uppercase()
        binding.tvPopupEmpId.text = if (code.isNotEmpty()) code else "---"
        binding.tvPopupRole.text = if (role.isNotEmpty()) role else "Nhân viên"
        binding.tvPopupDept.text = if (dept.isNotEmpty()) dept else "---"
        binding.tvPopupTime.text = time
        binding.tvPopupConfidence.text = conf
        binding.tvPopupCountdownNum.text = "1.0s"

        Glide.with(this)
            .load(avatarUrl)
            .diskCacheStrategy(DiskCacheStrategy.ALL)
            .placeholder(R.mipmap.ic_launcher_round)
            .error(R.mipmap.ic_launcher_round)
            .into(binding.imgPopupAvatar)

        binding.layoutPopupResult.visibility = View.VISIBLE

        // Thanh tiến trình chạy từ 100% về 0% trong 1000ms (1.0s)
        binding.progressCountdown.progress = 100
        popupAnimator = ValueAnimator.ofInt(100, 0).apply {
            duration = 1000L
            interpolator = LinearInterpolator()
            addUpdateListener { anim ->
                val p = anim.animatedValue as Int
                binding.progressCountdown.progress = p
                val secLeft = p * 1.0f / 100f
                binding.tvPopupCountdownNum.text = String.format(Locale.US, "%.1fs", secLeft)
            }
            start()
        }

        popupHideHandler.postDelayed({
            binding.layoutPopupResult.visibility = View.GONE
            binding.faceOverlayView.clear()
            binding.tvCameraStatus.text = "Sẵn sàng đón người tiếp theo • Nhìn thẳng camera"
            // Lưu ý quan trọng: KHÔNG gọi resetPersonalCard() tại đây!
            // Popup chúc mừng tắt đi sau 1.0s nhưng Thẻ cá nhân & Lịch sử các lượt chấm công hôm nay
            // sẽ tiếp tục hiển thị trên màn hình trong 10 giây (PERSONAL_CARD_TIMEOUT_MS = 10000L)
            // để người dùng có thời gian kiểm tra lịch sử, chuẩn theo kiến trúc bản Web Kiosk.
        }, 1000L)
    }

    /**
     * 9. Lấy trạng thái kết nối Kiosk từ Server
     */
    private fun fetchKioskStatus() {
        lifecycleScope.launch(Dispatchers.IO) {
            try {
                val api = ApiClient.getService(this@MainActivity)
                val resp = api.getKioskStatus()
                if (resp.isSuccessful && resp.body() != null) {
                    withContext(Dispatchers.Main) {
                        binding.dotOnlineStatus.backgroundTintList = ContextCompat.getColorStateList(this@MainActivity, R.color.neon_green)
                    }
                }
            } catch (e: Exception) {
                withContext(Dispatchers.Main) {
                    binding.dotOnlineStatus.backgroundTintList = ContextCompat.getColorStateList(this@MainActivity, R.color.neon_red)
                }
            }
        }
    }

    /**
     * 10. Màn hình Cài đặt Quản trị (Admin PIN)
     */
    private fun showAdminPinDialog() {
        val input = EditText(this).apply {
            hint = "Nhập mã PIN Quản lý (Mặc định: 123456)"
            inputType = android.text.InputType.TYPE_CLASS_NUMBER or android.text.InputType.TYPE_NUMBER_VARIATION_PASSWORD
        }

        AlertDialog.Builder(this)
            .setTitle("Bảo Mật Quản Trị")
            .setMessage("Vui lòng nhập mã PIN để cấu hình Kiosk:")
            .setView(input)
            .setPositiveButton("Xác Nhận") { _, _ ->
                val pin = input.text.toString().trim()
                if (pin == prefs.adminPin) {
                    showAdminSettingsDialog()
                } else {
                    Toast.makeText(this, "Mã PIN không chính xác!", Toast.LENGTH_SHORT).show()
                }
            }
            .setNegativeButton("Hủy", null)
            .show()
    }

    private fun showAdminSettingsDialog() {
        val dialogView = layoutInflater.inflate(R.layout.dialog_admin_settings, null)
        val edtIp = dialogView.findViewById<EditText>(R.id.edtServerIp)
        val edtPort = dialogView.findViewById<EditText>(R.id.edtServerPort)
        val btnSave = dialogView.findViewById<Button>(R.id.btnSave)
        val btnCancel = dialogView.findViewById<Button>(R.id.btnCancel)
        val btnTest = dialogView.findViewById<Button>(R.id.btnTestPing)

        edtIp.setText(prefs.serverIp)
        edtPort.setText(prefs.serverPort.toString())

        val dialog = AlertDialog.Builder(this)
            .setView(dialogView)
            .setCancelable(false)
            .create()

        btnCancel.setOnClickListener { dialog.dismiss() }

        btnTest.setOnClickListener {
            val testIp = edtIp.text.toString().trim()
            val testPort = edtPort.text.toString().toIntOrNull() ?: 5055
            Toast.makeText(this, "Đang kiểm tra kết nối tới $testIp:$testPort...", Toast.LENGTH_SHORT).show()

            lifecycleScope.launch(Dispatchers.IO) {
                try {
                    prefs.serverIp = testIp
                    prefs.serverPort = testPort
                    ApiClient.reset()
                    val resp = ApiClient.getService(this@MainActivity).getKioskStatus()
                    withContext(Dispatchers.Main) {
                        if (resp.isSuccessful) {
                            Toast.makeText(this@MainActivity, "Kết nối thành công tới Server Python! ✔", Toast.LENGTH_LONG).show()
                        } else {
                            Toast.makeText(this@MainActivity, "Server phản hồi mã lỗi: ${resp.code()}", Toast.LENGTH_SHORT).show()
                        }
                    }
                } catch (e: Exception) {
                    withContext(Dispatchers.Main) {
                        Toast.makeText(this@MainActivity, "Lỗi kết nối: ${e.message}", Toast.LENGTH_LONG).show()
                    }
                }
            }
        }

        btnSave.setOnClickListener {
            val newIp = edtIp.text.toString().trim()
            val newPort = edtPort.text.toString().toIntOrNull() ?: 5055

            if (newIp.isNotEmpty()) {
                prefs.serverIp = newIp
                prefs.serverPort = newPort
                ApiClient.reset()
                logAdapter.updateBaseUrl(prefs.getBaseUrl())
                binding.tvServerIpBadge.text = "$newIp:$newPort"
                fetchKioskStatus()
                dialog.dismiss()
                Toast.makeText(this, "Đã lưu cấu hình mới!", Toast.LENGTH_SHORT).show()
            }
        }

        dialog.show()
    }

    private fun updateDigitalClock() {
        val sdf = SimpleDateFormat("HH:mm:ss • EEEE, dd/MM/yyyy", Locale.forLanguageTag("vi-VN"))
        binding.tvDigitalClock.text = sdf.format(Date())
    }

    override fun onDestroy() {
        super.onDestroy()
        clockHandler.removeCallbacksAndMessages(null)
        popupHideHandler.removeCallbacksAndMessages(null)
        popupAnimator?.cancel()
        cameraHelper.shutdown()
        audioHelper.shutdown()
    }
}