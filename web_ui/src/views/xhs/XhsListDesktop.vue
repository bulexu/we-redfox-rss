<template>
  <a-spin :loading="feedLoading" tip="正在加载..." style="width: 100%; height: 100%;">
    <a-layout class="xhs-list">
      <!-- 左侧：订阅列表 -->
      <a-layout-sider :width="300"
        :style="{ background: '#fff', padding: '0', borderRight: '1px solid #eee', display: 'flex', flexDirection: 'column', border: 0 }">
        <a-card :bordered="false" title="小红书订阅"
          :headStyle="{ padding: '12px 16px', borderBottom: '1px solid #eee', background: '#fff', zIndex: 1, border: 0 }">
          <template #extra>
            <a-button type="primary" size="small" @click="goAdd">
              <template #icon><icon-plus /></template>
              订阅
            </a-button>
          </template>
          <div style="display: flex; flex-direction: column; background: #fff">
            <div style="margin-bottom: 12px;">
              <a-input-search
                v-model="feedSearchText"
                placeholder="搜索订阅名称或目标"
                @search="handleFeedSearch"
                @keyup.enter="handleFeedSearch"
                allow-clear
                size="small" />
            </div>
            <div style="margin-bottom: 8px; padding: 0 8px;">
              <a-radio-group v-model="kindFilter" type="button" size="small" style="width: 100%;">
                <a-radio value="" style="flex: 1; text-align: center;">全部</a-radio>
                <a-radio value="keyword" style="flex: 1; text-align: center;">关键词</a-radio>
                <a-radio value="account" style="flex: 1; text-align: center;">账号</a-radio>
              </a-radio-group>
            </div>
            <div style="margin-bottom: 8px; padding: 0 8px;">
              <a-radio-group v-model="statusFilter" type="button" size="small" style="width: 100%;">
                <a-radio :value="undefined" style="flex: 1; text-align: center;">全部</a-radio>
                <a-radio :value="1" style="flex: 1; text-align: center;">启用</a-radio>
                <a-radio :value="0" style="flex: 1; text-align: center;">停用</a-radio>
              </a-radio-group>
            </div>
            <a-list :data="feedList" :loading="feedLoading" bordered>
              <template #item="{ item }">
                <a-popover trigger="hover" position="right"
                  :content-style="{ padding: '12px', minWidth: '240px', maxWidth: '320px' }">
                  <a-list-item @click="handleFeedClick(item.id)"
                    :class="{ 'active-feed': activeFeedId === item.id }"
                    style="padding: 8px 6px; cursor: pointer; display: flex; align-items: center; justify-content: space-between;">
                    <div style="display: flex; align-items: center;">
                      <img :src="Avatar(item.cover) || '/static/logo.svg'" width="32"
                        style="float: left; margin-right: 8px; border-radius: 4px;" />
                      <a-typography-text strong style="line-height: 32px;">
                        {{ truncate(item.name, 12) }}
                      </a-typography-text>
                    </div>
                    <a-tag v-if="canManageFeed(item)" size="mini" :color="item.kind === 'keyword' ? 'arcoblue' : 'green'">
                      {{ item.kind === 'keyword' ? '关键词' : '账号' }}
                    </a-tag>
                  </a-list-item>
                  <template #content>
                    <div style="display: flex; flex-direction: column; gap: 8px;">
                      <div style="display: flex; align-items: center; gap: 8px;">
                        <img :src="Avatar(item.cover) || '/static/logo.svg'" width="32"
                          style="border-radius: 4px;" />
                        <div style="flex: 1;">
                          <div style="font-weight: 600; font-size: 14px;">{{ item.name }}</div>
                          <div style="font-size: 12px; color: var(--color-text-3);"
                            v-if="item.target">目标: {{ item.target }}</div>
                          <div style="font-size: 12px; color: var(--color-text-3);">ID: {{ item.id || '聚合视图' }}</div>
                        </div>
                      </div>
                      <div v-if="item.intro" style="font-size: 12px; color: var(--color-text-2); line-height: 1.5;">
                        {{ item.intro }}
                      </div>
                      <template v-if="canManageFeed(item)">
                        <div v-if="item.error_count > 0" style="font-size: 12px; color: var(--color-danger-6);">
                          最近失败: {{ item.last_error || '无详情' }}
                        </div>
                        <div
                          style="display: flex; gap: 8px; padding-top: 8px; border-top: 1px solid var(--color-border); flex-wrap: wrap;">
                          <a-button size="mini" type="text" @click.stop="editFeedById(item)">
                            <template #icon><icon-edit /></template>
                            编辑
                          </a-button>
                          <a-button size="mini" type="text" @click.stop="copyTarget(item.target)">
                            <template #icon><icon-copy /></template>
                            复制目标
                          </a-button>
                          <a-button size="mini" type="text"
                            :status="item.status ? 'warning' : 'success'"
                            @click.stop="toggleFeedStatus(item)">
                            <template #icon>
                              <icon-stop v-if="item.status === 1" />
                              <icon-play-arrow v-else />
                            </template>
                            {{ item.status === 1 ? '停用' : '启用' }}
                          </a-button>
                          <a-button size="mini" type="text" @click.stop="triggerSyncById(item.id)">
                            <template #icon><icon-refresh /></template>
                            同步
                          </a-button>
                          <a-button size="mini" type="text" status="danger" @click.stop="deleteFeedById(item)">
                            <template #icon><icon-delete /></template>
                            删除
                          </a-button>
                        </div>
                      </template>
                    </div>
                  </template>
                </a-popover>
              </template>
            </a-list>
            <a-pagination :total="feedPagination.total" simple
              @change="handleFeedPageChange" :show-total="true"
              style="margin-top: 1rem;" />
          </div>
        </a-card>
      </a-layout-sider>

      <!-- 右侧：笔记列表 -->
      <a-layout-content style="padding: 20px;">
        <a-page-header
          :title="activeFeed?.name || '全部'"
          :subtitle="activeFeedId === '' ? '显示所有小红书订阅的笔记' : (activeFeed?.target || '')"
          :show-back="false">
          <template #extra>
            <a-space>
              <!-- 聚合视图 -->
              <template v-if="activeFeedId === ''">
                <a-tag color="arcoblue">聚合视图</a-tag>
                <a-tag>共 {{ articlePagination.total }} 条</a-tag>
              </template>
              <!-- 单 feed 视图 -->
              <template v-else>
                <a-tag :color="activeFeed?.kind === 'keyword' ? 'arcoblue' : 'green'">
                  {{ activeFeed?.kind === 'keyword' ? '关键词' : '账号' }}
                </a-tag>
                <a-tag :color="activeFeed?.status ? 'green' : 'red'">
                  {{ activeFeed?.status ? '已启用' : '已禁用' }}
                </a-tag>
                <a-button @click="triggerSync" :loading="syncing">
                  <template #icon><icon-refresh /></template>
                  同步
                </a-button>
                <a-button @click="editFeed">
                  <template #icon><icon-edit /></template>
                  编辑
                </a-button>
                <a-button
                  :status="activeFeed?.status ? 'warning' : 'success'"
                  @click="toggleStatus">
                  <template #icon>
                    <icon-stop v-if="activeFeed?.status === 1" />
                    <icon-play-arrow v-else />
                  </template>
                  {{ activeFeed?.status === 1 ? '禁用' : '启用' }}
                </a-button>
                <a-button status="danger" @click="deleteFeed">
                  <template #icon><icon-delete /></template>
                  删除
                </a-button>
              </template>
            </a-space>
          </template>
        </a-page-header>

        <a-card style="border: 0">
          <a-alert v-if="activeFeed?.intro" type="info" closable>{{ activeFeed.intro }}</a-alert>
          <a-alert v-else-if="activeFeedId === ''" type="success" closable>
            聚合视图: 跨所有小红书订阅展示笔记, 点击左侧具体订阅可查看该订阅下的笔记并执行同步、编辑等操作
          </a-alert>
          <a-alert v-else closable>暂无订阅简介</a-alert>

          <div class="search-bar">
            <a-input-search class="search-input"
              v-model="articleSearchText"
              placeholder="搜索笔记标题或内容"
              @search="handleArticleSearch"
              @keyup.enter="handleArticleSearch"
              allow-clear />
            <a-button @click="refreshArticles" :loading="articleLoading">
              <template #icon><icon-refresh /></template>
              刷新
            </a-button>
          </div>

          <a-table :columns="articleColumns" :data="articles" :loading="articleLoading"
            :pagination="articlePagination"
            :scroll="{ x: '100%' }"
            @page-change="handleArticlePageChange"
            @page-size-change="handleArticlePageSizeChange">
            <template #title="{ record }">
              <a class="article-link" :title="record.title" style="cursor: pointer;"
                @click="viewArticle(record)">
                {{ record.title || '(无标题)' }}
              </a>
            </template>
            <template #cover="{ record }">
              <a-image v-if="record.pic_url" :src="record.pic_url" :width="48" :height="48" fit="cover" />
              <span v-else class="muted">—</span>
            </template>
            <template #author="{ record }">
              <span>{{ record.author || '—' }}</span>
            </template>
            <template #feed_name="{ record }">
              <a-tag size="mini" color="gray">{{ record.feed_name || '—' }}</a-tag>
            </template>
            <template #metrics="{ record }">
              <a-tooltip
                :content="`❤ ${record.liked_count} · 💬 ${record.comments_count} · ⭐ ${record.collected_count} · 📖 ${record.read_count} · 🔁 ${record.share_count}`">
                <a-space size="mini">
                  <span>❤ {{ record.liked_count }}</span>
                  <span>💬 {{ record.comments_count }}</span>
                </a-space>
              </a-tooltip>
            </template>
            <template #publish_time="{ record }">
              <span class="muted">{{ formatTimestamp(record.publish_time) }}</span>
            </template>
            <template #content="{ record }">
              <div class="content-preview">{{ truncate(record.content, 80) }}</div>
            </template>
          </a-table>
        </a-card>
      </a-layout-content>
    </a-layout>
  </a-spin>

  <!-- 编辑订阅模态框 -->
  <a-modal
    v-model:visible="editVisible"
    :title="editTitle"
    :ok-text="'保存'"
    @ok="saveEdit"
    @cancel="editVisible = false">
    <a-form :model="editForm" layout="vertical">
      <a-form-item label="显示名称" field="name">
        <a-input v-model="editForm.name" />
      </a-form-item>
      <a-form-item label="封面 URL" field="cover">
        <a-input v-model="editForm.cover" placeholder="https://..." />
      </a-form-item>
      <a-form-item label="简介" field="intro">
        <a-textarea v-model="editForm.intro" :auto-size="{ minRows: 2, maxRows: 4 }" />
      </a-form-item>
      <a-form-item label="每次最大抓取条数" field="max_fetch_count">
        <a-input-number v-model="editForm.max_fetch_count" :min="1" :max="200" />
      </a-form-item>
      <a-form-item label="刷新间隔 (小时)" field="refresh_interval_hours">
        <a-input-number v-model="editForm.refresh_interval_hours" :min="1" :max="168" />
      </a-form-item>
      <a-form-item label="状态" field="status">
        <a-switch
          :model-value="editForm.status === 1"
          @change="(v: boolean) => (editForm.status = v ? 1 : 0)" />
      </a-form-item>
    </a-form>
  </a-modal>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { Message, Modal } from '@arco-design/web-vue'
