<script setup>
/**
 * 学生首页概览 S1：GET /student/dashboard
 * 展示掌握度均值与分布、薄弱 TOP5、学习统计、当前计划进度、最近报告。
 */
import { computed, onMounted, ref } from 'vue'
import { student } from '../../api'
import { percentText, REPORT_TYPE_LABEL, formatDateTime, masteryStatus } from '../../utils/format'
import MasteryBars from '../../components/MasteryBars.vue'
import SkeletonBlock from '../../components/SkeletonBlock.vue'
import ErrorState from '../../components/ErrorState.vue'
import EmptyState from '../../components/EmptyState.vue'
import MarkdownView from '../../components/MarkdownView.vue'

const props = defineProps({
  user: { type: Object, required: true },
  navigate: { type: Function, required: true },
})

const loading = ref(true)
const error = ref('')
const data = ref(null)
const reportDrawer = ref(null)
const reportLoading = ref(false)

const mastery = computed(() => (data.value && data.value.mastery) || {})
const stats = computed(() => (data.value && data.value.stats) || {})
const currentPlan = computed(() => data.value && data.value.currentPlan)
const weakList = computed(() => (data.value && data.value.weakTop5) || [])
const reports = computed(() => (data.value && data.value.recentReports) || [])
const distribution = computed(() => {
  const list = (mastery.value && mastery.value.distribution) || []
  const max = Math.max(1, ...list.map((row) => Number(row.count) || 0))
  return list.map((row) => ({
    range: row.range,
    count: Number(row.count) || 0,
    percent: ((Number(row.count) || 0) / max) * 100,
  }))
})
const avgStatus = computed(() => masteryStatus(mastery.value.avg))

const statCards = computed(() => [
  { label: '累计答疑', value: stats.value.interactionCount ?? 0, unit: '次', note: `今日 ${stats.value.todayInteractionCount ?? 0} 次`, icon: '✳' },
  { label: '诊断次数', value: stats.value.diagnosisCount ?? 0, unit: '次', note: '快速 / 全面诊断', icon: '▥' },
  { label: '练习次数', value: stats.value.practiceCount ?? 0, unit: '次', note: '分层练习记录', icon: '✎' },
  { label: '待复盘错题', value: stats.value.unreviewedWrongCount ?? 0, unit: '道', note: `错题总计 ${stats.value.wrongCount ?? 0} 道`, icon: '⚑' },
])

async function load() {
  loading.value = true
  error.value = ''
  try {
    data.value = await student.dashboard()
  } catch (err) {
    error.value = err.message || '加载失败'
  } finally {
    loading.value = false
  }
}

async function openReport(report) {
  if (!report || !report.id) return
  reportDrawer.value = { id: report.id, title: report.title, loading: true }
  reportLoading.value = true
  try {
    const detail = await student.reportDetail(report.id)
    reportDrawer.value = detail || { id: report.id, title: report.title }
  } catch (err) {
    reportDrawer.value = { id: report.id, title: report.title, error: err.message }
  } finally {
    reportLoading.value = false
  }
}

function closeReport() {
  reportDrawer.value = null
}

function contentEntries(content) {
  if (!content || typeof content !== 'object') return []
  return Object.entries(content).filter(([, value]) => value !== null && value !== undefined && value !== '')
}

