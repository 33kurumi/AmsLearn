<script setup>
/**
 * 学习计划 S14 / S15 / S16 / S17
 * 生成计划（周期 / 天数 / 目标）→ 计划列表切换 → 每日学习-练习-复盘 → 勾选完成打卡。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { common, student } from '../../api'
import { toast } from '../../toast'
import { formatDate, percentText } from '../../utils/format'
import SkeletonBlock from '../../components/SkeletonBlock.vue'
import ErrorState from '../../components/ErrorState.vue'
import EmptyState from '../../components/EmptyState.vue'
import MarkdownView from '../../components/MarkdownView.vue'

const props = defineProps({
  user: { type: Object, required: true },
  navigate: { type: Function, required: true },
})

const PERIOD_LABEL = { DAY: '日计划', WEEK: '周计划', MONTH: '月计划', TERM: '学期计划', SEMESTER: '学期计划' }

const listLoading = ref(true)
const listError = ref('')
const plans = ref([])
const listPage = ref(1)
const listTotal = ref(0)
const listHasNext = ref(false)
const pageSize = 10

const detailLoading = ref(false)
const detailError = ref('')
const plan = ref(null)
const pendingDay = ref(null)

const knowledgePoints = ref([])
const kpLoading = ref(false)

const generating = ref(false)
const formError = ref('')
const form = reactive({ period: 'WEEK', days: 7, goal: '' })
const focusKpIds = ref([])
const showFocusPicker = ref(false)
const showGenerate = ref(false)

const periodOptions = ref([
  { value: 'WEEK', label: '周计划 · 7 天' },
  { value: 'MONTH', label: '月计划 · 30 天' },
  { value: 'TERM', label: '学期计划' },
])

const planProgress = computed(() => {
  if (!plan.value) return 0
  if (typeof plan.value.progress === 'number') return Math.round(plan.value.progress * 100)
  const days = plan.value.days || []
  if (!days.length) return 0
  return Math.round((days.filter((day) => day.done).length / days.length) * 100)
})

const doneDays = computed(() => {
  if (!plan.value) return 0
  if (typeof plan.value.doneDays === 'number') return plan.value.doneDays
  return (plan.value.days || []).filter((day) => day.done).length
})

const totalDays = computed(() => {
  if (!plan.value) return 0
  return plan.value.daysCount || (plan.value.days || []).length
})

async function loadDictionaries() {
  try {
    const data = await common.dictionaries()
    const periods = data && data.periods
    if (Array.isArray(periods) && periods.length) {
      periodOptions.value = periods.map((item) => {
        const value = typeof item === 'string' ? item : item.value || item.code
        const label = typeof item === 'string' ? PERIOD_LABEL[item] || item : item.label || PERIOD_LABEL[value] || value
        return { value, label }
      })
      if (!periodOptions.value.some((item) => item.value === form.period)) {
        form.period = periodOptions.value[0].value
      }
      syncDaysWithPeriod()
    }
  } catch {
    /* 字典接口未就绪时使用内置周期选项 */
  }
}

function syncDaysWithPeriod() {
  if (form.period === 'WEEK') form.days = 7
  else if (form.period === 'MONTH') form.days = 30
  else if (form.period === 'TERM') form.days = 30
}

async function loadKnowledgePoints() {
  kpLoading.value = true
  try {
    knowledgePoints.value = (await common.knowledgePoints()) || []
  } catch {
    knowledgePoints.value = []
  } finally {
    kpLoading.value = false
  }
}

async function loadPlans(page = 1) {
  listLoading.value = true
  listError.value = ''
  try {
    const data = await student.plans({ page, size: pageSize })
    const items = (data && data.items) || []
    plans.value = items
    listPage.value = (data && data.page) || page
    listTotal.value = (data && data.total) || items.length
    listHasNext.value = !!(data && data.hasNext)
    if (!plan.value && items.length) {
      await loadDetail(items[0].id)
    }
  } catch (error) {
    listError.value = error.message || '计划列表加载失败'
  } finally {
    listLoading.value = false
  }
}

async function loadDetail(id) {
  if (!id) return
  detailLoading.value = true
  detailError.value = ''
  try {
    plan.value = await student.planDetail(id)
  } catch (error) {
    detailError.value = error.message || '计划详情加载失败'
  } finally {
    detailLoading.value = false
  }
}