import { IconPlus, IconDelete, IconEdit, IconRefresh, IconStop, IconPlayArrow, IconCopy } from '@arco-design/web-vue/es/icon'
import {
  listXhsFeeds,
  updateXhsFeed,
  deleteXhsFeed,
  triggerXhsSync,
  listXhsFeedArticles,
  listXhsArticles,
  type XhsFeed,
  type XhsArticle,
  type XhsKind,
} from '@/api/xhs'
import { Avatar } from '@/utils/constants'
import { formatTimestamp } from '@/utils/date'

const router = useRouter()
const route = useRoute()

// ===== 左侧：订阅列表 =====
const feedList = ref<XhsFeed[]>([])
const feedLoading = ref(false)
const feedSearchText = ref('')
const kindFilter = ref<XhsKind | ''>('')
const statusFilter = ref<number | undefined>(undefined)
const feedPagination = reactive({ current: 1, pageSize: 10, total: 0 })
// activeFeedId === '' 表示聚合“全部」视图 (默认, 与公众号侧一致)
const activeFeedId = ref<string>('')

// 虚拟“全部」订阅项 (仅在默认筛选 + 无搜索时插入)
const ALL_FEED_SENTINEL: XhsFeed = {
  id: '',
  name: '全部',
  cover: '/static/logo.svg',
  intro: '显示所有小红书订阅的笔记',
  status: 1,
  kind: 'keyword',
  target: '',
  max_fetch_count: 0,
  refresh_interval_hours: 0,
  last_publish_time: 0,
  last_cursor: '',
  sync_time: 0,
  error_count: 0,
  last_error: '',
  last_error_at: 0,
  created_at: '',
  updated_at: '',
}

