<script setup>
/**
 * GateCard —— v1.3 前置自测卡片（答疑气泡内）
 * 契约：.tmp/v13-contract.md §3.2
 * - QUIZ：3 道单选 + 提交；PASSED：三步教学 + 正文 + citation 来源 + mode 标签
 * - FAILED：得分 + feedback + 薄弱前置 + 重新测试；EXPIRED：提示重新提问
 * - 历史会话只读：PASSED 仅显示摘要，不展示题目/选项
 */
import { computed, reactive, ref, watch } from 'vue'
import { student } from '../api'
import { toast } from '../toast'
import { KB_LABEL } from '../utils/format'
import { answerModeTags } from '../utils/aiMode'
import {
  GATE_STATE,
  buildGateCheckPayload,
  gateScoreLabel,
  gateStateLabel,
  normalizeGate,
  normalizeGateResult,
  normalizeTeaching,
  weakPrerequisiteNames,
} from '../utils/gate'
import MarkdownView from './MarkdownView.vue'

const props = defineProps({
  gate: { type: Object, required: true },
  conversationId: { type: [String, Number], default: null },
  readonly: { type: Boolean, default: false },
})
const emit = defineEmits(['checked'])

const info = computed(() => normalizeGate(props.gate) || normalizeGate({ state: GATE_STATE.EXPIRED }))
const selections = reactive({})
const submitting = ref(false)
const result = ref(null)
const error = ref('')
const localState = ref('')

const state = computed(() => {
  if (result.value) return result.value.state
  if (localState.value) return localState.value
  return info.value.state || GATE_STATE.QUIZ
})
const readonly = computed(() => props.readonly)
const isQuiz = computed(() => state.value === GATE_STATE.QUIZ && !readonly.value && info.value.questions.length > 0)
const answered = computed(() => info.value.questions.filter((question) => selections[question.questionId]).length)
const total = computed(() => info.value.total || info.value.questions.length || 3)
const canSubmit = computed(
  () => isQuiz.value && !submitting.value && !!info.value.gateId && answered.value === info.value.questions.length
)
const teaching = computed(
  () => (result.value && result.value.teaching) || normalizeTeaching(props.gate && props.gate.teaching)
)
const sources = computed(() => (result.value && result.value.sources) || [])
const modeTags = computed(() => answerModeTags(result.value || {}))
const weakNames = computed(() => weakPrerequisiteNames(info.value))
const stateText = computed(() => gateStateLabel(state.value))
const stateClass = computed(() => {
  if (state.value === GATE_STATE.FAILED) return 'orange'
  if (state.value === GATE_STATE.EXPIRED) return 'gray'
  return 'green'
})
const scoreLabel = computed(() =>
  gateScoreLabel(result.value ? result.value.score : info.value.score, result.value ? result.value.total : total.value)
)

function resetAll() {
  Object.keys(selections).forEach((key) => delete selections[key])
  result.value = null
  error.value = ''
  localState.value = ''
}
watch(() => info.value.gateId, resetAll)

function choose(question, key) {
  if (submitting.value) return
  selections[question.questionId] = key
}

async function submit() {
  if (submitting.value) return
  if (!info.value.gateId) {
    error.value = '前置测试缺少 gateId，请重新提问。'
    return
  }
  if (!info.value.questions.length) {
    error.value = '前置自测题目加载不完整，请重新提问。'
    return
  }
  if (answered.value !== info.value.questions.length) {
    toast.info('请完成全部 ' + info.value.questions.length + ' 道题后再提交。')
    return
  }
  const payload = buildGateCheckPayload(info.value, selections, props.conversationId)
  submitting.value = true
  error.value = ''
  try {
    const data = await student.gateCheck(payload)
    const normalized = normalizeGateResult(data)
    result.value = normalized
    if (normalized.state === GATE_STATE.PASSED) toast.success('前置测试已通过，已生成三步讲解。')
    else if (normalized.state === GATE_STATE.FAILED)
      toast.info('前置基础还需巩固（' + gateScoreLabel(normalized.score, normalized.total) + '），可重新测试。')
    emit('checked', { result: normalized })
  } catch (err) {
    if (err && err.status === 404) {
      error.value = '后端暂未提供前置自测接口（404），请稍后重试或联系管理员。'
    } else if (err && err.code === 'TIMEOUT') {
      error.value = '前置测试提交超时（已等待 90 秒），请重试。'
    } else {
      error.value = '前置测试提交失败：' + (err && err.message ? err.message : '请稍后重试')
    }
    toast.error(err && err.message ? err.message : '前置测试提交失败')
  } finally {
    submitting.value = false
  }
}

function retake() {
  if (submitting.value) return
  Object.keys(selections).forEach((key) => delete selections[key])
  result.value = null
  error.value = ''
  localState.value = GATE_STATE.QUIZ
}
</script>

