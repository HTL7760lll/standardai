import axios from 'axios'

const baseURL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

const api = axios.create({
  baseURL,
  timeout: 120000,
})

// 自动注入 Token
api.interceptors.request.use(config => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = 'Bearer ' + token
  }
  return config
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
  const token = localStorage.getItem('token')
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { 'Authorization': 'Bearer ' + token } : {}),
    },
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

// ── 统计 ──
export function getDocumentStats() {
  return api.get('/documents/stats')
}

export function searchDocuments(keyword, page = 1, pageSize = 5) {
  return api.get('/documents/search', { params: { keyword, page, page_size: pageSize } })
}

export function deleteDocument(documentId) {
  return api.delete(`/documents/${documentId}`)
}

// 标注
export function createAnnotation(data) {
  return api.post('/annotations', data)
}

// 起草辅助
export function getClauses(documentId) {
  return api.get(`/documents/${documentId}/clauses`)
}
export function draftCheck(documentId, data) {
  return api.post(`/documents/${documentId}/draft-check`, data)
}

// 引用图谱
export function getCitationGraph() {
  return api.get('/documents/citations/graph')
}

/**
 * SSE 流式 Agent 问答（工具调用版）
 * 事件类型比 askStream 多：
 *   { type: 'tool_call', name, arguments, status: 'calling' }
 *   { type: 'tool_status', name, status: 'executing' }
 *   { type: 'tool_result', name, result_preview }
 * 其余同 askStream
 */
export async function* askAgentStream(payload) {
  const url = `${baseURL}/ask/agent/stream`
  const token = localStorage.getItem('token')
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { 'Authorization': 'Bearer ' + token } : {}),
    },
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
    buffer = lines.pop()

    for (const line of lines) {
      const trimmed = line.trim()
      if (trimmed.startsWith('data: ')) {
        try {
          yield JSON.parse(trimmed.slice(6))
        } catch {
          // ignore parse errors
        }
      }
    }
  }
}

// 认证
export function login(data) {
  return api.post('/auth/login', data)
}
export function register(data) {
  return api.post('/auth/register', data)
}

export default api
