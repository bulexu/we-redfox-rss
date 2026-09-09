<template>
  <div class="redfox-logs">
    <a-page-header title="Redfox 接口日志" subtitle="redfox 数据接口调用日志与统计">
      <a-card :bordered="false" class="stats-card">
        <a-space>
          <a-date-picker
            v-model="selectedDate"
            style="width: 200px"
            @change="handleDateChange"
            :disabled-date="disabledDate"
            allow-clear
          />
          <a-button type="primary" @click="loadStats" :loading="loading">
            <template #icon><icon-search /></template>
            查询
          </a-button>
          <a-button @click="loadToday" :loading="loading">
            <template #icon><icon-calendar /></template>
            今日统计
          </a-button>
          <a-button @click="refresh" :loading="loading">
            <template #icon><icon-refresh /></template>
            刷新
          </a-button>
          <a-popconfirm
            content="确认清空所有 redfox 调用日志？历史日期统计不受影响。"
            @ok="handleClear"
          >
            <a-button status="danger" :loading="clearing">
              <template #icon><icon-delete /></template>
              清空日志
            </a-button>
          </a-popconfirm>
        </a-space>
      </a-card>

      <a-spin :loading="loading" style="width: 100%">
        <!-- 概览 -->
        <a-card :bordered="false" class="stats-card">
          <template #title>
            <span class="stats-card-title">
              <span class="stats-card-title-prefix">今日</span>
              <span>调用概览</span>
              <a-tag v-if="stats.date" color="arcoblue" size="small" class="stats-card-date-tag">
                {{ stats.date }}
              </a-tag>
            </span>
          </template>
          <a-row :gutter="16">
            <a-col :xs="24" :sm="12" :md="6">
              <a-statistic title="调用总数" :value="stats.total">
                <template #prefix><icon-send /></template>
              </a-statistic>
            </a-col>
            <a-col :xs="24" :sm="12" :md="6">
              <a-statistic
                title="成功"
                :value="stats.success"
                :value-style="{ color: '#00b42a' }"
              >
                <template #prefix><icon-check-circle-fill /></template>
              </a-statistic>
            </a-col>
            <a-col :xs="24" :sm="12" :md="6">
              <a-statistic
                title="失败"
                :value="stats.failed"
                :value-style="stats.failed > 0 ? { color: '#f53f3f' } : {}"
              >
                <template #prefix><icon-close-circle-fill /></template>
              </a-statistic>
            </a-col>
            <a-col :xs="24" :sm="12" :md="6">
              <a-statistic
                title="成功率"
                :value="successRateValue"
                :precision="2"
                :value-style="{ color: '#165dff' }"
                suffix="%"
              >
                <template #prefix><icon-star /></template>
              </a-statistic>
            </a-col>
          </a-row>
        </a-card>

        <!-- 每日调用趋势 -->
        <a-card :bordered="false" class="stats-card" title="每日调用趋势">
          <template #extra>
            <div class="trend-switch">
              <button
                v-for="opt in trendOptions"
                :key="opt.value"
                type="button"
                class="trend-switch-btn"
                :class="{ active: trendDays === opt.value }"
                @click="switchTrend(opt.value)"
              >
                {{ opt.label }}
              </button>
            </div>
          </template>
          <div v-if="trendLoading" class="trend-loading">加载中...</div>
          <div v-else>
            <div class="trend-summary">
              <span class="trend-summary-item">
                <span class="trend-summary-label">近 {{ trendDays }} 天累计</span>
                <strong>{{ trendSummary.total }}</strong> 次
              </span>
              <span class="trend-summary-item">
                <span class="trend-summary-label">成功</span>
                <strong style="color:#00b42a">{{ trendSummary.success }}</strong>
              </span>
              <span class="trend-summary-item">
                <span class="trend-summary-label">失败</span>
                <strong :style="{ color: trendSummary.failed > 0 ? '#f53f3f' : '#86909c' }">{{ trendSummary.failed }}</strong>
              </span>
              <span class="trend-summary-item">
                <span class="trend-summary-label">日均</span>
                <strong>{{ trendSummary.avg }}</strong>
              </span>
            </div>
            <div v-if="!dailyStats.length" class="trend-empty">
              所选时间段暂无 redfox 调用记录
            </div>
            <div v-else class="trend-chart" :style="{ height: trendChartHeight + 'px' }">
              <div
                v-for="(item, idx) in dailyStats"
                :key="item.date"
                class="trend-bar-cell"
                :class="{ wide: trendDays <= 60 }"
                :style="{ width: barCellWidth }"
                :title="`${item.date}\n总调用: ${item.total}\n成功: ${item.success}\n失败: ${item.failed}`"
              >
                <div class="trend-bar-wrapper">
                  <div
                    class="trend-bar"
                    :style="{
                      height: barHeight(item.total) + '%',
                      background: barColor(item),
                    }"
                  ></div>
                </div>
                <div v-if="item.total > 0" class="trend-bar-value">{{ item.total }}</div>
                <div v-else class="trend-bar-value muted">{{ item.total }}</div>
                <div class="trend-bar-label" :class="{ 'today-label': idx === dailyStats.length - 1 }">
                  {{ formatDateLabel(item.date) }}
                </div>
              </div>
            </div>
          </div>
        </a-card>

        <!-- 接口维度 -->
        <a-card
          :bordered="false"
          class="stats-card"
          title="接口维度统计"
          v-if="Object.keys(stats.endpoints || {}).length > 0"
        >
          <a-table
            :columns="endpointColumns"
            :data="endpointTableData"
            :pagination="false"
            :stripe="true"
            size="small"
          >
            <template #count="{ record }">
              <a-tag :color="record.count > 50 ? 'red' : record.count > 10 ? 'orange' : 'blue'">
                {{ record.count }}
              </a-tag>
            </template>
          </a-table>
        </a-card>

        <!-- 公众号维度 -->
        <a-card
          :bordered="false"
          class="stats-card"
          title="公众号维度统计"
          v-if="Object.keys(stats.mp_stats || {}).length > 0"
        >
          <a-table
            :columns="mpColumns"
            :data="mpTableData"
            :pagination="{ pageSize: 10 }"
            :stripe="true"
            size="small"
          >
            <template #count="{ record }">
              <a-tag :color="record.count > 50 ? 'red' : record.count > 10 ? 'orange' : 'arcoblue'">
                {{ record.count }}
              </a-tag>
            </template>
          </a-table>
        </a-card>

        <!-- 调用日志 -->
        <a-card :bordered="false" class="stats-card" title="最近调用日志">
          <a-table
            :columns="logColumns"
            :data="logs"
            :pagination="{ pageSize: 20, showTotal: true }"
            :stripe="true"
            size="small"
          >
            <template #success="{ record }">
              <a-tag :color="record.success ? 'green' : 'red'">
                {{ record.success ? '成功' : '失败' }}
              </a-tag>
            </template>
            <template #endpoint="{ record }">
              <a-tag>{{ record.endpoint }}</a-tag>
            </template>
            <template #latency="{ record }">
              <span :style="{ color: record.latency_ms > 3000 ? '#f53f3f' : record.latency_ms > 1000 ? '#ff7d00' : '#00b42a' }">
                {{ record.latency_ms }} ms
              </span>
            </template>
            <template #code="{ record }">
              <a-tag v-if="record.code === 2000" color="green">{{ record.code }}</a-tag>
              <a-tag v-else color="red">{{ record.code }}</a-tag>
            </template>
            <template #request="{ record }">
              <a-tooltip :content="JSON.stringify(record.request, null, 2)">
                <span class="request-cell">
                  {{ formatRequest(record.request) }}
                </span>
              </a-tooltip>
            </template>
            <template #error_msg="{ record }">
              <span v-if="record.error_msg" class="error-cell">{{ record.error_msg }}</span>
              <span v-else class="muted">—</span>
            </template>
          </a-table>
        </a-card>
      </a-spin>
    </a-page-header>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { Message } from '@arco-design/web-vue'
