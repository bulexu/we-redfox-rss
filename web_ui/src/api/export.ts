import http from './http'

export const ExportOPML = () => {
  return http.get<{code: number, data: string}>('/export/mps/opml', {
    params: {
      limit: 1000,
      offset: 0
    }
  })
}

export const ExportMPS = () => {
  return http.get('/export/mps/export', {
    params: { limit: 1000, offset: 0 },
    responseType: 'blob',
  });
};

export const ImportMPS = (formData: FormData) => {
  return http.post<{code: number, data: string}>('/export/mps/import', formData, {
    headers: {
      'Content-Type': 'multipart/form-data'
    }
  })
}

export const ExportTags = () => {
  return http.get('/export/tags', {
    params: { limit: 1000, offset: 0 },
    responseType: 'blob',
  });
};

export const ImportTags = (formData: FormData) => {
  return http.post<{code: number, data: string}>('/export/tags/import', formData, {
    headers: {
      'Content-Type': 'multipart/form-data'
    }
  })
}