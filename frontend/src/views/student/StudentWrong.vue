<script setup>
/**
 * 错题复盘 S7 / S8
 * GET /student/wrong-questions?kpId&errorType&reviewed&page&size；PATCH /student/wrong-questions/{id} {reviewed:true}
 */
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { common, student } from '../../api'
import { toast } from '../../toast'
import { formatDateTime } from '../../utils/format'
import SkeletonBlock from '../../components/SkeletonBlock.vue'
import ErrorState from '../../components/ErrorState.vue'
import EmptyState from '../../components/EmptyState.vue'
import MarkdownView from '../../components/MarkdownView.vue'

const props = defineProps({
  user: { type: Object, required: true },
  navigate: { type: Function, required: true },
})

const DEFAULT_ERROR_TYPES = ['概念混淆', '计算失误', '审题偏差', '方法不当']

const loading = ref(true)
const error = ref('')
const items = ref([])
const stats = ref({ total: 0, reviewed: 0, byErrorType: [] })
const page = ref(1)
const size = ref(10)
const total = ref(0)
const hasNext = ref(false)
const knowledgePoints = ref([])
const errorTypes = ref(DEFAULT_ERROR_TYPES)
const markingId = ref(null)

const filters = reactive({ kpId: '', errorType: '', reviewed: '' })

const reviewedCount = computed(() => {
  const fromStats = Number(stats.value.reviewed)
  if (!Number.isNaN(fromStats) && fromStats >= 0) return fromStats
  return items.value.filter((item) => item.reviewed).length
})

const unreviewedCount = computed(() => Math.max(0, (Number(stats.value.total) || total.value) - reviewedCount.value))

async function loadMeta() {
  try {
    const points = await common.knowledgePoints()
    knowledgePoints.value = points || []
  } catch {
    knowledgePoints.value = []
  }
  try {
    const dict = await common.dictionaries()
    if (dict && Array.isArray(dict.errorTypes) && dict.errorTypes.length) {
      errorTypes.value = dict.errorTypes.map((item) => (typeof item === 'string' ? item : item.label || item.value))
    }
  } catch {
    /* 使用内置错误类型 */
  }
}

async function load(targetPage = 1) {
  loading.value = true
  error.value = ''
  try {
    const data = await student.wrongQuestions({
      kpId: filters.kpId || undefined,
      errorType: filters.errorType || undefined,
      reviewed: filters.reviewed === '' ? undefined : filters.reviewed,
      page: targetPage,
      size: size.value,
    })
    const list = (data && data.items) || []
    items.value = list
    page.value = (data && data.page) || targetPage
    total.value = (data && data.total) || list.length
    hasNext.value = !!(data && data.hasNext)
    if (data && data.stats) stats.value = data.stats
  } catch (err) {
    error.value = err.message || '错题加载失败'
  } finally {
    loading.value = false
  }
}

async function markReviewed(item) {
  if (!item || !item.id || markingId.value !== null) return
  markingId.value = item.id
  try {
    await student.markWrongReviewed(item.id, true)
    item.reviewed = true
    if (stats.value) {
      stats.value.reviewed = (Number(stats.value.reviewed) || 0) + 1
    }
    toast.success('已标记为「已复盘」')
  } catch (err) {
    toast.error(err.message || '标记失败')
  } finally {
    markingId.value = null
  }
}

let filterTimer = null
watch(
  () => [filters.kpId, filters.errorType, filters.reviewed],
  () => {
    if (filterTimer) clearTimeout(filterTimer)
    filterTimer = setTimeout(() => load(1), 250)
  }
)

onMounted(() => {
  loadMeta()
  load(1)
})
</script>