// 虚拟“全部」项不可编辑/同步/删除 (用于 popover 操作按钮、右侧 panel)
const canManageFeed = (item: XhsFeed) => item.id !== ''

const activeFeed = computed<XhsFeed | undefined>(() =>
  feedList.value.find((f) => f.id === activeFeedId.value),
)

const truncate = (s: string, n: number) => {
  if (!s) return ''
  if (s.length <= n) return s
  return s.slice(0, n - 1) + '…'
}

const loadFeeds = async () => {
  feedLoading.value = true
  try {
    const res = await listXhsFeeds({
      kind: kindFilter.value || undefined,
      status: statusFilter.value,
      page: feedPagination.current - 1,
      pageSize: feedPagination.pageSize,
    })
    let list = res.list || []
    // 仅在默认筛选 + 无搜索时插入虚拟“全部」项 (与公众号侧一致)
    if (
      kindFilter.value === '' &&
      statusFilter.value === undefined &&
      !feedSearchText.value.trim()
    ) {
      list = [ALL_FEED_SENTINEL, ...list]
    }
    feedList.value = list
    feedPagination.total = res.total || 0
  } catch (err: any) {
    Message.error(err.message || '获取订阅列表错误')
  } finally {
    feedLoading.value = false
  }
}

const handleFeedSearch = () => {
  feedPagination.current = 1
  loadFeeds()
}

