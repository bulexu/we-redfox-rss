import http from './http'

// 兼容新旧参数名 (mp_id 是后端约定,feed_id 是前端约定)
const resolveFeedId = (params: any): string => {
  return params?.feed_id ?? params?.mp_id ?? ''
}

export const exportArticles = (params:any) => {
    const requestData = {
      mp_id: resolveFeedId(params),
      doc_id: params.scope === 'selected' ? params.ids : [],
      page_size: params.limit||10,
      page_count: params.page_count || 1,
      add_title: params.add_title || true,
      remove_images: params.remove_images || false,
      remove_links: params.remove_links || false,
      export_md: params.format.includes('md'),
      export_docx: params.format.includes('docx'),
      export_json: params.format.includes('json'),
      export_csv: params.format.includes('csv'),
      export_pdf: params.format.includes('pdf'),
      zip_filename: params.zip_filename||''
    };
  return http.post<{code: number, data: string}>('/wx/tools/export/articles', requestData, {
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'application/json',
      'X-Requested-With': 'XMLHttpRequest'
    }
  })
}
export const getExportRecords = (params:any) => {
    const requestData = {
      mp_id: resolveFeedId(params),
    };
  return http.get<{code: number, data: string}>('/wx/tools/export/list', {params:requestData})
}
export const DeleteExportRecords = (params:any) => {
    const requestData = {
      mp_id: resolveFeedId(params),
      filename: params.filename,
    };
  return http.delete<{code: number, data: string}>('/wx/tools/export/delete', {data:requestData})
}