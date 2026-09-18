<template>
  <div class="page">
    <a-page-header :title="`添加${label}关键词订阅`" :subtitle="`使用 Redfox 持续采集匹配关键词的${contentName}`" :show-back="true" @back="router.push(`/${platform}/feeds`)" />
    <a-card>
      <a-alert type="info" class="notice">{{ notice }}</a-alert>
      <a-form :model="form" layout="vertical" @submit="createKeyword">
        <a-form-item label="搜索关键词" required><a-input v-model="form.target" :placeholder="placeholder" allow-clear /></a-form-item>
        <a-form-item label="显示名称（可不填，默认使用关键词）"><a-input v-model="form.name" /></a-form-item>
        <a-form-item label="每次最大抓取条数"><a-input-number v-model="form.max_fetch_count" :min="1" :max="200" /></a-form-item>
        <a-form-item label="刷新间隔（小时）"><a-input-number v-model="form.refresh_interval_hours" :min="1" :max="168" /></a-form-item>
        <a-button type="primary" html-type="submit" :loading="creating">订阅</a-button>
      </a-form>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Message } from '@arco-design/web-vue'
import { createForeignFeed, type ForeignPlatform } from '@/api/foreign'

const props = defineProps<{
  platform: ForeignPlatform
  label: string
  contentName: string
  notice: string
  placeholder: string
}>()
const router = useRouter()
const creating = ref(false)
const form = reactive({ target:'', name:'', max_fetch_count:20, refresh_interval_hours:6 })
const createKeyword = async () => {
  if (!form.target.trim()) return Message.warning('请输入关键词')
  creating.value = true
  try {
    await createForeignFeed(props.platform, { kind:'keyword', target:form.target.trim(), name:form.name.trim() || undefined, max_fetch_count:form.max_fetch_count, refresh_interval_hours:form.refresh_interval_hours })
    Message.success(`已订阅，${props.label}首次采集已提交`)
    router.push(`/${props.platform}/feeds`)
  } catch (error:any) { Message.error(error?.message || String(error) || '订阅失败') }
  finally { creating.value = false }
}
</script>

<style scoped>
.page { padding:20px; max-width:760px; margin:0 auto; }
.notice { margin-bottom:20px; }
</style>
