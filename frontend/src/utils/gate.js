/**
 * src/utils/gate.js —— v1.3「前置自测」数据归一化（不依赖 DOM，便于单元测试）
 * 契约：.tmp/v13-contract.md §1.3~1.5 / §3.2
 * - chat 响应 gate.state=QUIZ 时前端渲染 3 题单选卡
 * - /student/gate/check 返回 PASSED / FAILED / EXPIRED，并带 teaching / answer / sources
 * - 兼容 camelCase 与 snake_case 字段，缺字段时安全降级
 */

function text(...values) {
  for (const value of values) {
    if (value === undefined || value === null) continue
    const str = String(value).trim()
    if (str) return str
  }
  return ''
}

function toNumber(value) {
  if (value === null || value === undefined || value === '') return null
  const num = Number(value)
  return Number.isFinite(num) ? num : null
}

export const GATE_STATE = { QUIZ: 'QUIZ', PASSED: 'PASSED', FAILED: 'FAILED', EXPIRED: 'EXPIRED' }

const STATE_LABEL = { QUIZ: '待完成', PASSED: '已通过', FAILED: '未通过', EXPIRED: '已过期' }

export function gateStateLabel(state) {
  return STATE_LABEL[text(state).toUpperCase()] || '待完成'
}

function normalizeOption(option, index) {
  if (option === null || option === undefined) return null
  if (typeof option === 'string' || typeof option === 'number') {
    return { key: String.fromCharCode(65 + index), text: String(option) }
  }
  if (typeof option !== 'object') return null
  const key = text(option.key, option.optionKey, option.option_key, String.fromCharCode(65 + index))
  const label = text(option.text, option.label, option.content, option.value)
  if (!key && !label) return null
  return { key, text: label || key }
}

function normalizeQuestion(question, index) {
  if (!question || typeof question !== 'object') return null
  const stem = text(question.stem, question.title, question.content)
  if (!stem) return null
  const options = Array.isArray(question.options)
    ? question.options.map(normalizeOption).filter(Boolean)
    : []
  return {
    questionId: text(question.questionId, question.question_id, question.id, 'q' + (index + 1)),
    index: toNumber(question.index) || index + 1,
    kpId: text(question.kpId, question.kp_id),
    kpName: text(question.kpName, question.kp_name),
    difficulty: toNumber(question.difficulty),
    stem,
    options,
  }
}

function normalizePrerequisite(item) {
  if (!item || typeof item !== 'object') return null
  return {
    kpId: text(item.kpId, item.kp_id),
    kpName: text(item.kpName, item.kp_name, item.name),
    citation: text(item.citation, item.source),
  }
}

/** gate 对象归一化；无有效内容返回 null */
export function normalizeGate(raw) {
  if (!raw || typeof raw !== 'object' || !Object.keys(raw).length) return null
  const questions = Array.isArray(raw.questions)
    ? raw.questions.map(normalizeQuestion).filter(Boolean)
    : []
  const prerequisites = Array.isArray(raw.prerequisites)
    ? raw.prerequisites.map(normalizePrerequisite).filter(Boolean)
    : []
  const total = toNumber(raw.total)
  const score = toNumber(raw.score)
  return {
    gateId: text(raw.gateId, raw.gate_id),
    topic: text(raw.topic),
    state: (text(raw.state) || GATE_STATE.QUIZ).toUpperCase(),
    reason: text(raw.reason),
    message: text(raw.message),
    prerequisites,
    questions,
    score,
    total: total && total > 0 ? total : questions.length || 3,
  }
}

export function normalizeTeaching(raw) {
  if (!raw || typeof raw !== 'object') return null
  const steps = Array.isArray(raw.steps)
    ? raw.steps
        .map((step, index) => {
          if (!step || typeof step !== 'object') return null
          const content = text(step.content, step.body, step.text)
          if (!content) return null
          return { title: text(step.title, step.name, '第 ' + (index + 1) + ' 步'), content }
        })
        .filter(Boolean)
    : []
  const practice = text(raw.practice, raw.exercise)
  if (!steps.length && !practice) return null
  return { steps, practice }
}