import {
  IconSearch,
  IconCalendar,
  IconRefresh,
  IconSend,
  IconCheckCircleFill,
  IconCloseCircleFill,
  IconStar,
  IconDelete,
} from '@arco-design/web-vue/es/icon'
import {
  clearRedfoxLogs,
  getRedfoxDailyStats,
  getRedfoxLogs,
  getRedfoxStats,
  type RedfoxDailyStat,
  type RedfoxLogEntry,
  type RedfoxStats,
} from '@/api/redfox'

const loading = ref(false)
const clearing = ref(false)
const trendLoading = ref(false)
const trendDays = ref<number>(7)
const trendOptions = [
  { label: '近 7 天', value: 7 },
  { label: '近 30 天', value: 30 },
  { label: '近 180 天', value: 180 },
]
const dailyStats = ref<RedfoxDailyStat[]>([])
const selectedDate = ref<string>('')
const stats = ref<RedfoxStats>({
  date: '',
  total: 0,
  success: 0,
  failed: 0,
  endpoints: {},
  mp_stats: {},
  recent_logs: [],
})
const logs = ref<RedfoxLogEntry[]>([])

const endpointColumns = [
  { title: '接口', dataIndex: 'endpoint', width: '60%' },
  { title: '次数', dataIndex: 'count', slotName: 'count', width: '20%' },
  { title: '占比', dataIndex: 'percentage', width: '20%' },
]

