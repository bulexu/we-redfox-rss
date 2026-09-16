<template>
  <a-watermark :content="appTitle"
  :alpha="0.1"
  :rotate="-22"
  :anti-tamper="true"
   >
    <!-- 一级入口(平台选择 / 系统管理) 已在 App.vue header 渲染;
         此处只承载 main 区域:  二级菜单 + 页面内容 -->
    <a-layout>
      <SubNav />
      <a-layout-content>
        <router-view />
      </a-layout-content>
    </a-layout>
  </a-watermark>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import SubNav from './SubNav.vue'

const appTitle = computed(() => {
  const ip = window.location.hostname
  return `${import.meta.env.VITE_APP_COPYRIGHT || 'Power By Rachel Design'}@${ip}`
})
</script>
