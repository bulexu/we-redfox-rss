<template>
  <div class="xhs-articles">
    <a-page-header
      :title="`小红书笔记: ${feedLabel}`"
      :show-back="true"
      @back="goBack"
    >
      <template #subtitle>
        <a-space>
          <a-tag v-if="feedInfo" :color="feedInfo.kind === 'keyword' ? 'arcoblue' : 'green'">
            {{ feedInfo.kind === 'keyword' ? '关键词' : '账号' }}
          </a-tag>
          <a-tag v-if="feedInfo">{{ feedInfo.target }}</a-tag>
          <a-tag v-if="feedInfo" :color="feedInfo.status ? 'green' : 'red'">
            {{ feedInfo.status ? '已启用' : '已禁用' }}
          </a-tag>
        </a-space>
      </template>
    </a-page-header>

    <a-card>
      <a-table
        :columns="columns"
        :data="articles"
        :pagination="pagination"
        @page-change="handlePageChange"
      >
        <template #title="{ record }">
          <a :href="record.url" target="_blank" rel="noopener" class="article-link">
            {{ record.title || '(无标题)' }}
          </a>
        </template>
        <template #cover="{ record }">
          <a-image
            v-if="record.pic_url"
            :src="record.pic_url"
            :width="60"
            :height="60"
            fit="cover"
          />
          <span v-else class="muted">—</span>
        </template>
        <template #author="{ record }">
          <a-space size="mini">
            <span>{{ record.author || '—' }}</span>
          </a-space>
        </template>
        <template #publish_time="{ record }">
          <span class="muted">{{ formatTime(record.publish_time) }}</span>
        </template>
        <template #metrics="{ record }">
          <a-tooltip
            :content="`❤ ${record.liked_count} · 💬 ${record.comments_count} · ⭐ ${record.collected_count} · 📖 ${record.read_count} · 🔁 ${record.share_count}`"
          >
            <a-space size="mini">
              <span>❤ {{ record.liked_count }}</span>
              <span>💬 {{ record.comments_count }}</span>
            </a-space>
          </a-tooltip>
        </template>
        <template #content="{ record }">
          <div class="content-preview">{{ truncate(record.content, 80) }}</div>
        </template>
      </a-table>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { Message } from '@arco-design/web-vue'
import { listXhsFeedArticles, getXhsFeed, type XhsArticle, type XhsFeed } from '@/api/xhs'

const router = useRouter()
const route = useRoute()

const feedId = computed(() => (route.query.feed_id as string) || '')
const feedInfo = ref<XhsFeed | null>(null)
const feedLabel = computed(() => feedInfo.value?.name || feedId.value || '未选择 feed')

const articles = ref<XhsArticle[]>([])
const pagination = reactive({ current: 1, pageSize: 20, total: 0 })

const columns = [
  { title: '标题', slotName: 'title', ellipsis: true, width: 280 },
  { title: '封面', slotName: 'cover', width: 80 },
  { title: '作者', slotName: 'author', width: 160 },
  { title: '互动', slotName: 'metrics', width: 160 },
  { title: '发布时间', slotName: 'publish_time', width: 160 },
  { title: '内容预览', slotName: 'content' },
]

const formatTime = (ts: number) => {
  if (!ts) return '—'
  return new Date(ts * 1000).toLocaleString('zh-CN')
}

const truncate = (s: string, n: number) => {
  if (!s) return ''
  s = s.trim().replace(/\s+/g, ' ')
  return s.length > n ? s.slice(0, n - 1) + '…' : s
}

const loadFeedInfo = async () => {
  if (!feedId.value) return
  try {
    const res = await getXhsFeed(feedId.value)
    if (res.code === 0) {
      feedInfo.value = res.data
    } else {
      throw new Error(res.message || '获取订阅信息失败')
    }
  } catch (err: any) {
    Message.error(err.message || '获取订阅信息失败')
  }
}

const loadArticles = async () => {
  if (!feedId.value) {
    Message.warning('请提供 feed_id 参数')
    return
  }
  try {
    const res = await listXhsFeedArticles(feedId.value, {
      page: pagination.current - 1,
      pageSize: pagination.pageSize,
    })
    if (res.code === 0) {
      articles.value = res.data.list || []
      pagination.total = res.data.total || 0
    } else {
      throw new Error(res.message || '获取笔记失败')
    }
  } catch (err: any) {
    Message.error(err.message || '获取笔记失败')
  }
}

const handlePageChange = (page: number) => {
  pagination.current = page
  loadArticles()
}

const goBack = () => router.push('/xhs/feeds')

watch(
  () => feedId.value,
  () => {
    pagination.current = 1
    loadFeedInfo()
    loadArticles()
  },
)

onMounted(() => {
  loadFeedInfo()
  loadArticles()
})
</script>

<style scoped>
.xhs-articles {
  padding: 20px;
}
.article-link {
  color: var(--color-text-1);
}
.article-link:hover {
  color: rgb(var(--arcoblue-6));
}
.muted {
  color: var(--color-text-4);
}
.content-preview {
  color: var(--color-text-3);
  font-size: 12px;
  line-height: 1.5;
}
</style>
