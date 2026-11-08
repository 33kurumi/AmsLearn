<script setup>
/**
 * 知识诊断 S10 / S11
 * POST /diagnose/start {mode, focusKpIds} → 答题 → POST /diagnose/{sessionId}/submit {answers}
 * 结果展示：成绩、逐题错因、掌握度变化、诊断报告。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { common, student } from '../../api'
import { toast } from '../../toast'
import {
  DIAGNOSE_MODE_META,
  formatDateTime,
  masteryStatus,
  percentText,
  scoreLevel,
} from '../../utils/format'
import SkeletonBlock from '../../components/SkeletonBlock.vue'
import ErrorState from '../../components/ErrorState.vue'
import MarkdownView from '../../components/MarkdownView.vue'
import EmptyState from '../../components/EmptyState.vue'

const props = defineProps({
  user: { type: Object, required: true },
  navigate: { type: Function, required: true },
})

const phase = ref('setup') // setup | exam | result
const mode = ref('QUICK')
const focusKpIds = ref([])
const kpLoading = ref(false)
const kpError = ref('')
const knowledgePoints = ref([])
const showFocusPicker = ref(false)

const starting = ref(false)
const startError = ref('')
const session = ref(null)
const questions = ref([])
const currentIndex = ref(0)
const answers = reactive({})
const submitting = ref(false)
const submitError = ref('')
const result = ref(null)
const resultTab = ref('score')
const showHint = ref(false)

const currentQuestion = computed(() => questions.value[currentIndex.value] || null)
const answeredCount = computed(
  () => questions.value.filter((question) => String(answers[question.questionId] ?? '').trim() !== '').length
)
const totalQuestions = computed(() => questions.value.length)
const progress = computed(() => (totalQuestions.value ? (answeredCount.value / totalQuestions.value) * 100 : 0))

const questionMap = computed(() => {
  const map = {}
  questions.value.forEach((question) => {
    map[question.questionId] = question
  })
  return map
})

function optionList(question) {
  if (!question) return []
  if (question.options && question.options.length) return question.options
  if (question.type === 'JUDGE') {
    return [
      { key: 'A', text: '正确' },
      { key: 'B', text: '错误' },
    ]
  }
  return []
}

async function loadKnowledgePoints() {
  kpLoading.value = true
  kpError.value = ''
  try {
    knowledgePoints.value = (await common.knowledgePoints()) || []
  } catch (error) {
    kpError.value = error.message
  } finally {
    kpLoading.value = false
  }
}

onMounted(loadKnowledgePoints)

function toggleFocus(kpId) {
  const index = focusKpIds.value.indexOf(kpId)
  if (index >= 0) focusKpIds.value.splice(index, 1)
  else focusKpIds.value.push(kpId)
}

async function startDiagnose() {
  if (starting.value) return
  starting.value = true
  startError.value = ''
  try {
    const data = await student.diagnoseStart({
      mode: mode.value,
      focusKpIds: focusKpIds.value.slice(),
    })
    if (!data || !data.sessionId || !Array.isArray(data.questions) || !data.questions.length) {
      throw new Error('诊断接口未返回有效题目，请检查 AI 服务是否正常。')
    }
    session.value = data
    questions.value = data.questions
    currentIndex.value = 0
    Object.keys(answers).forEach((key) => delete answers[key])
    result.value = null
    phase.value = 'exam'
    toast.success(`已生成 ${data.questions.length} 道诊断题`)
  } catch (error) {
    startError.value =
      error.code === 'TIMEOUT'
        ? '出题超时（已等待 90 秒）：AI 服务生成题目时间过长，请重试。'
        : error.message || '出题失败'
  } finally {
    starting.value = false
  }
}

function selectOption(question, key) {
  if (!question || submitting.value) return
  answers[question.questionId] = key
}

function goTo(index) {
  if (index < 0 || index >= totalQuestions.value) return
  currentIndex.value = index
  showHint.value = false
}

function next() {
  goTo(currentIndex.value + 1)
}

function prev() {
  goTo(currentIndex.value - 1)
}

async function submit() {
  if (submitting.value) return
  const unanswered = totalQuestions.value - answeredCount.value
  if (unanswered > 0) {
    const confirmed = window.confirm(`还有 ${unanswered} 道题未作答，未作答题目按错误计算。确定要交卷吗？`)
    if (!confirmed) return
  }
  submitting.value = true
  submitError.value = ''
  try {
    const payload = questions.value.map((question) => ({
      questionId: question.questionId,
      answer: String(answers[question.questionId] ?? ''),
    }))
    const data = await student.diagnoseSubmit(session.value.sessionId, payload)
    result.value = data
    resultTab.value = 'score'
    phase.value = 'result'
    toast.success('交卷成功，诊断报告已生成')
  } catch (error) {
    submitError.value =
      error.code === 'TIMEOUT' ? '交卷超时（已等待 90 秒），请重试。' : error.message || '交卷失败'
  } finally {
    submitting.value = false
  }
}

function restart() {
  phase.value = 'setup'
  session.value = null
  questions.value = []
  result.value = null
  startError.value = ''
  submitError.value = ''
  showHint.value = false
  Object.keys(answers).forEach((key) => delete answers[key])
}

const resultStats = computed(() => {
  if (!result.value) return null
  const level = scoreLevel(result.value.score)
  return { ...level, score: Number(result.value.score || 0) }
})

function resultQuestion(questionId) {
  return questionMap.value[questionId] || {}
}

function contentEntries(content) {
  if (!content || typeof content !== 'object') return []
  return Object.entries(content).filter(([, value]) => value !== null && value !== undefined && value !== '')
}

function entryValue(value) {
  if (Array.isArray(value)) {
    return value.map((item) => {
      if (item && typeof item === 'object') {
        return item.title || item.summary || item.text || JSON.stringify(item)
      }
      return String(item)
    }).join('；')
  }
  if (value && typeof value === 'object') return JSON.stringify(value)
  return String(value)
}
</script>

<template>
  <div>
    <div class="module-intro">
      <p class="eyebrow">知识诊断 · DIAGNOSIS</p>
      <h1>先诊断，再学习</h1>
      <p>快速诊断 5 题 / 全面诊断 15 题，交卷后生成错因分析、掌握度变化与诊断报告。</p>
    </div>

    <!-- 诊断配置 -->
    <template v-if="phase === 'setup'">
      <section class="panel">
        <div class="panel-heading">
          <div>
            <h3>选择诊断方式</h3>
            <p>快速诊断适合日常自查，全面诊断会覆盖更多知识点并生成完整报告。</p>
          </div>
          <span class="tag green">AI 出题</span>
        </div>
        <div class="radio-cards" style="grid-template-columns: repeat(auto-fit, minmax(240px, 1fr))">
          <button
            v-for="(meta, key) in DIAGNOSE_MODE_META"
            :key="key"
            type="button"
            class="radio-card"
            :class="{ selected: mode === key }"
            @click="mode = key"
          >
            <strong>{{ meta.label }}</strong>
            <span>{{ meta.desc }}</span>
          </button>
        </div>

        <div class="divider" style="margin: 20px 0"></div>

        <div class="flex-between" style="margin-bottom: 12px">
          <div>
            <strong class="text-strong">聚焦知识点（可选）</strong>
            <p class="muted" style="margin: 6px 0 0; font-size: 12px">
              不选择时由系统根据掌握度自动挑选；已选 {{ focusKpIds.length }} 个。
            </p>
          </div>
          <button class="btn btn-ghost btn-sm" @click="showFocusPicker = !showFocusPicker">
            {{ showFocusPicker ? '收起' : '选择知识点' }}
          </button>
        </div>

        <div v-if="showFocusPicker">
          <div v-if="kpLoading" class="loading-inline"><span class="spinner"></span> 正在加载知识点…</div>
          <ErrorState v-else-if="kpError" :title="'知识点加载失败'" :message="kpError" :show-cards="false" @retry="loadKnowledgePoints" />
          <div v-else class="chip-group kp-picker">
            <button
              v-for="kp in knowledgePoints"
              :key="kp.kpId"
              type="button"
              class="chip"
              :class="{ selected: focusKpIds.includes(kp.kpId) }"
              @click="toggleFocus(kp.kpId)"
            >
              {{ kp.kpName }}
              <span class="muted" style="margin-left: 4px">{{ percentText(kp.mastery) }}</span>
            </button>
          </div>
        </div>

        <div v-if="startError" class="alert alert-error" style="margin-top: 18px">
          <strong>出题失败：</strong>{{ startError }}
        </div>

        <div class="exam-actions">
          <button class="btn btn-primary" :disabled="starting" @click="startDiagnose">
            <span v-if="starting" class="spinner light"></span>
            {{ starting ? 'AI 正在出题（最长 90 秒）…' : `开始${DIAGNOSE_MODE_META[mode].label}` }}
          </button>
          <button class="btn btn-outline" :disabled="starting" @click="startDiagnose">重试出题</button>
        </div>
      </section>
    </template>

    <!-- 答题 -->
    <template v-else-if="phase === 'exam'">
      <div class="exam-layout">
        <div>
          <div class="panel" style="margin-bottom: 14px">
            <div class="flex-between">
              <div>
                <strong class="text-strong">{{ DIAGNOSE_MODE_META[session.mode] ? DIAGNOSE_MODE_META[session.mode].label : '知识诊断' }}</strong>
                <p class="muted" style="margin: 5px 0 0; font-size: 12px">
                  第 {{ currentIndex + 1 }} / {{ totalQuestions }} 题 · 已作答 {{ answeredCount }} 题
                </p>
              </div>
              <span class="tag green">{{ progress.toFixed(0) }}%</span>
            </div>
            <div class="progress-track" style="margin-top: 12px">
              <div class="progress-fill" :style="{ width: progress + '%' }"></div>
            </div>
          </div>

          <div v-if="currentQuestion" class="question-card">
            <div class="question-head">
              <span class="question-index">{{ currentIndex + 1 }}</span>
              <div class="flex-row" style="gap: 8px; flex-wrap: wrap">
                <span class="tag green">{{ currentQuestion.kpName || currentQuestion.kpId }}</span>
                <span class="tag gray">难度 {{ currentQuestion.difficulty }}</span>
                <span class="tag purple">{{ currentQuestion.type === 'SINGLE' ? '单选' : currentQuestion.type === 'JUDGE' ? '判断' : '填空' }}</span>
              </div>
            </div>

            <div class="question-stem">
              <MarkdownView :content="currentQuestion.stem" />
            </div>

            <div v-if="currentQuestion.type === 'FILL'" class="fill-answer">
              <input
                class="input"
                :value="answers[currentQuestion.questionId] || ''"
                placeholder="请输入答案"
                @input="answers[currentQuestion.questionId] = $event.target.value"
              />
            </div>
            <div v-else class="option-list">
              <button
                v-for="option in optionList(currentQuestion)"
                :key="option.key"
                type="button"
                class="option-item"
                :class="{ selected: answers[currentQuestion.questionId] === option.key }"
                @click="selectOption(currentQuestion, option.key)"
              >
                <span class="option-key">{{ option.key }}</span>
                <span>{{ option.text }}</span>
              </button>
            </div>

            <div class="flex-between" style="margin-top: 16px">
              <button class="btn btn-ghost btn-sm" @click="showHint = !showHint">
                {{ showHint ? '隐藏提示' : '查看提示' }}
              </button>
              <span class="muted" style="font-size: 11px">提示只给思路，不直接给答案</span>
            </div>
            <div v-if="showHint" class="alert alert-info" style="margin-top: 10px">
              {{ currentQuestion.hint || '暂无提示，请先回顾相关概念与公式。' }}
            </div>

            <div class="exam-actions">
              <button class="btn btn-outline btn-sm" :disabled="currentIndex === 0" @click="prev">上一题</button>
              <button
                v-if="currentIndex < totalQuestions - 1"
                class="btn btn-primary btn-sm"
                @click="next"
              >
                下一题
              </button>
              <button v-else class="btn btn-primary btn-sm" :disabled="submitting" @click="submit">
                <span v-if="submitting" class="spinner light"></span>
                {{ submitting ? '交卷中…' : '交卷' }}
              </button>
            </div>
          </div>

          <div v-if="submitError" class="alert alert-error" style="margin-top: 14px">
            <strong>交卷失败：</strong>{{ submitError }}
            <button class="text-button" style="margin-left: 8px" @click="submit">重试交卷</button>
          </div>
        </div>

        <aside class="answer-sheet">
          <h4>答题卡</h4>
          <div class="answer-grid">
            <button
              v-for="(question, index) in questions"
              :key="question.questionId"
              type="button"
              class="answer-dot"
              :class="{
                answered: String(answers[question.questionId] ?? '').trim() !== '',
                current: index === currentIndex,
              }"
              @click="goTo(index)"
            >
              {{ index + 1 }}
            </button>
          </div>
          <div class="answer-summary">
            <p>已作答 {{ answeredCount }} / {{ totalQuestions }}</p>
            <button class="btn btn-primary btn-block btn-sm" :disabled="submitting" @click="submit">
              {{ submitting ? '交卷中…' : '提交答卷' }}
            </button>
            <button class="btn btn-outline btn-block btn-sm" style="margin-top: 8px" @click="restart">
              放弃本次诊断
            </button>
          </div>
        </aside>
      </div>
    </template>

    <!-- 结果 -->
    <template v-else-if="phase === 'result' && result">
      <section class="result-banner">
        <div>
          <span class="eyebrow">{{ session && session.mode === 'FULL' ? '全面诊断报告' : '快速诊断报告' }}</span>
          <div class="score">{{ result.score }}<small>分</small></div>
          <h2>{{ resultStats.text }} · 答对 {{ result.correctCount }} / {{ result.total }} 题</h2>
          <p>诊断时间 {{ formatDateTime(session && session.startedAt) }} · 等级 {{ result.level || resultStats.text }}</p>
        </div>
        <div class="flex-row" style="gap: 10px">
          <button class="btn btn-outline btn-sm" @click="restart">再次诊断</button>
          <button class="btn btn-primary btn-sm" @click="navigate('plan')">生成学习计划</button>
        </div>
      </section>

      <div class="tab-bar" style="margin-bottom: 16px">
        <button class="tab" :class="{ selected: resultTab === 'score' }" @click="resultTab = 'score'">成绩概览</button>
        <button class="tab" :class="{ selected: resultTab === 'analysis' }" @click="resultTab = 'analysis'">错因分析</button>
        <button class="tab" :class="{ selected: resultTab === 'mastery' }" @click="resultTab = 'mastery'">掌握度变化</button>
        <button class="tab" :class="{ selected: resultTab === 'report' }" @click="resultTab = 'report'">诊断报告</button>
      </div>

      <section v-if="resultTab === 'score'" class="panel">
        <div class="panel-heading">
          <div><h3>逐题结果</h3><p>绿色为答对，红色为答错，错题已自动进入错题本</p></div>
        </div>
        <div class="result-list">
          <div
            v-for="(item, index) in result.results || []"
            :key="item.questionId"
            class="result-item"
          >
            <div class="result-item-top">
              <span class="question-index">{{ index + 1 }}</span>
              <span class="tag green">{{ item.kpName }}</span>
              <span class="tag" :class="item.correct ? 'green' : 'red'">{{ item.correct ? '答对' : '答错' }}</span>
              <span v-if="!item.correct && item.errorType" class="tag orange">{{ item.errorType }}</span>
            </div>
            <div class="result-stem">
              <MarkdownView :content="resultQuestion(item.questionId).stem || '（题干缺失）'" />
            </div>
            <div class="result-answer">
              你的答案：<b>{{ item.studentAnswer || '未作答' }}</b> · 正确答案：<b>{{ item.correctAnswer }}</b>
            </div>
            <div v-if="item.analysis" class="result-analysis">
              <MarkdownView :content="item.analysis" />
            </div>
          </div>
        </div>
      </section>

      <section v-else-if="resultTab === 'analysis'" class="panel">
        <div class="panel-heading">
          <div><h3>错因分析</h3><p>按错误类型归类，定位知识盲区与解题习惯问题</p></div>
        </div>
        <div v-if="(result.results || []).some((item) => !item.correct)" class="result-list">
          <div v-for="item in (result.results || []).filter((row) => !row.correct)" :key="item.questionId" class="result-item">
            <div class="result-item-top">
              <span class="tag green">{{ item.kpName }}</span>
              <span class="tag orange">{{ item.errorType || '未归类' }}</span>
              <span class="muted" style="font-size: 11px">你的答案 {{ item.studentAnswer || '未作答' }} · 正确 {{ item.correctAnswer }}</span>
            </div>
            <div class="result-analysis">
              <MarkdownView :content="item.analysis || '暂无解析'" />
            </div>
          </div>
        </div>
        <EmptyState v-else icon="✓" title="全部答对" description="本次诊断没有错题，继续保持！" />
      </section>

      <section v-else-if="resultTab === 'mastery'" class="panel">
        <div class="panel-heading">
          <div><h3>掌握度变化</h3><p>本次诊断后各知识点掌握度的前后对比</p></div>
        </div>
        <div v-if="(result.masteryChanges || []).length" class="mastery-change">
          <div v-for="row in result.masteryChanges" :key="row.kpId" class="mastery-change-row">
            <span class="text-strong">{{ row.kpName }}</span>
            <span class="flex-row" style="gap: 10px">
              <span class="muted">{{ percentText(row.before) }}</span>
              <span>→</span>
              <strong>{{ percentText(row.after) }}</strong>
              <span :class="row.after >= row.before ? 'delta-up' : 'delta-down'">
                {{ row.after >= row.before ? '↑' : '↓' }} {{ Math.abs((row.after - row.before) * 100).toFixed(1) }}%
              </span>
              <span class="tag" :class="masteryStatus(row.after).cls">{{ masteryStatus(row.after).text }}</span>
            </span>
          </div>
        </div>
        <EmptyState v-else icon="◎" title="暂无掌握度变化" description="需要更多答题数据才能更新掌握度。" />
      </section>

      <section v-else class="panel">
        <div class="panel-heading">
          <div><h3>{{ result.report && result.report.title ? result.report.title : '诊断报告' }}</h3><p>由 AI 生成的个性化诊断结论与建议</p></div>
          <span v-if="result.report" class="tag green">{{ result.report.status || '已生成' }}</span>
        </div>
        <div v-if="result.report && result.report.summary" class="detail-block">
          <h4>报告摘要</h4>
          <MarkdownView :content="result.report.summary" />
        </div>
        <div v-for="[key, value] in contentEntries(result.report && result.report.content)" :key="key" class="detail-block">
          <h4>{{ key }}</h4>
          <MarkdownView v-if="typeof value === 'string'" :content="value" />
          <p v-else class="muted">{{ entryValue(value) }}</p>
        </div>
        <EmptyState v-if="!result.report" icon="▥" title="报告数据缺失" description="诊断报告由 AI 服务生成，请检查 AI 服务是否正常。" />
      </section>
    </template>
  </div>
</template>

<style scoped>
.kp-picker { display: flex; flex-wrap: wrap; gap: 8px; max-height: 240px; overflow-y: auto; padding: 4px; }
.result-list { display: grid; gap: 14px; }
</style>