const mpColumns = [
  { title: '公众号', dataIndex: 'mp_id', width: '40%', ellipsis: true },
  { title: '次数', dataIndex: 'count', slotName: 'count', width: '20%' },
  { title: '占比', dataIndex: 'percentage', width: '20%' },
]

const logColumns = [
  { title: '时间', dataIndex: 'timestamp', width: '160px' },
  { title: '接口', dataIndex: 'endpoint', slotName: 'endpoint', width: '220px' },
  { title: '结果', dataIndex: 'success', slotName: 'success', width: '80px' },
  { title: 'code', dataIndex: 'code', slotName: 'code', width: '70px' },
  { title: 'HTTP', dataIndex: 'http_status', width: '70px' },
  { title: '耗时', dataIndex: 'latency_ms', slotName: 'latency', width: '90px' },
  { title: '公众号', dataIndex: 'mp_id', width: '200px', ellipsis: true },
  { title: '请求', dataIndex: 'request', slotName: 'request' },
  { title: '错误信息', dataIndex: 'error_msg', slotName: 'error_msg', width: '240px' },
]

const successRateValue = computed(() => {
  const total = stats.value.total || 0
  if (!total) return 0
  return Number(((stats.value.success / total) * 100).toFixed(2))
})

const trendChartHeight = computed(() => (trendDays.value > 60 ? 260 : 220))

const barCellWidth = computed<string>(() => {
  const n = dailyStats.value.length || 1
  // 大于 60 天时每柱固定 24px 宽度（容器可滚动），其余按比例平分
  if (n > 60) return '24px'
  return `${100 / n}%`
})

const trendMaxValue = computed(() => {
  const max = dailyStats.value.reduce((m, d) => Math.max(m, d.total || 0), 0)
  // 让最高柱不至于顶到 100%，保留 5% 顶部空隙
  return max * 1.05 || 1
})

const trendSummary = computed(() => {
  const total = dailyStats.value.reduce((s, d) => s + (d.total || 0), 0)
  const success = dailyStats.value.reduce((s, d) => s + (d.success || 0), 0)
  const failed = dailyStats.value.reduce((s, d) => s + (d.failed || 0), 0)
  const n = dailyStats.value.length || 1
  return {
    total,
    success,
    failed,
    avg: Math.round(total / n),
  }
})

