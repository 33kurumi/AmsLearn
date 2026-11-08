/**
 * utils/aiMode.js —— v1.2 AI 模式解析（顶栏徽标 / 登录页 / 答疑页共用）
 *
 * 数据来源：
 *   GET /api/health 的 data（v1.2 Java 透传）：
 *     mode: 'real' | 'mock'
 *     model: 'deepseek-flash' 等
 *     modelSource: 'system' | 'user' | 'mock' | 'none'（v1.2；none 表示规则硬拦截、本次未调用大模型；旧后端可能缺失）
 *     embeddingProvider / embeddingModel / supportsUserKey
 *   GET /api/profile/ai 的 data（可选第二参数，登录后由 App.vue 拉取）：
 *     { enabled, baseUrl, model, hasApiKey, apiKeyMasked }
 *     当 enabled=true 且 hasApiKey=true 时，徽标 Key 来源显示「我的 Key」。
 * 旧后端缺失字段 / 接口 404 时做降级推断，绝不抛错。
 */

function pickString(...values) {
  for (const value of values) {
    if (typeof value === 'string' && value.trim()) return value.trim()
  }
  return ''
}

function pickBoolean(...values) {
  for (const value of values) {
    if (typeof value === 'boolean') return value
  }
  return false
}

/** 归一化 /api/profile/ai 返回；仅「已启用 + 已保存 Key」视为生效 */
function normalizeUserAiConfig(userConfig) {
  if (!userConfig || typeof userConfig !== 'object') return null
  const enabled = userConfig.enabled === true || userConfig.enabled === 'true'
  const hasApiKey = userConfig.hasApiKey === true || userConfig.hasApiKey === 'true'
  if (!enabled || !hasApiKey) return null
  return {
    model: pickString(userConfig.model),
    baseUrl: pickString(userConfig.baseUrl),
    apiKeyMasked: pickString(userConfig.apiKeyMasked, userConfig.api_key_masked),
  }
}

/** 从 health 数据中提取 AI 运行状态；userAiConfig 可选（/api/profile/ai 的 data） */
export function readAiStatus(health, userAiConfig = null) {
  if (!health || typeof health !== 'object') {
    return {
      mode: 'unknown',
      available: false,
      model: '',
      modelSource: '',
      keySource: '',
      userKeyActive: false,
      embeddingProvider: '',
      embeddingModel: '',
      supportsUserKey: false,
      tone: 'gray',
      label: 'AI 状态未知',
      detail: '未获取到服务状态',
    }
  }
  const vector = health.vector && typeof health.vector === 'object' ? health.vector : {}
  const rawMode = pickString(health.mode, health.aiMode).toLowerCase()
  let model = pickString(health.model, health.llmModel, health.modelName)
  let modelSource = pickString(health.modelSource, health.model_source).toLowerCase()
  const mode = rawMode === 'real' || rawMode === 'mock' ? rawMode : model ? 'real' : 'unknown'
  if (!modelSource) {
    if (mode === 'mock') modelSource = 'mock'
    else if (mode === 'real') modelSource = 'system'
  }

  // 个人 Key 生效时覆盖 Key 来源（仅 real 模式且非规则拦截；mock / 规则拦截未调用大模型，不显示「我的 Key」）
  const userAi = normalizeUserAiConfig(userAiConfig)
  const userKeyActive = !!(userAi && mode === 'real' && modelSource !== 'none')
  if (userKeyActive) {
    modelSource = 'user'
    if (userAi.model) model = userAi.model
  }

  const embeddingProvider = pickString(
    health.embeddingProvider,
    health.embedding_provider,
    vector.provider,
    health.vectorProvider
  )
  const embeddingModel = pickString(
    health.embeddingModel,
    health.embedding_model,
    vector.embedding,
    health.embedding
  )
  const supportsUserKey = pickBoolean(health.supportsUserKey, health.supports_user_key)

  let tone = 'gray'
  let label = 'AI 状态未知'
  if (mode === 'mock') {
    tone = 'amber'
    label = 'mock'
  } else if (mode === 'real') {
    tone = 'green'
    const keyText =
      modelSource === 'user'
        ? '我的 Key'
        : modelSource === 'mock'
          ? 'mock'
          : modelSource === 'none'
            ? '规则拦截'
            : '系统 Key'
    // 后端未上报模型名时只显示模式与 Key 来源，避免展示不准确的模型名
    label = model ? 'real · ' + model + ' · ' + keyText : 'real · ' + keyText
  }

  const detailParts = []
  detailParts.push(mode === 'unknown' ? 'AI 模式未知' : mode === 'mock' ? 'AI 服务处于 mock 模式（未调用真实大模型）' : 'AI 服务已接入真实大模型')
  if (model) detailParts.push('模型：' + model)
  else if (mode === 'real') detailParts.push('模型：后端未上报（/api/health 缺少 model 字段）')
  if (modelSource === 'none') {
    detailParts.push('本次为规则拦截，未调用大模型')
  } else if (modelSource) {
    if (modelSource === 'user') {
      detailParts.push(
        'Key 来源：我的 Key（个人信息中已配置' +
          (userAi && userAi.apiKeyMasked ? '，' + userAi.apiKeyMasked : '') +
          '）'
      )
    } else {
      detailParts.push('Key 来源：' + (modelSource === 'mock' ? 'mock（未调用）' : '系统默认 Key'))
    }
  }
  if (userAi && mode === 'mock') detailParts.push('个人信息中已配置个人 Key，但当前 mock 模式未调用')
  if (embeddingProvider) detailParts.push('Embedding：' + embeddingProvider + (embeddingModel ? '（' + embeddingModel + '）' : ''))
  if (supportsUserKey) detailParts.push('支持在个人信息中配置自己的 Key')

  return {
    mode,
    available: mode !== 'unknown',
    model,
    modelSource,
    keySource: modelSource,
    userKeyActive,
    embeddingProvider,
    embeddingModel,
    supportsUserKey,
    tone,
    label,
    detail: detailParts.join(' · '),
  }
}

/** 回答底部小标签：mode + modelSource */
export function answerModeTags(payload) {
  const mode = pickString(payload && payload.mode, payload && payload.aiMode).toLowerCase()
  const model = pickString(payload && payload.model)
  const modelSource = pickString(payload && payload.modelSource, payload && payload.model_source).toLowerCase()
  const tags = []
  if (mode === 'real') tags.push({ text: 'real', tone: 'green' })
  else if (mode === 'mock') tags.push({ text: 'mock', tone: 'amber' })
  if (mode === 'real' && model) tags.push({ text: model, tone: 'gray' })
  if (mode === 'real' && modelSource === 'none') {
    // 规则硬拦截：未调用大模型，不展示 Key 来源，避免被误读为 mock
    tags.push({ text: '规则拦截', tone: 'gray' })
  } else if (mode === 'real' && modelSource) {
    tags.push({ text: modelSource === 'user' ? '我的 Key' : '系统 Key', tone: modelSource === 'user' ? 'purple' : 'gray' })
  }
  return tags
}

export default { readAiStatus, answerModeTags }
