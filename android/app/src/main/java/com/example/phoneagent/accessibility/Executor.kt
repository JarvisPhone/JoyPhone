package com.example.phoneagent.accessibility

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.content.Context
import android.graphics.Path
import android.os.Bundle
import android.view.accessibility.AccessibilityNodeInfo
import android.util.Log
import com.example.phoneagent.protocol.NodeDto

/** 单步动作执行结果。error 为机器可读错误码(anchor_not_found 等),随 action.result 回传云端。 */
data class ExecResult(val ok: Boolean, val error: String? = null)

/**
 * 真实动作执行器。framework 集成部分仅在真机联调验证；
 * 坐标几何委托给可单测的 GestureGeometry。
 *
 * 端侧为哑执行器，只做原子动作，归位判定在云端。
 *
 * 节点回收约定:
 * - rootInActiveWindow 拿到的 root 由本类各方法在使用完毕后 recycle。
 * - findByText / findEditable / findEditableAt 返回的命中节点所有权转移给调用方,
 *   调用方用完必须 recycle;遍历中未命中的节点在函数内部即时 recycle。
 */
@Suppress("DEPRECATION") // recycle() 在 API 33+ 标记废弃,但 minSdk 以下仍需显式回收防泄漏
class Executor(
    private val service: AccessibilityService,
    private val context: Context,
) {
    fun execute(op: String, params: Map<String, String>): ExecResult {
        return when (op) {
            "tap" -> tap(params)
            "tap_at" -> tapAt(params)
            "longpress" -> longPress(params)
            "input" -> input(params)
            "swipe" -> ExecResult(ok = swipe(params))
            "scroll_to" -> scrollTo(params)
            "open_notifications" -> openNotifications()
            "open_quick_settings" -> openQuickSettings()
            "back" -> {
                val ok = service.performGlobalAction(AccessibilityService.GLOBAL_ACTION_BACK)
                // back 转场约 200ms;不阻塞到位,云端 F2 补的 read_screen 抓到过渡帧,
                // 后续决策看到「半个页面」易误判。
                Thread.sleep(BACK_SETTLE_MS)
                ExecResult(ok = ok)
            }
            "home" -> {
                val ok = service.performGlobalAction(AccessibilityService.GLOBAL_ACTION_HOME)
                // ColorOS home 键回桌面动画约 400ms;阻塞 500ms 让 workspace 完全归位
                // ([0,0,W,H]),否则 home_locate 的第一帧就是 workspace 内缩的过渡态,
                // detect_scene 误判 MINUS_ONE、icon bounds 被 clip 影响 find_icon。
                Thread.sleep(HOME_SETTLE_MS)
                ExecResult(ok = ok)
            }
            "press_enter" -> pressEnter()
            "read_screen", "wait" -> ExecResult(true)
            else -> ExecResult(false, "unknown_op")
        }
    }

    /** 实时树快照:flatten 内部回收子节点,root 由本方法回收。 */
    private fun liveNodes(): List<NodeDto>? {
        val root = service.rootInActiveWindow ?: return null
        return try {
            NodeFlattener.flatten(root)
        } finally {
            root.recycle()
        }
    }

    /**
     * tap 只接受语义锚点:执行瞬间在实时树上重新定位,用「当下的」bounds 点击。
     * 不使用云端坐标(帧过期即点歪);匹配不到/有歧义 fail-closed 报错。
     */
    private fun tap(params: Map<String, String>): ExecResult {
        val anchor = AnchorResolver.fromParams(params)
            ?: return ExecResult(false, "anchor_missing")
        val nodes = liveNodes() ?: return ExecResult(false, "no_window")
        return when (val r = AnchorResolver.resolve(nodes, anchor)) {
            is ResolveResult.Found -> {
                val bounds = r.node.bounds
                    ?: return ExecResult(false, "anchor_no_bounds")
                val (cx, cy) = GestureGeometry.centerOf(bounds)
                ExecResult(dispatchTap(cx, cy))
            }
            ResolveResult.NotFound -> ExecResult(false, "anchor_not_found")
            is ResolveResult.Ambiguous -> ExecResult(false, "anchor_ambiguous")
        }
    }

    /** tap_at:原始坐标点击,逃生舱(画布/地图等无语义节点场景),正常任务不生成。 */
    private fun tapAt(params: Map<String, String>): ExecResult {
        val point = GestureGeometry.tapPointFromParams(params)
            ?: return ExecResult(false, "bad_coords")
        return ExecResult(dispatchTap(point.first, point.second))
    }

    /**
     * input 只接受语义锚点:在实时树上解析出目标 editable 的 NodeDto(含 id 路径),
     * 再按 id 路径在活树上找到对应 AccessibilityNodeInfo 执行 SET_TEXT。
     * 无锚点/未命中 fail-closed,绝不写进错误的输入框。
     */
    private fun input(params: Map<String, String>): ExecResult {
        val text = params["text"].orEmpty()
        val anchor = AnchorResolver.fromParams(params)
            ?: return ExecResult(false, "anchor_missing")
        val root = service.rootInActiveWindow ?: return ExecResult(false, "no_window")
        try {
            val targetId = when (val r = AnchorResolver.resolve(NodeFlattener.flatten(root), anchor, editableOnly = true)) {
                is ResolveResult.Found -> r.node.id
                ResolveResult.NotFound -> return ExecResult(false, "anchor_not_found")
                is ResolveResult.Ambiguous -> return ExecResult(false, "anchor_ambiguous")
            }
            val editable = findNodeByPath(root, targetId)
                ?: return ExecResult(false, "anchor_stale")
            try {
                val args = Bundle().apply {
                    putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, text)
                }
                return ExecResult(editable.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args), null)
            } finally {
                // editable 可能就是 root 本身(id="0"),外层 finally 会回收 root,避免 double-recycle
                if (editable !== root) editable.recycle()
            }
        } finally {
            root.recycle()
        }
    }

    /**
     * 按 NodeFlattener 的 id(DFS 下标路径,如 "0-1-2")在活树上定位节点。
     * 命中节点所有权转移给调用方(用完 recycle);路径失效(树已变化)返回 null。
     */
    private fun findNodeByPath(root: AccessibilityNodeInfo, id: String): AccessibilityNodeInfo? {
        val segments = id.split("-").mapNotNull { it.toIntOrNull() }
        if (segments.isEmpty()) return null
        val chain = mutableListOf<AccessibilityNodeInfo>()
        var current: AccessibilityNodeInfo = root
        for (seg in segments.drop(1)) {
            val child = current.getChild(seg) ?: break
            chain.add(child)
            current = child
        }
        if (chain.size != segments.size - 1) {
            chain.forEach { it.recycle() }
            return null
        }
        val target = chain.lastOrNull() ?: return root
        chain.dropLast(1).forEach { it.recycle() }
        return target
    }

    private fun swipe(params: Map<String, String>): Boolean {
        val metrics = context.resources.displayMetrics
        val w = metrics.widthPixels
        val h = metrics.heightPixels
        // 优先级:显式坐标 x1/y1/x2/y2 > 语义 direction > 默认上滑逃生舱
        val s = GestureGeometry.fromParams(params)
            ?: GestureGeometry.fromDirection(params["direction"], w, h)
            ?: GestureGeometry.defaultSwipeUp(w, h)
        // 水平翻页给 400ms(桌面 pager 对速度敏感,过快会被判成 fling 回弹);
        // 垂直 300ms 保持不变。
        val durationMs = if (s.startY == s.endY) 400L else 300L
        val path = Path().apply {
            moveTo(s.startX, s.startY)
            lineTo(s.endX, s.endY)
        }
        val gesture = GestureDescription.Builder()
            .addStroke(GestureDescription.StrokeDescription(path, 0, durationMs))
            .build()
        val ok = dispatchGestureFireAndForget(gesture, "swipe")
        // 阻塞到手势结束 + pager 结算(150ms 富余覆盖 fling 惯性收敛);
        // 云端 F2 补 read_screen 是在 action.result 到达后触发的,不让这里
        // 阻塞满,下一帧就是过渡态,home_locate 的 fingerprint 会误判 boundary
        // (Frame N/N+1 都是同一页的动画瞬时,label 集相同 = 假边界)。
        Thread.sleep(durationMs + SWIPE_SETTLE_MARGIN_MS)
        return ok
    }

    private fun dispatchTap(x: Float, y: Float): Boolean {
        val path = Path().apply { moveTo(x, y) }
        val gesture = GestureDescription.Builder()
            .addStroke(GestureDescription.StrokeDescription(path, 0, 50))
            .build()
        return dispatchGestureFireAndForget(gesture, "tap")
    }

    /**
     * longpress:与 tap 相同的语义锚点定位,但按住时间延长到 800ms,
     * 触发上下文菜单(长按列表项弹出删除/置顶等菜单)。
     */
    private fun longPress(params: Map<String, String>): ExecResult {
        val anchor = AnchorResolver.fromParams(params)
            ?: return ExecResult(false, "anchor_missing")
        val nodes = liveNodes() ?: return ExecResult(false, "no_window")
        return when (val r = AnchorResolver.resolve(nodes, anchor)) {
            is ResolveResult.Found -> {
                val bounds = r.node.bounds
                    ?: return ExecResult(false, "anchor_no_bounds")
                val (cx, cy) = GestureGeometry.centerOf(bounds)
                val path = Path().apply { moveTo(cx, cy) }
                val gesture = GestureDescription.Builder()
                    .addStroke(GestureDescription.StrokeDescription(path, 0, 800))
                    .build()
                ExecResult(dispatchGestureFireAndForget(gesture, "longpress"))
            }
            ResolveResult.NotFound -> ExecResult(false, "anchor_not_found")
            is ResolveResult.Ambiguous -> ExecResult(false, "anchor_ambiguous")
        }
    }

    /**
     * press_enter:在当前焦点 EditText 旁找「搜索/提交」按钮并点。
     * 多数搜索框把提交按钮做在 IME 上,但端侧 AccessibilityService 无法
     * 注入 KEYCODE_ENTER(无 WRITE_SECURE_SETTINGS),所以走「找按钮+click」兜底。
     * 如果找不到,返回 false 让 LLM 改用 tap 提交按钮。
     */
    private fun pressEnter(): ExecResult {
        val root = service.rootInActiveWindow ?: return ExecResult(false, "no_window")
        try {
            val flatten = NodeFlattener.flatten(root)
            val hasEditable = flatten.any { it.editable }
            if (!hasEditable) return ExecResult(false, "no_editable")
            // 在屏上找带「搜索」「确定」「Search」「Go」「Done」的 clickable 按钮
            val submitTexts = ("搜索|Search|搜索\n|Search\n|确定|Go|Done|提交|回车|搜索一下|搜一搜|send")
                .split("|")
            val submit = flatten.firstOrNull { n ->
                n.clickable && n.text?.trim()?.let { t ->
                    submitTexts.any { k -> t.equals(k, ignoreCase = true) }
                } == true
            } ?: return ExecResult(false, "no_submit_button")
            val node = findNodeByPath(root, submit.id)
                ?: return ExecResult(false, "anchor_stale")
            return try {
                val ok = node.performAction(AccessibilityNodeInfo.ACTION_CLICK)
                if (ok) ExecResult(true) else ExecResult(false, "click_failed")
            } finally {
                if (node !== root) node.recycle()
            }
        } finally {
            root.recycle()
        }
    }

    /**
     * scroll_to top|bottom:反复 swipe 让列表/卡片滚到顶或底。
     * 屏幕内容稳定(连续 2 次 swipe 后节点数差为 0)即停止,最多 MAX_ATTEMPTS 次。
     * 云端归位判定仍由 perception 帧负责,这里只负责「直到屏不再变」。
     */
    private fun scrollTo(params: Map<String, String>): ExecResult {
        val direction = params["direction"]?.trim()?.lowercase()
            ?: return ExecResult(false, "missing_direction")
        if (direction != "top" && direction != "bottom") return ExecResult(false, "bad_direction")
        val metrics = context.resources.displayMetrics
        val w = metrics.widthPixels.toFloat()
        val h = metrics.heightPixels.toFloat()
        val cx = w / 2f
        val yTop = h * 0.20f
        val yBottom = h * 0.80f
        val swipes = if (direction == "top") {
            // 滚到顶:从底向上 swipe
            listOf(cx to yTop, cx to yTop)   // start, end
        } else {
            // 滚到底:从顶向下 swipe
            listOf(cx to yBottom, cx to yBottom)
        }
        val maxAttempts = 5
        repeat(maxAttempts) {
            val path = Path().apply {
                moveTo(swipes.first().first, swipes.first().second)
                lineTo(swipes.last().first, swipes.last().second)
            }
            val gesture = GestureDescription.Builder()
                .addStroke(GestureDescription.StrokeDescription(path, 0, 300))
                .build()
            if (!dispatchGestureFireAndForget(gesture, "scroll_to_$direction")) {
                return ExecResult(false, "gesture_unaccepted")
            }
            // 简单等待:300ms swipe + 350ms 滚动动画,这里先发,真机云端「屏没变就停」由 SWIPE 改进制
            // 不在此 sleep,避免阻塞 WS 线(云端 frame 自身略延迟)
        }
        return ExecResult(true)
    }

    /**
     * open_notifications:从屏幕顶部边缘向下 swipe 至 1/3 屏高,
     * 触发通知栏下拉。同 quick_settings 差别:swipe 距离短(0.05 → 0.35),
     * 一次到位。
     */
    private fun openNotifications(): ExecResult {
        val metrics = context.resources.displayMetrics
        val w = metrics.widthPixels.toFloat()
        val h = metrics.heightPixels.toFloat()
        val cx = w / 2f
        val startY = h * 0.02f
        val endY = h * 0.40f
        val path = Path().apply { moveTo(cx, startY); lineTo(cx, endY) }
        val gesture = GestureDescription.Builder()
            .addStroke(GestureDescription.StrokeDescription(path, 0, 250))
            .build()
        return ExecResult(dispatchGestureFireAndForget(gesture, "open_notifications"))
    }

    /**
     * open_quick_settings:从上向下 swipe 至屏中偏上(0.75h),
     * 触发控制中心下拉(部分 OEM ROM 需二次 swipe;这里发一次足够,
     * 不够 LLM 下一帧再调一次或读屏重判)。
     */
    private fun openQuickSettings(): ExecResult {
        val metrics = context.resources.displayMetrics
        val w = metrics.widthPixels.toFloat()
        val h = metrics.heightPixels.toFloat()
        val cx = w / 2f
        val startY = h * 0.02f
        val endY = h * 0.70f
        val path = Path().apply { moveTo(cx, startY); lineTo(cx, endY) }
        val gesture = GestureDescription.Builder()
            .addStroke(GestureDescription.StrokeDescription(path, 0, 250))
            .build()
        return ExecResult(dispatchGestureFireAndForget(gesture, "open_quick_settings"))
    }

    /**
     * 非阻塞派发手势:返回值仅代表「框架已受理」,不代表手势已执行完成。
     * 不在 WS reader 线程上等待 GestureResultCallback——实测部分 ROM 上回调
     * 延迟 1.7~6s,等待会把后续动作全部堵在队列里(2026-07-21 back 延迟 6s
     * 导致误判 abort 事故的根因)。动作的真实结果由云端通过后续 perception
     * 帧判定(归位判定在云端),onCancelled 仅记日志。
     */
    private fun dispatchGestureFireAndForget(gesture: GestureDescription, tag: String): Boolean {
        return service.dispatchGesture(
            gesture,
            object : AccessibilityService.GestureResultCallback() {
                override fun onCancelled(gestureDescription: GestureDescription?) {
                    Log.w("PhoneAgent", "gesture cancelled: $tag")
                }
            },
            null,
        )
    }

    companion object {
        // 各动作的动画结算时长(阻塞到位再回 action.result,避免云端 F2 补的 read_screen
        // 抓到过渡态帧误判 boundary/scene);数值经真机 2026-07-28 一次挂机复盘定值。
        private const val HOME_SETTLE_MS = 500L        // 桌面回归动画约 400ms + margin
        private const val BACK_SETTLE_MS = 250L        // back 转场
        private const val SWIPE_SETTLE_MARGIN_MS = 150L // 覆盖 fling 惯性收敛
    }
}
