import http from './http'

// 小红书订阅 / 笔记 / 用户搜索接口

export type XhsKind = 'keyword' | 'account'

export interface XhsFeed {
  id: string
  name: string
  cover: string
  intro: string
  status: number  // 0=禁用, 1=启用
  kind: XhsKind
  target: string
  max_fetch_count: number
  refresh_interval_hours: number
  last_publish_time: number
  last_cursor: string
  sync_time: number
  error_count: number
  last_error: string
  last_error_at: number
  created_at: string
  updated_at: string
}

export interface XhsFeedListResult {
  code: number
  data: {
    list: XhsFeed[]
    total: number
  }
}

export interface CreateXhsFeedParams {
  kind: XhsKind
  target: string
  name?: string
  avatar?: string
  intro?: string
  max_fetch_count?: number
  refresh_interval_hours?: number
}

export interface UpdateXhsFeedParams {
  name?: string
  avatar?: string
  intro?: string
  max_fetch_count?: number
  refresh_interval_hours?: number
  status?: number
}

export interface XhsArticle {
  id: string
  feed_id: string
  title: string
  content: string
  pic_url: string
  url: string
  publish_time: number
  author: string
  author_id: string
  image_urls: string
  liked_count: number
  comments_count: number
  collected_count: number
  read_count: number
  share_count: number
  status: number
}

export interface XhsArticleListResult {
  code: number
  data: {
    list: XhsArticle[]
    total: number
  }
}

export interface XhsUser {
  // 字段命名取自 redfox /search/users 返回结构 (具体字段名以实际为准)
  userId?: string
  user_id?: string
  id?: string
  nickname?: string
  avatar?: string
  fans?: number
  [k: string]: any
}

export interface XhsUserSearchResult {
  code: number
  data: {
    list: XhsUser[]
    total: number
    has_more: boolean
  }
}

// ===== 订阅列表 / CRUD =====

export const listXhsFeeds = (params?: {
  kind?: XhsKind
  status?: number
  page?: number
  pageSize?: number
}) => {
  const apiParams = {
    offset: (params?.page || 0) * (params?.pageSize || 10),
    limit: params?.pageSize || 10,
    ...(params?.kind ? { kind: params.kind } : {}),
    ...(params?.status !== undefined && params?.status !== null ? { status: params.status } : {}),
  }
  return http.get<XhsFeedListResult>('/xhs/feeds', { params: apiParams })
}

export const getXhsFeed = (feed_id: string) => {
  return http.get<{ code: number; data: XhsFeed }>(`/xhs/feeds/${encodeURIComponent(feed_id)}`)
}

export const createXhsFeed = (data: CreateXhsFeedParams) => {
  return http.post<{ code: number; data: XhsFeed; message: string }>('/xhs/feeds', data)
}

export const updateXhsFeed = (feed_id: string, data: UpdateXhsFeedParams) => {
  return http.put<{ code: number; data: XhsFeed; message: string }>(
    `/xhs/feeds/${encodeURIComponent(feed_id)}`,
    data,
  )
}

export const deleteXhsFeed = (feed_id: string) => {
  return http.delete<{ code: number; message: string; data: { id: string; deleted_articles: number } }>(
    `/xhs/feeds/${encodeURIComponent(feed_id)}`,
  )
}

export const triggerXhsSync = (feed_id: string) => {
  return http.post<{ code: number; message: string }>(
    `/xhs/feeds/${encodeURIComponent(feed_id)}/sync`,
    {},
  )
}

// ===== 笔记列表 =====

export const listXhsFeedArticles = (feed_id: string, params?: { page?: number; pageSize?: number }) => {
  const apiParams = {
    offset: (params?.page || 0) * (params?.pageSize || 20),
    limit: params?.pageSize || 20,
  }
  return http.get<XhsArticleListResult>(
    `/xhs/feeds/${encodeURIComponent(feed_id)}/articles`,
    { params: apiParams },
  )
}

// ===== 用户搜索 (账号订阅前置) =====

export const searchXhsUsers = (keyword: string, offset = 0) => {
  return http.post<XhsUserSearchResult>('/xhs/search-users', { keyword, offset })
}
