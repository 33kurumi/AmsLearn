<script setup>
/**
 * 学习记录 S3 / S4
 * GET /student/records?type&kpId&from&to&page&size；GET /student/records/{id} 查看完整记录。
 */
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { common, student } from '../../api'
import { toast } from '../../toast'
import {
  KB_LABEL,
  RECORD_TYPE_ICON,
  RECORD_TYPE_LABEL,
  formatDateTime,
  formatFullDateTime,
  truncate,
} from '../../utils/format'
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
const items = ref([])
const page = ref(1)
const size = ref(10)
const total = ref(0)
const hasNext = ref(false)
const knowledgePoints = ref([])

const filters = reactive({
  type: '',
  kpId: '',
  from: '',
  to: '',
})

const TYPE_OPTIONS = [
  { value: '', label: '全部类型' },
  { value: 'QA', label: '答疑' },
  { value: 'DIAGNOSIS', label: '诊断' },
  { value: 'PRACTICE', label: '练习' },
  { value: 'PLAN', label: '计划' },
]

const drawer = ref(null)
const drawerLoading = ref(false)

const hasFilter = computed(() => filters.type || filters.kpId || filters.from || filters.to)

async function loadKnowledgePoints() {
  try {
    knowledgePoints.value = (await common.knowledgePoints()) || []
  } catch {
    knowledgePoints.value = []
  }
}

async function load(targetPage = 1) {
  loading.value = true
  error.value = ''
  try {
    const data = await student.records({
      type: filters.type || undefined,
      kpId: filters.kpId || undefined,
      from: filters.from || undefined,
      to: filters.to || undefined,
      page: targetPage,
      size: size.value,
    })
    const list = (data && data.items) || []
    items.value = list
    page.value = (data && data.page) || targetPage
    total.value = (data && data.total) || list.length
    hasNext.value = !!(data && data.hasNext)
  } catch (err) {
    error.value = err.message || '学习记录加载失败'
  } finally {
    loading.value = false
  }
}

async function openRecord(item) {
  if (!item || !item.id) return
  drawer.value = { ...item, loading: true }
  drawerLoading.value = true
  try {
    const detail = await student.recordDetail(item.id)
    drawer.value = detail || item
  } catch (err) {
    drawer.value = { ...item, error: err.message }
  } finally {
    drawerLoading.value = false
  }
}

function closeDrawer() {
  drawer.value = null
}

/** 答疑记录 → 跳转答疑页并载入该会话（v1.2 会话式答疑） */
function continueChat(item) {
  const conversationId = item && (item.conversationId || (drawer.value && drawer.value.conversationId))
  if (conversationId === undefined || conversationId === null || conversationId === '') {
    toast.info('该记录没有关联会话，无法继续对话。')
    return
  }
  drawer.value = null
  props.navigate('tutor', { conversationId })
}

function resetFilters() {
  filters.type = ''
  filters.kpId = ''
  filters.from = ''
  filters.to = ''
  load(1)
}

let searchTimer = null
watch(
  () => [filters.type, filters.kpId, filters.from, filters.to],
  () => {
    if (searchTimer) clearTimeout(searchTimer)
    searchTimer = setTimeout(() => load(1), 250)
  }
)

onMounted(() => {
  loadKnowledgePoints()
  load(1)
})
</script>