const barHeight = (value: number) => {
  if (!value) return 2 // 空数据时仍显示一根极矮的灰色条
  return Math.max(2, (value / trendMaxValue.value) * 100)
}

const barColor = (item: RedfoxDailyStat) => {
  if (!item.total) return '#e5e6eb'
  if (item.failed > 0 && item.success === 0) return '#f53f3f'
  if (item.failed > 0) {
    // 失败率越高颜色越偏红：橙 -> 红
    const ratio = item.failed / item.total
    if (ratio > 0.3) return '#ff7d00'
    return '#165dff'
  }
  return '#00b42a'
}

const formatDateLabel = (date: string) => {
  // 7 天视图显示月-日；30/180 天视图显示日（更紧凑）
  if (trendDays.value <= 7) {
    const [, m, d] = date.split('-')
    return `${m}-${d}`
  }
  const [, , d] = date.split('-')
  return d
}

const endpointTableData = computed(() => {
  const data: any[] = []
  Object.entries(stats.value.endpoints || {}).forEach(([endpoint, count]) => {
    const c = parseInt(count) || 0
    data.push({
      endpoint,
      count: c,
      percentage: stats.value.total > 0
        ? ((c / stats.value.total) * 100).toFixed(2) + '%'
        : '0%',
    })
  })
  return data.sort((a, b) => b.count - a.count)
})

const mpTableData = computed(() => {
  const data: any[] = []
  Object.entries(stats.value.mp_stats || {}).forEach(([mpId, count]) => {
    const c = parseInt(count) || 0
    data.push({
      mp_id: mpId,
      count: c,
      percentage: stats.value.total > 0
        ? ((c / stats.value.total) * 100).toFixed(2) + '%'
        : '0%',
    })
  })
  return data.sort((a, b) => b.count - a.count)
})

const disabledDate = (current: Date) => current && current > new Date()

const formatRequest = (request: Record<string, any> | undefined) => {
  if (!request || Object.keys(request).length === 0) return '—'
  return Object.entries(request)
    .map(([k, v]) => `${k}=${v}`)
    .join(', ')
}

const handleDateChange = (value: string) => {
  selectedDate.value = value || ''
}

const loadLogs = async () => {
  try {
    const res = await getRedfoxLogs(200, 0)
    logs.value = res.items || []
  } catch (err: any) {
    console.error('加载 redfox 日志失败', err)
  }
}

const loadStats = async () => {
  loading.value = true
  try {
    const date = selectedDate.value || new Date().toISOString().split('T')[0]
    const result = await getRedfoxStats(date)
    stats.value = {
      date: result.date || date,
      total: result.total || 0,
      success: result.success || 0,
      failed: result.failed || 0,
      endpoints: result.endpoints || {},
      mp_stats: result.mp_stats || {},
      recent_logs: result.recent_logs || [],
    }
    if (stats.value.total === 0) {
      Message.info('该日期暂无 redfox 调用记录')
    }
  } catch (err: any) {
    Message.error(err?.message || '加载统计失败')
  } finally {
    loading.value = false
  }
}

const loadToday = async () => {
  selectedDate.value = ''
  await loadStats()
}

const refresh = async () => {
  await Promise.all([loadStats(), loadLogs(), loadDailyStats()])
}

const loadDailyStats = async () => {
  trendLoading.value = true
  try {
    const res = await getRedfoxDailyStats(trendDays.value)
    dailyStats.value = res.items || []
  } catch (err: any) {
    console.error('加载 redfox 每日统计失败', err)
    Message.error(err?.message || '加载每日统计失败')
    dailyStats.value = []
  } finally {
    trendLoading.value = false
  }
}

