package com.example.phoneagent.protocol

import java.io.File
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * 双端契约测试:与 server/tests/test_contract.py 共用 shared/protocol/v2 下的 golden JSON 样本。
 *
 * golden 目录定位:优先读环境变量 PROJECT_ROOT(指向仓库根);
 * 否则从 user.dir(gradle 单测 workdir 通常是 android/app)逐级上溯,
 * 直到找到 shared/protocol/v2 目录。两种方式都不依赖固定相对深度。
 *
 * 注:new_message.json(event.newMessage)是 server-only 事件,端侧无对应模型,此处不覆盖。
 */
class ContractTest {

    // 契约测试专用实例:ignoreUnknownKeys = false,golden 中出现模型没有的字段时直接抛异常,
    // 防止 golden 与模型漂移被静默吞掉。生产 Json(WsDispatcher/AppModule)保持 ignoreUnknownKeys = true 不动。
    private val json = Json { ignoreUnknownKeys = false; encodeDefaults = true }

    private val goldenDir: File by lazy {
        val envRoot = System.getenv("PROJECT_ROOT")
        if (!envRoot.isNullOrBlank() && File(envRoot, "shared/protocol/v2").isDirectory) {
            File(envRoot, "shared/protocol/v2")
        } else {
            var dir = File(System.getProperty("user.dir")).absoluteFile
            while (!File(dir, "shared/protocol/v2").isDirectory) {
                dir = dir.parentFile
                    ?: error("cannot locate shared/protocol/v2 from ${System.getProperty("user.dir")}")
            }
            File(dir, "shared/protocol/v2")
        }
    }

    private fun golden(name: String): String = File(goldenDir, name).readText()

    // ---- 上行 ----

    @Test
    fun golden_perception_deserializes() {
        val p = json.decodeFromString<UplinkPerception>(golden("perception.json"))

        assertEquals("perception", p.type)
        assertEquals(42, p.seq)
        assertTrue(p.seq > 0)
        assertEquals("com.ss.android.lark", p.pkg)
        assertEquals(".MainActivity", p.activity)
        assertEquals(2, p.nodeTree.size)
        val editable = p.nodeTree[0]
        assertTrue(editable.editable)
        assertEquals(listOf(10, 20, 300, 80), editable.bounds)
        assertFalse(p.nodeTree[1].editable)
    }

    @Test
    fun golden_action_result_deserializes() {
        val raw = golden("action_result.json")
        assertFalse(raw.contains("atEnd"))
        val r = json.decodeFromString<UplinkActionResult>(raw)

        assertEquals("action.result", r.type)
        assertEquals("act-0007", r.actionId)
        assertFalse(r.ok)
        assertEquals("node_not_found", r.error)
        assertEquals(43, r.seq)
    }

    @Test
    fun uplinkActionResult_serialization_omits_atEnd() {
        val out = json.encodeToString(
            UplinkActionResult(actionId = "act-0007", ok = false, error = "node_not_found", ts = 1750300000100L, seq = 43)
        )

        assertFalse(out.contains("atEnd"))
        assertTrue(out.contains("\"seq\":43"))
    }

    @Test
    fun golden_heartbeat_deserializes() {
        val hb = json.decodeFromString<UplinkHeartbeat>(golden("heartbeat.json"))

        assertEquals("heartbeat", hb.type)
        assertEquals("pixel-7-pro-01", hb.deviceId)
        assertEquals(1750300000300L, hb.ts)
    }

    @Test
    fun golden_task_request_deserializes() {
        val req = json.decodeFromString<UplinkTaskRequest>(golden("task_request.json"))

        assertEquals("task.request", req.type)
        assertEquals("给张三发一条飞书消息:周报已提交", req.goal)
    }

    @Test
    fun golden_confirm_response_deserializes() {
        val resp = json.decodeFromString<UplinkConfirmResponse>(golden("confirm_response.json"))

        assertEquals("task.confirm_response", resp.type)
        assertEquals("task-20260720-001", resp.taskId)
        assertEquals("cfm-0001", resp.confirmId)
        assertTrue(resp.approved)
    }

    @Test
    fun golden_sample_capture_deserializes() {
        val sc = json.decodeFromString<UplinkSampleCapture>(golden("sample_capture.json"))

        assertEquals("sample.capture", sc.type)
        assertEquals("lark_chat_page", sc.label)
        assertEquals(2, sc.nodeTree.size)
        assertTrue(sc.nodeTree[0].editable)
        assertEquals("pixel-7-pro-01", sc.device)
    }

    // ---- 下行 ----

    @Test
    fun golden_task_start_deserializes() {
        val ts = json.decodeFromString<DownTaskStart>(golden("task_start.json"))

        assertEquals("task.start", ts.type)
        assertEquals("task-20260720-001", ts.taskId)
        assertEquals("给张三发一条飞书消息:周报已提交", ts.goal)
        assertEquals("张三", ts.target)
    }

    @Test
    fun golden_action_deserializes_params_all_strings() {
        val raw = golden("action.json")
        val action = json.decodeFromString<DownAction>(raw)

        assertEquals("action", action.type)
        assertEquals("act-0001", action.actionId)
        assertEquals("input", action.op)
        assertEquals("消息输入框", action.params["match_text"])
        assertEquals("周报已提交", action.params["text"])
        assertEquals("0", action.params["index"])
    }

    @Test
    fun golden_task_done_deserializes() {
        val done = json.decodeFromString<DownTaskDone>(golden("task_done.json"))

        assertEquals("task.done", done.type)
        assertEquals("task-20260720-001", done.taskId)
        assertEquals("消息已发送给张三", done.result)
        assertEquals("打开飞书→搜索张三→输入文本→确认→发送", done.summary)
    }

    @Test
    fun golden_task_abort_deserializes() {
        val abort = json.decodeFromString<DownTaskAbort>(golden("task_abort.json"))

        assertEquals("task.abort", abort.type)
        assertEquals("task-20260720-001", abort.taskId)
        assertEquals("user_cancelled", abort.reason)
    }

    @Test
    fun golden_task_confirm_deserializes() {
        val confirm = json.decodeFromString<DownTaskConfirm>(golden("task_confirm.json"))

        assertEquals("task.confirm", confirm.type)
        assertEquals("task-20260720-001", confirm.taskId)
        assertEquals("cfm-0001", confirm.confirmId)
        assertEquals("张三", confirm.target)
        assertEquals("周报已提交", confirm.message)
        assertEquals(5000, confirm.timeoutMs)
    }

    @Test
    fun golden_heartbeat_ack_deserializes() {
        val ack = json.decodeFromString<DownHeartbeatAck>(golden("heartbeat_ack.json"))

        assertEquals("heartbeat.ack", ack.type)
        assertEquals("pixel-7-pro-01", ack.deviceId)
        assertEquals(1750300000600L, ack.ts)
    }
}