<template>
  <div>
    <div class="module-intro">
      <p class="eyebrow">学习记录 · RECORDS</p>
      <h1>每一步学习都有迹可循</h1>
      <p>按类型、知识点与时间筛选答疑、诊断、练习与计划记录，点击查看完整对话与解析。</p>
    </div>

    <section class="panel" style="margin-bottom: 16px">
      <div class="filter-bar">
        <div class="form-field">
          <label>记录类型</label>
          <select v-model="filters.type" class="select">
            <option v-for="option in TYPE_OPTIONS" :key="option.value" :value="option.value">{{ option.label }}</option>
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
          <label>开始日期</label>
          <input v-model="filters.from" class="input" type="date" />
        </div>
        <div class="form-field">
          <label>结束日期</label>
          <input v-model="filters.to" class="input" type="date" />
        </div>
        <div class="form-field" style="justify-content: flex-end">
          <button class="btn btn-ghost btn-sm" :disabled="!hasFilter" @click="resetFilters">清空筛选</button>
        </div>
      </div>
    </section>

    <section class="panel">
      <div class="panel-heading">
        <div><h3>记录列表</h3><p>共 {{ total }} 条记录，按时间倒序</p></div>
        <button class="text-button" :disabled="loading" @click="load(page)">{{ loading ? '刷新中…' : '刷新' }}</button>
      </div>

      <SkeletonBlock v-if="loading" :show-cards="false" :rows="6" />
      <ErrorState v-else-if="error" :message="error" :show-cards="false" @retry="load(page)" />
      <template v-else-if="items.length">
        <div class="record-list">
          <div
            v-for="item in items"
            :key="item.id"
            class="record-item"
            role="button"
            tabindex="0"
            @click="openRecord(item)"
            @keydown.enter="openRecord(item)"
            @keydown.space.prevent="openRecord(item)"
          >
            <span class="record-icon">{{ RECORD_TYPE_ICON[item.type] || '·' }}</span>
            <span class="record-main">
              <strong>{{ RECORD_TYPE_LABEL[item.type] || item.type }} · {{ truncate(item.userMessage || '（无提问内容）', 46) }}</strong>
              <span class="record-snippet">{{ item.blocked ? '超出教学范围，已被拦截' : truncate(item.aiResponse || '', 90) }}</span>
              <span class="record-meta">
                <span v-if="item.blocked" class="tag red">已拦截</span>
                <span v-for="name in (item.kpNames || []).slice(0, 3)" :key="name" class="tag green">{{ name }}</span>
                <span v-if="(item.sources || []).length" class="tag gray">来源 {{ item.sources.length }}</span>
                <button
                  v-if="item.type === 'QA' && item.conversationId !== null && item.conversationId !== undefined"
                  class="text-button record-continue"
                  type="button"
                  @click.stop="continueChat(item)"
                >
                  继续对话 →
                </button>
              </span>
            </span>
            <span class="record-time">{{ formatDateTime(item.createdAt) }}</span>
          </div>
        </div>
        <div class="pager">
          <span class="muted">第 {{ page }} 页 · 每页 {{ size }} 条 · 共 {{ total }} 条</span>
          <div class="pager-actions">
            <button class="btn btn-ghost btn-sm" :disabled="page <= 1 || loading" @click="load(page - 1)">上一页</button>
            <button class="btn btn-ghost btn-sm" :disabled="!hasNext || loading" @click="load(page + 1)">下一页</button>
          </div>
        </div>
      </template>
      <EmptyState
        v-else
        icon="◷"
        title="没有符合条件的记录"
        :description="hasFilter ? '当前筛选条件下没有记录，试试清空筛选。' : '先去答疑或做一次诊断，记录会出现在这里。'"
      />
    </section>

    <Transition name="drawer">
      <div v-if="drawer" class="mask" @click.self="closeDrawer">
        <div class="drawer" style="max-width: 640px">
          <div class="drawer-header">
            <div>
              <h3>{{ RECORD_TYPE_LABEL[drawer.type] || drawer.type }}详情</h3>
              <p>{{ formatFullDateTime(drawer.createdAt) }}</p>
            </div>
            <button class="drawer-close" @click="closeDrawer">✕</button>
          </div>
          <div class="drawer-body">
            <div v-if="drawerLoading" class="skeleton">
              <div class="skeleton-line w-60"></div>
              <div class="skeleton-line w-80"></div>
              <div class="skeleton-line w-40"></div>
            </div>
            <div v-else-if="drawer.error" class="alert alert-error">{{ drawer.error }}</div>
            <template v-else>
              <div class="detail-block">
                <h4>我的提问</h4>
                <p style="white-space: pre-wrap">{{ drawer.userMessage || '（无）' }}</p>
              </div>
              <div v-if="drawer.blocked" class="alert alert-warn">
                <strong>超出教学范围：</strong>{{ drawer.blockReason || '该内容超出当前教学范围，暂时无法解答。' }}
              </div>
              <div class="detail-block">
                <h4>AI 回答</h4>
                <MarkdownView :content="drawer.aiResponse || '（无回答内容）'" />
              </div>
              <div v-if="(drawer.kpNames || []).length" class="detail-block">
                <h4>相关知识点</h4>
                <div class="chip-group">
                  <span v-for="name in drawer.kpNames" :key="name" class="chip selected">{{ name }}</span>
                </div>
              </div>
              <div v-if="(drawer.sources || []).length" class="detail-block">
                <h4>知识库来源</h4>
                <div v-for="(source, index) in drawer.sources" :key="index" class="source-card">
                  <div class="source-title">
                    {{ source.title || '知识库文档' }}
                    <span>{{ KB_LABEL[source.kb] || source.kb || '知识库' }}</span>
                  </div>
                  <p>{{ source.excerpt || '' }}</p>
                </div>
              </div>
            </template>
          </div>
          <div class="drawer-footer">
            <button
              v-if="drawer.type === 'QA' && drawer.conversationId !== null && drawer.conversationId !== undefined"
              class="btn btn-primary btn-sm"
              @click="continueChat(drawer)"
            >
              继续对话
            </button>
            <button class="btn btn-outline btn-sm" @click="closeDrawer">关闭</button>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.record-list { display: grid; }
.record-item { width: 100%; text-align: left; border-left: 0; border-right: 0; border-bottom: 0; background: transparent; font: inherit; color: inherit; }
.record-main { display: grid; gap: 5px; min-width: 0; flex: 1; }
.record-meta { display: flex; gap: 6px; flex-wrap: wrap; }
</style>
