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

    /** tap 坐标下发：云侧把选中节点解析为 x/y 中心坐标塞进 params，端侧优先按此坐标点击。
     *  x 或 y 缺失/非法返回 null，调用方回退 match_text 子串匹配。 */
    fun tapPointFromParams(params: Map<String, String>): Pair<Float, Float>? {
        val x = params["x"]?.toFloatOrNull()
        val y = params["y"]?.toFloatOrNull()
        if (x == null || y == null) return null
        return x to y
    }

    /** 默认上滑：屏�水平居中，从下方 80% 滑到 30%。 */
    fun defaultSwipeUp(width: Int, height: Int): Swipe {
        val x = width / 2f
        return Swipe(startX = x, startY = height * 0.8f, endX = x, endY = height * 0.3f)
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