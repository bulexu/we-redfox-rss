import http from './http'

export interface BilibiliFeed {
  id: string; name: string; cover: string; intro: string; status: number
  kind: 'keyword'; target: string; max_fetch_count: number
  refresh_interval_hours: number; last_publish_time: number; last_cursor: string
  sync_time: number; error_count: number; last_error: string
  last_error_at: number; created_at: string; updated_at: string
}

export interface BilibiliArticle {
  id: string; feed_id: string; feed_name?: string; title: string
  description: string; content: string; pic_url: string; url: string
  extinfo: string; publish_time: number; author: string; author_id: string
  liked_count: number; comments_count: number; collected_count: number
  read_count: number; share_count: number
}

const paging = (params?: { page?: number; pageSize?: number }) => ({
  offset: (params?.page || 0) * (params?.pageSize || 20),
  limit: params?.pageSize || 20,
})

export const listBilibiliFeeds = (params?: { status?: number; kw?: string; page?: number; pageSize?: number }) =>
  http.get('/bilibili/feeds', { params: {
    ...paging({ page: params?.page, pageSize: params?.pageSize || 10 }),
    ...(params?.status !== undefined ? { status: params.status } : {}),
    ...(params?.kw ? { kw: params.kw } : {}),
  } })

export const createBilibiliFeed = (data: {
  kind: 'keyword'; target: string; name?: string; avatar?: string; intro?: string
  max_fetch_count?: number; refresh_interval_hours?: number
}) => http.post('/bilibili/feeds', data)

export const updateBilibiliFeed = (feedId: string, data: {
  name?: string; avatar?: string; intro?: string; max_fetch_count?: number
  refresh_interval_hours?: number; status?: number
}) => http.put(`/bilibili/feeds/${encodeURIComponent(feedId)}`, data)

export const deleteBilibiliFeed = (feedId: string) =>
  http.delete(`/bilibili/feeds/${encodeURIComponent(feedId)}`)

export const triggerBilibiliSync = (feedId: string) =>
  http.post(`/bilibili/feeds/${encodeURIComponent(feedId)}/sync`, {})

export const listBilibiliArticles = (params?: { page?: number; pageSize?: number; search?: string }) =>
  http.get('/bilibili/articles', { params: { ...paging(params), search: params?.search } })

export const listBilibiliFeedArticles = (
  feedId: string,
  params?: { page?: number; pageSize?: number; search?: string },
) => http.get(`/bilibili/feeds/${encodeURIComponent(feedId)}/articles`, {
  params: { ...paging(params), search: params?.search },
})
