/**
 * src/api.js —— 统一后端接口封装
 * 契约：docs/开发过程/01-接口约定.md（第 3、4 节）
 * - baseURL = import.meta.env.VITE_API_BASE || 'http://localhost:8080/api'
 * - 自动附加 Authorization: Bearer <localStorage.ams_token>
 * - 统一响应 { success, message, data, code }，success=false 抛 ApiError
 * - 401 清除本地登录态并通过回调回到登录页
 * - userId / role 等不在此处处理，由调用方决定
 */

const DEFAULT_BASE = 'http://localhost:8080/api'
export const BASE_URL = (import.meta.env.VITE_API_BASE || DEFAULT_BASE).replace(/\/+$/, '')

export const TOKEN_KEY = 'ams_token'
export const USER_KEY = 'ams_user'

/** 普通请求超时：20s；AI 类请求超时：90s（与 AI 服务 LLM_TIMEOUT_SECONDS 对齐）；识图 60s */
export const DEFAULT_TIMEOUT = 20000
export const AI_TIMEOUT = 90000
export const VISION_TIMEOUT = 60000

export class ApiError extends Error {
  constructor(message, { code = null, status = 0, cause = null } = {}) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = status
    this.cause = cause
  }
}

let unauthorizedHandler = null
/** 注册 401 处理（App.vue 中用于回登录页） */
export function setUnauthorizedHandler(fn) {
  unauthorizedHandler = fn
}

export function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

export function getStoredUser() {
  try {
    const raw = localStorage.getItem(USER_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

export function saveAuth(token, user) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    if (user) localStorage.setItem(USER_KEY, JSON.stringify(user))
  } catch {
    /* 隐私模式下 localStorage 可能不可用，忽略 */
  }
}

export function saveUser(user) {
  try {
    if (user) localStorage.setItem(USER_KEY, JSON.stringify(user))
  } catch {
    /* ignore */
  }
}

export function clearAuth() {
  try {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
  } catch {
    /* ignore */
  }
}

export function isAiTimeout(err) {
  return err instanceof ApiError && err.code === 'TIMEOUT'
}

function buildQuery(params = {}) {
  const search = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') return
    if (Array.isArray(value)) {
      value.forEach((item) => {
        if (item !== undefined && item !== null && item !== '') search.append(key, item)
      })
      return
    }
    search.append(key, value)
  })
  const text = search.toString()
  return text ? `?${text}` : ''
}

function networkMessage(error) {
  if (error && (error.name === 'AbortError' || error.name === 'TimeoutError')) {
    return '请求超时：服务响应时间过长，请稍后重试。'
  }
  return `无法连接业务服务（${BASE_URL}）。请确认 Spring Boot 服务已在 8080 端口启动，然后重试。`
}

/**
 * 底层请求
 * @param {string} path 以 / 开头的接口路径
 * @param {{method?:string, body?:any, query?:object, timeout?:number}} options
 */
