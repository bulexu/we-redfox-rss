import http from './http'

export type ForeignPlatform = 'tiktok' | 'youtube' | 'instagram'

export interface ForeignFeed {
  id: string; name: string; cover: string; intro: string; status: number
  kind: 'keyword'; target: string; max_fetch_count: number
  refresh_interval_hours: number; last_publish_time: number; last_cursor: string
  sync_time: number; error_count: number; last_error: string
  last_error_at: number; created_at: string; updated_at: string
}

export interface ForeignArticle {
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

export const listForeignFeeds = (platform: ForeignPlatform, params?: { status?: number; kw?: string; page?: number; pageSize?: number }) =>
  http.get(`/${platform}/feeds`, { params: {
    ...paging({ page: params?.page, pageSize: params?.pageSize || 10 }),
    ...(params?.status !== undefined ? { status: params.status } : {}),
    ...(params?.kw ? { kw: params.kw } : {}),
  } })

export const createForeignFeed = (platform: ForeignPlatform, data: {
  kind: 'keyword'; target: string; name?: string; avatar?: string; intro?: string
  max_fetch_count?: number; refresh_interval_hours?: number
}) => http.post(`/${platform}/feeds`, data)

export const updateForeignFeed = (platform: ForeignPlatform, feedId: string, data: {
  name?: string; avatar?: string; intro?: string; max_fetch_count?: number
  refresh_interval_hours?: number; status?: number
}) => http.put(`/${platform}/feeds/${encodeURIComponent(feedId)}`, data)

export const deleteForeignFeed = (platform: ForeignPlatform, feedId: string) =>
  http.delete(`/${platform}/feeds/${encodeURIComponent(feedId)}`)

export const triggerForeignSync = (platform: ForeignPlatform, feedId: string) =>
  http.post(`/${platform}/feeds/${encodeURIComponent(feedId)}/sync`, {})

export const listForeignArticles = (platform: ForeignPlatform, params?: { page?: number; pageSize?: number; search?: string }) =>
  http.get(`/${platform}/articles`, { params: { ...paging(params), search: params?.search } })

export const listForeignFeedArticles = (
  platform: ForeignPlatform,
  feedId: string,
  params?: { page?: number; pageSize?: number; search?: string },
) => http.get(`/${platform}/feeds/${encodeURIComponent(feedId)}/articles`, {
  params: { ...paging(params), search: params?.search },
})
