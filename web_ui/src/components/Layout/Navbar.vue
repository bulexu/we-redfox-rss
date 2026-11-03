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
      <a-menu-item key="/douyin/feeds">
        <template #icon><icon-tiktok-color /></template>
        抖音
      </a-menu-item>
      <a-menu-item key="/bilibili/feeds">
        <template #icon><icon-play-circle /></template>
        B 站
      </a-menu-item>
      <a-menu-item key="/x/feeds">
        <template #icon><icon-twitter /></template>
        X
      </a-menu-item>
      <a-menu-item key="/tiktok/feeds">
        <template #icon><icon-tiktok-color /></template>
        TikTok
      </a-menu-item>
      <a-menu-item key="/youtube/feeds">
        <template #icon><icon-play-circle /></template>
        YouTube
      </a-menu-item>
      <a-menu-item key="/instagram/feeds">
        <template #icon><icon-camera /></template>
        Instagram
      </a-menu-item>
    </a-sub-menu>

    <!-- ========== 任务监控 (跨平台的任务/规则/日志; 点击切到第一项) ========== -->
    <a-menu-item key="task">
      任务监控
    </a-menu-item>

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

// 「任务监控」一级菜单对应的子路径前缀。
// 包含: 导出记录、标签管理、消息任务、过滤规则、任务队列、Redfox 日志、飞书多维表。
const taskPrefixes = [
  '/feedops/exports',
  '/feedops/tags',
  '/feedops/message-tasks',
  '/feedops/filter-rules',
  '/feedops/task-queue',
  '/redfox/logs',
  '/feedops/lark/bitables',
]

// 「系统管理」对应的子路径前缀 (移走 Redfox 日志、飞书多维表后剩下的部分)。
const systemPrefixes = [
  '/access-keys',
  '/users',
  '/configs',
  '/sys-info',
]

// 根据当前路由判断顶部菜单高亮:
//   命中 task 前缀 → 「任务监控」高亮; 命中 system 前缀 → 「系统管理」高亮;
//   WeChat (默认 `/`) / XHS → 「平台选择」高亮 (走默认)。
const selectedTopKeys = computed<string[]>(() => {
  if (taskPrefixes.some((p) => route.path.startsWith(p))) {
    return ['task']
  }
  if (systemPrefixes.some((p) => route.path.startsWith(p))) {
    return ['system']
  }
  // WeChat (默认 `/`) / XHS → 「平台选择」高亮
  return ['platform']
})

const handleMenuClick = (key: string) => {
  if (key === 'task') {
    // 「任务监控」无默认 home 路由,  跳到第一项
    router.push('/feedops/exports').catch((err) => {
      if (!err.message?.includes('Avoided redundant navigation')) {
        console.error('路由导航失败:', err)
      }
    })
    return
  }
  if (key === 'system') {
    // 「系统管理」无默认 home 路由,  跳到第一个系统项
    router.push('/access-keys').catch((err) => {
      if (!err.message?.includes('Avoided redundant navigation')) {
        console.error('路由导航失败:', err)
      }
    })
    return
  }
  // 「平台选择」下拉里的平台路由都以 / 开头。
  if (!key.startsWith('/')) return
  if (route.path === key) return
  router.push(key).catch((err) => {
    if (!err.message?.includes('Avoided redundant navigation')) {
      console.error('路由导航失败:', err)
    }
  })
}
</script>
