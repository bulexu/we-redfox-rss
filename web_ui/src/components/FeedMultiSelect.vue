<script setup lang="ts">
/**
 * 跨平台 Feed 多选器 —— ``MpMultiSelect`` 的替代品。
 *
 * 与旧组件 API 完全兼容 (v-model 双向绑定的元素类型是 ``FeedItem``,
 * 对外暴露 ``parseSelected``), 但内部:
 *   * 调 ``/feeds`` (新增, 跨平台), 不再调 ``/mps``
 *   * 顶部有平台 tabs: 全部 / 公众号 / 小红书
 *   * 每个选项带 platform 徽标 + 可选的 target 提示
 *
 * 调用方升级: ``import FeedMultiSelect from '@/components/FeedMultiSelect.vue'``,
 * 把 ``MpItem[]`` 替换成 ``FeedItem[]``。
 */
import { ref, computed, onMounted } from 'vue'
import { Message } from '@arco-design/web-vue'
import http from '@/api/http'
import type { MpItem } from '@/types/subscription'

/** Feed 选项 — 兼容旧 MpItem 字段, 多两个跨平台用字段 (platform, target)。 */
export interface FeedItem extends MpItem {
  platform?: 'mp' | 'xhs' | 'unknown'
  target?: string
}

const props = defineProps({
  modelValue: {
    type: Array as () => FeedItem[],
    default: () => []
  }
})

const emit = defineEmits(['update:modelValue'])

type Platform = 'all' | 'mp' | 'xhs'

const searchKeyword = ref('')
const loading = ref(false)
const feedList = ref<FeedItem[]>([])
const selectedFeeds = ref<FeedItem[]>([])
const currentOffset = ref(0)
const totalCount = ref(0)
const hasMore = ref(true)
const pageSize = 20
const maxOffset = 100

const currentPlatform = ref<Platform>('all')

const platformTabs: { label: string; value: Platform }[] = [
  { label: '全部', value: 'all' },
  { label: '公众号', value: 'mp' },
  { label: '小红书', value: 'xhs' },
]

const filteredFeeds = computed(() => {
  // 已选中的从候选里去掉 (与旧 MpMultiSelect 行为一致)
  const selectedIds = new Set(selectedFeeds.value.map(s => s.id))
  return feedList.value.filter(f => {
    if (selectedIds.has(f.id)) return false
    // "精选文章" 虚拟 feed 旧版会过滤,这里也保留兼容
    if (f.mp_name === '精选文章') return false
    // 按当前 tab 过滤
    if (currentPlatform.value === 'all') return true
    return f.platform === currentPlatform.value
  })
})

const fetchFeeds = async (reset = true) => {
  loading.value = true
  try {
    if (reset) {
      currentOffset.value = 0
      feedList.value = []
    }

    const params: Record<string, any> = {
      kw: searchKeyword.value,
      offset: currentOffset.value,
      limit: pageSize,
    }
    if (currentPlatform.value !== 'all') {
      params.platform = currentPlatform.value
    }

    const res = await http.get<{ code: number; data: { list: any[]; total: number } }>(
      '/feeds',
      { params }
    )

    const mapped: FeedItem[] = (res.data?.list || []).map((item: any) => ({
      id: item.id,
      mp_name: item.name || item.mp_name || '',
      mp_cover: item.cover || item.mp_cover || item.avatar || '',
      avatar: item.cover || item.avatar || '',
      platform: item.platform || 'unknown',
      target: item.target || '',
    }))

    if (reset) {
      feedList.value = mapped
    } else {
      const newFeeds = mapped.filter(nf => !feedList.value.some(ef => ef.id === nf.id))
      feedList.value = [...feedList.value, ...newFeeds]
    }

    totalCount.value = res.data?.total || 0
    hasMore.value =
      feedList.value.length < totalCount.value && currentOffset.value + pageSize < maxOffset

  } catch (err: any) {
    console.error('fetchFeeds failed:', err)
    Message.error('搜索订阅失败: ' + (err?.message || String(err)))
  } finally {
    loading.value = false
  }
}

const loadMore = async () => {
  currentOffset.value += pageSize
  await fetchFeeds(false)
}

const handleSearch = () => {
  fetchFeeds(true)
}

const onPlatformChange = (val: Platform | string | number | undefined) => {
  // arco a-tabs change 事件 value 类型为 string | number | undefined
  if (val === 'mp' || val === 'xhs' || val === 'all') {
    currentPlatform.value = val
    fetchFeeds(true)
  }
}

const toggleSelect = (feed: FeedItem) => {
  const index = selectedFeeds.value.findIndex(f => f.id === feed.id)
  if (index === -1) {
    selectedFeeds.value.push(feed)
  } else {
    selectedFeeds.value.splice(index, 1)
  }
  emitSelected()
}

const removeSelected = (feed: FeedItem) => {
  selectedFeeds.value = selectedFeeds.value.filter(f => f.id !== feed.id)
  emitSelected()
}

const clearAll = () => {
  selectedFeeds.value = []
  emitSelected()
}

