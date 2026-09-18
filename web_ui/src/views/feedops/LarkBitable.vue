<script setup lang="ts">
import { ref, reactive, onMounted, computed, h, nextTick } from 'vue'
import {
  listBitables,
  createBitable,
  updateBitable,
  deleteBitable,
  testBitable,
  manualPush,
  getLarkStatus,
} from '@/api/lark'
import type {
  LarkBitable,
  CreateBitableRequest,
  UpdateBitableRequest,
  TestBitableResp,
  LarkStatus,
} from '@/api/lark'
import { Modal, Message } from '@arco-design/web-vue'
import {
  IconPlus,
  IconRefresh,
  IconEdit,
  IconDelete,
  IconLink,
  IconCheckCircle,
  IconCloseCircle,
  IconStorage,
} from '@arco-design/web-vue/es/icon'
import FeedMultiSelect, { type FeedItem } from '@/components/FeedMultiSelect.vue'
import { getArticles } from '@/api/article'
import type { Article } from '@/api/article'

interface MappingRow {
  key: string
  value: string
}

const bitables = ref<LarkBitable[]>([])
const allowedKeys = ref<string[]>([])
const total = ref(0)
const loading = ref(false)
const larkStatus = ref<LarkStatus | null>(null)

const showForm = ref(false)
const showTestModal = ref(false)
const showMpSelector = ref(false)
const editingId = ref<string | null>(null)
const mpSelectorRef = ref<InstanceType<typeof FeedMultiSelect> | null>(null)
const formData = reactive<{
  name: string
  app_token: string
  table_id: string
  selected_mps: FeedItem[]
  mapping_rows: MappingRow[]
  enabled: boolean
  push_interval_hours: 1 | 2 | 4 | 6 | 12 | 24
}>({
  name: '',
  app_token: '',
  table_id: '',
  selected_mps: [],
  mapping_rows: [{ key: '', value: '' }],
  enabled: true,
  push_interval_hours: 6,
})

const testResult = ref<TestBitableResp | null>(null)
const testing = ref(false)
const submitting = ref(false)

// ---------- 列表 ----------

const loadBitables = async () => {
  loading.value = true
  try {
    const resp = await listBitables({ limit: 200 })
    bitables.value = resp.list || []
    total.value = resp.total || 0
    allowedKeys.value = resp.allowed_field_keys || []
  } catch (err: any) {
    Message.error('加载失败: ' + (err?.message || String(err)))
  } finally {
    loading.value = false
  }
}

const loadStatus = async () => {
  try {
    larkStatus.value = await getLarkStatus()
  } catch (err: any) {
    console.error('loadStatus failed:', err)
    larkStatus.value = null
  }
}

onMounted(() => {
  loadStatus()
  loadBitables()
})

const columns = [
  { title: '状态', slotName: 'enabled', width: 80 },
  { title: '名称', slotName: 'name', width: 200 },
  { title: 'App Token', dataIndex: 'app_token', width: 200, ellipsis: true, tooltip: true },
  { title: 'Table ID', dataIndex: 'table_id', width: 200, ellipsis: true, tooltip: true },
  { title: '关联公众号', slotName: 'feed_ids', width: 80 },
  { title: '自动写入', slotName: 'push_interval', width: 110 },
  { title: '最近推送', slotName: 'last_pushed', width: 200 },
  { title: '操作', slotName: 'action', width: 200, fixed: 'right' },
]

const formatTime = (ts: number | null | undefined): string => {
  if (!ts) return '—'
  const d = new Date(ts)
  if (isNaN(d.getTime())) return '—'
  return d.toLocaleString()
}

// ---------- 表单 ----------

const resetForm = () => {
  formData.name = ''
  formData.app_token = ''
  formData.table_id = ''
  formData.selected_mps = []
  formData.mapping_rows = [{ key: '', value: '' }]
  formData.enabled = true
  formData.push_interval_hours = 6
  editingId.value = null
}

const showCreate = () => {
  resetForm()
  showForm.value = true
}

