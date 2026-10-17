package com.hrms.kiosk.audio

import android.content.Context
import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioTrack
import android.speech.tts.TextToSpeech
import java.util.Calendar
import java.util.Locale
import kotlin.math.PI
import kotlin.math.exp
import kotlin.math.sin

/**
 * Quản lý âm thanh Kiosk chuẩn 1:1 Kiosk Web (kiosk_portal.py):
 * - Hợp âm Ting Doanh nghiệp (A-Major: 880Hz, 1100Hz, 1320Hz) tổng hợp PCM Hi-Fi 0ms latency
 * - Âm thanh cảnh báo giả mạo / góc nghiêng (Quét hạ tần 220Hz -> 160Hz)
 * - Giọng đọc Tiếng Việt (Google TTS Native) thông minh ngẫu nhiên theo 3 khung giờ: Sáng, Chiều, Tối
 */
class AudioHelper(context: Context) {

    private var tts: TextToSpeech? = null
    private var isTtsReady: Boolean = false

    private var successAudioTrack: AudioTrack? = null
    private var warningAudioTrack: AudioTrack? = null

    init {
        // 1. Khởi tạo Text-to-Speech Tiếng Việt
        tts = TextToSpeech(context.applicationContext) { status ->
            if (status == TextToSpeech.SUCCESS) {
                val result = tts?.setLanguage(Locale.forLanguageTag("vi-VN"))
                if (result == TextToSpeech.LANG_MISSING_DATA || result == TextToSpeech.LANG_NOT_SUPPORTED) {
                    tts?.language = Locale.getDefault()
                }
                tts?.setSpeechRate(1.18f)  // Tốc độ nhanh nhẹn, dứt khoát hoàn tất trong 1 giây
                tts?.setPitch(1.05f)       // Giọng trong trẻo, tươi vui chuẩn bản Web
                isTtsReady = true
            }
        }

        // 2. Khởi tạo âm thanh Ting Hợp âm A-Major (880Hz, 1100Hz, 1320Hz) chuẩn Web Audio API
        initSuccessChime()

        // 3. Khởi tạo âm thanh Cảnh báo (Sawtooth Sweep 220Hz -> 160Hz)
        initWarningSound()
    }

    /**
     * Tạo âm thanh chuông Ting đa âm A-Major:
     * - Nốt 1: 880 Hz (La 5) tại 0.00s
     * - Nốt 2: 1100 Hz (Đô# 6) tại 0.10s
     * - Nốt 3: 1320 Hz (Mi 6) tại 0.22s
     * - Giảm dần theo hàm mũ (Exponential Decay) trong 0.6s
     */
    private fun initSuccessChime() {
        try {
            val sampleRate = 44100
            val durationSec = 0.85
            val numSamples = (durationSec * sampleRate).toInt()
            val samples = ShortArray(numSamples)

            for (i in 0 until numSamples) {
                val t = i.toDouble() / sampleRate.toDouble()

                // Nốt 1: 880Hz tại t >= 0.0s
                val t1 = t - 0.00
                val a1 = if (t1 >= 0) exp(-t1 * 5.2) * sin(2.0 * PI * 880.0 * t1) else 0.0

                // Nốt 2: 1100Hz tại t >= 0.10s
                val t2 = t - 0.10
                val a2 = if (t2 >= 0) exp(-t2 * 5.2) * sin(2.0 * PI * 1100.0 * t2) else 0.0

                // Nốt 3: 1320Hz tại t >= 0.22s
                val t3 = t - 0.22
                val a3 = if (t3 >= 0) exp(-t3 * 5.2) * sin(2.0 * PI * 1320.0 * t3) else 0.0

                val totalAmp = (a1 * 0.35 + a2 * 0.35 + a3 * 0.38).coerceIn(-1.0, 1.0)
                samples[i] = (totalAmp * 32767).toInt().toShort()
            }

            val bufferSize = numSamples * 2
            successAudioTrack = AudioTrack.Builder()
                .setAudioAttributes(
                    AudioAttributes.Builder()
                        .setUsage(AudioAttributes.USAGE_MEDIA)
                        .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                        .build()
                )
                .setAudioFormat(
                    AudioFormat.Builder()
                        .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                        .setSampleRate(sampleRate)
                        .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                        .build()
                )
                .setBufferSizeInBytes(bufferSize)
                .setTransferMode(AudioTrack.MODE_STATIC)
                .build()

            successAudioTrack?.write(samples, 0, numSamples)
        } catch (e: Exception) {
            e.printStackTrace()
        }
    }

