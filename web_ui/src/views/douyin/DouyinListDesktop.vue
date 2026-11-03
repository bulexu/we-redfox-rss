<template>
  <a-spin :loading="feedLoading" tip="正在加载..." style="width:100%;height:100%">
    <a-layout class="douyin-list">
      <a-layout-sider
        :width="300"
        :style="{ background:'#fff', padding:'0', borderRight:'1px solid #eee', display:'flex', flexDirection:'column', border:0 }"
      >
        <a-card
          :bordered="false"
          title="抖音订阅"
          :head-style="{ padding:'12px 16px', borderBottom:'1px solid #eee', background:'#fff', zIndex:1, border:0 }"
        >
          <template #extra>
            <a-button type="primary" size="small" @click="goAdd">
              <template #icon><icon-plus /></template>订阅
            </a-button>
          </template>

          <div class="feed-panel">
            <a-input-search
              v-model="feedSearchText"
              placeholder="搜索订阅名称或目标"
              allow-clear
              size="small"
              @search="handleFeedSearch"
              @keyup.enter="handleFeedSearch"
            />

            <div class="filter-row">
              <a-radio-group v-model="kindFilter" type="button" size="small" style="width:100%">
                <a-radio value="" class="filter-option">全部</a-radio>
                <a-radio value="keyword" class="filter-option">关键词</a-radio>
              </a-radio-group>
            </div>
            <div class="filter-row">
              <a-radio-group v-model="statusFilter" type="button" size="small" style="width:100%">
                <a-radio :value="undefined" class="filter-option">全部</a-radio>
                <a-radio :value="1" class="filter-option">启用</a-radio>
                <a-radio :value="0" class="filter-option">停用</a-radio>
              </a-radio-group>
            </div>

            <a-list :data="feedList" :loading="feedLoading" bordered>
              <template #item="{ item }">
                <a-popover
                  trigger="hover"
                  position="right"
                  :content-style="{ padding:'12px', minWidth:'240px', maxWidth:'320px' }"
                >
                  <a-list-item
                    :class="{ 'active-feed': activeFeedId === item.id }"
                    class="feed-item"
                    @click="handleFeedClick(item.id)"
                  >
                    <div class="feed-summary">
                      <img :src="Avatar(item.cover) || '/static/logo.svg'" width="32" class="feed-avatar" />
                      <a-typography-text strong>{{ truncate(item.name, 12) }}</a-typography-text>
                    </div>
                    <a-tag v-if="canManageFeed(item)" size="mini" color="arcoblue">关键词</a-tag>
                  </a-list-item>

                  <template #content>
                    <div class="feed-popover">
                      <div class="feed-popover-head">
                        <img :src="Avatar(item.cover) || '/static/logo.svg'" width="32" class="feed-avatar" />
                        <div>
                          <div class="feed-popover-name">{{ item.name }}</div>
                          <div v-if="item.target" class="small-muted">目标：{{ item.target }}</div>
                          <div class="small-muted">ID：{{ item.id || '聚合视图' }}</div>
                        </div>
                      </div>
                      <div v-if="item.intro" class="feed-intro">{{ item.intro }}</div>
                      <template v-if="canManageFeed(item)">
                        <div v-if="item.error_count > 0" class="feed-error">
                          最近失败：{{ item.last_error || '无详情' }}
                        </div>
                        <div class="feed-actions">
                          <a-button size="mini" type="text" @click.stop="editFeedById(item)">
                            <template #icon><icon-edit /></template>编辑
                          </a-button>
                          <a-button size="mini" type="text" @click.stop="copyTarget(item.target)">
                            <template #icon><icon-copy /></template>复制目标
                          </a-button>
                          <a-button
                            size="mini"
                            type="text"
                            :status="item.status ? 'warning' : 'success'"
                            @click.stop="toggleFeedStatus(item)"
                          >{{ item.status ? '停用' : '启用' }}</a-button>
                          <a-button size="mini" type="text" @click.stop="triggerSyncById(item.id)">
                            <template #icon><icon-refresh /></template>同步
                          </a-button>
                          <a-button size="mini" type="text" status="danger" @click.stop="deleteFeedById(item)">
                            <template #icon><icon-delete /></template>删除
                          </a-button>
                        </div>
                      </template>
                    </div>
                  </template>
                </a-popover>
              </template>
            </a-list>

            <a-pagination
              :total="feedPagination.total"
              :page-size="feedPagination.pageSize"
              :current="feedPagination.current"
              simple
              :show-total="true"
              class="feed-pagination"
              @change="handleFeedPageChange"
            />
          </div>
        </a-card>
      </a-layout-sider>

      <a-layout-content class="main-content">
        <a-page-header
          :title="activeFeed?.name || '全部'"
          :subtitle="activeFeedId === '' ? '显示所有抖音订阅的作品' : (activeFeed?.target || '')"
          :show-back="false"
        >
          <template #extra>
            <a-space>
              <template v-if="activeFeedId === ''">
                <a-tag color="arcoblue">聚合视图</a-tag>
                <a-tag>共 {{ articlePagination.total }} 条</a-tag>
              </template>
              <template v-else>
                <a-tag :color="activeFeed?.status ? 'green' : 'red'">
                  {{ activeFeed?.status ? '已启用' : '已禁用' }}
                </a-tag>
              </template>
              <a-dropdown>
                <a-button :disabled="activeFeedId === ''">
                  <template #icon><icon-wifi /></template>订阅<icon-down />
                </a-button>
                <template #content>
                  <a-doption @click="rssFormat='atom';openRssFeed()">ATOM</a-doption>
                  <a-doption @click="rssFormat='rss';openRssFeed()">RSS</a-doption>
                  <a-doption @click="rssFormat='json';openRssFeed()">JSON</a-doption>
                  <a-doption @click="rssFormat='md';openRssFeed()">Markdown</a-doption>
                  <a-doption @click="rssFormat='txt';openRssFeed()">Text</a-doption>
                </template>
              </a-dropdown>
              <a-button
                type="primary"
                status="danger"
                :disabled="!selectedRowKeys.length"
                @click="handleBatchDelete"
              >
                <template #icon><icon-delete /></template>批量删除
              </a-button>
            </a-space>
          </template>
        </a-page-header>

        <a-card style="border:0">
          <a-alert v-if="activeFeed?.intro" type="info" closable>{{ activeFeed.intro }}</a-alert>
          <a-alert v-else-if="activeFeedId === ''" type="success" closable>
            聚合视图：跨所有抖音关键词订阅展示作品，点击左侧具体订阅可查看对应作品并执行同步、编辑等操作
          </a-alert>
          <a-alert v-else closable>暂无订阅简介</a-alert>

          <div class="search-bar">
            <a-input-search
              v-model="articleSearchText"
              class="search-input"
              placeholder="搜索作品标题或内容"
              allow-clear
              @search="handleArticleSearch"
              @keyup.enter="handleArticleSearch"
            />
            <a-button
              v-if="activeFeedId"
              type="primary"
              :loading="syncing"
              @click="triggerSyncById(activeFeedId)"
            >
              <template #icon><icon-refresh /></template>同步 Redfox
            </a-button>
            <a-button :loading="articleLoading" @click="refreshArticles">
              <template #icon><icon-refresh /></template>刷新列表
            </a-button>
          </div>

          <a-table
            :columns="articleColumns"
            :data="articles"
            :loading="articleLoading"
            :pagination="articlePagination"
            :row-selection="{
              type:'checkbox', showCheckedAll:true, width:50, fixed:true,
              checkStrictly:true, onlyCurrent:false
            }"
            row-key="id"
            v-model:selected-keys="selectedRowKeys"
            @page-change="handleArticlePageChange"
            @page-size-change="handleArticlePageSizeChange"
          >
            <template #cover="{ record }">
              <a-image v-if="record.pic_url" :src="record.pic_url" :width="48" :height="48" fit="cover" />
              <span v-else class="muted">—</span>
            </template>
            <template #title="{ record }">
              <a class="article-link" :title="record.title" @click="viewArticle(record)">
                {{ record.title || truncate(record.content || record.description, 60) || '(无标题)' }}
              </a>
            </template>
            <template #author="{ record }">{{ record.author || '—' }}</template>
            <template #metrics="{ record }">
              <a-tooltip :content="`❤ ${record.liked_count||0} · 💬 ${record.comments_count||0} · ⭐ ${record.collected_count||0} · ▶ ${record.read_count||0} · 🔁 ${record.share_count||0}`">
                <a-space size="mini">
                  <span>❤ {{ record.liked_count || 0 }}</span>
                  <span>💬 {{ record.comments_count || 0 }}</span>
                </a-space>
              </a-tooltip>
            </template>
            <template #publish_time="{ record }">
              <span class="muted">{{ formatTimestamp(record.publish_time) }}</span>
            </template>
            <template #feed_name="{ record }">
              <a-tag size="mini" color="gray">{{ record.feed_name || '—' }}</a-tag>
            </template>
            <template #content="{ record }">
              <div class="content-preview">{{ truncate(record.content || record.description, 80) }}</div>
            </template>
          </a-table>
        </a-card>
      </a-layout-content>
    </a-layout>
  </a-spin>

  <a-modal v-model:visible="editVisible" :title="editTitle" ok-text="保存" @ok="saveEdit">
    <a-form :model="editForm" layout="vertical">
      <a-form-item label="显示名称"><a-input v-model="editForm.name" /></a-form-item>
      <a-form-item label="封面 URL"><a-input v-model="editForm.cover" placeholder="https://..." /></a-form-item>
      <a-form-item label="简介">
        <a-textarea v-model="editForm.intro" :auto-size="{ minRows:2, maxRows:4 }" />
      </a-form-item>
      <a-form-item label="每次最大抓取条数">
        <a-input-number v-model="editForm.max_fetch_count" :min="1" :max="200" />
      </a-form-item>
      <a-form-item label="刷新间隔（小时）">
        <a-input-number v-model="editForm.refresh_interval_hours" :min="1" :max="168" />
      </a-form-item>
      <a-form-item label="状态">
        <a-switch :model-value="editForm.status===1" @change="(v:boolean)=>(editForm.status=v?1:0)" />
      </a-form-item>
    </a-form>
  </a-modal>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Message, Modal } from '@arco-design/web-vue'
