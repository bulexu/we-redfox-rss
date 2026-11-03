<script setup lang="ts">
import { ref, onMounted, nextTick } from 'vue'
const formRef = ref()
import { useRoute, useRouter } from 'vue-router'
import { getMessageTask, createMessageTask, updateMessageTask } from '@/api/messageTask'
import type { MessageTaskCreate } from '@/types/messageTask'
import cronExpressionPicker from '@/components/CronExpressionPicker.vue'
import FeedMultiSelect, { type FeedItem } from '@/components/FeedMultiSelect.vue'
import { Message } from '@arco-design/web-vue'
import ACodeEditor from '@/components/ACodeEditor.vue'
const route = useRoute()
const router = useRouter()
const loading = ref(false)
const isEditMode = ref(false)
const taskId = ref<string | null>(null)
const showCronPicker = ref(false)
const showMpSelector = ref(false)
const activeTab = ref('basic')

const platformOptions = [
  { label: '公众号', value: 'mp' },
  { label: '小红书', value: 'xhs' },
  { label: '抖音', value: 'dy' },
  { label: 'B站', value: 'bili' },
  { label: 'X', value: 'x' },
  { label: 'TikTok', value: 'tiktok' },
  { label: 'YouTube', value: 'youtube' },
  { label: 'Instagram', value: 'instagram' },
]