    /**
     * Tạo âm thanh cảnh báo trầm (Sawtooth Sweep 220Hz -> 160Hz) chuẩn Web
     */
    private fun initWarningSound() {
        try {
            val sampleRate = 44100
            val durationSec = 0.45
            val numSamples = (durationSec * sampleRate).toInt()
            val samples = ShortArray(numSamples)

            for (i in 0 until numSamples) {
                val t = i.toDouble() / sampleRate.toDouble()
                val freq = 220.0 - (60.0 * (t / durationSec)) // Quét từ 220Hz xuống 160Hz
                val decay = exp(-t * 3.5)
                val amp = (sin(2.0 * PI * freq * t) * 0.45 * decay).coerceIn(-1.0, 1.0)
                samples[i] = (amp * 32767).toInt().toShort()
            }

            val bufferSize = numSamples * 2
            warningAudioTrack = AudioTrack.Builder()
                .setAudioAttributes(
                    AudioAttributes.Builder()
                        .setUsage(AudioAttributes.USAGE_MEDIA)
                        .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                        .build()
                )
                .setAudioFormat(
                    AudioFormat.Builder()
                        .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                        .setSampleRate(sampleRate)
                        .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                        .build()
                )
                .setBufferSizeInBytes(bufferSize)
                .setTransferMode(AudioTrack.MODE_STATIC)
                .build()

            warningAudioTrack?.write(samples, 0, numSamples)
        } catch (e: Exception) {
            e.printStackTrace()
        }
    }

    /**
     * Phát âm thanh chuông Ting hợp âm A-Major ngân vang
     */
    fun playSuccessTing() {
        try {
            successAudioTrack?.let { track ->
                if (track.playState == AudioTrack.PLAYSTATE_PLAYING) {
                    track.stop()
                }
                track.reloadStaticData()
                track.play()
            }
        } catch (e: Exception) {
            e.printStackTrace()
        }
    }

    /**
     * Phát âm thanh cảnh báo
     */
    fun playWarningBeep() {
        try {
            warningAudioTrack?.let { track ->
                if (track.playState == AudioTrack.PLAYSTATE_PLAYING) {
                    track.stop()
                }
                track.reloadStaticData()
                track.play()
            }
        } catch (e: Exception) {
            e.printStackTrace()
        }
    }

    /**
     * Bộ câu chúc thông minh Tiếng Việt ngắn gọn dứt khoát hoàn tất trong 1 giây (khớp với thời gian Popup 1.0s)
     * Trích xuất tên gọi (ví dụ "Nguyễn Văn An" -> "An") và phát câu chúc 3-4 từ nhanh gọn.
     */
    fun speakGreeting(fullName: String) {
        if (!isTtsReady) return

        val callName = if (fullName.isNotBlank() && fullName != "Nhân viên" && fullName != "---") {
            fullName.trim().split("\\s+".toRegex()).lastOrNull() ?: fullName
        } else {
            "bạn"
        }

        val hour = Calendar.getInstance().get(Calendar.HOUR_OF_DAY)
        val wishes = when {
            // 1. Buổi sáng (Trước 11:00) - Ngắn gọn <= 4 từ (~0.7s)
            hour < 11 -> listOf(
                "Chào buổi sáng $callName!",
                "Xin chào $callName!",
                "Chào $callName ngày mới!"
            )
            // 2. Buổi trưa & Chiều (11:00 đến 17:00) - Ngắn gọn <= 4 từ (~0.7s)
            hour in 11..16 -> listOf(
                "Chào buổi chiều $callName!",
                "Xin chào $callName!",
                "Chào $callName nhé!"
            )
            // 3. Buổi tối / Tan ca (Từ 17:00 trở đi) - Ngắn gọn <= 4 từ (~0.7s)
            else -> listOf(
                "Tạm biệt $callName!",
                "Chào $callName ra về!",
                "Hẹn gặp lại $callName!"
            )
        }

        val chosenWish = wishes.random()
        tts?.stop()
        tts?.speak(chosenWish, TextToSpeech.QUEUE_FLUSH, null, "greeting_id")
    }

    /**
     * Lời nhắc cảnh báo lịch sự chuẩn bản Web
     */
    fun speakWarning(warningMsg: String = "Vui lòng nhìn thẳng vào camera và thử lại.") {
        if (!isTtsReady) return
        tts?.stop()
        tts?.speak(warningMsg, TextToSpeech.QUEUE_FLUSH, null, "warning_id")
    }

    fun shutdown() {
        try {
            tts?.stop()
            tts?.shutdown()
            successAudioTrack?.release()
            warningAudioTrack?.release()
        } catch (e: Exception) {
            e.printStackTrace()
        }
    }
}