import { IconCopy, IconDelete, IconEdit, IconPlus, IconRefresh, IconWifi } from '@arco-design/web-vue/es/icon'
import {
  deleteDouyinFeed,
  listDouyinArticles,
  listDouyinFeedArticles,
  listDouyinFeeds,
  triggerDouyinSync,
  updateDouyinFeed,
  type DouyinArticle,
  type DouyinFeed,
} from '@/api/douyin'
import { deleteArticle as deleteArticleApi } from '@/api/article'
import { Avatar } from '@/utils/constants'
import { formatTimestamp } from '@/utils/date'

const router = useRouter()
const route = useRoute()
const feedList = ref<DouyinFeed[]>([])
const feedLoading = ref(false)
const feedSearchText = ref('')
const kindFilter = ref<'' | 'keyword'>('')
const statusFilter = ref<number | undefined>(undefined)
const feedPagination = reactive({ current:1, pageSize:10, total:0 })
const activeFeedId = ref('')

const ALL_FEED_SENTINEL: DouyinFeed = {
  id:'', name:'全部', cover:'/static/logo.svg', intro:'显示所有抖音订阅的作品',
  status:1, kind:'keyword', target:'', max_fetch_count:0, refresh_interval_hours:0,
  last_publish_time:0, last_cursor:'', sync_time:0, error_count:0,
  last_error:'', last_error_at:0, created_at:'', updated_at:'',
}

