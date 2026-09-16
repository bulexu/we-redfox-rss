<template>
  <div class="xhs-feeds">
    <a-card title="小红书订阅管理" :bordered="false">
      <a-space style="margin-bottom: 16px">
        <a-button type="primary" @click="goAdd">添加订阅</a-button>
        <a-radio-group v-model="filterKind" type="button" @change="loadData">
          <a-radio value="">全部</a-radio>
          <a-radio value="keyword">关键词</a-radio>
          <a-radio value="account">账号</a-radio>
        </a-radio-group>
        <a-radio-group v-model="filterStatus" type="button" @change="loadData">
          <a-radio :value="undefined">全部状态</a-radio>
          <a-radio :value="1">启用</a-radio>
          <a-radio :value="0">禁用</a-radio>
        </a-radio-group>
      </a-space>

      <a-table
        :columns="columns"
        :data="feedList"
        :pagination="pagination"
        @page-change="handlePageChange"
      >
        <template #kind="{ record }">
          <a-tag :color="record.kind === 'keyword' ? 'arcoblue' : 'green'">
            {{ record.kind === 'keyword' ? '关键词' : '账号' }}
          </a-tag>
        </template>
        <template #target="{ record }">
          <span class="target-text">{{ record.target }}</span>
        </template>
        <template #status="{ record }">
          <a-tag :color="record.status ? 'green' : 'red'">
            {{ record.status ? '已启用' : '已禁用' }}
          </a-tag>
        </template>
        <template #error="{ record }">
          <a-tooltip v-if="record.error_count > 0" :content="record.last_error || '无详情'">
            <a-tag color="orange">{{ record.error_count }}</a-tag>
          </a-tooltip>
          <span v-else class="muted">—</span>
        </template>
        <template #sync_time="{ record }">
          <span class="muted">{{ formatTime(record.sync_time) }}</span>
        </template>
        <template #action="{ record }">
          <a-space>
            <a-button size="mini" @click="goArticles(record)">笔记</a-button>
            <a-button size="mini" @click="editFeed(record)">编辑</a-button>
            <a-button
              size="mini"
              :status="record.status ? 'warning' : 'success'"
              @click="toggleStatus(record)"
            >
              {{ record.status ? '禁用' : '启用' }}
            </a-button>
            <a-button size="mini" type="outline" @click="triggerSync(record)">同步</a-button>
            <a-button size="mini" status="danger" @click="deleteFeed(record)">删除</a-button>
          </a-space>
        </template>
      </a-table>
    </a-card>

    <a-modal
      v-model:visible="editVisible"
      :title="editTitle"
      :ok-text="'保存'"
      @ok="saveEdit"
      @cancel="editVisible = false"
    >
      <a-form :model="editForm" layout="vertical">
        <a-form-item label="显示名称" field="name">
          <a-input v-model="editForm.name" />
        </a-form-item>
        <a-form-item label="头像 URL" field="cover">
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
            @change="(v: boolean) => (editForm.status = v ? 1 : 0)"
          />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Message, Modal } from '@arco-design/web-vue'
import {
  listXhsFeeds,
  updateXhsFeed,
  deleteXhsFeed,
  triggerXhsSync,
  type XhsFeed,
  type XhsKind,
} from '@/api/xhs'

const router = useRouter()

const filterKind = ref<XhsKind | ''>('')
const filterStatus = ref<number | undefined>(undefined)
const feedList = ref<XhsFeed[]>([])
const pagination = reactive({ current: 1, pageSize: 10, total: 0 })

const columns = [
  { title: '类型', slotName: 'kind', width: 90 },
  { title: '目标', slotName: 'target', ellipsis: true },
  { title: '显示名', dataIndex: 'name', ellipsis: true },
  { title: '状态', slotName: 'status', width: 90 },
  { title: '失败次数', slotName: 'error', width: 90 },
  { title: '最后同步', slotName: 'sync_time', width: 180 },
  { title: '操作', slotName: 'action', width: 320 },
]

const formatTime = (ts: number) => {
  if (!ts) return '—'
  return new Date(ts * 1000).toLocaleString('zh-CN')
}

const loadData = async () => {
  try {
    const res = await listXhsFeeds({
      kind: filterKind.value || undefined,
      status: filterStatus.value,
      page: pagination.current - 1,
      pageSize: pagination.pageSize,
    })
    if (res.code === 0) {
      feedList.value = res.data.list || []
      pagination.total = res.data.total || 0
    } else {
      throw new Error(res.message || '获取订阅列表失败')
    }
  } catch (err: any) {
    Message.error(err.message || '获取订阅列表错误')
  }
}

const handlePageChange = (page: number) => {
  pagination.current = page
  loadData()
}

const goAdd = () => router.push('/xhs/subscriptions')
const goArticles = (rec: XhsFeed) =>
  router.push({ path: '/xhs/articles', query: { feed_id: rec.id } })

// ===== 编辑 =====
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

const editFeed = (rec: XhsFeed) => {
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
    if (res.code === 0) {
      Message.success('已保存')
      editVisible.value = false
      loadData()
    } else {
      throw new Error(res.message || '保存失败')
    }
  } catch (err: any) {
    Message.error(err.message || '保存失败')
  }
}

// ===== 启停 / 同步 / 删除 =====
const toggleStatus = async (rec: XhsFeed) => {
  const next = rec.status ? 0 : 1
  try {
    await updateXhsFeed(rec.id, { status: next })
    Message.success(next ? '已启用' : '已禁用')
    loadData()
  } catch (err: any) {
    Message.error(err.message || '操作失败')
  }
}

const triggerSync = async (rec: XhsFeed) => {
  try {
    const res = await triggerXhsSync(rec.id)
    if (res.code === 0) {
      Message.success('已提交同步任务')
    } else {
      throw new Error(res.message || '提交失败')
    }
  } catch (err: any) {
    Message.error(err.message || '提交同步失败')
  }
}

const deleteFeed = (rec: XhsFeed) => {
  Modal.confirm({
    title: '删除订阅',
    content: `确定删除 ${rec.target} 吗? 将同时清理该订阅下的所有笔记。`,
    okText: '删除',
    cancelText: '取消',
    okButtonProps: { status: 'danger' },
    onOk: async () => {
      try {
        const res = await deleteXhsFeed(rec.id)
        if (res.code === 0) {
          Message.success(res.message || '已删除')
          loadData()
        } else {
          throw new Error(res.message || '删除失败')
        }
      } catch (err: any) {
        Message.error(err.message || '删除失败')
      }
    },
  })
}

onMounted(loadData)
</script>

<style scoped>
.xhs-feeds {
  padding: 20px;
}
.target-text {
  font-family: monospace;
  color: var(--color-text-2);
}
.muted {
  color: var(--color-text-4);
}
</style>
