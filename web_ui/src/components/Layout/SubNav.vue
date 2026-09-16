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

// 微信公众号 (默认平台) 的二级菜单 — 与 Navbar.vue 平台选择下的二级菜单保持一致
const wechatItems: SubItem[] = [
  { key: '/', label: '订阅管理', icon: IconHome },
  { key: '/export/records', label: '导出记录', icon: IconExport },
  { key: '/tags', label: '标签管理', icon: IconTag },
  { key: '/message-tasks', label: '消息任务', icon: IconNotification },
  { key: '/filter-rules', label: '过滤规则', icon: IconFilter },
  { key: '/task-queue', label: '任务队列', icon: IconList },
  { key: '/cascade/feed-status', label: '信源状态', icon: IconStorage },
  { key: '/cascade', label: '级联管理', icon: IconShareExternal },
  { key: '/env-exception', label: '异常统计', icon: IconExclamationCircle },
]

// 小红书 (XHS) 二级菜单
const xhsItems: SubItem[] = [
  { key: '/xhs/feeds', label: '订阅管理', icon: IconHome },
  { key: '/xhs/subscriptions', label: '添加订阅', icon: IconPlus },
  { key: '/xhs/articles', label: '笔记浏览', icon: IconList },
]

// 系统管理的二级菜单
const systemItems: SubItem[] = [
  { key: '/access-keys', label: 'Access Key', icon: IconLock },
  { key: '/users', label: '用户管理', icon: IconUser },
  { key: '/redfox/logs', label: 'Redfox 日志', icon: IconSafe },
  { key: '/configs', label: '配置信息', icon: IconSettings },
  { key: '/lark/bitables', label: '飞书多维表', icon: IconStorage },
  { key: '/sys-info', label: '系统信息', icon: IconInfoCircle },
]

const systemPrefixes = [
  '/access-keys',
  '/users',
  '/redfox',
  '/configs',
  '/lark',
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

const items = computed<SubItem[]>(() => {
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