const handleFeedPageChange = (page: number) => {
  feedPagination.current = page
  loadFeeds()
}

watch([kindFilter, statusFilter], () => {
  feedPagination.current = 1
  loadFeeds()
})

const handleFeedClick = (id: string) => {
  activeFeedId.value = id
  articlePagination.current = 1
  articleSearchText.value = ''
  loadArticles()
}

// ===== 右侧：笔记列表 =====
const articles = ref<XhsArticle[]>([])
const articleLoading = ref(false)
const articleSearchText = ref('')
const articlePagination = reactive({ current: 1, pageSize: 20, total: 0 })

// 表格列: 聚合视图 (activeFeedId==='') 时多一列「来源订阅」
interface ArticleColumn {
  title: string
  slotName?: string
  dataIndex?: string
  ellipsis?: boolean
  width?: number
}
// 参考 wechat/ArticleListDesktop.viewArticle: 跳转站内模板页 (/views/article/{id})，
// 不再直接打开小红书外链。模板页已支持 XHS 互动指标 + 订阅源信息卡 (article_detail.html)。
const viewArticle = (record: any) => {
  if (!record?.id) return
  window.open(`/views/article/${record.id}`, '_blank', 'noopener,noreferrer')
}
const articleColumns = computed<ArticleColumn[]>(() => {
  const cols: ArticleColumn[] = [
    { title: '封面', slotName: 'cover', width: 70 },
    { title: '标题', slotName: 'title', ellipsis: true, width: 280 },
    { title: '作者', slotName: 'author', width: 140 },
    { title: '互动', slotName: 'metrics', width: 160 },
    { title: '发布时间', slotName: 'publish_time', width: 160 },
  ]
  if (activeFeedId.value === '') {
    cols.push({ title: '来源订阅', dataIndex: 'feed_name', slotName: 'feed_name', width: 160 })
  }
  cols.push({ title: '内容预览', slotName: 'content' })
  return cols
})

