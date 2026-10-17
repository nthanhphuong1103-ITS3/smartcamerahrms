package com.hrms.kiosk.util

import android.content.Context
import android.content.SharedPreferences

class AppPreferences(context: Context) {

    private val prefs: SharedPreferences = context.getSharedPreferences(PREF_NAME, Context.MODE_PRIVATE)

    companion object {
        private const val PREF_NAME = "hrms_kiosk_prefs"
        private const val KEY_SERVER_IP = "key_server_ip"
        private const val KEY_SERVER_PORT = "key_server_port"
        private const val KEY_SHIFT_MODE = "key_shift_mode"
        private const val KEY_CAMERA_FACING = "key_camera_facing"
        private const val KEY_ADMIN_PIN = "key_admin_pin"
        private const val KEY_COOLDOWN_MS = "key_cooldown_ms"

        const val DEFAULT_IP = "192.168.5.99"
        const val DEFAULT_PORT = 5055
        const val DEFAULT_PIN = "123456"
        const val DEFAULT_COOLDOWN = 3500L
    }

    var serverIp: String
        get() = prefs.getString(KEY_SERVER_IP, DEFAULT_IP) ?: DEFAULT_IP
        set(value) = prefs.edit().putString(KEY_SERVER_IP, value.trim()).apply()

    var serverPort: Int
        get() = prefs.getInt(KEY_SERVER_PORT, DEFAULT_PORT)
        set(value) = prefs.edit().putInt(KEY_SERVER_PORT, value).apply()

    var shiftMode: String
        get() = prefs.getString(KEY_SHIFT_MODE, "auto") ?: "auto"
        set(value) = prefs.edit().putString(KEY_SHIFT_MODE, value).apply()

    var cameraFacing: String
        get() = prefs.getString(KEY_CAMERA_FACING, "front") ?: "front"
        set(value) = prefs.edit().putString(KEY_CAMERA_FACING, value).apply()

    var adminPin: String
        get() = prefs.getString(KEY_ADMIN_PIN, DEFAULT_PIN) ?: DEFAULT_PIN
        set(value) = prefs.edit().putString(KEY_ADMIN_PIN, value.trim()).apply()

    var cooldownMs: Long
        get() = prefs.getLong(KEY_COOLDOWN_MS, DEFAULT_COOLDOWN)
        set(value) = prefs.edit().putLong(KEY_COOLDOWN_MS, value).apply()

    fun getBaseUrl(): String {
        val ip = serverIp.trim().removeSuffix("/")
        return if (ip.startsWith("http://") || ip.startsWith("https://")) {
            "$ip:$serverPort/"
        } else {
            "http://$ip:$serverPort/"
        }
    }
}
