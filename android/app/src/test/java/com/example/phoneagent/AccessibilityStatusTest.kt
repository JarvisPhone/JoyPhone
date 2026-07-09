package com.example.phoneagent

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class AccessibilityStatusTest {

    private val target = "com.example.phoneagent/com.example.phoneagent.accessibility.PhoneAgentService"

    @Test
    fun enabled_when_setting_contains_component() {
        val setting = "com.other/foo:$target"
        assertTrue(AccessibilityStatus.isEnabled(setting, target))
    }

    @Test
    fun enabled_when_only_component() {
        assertTrue(AccessibilityStatus.isEnabled(target, target))
    }

    @Test
    fun disabled_when_setting_null() {
        assertFalse(AccessibilityStatus.isEnabled(null, target))
    }

    @Test
    fun disabled_when_component_absent() {
        assertFalse(AccessibilityStatus.isEnabled("com.other/foo:com.bar/baz", target))
    }
}