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
}