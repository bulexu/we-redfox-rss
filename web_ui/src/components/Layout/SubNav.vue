<template>
  <div v-if="visible" class="sub-nav">
    <a-menu
      mode="horizontal"
      :selected-keys="selectedKeys"
      @menu-item-click="handleClick"
    >
      <a-menu-item v-for="item in items" :key="item.key">
        <template v-if="item.icon" #icon>
          <component :is="item.icon" />
        </template>
        {{ item.label }}
      </a-menu-item>
    </a-menu>
  </div>
</template>

<script setup lang="ts">
import { computed, type Component } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import {
  IconHome,
  IconExport,
  IconTag,
  IconNotification,
  IconFilter,
  IconList,
  IconStorage,
  IconShareExternal,
  IconExclamationCircle,
  IconLock,
  IconUser,
  IconSafe,
  IconSettings,
  IconInfoCircle,
  IconPlus,
} from '@arco-design/web-vue/es/icon'

interface SubItem {
  key: string
  label: string
  icon?: Component
}

// 微信公众号 (默认平台) 的二级菜单 — 仅保留订阅/级联/异常相关。
// 任务监控相关项 (导出记录/标签/消息任务/过滤规则/任务队列) 已上移到一级菜单。
// 「添加订阅」与小红书一致, 便于跨平台交互统一。
const wechatItems: SubItem[] = [
  { key: '/', label: '订阅管理', icon: IconHome },
  { key: '/add-subscription', label: '添加订阅', icon: IconPlus },
  { key: '/cascade/feed-status', label: '信源状态', icon: IconStorage },
  { key: '/cascade', label: '级联管理', icon: IconShareExternal },
  { key: '/env-exception', label: '异常统计', icon: IconExclamationCircle },
]

// 小红书 (XHS) 二级菜单
// /xhs/articles 已合并到 /xhs/feeds 的右侧面板, 二级菜单只保留入口与添加
const xhsItems: SubItem[] = [
  { key: '/xhs/feeds', label: '订阅管理', icon: IconHome },
  { key: '/xhs/subscriptions', label: '添加订阅', icon: IconPlus },
]

// 任务监控二级菜单 (跨平台共用的任务/规则/日志)。
// 集合了原 WeChat 子菜单的 导出记录/标签/消息任务/过滤规则/任务队列,
// 以及原系统菜单的 Redfox 日志/飞书多维表。
// Redfox 日志放最后,  与平台级日志阅读习惯一致 (高频监控项在前, 诊断日志在后)。
const taskItems: SubItem[] = [
  { key: '/feedops/exports', label: '导出记录', icon: IconExport },
  { key: '/feedops/tags', label: '标签管理', icon: IconTag },
  { key: '/feedops/message-tasks', label: '消息任务', icon: IconNotification },
  { key: '/feedops/filter-rules', label: '过滤规则', icon: IconFilter },
  { key: '/feedops/task-queue', label: '任务队列', icon: IconList },
  { key: '/feedops/lark/bitables', label: '飞书多维表', icon: IconStorage },
  { key: '/redfox/logs', label: 'Redfox 日志', icon: IconSafe },
]

// 系统管理的二级菜单 (移走 Redfox 日志/飞书多维表后剩下的)。
const systemItems: SubItem[] = [
  { key: '/access-keys', label: 'Access Key', icon: IconLock },
  { key: '/users', label: '用户管理', icon: IconUser },
  { key: '/configs', label: '配置信息', icon: IconSettings },
  { key: '/sys-info', label: '系统信息', icon: IconInfoCircle },
]

// 任务监控对应的路径前缀
const taskPrefixes = [
  '/feedops/exports',
  '/feedops/tags',
  '/feedops/message-tasks',
  '/feedops/filter-rules',
  '/feedops/task-queue',
  '/redfox/logs',
  '/feedops/lark/bitables',
]

// 系统管理对应的路径前缀
const systemPrefixes = [
  '/access-keys',
  '/users',
  '/configs',
  '/sys-info',
]

// 不展示 sub-nav 的路径 (登录 / 找回密码 / 阅读器 / 修改密码等)
const hidePrefixes = [
  '/login',
  '/forgot-password',
  '/reader',
  '/change-password',
  '/edit-user',
]

const router = useRouter()
const route = useRoute()

// 按当前路径切换显示的二级菜单:
//   task*  → 任务监控;  system*  → 系统管理;  /xhs* → 小红书;  其它 → 微信公众号。
const items = computed<SubItem[]>(() => {
  if (taskPrefixes.some((p) => route.path.startsWith(p))) {
    return taskItems
  }
  if (systemPrefixes.some((p) => route.path.startsWith(p))) {
    return systemItems
  }
  if (route.path.startsWith('/xhs')) {
    return xhsItems
  }
  return wechatItems
})

const visible = computed(() => {
  return !hidePrefixes.some((p) => route.path.startsWith(p))
})

const selectedKeys = computed<string[]>(() => [route.path])

const handleClick = (key: string) => {
  if (route.path === key) return
  router.push(key).catch((err) => {
    if (!err.message?.includes('Avoided redundant navigation')) {
      console.error('路由导航失败:', err)
    }
  })
}
</script>

<style scoped>
.sub-nav {
  background: var(--color-bg-2, #fff);
  border-bottom: 1px solid var(--color-border-2, #e5e6eb);
}
.sub-nav :deep(.arco-menu) {
  padding: 0 16px;
}
</style>