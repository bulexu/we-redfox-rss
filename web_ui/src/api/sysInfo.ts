import http from './http'

export const getSysInfo = async (): Promise<any> => {
  const data = await http.get('/sys/info')
  return data
}

export const getSysResources = async (): Promise<any> => {
  const data = await http.get('/sys/resources')
  return data
}

export const refreshArticleStats = async (): Promise<any> => {
  const data = await http.post('/sys/article/refresh')
  return data
}