const selectAll = () => {
  filteredFeeds.value.forEach(feed => {
    if (!selectedFeeds.value.some(f => f.id === feed.id)) {
      selectedFeeds.value.push(feed)
    }
  })
  emitSelected()
}

const emitSelected = () => {
  emit('update:modelValue', selectedFeeds.value)
}

const parseSelected = (data: FeedItem[]) => {
  // 后端只给了 id 列表时,用已知列表里的补全; 找不到就用 id 当 name 占位
  selectedFeeds.value = data.map(item => {
    const found = feedList.value.find(f => f.id === item.id)
    return found || { ...item }
  })
}

defineExpose({
  parseSelected
})

const platformBadgeLabel = (p?: string) => {
  if (p === 'mp') return '公众号'
  if (p === 'xhs') return '小红书'
  return ''
}

const platformBadgeColor = (p?: string) => {
  if (p === 'mp') return '#165DFF'
  if (p === 'xhs') return '#F53F3F'
  return '#86909C'
}

onMounted(() => {
  fetchFeeds()
  if (props.modelValue && props.modelValue.length > 0) {
    parseSelected(props.modelValue)
  }
})
</script>

<template>
  <a-card class="feed-multi-select" :bordered="false">
    <a-space direction="vertical" fill>
      <a-tabs
        :active-tab="currentPlatform"
        @tab-click="(k: any) => onPlatformChange(k as Platform)"
      >
        <a-tab-pane
          v-for="t in platformTabs"
          :key="t.value"
          :title="t.label"
        />
      </a-tabs>

      <a-space>
        <a-input
          v-model="searchKeyword"
          placeholder="搜索订阅 (公众号/小红书)"
          allow-clear
          @press-enter="handleSearch"
        />
        <a-button type="primary" @click="handleSearch">搜索</a-button>
      </a-space>

      <a-spin :loading="loading">
        <template v-if="selectedFeeds.length > 0">
          <a-space align="center" class="title-line">
            <h4>已选 ({{ selectedFeeds.length }})</h4>
            <a-button size="mini" type="text" @click="clearAll">清空</a-button>
          </a-space>
          <a-space wrap>
            <a-tag
              v-for="feed in selectedFeeds"
              :key="feed.id"
              closable
              @close="removeSelected(feed)"
            >
              <a-avatar :size="20" :image-url="feed.mp_cover">
                <img v-if="feed.mp_cover" :src="feed.mp_cover" :alt="feed.mp_name" />
              </a-avatar>
              {{ feed.mp_name }}
              <span
                v-if="feed.platform"
                class="platform-badge"
                :style="{ backgroundColor: platformBadgeColor(feed.platform) }"
              >{{ platformBadgeLabel(feed.platform) }}</span>
            </a-tag>
          </a-space>
        </template>

        <a-space align="center" class="title-line">
          <h4>可选订阅</h4>
          <a-button size="mini" type="text" @click="selectAll">全选</a-button>
        </a-space>
        <div class="feed-list">
          <div
            v-for="feed in filteredFeeds"
            :key="feed.id"
            class="feed-item"
            @click="toggleSelect(feed)"
          >
            <a-space>
              <a-avatar :size="24" :image-url="feed.mp_cover">
                <img v-if="feed.mp_cover" :src="feed.mp_cover" :alt="feed.mp_name" />
              </a-avatar>
              <span>{{ feed.mp_name }}</span>
              <span
                v-if="feed.platform"
                class="platform-badge"
                :style="{ backgroundColor: platformBadgeColor(feed.platform) }"
              >{{ platformBadgeLabel(feed.platform) }}</span>
              <a-tag v-if="feed.target" size="small">{{ feed.target }}</a-tag>
            </a-space>
          </div>
        </div>

        <div v-if="hasMore" class="load-more">
          <a-button type="text" @click="loadMore" :loading="loading" :disabled="loading">
            加载更多 ({{ feedList.length }}/{{ totalCount }})
          </a-button>
        </div>
        <div v-else-if="feedList.length > 0" class="load-more no-more">
          已加载全部 {{ totalCount }} 个订阅
        </div>
      </a-spin>
    </a-space>
  </a-card>
</template>

<style scoped>
.feed-multi-select {
  padding: 15px;
}
.title-line {
  width: 100%;
}
h4 {
  margin-bottom: 10px;
  display: block;
  font-size: 14px;
  color: var(--color-text-2);
}

.feed-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.feed-item {
  padding: 6px 12px;
  border-radius: 4px;
  cursor: pointer;
  background-color: var(--color-fill-1);
  border-radius: 2rem;
}
.feed-item:hover {
  background-color: var(--color-fill-2);
}

.platform-badge {
  display: inline-block;
  padding: 0 6px;
  margin-left: 4px;
  font-size: 10px;
  color: #fff;
  border-radius: 8px;
  line-height: 16px;
  vertical-align: middle;
}

.load-more {
  display: flex;
  justify-content: center;
  margin-top: 16px;
}

.no-more {
  color: var(--color-text-3);
  font-size: 12px;
}
</style>