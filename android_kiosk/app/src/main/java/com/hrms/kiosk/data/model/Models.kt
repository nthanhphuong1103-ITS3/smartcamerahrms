package com.hrms.kiosk.data.model

import com.google.gson.annotations.SerializedName

/**
 * Request gửi ảnh nhận diện lên Server
 */
data class ScanFaceRequest(
    @SerializedName("image")
    val image: String, // Chuỗi Base64 JPEG (kèm hoặc không kèm header data:image/jpeg;base64,)

    @SerializedName("mode")
    val mode: String = "auto" // "auto" | "in" | "out"
)

/**
 * Phản hồi từ API POST /api/kiosk/scan_face
 */
data class ScanFaceResponse(
    @SerializedName("success")
    val success: Boolean = false,

    @SerializedName("recognized")
    val recognized: Boolean = false,

    @SerializedName("cooldown")
    val cooldown: Boolean = false,

    @SerializedName("logged")
    val logged: Boolean = false,

    @SerializedName("emp_id")
    val empId: String? = null,

    @SerializedName("code")
    val code: String? = null,

    @SerializedName("profile")
    val profile: EmployeeProfile? = null,

    @SerializedName("card")
    val card: KioskCard? = null,

    @SerializedName("confidence")
    val confidence: Double? = null,

    @SerializedName("reason")
    val reason: String? = null, // "no_face" | "pose" | "spoof" | "need_motion" | "unknown" | "low_confidence"

    @SerializedName("message")
    val message: String? = null,

    @SerializedName("snapshot")
    val snapshot: String? = null,

    @SerializedName("snapshot_url")
    val snapshotUrl: String? = null,

    @SerializedName("p_real")
    val pReal: Double? = null,

    @SerializedName("p_screen")
    val pScreen: Double? = null
)

/**
 * Thông tin hồ sơ nhân viên HRMS
 */
data class EmployeeProfile(
    @SerializedName("ID")
    val id: String? = null,

    @SerializedName("EmployeeCode")
    val employeeCode: String? = null,

    @SerializedName("FullName")
    val fullName: String? = null,

    @SerializedName("Name_Role")
    val nameRole: String? = null,

    @SerializedName("Dept_Name")
    val deptName: String? = null,

    @SerializedName("Company_Name")
    val companyName: String? = null,

    @SerializedName("WorkPlaceName")
    val workPlaceName: String? = null
)

/**
 * Thẻ thông tin Kiosk hiển thị trên màn hình
 */
data class KioskCard(
    @SerializedName("event_id")
    val eventId: Long = 0,

    @SerializedName("card_id")
    val cardId: String? = null,

    @SerializedName("timestamp")
    val timestamp: Double = 0.0,

    @SerializedName("emp_id")
    val empId: String? = null,

    @SerializedName("code")
    val code: String? = null,

    @SerializedName("name")
    val name: String? = null,

    @SerializedName("role")
    val role: String? = null,

    @SerializedName("dept")
    val dept: String? = null,

    @SerializedName("company")
    val company: String? = null,

    @SerializedName("workplace")
    val workplace: String? = null,

    @SerializedName("profile")
    val profile: EmployeeProfile? = null,

    @SerializedName("confidence")
    val confidence: Double? = null,

    @SerializedName("expire_time")
    val expireTime: Double = 0.0,

    @SerializedName("cam_name")
    val camName: String? = null,

    @SerializedName("snapshot")
    val snapshot: String? = null,

    @SerializedName("snapshot_url")
    val snapshotUrl: String? = null,

    @SerializedName("avatar")
    val avatar: String? = null,

    @SerializedName("mode")
    val mode: String? = null,

    @SerializedName("time")
    val time: String? = null,

    @SerializedName("today_logs")
    val todayLogs: List<AttendanceLogItem> = emptyList()
)

/**
 * Lịch sử 1 lượt điểm danh
 */
data class AttendanceLogItem(
    @SerializedName("time")
    val time: String? = null,

    @SerializedName("time_short")
    val timeShort: String? = null,

    @SerializedName("code")
    val code: String? = null,

    @SerializedName("name")
    val name: String? = null,

    @SerializedName("role")
    val role: String? = null,

    @SerializedName("dept")
    val dept: String? = null,

    @SerializedName("company")
    val company: String? = null,

    @SerializedName("status")
    val status: String? = null,

    @SerializedName("type")
    val type: String? = null,

    @SerializedName("conf")
    val conf: String? = null,

    @SerializedName("cam")
    val cam: String? = null,

    @SerializedName("snapshot")
    val snapshot: String? = null,

    @SerializedName("avatar")
    val avatar: String? = null
)

/**
 * Phản hồi trạng thái GET /api/kiosk_status
 */
data class KioskStatusResponse(
    @SerializedName("api_count")
    val apiCount: Int = 0,

    @SerializedName("db_count")
    val dbCount: Int = 0,

    @SerializedName("active_card")
    val activeCard: KioskCard? = null,

    @SerializedName("latest_event")
    val latestEvent: KioskCard? = null,

    @SerializedName("last_event_id")
    val lastEventId: Long = 0,

    @SerializedName("logs")
    val logs: List<AttendanceLogItem> = emptyList()
)

/**
 * Phản hồi nhật ký nhân viên hôm nay
 */
data class EmployeeLogsResponse(
    @SerializedName("success")
    val success: Boolean = false,

    @SerializedName("code")
    val code: String? = null,

    @SerializedName("logs")
    val logs: List<AttendanceLogItem> = emptyList()
)