/** /student/gate/check 响应归一化 */
export function normalizeGateResult(raw) {
  const source = raw && typeof raw === 'object' ? raw : {}
  const passed = typeof source.passed === 'boolean' ? source.passed : null
  const gate = normalizeGate(source.gate)
  let state = (text(source.state) || (passed ? GATE_STATE.PASSED : GATE_STATE.FAILED)).toUpperCase()
  if (![GATE_STATE.PASSED, GATE_STATE.FAILED, GATE_STATE.EXPIRED, GATE_STATE.QUIZ].includes(state)) {
    state = passed ? GATE_STATE.PASSED : GATE_STATE.FAILED
  }
  const score = toNumber(source.score)
  const total = toNumber(source.total) || (gate && gate.total) || 3
  return {
    passed: passed === null ? state === GATE_STATE.PASSED : passed,
    score: score === null ? 0 : score,
    total,
    state,
    feedback: text(source.feedback),
    answer: text(source.answer, source.reply),
    sources: Array.isArray(source.sources) ? source.sources : [],
    knowledgeCovered: source.knowledgeCovered !== false && source.knowledge_covered !== false,
    teaching: normalizeTeaching(source.teaching),
    gate,
    mode: text(source.mode),
    model: text(source.model),
    modelSource: text(source.modelSource, source.model_source),
    recordId: source.recordId !== undefined && source.recordId !== null ? source.recordId : source.record_id,
    conversationId:
      source.conversationId !== undefined && source.conversationId !== null
        ? source.conversationId
        : source.conversation_id,
  }
}

/** 消息是否携带待完成的前置自测 */
export function isGateQuizMessage(message) {
  if (!message || typeof message !== 'object') return false
  const action = message.action
  if (!action || action.type !== 'GATE') return false
  const gate = normalizeGate(message.gate)
  return !!(gate && gate.state === GATE_STATE.QUIZ && gate.questions.length)
}

/** 是否 Gate 动作（用于隐藏通用 action 按钮） */
export function isGateAction(action) {
  return !!(action && action.type === 'GATE')
}

export function answeredCount(gate, selections) {
  const info = gate || {}
  const picked = selections || {}
  return (info.questions || []).filter((question) => picked[question.questionId]).length
}

export function missingQuestionNumbers(gate, selections) {
  const info = gate || {}
  const picked = selections || {}
  return (info.questions || [])
    .filter((question) => !picked[question.questionId])
    .map((question) => question.index)
}

export function gateScoreLabel(score, total) {
  const max = toNumber(total) || 3
  const got = toNumber(score)
  return (got === null ? 0 : got) + '/' + max
}

/** 失败时展示的「建议先补」前置知识点（去重） */
export function weakPrerequisiteNames(gate) {
  const seen = new Set()
  const names = []
  ;((gate && gate.prerequisites) || []).forEach((item) => {
    if (item && item.kpName && !seen.has(item.kpName)) {
      seen.add(item.kpName)
      names.push(item.kpName)
    }
  })
  return names
}

/** 构造 /student/gate/check 请求体 */
export function buildGateCheckPayload(gate, selections, conversationId) {
  const info = gate || {}
  const picked = selections || {}
  const answers = (info.questions || [])
    .filter((question) => picked[question.questionId])
    .map((question) => ({ questionId: question.questionId, choice: picked[question.questionId] }))
  return {
    gateId: info.gateId || '',
    conversationId: conversationId === undefined || conversationId === '' ? null : conversationId,
    answers,
  }
}

export default {
  GATE_STATE,
  gateStateLabel,
  normalizeGate,
  normalizeTeaching,
  normalizeGateResult,
  isGateQuizMessage,
  isGateAction,
  answeredCount,
  missingQuestionNumbers,
  gateScoreLabel,
  weakPrerequisiteNames,
  buildGateCheckPayload,
}