function selectPlan(item) {
  if (!item || !item.id) return
  loadDetail(item.id)
}

function onPeriodChange() {
  syncDaysWithPeriod()
}

function toggleFocus(kpId) {
  const index = focusKpIds.value.indexOf(kpId)
  if (index >= 0) focusKpIds.value.splice(index, 1)
  else focusKpIds.value.push(kpId)
}

async function generate() {
  if (generating.value) return
  formError.value = ''
  const days = Number(form.days)
  if (!days || days < 1 || days > 60) {
    formError.value = '学习天数需在 1 ~ 60 天之间。'
    return
  }
  if (!form.goal.trim() && !focusKpIds.value.length) {
    formError.value = '请填写学习目标，或至少选择一个聚焦知识点。'
    return
  }
  generating.value = true
  try {
    const data = await student.plansGenerate({
      period: form.period,
      days,
      focusKpIds: focusKpIds.value.slice(),
      goal: form.goal.trim(),
    })
    if (!data || !data.id) throw new Error('计划接口未返回有效计划，请检查 AI 服务。')
    plan.value = data
    showGenerate.value = false
    form.goal = ''
    focusKpIds.value = []
    toast.success('学习计划已生成')
    await loadPlans(1)
  } catch (error) {
    formError.value =
      error.code === 'TIMEOUT' ? '生成超时（已等待 90 秒），请重试或减少天数。' : error.message || '生成计划失败'
  } finally {
    generating.value = false
  }
}

async function toggleDay(day) {
  if (!plan.value || pendingDay.value !== null) return
  pendingDay.value = day.dayIndex
  try {
    const updated = await student.planDayDone(plan.value.id, day.dayIndex, !day.done)
    if (updated) plan.value = updated
    else await loadDetail(plan.value.id)
    toast.success(day.done ? `第 ${day.dayIndex} 天已取消打卡` : `第 ${day.dayIndex} 天打卡完成`)
  } catch (error) {
    toast.error(error.message || '打卡失败')
  } finally {
    pendingDay.value = null
  }
}

function dayDate(day) {
  return day.date ? formatDate(day.date) : `第 ${day.dayIndex} 天`
}

function textOf(value) {
  if (value === null || value === undefined) return ''
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  if (Array.isArray(value)) return value.map(textOf).join('；')
  return value.text || value.title || value.content || value.summary || JSON.stringify(value)
}

function practiceList(practice) {
  if (!practice) return []
  if (Array.isArray(practice.questions)) return practice.questions
  if (typeof practice === 'string') return [practice]
  return Object.values(practice).flat().filter((item) => item !== null && item !== undefined)
}

function practiceText(item) {
  if (typeof item === 'string') return item
  if (!item || typeof item !== 'object') return String(item)
  const stem = item.stem || item.questionText || item.text || item.title
  const answer = item.answer ? `（参考答案：${textOf(item.answer)}）` : ''
  return `${stem || JSON.stringify(item)}${answer}`
}

function checklistList(review) {
  if (!review) return []
  if (Array.isArray(review.checklist)) return review.checklist
  if (typeof review === 'string') return [review]
  return []
}

onMounted(() => {
  loadDictionaries()
  loadKnowledgePoints()
  loadPlans(1)
})
</script>