const canManageFeed = (feed: DouyinFeed) => feed.id !== ''
const activeFeed = computed(() => feedList.value.find((feed) => feed.id === activeFeedId.value))
const truncate = (text: string, length: number) => {
  if (!text) return ''
  return text.length <= length ? text : `${text.slice(0, length - 1)}…`
}

const loadFeeds = async () => {
  feedLoading.value = true
  try {
    const result: any = await listDouyinFeeds({
      status: statusFilter.value,
      kw: feedSearchText.value.trim() || undefined,
      page: feedPagination.current - 1,
      pageSize: feedPagination.pageSize,
    })
    let list: DouyinFeed[] = result.list || []
    if (kindFilter.value === '' && statusFilter.value === undefined && !feedSearchText.value.trim()) {
      list = [ALL_FEED_SENTINEL, ...list]
    }
    feedList.value = list
    feedPagination.total = result.total || 0
  } catch (error: any) {
    Message.error(error?.message || String(error) || '获取订阅列表错误')
  } finally {
    feedLoading.value = false
  }
}

const handleFeedSearch = () => { feedPagination.current = 1; loadFeeds() }
const handleFeedPageChange = (page: number) => { feedPagination.current = page; loadFeeds() }
watch([kindFilter, statusFilter], () => { feedPagination.current = 1; loadFeeds() })