const showEdit = async (b: LarkBitable) => {
  resetForm()
  editingId.value = b.id
  formData.name = b.name
  formData.app_token = b.app_token
  formData.table_id = b.table_id
  formData.enabled = !!b.enabled
  formData.push_interval_hours = b.push_interval_hours || 6
  // 把后端存的 feed_ids 字符串数组转成 FeedItem[] 占位,
// 打开选择器后 FeedMultiSelect.parseSelected 会尝试用搜索结果补全 mp_name/cover。
  formData.selected_mps = (b.feed_ids || []).map((id) => ({
    id,
    mp_name: id,
    mp_cover: '',
  }))
  const entries = Object.entries(b.field_mapping || {})
  formData.mapping_rows = entries.length
    ? entries.map(([k, v]) => ({ key: k, value: v }))
    : [{ key: '', value: '' }]
  showForm.value = true
}

const addMappingRow = () => {
  formData.mapping_rows.push({ key: '', value: '' })
}

const removeMappingRow = (idx: number) => {
  if (formData.mapping_rows.length === 1) {
    formData.mapping_rows[0] = { key: '', value: '' }
    return
  }
  formData.mapping_rows.splice(idx, 1)
}

const collectPayload = (): CreateBitableRequest | UpdateBitableRequest => {
  if (!formData.name.trim()) throw new Error('请输入名称')
  if (!formData.app_token.trim()) throw new Error('请输入 App Token')
  if (!formData.table_id.trim()) throw new Error('请输入 Table ID')

  const dedup = Array.from(
    new Set(formData.selected_mps.map((m) => m.id).filter(Boolean)),
  )

  const field_mapping: Record<string, string> = {}
  const seen = new Set<string>()
  for (const row of formData.mapping_rows) {
    const k = (row.key || '').trim()
    const v = (row.value || '').trim()
    if (!k && !v) continue
    if (!k) throw new Error('字段映射: 选择文章字段后必须填写多维表字段名')
    if (!v) throw new Error(`字段映射 [${k}]: 多维表字段名不能为空`)
    if (seen.has(k)) throw new Error(`字段映射存在重复: ${k}`)
    seen.add(k)
    field_mapping[k] = v
  }

  return {
    name: formData.name.trim(),
    app_token: formData.app_token.trim(),
    table_id: formData.table_id.trim(),
    feed_ids: dedup,
    field_mapping,
    enabled: formData.enabled,
    push_interval_hours: formData.push_interval_hours,
  }
}

const submitForm = async () => {
  let payload
  try {
    payload = collectPayload()
  } catch (e: any) {
    Message.warning(e?.message || String(e))
    return
  }
  submitting.value = true
  try {
    if (editingId.value) {
      await updateBitable(editingId.value, payload)
      Message.success('已更新')
    } else {
      await createBitable(payload as CreateBitableRequest)
      Message.success('已创建')
    }
    showForm.value = false
    await loadBitables()
  } catch (err: any) {
    Message.error('保存失败: ' + (err?.message || String(err)))
  } finally {
    submitting.value = false
  }
}

const openMpSelector = async () => {
  showMpSelector.value = true
  // 等 FeedMultiSelect 的 onMounted 拉完一次 searchFeeds 后,
  // 用 parseSelected 把 selected_mps 占位项尝试用搜索结果回填 mp_name/cover。
  await nextTick()
  await new Promise((r) => setTimeout(r, 400))
  if (mpSelectorRef.value && formData.selected_mps.length) {
    mpSelectorRef.value.parseSelected(formData.selected_mps)
  }
}

// ---------- 测试 / 删除 / 手动推送 ----------

const onTest = async (b: LarkBitable) => {
  testing.value = true
  testResult.value = null
  showTestModal.value = true
  try {
    const resp = await testBitable(b.id)
    testResult.value = resp
    if (resp?.ok) {
      Message.success(`连通正常,共 ${resp.field_count ?? 0} 个字段`)
      await loadBitables()
    } else {
      Message.warning('连通失败: ' + (resp?.message || '未知错误'))
    }
  } catch (err: any) {
    testResult.value = { ok: false, message: err?.message || String(err) }
    Message.error('测试失败: ' + (err?.message || String(err)))
  } finally {
    testing.value = false
  }
}