function entryValue(value) {
  if (Array.isArray(value)) {
    return value.map((item) => (typeof item === 'object' ? JSON.stringify(item) : String(item))).join(' / ')
  }
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

onMounted(load)
</script>

<template>
  <div>
    <div class="module-intro">
      <p class="eyebrow">学习概览 · STUDENT DASHBOARD</p>
      <h1>你好，{{ user.displayName || user.username }}</h1>
      <p>
        {{ (data && data.classInfo && data.classInfo.className) || user.className || '高等数学' }}
        · 目标院校 {{ user.targetSchool || '待设置' }} · 掌握度均值 {{ percentText(mastery.avg) }}
      </p>
    </div>

    <SkeletonBlock v-if="loading" :cards="4" :rows="5" />
    <ErrorState v-else-if="error" :message="error" @retry="load" />

    <template v-else-if="data">
      <div class="stats-grid cols-4">
        <div class="stat-card">
          <div class="stat-top">
            <span class="stat-icon purple">◎</span>
            <span class="tag" :class="avgStatus.cls">{{ avgStatus.text }}</span>
          </div>
          <div class="stat-number">{{ percentText(mastery.avg) }}</div>
          <div class="stat-foot">掌握度均值 · 覆盖 {{ mastery.totalKp || 0 }} 个知识点</div>
          <div class="progress-track thick" style="margin-top: 12px">
            <div class="progress-fill" :style="{ width: Math.min(100, (mastery.avg || 0) * 100) + '%' }"></div>
          </div>
        </div>

        <div class="stat-card">
          <div class="stat-top">
            <span class="stat-icon orange">⚑</span>
            <span class="tag orange">薄弱</span>
          </div>
          <div class="stat-number">{{ mastery.weakCount ?? 0 }}<small> / {{ mastery.totalKp ?? 0 }}</small></div>
          <div class="stat-foot">掌握度低于 30% 的知识点</div>
          <div class="stat-foot" style="margin-top: 10px">建议优先诊断与练习</div>
        </div>

        <div v-for="card in statCards.slice(0, 2)" :key="card.label" class="stat-card">
          <div class="stat-top">
            <span class="stat-icon green">{{ card.icon }}</span>
            <span class="mini-badge">{{ card.label }}</span>
          </div>
          <div class="stat-number">{{ card.value }}<small>{{ card.unit }}</small></div>
          <div class="stat-foot">{{ card.note }}</div>
        </div>
      </div>

      <div class="lower-grid">
        <section class="panel">
          <div class="panel-heading">
            <div>
              <h3>薄弱知识点 TOP5</h3>
              <p>按掌握度由低到高排序，建议优先突破</p>
            </div>
            <button class="text-button" @click="navigate('diagnose')">去诊断 →</button>
          </div>
          <MasteryBars v-if="weakList.length" :items="weakList" />
          <EmptyState
            v-else
            icon="✓"
            title="暂无薄弱知识点"
            description="完成一次知识诊断后，这里会展示掌握度最低的 5 个知识点。"
          />
        </section>

        <section class="panel">
          <div class="panel-heading">
            <div>
              <h3>掌握度分布</h3>
              <p>各掌握度区间覆盖的知识点数量</p>
            </div>
          </div>
          <div v-if="distribution.length" class="distribution-list">
            <div v-for="row in distribution" :key="row.range" class="distribution-row">
              <div class="distribution-head">
                <span>{{ row.range }}</span>
                <strong>{{ row.count }} 个</strong>
              </div>
              <div class="progress-track">
                <div class="progress-fill" :style="{ width: row.percent + '%' }"></div>
              </div>
            </div>
          </div>
          <EmptyState v-else icon="▥" title="暂无分布数据" description="诊断之后将生成掌握度分布。" />
        </section>
      </div>

      <section class="panel" style="margin-top: 16px">
        <div class="panel-heading">
          <div>
            <h3>当前学习计划</h3>
            <p>按天推进「学习 - 练习 - 复盘」，完成后自动更新进度</p>
          </div>
          <button class="btn btn-outline btn-sm" @click="navigate('plan')">
            {{ currentPlan ? '查看计划' : '生成计划' }}
          </button>
        </div>
        <div v-if="currentPlan" class="plan-banner" style="margin: 0">
          <div>
            <span class="eyebrow">{{ currentPlan.period }} · {{ currentPlan.daysCount }} 天</span>
            <h2>{{ currentPlan.title }}</h2>
            <p>已完成 {{ currentPlan.doneDays || 0 }} / {{ currentPlan.daysCount || 0 }} 天</p>
            <div class="progress-track thick" style="margin-top: 12px; max-width: 420px">
              <div class="progress-fill" :style="{ width: Math.round((currentPlan.progress || 0) * 100) + '%' }"></div>
            </div>
          </div>
          <div class="plan-ring" :style="{ '--progress': Math.round((currentPlan.progress || 0) * 100) + '%' }">
            <div>{{ Math.round((currentPlan.progress || 0) * 100) }}%</div>
          </div>
        </div>
        <EmptyState
          v-else
          icon="▤"
          title="还没有学习计划"
          description="根据薄弱知识点生成一份按天推进的学习计划，学习更有效率。"
        >
          <template #action>
            <button class="btn btn-primary btn-sm" style="margin-top: 12px" @click="navigate('plan')">去生成计划</button>
          </template>
        </EmptyState>
      </section>

      <div class="lower-grid">
        <section class="panel">
          <div class="panel-heading">
            <div>
              <h3>最近学习报告</h3>
              <p>诊断、练习与学习计划报告</p>
            </div>
            <button class="text-button" @click="navigate('records')">全部记录 →</button>
          </div>
          <div v-if="reports.length" class="report-list">
            <button v-for="report in reports" :key="report.id" class="record-item report-row" @click="openReport(report)">
              <span class="record-icon">▥</span>
              <span class="record-main">
                <strong>{{ report.title || REPORT_TYPE_LABEL[report.type] || '学习报告' }}</strong>
                <span class="record-snippet">{{ report.summary || '暂无摘要' }}</span>
              </span>
              <span class="record-time">{{ formatDateTime(report.createdAt) }}</span>
            </button>
          </div>
          <EmptyState v-else icon="▥" title="暂无学习报告" description="完成知识诊断后会自动生成诊断报告。" />
        </section>

        <section class="panel">
          <div class="panel-heading">
            <div>
              <h3>学习统计</h3>
              <p>累计学习行为数据</p>
            </div>
          </div>
          <div class="stats-grid" style="grid-template-columns: 1fr 1fr; margin-top: 0">
            <div v-for="card in statCards" :key="card.label" class="stat-card">
              <div class="stat-top">
                <span class="stat-icon green">{{ card.icon }}</span>
              </div>
              <div class="stat-number">{{ card.value }}<small>{{ card.unit }}</small></div>
              <div class="stat-foot">{{ card.label }} · {{ card.note }}</div>
            </div>
          </div>
        </section>
      </div>
    </template>

    <Transition name="drawer">
      <div v-if="reportDrawer" class="mask" @click.self="closeReport">
        <div class="drawer" style="max-width: 560px">
          <div class="drawer-header">
            <div>
              <h3>{{ reportDrawer.title || '报告详情' }}</h3>
              <p>{{ reportDrawer.type ? REPORT_TYPE_LABEL[reportDrawer.type] || reportDrawer.type : '学习报告' }}</p>
            </div>
            <button class="drawer-close" @click="closeReport">✕</button>
          </div>
          <div class="drawer-body">
            <div v-if="reportLoading" class="skeleton">
              <div class="skeleton-line w-60"></div>
              <div class="skeleton-line w-80"></div>
              <div class="skeleton-line w-40"></div>
            </div>
            <div v-else-if="reportDrawer.error" class="alert alert-error">{{ reportDrawer.error }}</div>
            <template v-else>
              <div class="detail-block">
                <h4>基本信息</h4>
                <p class="muted">{{ formatDateTime(reportDrawer.createdAt) }} · 状态 {{ reportDrawer.status || '—' }}</p>
              </div>
              <div class="detail-block">
                <h4>摘要</h4>
                <MarkdownView :content="reportDrawer.summary || '暂无摘要'" />
              </div>
              <div v-for="[key, value] in contentEntries(reportDrawer.content)" :key="key" class="detail-block">
                <h4>{{ key }}</h4>
                <MarkdownView v-if="typeof value === 'string'" :content="value" />
                <p v-else class="muted">{{ entryValue(value) }}</p>
              </div>
            </template>
          </div>
          <div class="drawer-footer">
            <button class="btn btn-outline btn-sm" @click="closeReport">关闭</button>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.distribution-list { display: grid; gap: 2px; }
.report-list { display: grid; }
.report-row { width: 100%; text-align: left; border: 0; background: transparent; font: inherit; color: inherit; }
.report-row .record-main { display: grid; gap: 5px; min-width: 0; }
.report-row .record-main strong { font-size: 12.5px; }
</style>
