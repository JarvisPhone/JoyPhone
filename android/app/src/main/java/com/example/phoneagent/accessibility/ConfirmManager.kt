package com.example.phoneagent.accessibility

import com.example.phoneagent.protocol.DownTaskConfirm

/**
 * Toast 确认窗口状态管理:持有 pending confirm,负责超时自动 approved=true。
 * 取消(onTaskEnd/onDestroy)即真实清理,无标志位。
 */
class ConfirmManager(
    private val sendResponse: (taskId: String, confirmId: String, approved: Boolean, reason: String) -> Unit,
    private val postDelayed: (Runnable, Long) -> Unit,
    private val removeCallbacks: (Runnable) -> Unit,
    private val onTrace: ((String) -> Unit)? = null,
) {
    private var pendingConfirm: DownTaskConfirm? = null

    private val timeoutRunnable = Runnable {
        val pending = pendingConfirm
        if (pending != null) {
            pendingConfirm = null
            sendResponse(pending.taskId, pending.confirmId, true, "toast_timeout_auto_confirm")
            onTrace?.invoke("approved=true(toast_timeout)")
        }
    }

    fun onConfirm(confirm: DownTaskConfirm) {
        pendingConfirm = confirm
        removeCallbacks(timeoutRunnable)
        postDelayed(timeoutRunnable, confirm.timeoutMs.toLong())
    }

    fun onTaskEnd() = clear()

    fun onDestroy() = clear()

    private fun clear() {
        removeCallbacks(timeoutRunnable)
        pendingConfirm = null
    }
}
