<script setup>
/**
 * 班级学情 T6
 * GET /teacher/analysis?period=7D|30D|TERM
 */
import { computed, onMounted, ref } from 'vue'
import { teacher } from '../../api'
import { PRIORITY_LABEL, formatDateTime, percentText } from '../../utils/format'
import SkeletonBlock from '../../components/SkeletonBlock.vue'
import ErrorState from '../../components/ErrorState.vue'
import EmptyState from '../../components/EmptyState.vue'
import MasteryBars from '../../components/MasteryBars.vue'
import MarkdownView from '../../components/MarkdownView.vue'

const props = defineProps({
  user: { type: Object, required: true },
  navigate: { type: Function, required: true },
})

const PERIODS = [
  { key: '7D', label: '近 7 天' },
  { key: '30D', label: '近 30 天' },
  { key: 'TERM', label: '本学期' },
]

const period = ref('7D')
const loading = ref(true)
const error = ref('')
const data = ref(null)

const overview = computed(() => (data.value && data.value.overview) || {})
const distribution = computed(() => (data.value && data.value.masteryDistribution) || [])
const weakTop10 = computed(() => (data.value && data.value.weakTop10) || [])
const errorSummary = computed(() => (data.value && data.value.errorSummary) || [])
const hotQuestions = computed(() => (data.value && data.value.hotQuestions) || [])
const ranking = computed(() => (data.value && data.value.ranking) || [])
const advice = computed(() => (data.value && data.value.advice) || [])

const distributionMax = computed(() => {
  let max = 1
  distribution.value.forEach((item) => {
    const count = Number(item.count) || 0
    if (count > max) max = count
  })
  return max
})

const rankingMax = computed(() => {
  let max = 0.0001
  ranking.value.forEach((item) => {
    const value = Number(item.mastery) || 0
    if (value > max) max = value
  })
  return max
})

