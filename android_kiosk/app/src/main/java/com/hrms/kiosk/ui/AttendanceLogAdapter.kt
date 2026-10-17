package com.hrms.kiosk.ui

import android.view.LayoutInflater
import android.view.ViewGroup
import androidx.core.content.ContextCompat
import androidx.recyclerview.widget.RecyclerView
import com.bumptech.glide.Glide
import com.bumptech.glide.load.engine.DiskCacheStrategy
import com.hrms.kiosk.R
import com.hrms.kiosk.data.model.AttendanceLogItem
import com.hrms.kiosk.databinding.ItemAttendanceLogBinding

class AttendanceLogAdapter(
    private var baseUrl: String,
    private val items: MutableList<AttendanceLogItem> = mutableListOf()
) : RecyclerView.Adapter<AttendanceLogAdapter.LogViewHolder>() {

    fun updateBaseUrl(newBaseUrl: String) {
        this.baseUrl = newBaseUrl
    }

    fun submitList(newItems: List<AttendanceLogItem>) {
        items.clear()
        items.addAll(newItems)
        notifyDataSetChanged()
    }

    fun addFirst(item: AttendanceLogItem) {
        items.add(0, item)
        notifyItemInserted(0)
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): LogViewHolder {
        val binding = ItemAttendanceLogBinding.inflate(
            LayoutInflater.from(parent.context), parent, false
        )
        return LogViewHolder(binding)
    }

    override fun onBindViewHolder(holder: LogViewHolder, position: Int) {
        holder.bind(items[position])
    }

    override fun getItemCount(): Int = items.size

    inner class LogViewHolder(private val binding: ItemAttendanceLogBinding) :
        RecyclerView.ViewHolder(binding.root) {

        fun bind(item: AttendanceLogItem) {
            val context = binding.root.context

            // Họ và tên
            binding.tvName.text = item.name?.uppercase() ?: "NHÂN VIÊN"

            // Mã NV & Phòng ban
            val code = item.code ?: ""
            val dept = item.dept ?: ""
            val sub = listOf(code, dept).filter { it.isNotEmpty() }.joinToString(" · ")
            binding.tvSubInfo.text = sub.ifEmpty { "Nhân sự HRMS" }

            // Giờ chấm công
            val timeStr = item.time ?: ""
            val timeDisplay = if (timeStr.contains(" ")) {
                timeStr.substringAfterLast(" ")
            } else {
                timeStr
            }
            binding.tvTime.text = timeDisplay.ifEmpty { "--:--" }

            // Huy hiệu loại ca (Vào ca / Tan ca / Điểm danh)
            val camUpper = (item.cam ?: "").uppercase()
            val statusUpper = (item.status ?: "").uppercase()

            val isShiftIn = camUpper.contains("VÀO") || statusUpper.contains("VÀO")
            val isShiftOut = camUpper.contains("TAN") || camUpper.contains("RA") || statusUpper.contains("TAN")

            when {
                isShiftIn -> {
                    binding.tvBadge.text = "Vào ca"
                    binding.tvBadge.setBackgroundColor(ContextCompat.getColor(context, R.color.shift_in))
                }
                isShiftOut -> {
                    binding.tvBadge.text = "Tan ca"
                    binding.tvBadge.setBackgroundColor(ContextCompat.getColor(context, R.color.shift_out))
                }
                else -> {
                    binding.tvBadge.text = "Điểm danh"
                    binding.tvBadge.setBackgroundColor(ContextCompat.getColor(context, R.color.shift_auto))
                }
            }

            // Tải ảnh đại diện / snapshot bằng Glide
            val cleanBase = baseUrl.removeSuffix("/")
            val imageUrl = when {
                !item.snapshot.isNullOrEmpty() -> "$cleanBase/snapshots/${item.snapshot}"
                !item.avatar.isNullOrEmpty() -> "$cleanBase/api_faces/${item.avatar}"
                !code.isEmpty() -> "$cleanBase/api_faces/$code.jpg"
                else -> ""
            }

            if (imageUrl.isNotEmpty()) {
                Glide.with(context)
                    .load(imageUrl)
                    .diskCacheStrategy(DiskCacheStrategy.ALL)
                    .placeholder(R.mipmap.ic_launcher_round)
                    .error(R.mipmap.ic_launcher_round)
                    .into(binding.imgAvatar)
            } else {
                binding.imgAvatar.setImageResource(R.mipmap.ic_launcher_round)
            }
        }
    }
}
