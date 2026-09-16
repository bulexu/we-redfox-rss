import http from './http'

export interface LarkBitable {
  id: string
  name: string
  app_token: string
  table_id: string
  feed_ids: string[]
  field_mapping: Record<string, string>
  enabled: boolean
  last_pushed_at: number | null
  last_error: string | null
  last_error_at: number | null
  created_at: string | null
  updated_at: string | null
}

export interface LarkBitableListResp {
  list: LarkBitable[]
  total: number
  page: { limit: number; offset: number }
  allowed_field_keys: string[]
}

export interface CreateBitableRequest {
  name: string
  app_token: string
  table_id: string
  feed_ids: string[]
  field_mapping: Record<string, string>
  enabled: boolean
}

export interface UpdateBitableRequest {
  name?: string
  app_token?: string
  table_id?: string
  feed_ids?: string[]
  field_mapping?: Record<string, string>
  enabled?: boolean
}

export interface LarkFieldInfo {
  name: string
  type: number
  id: string
}

export interface TestBitableResp {
  ok: boolean
  code?: number | null
  message?: string | null
  field_count?: number
  fields?: LarkFieldInfo[]
}

export const listBitables = (params?: { enabled?: boolean; feed_id?: string; limit?: number; offset?: number }) => {
  return http.get<LarkBitableListResp>('/lark/bitables', { params })
}

export interface LarkStatus {
  enabled: boolean
  has_app_id: boolean
  has_app_secret: boolean
  bitable_count: number
  enabled_count: number
  token_ok: boolean | null
  issues: string[]
}

export const getLarkStatus = () => {
  return http.get<LarkStatus>('/lark/status')
}

export const createBitable = (data: CreateBitableRequest) => {
  return http.post<LarkBitable>('/lark/bitables', data)
}

export const getBitable = (id: string) => {
  return http.get<LarkBitable>(`/lark/bitables/${id}`)
}

export const updateBitable = (id: string, data: UpdateBitableRequest) => {
  return http.put<LarkBitable>(`/lark/bitables/${id}`, data)
}

export const deleteBitable = (id: string) => {
  return http.delete(`/lark/bitables/${id}`)
}

export const testBitable = (id: string) => {
  return http.post<TestBitableResp>(`/lark/bitables/${id}/test`)
}

export interface ManualPushItemResult {
  article_id: string
  ok: boolean
  error?: string
  already_pushed?: boolean
  previous_record_id?: string | null
}

export interface ManualPushResp {
  submitted: boolean
  bitable_id?: string
  total?: number
  submitted_count?: number
  results?: ManualPushItemResult[]
  // 单条模式下的兼容字段
  article_id?: string | null
  already_pushed?: boolean
  previous_record_id?: string | null
}

export const manualPush = (id: string, article_ids: string[]) => {
  return http.post<ManualPushResp>(`/lark/bitables/${id}/push`, {
    article_ids,
  })
}