const onDelete = (b: LarkBitable) => {
  Modal.confirm({
    title: '确认删除',
    content: `删除多维表配置「${b.name}」?已推送的多维表记录会保留。`,
    okText: '删除',
    cancelText: '取消',
    okButtonProps: { status: 'danger' },
    onOk: async () => {
      try {
        await deleteBitable(b.id)
        Message.success('已删除')
        await loadBitables()
      } catch (err: any) {
        Message.error('删除失败: ' + (err?.message || String(err)))
      }
    },
  })
}

const onManualPush = (b: LarkBitable) => {
  // 多选推送:打开专用模态,内含文章搜索 + 复选列表
  pushModalBitable.value = b
  pushModalSelected.value = []
  pushModalSearch.value = ''
  showPushModal.value = true
  // 后端 mp_id 仅支持单值过滤,所以多 feed_id 走前端过滤。
  // 0 个 feed_id 时不做过滤,允许推送任意公众号文章(和后端 worker 行为一致)。
  pushModalMpIds.value = Array.isArray(b.feed_ids) ? [...b.feed_ids] : []
  loadPushModalArticles(true)
}

// ---------- 多选推送模态 ----------
const showPushModal = ref(false)
const pushModalBitable = ref<LarkBitable | null>(null)
const pushModalSelected = ref<string[]>([])
const pushModalSearch = ref('')
const pushModalMpIds = ref<string[]>([]) // 该 bitable 关联的 feed_ids,用于客户端过滤
const pushModalArticles = ref<Article[]>([])
const pushModalLoading = ref(false)
const pushModalSubmitting = ref(false)
const pushModalOffset = ref(0)
const pushModalLimit = 20
const pushModalTotal = ref(0)
const pushModalHasMore = ref(false)

const loadPushModalArticles = async (reset = false) => {
  if (!pushModalBitable.value) return
  pushModalLoading.value = true
  try {
    if (reset) {
      pushModalOffset.value = 0
      pushModalArticles.value = []
    }
    const resp: any = await getArticles({
      // getArticles 内部会把 page * pageSize 作为 offset,所以这里传 page 即可
      page: Math.floor(pushModalOffset.value / pushModalLimit),
      pageSize: pushModalLimit,
      search: pushModalSearch.value || undefined,
      has_content: true, // 没正文的 article lark worker 会跳过,提前过滤掉
    })
    // 后端 mp_id 接口只支持单值,所以过滤放在前端:
    // 仅保留 article.feed_id 在 bitable.feed_ids 集合内的条目。
    const list: Article[] = (resp?.list || []) as Article[]
    const mpSet = new Set(pushModalMpIds.value.map((s) => String(s)))
    const filtered = mpSet.size
      ? list.filter((a) => mpSet.has(String((a as any).feed_id || a.mp_id || '')))
      : list
    if (reset) {
      pushModalArticles.value = filtered
    } else {
      const existingIds = new Set(pushModalArticles.value.map((a) => String(a.id)))
      pushModalArticles.value = [
        ...pushModalArticles.value,
        ...filtered.filter((a) => !existingIds.has(String(a.id))),
      ]
    }
    pushModalTotal.value = Number(resp?.total || 0)
    // 继续翻页条件:
    //   1) 后端还有更多(list 长度 == pageSize 表示还有,小于则说明到底了)
    //   2) 我们累计拉的页数没到上限(200,避免极端情况下无限拉)
    // 这里不能用 pushModalArticles.length < pushModalTotal,因为 total 是未过滤前的
    // 总数,前端过滤后永远小于它,会陷入"加载更多但始终拿不到目标 mp 文章"的循环。
    pushModalHasMore.value =
      list.length >= pushModalLimit && pushModalOffset.value + pushModalLimit < 200
    pushModalOffset.value += pushModalLimit
  } catch (err: any) {
    Message.error('加载文章失败: ' + (err?.message || String(err)))
  } finally {
    pushModalLoading.value = false
  }
}

const onPushModalSearch = () => {
  loadPushModalArticles(true)
}

const onPushModalLoadMore = () => {
  if (pushModalLoading.value || !pushModalHasMore.value) return
  loadPushModalArticles(false)
}

