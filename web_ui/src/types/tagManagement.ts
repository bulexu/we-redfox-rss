export interface Tag {
  id: string
  name: string
  cover?: string | null
  intro?: string | null
  status: number
  feed_ids?: string  // JSON字符串
  created_at: string
  updated_at: string
}

export interface TagCreate {
  name: string
  cover?: string | null
  intro?: string | null
  status?: number
  feed_ids?: string  // JSON字符串
}