<template>
  <div>
    <div class="module-intro">
      <p class="eyebrow">错题复盘 · WRONG QUESTIONS</p>
      <h1>把错题变成得分点</h1>
      <p>按错误类型与知识点筛选错题，查看解析与正确答案，复盘完成后标记状态。</p>
    </div>

    <div class="stats-grid" style="margin-bottom: 16px">
      <div class="stat-card">
        <div class="stat-top"><span class="stat-icon orange">⚑</span><span class="mini-badge">错题总数</span></div>
        <div class="stat-number">{{ stats.total || total || 0 }}<small>道</small></div>
        <div class="stat-foot">来自诊断与练习</div>
      </div>
      <div class="stat-card">
        <div class="stat-top"><span class="stat-icon green">✓</span><span class="mini-badge">已复盘</span></div>
        <div class="stat-number">{{ reviewedCount }}<small>道</small></div>
        <div class="stat-foot">已标记复盘完成</div>
      </div>
      <div class="stat-card">
        <div class="stat-top"><span class="stat-icon red">!</span><span class="mini-badge">待复盘</span></div>
        <div class="stat-number">{{ unreviewedCount }}<small>道</small></div>
        <div class="stat-foot">建议尽快复盘</div>
      </div>
      <div class="stat-card">
        <div class="stat-top"><span class="stat-icon purple">◔</span><span class="mini-badge">主要错因</span></div>
        <div class="stat-number" style="font-size: 20px">
          {{ (stats.byErrorType && stats.byErrorType[0] && stats.byErrorType[0].errorType) || '—' }}
        </div>
        <div class="stat-foot">
          {{ (stats.byErrorType && stats.byErrorType[0] && stats.byErrorType[0].count) || 0 }} 道
        </div>
      </div>
    </div>

    <section class="panel" style="margin-bottom: 16px">
      <div class="filter-bar">
        <div class="form-field">
          <label>错误类型</label>
          <select v-model="filters.errorType" class="select">
            <option value="">全部错因</option>
            <option v-for="type in errorTypes" :key="type" :value="type">{{ type }}</option>
          </select>
        </div>
        <div class="form-field">
          <label>知识点</label>
          <select v-model="filters.kpId" class="select">
            <option value="">全部知识点</option>
            <option v-for="kp in knowledgePoints" :key="kp.kpId" :value="kp.kpId">{{ kp.kpName }}</option>
          </select>
        </div>
        <div class="form-field">
          <label>复盘状态</label>
          <select v-model="filters.reviewed" class="select">
            <option value="">全部</option>
            <option :value="false">待复盘</option>
            <option :value="true">已复盘</option>
          </select>
        </div>
        <div class="form-field" style="justify-content: flex-end">
          <button
            class="btn btn-ghost btn-sm"
            @click="filters.kpId = ''; filters.errorType = ''; filters.reviewed = ''; load(1)"
          >
            清空筛选
          </button>
        </div>
      </div>
    </section>

    <section class="panel">
      <div class="panel-heading">
        <div><h3>错题列表</h3><p>共 {{ total }} 道错题</p></div>
        <button class="text-button" :disabled="loading" @click="load(page)">{{ loading ? '刷新中…' : '刷新' }}</button>
      </div>

      <SkeletonBlock v-if="loading" :show-cards="false" :rows="6" />
      <ErrorState v-else-if="error" :message="error" :show-cards="false" @retry="load(page)" />
      <template v-else-if="items.length">
        <article v-for="(item, index) in items" :key="item.id" class="wrong-item">
          <div class="wrong-head">
            <span class="question-index">{{ (page - 1) * size + index + 1 }}</span>
            <span class="tag green">{{ item.kpName || item.kpId }}</span>
            <span class="tag orange">{{ item.errorType || '未归类' }}</span>
            <span class="tag gray">难度 {{ item.difficulty }}</span>
            <span class="tag" :class="item.reviewed ? 'green' : 'red'">{{ item.reviewed ? '已复盘' : '待复盘' }}</span>
            <span class="record-time" style="margin-left: auto">{{ formatDateTime(item.createdAt) }}</span>
          </div>

          <div class="wrong-stem">
            <MarkdownView :content="item.questionText || '（题干缺失）'" />
          </div>

          <div class="answer-compare">
            <span class="wrong-answer">我的答案：{{ item.studentAnswer || '未作答' }}</span>
            <span class="right-answer">正确答案：{{ item.correctAnswer || '—' }}</span>
          </div>

          <div v-if="item.analysis" class="wrong-analysis">
            <MarkdownView :content="item.analysis" />
          </div>

          <div class="wrong-foot">
            <span class="muted" style="font-size: 11px">来源：{{ item.sourceType || '练习' }}</span>
            <button
              v-if="!item.reviewed"
              class="btn btn-primary btn-sm"
              :disabled="markingId !== null"
              @click="markReviewed(item)"
            >
              {{ markingId === item.id ? '提交中…' : '标记已复盘' }}
            </button>
            <span v-else class="tag green">复盘完成</span>
          </div>
        </article>

        <div class="pager">
          <span class="muted">第 {{ page }} 页 · 共 {{ total }} 道</span>
          <div class="pager-actions">
            <button class="btn btn-ghost btn-sm" :disabled="page <= 1 || loading" @click="load(page - 1)">上一页</button>
            <button class="btn btn-ghost btn-sm" :disabled="!hasNext || loading" @click="load(page + 1)">下一页</button>
          </div>
        </div>
      </template>
      <EmptyState
        v-else
        icon="✓"
        title="没有符合条件的错题"
        description="做一次诊断或练习后，答错的题目会自动收录到错题本。"
      >
        <template #action>
          <button class="btn btn-primary btn-sm" style="margin-top: 12px" @click="navigate('diagnose')">去做诊断</button>
        </template>
      </EmptyState>
    </section>
  </div>
</template>
