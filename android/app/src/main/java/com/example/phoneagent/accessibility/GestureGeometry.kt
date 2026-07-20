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

    /** 在一组候选 bounds 中找第一个包含点 (x, y) 的下标；无命中返回 null。
     *  生产路径:Executor.findEditableAt 按 DFS 前序收集 editable bounds 后用它选中命中者。 */
    fun indexOfBoundsContaining(candidates: List<List<Int>>, x: Float, y: Float): Int? {
        return candidates.indexOfFirst { pointInBounds(it, x, y) }.takeIf { it >= 0 }
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