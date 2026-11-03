import http from './http'
import type { Tag, TagCreate } from '@/types/tagManagement'

export const listTags = (params?: { offset?: number; limit?: number }) => {
  return http.get<Tag[]>('/tags', { 
    params: {
      offset: params?.offset || 0,
      limit: params?.limit || 100
    }
  })
}

export const getTag = (id: string) => {
  return http.get<Tag>(`/tags/${id}`)
}

export const createTag = (data: TagCreate) => {
  return http.post('/tags', data)
}

export const updateTag = (id: string, data: TagCreate) => {
  return http.put(`/tags/${id}`, data)
}

export const deleteTag = (id: string) => {
  return http.delete(`/tags/${id}`)
}