<template>
  <div>
    <div class="module-intro">
      <p class="eyebrow">学习计划 · STUDY PLAN</p>
      <h1>按天拆解，稳步推进</h1>
      <p>根据薄弱知识点与目标生成计划，每天包含学习、练习与复盘三部分；完成后勾选打卡。</p>
    </div>

    <div class="flex-between" style="margin-bottom: 16px">
      <div class="flex-row" style="gap: 8px">
        <button class="btn btn-primary btn-sm" @click="showGenerate = !showGenerate">
          {{ showGenerate ? '收起生成表单' : '＋ 生成新计划' }}
        </button>
        <button class="btn btn-outline btn-sm" :disabled="listLoading" @click="loadPlans(listPage)">
          {{ listLoading ? '刷新中…' : '刷新列表' }}
        </button>
      </div>
      <span class="muted" style="font-size: 12px">共 {{ listTotal }} 份计划</span>
    </div>

    <!-- 生成表单 -->
    <section v-if="showGenerate" class="panel" style="margin-bottom: 16px">
      <div class="panel-heading">
        <div><h3>生成学习计划</h3><p>AI 会根据周期、天数、目标与聚焦知识点编排每日任务</p></div>
      </div>
      <div v-if="formError" class="alert alert-error" style="margin-bottom: 14px">{{ formError }}</div>
      <div class="form-grid cols-3">
        <div class="form-field">
          <label>学习周期 <span class="required">*</span></label>
          <select v-model="form.period" class="select" :disabled="generating" @change="onPeriodChange">
            <option v-for="option in periodOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
          </select>
        </div>
        <div class="form-field">
          <label>计划天数 <span class="required">*</span></label>
          <input v-model.number="form.days" class="input" type="number" min="1" max="60" :disabled="generating" />
          <span class="form-hint">1 ~ 60 天，默认跟随周期</span>
        </div>
        <div class="form-field">
          <label>聚焦知识点</label>
          <button class="btn btn-outline btn-sm" style="justify-content: flex-start" @click="showFocusPicker = !showFocusPicker">
            已选 {{ focusKpIds.length }} 个 · {{ showFocusPicker ? '收起' : '选择' }}
          </button>
        </div>
        <div class="form-field full">
          <label>学习目标</label>
          <textarea
            v-model="form.goal"
            class="textarea"
            rows="2"
            placeholder="例如：两周内掌握极限与导数计算，把薄弱知识点提升到 60% 以上。"
            :disabled="generating"
          ></textarea>
        </div>
      </div>

      <div v-if="showFocusPicker" style="margin-top: 6px">
        <div v-if="kpLoading" class="loading-inline"><span class="spinner"></span> 正在加载知识点…</div>
        <div v-else class="chip-group kp-picker">
          <button
            v-for="kp in knowledgePoints"
            :key="kp.kpId"
            type="button"
            class="chip"
            :class="{ selected: focusKpIds.includes(kp.kpId) }"
            @click="toggleFocus(kp.kpId)"
          >
            {{ kp.kpName }} <span class="muted">{{ percentText(kp.mastery) }}</span>
          </button>
        </div>
      </div>

      <div class="exam-actions">
        <button class="btn btn-primary" :disabled="generating" @click="generate">
          <span v-if="generating" class="spinner light"></span>
          {{ generating ? 'AI 正在生成计划（最长 90 秒）…' : '生成学习计划' }}
        </button>
        <button class="btn btn-outline" :disabled="generating" @click="showGenerate = false">取消</button>
      </div>
    </section>

    <div class="plan-layout">
      <!-- 计划列表 -->
      <section class="panel">
        <div class="panel-heading">
          <div><h3>我的计划</h3><p>点击切换查看每日任务</p></div>
        </div>
        <SkeletonBlock v-if="listLoading" :show-cards="false" :rows="4" />
        <ErrorState v-else-if="listError" :message="listError" :show-cards="false" @retry="loadPlans(1)" />
        <div v-else-if="plans.length" class="plan-list">
          <button
            v-for="item in plans"
            :key="item.id"
            type="button"
            class="plan-list-item"
            :class="{ active: plan && plan.id === item.id }"
            @click="selectPlan(item)"
          >
            <span class="plan-list-main">
              <strong>{{ item.title }}</strong>
              <span>{{ PERIOD_LABEL[item.period] || item.period }} · {{ item.daysCount }} 天 · 完成 {{ item.doneDays || 0 }} 天 · {{ percentText(item.progress) }}</span>
            </span>
            <span class="tag green">{{ percentText(item.progress) }}</span>
          </button>
          <div class="pager" style="margin-top: 12px">
            <span class="muted">第 {{ listPage }} 页</span>
            <div class="pager-actions">
              <button class="btn btn-ghost btn-sm" :disabled="listPage <= 1" @click="loadPlans(listPage - 1)">上一页</button>
              <button class="btn btn-ghost btn-sm" :disabled="!listHasNext" @click="loadPlans(listPage + 1)">下一页</button>
            </div>
          </div>
        </div>
        <EmptyState v-else icon="▤" title="还没有学习计划" description="点击上方「生成新计划」，让 AI 为你排一份计划。">
          <template #action>
            <button class="btn btn-primary btn-sm" style="margin-top: 12px" @click="showGenerate = true">生成计划</button>
          </template>
        </EmptyState>
      </section>

      <!-- 计划详情 -->
      <section>
        <SkeletonBlock v-if="detailLoading" :show-cards="false" :rows="6" />
        <ErrorState v-else-if="detailError" :title="'计划详情加载失败'" :message="detailError" :show-cards="false" @retry="loadDetail(plan && plan.id)" />
        <template v-else-if="plan">
          <div class="plan-banner">
            <div>
              <span class="eyebrow">{{ PERIOD_LABEL[plan.period] || plan.period }} · 共 {{ totalDays }} 天</span>
              <h2>{{ plan.title }}</h2>
              <p>开始日期 {{ formatDate(plan.startDate) }} · 已完成 {{ doneDays }} / {{ totalDays }} 天</p>
              <div class="progress-track thick" style="margin-top: 12px; max-width: 420px">
                <div class="progress-fill" :style="{ width: planProgress + '%' }"></div>
              </div>
            </div>
            <div class="plan-ring" :style="{ '--progress': planProgress + '%' }">
              <div>{{ planProgress }}%</div>
            </div>
          </div>

          <div v-if="plan.summary" class="panel" style="margin-bottom: 16px">
            <div class="panel-heading"><div><h3>计划说明</h3></div></div>
            <MarkdownView :content="plan.summary" />
          </div>

          <div class="plan-days">
            <article v-for="day in plan.days || []" :key="day.dayIndex" class="day-card" :class="{ done: day.done }">
              <div class="day-head">
                <span class="day-badge">{{ day.dayIndex }}</span>
                <div class="day-title">
                  <strong>{{ day.kpName || '综合复习' }}</strong>
                  <span>{{ dayDate(day) }} · {{ day.done ? '已完成' : '待完成' }}</span>
                </div>
                <button
                  class="btn btn-sm"
                  :class="day.done ? 'btn-outline' : 'btn-primary'"
                  :disabled="pendingDay !== null"
                  @click="toggleDay(day)"
                >
                  {{ pendingDay === day.dayIndex ? '提交中…' : day.done ? '取消打卡' : '完成打卡' }}
                </button>
              </div>
              <div class="day-body">
                <p v-if="day.goal" class="muted" style="margin: 0 0 10px">当日目标：{{ day.goal }}</p>
                <div class="day-section">
                  <h5>学习</h5>
                  <MarkdownView v-if="day.study && day.study.summary" :content="day.study.summary" />
                  <ul v-if="day.study && (day.study.points || []).length">
                    <li v-for="(point, index) in day.study.points" :key="index">{{ textOf(point) }}</li>
                  </ul>
                  <p v-if="day.study && day.study.example" class="muted">示例：{{ textOf(day.study.example) }}</p>
                </div>
                <div class="day-section">
                  <h5>练习</h5>
                  <div
                    v-for="(question, index) in practiceList(day.practice)"
                    :key="index"
                    class="day-practice-item"
                  >
                    {{ index + 1 }}. {{ practiceText(question) }}
                  </div>
                  <p v-if="!practiceList(day.practice).length" class="muted">今日暂无练习</p>
                </div>
                <div class="day-section">
                  <h5>复盘</h5>
                  <MarkdownView v-if="day.review && day.review.summary" :content="day.review.summary" />
                  <ul v-if="checklistList(day.review).length">
                    <li v-for="(item, index) in checklistList(day.review)" :key="index">{{ textOf(item) }}</li>
                  </ul>
                </div>
              </div>
            </article>
          </div>
          <EmptyState v-if="!plan.days || !plan.days.length" icon="▤" title="计划暂无每日内容" description="请重新生成计划，或等待 AI 服务返回完整内容。" />
        </template>
        <EmptyState v-else icon="▤" title="请选择一份计划" description="从左侧列表选择计划查看每日学习安排。" />
      </section>
    </div>
  </div>
</template>

<style scoped>
.plan-layout { display: grid; grid-template-columns: 300px minmax(0, 1fr); gap: 16px; align-items: start; }
.plan-list { display: grid; gap: 8px; }
.plan-list .plan-list-item { width: 100%; text-align: left; font: inherit; color: inherit; border: 1px solid transparent; background: transparent; }
.kp-picker { display: flex; flex-wrap: wrap; gap: 8px; max-height: 200px; overflow-y: auto; }
@media (max-width: 1100px) {
  .plan-layout { grid-template-columns: 1fr; }
}
</style>
