<template>
  <a-menu
    mode="horizontal"
    :selected-keys="selectedTopKeys"
    @menu-item-click="handleMenuClick"
  >
    <!-- ========== 平台选择 (下拉选择器) ========== -->
    <a-sub-menu key="platform">
      <template #title>平台选择</template>
      <a-menu-item key="/">
        <template #icon><icon-wechat /></template>
        微信公众号
      </a-menu-item>
      <a-menu-item key="/xhs/feeds">
        <template #icon><icon-fire /></template>
        小红书
      </a-menu-item>
      <a-menu-item key="platform-douyin" disabled>
        <template #icon><icon-tiktok-color /></template>
        抖音
      </a-menu-item>
      <a-menu-item key="platform-bilibili" disabled>
        <template #icon><icon-play-circle /></template>
        B 站
      </a-menu-item>
    </a-sub-menu>

    <!-- ========== 系统管理 (点击切到第一个系统项) ========== -->
    <a-menu-item key="system">
      系统管理
    </a-menu-item>
  </a-menu>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'

const router = useRouter()
const route = useRoute()

// 根据当前路由判断顶部菜单高亮:
//   命中 WeChat/XHS 路径 → 「平台选择」高亮;  命中 System 路径 → 「系统管理」高亮
const systemPrefixes = [
  '/access-keys',
  '/users',
  '/redfox',
  '/configs',
  '/lark',
  '/sys-info',
]

const selectedTopKeys = computed<string[]>(() => {
  if (systemPrefixes.some((p) => route.path.startsWith(p))) {
    return ['system']
  }
  // WeChat/XHS 路径或默认 → 「平台选择」高亮
  return ['platform']
})

const handleMenuClick = (key: string) => {
  if (key === 'system') {
    // 「系统管理」无默认 home 路由,  跳到第一个系统项
    router.push('/access-keys').catch((err) => {
      if (!err.message?.includes('Avoided redundant navigation')) {
        console.error('路由导航失败:', err)
      }
    })
    return
  }
  // 「平台选择」下拉里只处理 WeChat / XHS key (其它 key 是 disabled,  Arco 不会触发)
  if (!key.startsWith('/')) return
  if (route.path === key) return
  router.push(key).catch((err) => {
    if (!err.message?.includes('Avoided redundant navigation')) {
      console.error('路由导航失败:', err)
    }
  })
}
</script>
