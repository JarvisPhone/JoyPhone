package com.example.phoneagent.net

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class WsClientBackoffTest {

    @Test
    fun backoff_grows_exponentially_from_initial_delay() {
        assertEquals(3000L, WsClient.backoffDelayMs(1))
        assertEquals(6000L, WsClient.backoffDelayMs(2))
        assertEquals(12000L, WsClient.backoffDelayMs(3))
        assertEquals(24000L, WsClient.backoffDelayMs(4))
        assertEquals(48000L, WsClient.backoffDelayMs(5))
    }

    @Test
    fun backoff_caps_at_max_delay() {
        assertEquals(60000L, WsClient.backoffDelayMs(6))
        assertEquals(60000L, WsClient.backoffDelayMs(10))
    }

    @Test
    fun backoff_never_overflows_for_huge_retry_count() {
        // 无限重试下 retryCount 无上限，移位必须封顶、结果必须恒为正且不超上限
        for (count in listOf(64, 100, 1000, Int.MAX_VALUE)) {
            val delay = WsClient.backoffDelayMs(count)
            assertTrue("delay must be positive for count=$count", delay > 0)
            assertTrue("delay must be capped for count=$count", delay <= WsClient.MAX_RETRY_DELAY_MS)
        }
    }

    @Test
    fun backoff_handles_non_positive_count() {
        assertEquals(3000L, WsClient.backoffDelayMs(0))
        assertEquals(3000L, WsClient.backoffDelayMs(-5))
    }
}
