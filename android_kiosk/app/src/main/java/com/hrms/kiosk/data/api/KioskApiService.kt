package com.hrms.kiosk.data.api

import com.hrms.kiosk.data.model.EmployeeLogsResponse
import com.hrms.kiosk.data.model.KioskStatusResponse
import com.hrms.kiosk.data.model.ScanFaceRequest
import com.hrms.kiosk.data.model.ScanFaceResponse
import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Path

interface KioskApiService {

    /**
     * Gửi khung hình JPEG base64 lên server để nhận diện, chống giả mạo và điểm danh tức thì
     */
    @POST("api/kiosk/scan_face")
    suspend fun scanFace(
        @Body request: ScanFaceRequest
    ): Response<ScanFaceResponse>

    /**
     * Lấy trạng thái Kiosk, danh sách nhật ký chấm công hôm nay và số lượng nhân sự
     */
    @GET("api/kiosk_status")
    suspend fun getKioskStatus(): Response<KioskStatusResponse>

    /**
     * Lấy lịch sử tất cả các lượt chấm công trong ngày của 1 nhân viên cụ thể
     */
    @GET("api/kiosk/employee_today_logs/{emp_code}")
    suspend fun getEmployeeLogs(
        @Path("emp_code") empCode: String
    ): Response<EmployeeLogsResponse>

    /**
     * Xóa thẻ active card trên máy chủ (khi reset màn hình)
     */
    @POST("api/dismiss_card")
    suspend fun dismissCard(): Response<Map<String, Any>>
}