const togglePushModalItem = (articleId: string) => {
  const idx = pushModalSelected.value.indexOf(articleId)
  if (idx >= 0) {
    pushModalSelected.value.splice(idx, 1)
  } else {
    pushModalSelected.value.push(articleId)
  }
}

const isPushModalSelected = (articleId: string) =>
  pushModalSelected.value.includes(articleId)

const selectAllPushModalVisible = () => {
  const visibleIds = pushModalArticles.value.map((a) => String(a.id))
  const allSelected = visibleIds.every((id) => pushModalSelected.value.includes(id))
  if (allSelected) {
    // 取消当前可见项
    pushModalSelected.value = pushModalSelected.value.filter(
      (id) => !visibleIds.includes(id),
    )
  } else {
    // 合并:保留已选 + 新增可见未选
    const set = new Set(pushModalSelected.value)
    visibleIds.forEach((id) => set.add(id))
    pushModalSelected.value = Array.from(set)
  }
}

const allVisibleSelected = computed(() => {
  if (!pushModalArticles.value.length) return false
  return pushModalArticles.value.every((a) =>
    pushModalSelected.value.includes(String(a.id)),
  )
})

const clearPushModalSelection = () => {
  pushModalSelected.value = []
}

const closePushModal = () => {
  showPushModal.value = false
  pushModalBitable.value = null
  pushModalSelected.value = []
  pushModalArticles.value = []
  pushModalSearch.value = ''
}

const submitPushModal = async (): Promise<boolean | undefined> => {
  if (!pushModalBitable.value) return true
  if (!pushModalSelected.value.length) {
    Message.warning('请至少选择一篇文章')
    return false // 阻止关闭
  }
  pushModalSubmitting.value = true
  try {
    const resp: any = await manualPush(
      pushModalBitable.value.id,
      pushModalSelected.value,
    )
    const submittedCount = Number(resp?.submitted_count ?? 0)
    const totalCount = Number(resp?.total ?? pushModalSelected.value.length)
    if (submittedCount === totalCount && totalCount > 0) {
      Message.success(`已提交 ${submittedCount}/${totalCount} 条到 worker`)
    } else if (submittedCount > 0) {
      Message.warning(`部分提交成功: ${submittedCount}/${totalCount}`)
    } else {
      Message.error('提交失败:请查看详情')
    }
    // 返回 undefined → Arco 自动关闭模态
    return
  } catch (err: any) {
    Message.error('提交失败: ' + (err?.message || String(err)))
    return false // 失败时阻止关闭,允许用户重试
  } finally {
    pushModalSubmitting.value = false
  }
}

const formatArticleTime = (ts: any): string => {
  if (!ts) return ''
  // 文章接口可能返回秒或毫秒或 ISO 字符串,统一尝试
  let d: Date
  if (typeof ts === 'number') {
    d = new Date(ts < 1e12 ? ts * 1000 : ts)
  } else {
    d = new Date(ts)
  }
  if (isNaN(d.getTime())) return ''
  return d.toLocaleString()
}

// arco Modal.confirm 中用 h() 需要显式 import (setup 内置 h)
// 实际可在 <script setup> 中直接使用 h — Vue 3 内置

const sortedBitables = computed(() => bitables.value)

const statusIssues = computed(() => larkStatus.value?.issues || [])
const statusEnabled = computed(() => larkStatus.value?.enabled ?? false)
</script>

