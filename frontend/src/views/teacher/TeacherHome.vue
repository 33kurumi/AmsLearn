<script setup>
/**
 * 教师端学情总览 T1
 * GET /teacher/dashboard
 */
import { computed, onMounted, ref } from 'vue'
import { teacher } from '../../api'
import { formatDateTime, percentText, truncate } from '../../utils/format'
import { RECORD_TYPE_LABEL, RECORD_TYPE_ICON } from '../../utils/format'
import SkeletonBlock from '../../components/SkeletonBlock.vue'
import ErrorState from '../../components/ErrorState.vue'
import EmptyState from '../../components/EmptyState.vue'
import MasteryBars from '../../components/MasteryBars.vue'

const props = defineProps({
  user: { type: Object, required: true },
  navigate: { type: Function, required: true },
})

const loading = ref(true)
const error = ref('')
const data = ref(null)

const stats = computed(() => (data.value && data.value.stats) || {})
const classInfo = computed(() => (data.value && data.value.classInfo) || {})
const knowledgeStats = computed(() => (data.value && data.value.knowledgeStats) || {})
const weakTop5 = computed(() => (data.value && data.value.weakTop5) || [])
const recentInteractions = computed(() => (data.value && data.value.recentInteractions) || [])

async function load() {
  loading.value = true
  error.value = ''
  try {
    data.value = await teacher.dashboard()
  } catch (err) {
    error.value = err.message || '学情总览加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div>
    <div class="module-intro">
      <p class="eyebrow">学情总览 · TEACHER DASHBOARD</p>
      <h1>你好，{{ (data && data.user && data.user.displayName) || user.displayName || '老师' }}</h1>
      <p>
        {{ classInfo.className || user.className || '班级' }} · {{ classInfo.subject || '高等数学' }} ·
        授课教师 {{ classInfo.teacherName || user.displayName || '—' }}
      </p>
    </div>

    <SkeletonBlock v-if="loading" :rows="6" :cards="4" />
    <ErrorState
      v-else-if="error"
      title="学情总览加载失败"
      :message="error"
      hint="教师端需要业务服务已启动且当前账号为教师角色。"
      @retry="load"
    />
    <template v-else>
      <div class="stats-grid cols-4">
        <div class="stat-card">
          <div class="stat-top"><span class="stat-icon green">◎</span><span class="mini-badge">班级学生</span></div>
          <div class="stat-number">{{ stats.studentCount || 0 }}<small>人</small></div>
          <div class="stat-foot">{{ classInfo.className || user.className || '—' }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-top"><span class="stat-icon purple">◐</span><span class="mini-badge">掌握度均值</span></div>
          <div class="stat-number">{{ percentText(stats.avgMastery) }}</div>
          <div class="progress-track" style="margin-top: 8px">
            <div class="progress-fill" :style="{ width: (Number(stats.avgMastery) * 100 || 0) + '%' }"></div>
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-top"><span class="stat-icon red">!</span><span class="mini-badge">薄弱学生</span></div>
          <div class="stat-number">{{ stats.weakStudentCount || 0 }}<small>人</small></div>
          <div class="stat-foot">掌握度低于 30%</div>
        </div>
        <div class="stat-card">
          <div class="stat-top"><span class="stat-icon orange">✳</span><span class="mini-badge">累计答疑</span></div>
          <div class="stat-number">{{ stats.interactionCount || 0 }}<small>次</small></div>
          <div class="stat-foot">今日 {{ stats.todayInteractionCount || 0 }} 次</div>
        </div>
      </div>

      <div class="lower-grid">
        <section class="panel">
          <div class="panel-heading">
            <div><h3>班级薄弱知识点 TOP5</h3><p>按平均掌握度升序，优先安排教学</p></div>
            <button class="text-button" @click="navigate('analysis')">查看班级学情 →</button>
          </div>
          <MasteryBars :items="weakTop5" label-key="kpName" value-key="mastery" empty-text="暂无薄弱知识点数据" />
          <div v-if="weakTop5.length" style="margin-top: 12px">
            <span class="muted" style="font-size: 11px">章节分布：</span>
            <span v-for="kp in weakTop5" :key="kp.kpId" class="tag gray" style="margin-left: 6px">{{ kp.chapter || '未分章' }}</span>
          </div>
        </section>

        <section class="panel">
          <div class="panel-heading">
            <div><h3>知识库状态</h3><p>支持检索的文档与切块统计</p></div>
            <button class="text-button" @click="navigate('knowledge')">管理知识库 →</button>
          </div>
          <div class="stats-grid cols-3" style="margin-bottom: 14px">
            <div class="stat-card" style="padding: 14px">
              <div class="stat-number small">{{ knowledgeStats.documents || 0 }}</div>
              <div class="stat-foot">文档数</div>
            </div>
            <div class="stat-card" style="padding: 14px">
              <div class="stat-number small">{{ knowledgeStats.chunks || 0 }}</div>
              <div class="stat-foot">知识切块</div>
            </div>
            <div class="stat-card" style="padding: 14px">
              <div class="stat-number small">{{ classInfo.className ? '本班' : '全局' }}</div>
              <div class="stat-foot">资料范围</div>
            </div>
          </div>
          <div class="alert alert-info" style="font-size: 12px; line-height: 1.6">
            知识库是答疑与出题的事实来源。教师可在「知识库管理」上传本班资料，关闭某类知识库后相关提问将不再命中。
          </div>
        </section>
      </div>

      <section class="panel">
        <div class="panel-heading">
          <div><h3>最近答疑动态</h3><p>学生最近向 AI 提出的问题</p></div>
          <button class="text-button" @click="navigate('students')">查看学生记录 →</button>
        </div>
        <div v-if="recentInteractions.length">
          <div v-for="(item, index) in recentInteractions" :key="index" class="record-item">
            <div class="record-icon">{{ RECORD_TYPE_ICON[item.type] || '✳' }}</div>
            <div class="record-main">
              <div class="flex-between">
                <strong class="text-strong" style="font-size: 13px">{{ item.studentName || '学生' }}</strong>
                <span class="record-time">{{ formatDateTime(item.createdAt) }}</span>
              </div>
              <p class="record-snippet" style="margin: 4px 0 0">{{ truncate(item.userMessage, 110) }}</p>
              <div style="margin-top: 6px">
                <span class="tag gray">{{ RECORD_TYPE_LABEL[item.type] || item.type || '答疑' }}</span>
              </div>
            </div>
          </div>
        </div>
        <EmptyState v-else icon="✳" title="暂无答疑记录" description="学生开始提问后，这里会显示最近的动态。" />

        <div class="divider"></div>
        <div class="section-heading"><h4>快捷操作</h4></div>
        <div class="grid-4" style="margin-top: 10px">
          <button class="outline-button" style="text-align: left" @click="navigate('config')">⚙ 班级配置<br /><small class="muted">回答模式与知识边界</small></button>
          <button class="outline-button" style="text-align: left" @click="navigate('analysis')">▥ 班级学情<br /><small class="muted">7D / 30D / 学期分析</small></button>
          <button class="outline-button" style="text-align: left" @click="navigate('knowledge')">▤ 知识库管理<br /><small class="muted">上传、启停、重建索引</small></button>
          <button class="outline-button" style="text-align: left" @click="navigate('students')">◎ 学生记录<br /><small class="muted">查看学生学习轨迹</small></button>
        </div>
      </section>
    </template>
  </div>
</template>