async function request(path, { method = 'GET', body, query, timeout = DEFAULT_TIMEOUT } = {}) {
  const url = BASE_URL + path + buildQuery(query)
  const headers = { Accept: 'application/json' }
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`

  let payloadBody
  if (typeof FormData !== 'undefined' && body instanceof FormData) {
    payloadBody = body
  } else if (body !== undefined && body !== null) {
    headers['Content-Type'] = 'application/json'
    payloadBody = JSON.stringify(body)
  }

  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeout)
  let response
  try {
    response = await fetch(url, {
      method,
      headers,
      body: payloadBody,
      signal: controller.signal,
    })
  } catch (error) {
    const timedOut = error && (error.name === 'AbortError' || error.name === 'TimeoutError')
    throw new ApiError(timedOut ? '请求超时：服务响应时间过长，请稍后重试。' : networkMessage(error), {
      code: timedOut ? 'TIMEOUT' : 'NETWORK_ERROR',
      status: 0,
      cause: error,
    })
  } finally {
    clearTimeout(timer)
  }

  const text = await response.text().catch(() => '')
  let payload = null
  if (text) {
    try {
      payload = JSON.parse(text)
    } catch {
      payload = null
    }
  }

  if (response.status === 401) {
    clearAuth()
    const message = (payload && payload.message) || '登录状态已过期，请重新登录。'
    if (unauthorizedHandler) unauthorizedHandler(message)
    throw new ApiError(message, { code: 'UNAUTHORIZED', status: 401 })
  }

  const failed = !response.ok || (payload && payload.success === false)
  if (failed) {
    const message =
      (payload && payload.message) ||
      (response.status === 403
        ? '没有访问权限（当前账号角色不允许访问该功能）。'
        : `请求失败（HTTP ${response.status}）`)
    throw new ApiError(message, {
      code: (payload && payload.code) || `HTTP_${response.status}`,
      status: response.status,
    })
  }

  if (payload && Object.prototype.hasOwnProperty.call(payload, 'success')) {
    return payload.data
  }
  if (payload === null) {
    const message = '服务返回内容无法解析（不是合法 JSON），请检查后端服务。'
    throw new ApiError(message, { code: 'BAD_RESPONSE', status: response.status })
  }
  return payload
}

/* ============================ 认证与用户 ============================ */
export const auth = {
  login(username, password) {
    return request('/auth/login', { method: 'POST', body: { username, password } })
  },
  /** v1.4 学生注册：{username, password, displayName, email?} → {token, expiresAt, user} */
  register({ username, password, displayName, email }) {
    const body = { username, password, displayName }
    if (email !== undefined && email !== null && String(email).trim()) body.email = String(email).trim()
    return request('/auth/register', { method: 'POST', body })
  },
  me() {
    return request('/auth/me')
  },
  logout() {
    return request('/auth/logout', { method: 'POST' })
  },
  changePassword(oldPassword, newPassword) {
    return request('/auth/password', { method: 'PUT', body: { oldPassword, newPassword } })
  },
  updateProfile(payload) {
    return request('/users/me', { method: 'PUT', body: payload })
  },
  /** v1.2 用户 AI 配置（本人）：返回 {enabled, baseUrl, model, hasApiKey, apiKeyMasked} */
  aiConfig() {
    return request('/profile/ai')
  },
  saveAiConfig(payload) {
    return request('/profile/ai', { method: 'PUT', body: payload })
  },
  clearAiConfig() {
    return request('/profile/ai', { method: 'DELETE' })
  },
}

/* ============================ 公共 ============================ */
export const common = {
  health() {
    return request('/health')
  },
  knowledgePoints() {
    return request('/meta/knowledge-points')
  },
  dictionaries() {
    return request('/meta/dictionaries')
  },
}

/* ============================ 学生端 ============================ */
export const student = {
  dashboard() {
    return request('/student/dashboard')
  },
  knowledgePoints() {
    return request('/student/knowledge-points')
  },
  records(params) {
    return request('/student/records', { query: params })
  },
  recordDetail(id) {
    return request(`/student/records/${encodeURIComponent(id)}`)
  },
  reports(params) {
    return request('/student/reports', { query: params })
  },
  reportDetail(id) {
    return request(`/student/reports/${encodeURIComponent(id)}`)
  },
  wrongQuestions(params) {
    return request('/student/wrong-questions', { query: params })
  },
  markWrongReviewed(id, reviewed = true) {
    return request(`/student/wrong-questions/${encodeURIComponent(id)}`, {
      method: 'PATCH',
      body: { reviewed },
    })
  },
  /** v1.2：conversationId 可空；为空时后端新建会话并返回 conversationId/mode/model/modelSource */
  chat({ message, imageUrl = null, conversationId = null }) {
    const body = { message, imageUrl }
    if (conversationId !== null && conversationId !== undefined && conversationId !== '') {
      body.conversationId = conversationId
    }
    return request('/chat', {
      method: 'POST',
      body,
      timeout: AI_TIMEOUT,
    })
  },
  /**
   * v1.3 图片答疑：multipart 字段 file，由 Java 转发 AI /vision/extract。
   * 返回 {ok, text, model, provider, message}；ok=false 时 message 可直接展示。
   */
  chatVision(file) {
    const form = new FormData()
    form.append('file', file)
    return request('/student/chat/vision', { method: 'POST', body: form, timeout: VISION_TIMEOUT })
  },
  /** v1.3 前置自测提交：{gateId, conversationId, answers:[{questionId, choice}]} */
  gateCheck({ gateId, conversationId, answers }) {
    return request('/student/gate/check', {
      method: 'POST',
      body: { gateId, conversationId: conversationId === undefined ? null : conversationId, answers },
      timeout: AI_TIMEOUT,
    })
  },
  /* ---------- v1.2 会话 ---------- */
  conversations(params) {
    return request('/conversations', { query: params })
  },
  conversation(id) {
    return request(`/conversations/${encodeURIComponent(id)}`)
  },
  createConversation(title = '') {
    return request('/conversations', { method: 'POST', body: title ? { title } : {} })
  },
  renameConversation(id, title) {
    return request(`/conversations/${encodeURIComponent(id)}`, { method: 'PATCH', body: { title } })
  },
  deleteConversation(id) {
    return request(`/conversations/${encodeURIComponent(id)}`, { method: 'DELETE' })
  },
  diagnoseStart({ mode = 'QUICK', focusKpIds = [] }) {
    return request('/diagnose/start', {
      method: 'POST',
      body: { mode, focusKpIds },
      timeout: AI_TIMEOUT,
    })
  },
  diagnoseSubmit(sessionId, answers) {
    return request(`/diagnose/${encodeURIComponent(sessionId)}/submit`, {
      method: 'POST',
      body: { answers },
      timeout: AI_TIMEOUT,
    })
  },
  practiceGenerate({ layer = 'A', count = 3, kpIds = [] }) {
    return request('/practice/generate', {
      method: 'POST',
      body: { layer, count, kpIds },
      timeout: AI_TIMEOUT,
    })
  },
  practiceHint({ batchId, questionId, studentAnswer = '' }) {
    return request('/practice/hint', {
      method: 'POST',
      body: { batchId, questionId, studentAnswer },
      timeout: AI_TIMEOUT,
    })
  },
  plansGenerate({ period = 'WEEK', days = 7, focusKpIds = [], goal = '' }) {
    return request('/plans/generate', {
      method: 'POST',
      body: { period, days, focusKpIds, goal },
      timeout: AI_TIMEOUT,
    })
  },
  plans(params) {
    return request('/plans', { query: params })
  },
  planDetail(id) {
    return request(`/plans/${encodeURIComponent(id)}`)
  },
  planDayDone(id, dayIndex, done) {
    return request(`/plans/${encodeURIComponent(id)}/days/${encodeURIComponent(dayIndex)}`, {
      method: 'PATCH',
      body: { done },
    })
  },
}

/* ============================ 教师端 ============================ */
export const teacher = {
  dashboard() {
    return request('/teacher/dashboard')
  },
  config() {
    return request('/teacher/config')
  },
  saveConfig(payload) {
    return request('/teacher/config', { method: 'PUT', body: payload })
  },
  configLogs(params) {
    return request('/teacher/config/logs', { query: params })
  },
  extractConfig(text) {
    return request('/teacher/config/extract', {
      method: 'POST',
      body: { text },
      timeout: AI_TIMEOUT,
    })
  },
  analysis(period = '7D') {
    return request('/teacher/analysis', { query: { period }, timeout: AI_TIMEOUT })
  },
  students() {
    return request('/teacher/students')
  },
  /** v1.4 教师重置本班学生密码：PUT /teacher/students/{id}/password → data=null */
  resetStudentPassword(studentId, newPassword) {
    return request(`/teacher/students/${encodeURIComponent(studentId)}/password`, {
      method: 'PUT',
      body: { newPassword },
    })
  },
  studentRecords(studentId, params) {
    return request(`/teacher/students/${encodeURIComponent(studentId)}/records`, { query: params })
  },
  knowledge() {
    return request('/teacher/knowledge')
  },
  uploadKnowledge(file, kb = 'KB4') {
    const form = new FormData()
    form.append('file', file)
    form.append('kb', kb)
    return request('/teacher/knowledge/upload', { method: 'POST', body: form, timeout: 60000 })
  },
  setKnowledgeEnabled(documentId, enabled) {
    return request(`/teacher/knowledge/${encodeURIComponent(documentId)}`, {
      method: 'PATCH',
      body: { enabled },
    })
  },
  deleteKnowledge(documentId) {
    return request(`/teacher/knowledge/${encodeURIComponent(documentId)}`, { method: 'DELETE' })
  },
  rebuildKnowledge() {
    return request('/teacher/knowledge/rebuild', { method: 'POST', timeout: 60000 })
  },
}

export const api = {
  ...auth,
  ...common,
  login: auth.login,
  me: auth.me,
  logout: auth.logout,
  health: common.health,
  knowledgePoints: common.knowledgePoints,
  dictionaries: common.dictionaries,
}

export default api