<template>
  <div class="lark-page">
    <a-card title="飞书多维表配置" :bordered="false">
      <template #extra>
        <a-space>
          <a-button @click="loadBitables">
            <template #icon><icon-refresh /></template>
            刷新
          </a-button>
          <a-button type="primary" @click="showCreate">
            <template #icon><icon-plus /></template>
            新建配置
          </a-button>
        </a-space>
      </template>

      <a-alert
        v-if="!allowedKeys.length"
        type="warning"
        style="margin-bottom: 12px"
        :show-icon="true"
      >
        后端尚未返回允许的字段列表,请检查后端是否正常。
      </a-alert>

      <a-alert
        v-if="statusIssues.length"
        :type="statusEnabled ? 'warning' : 'error'"
        style="margin-bottom: 12px"
        :show-icon="true"
        :title="statusEnabled ? '推送可能不生效' : '推送未启用'"
      >
        <ul style="margin: 0; padding-left: 18px">
          <li v-for="(msg, i) in statusIssues" :key="i">{{ msg }}</li>
        </ul>
      </a-alert>

      <p style="margin: 0 0 12px; color: var(--color-text-3); font-size: 12px">
        允许的文章字段 (LHS): <code>{{ allowedKeys.join(', ') || '—' }}</code>
      </p>

      <a-table
        :columns="columns"
        :data="sortedBitables"
        :loading="loading"
        :pagination="false"
        row-key="id"
        size="small"
      >
        <template #enabled="{ record }">
          <a-tag v-if="record.enabled" color="green">启用</a-tag>
          <a-tag v-else color="gray">禁用</a-tag>
        </template>
        <template #name="{ record }">
          <strong>{{ record.name }}</strong>
          <div style="font-size: 11px; color: var(--color-text-3)">{{ record.id }}</div>
        </template>
        <template #feed_ids="{ record }">
          <a-tag color="arcoblue" style="margin: 1px">
            {{ record.feed_ids?.length }}
          </a-tag>
        </template>
        <template #push_interval="{ record }">
          <span>每 {{ record.push_interval_hours || 6 }} 小时</span>
        </template>
        <template #field_mapping="{ record }">
          <a-tag
            v-for="(v, k) in record.field_mapping"
            :key="k"
            color="gray"
            style="margin: 1px; font-family: var(--code-font-family)"
          >
            {{ k }} → {{ v }}
          </a-tag>
          <span
            v-if="!Object.keys(record.field_mapping || {}).length"
            style="color: var(--color-text-3)"
          >(无映射)</span>
        </template>
        <template #last_pushed="{ record }">
          <div>{{ formatTime(record.last_pushed_at) }}</div>
          <div
            v-if="record.last_error"
            style="font-size: 11px; color: rgb(var(--red-6)); max-width: 360px; word-break: break-all"
          >
            {{ formatTime(record.last_error_at) }}: {{ record.last_error }}
          </div>
        </template>
        <template #action="{ record }">
          <a-space>
            <a-button size="mini" @click="onTest(record)">
              <template #icon><icon-link /></template>
              测试
            </a-button>
            <a-button size="mini" @click="onManualPush(record)" type="outline">
              <template #icon><icon-storage /></template>
              推送
            </a-button>
            <a-button size="mini" @click="showEdit(record)" type="secondary">
              <template #icon><icon-edit /></template>
              编辑
            </a-button>
            <a-button size="mini" @click="onDelete(record)" status="danger" type="outline">
              <template #icon><icon-delete /></template>
              删除
            </a-button>
          </a-space>
        </template>
      </a-table>

      <div style="margin-top: 12px; color: var(--color-text-3); font-size: 12px">
        共 {{ total }} 条
      </div>
    </a-card>

    <!-- 表单模态 -->
    <a-modal
      v-model:visible="showForm"
      :title="editingId ? '编辑多维表配置' : '新建多维表配置'"
      :ok-text="editingId ? '保存' : '创建'"
      :ok-button-props="{ loading: submitting }"
      :width="720"
      @ok="submitForm"
      unmount-on-close
    >
      <a-form :model="formData" layout="vertical">
        <a-form-item label="名称" required>
          <a-input v-model="formData.name" placeholder="例:科技日报 → 飞书多维表" max-length="255" />
        </a-form-item>
        <a-form-item label="App Token" required>
          <a-input v-model="formData.app_token" placeholder="bascnxxxxxxxxxxxxxxxxxxxxxx" />
        </a-form-item>
        <a-form-item label="Table ID" required>
          <a-input v-model="formData.table_id" placeholder="tblxxxxxxxxxxxx" />
        </a-form-item>
        <a-form-item label="关联公众号">
          <a-input
            :model-value="`已选 ${formData.selected_mps.length} 个订阅`"
            placeholder="留空则对所有公众号生效"
            readonly
            allow-clear
          >
            <template #append>
              <a-button @click="openMpSelector">选择</a-button>
            </template>
          </a-input>
        </a-form-item>
        <a-form-item label="自动写入间隔" required>
          <a-select v-model="formData.push_interval_hours" placeholder="请选择自动写入间隔">
            <a-option :value="1">每隔 1 小时</a-option>
            <a-option :value="2">每隔 2 小时</a-option>
            <a-option :value="4">每隔 4 小时</a-option>
            <a-option :value="6">每隔 6 小时</a-option>
            <a-option :value="12">每隔 12 小时</a-option>
            <a-option :value="24">每隔 24 小时</a-option>
          </a-select>
          <template #extra>启用配置后，系统会按此间隔把新增文章自动写入该多维表。</template>
        </a-form-item>
        <a-form-item>
          <a-checkbox v-model="formData.enabled">启用此配置</a-checkbox>
        </a-form-item>

        <a-divider>字段映射</a-divider>
        <p style="margin: 0 0 8px; color: var(--color-text-3); font-size: 12px">
          左侧 = 文章字段; 右侧 = 多维表字段名
        </p>
        <div
          v-for="(row, idx) in formData.mapping_rows"
          :key="idx"
          style="display: flex; gap: 8px; margin-bottom: 8px; align-items: center"
        >
          <a-select
            v-model="row.key"
            placeholder="选择文章字段"
            style="flex: 1"
            allow-clear
          >
            <a-option v-for="k in allowedKeys" :key="k" :value="k">{{ k }}</a-option>
          </a-select>
          <a-input
            v-model="row.value"
            placeholder="多维表字段名"
            style="flex: 1"
            allow-clear
          />
          <a-button
            size="mini"
            status="danger"
            type="outline"
            @click="removeMappingRow(idx)"
          >
            删除
          </a-button>
        </div>
        <a-button size="small" type="dashed" @click="addMappingRow">
          + 添加一行
        </a-button>
      </a-form>
    </a-modal>

    <!-- 测试结果模态 -->
    <a-modal
      v-model:visible="showTestModal"
      title="连通测试结果"
      :footer="false"
      :width="640"
      unmount-on-close
    >
      <div v-if="testing" style="text-align: center; padding: 24px">
        <a-spin />
      </div>
      <div v-else-if="testResult">
        <div style="margin-bottom: 12px">
          <a-tag v-if="testResult.ok" color="green" size="large">
            <template #icon><icon-check-circle /></template>
            连通正常
          </a-tag>
          <a-tag v-else color="red" size="large">
            <template #icon><icon-close-circle /></template>
            连通失败
          </a-tag>
        </div>
        <div v-if="testResult.message" style="margin-bottom: 8px">
          <strong>信息:</strong> {{ testResult.message }}
        </div>
        <div v-if="testResult.code !== undefined && testResult.code !== null" style="margin-bottom: 8px">
          <strong>错误码:</strong> {{ testResult.code }}
        </div>
        <div v-if="testResult.field_count !== undefined" style="margin-bottom: 8px">
          <strong>字段数:</strong> {{ testResult.field_count }}
        </div>
        <div v-if="testResult.fields?.length">
          <strong>字段列表:</strong>
          <ul style="margin: 4px 0; padding-left: 20px">
            <li v-for="f in testResult.fields" :key="f.id">
              <code>{{ f.name }}</code>
              <span style="color: var(--color-text-3); font-size: 12px">
                (type={{ f.type }}, id={{ f.id }})
              </span>
            </li>
          </ul>
        </div>
      </div>
    </a-modal>

    <!-- 手动推送文章(多选) -->
    <a-modal
      v-model:visible="showPushModal"
      title="手动推送文章"
      :ok-text="pushModalSubmitting ? '提交中...' : `提交 (${pushModalSelected.length})`"
      :ok-button-props="{ disabled: !pushModalSelected.length || pushModalSubmitting, loading: pushModalSubmitting }"
      :cancel-text="'取消'"
      :mask-closable="!pushModalSubmitting"
      width="780px"
      :on-before-ok="submitPushModal"
      @cancel="closePushModal"
    >
      <div class="push-modal">
        <a-alert type="info" :show-icon="true" style="margin-bottom: 12px">
          推送到「{{ pushModalBitable?.name }}」
          <span v-if="pushModalMpIds.length">
            ,已按 {{ pushModalMpIds.length }} 个关联公众号过滤候选文章
          </span>
          <span v-else>
            ,未关联任何公众号,可手动选择任意文章推送(worker 会按 article.feed_id 自动匹配)
          </span>
        </a-alert>

        <div class="push-modal-toolbar">
          <a-input-search
            v-model="pushModalSearch"
            placeholder="搜索文章标题或 ID"
            allow-clear
            @search="onPushModalSearch"
            @clear="onPushModalSearch"
            style="flex: 1"
          />
          <a-button @click="selectAllPushModalVisible" :disabled="!pushModalArticles.length">
            {{ allVisibleSelected ? '取消全选' : '全选当前页' }}
          </a-button>
          <a-button @click="clearPushModalSelection" :disabled="!pushModalSelected.length">
            清空 ({{ pushModalSelected.length }})
          </a-button>
        </div>

        <div class="push-modal-summary">
          <span>
            已选 {{ pushModalSelected.length }} /
            可见 {{ pushModalArticles.length }}
            <template v-if="pushModalMpIds.length">
              / 匹配 {{ pushModalArticles.length }} 条(后端共 {{ pushModalTotal }} 条)
            </template>
            <template v-else>
              / 总计 {{ pushModalTotal }}
            </template>
          </span>
        </div>

        <a-spin :loading="pushModalLoading" style="width: 100%">
          <div class="push-modal-list">
            <a-checkbox
              v-for="a in pushModalArticles"
              :key="String(a.id)"
              :model-value="isPushModalSelected(String(a.id))"
              @change="togglePushModalItem(String(a.id))"
              class="push-modal-item"
            >
              <div class="push-modal-item-title">{{ a.title || '(无标题)' }}</div>
              <div class="push-modal-item-meta">
                <span>{{ (a as any).name || (a as any).mp_name || '未知公众号' }}</span>
                <span class="push-modal-item-id">id: {{ a.id }}</span>
                <span v-if="a.publish_time">{{ formatArticleTime(a.publish_time) }}</span>
              </div>
            </a-checkbox>
            <a-empty v-if="!pushModalLoading && !pushModalArticles.length" description="暂无匹配文章" />
          </div>
        </a-spin>

        <div v-if="pushModalHasMore" class="push-modal-loadmore">
          <a-button
            type="text"
            :loading="pushModalLoading"
            @click="onPushModalLoadMore"
          >
            加载更多
          </a-button>
        </div>
      </div>
    </a-modal>

    <!-- 公众号选择器 -->
    <a-modal
      v-model:visible="showMpSelector"
      title="选择公众号"
      :footer="false"
      width="800px"
    >
      <FeedMultiSelect
        ref="mpSelectorRef"
        v-model="formData.selected_mps"
      />
      <template #footer>
        <a-button type="primary" @click="showMpSelector = false">确定</a-button>
      </template>
    </a-modal>
  </div>
</template>

<style scoped>
.lark-page { padding: 16px; }
code { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }

.push-modal-toolbar {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
}
.push-modal-summary {
  font-size: 12px;
  color: var(--color-text-3);
  margin-bottom: 8px;
}
.push-modal-list {
  max-height: 420px;
  overflow-y: auto;
  border: 1px solid var(--color-border-2);
  border-radius: 4px;
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.push-modal-item {
  padding: 6px 8px;
  border-radius: 4px;
  transition: background-color 0.15s;
}
.push-modal-item:hover {
  background-color: var(--color-fill-2);
}
.push-modal-item-title {
  font-size: 14px;
  color: var(--color-text-1);
  word-break: break-all;
}
.push-modal-item-meta {
  font-size: 12px;
  color: var(--color-text-3);
  display: flex;
  gap: 12px;
  margin-top: 2px;
  flex-wrap: wrap;
}
.push-modal-item-id {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}
.push-modal-loadmore {
  text-align: center;
  margin-top: 8px;
}
</style>