const articles = ref<DouyinArticle[]>([])
const articleLoading = ref(false)
const articleSearchText = ref('')
const articlePagination = reactive({
  current:1, pageSize:20, total:0, showTotal:true, showPageSize:true,
  pageSizeOptions:[10, 20, 50, 100],
})
const selectedRowKeys = ref<string[]>([])
const rssFormat = ref<'rss'|'atom'|'json'|'md'|'txt'>('atom')

interface ArticleColumn { title:string; slotName?:string; dataIndex?:string; ellipsis?:boolean; width?:number }
const articleColumns = computed<ArticleColumn[]>(() => {
  const columns: ArticleColumn[] = [
    { title:'封面', slotName:'cover', width:70 },
    { title:'标题', slotName:'title', ellipsis:true, width:280 },
    { title:'作者', slotName:'author', width:140 },
    { title:'互动', slotName:'metrics', width:160 },
    { title:'发布时间', slotName:'publish_time', width:160 },
  ]
  if (!activeFeedId.value) columns.push({ title:'来源订阅', slotName:'feed_name', width:160 })
  columns.push({ title:'内容预览', slotName:'content' })
  return columns
})

const loadArticles = async () => {
  articleLoading.value = true
  try {
    const params = {
      page: articlePagination.current - 1,
      pageSize: articlePagination.pageSize,
      search: articleSearchText.value.trim() || undefined,
    }
    const result: any = activeFeedId.value
      ? await listDouyinFeedArticles(activeFeedId.value, params)
      : await listDouyinArticles(params)
    articles.value = result.list || []
    articlePagination.total = result.total || 0
  } catch (error: any) {
    Message.error(error?.message || String(error) || '获取作品失败')
  } finally {
    articleLoading.value = false
  }
}

const handleFeedClick = (id: string) => {
  activeFeedId.value = id
  articlePagination.current = 1
  articleSearchText.value = ''
  selectedRowKeys.value = []
  loadArticles()
}
const handleArticleSearch = () => { articlePagination.current = 1; loadArticles() }
const handleArticlePageChange = (page:number) => { articlePagination.current = page; loadArticles() }
const handleArticlePageSizeChange = (size:number) => {
  articlePagination.pageSize = size
  articlePagination.current = 1
  loadArticles()
}
const refreshArticles = () => loadArticles()
const viewArticle = (record: DouyinArticle) => {
  if (record?.id) window.open(`/views/article/${record.id}`, '_blank', 'noopener,noreferrer')
}
const openRssFeed = () => {
  if (activeFeedId.value) window.open(`/feed/${activeFeedId.value}.${rssFormat.value}`, '_blank')
}

const handleBatchDelete = () => {
  if (!selectedRowKeys.value.length) return
  Modal.confirm({
    title:'确认批量删除',
    content:`确定要删除选中的 ${selectedRowKeys.value.length} 个作品吗？删除后无法恢复。`,
    okText:'确认', cancelText:'取消',
    onOk: async () => {
      try {
        await Promise.all(selectedRowKeys.value.map((id) => deleteArticleApi(id)))
        Message.success(`成功删除 ${selectedRowKeys.value.length} 个作品`)
        selectedRowKeys.value = []
        loadArticles()
      } catch { Message.error('删除部分作品失败') }
    },
  })
}

