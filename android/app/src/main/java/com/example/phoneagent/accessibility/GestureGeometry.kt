package com.example.phoneagent.accessibility

data class Swipe(
    val startX: Float,
    val startY: Float,
    val endX: Float,
    val endY: Float,
)

/** 纯几何计算，无 framework 依赖，可单测。 */
object GestureGeometry {

    /** bounds = [left, top, right, bottom] → 中心点 (cx, cy)。 */
    fun centerOf(bounds: List<Int>): Pair<Float, Float> {
        val cx = (bounds[0] + bounds[2]) / 2f
        val cy = (bounds[1] + bounds[3]) / 2f
        return cx to cy
    }

    /** bounds = [left, top, right, bottom],判断点 (x, y) 是否落在 bounds 内(含边缘)。 */
    fun pointInBounds(bounds: List<Int>, x: Float, y: Float): Boolean {
        return x >= bounds[0] && x <= bounds[2] && y >= bounds[1] && y <= bounds[3]
    }

    /** tap_at 逃生舱坐标解析:x 或 y 缺失/非法返回 null。 */
    fun tapPointFromParams(params: Map<String, String>): Pair<Float, Float>? {
        val x = params["x"]?.toFloatOrNull()
        val y = params["y"]?.toFloatOrNull()
        if (x == null || y == null) return null
        return x to y
    }

    /** 默认上滑：屏水平居中，从下方 80% 滑到 30%。 */
    fun defaultSwipeUp(width: Int, height: Int): Swipe {
        val x = width / 2f
        return Swipe(startX = x, startY = height * 0.8f, endX = x, endY = height * 0.3f)
    }

    /**
     * 语义 direction → 具体轨迹。
     *
     * 约定与云端一致(protocol/models.py::Swipe.direction):
     * - left  : 内容向左移动 = 手指从右向左划 = 桌面 pager 翻到下一页(右侧页)
     * - right : 内容向右移动 = 手指从左向右划 = 桌面 pager 翻到上一页(左侧页)
     * - up    : 内容向上移动 = 手指从下往上划 = 列表向下滚
     * - down  : 内容向下移动 = 手指从上往下划 = 列表向上滚
     *
     * 水平方向留 15%/85% 的边距,避免起点落在系统全屏手势敏感区,同时给桌面
     * pager 足够的位移量识别为翻页(过短会被识别为「拒绝」抖动回原页)。
     * unknown 或大小写异常 → null,交由调用方回落 defaultSwipeUp。
     */
    fun fromDirection(direction: String?, width: Int, height: Int): Swipe? {
        if (direction.isNullOrBlank()) return null
        val w = width.toFloat()
        val h = height.toFloat()
        val midX = w / 2f
        val midY = h / 2f
        return when (direction.lowercase()) {
            "left"  -> Swipe(startX = w * 0.85f, startY = midY, endX = w * 0.15f, endY = midY)
            "right" -> Swipe(startX = w * 0.15f, startY = midY, endX = w * 0.85f, endY = midY)
            "up"    -> Swipe(startX = midX, startY = h * 0.80f, endX = midX, endY = h * 0.20f)
            "down"  -> Swipe(startX = midX, startY = h * 0.20f, endX = midX, endY = h * 0.80f)
            else    -> null
        }
    }

    /** 从 params 读 x1,y1,x2,y2；任一缺失返回 null。 */
    fun fromParams(params: Map<String, String>): Swipe? {
        val x1 = params["x1"]?.toFloatOrNull()
        val y1 = params["y1"]?.toFloatOrNull()
        val x2 = params["x2"]?.toFloatOrNull()
        val y2 = params["y2"]?.toFloatOrNull()
        if (x1 == null || y1 == null || x2 == null || y2 == null) return null
        return Swipe(x1, y1, x2, y2)
    }
}