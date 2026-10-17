package com.hrms.kiosk.ui

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import androidx.core.content.ContextCompat
import androidx.recyclerview.widget.RecyclerView
import com.bumptech.glide.Glide
import com.bumptech.glide.load.engine.DiskCacheStrategy
import com.hrms.kiosk.R
import com.hrms.kiosk.data.model.AttendanceLogItem
import com.hrms.kiosk.databinding.ItemEmployeeTodayLogBinding

/**
 * Adapter hiển thị toàn bộ các ca chấm công trong ngày của riêng nhân viên đang được nhận diện (Cột 1)
 */
class EmployeeTodayLogAdapter(
    private var baseUrl: String,
    private val items: MutableList<AttendanceLogItem> = mutableListOf()
) : RecyclerView.Adapter<EmployeeTodayLogAdapter.ShiftViewHolder>() {

    fun updateBaseUrl(newBaseUrl: String) {
        this.baseUrl = newBaseUrl
    }

    fun submitList(newItems: List<AttendanceLogItem>) {
        items.clear()
        items.addAll(newItems)
        notifyDataSetChanged()
    }

    fun clear() {
        items.clear()
        notifyDataSetChanged()
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ShiftViewHolder {
        val binding = ItemEmployeeTodayLogBinding.inflate(
            LayoutInflater.from(parent.context), parent, false
        )
        return ShiftViewHolder(binding)
    }

    override fun onBindViewHolder(holder: ShiftViewHolder, position: Int) {
        holder.bind(items[position], position, items.size)
    }

    override fun getItemCount(): Int = items.size

    inner class ShiftViewHolder(private val binding: ItemEmployeeTodayLogBinding) :
        RecyclerView.ViewHolder(binding.root) {

        fun bind(item: AttendanceLogItem, index: Int, total: Int) {
            val context = binding.root.context
            val isLatest = (index == 0)
            val seqNumber = total - index

            binding.tvShiftSeq.text = "#$seqNumber"

            val timeStr = item.time ?: ""
            val timeDisplay = if (timeStr.contains(" ")) timeStr.substringAfterLast(" ") else timeStr
            binding.tvShiftTime.text = timeDisplay.ifEmpty { "--:--" }

            val camName = item.cam ?: "TABLET KIOSK"
            binding.tvShiftCam.text = camName

            binding.tvShiftLatestTag.visibility = if (isLatest) View.VISIBLE else View.GONE

            val camUpper = camName.uppercase()
            val statusUpper = (item.status ?: "").uppercase()
            val isShiftIn = camUpper.contains("VÀO") || statusUpper.contains("VÀO")
            val isShiftOut = camUpper.contains("TAN") || camUpper.contains("RA") || statusUpper.contains("TAN")

            when {
                isShiftIn -> {
                    binding.tvShiftBadge.text = "Vào ca"
                    binding.tvShiftBadge.setBackgroundColor(ContextCompat.getColor(context, R.color.shift_in))
                }
                isShiftOut -> {
                    binding.tvShiftBadge.text = "Tan ca"
                    binding.tvShiftBadge.setBackgroundColor(ContextCompat.getColor(context, R.color.shift_out))
                }
                else -> {
                    binding.tvShiftBadge.text = "Điểm danh"
                    binding.tvShiftBadge.setBackgroundColor(ContextCompat.getColor(context, R.color.shift_auto))
                }
            }

            // Nạp ảnh chụp camera thời điểm chấm
            val cleanBase = baseUrl.removeSuffix("/")
            val code = item.code ?: ""
            val snapUrl = when {
                !item.snapshot.isNullOrEmpty() -> "$cleanBase/snapshots/${item.snapshot}"
                !item.avatar.isNullOrEmpty() -> "$cleanBase/api_faces/${item.avatar}"
                code.isNotEmpty() -> "$cleanBase/api_faces/$code.jpg"
                else -> ""
            }

            Glide.with(context)
                .load(snapUrl)
                .diskCacheStrategy(DiskCacheStrategy.ALL)
                .placeholder(R.mipmap.ic_launcher_round)
                .error(R.mipmap.ic_launcher_round)
                .into(binding.imgShiftThumb)
        }
    }
}
