import axios from 'axios'

const baseURL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

const api = axios.create({
  baseURL,
  timeout: 120000,
})

// ── 文档管理 ──
export function getDocuments(params = {}) {
  return api.get('/documents', { params })
}

export function uploadDocument(formData) {
  return api.post('/documents/upload', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  })
}

export function generateChunks(documentId) {
  return api.post(`/documents/${documentId}/chunks`)
}

export function analyzeDocument(documentId) {
  return api.post(`/documents/${documentId}/analyze`)
}

// ── 问答 ──
export function askQuestion(payload) {
  return api.post('/ask', payload)
}

/**
 * SSE 流式问答
 * 返回 async iterable，每次 yield 一个事件对象：
 *   { type: 'meta', references, recommendations, follow_up_questions }
 *   { type: 'token', content: '...' }
 *   { type: 'done', full_answer_length }
 *   { type: 'error', message }
 */
export async function* askStream(payload) {
  const url = `${baseURL}/ask/stream`
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}: ${response.statusText}`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop()  // 保留不完整的最后一行

    for (const line of lines) {
      const trimmed = line.trim()
      if (trimmed.startsWith('data: ')) {
        try {
          yield JSON.parse(trimmed.slice(6))
        } catch {
          // 忽略解析失败的行
        }
      }
    }
  }
}

// ── 标准动态监控 ──
export function getStandardsStatus(params = {}) {
  return api.get('/standards/watchdog', { params })
}

export function getStandardDetail(versionId) {
  return api.get(`/standards/watchdog/${versionId}`)
}

export function triggerStandardCheck(versionId) {
  return api.post(`/standards/watchdog/${versionId}/check`)
}

export function triggerBatchCheck() {
  return api.post('/standards/watchdog/batch-check')
}

export function updateStandardStatus(versionId, params) {
  return api.patch(`/standards/watchdog/${versionId}/status`, null, { params })
}

// ── 统计 ──
export function getDocumentStats() {
  return api.get('/documents/stats')
}

export function searchDocuments(keyword, page = 1, pageSize = 5) {
  return api.get('/documents/search', { params: { keyword, page, page_size: pageSize } })
}

export default api
