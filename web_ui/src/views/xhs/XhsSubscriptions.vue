<template>
  <div class="xhs-subscriptions">
    <a-page-header
      title="添加小红书订阅"
      subtitle="按关键词或账号订阅小红书笔记"
      :show-back="true"
      @back="goBack"
    />

    <a-tabs v-model:active-key="activeTab" type="rounded">
      <!-- 关键词订阅 -->
      <a-tab-pane key="keyword" title="关键词">
        <a-card>
          <a-form :model="kwForm" layout="vertical" @submit="handleCreateKeyword">
            <a-form-item label="搜索关键词" field="target" required>
              <a-input
                v-model="kwForm.target"
                placeholder="例如: 口红色号 / 露营装备"
                allow-clear
                :max-length="200"
              />
            </a-form-item>
            <a-form-item label="显示名称 (留空则用关键词)" field="name">
              <a-input v-model="kwForm.name" :max-length="200" />
            </a-form-item>
            <a-form-item label="每次最大抓取条数" field="max_fetch_count">
              <a-input-number v-model="kwForm.max_fetch_count" :min="1" :max="200" />
            </a-form-item>
            <a-form-item label="刷新间隔 (小时)" field="refresh_interval_hours">
              <a-input-number v-model="kwForm.refresh_interval_hours" :min="1" :max="168" />
            </a-form-item>
            <a-form-item>
              <a-space>
                <a-button type="primary" html-type="submit" :loading="loading">订阅</a-button>
                <a-button @click="resetKw">重置</a-button>
              </a-space>
            </a-form-item>
          </a-form>
        </a-card>
      </a-tab-pane>

      <!-- 账号订阅 (先搜索 userId 再订阅) -->
      <a-tab-pane key="account" title="账号">
        <a-card>
          <a-form :model="userSearch" layout="inline" @submit="handleSearchUser">
            <a-form-item label="搜索昵称 / 关键词" field="keyword">
              <a-input
                v-model="userSearch.keyword"
                placeholder="输入昵称搜索"
                allow-clear
                style="width: 280px"
              />
            </a-form-item>
            <a-form-item>
              <a-button type="primary" html-type="submit" :loading="searching">搜索</a-button>
            </a-form-item>
          </a-form>

          <a-divider />

          <a-table
            v-if="userResults.length"
            :columns="userColumns"
            :data="userResults"
            :pagination="false"
          >
            <template #avatar="{ record }">
              <a-avatar :size="32">
                <img v-if="record.accountAvatar || record.avatar || record.image" :src="record.accountAvatar || record.avatar || record.image" />
              </a-avatar>
            </template>
            <template #userId="{ record }">
              <span class="target-text">{{ record.accountId || record.userId || record.user_id || record.id }}</span>
            </template>
            <template #action="{ record }">
              <a-button
                size="mini"
                type="primary"
                @click="subscribeUser(record)"
                :loading="subTarget === (record.accountId || record.userId || record.user_id || record.id)"
              >
                订阅
              </a-button>
            </template>
          </a-table>
          <a-empty v-else-if="searched" description="未找到匹配用户" />
        </a-card>
      </a-tab-pane>
    </a-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { Message } from '@arco-design/web-vue'
import { createXhsFeed, searchXhsUsers, type XhsUser } from '@/api/xhs'

const router = useRouter()

const activeTab = ref<'keyword' | 'account'>('keyword')

// ===== 关键词订阅 =====
const loading = ref(false)
const kwForm = reactive({
  target: '',
  name: '',
  max_fetch_count: 20,
  refresh_interval_hours: 6,
})

const resetKw = () => {
  kwForm.target = ''
  kwForm.name = ''
  kwForm.max_fetch_count = 20
  kwForm.refresh_interval_hours = 6
}

const handleCreateKeyword = async () => {
  if (!kwForm.target.trim()) {
    Message.warning('请输入关键词')
    return
  }
  loading.value = true
  try {
    const res = await createXhsFeed({
      kind: 'keyword',
      target: kwForm.target.trim(),
      name: kwForm.name.trim() || undefined,
      max_fetch_count: kwForm.max_fetch_count,
      refresh_interval_hours: kwForm.refresh_interval_hours,
    })
    Message.success('已订阅, 首次采集已提交')
    router.push('/xhs/feeds')
  } catch (err: any) {
    Message.error(err.message || '订阅失败')
  } finally {
    loading.value = false
  }
}

// ===== 账号订阅 =====
const searching = ref(false)
const searched = ref(false)
const userSearch = reactive({ keyword: '' })
const userResults = ref<XhsUser[]>([])
const subTarget = ref<string | null>(null)

const userColumns = [
  { title: '头像', slotName: 'avatar', width: 80 },
  { title: '昵称', dataIndex: 'accountName' },
  { title: 'userId', slotName: 'userId' },
  { title: '操作', slotName: 'action', width: 100 },
]

const handleSearchUser = async () => {
  if (!userSearch.keyword.trim()) {
    Message.warning('请输入搜索关键词')
    return
  }
  searching.value = true
  searched.value = false
  try {
    const res = await searchXhsUsers(userSearch.keyword.trim())
    userResults.value = res.list || []
    searched.value = true
  } catch (err: any) {
    Message.error(err.message || '搜索失败')
  } finally {
    searching.value = false
  }
}

const subscribeUser = async (record: XhsUser) => {
  const userId = record.accountId || record.userId || record.user_id || record.id
  if (!userId) {
    Message.error('用户记录缺少 userId')
    return
  }
  subTarget.value = String(userId)
  try {
    const res = await createXhsFeed({
      kind: 'account',
      target: String(userId),
      name: record.accountName || record.nickname || undefined,
      avatar: record.accountAvatar || record.avatar || record.image || undefined,
    })
    Message.success('已订阅')
    router.push('/xhs/feeds')
  } catch (err: any) {
    Message.error(err.message || '订阅失败')
  } finally {
    subTarget.value = null
  }
}

const goBack = () => router.push('/xhs/feeds')
</script>

<style scoped>
.xhs-subscriptions {
  padding: 20px;
  max-width: 960px;
  margin: 0 auto;
}
.target-text {
  font-family: monospace;
  color: var(--color-text-2);
}
</style>