<template>
  <section class="gate-card" :class="'gate-state-' + String(state).toLowerCase()">
    <header class="gate-head">
      <div class="gate-head-main">
        <span class="gate-icon" aria-hidden="true">🧭</span>
        <div class="gate-head-text">
          <strong>前置自测 · 共 {{ total }} 题</strong>
          <span v-if="info.topic" class="gate-topic">主题：{{ info.topic }}</span>
        </div>
      </div>
      <span class="tag" :class="stateClass">{{ stateText }}</span>
    </header>

    <p v-if="info.reason" class="gate-reason">{{ info.reason }}</p>
    <p v-if="info.message" class="gate-message">{{ info.message }}</p>

    <div v-if="readonly" class="gate-summary">
      <p v-if="state === 'PASSED'" class="gate-summary-text">
        ✅ 前置测试已通过<template v-if="info.score !== null">（{{ scoreLabel }}）</template>
      </p>
      <p v-else class="gate-summary-text muted">
        前置自测未完成（{{ stateText }}）。历史会话仅保留摘要，如需重测请重新提问。
      </p>
    </div>

    <div v-else-if="isQuiz" class="gate-quiz">
      <div v-if="info.prerequisites.length" class="gate-prereq">
        <span class="gate-label">需要的前置知识</span>
        <span v-for="item in info.prerequisites" :key="item.kpId || item.kpName" class="chip">{{ item.kpName }}</span>
      </div>

      <div v-for="question in info.questions" :key="question.questionId" class="gate-question">
        <div class="gate-question-head">
          <span class="question-index">{{ question.index }}</span>
          <span v-if="question.kpName" class="gate-kp">{{ question.kpName }}</span>
          <span v-if="question.difficulty" class="gate-diff">难度 {{ question.difficulty }}</span>
        </div>
        <p class="gate-stem">{{ question.stem }}</p>
        <div class="option-list">
          <label
            v-for="option in question.options"
            :key="option.key"
            class="option-item gate-option"
            :class="{ selected: selections[question.questionId] === option.key }"
          >
            <input
              type="radio"
              class="gate-radio"
              :name="'gate-' + info.gateId + '-' + question.questionId"
              :value="option.key"
              :checked="selections[question.questionId] === option.key"
              :disabled="submitting"
              @change="choose(question, option.key)"
            />
            <span class="option-key">{{ option.key }}</span>
            <span class="gate-option-text">{{ option.text }}</span>
          </label>
        </div>
      </div>

      <div v-if="error" class="alert alert-error gate-error">
        <span>{{ error }}</span>
        <button class="btn btn-ghost btn-sm" type="button" @click="submit">重试</button>
      </div>

      <div class="gate-actions">
        <span class="gate-progress">已作答 {{ answered }} / {{ info.questions.length }}</span>
        <button class="btn btn-primary btn-sm" type="button" :disabled="!canSubmit" @click="submit">
          <span v-if="submitting" class="spinner light"></span>
          {{ submitting ? '提交中…' : '提交前置测试' }}
        </button>
      </div>
      <p class="gate-tip">通过线 2/3（允许错 1 题）；通过后会按三步循序渐进讲解，不会直接给出作业答案。</p>
    </div>

    <div v-else-if="state === 'PASSED'" class="gate-passed">
      <div class="gate-result-badge passed">✅ 前置测试已通过（{{ scoreLabel }}）</div>
      <p v-if="result && result.feedback" class="gate-feedback">{{ result.feedback }}</p>

      <div v-if="teaching && teaching.steps.length" class="gate-steps">
        <div v-for="(step, index) in teaching.steps" :key="index" class="gate-step">
          <div class="gate-step-title">{{ step.title }}</div>
          <MarkdownView :content="step.content" />
        </div>
      </div>
      <div v-if="teaching && teaching.practice" class="gate-practice">
        <strong>练习建议</strong>
        <p>{{ teaching.practice }}</p>
      </div>

      <div v-if="result && result.answer" class="gate-answer">
        <div class="gate-label">讲解正文</div>
        <MarkdownView :content="result.answer" />
      </div>

      <div v-if="sources.length" class="gate-sources">
        <div class="gate-label">参考来源</div>
        <div v-for="(source, index) in sources" :key="source.chunkId || source.chunk_id || index" class="gate-source">
          <div class="gate-source-head">
            <strong>{{ source.citation || source.title || '课程知识库' }}</strong>
            <span v-if="source.kb" class="tag purple">{{ KB_LABEL[source.kb] || source.kb }}</span>
          </div>
          <p v-if="source.excerpt">{{ source.excerpt }}</p>
        </div>
      </div>

      <div v-if="modeTags.length" class="answer-mode">
        <span v-for="tag in modeTags" :key="tag.text" class="tag" :class="tag.tone">{{ tag.text }}</span>
      </div>
    </div>

    <div v-else-if="state === 'EXPIRED'" class="gate-expired">
      <div class="alert alert-warn">
        前置测试已过期，请重新提问以生成新的前置自测。
      </div>
    </div>

    <div v-else class="gate-failed">
      <div class="gate-result-badge failed">前置基础还需巩固（{{ scoreLabel }}）</div>
      <p v-if="result && result.feedback" class="gate-feedback">{{ result.feedback }}</p>
      <div v-if="weakNames.length" class="gate-prereq">
        <span class="gate-label">建议先补</span>
        <span v-for="name in weakNames" :key="name" class="chip">{{ name }}</span>
      </div>
      <div class="gate-actions">
        <span class="gate-tip">可修改答案后重新提交（同一组题）。</span>
        <button class="btn btn-outline btn-sm" type="button" :disabled="submitting" @click="retake">重新测试</button>
      </div>
    </div>
  </section>
</template>