const switchTrend = (days: number) => {
  if (trendDays.value === days) return
  trendDays.value = days
  loadDailyStats()
}

const handleClear = async () => {
  clearing.value = true
  try {
    const res = await clearRedfoxLogs()
    if (res) {
      Message.success('已清空 redfox 调用日志')
      await refresh()
    } else {
      Message.error('清空失败')
    }
  } catch (err: any) {
    Message.error(err?.message || '清空失败')
  } finally {
    clearing.value = false
  }
}

onMounted(() => {
  refresh()
})
</script>

<style scoped>
.redfox-logs {
  padding: 16px;
}

.stats-card {
  margin-bottom: 16px;
  border-radius: 8px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
  transition: all 0.3s ease;
}

.stats-card:hover {
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
}

.stats-card-title {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.stats-card-title-prefix {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  font-size: 12px;
  font-weight: 500;
  line-height: 18px;
  color: #ffffff;
  background: #165dff;
  border-radius: 4px;
}

.stats-card-date-tag {
  margin-left: 4px;
}

:deep(.arco-statistic-title) {
  font-size: 14px;
  margin-bottom: 8px;
}

:deep(.arco-statistic-content) {
  font-size: 24px;
}

:deep(.arco-table-wrapper) {
  margin-top: -8px;
}

.request-cell {
  display: inline-block;
  max-width: 280px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: middle;
}

.error-cell {
  color: #f53f3f;
  font-size: 12px;
}

.muted {
  color: #c9cdd4;
}

.trend-loading,
.trend-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 160px;
  color: #86909c;
  font-size: 13px;
}

.trend-switch {
  display: inline-flex;
  align-items: center;
  padding: 2px;
  background: #f2f3f5;
  border-radius: 6px;
  border: 1px solid #e5e6eb;
}

.trend-switch-btn {
  appearance: none;
  border: 0;
  background: transparent;
  padding: 4px 12px;
  font-size: 13px;
  line-height: 20px;
  color: #4e5969;
  cursor: pointer;
  border-radius: 4px;
  transition: background 0.2s ease, color 0.2s ease, box-shadow 0.2s ease;
}

.trend-switch-btn:hover:not(.active) {
  color: #1d2129;
}

.trend-switch-btn.active {
  background: #ffffff;
  color: #165dff;
  font-weight: 500;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.06);
}

.trend-switch-btn + .trend-switch-btn {
  margin-left: 2px;
}

.trend-summary {
  display: flex;
  gap: 24px;
  flex-wrap: wrap;
  margin-bottom: 12px;
  font-size: 13px;
  color: #4e5969;
}

.trend-summary-item strong {
  margin: 0 4px;
  font-weight: 600;
  color: #1d2129;
}

.trend-summary-label {
  color: #86909c;
  font-size: 12px;
  margin-right: 4px;
}

.trend-chart {
  display: flex;
  align-items: stretch;
  gap: 4px;
  padding: 8px 4px 4px;
  border-bottom: 1px solid #e5e6eb;
  overflow-x: auto;
}

.trend-bar-cell {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-end;
  min-width: 24px;
  height: 100%;
  flex: 0 0 auto;
}

.trend-bar-cell.wide {
  flex: 1 0 auto;
}

.trend-bar-wrapper {
  width: 100%;
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  align-items: flex-end;
  justify-content: center;
}

.trend-bar {
  width: 60%;
  min-width: 8px;
  max-width: 24px;
  border-radius: 3px 3px 0 0;
  transition: height 0.25s ease;
}

.trend-bar-value {
  font-size: 11px;
  color: #1d2129;
  margin-top: 4px;
  line-height: 1;
}

.trend-bar-value.muted {
  color: #c9cdd4;
}

.trend-bar-label {
  font-size: 11px;
  color: #86909c;
  margin-top: 4px;
  line-height: 1;
}

.trend-bar-label.today-label {
  color: #165dff;
  font-weight: 600;
}
</style>
