<script setup>
/**
 * 班级配置 T2 ~ T5
 * GET/PUT /teacher/config；GET /teacher/config/logs；POST /teacher/config/extract
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { common, teacher } from '../../api'
import { toast } from '../../toast'
import { ANSWER_MODE_LABEL, KB_LABEL, formatDateTime } from '../../utils/format'
import SkeletonBlock from '../../components/SkeletonBlock.vue'
import ErrorState from '../../components/ErrorState.vue'
import EmptyState from '../../components/EmptyState.vue'

defineProps({
  user: { type: Object, required: true },
  navigate: { type: Function, required: true },
})

const ANSWER_MODES = [
  { key: 'GUIDED', label: '引导式', desc: '先给提示与思路，引导学生自己完成关键步骤。' },
  { key: 'DIRECT', label: '直接讲解', desc: '直接给出完整讲解与答案，适合复习与自学。' },
  { key: 'MIXED', label: '混合', desc: '概念题讲解、作业题引导，按场景自动切换。' },
]

const SCOPE_MODES = [
  { key: 'ALL', label: '全部知识点', desc: '覆盖知识库内全部章节内容。' },
  { key: 'CHAPTER', label: '指定章节', desc: '只讲解选定章节，其余内容视为超范围。' },
  { key: 'CUSTOM', label: '指定知识点', desc: '精确到知识点，适合专题强化。' },
]

const KB_KEYS = ['kb1', 'kb2', 'kb3', 'kb4']

const loading = ref(true)
const error = ref('')
const saving = ref(false)
const formError = ref('')
const lastChanges = ref([])
const effectNote = ref('')
const updatedInfo = ref({ updatedAt: null, updatedByName: '' })

const draft = reactive({
  answerMode: 'MIXED',
  maxDifficulty: 3,
  scopeMode: 'ALL',
  chaptersText: '',
  kpIds: [],
  boundaryRules: '',
  kbAccess: { kb1: true, kb2: true, kb3: true, kb4: true },
  disabledTopics: [],
})
const savedSignature = ref('')

const newTopic = ref('')
const knowledgePoints = ref([])

const logs = ref([])
const logsLoading = ref(false)
const logsError = ref('')
const logsPage = ref(1)
const logsTotal = ref(0)
const logsHasNext = ref(false)

const quickText = ref('')
const extracting = ref(false)
const extractError = ref('')
const extractResult = ref(null)
const applying = ref(false)

const dirty = computed(() => buildSignature(draft) !== savedSignature.value)
const chapters = computed(() =>
  draft.chaptersText
    .split(/[,，、\s]+/)
    .map((item) => item.trim())
    .filter(Boolean)
)

function buildSignature(source) {
  return JSON.stringify({
    answerMode: source.answerMode,
    maxDifficulty: Number(source.maxDifficulty) || 0,
    scopeMode: source.scopeMode,
    chaptersText: source.chaptersText,
    kpIds: source.kpIds,
    boundaryRules: source.boundaryRules,
    kbAccess: source.kbAccess,
    disabledTopics: source.disabledTopics,
  })
}

function applyConfig(configData) {
  if (!configData) return
  draft.answerMode = configData.answerMode || 'MIXED'
  draft.maxDifficulty = Number(configData.maxDifficulty) || 3
  const scope = configData.knowledgeScope || {}
  draft.scopeMode = scope.mode || 'ALL'
  draft.chaptersText = Array.isArray(scope.chapters) ? scope.chapters.join('、') : ''
  draft.kpIds = Array.isArray(scope.kpIds) ? scope.kpIds.slice() : []
  draft.boundaryRules = configData.boundaryRules || ''
  const access = configData.kbAccess || {}
  KB_KEYS.forEach((key) => {
    draft.kbAccess[key] = access[key] !== false
  })
  draft.disabledTopics = Array.isArray(configData.disabledTopics) ? configData.disabledTopics.slice() : []
  updatedInfo.value = { updatedAt: configData.updatedAt || null, updatedByName: configData.updatedByName || '' }
  savedSignature.value = buildSignature(draft)
}

async function loadConfig() {
  loading.value = true
  error.value = ''
  try {
    const data = await teacher.config()
    applyConfig(data)
  } catch (err) {
    error.value = err.message || '班级配置加载失败'
  } finally {
    loading.value = false
  }
}

async function loadLogs(targetPage = 1) {
  logsLoading.value = true
  logsError.value = ''
  try {
    const data = await teacher.configLogs({ page: targetPage, size: 5 })
    logs.value = (data && data.items) || []
    logsPage.value = (data && data.page) || targetPage
    logsTotal.value = (data && data.total) || logs.value.length
    logsHasNext.value = !!(data && data.hasNext)
  } catch (err) {
    logsError.value = err.message || '变更记录加载失败'
  } finally {
    logsLoading.value = false
  }
}

async function loadKnowledgePoints() {
  try {
    knowledgePoints.value = (await common.knowledgePoints()) || []
  } catch {
    knowledgePoints.value = []
  }
}

function validate() {
  if (!['GUIDED', 'DIRECT', 'MIXED'].includes(draft.answerMode)) return '回答模式取值非法。'
  const difficulty = Number(draft.maxDifficulty)
  if (!difficulty || difficulty < 1 || difficulty > 4) return '最大难度必须在 1~4 之间。'
  if (draft.scopeMode === 'CHAPTER' && !chapters.value.length) return '指定章节模式至少填写一个章节。'
  if (draft.scopeMode === 'CUSTOM' && !draft.kpIds.length) return '指定知识点模式至少选择一个知识点。'
  if ((draft.boundaryRules || '').length > 500) return '边界规则不能超过 500 字。'
  return ''
}

function buildPayload(source) {
  const scope = source || draft
  return {
    answerMode: scope.answerMode,
    maxDifficulty: Number(scope.maxDifficulty),
    knowledgeScope: {
      mode: scope.scopeMode,
      chapters: scope.scopeMode === 'CHAPTER' ? chapters.value : [],
      kpIds: scope.scopeMode === 'CUSTOM' ? scope.kpIds.slice() : [],
    },
    boundaryRules: scope.boundaryRules || '',
    kbAccess: {
      kb1: !!scope.kbAccess.kb1,
      kb2: !!scope.kbAccess.kb2,
      kb3: !!scope.kbAccess.kb3,
      kb4: !!scope.kbAccess.kb4,
    },
    disabledTopics: scope.disabledTopics.slice(),
  }
}

async function save() {
  if (saving.value) return
  formError.value = validate()
  if (formError.value) return
  saving.value = true
  try {
    const result = await teacher.saveConfig(buildPayload())
    lastChanges.value = (result && result.changes) || []
    effectNote.value = (result && result.effectNote) || '配置已保存，对后续所有请求立即生效。'
    if (result && result.config) applyConfig(result.config)
    else savedSignature.value = buildSignature(draft)
    toast.success('配置已保存，立即生效')
    await Promise.all([loadConfig(), loadLogs(1)])
  } catch (err) {
    formError.value = err.message || '保存失败'
  } finally {
    saving.value = false
  }
}

function reset() {
  loadConfig()
  formError.value = ''
  lastChanges.value = []
}

function addTopic() {
  const value = (newTopic.value || '').trim()
  if (!value) return
  if (draft.disabledTopics.includes(value)) {
    newTopic.value = ''
    return
  }
  draft.disabledTopics.push(value)
  newTopic.value = ''
}

function removeTopic(topic) {
  draft.disabledTopics = draft.disabledTopics.filter((item) => item !== topic)
}

function toggleKp(kpId) {
  if (draft.kpIds.includes(kpId)) draft.kpIds = draft.kpIds.filter((item) => item !== kpId)
  else draft.kpIds.push(kpId)
}

function toggleKb(key) {
  draft.kbAccess[key] = !draft.kbAccess[key]
}

async function extract() {
  if (extracting.value) return
  extractError.value = ''
  extractResult.value = null
  const text = (quickText.value || '').trim()
  if (!text) {
    extractError.value = '请先描述你的配置需求。'
    return
  }
  extracting.value = true
  try {
    extractResult.value = await teacher.extractConfig(text)
  } catch (err) {
    extractError.value = err.message || '解析失败'
  } finally {
    extracting.value = false
  }
}

const FIELD_LABEL = {
  answerMode: '回答模式',
  maxDifficulty: '最大难度',
  knowledgeScope: '知识范围',
  boundaryRules: '边界规则',
  kbAccess: '知识库访问',
  disabledTopics: '禁用话题',
}

function displayValue(field, value) {
  if (value === null || value === undefined) return '—'
  if (field === 'answerMode') return ANSWER_MODE_LABEL[value] || value
  if (field === 'kbAccess' && typeof value === 'object') {
    return KB_KEYS.map((key) => (KB_LABEL['KB' + key.slice(2)] || key) + (value[key] ? '开' : '关')).join(' / ')
  }
  if (field === 'knowledgeScope' && typeof value === 'object') {
    const mode = value.mode || ''
    const label = mode === 'ALL' ? '全部知识点' : mode === 'CHAPTER' ? '章节：' + (value.chapters || []).join('、') : '知识点：' + (value.kpIds || []).join('、')
    return label
  }
  if (Array.isArray(value)) return value.length ? value.join('、') : '（清空）'
  return String(value)
}

const extractDiff = computed(() => {
  if (!extractResult.value || !extractResult.value.patch) return []
  const patch = extractResult.value.patch
  const rows = []
  Object.keys(patch).forEach((field) => {
    const after = patch[field]
    let before
    if (field === 'kbAccess') before = draft.kbAccess
    else if (field === 'knowledgeScope') before = { mode: draft.scopeMode, chapters: chapters.value, kpIds: draft.kpIds }
    else if (field === 'disabledTopics') before = draft.disabledTopics
    else before = draft[field]
    rows.push({
      field,
      label: FIELD_LABEL[field] || field,
      before: displayValue(field, before),
      after: displayValue(field, after),
    })
  })
  return rows
})

function applyPatchToDraft(patch) {
  Object.keys(patch).forEach((field) => {
    const value = patch[field]
    if (field === 'answerMode' && value) draft.answerMode = value
    else if (field === 'maxDifficulty' && value) draft.maxDifficulty = Number(value)
    else if (field === 'knowledgeScope' && value) {
      draft.scopeMode = value.mode || draft.scopeMode
      draft.chaptersText = Array.isArray(value.chapters) ? value.chapters.join('、') : draft.chaptersText
      draft.kpIds = Array.isArray(value.kpIds) ? value.kpIds.slice() : draft.kpIds
    } else if (field === 'boundaryRules' && typeof value === 'string') draft.boundaryRules = value
    else if (field === 'kbAccess' && value) {
      KB_KEYS.forEach((key) => {
        if (typeof value[key] === 'boolean') draft.kbAccess[key] = value[key]
      })
    } else if (field === 'disabledTopics' && Array.isArray(value)) draft.disabledTopics = value.slice()
  })
}

async function confirmExtract() {
  if (!extractResult.value || applying.value) return
  formError.value = validate()
  if (formError.value) {
    extractError.value = '合并后的配置校验失败：' + formError.value
    return
  }
  applying.value = true
  extractError.value = ''
  try {
    applyPatchToDraft(extractResult.value.patch || {})
    formError.value = validate()
    if (formError.value) {
      extractError.value = '合并后的配置校验失败：' + formError.value
      return
    }
    extractResult.value = null
    quickText.value = ''
    await save()
    toast.success('已按自然语言配置完成修改')
  } finally {
    applying.value = false
  }
}

onMounted(() => {
  loadConfig()
  loadLogs(1)
  loadKnowledgePoints()
})
</script>

<template>
  <div>
    <div class="module-intro">
      <p class="eyebrow">班级配置 · CLASS CONFIG</p>
      <h1>教学边界与回答策略</h1>
      <p>配置回答模式、最大难度、知识范围与知识库访问权限，保存后对后续所有请求立即生效。</p>
    </div>

    <SkeletonBlock v-if="loading" :rows="8" :cards="3" />
    <ErrorState
      v-else-if="error"
      title="班级配置加载失败"
      :message="error"
      hint="配置读取自业务服务，请确认 8080 端口已启动并使用教师账号登录。"
      @retry="loadConfig"
    />
    <template v-else>
      <div v-if="updatedInfo.updatedAt" class="muted" style="margin-bottom: 12px; font-size: 12px">
        最近修改：{{ updatedInfo.updatedByName || '—' }} · {{ formatDateTime(updatedInfo.updatedAt) }}
        <span v-if="dirty" class="tag orange" style="margin-left: 8px">有未保存的修改</span>
      </div>

      <div class="config-layout">
        <div>
          <section class="panel config-section" style="margin-bottom: 16px">
            <div class="panel-heading"><div><h3>回答模式</h3><p>决定 AI 答疑的讲解风格</p></div></div>
            <div class="radio-cards">
              <button
                v-for="mode in ANSWER_MODES"
                :key="mode.key"
                type="button"
                class="radio-card"
                :class="{ selected: draft.answerMode === mode.key }"
                @click="draft.answerMode = mode.key"
              >
                <strong>{{ mode.label }}</strong>
                <span>{{ mode.desc }}</span>
              </button>
            </div>
          </section>

          <section class="panel config-section" style="margin-bottom: 16px">
            <div class="panel-heading"><div><h3>题目难度上限</h3><p>诊断与练习生成的题目不超过该难度</p></div></div>
            <div class="form-grid">
              <div class="form-field">
                <label>最大难度 / 4</label>
                <select v-model.number="draft.maxDifficulty" class="select">
                  <option :value="1">1 · 基础概念</option>
                  <option :value="2">2 · 常规题</option>
                  <option :value="3">3 · 综合题</option>
                  <option :value="4">4 · 压轴/考研真题</option>
                </select>
              </div>
              <div class="form-field">
                <label>当前难度等级</label>
                <span class="level-pill" style="align-self: flex-start">难度 {{ draft.maxDifficulty }} · {{ ['基础', '常规', '综合', '压轴'][Number(draft.maxDifficulty) - 1] || '综合' }}</span>
              </div>
            </div>
          </section>

          <section class="panel config-section" style="margin-bottom: 16px">
            <div class="panel-heading"><div><h3>知识范围</h3><p>超出范围的内容将被拦截并给出统一话术</p></div></div>
            <div class="radio-cards">
              <button
                v-for="mode in SCOPE_MODES"
                :key="mode.key"
                type="button"
                class="radio-card"
                :class="{ selected: draft.scopeMode === mode.key }"
                @click="draft.scopeMode = mode.key"
              >
                <strong>{{ mode.label }}</strong>
                <span>{{ mode.desc }}</span>
              </button>
            </div>
            <div v-if="draft.scopeMode === 'CHAPTER'" class="form-field" style="margin-top: 14px">
              <label>章节列表 <span class="required">*</span></label>
              <input v-model="draft.chaptersText" class="input" placeholder="用顿号或逗号分隔，例如：函数与极限、导数与微分" />
              <span class="form-hint">当前：{{ chapters.length ? chapters.join('、') : '未填写' }}</span>
            </div>
            <div v-if="draft.scopeMode === 'CUSTOM'" style="margin-top: 14px">
              <label class="form-hint">选择知识点（已选 {{ draft.kpIds.length }} 个）</label>
              <div v-if="knowledgePoints.length" class="chip-group" style="max-height: 220px; overflow: auto">
                <button
                  v-for="kp in knowledgePoints"
                  :key="kp.kpId"
                  type="button"
                  class="chip"
                  :class="{ selected: draft.kpIds.includes(kp.kpId) }"
                  @click="toggleKp(kp.kpId)"
                >
                  {{ kp.kpName }}
                </button>
              </div>
              <div v-else class="muted" style="font-size: 12px">知识点列表暂不可用，请稍后重试。</div>
            </div>
          </section>

          <section class="panel config-section" style="margin-bottom: 16px">
            <div class="panel-heading"><div><h3>边界规则</h3><p>用于约束 AI 的表达方式，最多 500 字</p></div></div>
            <div class="form-field">
              <textarea
                v-model="draft.boundaryRules"
                class="textarea"
                rows="4"
                maxlength="500"
                placeholder="例如：作业与考试题只给思路不给最终答案；不讨论超纲内容；回答使用中文。"
              ></textarea>
              <span class="form-hint" :class="{ 'form-error': (draft.boundaryRules || '').length > 500 }">
                {{ (draft.boundaryRules || '').length }} / 500
              </span>
            </div>
          </section>

          <section class="panel config-section" style="margin-bottom: 16px">
            <div class="panel-heading"><div><h3>知识库访问</h3><p>关闭后该类知识库不参与检索</p></div></div>
            <div class="upload-row" style="flex-wrap: wrap; gap: 10px">
              <label v-for="key in KB_KEYS" :key="key" class="check-row" style="min-width: 180px">
                <span class="switch">
                  <input type="checkbox" :checked="draft.kbAccess[key]" @change="toggleKb(key)" />
                  <span class="slider"></span>
                </span>
                <span>{{ KB_LABEL['KB' + key.slice(2)] || key }}</span>
              </label>
            </div>
          </section>

          <section class="panel config-section" style="margin-bottom: 16px">
            <div class="panel-heading"><div><h3>禁用话题</h3><p>命中禁用话题的提问将直接返回拦截话术</p></div></div>
            <div class="flex-row" style="gap: 8px; margin-bottom: 10px">
              <input v-model="newTopic" class="input" style="max-width: 240px" placeholder="输入话题后回车，例如：级数" @keydown.enter.prevent="addTopic" />
              <button class="btn btn-outline btn-sm" @click="addTopic">添加话题</button>
            </div>
            <div v-if="draft.disabledTopics.length" class="chip-group">
              <button v-for="topic in draft.disabledTopics" :key="topic" type="button" class="chip selected" @click="removeTopic(topic)">
                {{ topic }} ✕
              </button>
            </div>
            <div v-else class="muted" style="font-size: 12px">暂无禁用话题</div>
          </section>

          <div v-if="formError" class="alert alert-error" style="margin-bottom: 12px">{{ formError }}</div>
          <div v-if="lastChanges.length" class="panel" style="margin-bottom: 12px">
            <div class="panel-heading"><div><h3>本次修改</h3><p>{{ effectNote }}</p></div></div>
            <div class="diff-list">
              <div v-for="change in lastChanges" :key="change.field" class="diff-row">
                <span class="diff-field">{{ change.label || change.field }}</span>
                <span class="diff-value">
                  <span class="before">{{ displayValue(change.field, change.before) }}</span>
                  <span class="muted">→</span>
                  <span class="after">{{ displayValue(change.field, change.after) }}</span>
                </span>
              </div>
            </div>
          </div>

          <div class="config-actions">
            <button class="btn btn-primary" :disabled="saving || !dirty" @click="save">
              <span v-if="saving" class="spinner light"></span>
              {{ saving ? '保存中…' : '保存配置' }}
            </button>
            <button class="btn btn-outline" :disabled="saving || !dirty" @click="reset">撤销修改</button>
          </div>
        </div>

        <div>
          <section class="panel" style="margin-bottom: 16px">
            <div class="panel-heading"><div><h3>自然语言快速配置</h3><p>描述需求，AI 解析为配置项，确认后保存</p></div></div>
            <div class="form-field">
              <textarea
                v-model="quickText"
                class="textarea"
                rows="3"
                placeholder="例如：把最大难度调到 2，暂时关闭教师资料，级数先别讲"
                :disabled="extracting"
              ></textarea>
            </div>
            <div class="flex-row" style="gap: 8px; margin-top: 10px">
              <button class="btn btn-primary btn-sm" :disabled="extracting || !quickText.trim()" @click="extract">
                <span v-if="extracting" class="spinner light"></span>
                {{ extracting ? '解析中…' : '解析配置' }}
              </button>
              <button class="btn btn-ghost btn-sm" :disabled="extracting" @click="quickText = ''; extractResult = null; extractError = ''">清空</button>
            </div>
            <div v-if="extractError" class="form-error" style="margin-top: 10px">{{ extractError }}</div>

            <div v-if="extractResult" style="margin-top: 14px">
              <div class="alert alert-info" style="font-size: 12px; margin-bottom: 10px">
                {{ extractResult.explanation || '已识别以下配置修改，请确认后保存。' }}
                <span v-if="extractResult.mode" class="tag gray" style="margin-left: 6px">{{ extractResult.mode }}</span>
              </div>
              <div v-if="extractDiff.length" class="diff-list">
                <div v-for="row in extractDiff" :key="row.field" class="diff-row">
                  <span class="diff-field">{{ row.label }}</span>
                  <span class="diff-value">
                    <span class="before">{{ row.before }}</span>
                    <span class="muted">→</span>
                    <span class="after">{{ row.after }}</span>
                  </span>
                </div>
              </div>
              <div v-else class="muted" style="font-size: 12px">未识别到可修改的配置项。</div>
              <div v-if="(extractResult.unrecognized || []).length" class="alert alert-warn" style="margin-top: 10px; font-size: 12px">
                未识别：{{ extractResult.unrecognized.join('、') }}
              </div>
              <div class="flex-row" style="gap: 8px; margin-top: 12px">
                <button class="btn btn-primary btn-sm" :disabled="applying || !extractDiff.length" @click="confirmExtract">
                  {{ applying ? '应用中…' : '确认并保存' }}
                </button>
                <button class="btn btn-ghost btn-sm" :disabled="applying" @click="extractResult = null">取消</button>
              </div>
            </div>
          </section>

          <section class="panel">
            <div class="panel-heading">
              <div><h3>变更记录</h3><p>共 {{ logsTotal }} 条</p></div>
              <button class="text-button" :disabled="logsLoading" @click="loadLogs(logsPage)">刷新</button>
            </div>
            <SkeletonBlock v-if="logsLoading" :show-cards="false" :rows="3" />
            <ErrorState v-else-if="logsError" :message="logsError" :show-cards="false" @retry="loadLogs(logsPage)" />
            <template v-else-if="logs.length">
              <div v-for="log in logs" :key="log.id" class="log-item">
                <div class="log-head">
                  <strong style="font-size: 12px">{{ log.summary || '配置变更' }}</strong>
                  <span class="record-time">{{ formatDateTime(log.changedAt) }}</span>
                </div>
                <div class="muted" style="font-size: 11px; margin-top: 2px">操作人：{{ log.changedByName || '—' }}</div>
                <div v-if="(log.changes || []).length" class="log-changes">
                  <div v-for="(change, index) in log.changes" :key="index" class="log-change">
                    {{ change.label || change.field }}：{{ displayValue(change.field, change.before) }} → {{ displayValue(change.field, change.after) }}
                  </div>
                </div>
              </div>
              <div class="pager">
                <span class="muted">第 {{ logsPage }} 页</span>
                <div class="pager-actions">
                  <button class="btn btn-ghost btn-sm" :disabled="logsPage <= 1 || logsLoading" @click="loadLogs(logsPage - 1)">上一页</button>
                  <button class="btn btn-ghost btn-sm" :disabled="!logsHasNext || logsLoading" @click="loadLogs(logsPage + 1)">下一页</button>
                </div>
              </div>
            </template>
            <EmptyState v-else icon="▤" title="暂无变更记录" description="修改配置后这里会记录变更内容与操作人。" />
          </section>
        </div>
      </div>
    </template>
  </div>
</template>