const loadArticles = async () => {
  articleLoading.value = true
  try {
    const req = {
      page: articlePagination.current - 1,
      pageSize: articlePagination.pageSize,
    }
    // 聚合视图 (activeFeedId==='') 走专用接口
    const res = activeFeedId.value === ''
      ? await listXhsArticles(req)
      : await listXhsFeedArticles(activeFeedId.value, req)
    let list = res.list || []
    const kw = articleSearchText.value.trim().toLowerCase()
    if (kw) {
      list = list.filter(
        (a) =>
          (a.title || '').toLowerCase().includes(kw) ||
          (a.content || '').toLowerCase().includes(kw),
      )
    }
    articles.value = list
    articlePagination.total = res.total || 0
  } catch (err: any) {
    Message.error(err.message || '获取笔记失败')
  } finally {
    articleLoading.value = false
  }
}

const handleArticleSearch = () => {
  articlePagination.current = 1
  loadArticles()
}

const handleArticlePageChange = (page: number) => {
  articlePagination.current = page
  loadArticles()
}

const handleArticlePageSizeChange = (pageSize: number) => {
  articlePagination.pageSize = pageSize
  articlePagination.current = 1
  loadArticles()
}

const refreshArticles = () => {
  loadArticles()
}

// ===== 订阅操作 =====
// 编辑：传入 item 时从 popover 触发，传入当前 activeFeed 时从 extra 区触发
const editVisible = ref(false)
const editTitle = ref('编辑订阅')
const editForm = reactive({
  id: '',
  name: '',
  cover: '',
  intro: '',
  max_fetch_count: 20,
  refresh_interval_hours: 6,
  status: 1,
})

const fillEditForm = (rec: XhsFeed) => {
  editTitle.value = `编辑: ${rec.target}`
  Object.assign(editForm, {
    id: rec.id,
    name: rec.name,
    cover: rec.cover,
    intro: rec.intro,
    max_fetch_count: rec.max_fetch_count,
    refresh_interval_hours: rec.refresh_interval_hours,
    status: rec.status,
  })
  editVisible.value = true
}

const editFeedById = (item: XhsFeed) => fillEditForm(item)
const editFeed = () => {
  if (!activeFeed.value) return
  fillEditForm(activeFeed.value)
}

const saveEdit = async () => {
  try {
    const res = await updateXhsFeed(editForm.id, {
      name: editForm.name,
      avatar: editForm.cover,
      intro: editForm.intro,
      max_fetch_count: editForm.max_fetch_count,
      refresh_interval_hours: editForm.refresh_interval_hours,
      status: editForm.status,
    })
    Message.success('已保存')
    editVisible.value = false
    // 当前 feed 编辑后保持选中, 刷新列表更新本地数据
    await loadFeeds()
  } catch (err: any) {
    Message.error(err.message || '保存失败')
  }
}

const toggleFeedStatus = async (rec: XhsFeed) => {
  const next = rec.status ? 0 : 1
  try {
    await updateXhsFeed(rec.id, { status: next })
    Message.success(next ? '已启用' : '已禁用')
    await loadFeeds()
  } catch (err: any) {
    Message.error(err.message || '操作失败')
  }
}

const toggleStatus = () => {
  if (!activeFeed.value) return
  toggleFeedStatus(activeFeed.value)
}

