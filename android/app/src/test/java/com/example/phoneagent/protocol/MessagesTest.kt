package com.example.phoneagent.protocol

import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class MessagesTest {

    private val json = Json { ignoreUnknownKeys = true; encodeDefaults = true }

    @Test
    fun perception_serializes_with_node_fields() {
        val p = UplinkPerception(
            nodeTree = listOf(
                NodeDto(
                    id = "n1",
                    text = "搜索",
                    desc = "search",
                    className = "android.widget.TextView",
                    bounds = listOf(0, 0, 100, 50),
                    clickable = true,
                    editable = false,
                )
            ),
            pkg = "com.ss.android.lark",
            activity = ".MainActivity",
            ts = 123L,
        )
        val out = json.encodeToString(p)

        assertTrue(out.contains("\"type\":\"perception\""))
        assertTrue(out.contains("\"pkg\":\"com.ss.android.lark\""))
        assertTrue(out.contains("\"bounds\":[0,0,100,50]"))
        assertTrue(out.contains("\"desc\":\"search\""))
    }

    @Test
    fun action_deserializes_from_downlink_json() {
        val raw = """{"type":"action","actionId":"a1","op":"tap","params":{"match_text":"搜索"}}"""
        val action = json.decodeFromString<DownAction>(raw)

        assertEquals("a1", action.actionId)
        assertEquals("tap", action.op)
        assertEquals("搜索", action.params["match_text"])
    }

    @Test
    fun action_deserializes_empty_params() {
        val raw = """{"type":"action","actionId":"a2","op":"read_screen","params":{}}"""
        val action = json.decodeFromString<DownAction>(raw)

        assertEquals("read_screen", action.op)
        assertTrue(action.params.isEmpty())
    }

    @Test
    fun uplinkActionResult_serializes_without_atEnd() {
        val result = UplinkActionResult(actionId = "a1", ok = true, seq = 7, error = null)
        val out = json.encodeToString(result)

        assertTrue(out.contains("\"type\":\"action.result\""))
        assertTrue(out.contains("\"actionId\":\"a1\""))
        assertTrue(out.contains("\"ok\":true"))
        assertTrue(out.contains("\"seq\":7"))
        assertTrue(!out.contains("atEnd"))
    }

    @Test
    fun uplinkActionResult_roundtrip() {
        val result = UplinkActionResult(actionId = "a2", ok = false, seq = 3, error = "node_not_found")
        val decoded = json.decodeFromString<UplinkActionResult>(json.encodeToString(result))

        assertEquals(result, decoded)
    }

    @Test
    fun heartbeat_ack_deserializes_from_downlink_json() {
        val raw = """{"type":"heartbeat.ack","deviceId":"dev-1","ts":456}"""
        val ack = json.decodeFromString<DownHeartbeatAck>(raw)

        assertEquals("heartbeat.ack", ack.type)
        assertEquals("dev-1", ack.deviceId)
        assertEquals(456L, ack.ts)
    }

    @Test
    fun task_request_serializes_with_goal() {
        val req = UplinkTaskRequest(goal = "帮我完成一件事")
        val out = json.encodeToString(req)

        assertTrue(out.contains("\"type\":\"task.request\""))
        assertTrue(out.contains("\"goal\":\"帮我完成一件事\""))
    }
}