async function load(target = period.value) {
  period.value = target
  loading.value = true
  error.value = ''
  try {
    data.value = await teacher.analysis(target)
  } catch (err) {
    error.value = err.message || '班级学情加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(() => load('7D'))
</script>

<template>
  <div>
    <div class="module-intro">
      <p class="eyebrow">班级学情 · CLASS ANALYSIS</p>
      <h1>班级学习数据分析</h1>
      <p>基于本班答题与答疑记录生成分析，并给出教学建议。AI 生成内容需要几秒，请稍候。</p>
    </div>

    <div class="tab-bar" style="margin-bottom: 16px">
      <button
        v-for="item in PERIODS"
        :key="item.key"
        class="tab"
        :class="{ selected: period === item.key }"
        :disabled="loading"
        @click="load(item.key)"
      >
        {{ item.label }}
      </button>
      <span v-if="data && data.generatedAt" class="muted" style="margin-left: auto; font-size: 11px">
        生成于 {{ formatDateTime(data.generatedAt) }}
      </span>
    </div>

    <SkeletonBlock v-if="loading" :rows="8" :cards="4" />
    <ErrorState
      v-else-if="error"
      title="班级学情加载失败"
      :message="error"
      hint="班级学情由 AI 服务汇总生成，请确认 8000 端口服务已启动。"
      @retry="load(period)"
    />
    <template v-else-if="data">
      <div v-if="data.summary" class="alert alert-info" style="margin-bottom: 16px; line-height: 1.7">
        <strong>整体结论：</strong>{{ data.summary }}
      </div>

      <div class="stats-grid cols-4" style="margin-bottom: 16px">
        <div class="stat-card">
          <div class="stat-top"><span class="stat-icon green">◎</span><span class="mini-badge">班级人数</span></div>
          <div class="stat-number">{{ overview.studentCount || 0 }}<small>人</small></div>
          <div class="stat-foot">活跃 {{ overview.activeStudents || 0 }} 人</div>
        </div>
        <div class="stat-card">
          <div class="stat-top"><span class="stat-icon purple">◐</span><span class="mini-badge">掌握度均值</span></div>
          <div class="stat-number">{{ percentText(overview.avgMastery) }}</div>
          <div class="progress-track" style="margin-top: 8px">
            <div class="progress-fill" :style="{ width: (Number(overview.avgMastery) * 100 || 0) + '%' }"></div>
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-top"><span class="stat-icon orange">✳</span><span class="mini-badge">答疑互动</span></div>
          <div class="stat-number">{{ overview.interactionCount || 0 }}<small>次</small></div>
          <div class="stat-foot">统计区间内</div>
        </div>
        <div class="stat-card">
          <div class="stat-top"><span class="stat-icon green">✓</span><span class="mini-badge">答题正确率</span></div>
          <div class="stat-number">{{ percentText(overview.accuracy) }}</div>
          <div class="progress-track" style="margin-top: 8px">
            <div class="progress-fill" :style="{ width: (Number(overview.accuracy) * 100 || 0) + '%' }"></div>
          </div>
        </div>
      </div>

      <div class="grid-2" style="margin-bottom: 16px">
        <section class="panel">
          <div class="panel-heading"><div><h3>掌握度分布</h3><p>全班知识点掌握档位人数</p></div></div>
          <div v-if="distribution.length">
            <div v-for="item in distribution" :key="item.range" class="distribution-row">
              <div class="distribution-head">
                <span>{{ item.range }}</span>
                <strong>{{ item.count }} 人</strong>
              </div>
              <div class="progress-track">
                <div class="progress-fill" :style="{ width: ((Number(item.count) || 0) / distributionMax) * 100 + '%' }"></div>
              </div>
            </div>
          </div>
          <EmptyState v-else icon="▥" title="暂无分布数据" description="学生完成诊断后才会生成掌握度分布。" />
        </section>

        <section class="panel">
          <div class="panel-heading"><div><h3>共性错因</h3><p>按错误类型聚合，含典型例题</p></div></div>
          <div v-if="errorSummary.length">
            <div v-for="item in errorSummary" :key="item.errorType" class="log-item">
              <div class="log-head">
                <strong>{{ item.errorType }}</strong>
                <span class="tag orange">{{ item.count }} 次 · {{ percentText(item.ratio) }}</span>
              </div>
              <div v-if="item.examples && item.examples.length" class="muted" style="font-size: 12px; margin-top: 6px">
                <div v-for="(example, index) in item.examples.slice(0, 2)" :key="index" style="margin: 4px 0">
                  <MarkdownView :content="example" />
                </div>
              </div>
            </div>
          </div>
          <EmptyState v-else icon="!" title="暂无错因数据" description="诊断与练习产生的错题会按错因聚合。" />
        </section>
      </div>

      <div class="lower-grid" style="margin-bottom: 16px">
        <section class="panel">
          <div class="panel-heading"><div><h3>薄弱知识点 TOP10</h3><p>按平均掌握度升序</p></div></div>
          <MasteryBars :items="weakTop10" label-key="kpName" value-key="avgMastery" empty-text="暂无薄弱知识点数据" />
          <div v-if="weakTop10.length" style="margin-top: 10px">
            <div v-for="kp in weakTop10" :key="kp.kpId" class="muted" style="font-size: 11px; margin-top: 2px">
              {{ kp.kpName }}：{{ kp.studentCount || 0 }} 人未掌握（平均 {{ percentText(kp.avgMastery) }}）
            </div>
          </div>
        </section>

        <section class="panel">
          <div class="panel-heading"><div><h3>学生排行</h3><p>按掌握度展示班级学习状态</p></div></div>
          <div v-if="ranking.length">
            <div v-for="(item, index) in ranking" :key="item.studentId" class="knowledge-row">
              <div class="knowledge-label" style="min-width: 120px">
                <span class="question-index" style="margin-right: 6px">{{ index + 1 }}</span>{{ item.displayName }}
              </div>
              <div class="progress-track">
                <div
                  class="progress-fill"
                  :style="{ width: ((Number(item.mastery) || 0) / rankingMax) * 100 + '%' }"
                ></div>
              </div>
              <span class="muted" style="width: 90px; text-align: right; font-size: 12px">
                {{ percentText(item.mastery) }} · {{ item.interactions || 0 }} 次
              </span>
            </div>
          </div>
          <EmptyState v-else icon="◎" title="暂无排行数据" description="学生产生学习行为后显示排行。" />
        </section>
      </div>

      <div class="grid-2" style="margin-bottom: 16px">
        <section class="panel">
          <div class="panel-heading"><div><h3>高频问题</h3><p>学生问得最多的问题</p></div></div>
          <div v-if="hotQuestions.length">
            <div v-for="(item, index) in hotQuestions" :key="index" class="record-item">
              <div class="record-icon">{{ index + 1 }}</div>
              <div class="record-main">
                <div class="record-snippet" style="margin: 0"><MarkdownView :content="item.question" /></div>
                <div class="record-meta">
                  <span class="tag gray">提问 {{ item.count }} 次</span>
                  <span class="record-time">{{ formatDateTime(item.lastAskedAt) }}</span>
                </div>
              </div>
            </div>
          </div>
          <EmptyState v-else icon="✳" title="暂无高频问题" description="学生答疑记录会聚合为高频问题。" />
        </section>

        <section class="panel">
          <div class="panel-heading"><div><h3>教学建议</h3><p>由 AI 根据学情生成</p></div></div>
          <div v-if="advice.length">
            <div v-for="(item, index) in advice" :key="index" class="advice-card" :class="(item.priority || 'medium').toLowerCase()">
              <div class="flex-between">
                <strong>{{ item.title }}</strong>
                <span class="tag" :class="item.priority === 'HIGH' ? 'red' : item.priority === 'LOW' ? 'gray' : 'orange'">
                  {{ PRIORITY_LABEL[item.priority] || '中' }}优先级
                </span>
              </div>
              <p class="muted" style="margin: 6px 0 0; line-height: 1.7">{{ item.content }}</p>
            </div>
          </div>
          <EmptyState v-else icon="✦" title="暂无教学建议" description="统计区间内数据不足时不会生成建议。" />
        </section>
      </div>
    </template>
  </div>
</template>