const syncing = ref(false)
const doTriggerSync = async (feedId: string) => {
  syncing.value = true
  try {
    const res = await triggerXhsSync(feedId)
    Message.success('已提交同步任务')
  } catch (err: any) {
    Message.error(err.message || '提交同步失败')
  } finally {
    syncing.value = false
  }
}

const triggerSyncById = (id: string) => doTriggerSync(id)
const triggerSync = () => {
  if (!activeFeedId.value) return
  doTriggerSync(activeFeedId.value)
}

const deleteFeedById = (item: XhsFeed) => {
  Modal.confirm({
    title: '删除订阅',
    content: `确定删除 ${item.target} 吗? 将同时清理该订阅下的所有笔记。`,
    okText: '删除',
    cancelText: '取消',
    okButtonProps: { status: 'danger' },
    onOk: async () => {
      try {
        const res = await deleteXhsFeed(item.id)
        Message.success('已删除')
        // 如果删除的是当前选中的 feed，清空右侧
        if (activeFeedId.value === item.id) {
          activeFeedId.value = ''
          articles.value = []
          articlePagination.total = 0
        }
        await loadFeeds()
      } catch (err: any) {
        Message.error(err.message || '删除失败')
      }
    },
  })
}

const deleteFeed = () => {
  if (!activeFeed.value) return
  deleteFeedById(activeFeed.value)
}

const copyTarget = async (target: string) => {
  if (!target) {
    Message.warning('目标为空')
    return
  }
  try {
    await navigator.clipboard.writeText(target)
    Message.success('已复制目标到剪贴板')
  } catch (err) {
    // 回退方案
    const ta = document.createElement('textarea')
    ta.value = target
    ta.style.position = 'fixed'
    ta.style.left = '-999999px'
    document.body.appendChild(ta)
    ta.select()
    try {
      document.execCommand('copy')
      Message.success('已复制目标到剪贴板')
    } catch (e) {
      Message.error('复制失败，请手动复制')
    }
    document.body.removeChild(ta)
  }
}

// ===== 导航 =====
const goAdd = () => router.push('/xhs/subscriptions')

// ===== URL 同步 =====
// 监听 ?feed_id=xxx: 支持直接以 /xhs/feeds?feed_id=xxx 打开
watch(
  () => route.query.feed_id,
  (v) => {
    if (v && typeof v === 'string' && v !== activeFeedId.value) {
      activeFeedId.value = v
      articlePagination.current = 1
      articleSearchText.value = ''
      loadArticles()
    }
  },
  { immediate: false },
)

onMounted(async () => {
  await loadFeeds()
  // 如果 URL 带 feed_id, 等列表加载完成后尝试选中
  const q = route.query.feed_id
  if (q && typeof q === 'string' && feedList.value.some((f) => f.id === q)) {
    activeFeedId.value = q
  }
  // 默认 activeFeedId='' (聚合视图), 总是加载笔记列表
  await loadArticles()
})
</script>

<style scoped>
.xhs-list {
  width: 100%;
  height: 100%;
  overflow: hidden;
}

.xhs-list :deep(.arco-layout) {
  display: flex;
  width: 100%;
  height: 100%;
}

.xhs-list :deep(.arco-layout-sider) {
  flex-shrink: 0;
  overflow: hidden;
}

.xhs-list :deep(.arco-layout-content) {
  flex: 1;
  min-width: 0;
  overflow: auto;
  box-sizing: border-box;
}

.active-feed {
  background-color: var(--color-primary-light-1);
}

.search-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 20px;
}

.search-input {
  flex: 1;
  min-width: 200px;
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

:deep(.arco-table-th-item) {
  justify-content: center;
}

:deep(.arco-table) {
  width: 100% !important;
}

:deep(.arco-table-container) {
  width: 100% !important;
  overflow-x: auto;
}

:deep(.arco-card) {
  width: 100%;
  box-sizing: border-box;
}
</style>