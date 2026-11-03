import http from './http'
import type { ConfigManagement, ConfigManagementUpdate } from '@/types/configManagement'

export const listConfigs = (params?: { page?: number; pageSize?: number }) => {
  const apiParams = {
    offset: (params?.page || 0) * (params?.pageSize || 10),
    limit: params?.pageSize || 10
  }
  return http.get<ConfigManagement>('/configs', { params: apiParams })
}
export const getConfig = (key: string) => {
  return http.get<ConfigManagement>(`/configs/${key}`)
}



export const createConfig = (data: ConfigManagementUpdate) => {
  return http.post('/configs', data)
}

export const updateConfig = (key: string, data: ConfigManagementUpdate) => {
  return http.put(`/configs/${key}`, data)
}

export const deleteConfig = (key: string) => {
  return http.delete(`/configs/${key}`)
}