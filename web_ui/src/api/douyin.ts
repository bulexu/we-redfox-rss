import http from './http'

export type DouyinKind = 'keyword'

export interface DouyinFeed {
  id: string
  name: string
  cover: string
  intro: string
  status: number
  kind: DouyinKind
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

export interface DouyinArticle {
  id: string
  feed_id: string
  feed_name?: string
  title: string
  description: string
  content: string
  pic_url: string
  url: string
  extinfo: string
  publish_time: number
  author: string
  author_id: string
  liked_count: number
  comments_count: number
  collected_count: number
  read_count: number
  share_count: number
}

const paging = (params?: { page?: number; pageSize?: number }) => ({
  offset: (params?.page || 0) * (params?.pageSize || 20),
  limit: params?.pageSize || 20,
})

export const listDouyinFeeds = (params?: {
  status?: number
  kw?: string
  page?: number
  pageSize?: number
}) => http.get('/douyin/feeds', {
  params: {
    ...paging({ page: params?.page, pageSize: params?.pageSize || 10 }),
    ...(params?.status !== undefined ? { status: params.status } : {}),
    ...(params?.kw ? { kw: params.kw } : {}),
  },
})

export const createDouyinFeed = (data: {
  kind: DouyinKind
  target: string
  name?: string
  avatar?: string
  intro?: string
  max_fetch_count?: number
  refresh_interval_hours?: number
}) => http.post('/douyin/feeds', data)

export const updateDouyinFeed = (feedId: string, data: {
  name?: string
  avatar?: string
  intro?: string
  max_fetch_count?: number
  refresh_interval_hours?: number
  status?: number
}) =>
  http.put(`/douyin/feeds/${encodeURIComponent(feedId)}`, data)

export const deleteDouyinFeed = (feedId: string) =>
  http.delete(`/douyin/feeds/${encodeURIComponent(feedId)}`)

export const triggerDouyinSync = (feedId: string) =>
  http.post(`/douyin/feeds/${encodeURIComponent(feedId)}/sync`, {})

export const listDouyinArticles = (params?: { page?: number; pageSize?: number; search?: string }) =>
  http.get('/douyin/articles', { params: { ...paging(params), search: params?.search } })

export const listDouyinFeedArticles = (
  feedId: string,
  params?: { page?: number; pageSize?: number; search?: string },
) => http.get(`/douyin/feeds/${encodeURIComponent(feedId)}/articles`, {
  params: { ...paging(params), search: params?.search },
})
