package com.example.phoneagent.accessibility

import org.junit.Assert.assertEquals
import org.junit.Test

class AppTargetTest {

    @Test
    fun package_key_is_treated_as_package_name() {
        val t = AppTarget.fromParams(mapOf("package" to "com.ss.android.lark"))
        assertEquals(AppTarget.ByPackage("com.ss.android.lark"), t)
    }

    @Test
    fun pkg_key_is_treated_as_package_name() {
        val t = AppTarget.fromParams(mapOf("pkg" to "com.ss.android.lark"))
        assertEquals(AppTarget.ByPackage("com.ss.android.lark"), t)
    }

    @Test
    fun app_key_is_treated_as_display_label() {
        val t = AppTarget.fromParams(mapOf("app" to "飞书"))
        assertEquals(AppTarget.ByLabel("飞书"), t)
    }

    @Test
    fun package_takes_priority_over_app() {
        val t = AppTarget.fromParams(mapOf("app" to "飞书", "package" to "com.ss.android.lark"))
        assertEquals(AppTarget.ByPackage("com.ss.android.lark"), t)
    }

    @Test
    fun blank_values_are_ignored() {
        val t = AppTarget.fromParams(mapOf("package" to "", "app" to "飞书"))
        assertEquals(AppTarget.ByLabel("飞书"), t)
    }

    @Test
    fun no_identifier_returns_none() {
        val t = AppTarget.fromParams(mapOf("foo" to "bar"))
        assertEquals(AppTarget.None, t)
    }
}