const parseList = (value: any): any[] => {
  if (Array.isArray(value)) return value
  if (!value) return []
  try {
    const parsed = JSON.parse(value)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

const cronPickerRef = ref<InstanceType<typeof cronExpressionPicker> | null>(null)
const mpSelectorRef = ref<InstanceType<typeof FeedMultiSelect> | null>(null)

const formData = ref<MessageTaskCreate>({
  name: '',
  message_type: 0,
  message_template: '',
  web_hook_url: '',
  headers: '',
  cookies: '',
  scope_type: 'all',
  target_platforms: [],
  target_feed_ids: [] as FeedItem[],
  status: 1,
  cron_exp: '*/5 * * * *'
})

const fetchTaskDetail = async (id: string) => {
  loading.value = true
  try {
    const res = await getMessageTask(id)
    const selectedFeeds = parseList(res.target_feed_ids)
    let scopeType = res.scope_type
    let targetPlatforms = parseList(res.target_platforms)
    // 兼容升级前创建的任务：具体订阅优先；空列表仍按旧 platform 的整个平台处理。
    if (!['all', 'platforms', 'custom'].includes(scopeType)) {
      if (selectedFeeds.length) {
        scopeType = 'custom'
      } else {
        scopeType = 'platforms'
        const legacyPlatform = ['wechat', 'wx', 'weixin'].includes(res.platform) ? 'mp' : res.platform
        targetPlatforms = legacyPlatform ? [legacyPlatform] : ['mp']
      }
    }
    formData.value = {
      name: res.name || '',
      message_type: res.message_type || 0,
      message_template: res.message_template || '',
      web_hook_url: res.web_hook_url || '',
      headers: res.headers || '',
      cookies: res.cookies || '',
      scope_type: scopeType,
      target_platforms: targetPlatforms,
      target_feed_ids: selectedFeeds,
      status: res.status || 0,
      cron_exp: res.cron_exp || '*/5 * * * *'
    }
    // 初始化选择器数据
    nextTick(() => {
      if (cronPickerRef.value) {
        cronPickerRef.value.parseExpression(formData.value.cron_exp)
      }
      if (mpSelectorRef.value) {
        mpSelectorRef.value.parseSelected(formData.value.target_feed_ids)
      }
    })
  } finally {
    loading.value = false
  }
}

const handleSubmit = async () => {
  try {
    // 表单验证

  loading.value = true

  // 表单验证
  try {
    await formRef.value.validate()
  } catch (error) {
    Message.error(error?.errors?.join('\n') || '表单验证失败，请检查输入内容')
    loading.value = false
    return
  }

  if (formData.value.scope_type === 'platforms' && !formData.value.target_platforms?.length) {
    Message.error('请至少选择一个平台')
    loading.value = false
    return
  }
  if (formData.value.scope_type === 'custom' && !formData.value.target_feed_ids?.length) {
    Message.error('请至少选择一个具体订阅')
    loading.value = false
    return
  }


    loading.value = true
    // 后端 Pydantic 已直接命名为 target_feed_ids (commit 1 改名 mps_id → target_feed_ids),
    // 这里直接传 JSON 字符串,不再做 Pydantic→ORM 字段映射。
    const submitData: MessageTaskCreate = {
      ...formData.value,
      target_platforms: JSON.stringify(
        formData.value.scope_type === 'platforms' ? formData.value.target_platforms : []
      ),
      target_feed_ids: JSON.stringify(
        formData.value.scope_type === 'custom' ? formData.value.target_feed_ids : []
      ),
    }

    if (isEditMode.value && taskId.value) {
      await updateMessageTask(taskId.value, submitData)
      Message.success('更新任务成功，点击应用按钮后任务才会生效')
    } else {
      await createMessageTask(submitData)
      Message.success('创建任务成功，点击应用按钮后任务才会生效')
    }
    setTimeout(() => {
      router.push('/feedops/message-tasks')
    }, 1500)
  } catch (error) {
    console.error(error)
  } finally {
    loading.value = false
  }
}
const rules = {
  name: [
    { required: true, message: '请输入任务名称' },
    { min: 2, max: 30, message: '公众号名称长度应在2-30个字符之间' }
  ],
  description: [
    { max: 200, message: '描述不能超过200个字符' }
  ]
}
onMounted(() => {
  if (route.params.id) {
    isEditMode.value = true
    taskId.value = Array.isArray(route.params.id) ? route.params.id[0] : route.params.id
    if (taskId.value) {
      fetchTaskDetail(taskId.value)
    }
  }
})
</script>

<template>
  <a-spin :loading="loading">
    <div class="message-task-form">
      <h2>{{ isEditMode ? '编辑消息任务' : '添加消息任务' }}</h2>
      
      <a-form :model="formData" @submit="handleSubmit" ref="formRef"   :rules="rules">
        <a-tabs v-model:active-key="activeTab" type="card">
          <!-- 基本配置 -->
          <a-tab-pane key="basic" title="基本配置">
            <a-form-item label="任务名称" field="name" required>
              <a-input
                v-model="formData.name"
                placeholder="请输入任务名称"
              />
            </a-form-item>

            <a-form-item label="类型" field="message_type">
              <a-radio-group v-model="formData.message_type" type="button">
                <a-radio :value="0">Message</a-radio>
                <a-radio :value="1">WebHook</a-radio>
              </a-radio-group>
            </a-form-item>


            <a-form-item label="消息模板" field="message_template">
              <a-code-editor
                v-model="formData.message_template"
                placeholder="请输入消息模板内容"
                language="custom"
              />
              <a-button v-if="formData.message_type === 0"
                type="outline"
                style="margin-top: 8px"
                @click="formData.message_template = '### {{feed.mp_name}} 订阅消息：\n{% if articles %}\n{% for article in articles %}\n- [**{{ article.title }}**]({{article.url}}) ({{ article.publish_time }})\n{% endfor %}\n{% else %}\n- 暂无文章\n{% endif %}'">
                使用示例消息模板
              </a-button>
              <a-button v-else
                type="outline"
                style="margin-top: 8px"
                @click="formData.message_template = `{
    'articles': [
    {% for article in articles %}
    {{article}}
    {% if not loop.last %},{% endif %}
    {% endfor %}
    ]
}`">

                使用示例WebHook模板
              </a-button>
            </a-form-item>

            <a-form-item label="WebHook地址" field="web_hook_url">
              <a-input
                v-model="formData.web_hook_url"
                placeholder="请输入WebHook地址"
              />
              <a-link href="https://open.dingtalk.com/document/orgapp/obtain-the-webhook-address-of-a-custom-robot" target="_blank">如何获取WebHook</a-link>
            </a-form-item>

            <a-form-item label="Cron表达式" field="cron_exp" required>
              <a-space>
                <a-input
                  v-model="formData.cron_exp"
                  placeholder="请输入Cron表达式"
                  readonly
                  style="width: 300px"
                />
                <a-button @click="showCronPicker = true">选择</a-button>
              </a-space>
            </a-form-item>

            <a-form-item label="抓取范围" field="scope_type">
              <a-radio-group v-model="formData.scope_type" type="button">
                <a-radio value="all">全选</a-radio>
                <a-radio value="platforms">按平台选择</a-radio>
                <a-radio value="custom">自定义选择</a-radio>
              </a-radio-group>
              <template #extra>
                <span v-if="formData.scope_type === 'all'">抓取所有平台中已启用的全部订阅</span>
                <span v-else-if="formData.scope_type === 'platforms'">抓取所选平台中已启用的全部订阅</span>
                <span v-else>只抓取关联订阅中选中的具体订阅</span>
              </template>
            </a-form-item>

            <a-form-item
              v-if="formData.scope_type === 'platforms'"
              label="选择平台"
              field="target_platforms"
              required
            >
              <a-checkbox-group v-model="formData.target_platforms">
                <a-space wrap>
                  <a-checkbox
                    v-for="item in platformOptions"
                    :key="item.value"
                    :value="item.value"
                  >{{ item.label }}</a-checkbox>
                </a-space>
              </a-checkbox-group>
            </a-form-item>

            <a-form-item
              v-if="formData.scope_type === 'custom'"
              label="关联订阅"
              field="target_feed_ids"
              required
            >
              <a-space>
                <a-input
                  :model-value="(formData.target_feed_ids||[]).map((mp: any) => mp.id?.toString() || mp.toString()).join(',')"
                  placeholder="请选择一个或多个平台中的具体订阅"
                  readonly
                  style="width: 300px"
                />
                <a-button @click="showMpSelector = true">选择</a-button>
              </a-space>
            </a-form-item>

            <a-form-item label="状态" field="status">
              <a-radio-group v-model="formData.status" type="button">
                <a-radio :value="1">启用</a-radio>
                <a-radio :value="0">禁用</a-radio>
              </a-radio-group>
            </a-form-item>
          </a-tab-pane>

          <!-- 高级配置 -->
          <a-tab-pane key="advanced" title="高级配置">
            <a-alert type="info" style="margin-bottom: 16px;">
              用于配置需要认证的WebHook接口
            </a-alert>

            <a-form-item label="Headers (JSON)" field="headers">
              <a-textarea
                v-model="formData.headers"
                placeholder='{"Authorization": "Bearer token", "Content-Type": "application/json"}'
                :auto-size="{ minRows: 4, maxRows: 8 }"
              />
              <template #extra>用于认证的自定义请求头，格式为JSON</template>
            </a-form-item>

            <a-form-item label="Cookies" field="cookies">
              <a-textarea
                v-model="formData.cookies"
                placeholder="session_id=xxx; token=yyy"
                :auto-size="{ minRows: 4, maxRows: 8 }"
              />
              <template #extra>用于认证的Cookie字符串</template>
            </a-form-item>
          </a-tab-pane>
        </a-tabs>

        <a-form-item style="margin-top: 24px;">
          <a-space>
            <a-button html-type="submit" type="primary" :loading="loading">
              提交
            </a-button>
            <a-button @click="router.go(-1)">取消</a-button>
          </a-space>
        </a-form-item>
      </a-form>

      <!-- cron表达式选择器模态框 -->
      <a-modal
        v-model:visible="showCronPicker"
        title="选择Cron表达式"
        :footer="false"
        width="800px"
      >
        <cronExpressionPicker 
          ref="cronPickerRef"
          v-model="formData.cron_exp"
        />
        <template #footer>
          <a-button type="primary" @click="showCronPicker = false">确定</a-button>
        </template>
      </a-modal>

      <!-- 订阅选择器模态框 -->
      <a-modal
        v-model:visible="showMpSelector"
        title="选择订阅"
        :footer="false"
        width="800px"
      >
        <FeedMultiSelect
          ref="mpSelectorRef"
          v-model="formData.target_feed_ids"
        />
        <template #footer>
          <a-button type="primary" @click="showMpSelector = false">确定</a-button>
        </template>
      </a-modal>
    </div>
  </a-spin>
</template>

<style scoped>
.message-task-form {
  width: 90%;
  margin: 0 auto;
}

h2 {
  margin-bottom: 20px;
  color: var(--color-text-1);
}
</style>