const editVisible = ref(false)
const editTitle = ref('编辑订阅')
const editForm = reactive({
  id:'', name:'', cover:'', intro:'', max_fetch_count:20, refresh_interval_hours:6, status:1,
})
const fillEditForm = (feed: DouyinFeed) => {
  editTitle.value = `编辑：${feed.target}`
  Object.assign(editForm, {
    id:feed.id, name:feed.name, cover:feed.cover, intro:feed.intro,
    max_fetch_count:feed.max_fetch_count, refresh_interval_hours:feed.refresh_interval_hours,
    status:feed.status,
  })
  editVisible.value = true
}
const editFeedById = (feed: DouyinFeed) => fillEditForm(feed)
const saveEdit = async () => {
  try {
    await updateDouyinFeed(editForm.id, {
      name:editForm.name, avatar:editForm.cover, intro:editForm.intro,
      max_fetch_count:editForm.max_fetch_count,
      refresh_interval_hours:editForm.refresh_interval_hours,
      status:editForm.status,
    })
    Message.success('已保存')
    editVisible.value = false
    await loadFeeds()
  } catch (error:any) { Message.error(error?.message || String(error) || '保存失败') }
}
const toggleFeedStatus = async (feed: DouyinFeed) => {
  try {
    await updateDouyinFeed(feed.id, { status:feed.status ? 0 : 1 })
    Message.success(feed.status ? '已停用' : '已启用')
    await loadFeeds()
  } catch (error:any) { Message.error(error?.message || String(error) || '操作失败') }
}
const syncing = ref(false)
const triggerSyncById = async (id:string) => {
  syncing.value = true
  try {
    await triggerDouyinSync(id)
    Message.success('已提交同步任务')
  } catch (error:any) { Message.error(error?.message || String(error) || '同步失败') }
  finally { syncing.value = false }
}
const deleteFeedById = (feed: DouyinFeed) => {
  Modal.confirm({
    title:'删除订阅',
    content:`确定删除 ${feed.target} 吗？将同时清理该订阅下的所有作品。`,
    okText:'删除', cancelText:'取消', okButtonProps:{ status:'danger' },
    onOk: async () => {
      try {
        await deleteDouyinFeed(feed.id)
        if (activeFeedId.value === feed.id) activeFeedId.value = ''
        await loadFeeds()
        await loadArticles()
        Message.success('已删除')
      } catch (error:any) { Message.error(error?.message || String(error) || '删除失败') }
    },
  })
}
const copyTarget = async (target:string) => {
  if (!target) return Message.warning('目标为空')
  try { await navigator.clipboard.writeText(target); Message.success('已复制目标') }
  catch { Message.error('复制失败，请手动复制') }
}

const goAdd = () => router.push('/douyin/subscriptions')
watch(() => route.query.feed_id, (value) => {
  if (typeof value === 'string' && value !== activeFeedId.value) {
    activeFeedId.value = value
    articlePagination.current = 1
    loadArticles()
  }
})
onMounted(async () => {
  await loadFeeds()
  const queryFeed = route.query.feed_id
  if (typeof queryFeed === 'string') activeFeedId.value = queryFeed
  await loadArticles()
})
</script>

<style scoped>
.douyin-list { width:100%; height:100%; overflow:hidden; }
.douyin-list :deep(.arco-layout) { display:flex; width:100%; height:100%; }
.douyin-list :deep(.arco-layout-sider) { flex-shrink:0; overflow:hidden; }
.douyin-list :deep(.arco-layout-content) { flex:1; min-width:0; overflow:auto; box-sizing:border-box; }
.feed-panel { display:flex; flex-direction:column; gap:8px; background:#fff; }
.filter-row { padding:0 8px; }
.filter-option { flex:1; text-align:center; }
.feed-item { padding:8px 6px; cursor:pointer; display:flex; align-items:center; justify-content:space-between; }
.feed-summary { display:flex; align-items:center; gap:8px; }
.feed-avatar { border-radius:4px; }
.active-feed { background-color:var(--color-primary-light-1); }
.feed-pagination { margin-top:1rem; }
.feed-popover { display:flex; flex-direction:column; gap:8px; }
.feed-popover-head { display:flex; align-items:center; gap:8px; }
.feed-popover-name { font-weight:600; font-size:14px; }
.small-muted { font-size:12px; color:var(--color-text-3); }
.feed-intro { font-size:12px; color:var(--color-text-2); line-height:1.5; }
.feed-error { font-size:12px; color:var(--color-danger-6); }
.feed-actions { display:flex; gap:8px; padding-top:8px; border-top:1px solid var(--color-border); flex-wrap:wrap; }
.main-content { padding:20px; }
.search-bar { display:flex; align-items:center; gap:12px; margin:20px 0; }
.search-input { flex:1; min-width:200px; }
.article-link { color:var(--color-text-1); cursor:pointer; }
.article-link:hover { color:rgb(var(--arcoblue-6)); }
.muted { color:var(--color-text-4); }
.content-preview { color:var(--color-text-3); font-size:12px; line-height:1.5; }
:deep(.arco-table-th-item) { justify-content:center; }
:deep(.arco-table), :deep(.arco-table-container), :deep(.arco-card) { width:100% !important; box-sizing:border-box; }
:deep(.arco-table-container) { overflow-x:auto; }
</style>
