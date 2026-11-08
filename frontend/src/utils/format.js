/** 通用格式化 / 枚举文案工具（枚举值以 docs/开发过程/01-接口约定.md 第 3.4 节为准） */

export const RECORD_TYPE_LABEL = {
  QA: '答疑',
  DIAGNOSIS: '诊断',
  PRACTICE: '练习',
  PLAN: '计划',
}

export const RECORD_TYPE_ICON = {
  QA: '✳',
  DIAGNOSIS: '▥',
  PRACTICE: '✎',
  PLAN: '▤',
}

export const REPORT_TYPE_LABEL = {
  DIAGNOSIS: '诊断报告',
  PLAN: '学习计划',
  PRACTICE: '练习报告',
  CLASS_ANALYSIS: '班级学情',
}

export const ANSWER_MODE_LABEL = {
  GUIDED: '引导式',
  DIRECT: '直接讲解',
  MIXED: '混合',
}

export const LAYER_META = {
  A: { label: 'A 层 · 基础', desc: '难度 1~2，夯实概念与基本运算。' },
  B: { label: 'B 层 · 提升', desc: '难度 2~3，综合运用与常见题型。' },
  C: { label: 'C 层 · 拓展', desc: '难度 3~4，冲刺高分与解题策略。' },
}

export const DIAGNOSE_MODE_META = {
  QUICK: { label: '快速诊断', desc: '5 题 · 约 5 分钟，快速定位薄弱点。', count: 5 },
  FULL: { label: '全面诊断', desc: '15 题 · 约 20 分钟，生成完整诊断报告。', count: 15 },
}

export const KB_LABEL = {
  KB1: '课程大纲',
  KB2: '教材讲义',
  KB3: '题库',
  KB4: '教师资料',
  KB5: '知识图谱',
}

export const PRIORITY_LABEL = { HIGH: '高', MEDIUM: '中', LOW: '低' }

/** 'YYYY-MM-DDTHH:mm:ss' / ISO → 'MM-DD HH:mm' */
export function formatDateTime(value) {
  if (!value) return '—'
  const text = String(value).replace('T', ' ')
  const match = text.match(/^(\d{4})-(\d{2})-(\d{2})[ ]?(\d{2}:\d{2})?/)
  if (!match) return String(value)
  const [, , month, day, time] = match
  return time ? `${month}-${day} ${time}` : `${month}-${day}`
}

export function formatDate(value) {
  if (!value) return '—'
  const match = String(value).match(/^(\d{4})-(\d{2})-(\d{2})/)
  if (!match) return String(value)
  return `${match[1]}-${match[2]}-${match[3]}`
}

export function formatFullDateTime(value) {
  if (!value) return '—'
  return String(value).replace('T', ' ').slice(0, 19)
}

export function todayText() {
  const now = new Date()
  const week = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'][now.getDay()]
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')} ${week}`
}

/** 0.42 → 42 */
export function toPercent(value, digits = 0) {
  const number = Number(value)
  if (Number.isNaN(number)) return '—'
  return (number * 100).toFixed(digits)
}

/** 0.42 → '42%' */
export function percentText(value, digits = 0) {
  return `${toPercent(value, digits)}%`
}

/** 掌握度状态（契约 3.4：未开始 / 薄弱 <0.3 / 一般 0.3~0.7 / 良好 ≥0.7） */
export function masteryStatus(mastery, attempts = 0) {
  const number = Number(mastery) || 0
  if (!attempts && number <= 0) return { text: '未开始', cls: 'gray' }
  if (number < 0.3) return { text: '薄弱', cls: 'red' }
  if (number < 0.7) return { text: '一般', cls: 'orange' }
  return { text: '良好', cls: 'green' }
}

export function masteryFillClass(mastery) {
  const number = Number(mastery) || 0
  if (number < 0.3) return 'red-fill'
  if (number < 0.6) return 'orange-fill'
  if (number < 0.7) return ''
  return ''
}

export function scoreLevel(score) {
  const number = Number(score) || 0
  if (number >= 85) return { text: '优秀', cls: 'green' }
  if (number >= 70) return { text: '良好', cls: 'green' }
  if (number >= 55) return { text: '一般', cls: 'orange' }
  return { text: '待提升', cls: 'red' }
}

export function truncate(text, length = 80) {
  const value = String(text || '')
  if (value.length <= length) return value
  return `${value.slice(0, length)}…`
}

/** 从对象中提取 local date（datetime → date） */
export function toDateOnly(value) {
  if (!value) return ''
  return String(value).slice(0, 10)
}

/** 用于展示掌握度变化 before/after */
export function formatMastery(value) {
  const number = Number(value)
  if (Number.isNaN(number)) return '—'
  return percentText(number)
}
