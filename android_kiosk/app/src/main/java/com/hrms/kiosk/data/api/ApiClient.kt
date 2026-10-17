package com.hrms.kiosk.data.api

import android.content.Context
import com.hrms.kiosk.util.AppPreferences
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import java.util.concurrent.TimeUnit

object ApiClient {

    private var currentBaseUrl: String? = null
    private var cachedService: KioskApiService? = null

    private val okHttpClient: OkHttpClient by lazy {
        val logging = HttpLoggingInterceptor().apply {
            level = HttpLoggingInterceptor.Level.NONE
        }

        OkHttpClient.Builder()
            .addInterceptor(logging)
            .connectTimeout(4, TimeUnit.SECONDS)
            .readTimeout(8, TimeUnit.SECONDS)
            .writeTimeout(8, TimeUnit.SECONDS)
            .retryOnConnectionFailure(true)
            .build()
    }

    /**
     * Lấy KioskApiService, tự động cập nhật Retrofit nếu người dùng đổi IP/Cổng trong cài đặt
     */
    @Synchronized
    fun getService(context: Context): KioskApiService {
        val prefs = AppPreferences(context)
        val targetUrl = prefs.getBaseUrl()

        if (cachedService != null && currentBaseUrl == targetUrl) {
            return cachedService!!
        }

        currentBaseUrl = targetUrl
        val retrofit = Retrofit.Builder()
            .baseUrl(targetUrl)
            .client(okHttpClient)
            .addConverterFactory(GsonConverterFactory.create())
            .build()

        cachedService = retrofit.create(KioskApiService::class.java)
        return cachedService!!
    }

    /**
     * Hủy cache để ép Retrofit kết nối lại theo IP mới
     */
    @Synchronized
    fun reset() {
        currentBaseUrl = null
        cachedService = null
    }
}
