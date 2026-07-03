package com.example.phoneagent.protocol

import org.junit.Assert.assertTrue
import org.junit.Test

class MessagesTest {
    @Test
    fun actionToJson_containsTypeAndOp() {
        val a = DownAction(actionId = "a1", op = "tap", params = mapOf("match_text" to "通讯录"))
        val json = a.toJson()
        assertTrue(json.contains("\"type\":\"action\""))
        assertTrue(json.contains("\"op\":\"tap\""))
    }
}