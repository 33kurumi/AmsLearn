<script setup>
/**
 * 知识库管理 T9 ~ T13
 * GET /teacher/knowledge；POST upload(multipart)；PATCH {enabled}；DELETE；POST rebuild
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { common, teacher } from '../../api'
import { toast } from '../../toast'
import { KB_LABEL, formatDateTime } from '../../utils/format'
import SkeletonBlock from '../../components/SkeletonBlock.vue'
import ErrorState from '../../components/ErrorState.vue'
import EmptyState from '../../components/EmptyState.vue'

defineProps({
  user: { type: Object, required: true },
  navigate: { type: Function, required: true },
})

const KB_OPTIONS = [
  { key: 'KB1', label: 'KB1 · 课程大纲' },
  { key: 'KB2', label: 'KB2 · 教材讲义' },
  { key: 'KB3', label: 'KB3 · 题库' },
  { key: 'KB4', label: 'KB4 · 教师资料' },
]

const loading = ref(true)
const error = ref('')
const documents = ref([])
const stats = reactive({ documentCount: 0, chunkCount: 0, byKb: {} })

const uploadKb = ref('KB4')
const selectedFile = ref(null)
const uploading = ref(false)
const uploadError = ref('')
const fileInput = ref(null)

const togglingId = ref(null)
const deletingId = ref(null)
const rebuilding = ref(false)
const rebuildResult = ref(null)

/**
 * 向量库状态（v1.1 契约）：AI 服务 /health 返回 vector_store、embedding、vector_dim、vector_count，
 * 业务服务透传；知识库 stats 若也带这些字段则作为补充来源。
 * 字段名同时兼容 snake_case（AI 原始）与 camelCase（Java 透传），旧后端缺失时不崩、只提示。
 */
const vector = reactive({
  store: '',
  embedding: '',
  dim: null,
  count: null,
  loaded: false,
  loading: false,
  error: '',
  source: '',
})

const VECTOR_ALIASES = {
  store: ['vectorstore', 'storename', 'vectorstorename'],
  embedding: ['embedding', 'embeddingmodel', 'embeddingname'],
  dim: ['vectordim', 'vectordimension', 'dimension'],
  count: ['vectorcount', 'vectorsize', 'vectorlength'],
}

function normalizeKey(key) {
  return String(key || '')
    .toLowerCase()
    .replace(/[^a-z0-9]/g, '')
}

/** 在任意层级对象中提取向量字段：短名（store/dim/count）只在向量上下文或 vector_* 前缀下采信，避免误读业务统计 */
function readVectorFields(payload) {
  const found = { store: null, embedding: null, dim: null, count: null }
  const walk = (node, depth, path) => {
    if (!node || typeof node !== 'object' || depth > 3) return
    for (const [key, value] of Object.entries(node)) {
      const norm = normalizeKey(key)
      const vectorContext = path.includes('vector') || norm.includes('vector')
      if (value !== null && (typeof value === 'string' || typeof value === 'number')) {
        for (const field of Object.keys(VECTOR_ALIASES)) {
          if (found[field] !== null || !VECTOR_ALIASES[field].includes(norm)) continue
          if (field !== 'embedding' && !vectorContext) continue
          if (typeof value === 'number' && !Number.isFinite(value)) continue
          if (typeof value === 'string' && !value.trim()) continue
          found[field] = typeof value === 'string' ? value.trim() : value
        }
      } else if (value && typeof value === 'object') {
        walk(value, depth + 1, path + '.' + norm)
      }
    }
  }
  walk(payload, 0, '')
  return found
}

function resetVectorState() {
  vector.store = ''
  vector.embedding = ''
  vector.dim = null
  vector.count = null
  vector.loaded = false
  vector.source = ''
}

function applyVectorFields(payload, label) {
  const info = readVectorFields(payload)
  let touched = false
  ;['store', 'embedding', 'dim', 'count'].forEach((field) => {
    if (info[field] !== null && info[field] !== undefined && (vector[field] === null || vector[field] === '')) {
      vector[field] = info[field]
      touched = true
    }
  })
  if (touched) {
    vector.loaded = true
    vector.source = label
  }
  return touched
}

async function loadVectorStatus() {
  try {
    const health = await common.health()
    applyVectorFields(health, 'AI 服务 /health')
  } catch (err) {
    vector.error = '向量库状态获取失败：' + (err.message || '未知错误')
    return
  }
  if (!vector.loaded) {
    vector.error =
      '未从 /health 读取到向量统计（vector_store / embedding / vector_dim / vector_count）。请确认 AI 服务与业务服务已升级到 v1.1 并重启，然后点击「刷新状态」。'
  } else {
    vector.error = ''
  }
}

async function refreshVector() {
  if (vector.loading) return
  vector.loading = true
  vector.error = ''
  await loadVectorStatus()
  vector.loading = false
}

const byKbRows = computed(() => {
  const map = stats.byKb || {}
  return Object.keys(map).map((key) => ({ key, label: KB_LABEL[key] || key, count: map[key] }))
})

const totalChunksFromDocs = computed(() =>
  documents.value.reduce((sum, doc) => sum + (Number(doc.chunks) || 0), 0)
)

async function load() {
  loading.value = true
  error.value = ''
  resetVectorState()
  vector.error = ''
  try {
    const data = await teacher.knowledge()
    documents.value = (data && data.documents) || []
    const s = (data && data.stats) || {}
    stats.documentCount = s.documentCount || documents.value.length
    stats.chunkCount = s.chunkCount || 0
    stats.byKb = s.byKb || {}
    // 知识库 stats 若已带向量字段先采用，再由 /health 补全缺失项
    applyVectorFields(s, '知识库统计')
    await loadVectorStatus()
  } catch (err) {
    error.value = err.message || '知识库加载失败'
  } finally {
    loading.value = false
  }
}

function pickFile() {
  if (fileInput.value) fileInput.value.click()
}

function onFileChange(event) {
  const file = event.target.files && event.target.files[0]
  uploadError.value = ''
  if (!file) return
  const name = (file.name || '').toLowerCase()
  if (!name.endsWith('.md') && !name.endsWith('.txt')) {
    uploadError.value = '仅支持 .md / .txt 文件。'
    selectedFile.value = null
    return
  }
  if (file.size > 2 * 1024 * 1024) {
    uploadError.value = '文件不能超过 2MB。'
    selectedFile.value = null
    return
  }
  selectedFile.value = file
}

async function upload() {
  if (uploading.value) return
  uploadError.value = ''
  if (!selectedFile.value) {
    uploadError.value = '请先选择 .md / .txt 文件。'
    return
  }
  uploading.value = true
  try {
    await teacher.uploadKnowledge(selectedFile.value, uploadKb.value)
    toast.success('资料已上传并加入索引')
    selectedFile.value = null
    if (fileInput.value) fileInput.value.value = ''
    await load()
  } catch (err) {
    uploadError.value = err.message || '上传失败'
  } finally {
    uploading.value = false
  }
}

async function toggle(doc) {
  if (togglingId.value !== null) return
  togglingId.value = doc.documentId
  try {
    const updated = await teacher.setKnowledgeEnabled(doc.documentId, !doc.enabled)
    doc.enabled = updated && typeof updated.enabled === 'boolean' ? updated.enabled : !doc.enabled
    toast.success(doc.enabled ? '已启用该资料' : '已停用该资料，检索将立即不再命中')
  } catch (err) {
    toast.error(err.message || '操作失败')
  } finally {
    togglingId.value = null
  }
}

async function remove(doc) {
  if (deletingId.value !== null) return
  if (!window.confirm('确认删除《' + doc.name + '》？删除后索引立即失效。')) return
  deletingId.value = doc.documentId
  try {
    await teacher.deleteKnowledge(doc.documentId)
    toast.success('资料已删除')
    await load()
  } catch (err) {
    if (err.status === 400) {
      toast.error(err.message || '内置资料不可删除，可改为停用。')
    } else {
      toast.error(err.message || '删除失败')
    }
  } finally {
    deletingId.value = null
  }
}

async function rebuild() {
  if (rebuilding.value) return
  rebuilding.value = true
  rebuildResult.value = null
  try {
    const result = await teacher.rebuildKnowledge()
    rebuildResult.value = result
    toast.success('索引重建完成')
    await load()
  } catch (err) {
    toast.error(err.message || '索引重建失败')
  } finally {
    rebuilding.value = false
  }
}

function formatSize(bytes) {
  const size = Number(bytes) || 0
  if (size < 1024) return size + ' B'
  if (size < 1024 * 1024) return (size / 1024).toFixed(1) + ' KB'
  return (size / 1024 / 1024).toFixed(2) + ' MB'
}

onMounted(load)
</script>

<template>
  <div>
    <div class="module-intro">
      <p class="eyebrow">知识库管理 · KNOWLEDGE BASE</p>
      <h1>知识库文档与索引</h1>
      <p>答疑、诊断与练习都基于知识库检索。上传本班资料、启停或重建索引后立即生效。</p>
    </div>

    <SkeletonBlock v-if="loading" :rows="5" :cards="3" />
    <ErrorState
      v-else-if="error"
      title="知识库加载失败"
      :message="error"
      hint="知识库由 AI 服务提供，请确认 8000 端口服务已启动。"
      @retry="load"
    />
    <template v-else>
      <div class="stats-grid cols-3" style="margin-bottom: 16px">
        <div class="stat-card">
          <div class="stat-top"><span class="stat-icon green">▤</span><span class="mini-badge">文档总数</span></div>
          <div class="stat-number">{{ stats.documentCount || documents.length }}<small>份</small></div>
          <div class="stat-foot">内置 5 份 + 本班上传</div>
        </div>
        <div class="stat-card">
          <div class="stat-top"><span class="stat-icon purple">▥</span><span class="mini-badge">知识切块</span></div>
          <div class="stat-number">{{ stats.chunkCount || totalChunksFromDocs }}<small>块</small></div>
          <div class="stat-foot">切块用于向量检索</div>
        </div>
        <div class="stat-card">
          <div class="stat-top"><span class="stat-icon orange">⚙</span><span class="mini-badge">索引状态</span></div>
          <div class="stat-number" style="font-size: 20px">
            {{ rebuildResult ? '已重建' : '可用' }}
          </div>
          <div class="stat-foot">
            {{ rebuildResult ? rebuildResult.documentCount + ' 份 / ' + rebuildResult.chunkCount + ' 块 / ' + rebuildResult.durationMs + 'ms' : '最近一次索引正常' }}
          </div>
        </div>
      </div>

      <section class="panel vector-panel" style="margin-bottom: 16px">
        <div class="panel-heading">
          <div>
            <h3>向量检索（LangChain）</h3>
            <p>LangChain InMemoryVectorStore + 本地字符 n-gram Embedding，离线可复现；随索引重建自动更新</p>
          </div>
          <button class="text-button" :disabled="vector.loading" @click="refreshVector">
            {{ vector.loading ? '刷新中…' : '刷新状态' }}
          </button>
        </div>
        <div class="stats-grid cols-4 vector-grid">
          <div class="stat-card">
            <div class="stat-top"><span class="stat-icon green">◈</span><span class="mini-badge">向量库 Store</span></div>
            <div class="stat-number small vector-value">{{ vector.store || '—' }}</div>
            <div class="stat-foot">{{ vector.store ? 'LangChain VectorStore' : '等待 /health 返回 vector_store' }}</div>
          </div>
          <div class="stat-card">
            <div class="stat-top"><span class="stat-icon purple">⌘</span><span class="mini-badge">Embedding</span></div>
            <div class="stat-number small vector-value">{{ vector.embedding || '—' }}</div>
            <div class="stat-foot">{{ vector.embedding ? '本地离线向量化' : '等待 /health 返回 embedding' }}</div>
          </div>
          <div class="stat-card">
            <div class="stat-top"><span class="stat-icon orange">▦</span><span class="mini-badge">向量维度</span></div>
            <div class="stat-number small vector-value">
              {{ vector.dim === null || vector.dim === '' ? '—' : vector.dim }}<small v-if="vector.dim !== null && vector.dim !== ''">维</small>
            </div>
            <div class="stat-foot">vector_dim</div>
          </div>
          <div class="stat-card">
            <div class="stat-top"><span class="stat-icon green">▤</span><span class="mini-badge">向量数量</span></div>
            <div class="stat-number small vector-value">
              {{ vector.count === null || vector.count === '' ? '—' : vector.count }}<small v-if="vector.count !== null && vector.count !== ''">条</small>
            </div>
            <div class="stat-foot">vector_count · 与索引块数一致</div>
          </div>
        </div>
        <div v-if="vector.error" class="alert alert-warn" style="margin-top: 12px; font-size: 12px">
          {{ vector.error }}
        </div>
        <div v-else class="alert alert-info" style="margin-top: 12px; font-size: 12px">
          数据来源：{{ vector.source || 'AI 服务 /health' }}（Java 业务服务透传）。重建索引后卡片自动刷新；向量库状态可作为「LangChain 文档导入 + 向量统计」的截图证据。
        </div>
      </section>

      <section class="panel" style="margin-bottom: 16px">
        <div class="panel-heading">
          <div><h3>上传本班资料</h3><p>支持 .md / .txt，单文件不超过 2MB</p></div>
          <button class="btn btn-outline btn-sm" :disabled="rebuilding" @click="rebuild">
            <span v-if="rebuilding" class="spinner"></span>
            {{ rebuilding ? '重建中…' : '重建索引' }}
          </button>
        </div>
        <div class="upload-box">
          <div class="upload-row">
            <label class="btn btn-outline btn-sm" style="cursor: pointer">
              选择文件
              <input ref="fileInput" type="file" accept=".md,.txt,text/markdown,text/plain" style="display: none" @change="onFileChange" />
            </label>
            <span class="doc-name">{{ selectedFile ? selectedFile.name : '未选择文件' }}</span>
            <span v-if="selectedFile" class="muted" style="font-size: 12px">{{ formatSize(selectedFile.size) }}</span>
            <div class="form-field" style="margin-left: auto; min-width: 170px">
              <select v-model="uploadKb" class="select" :disabled="uploading">
                <option v-for="item in KB_OPTIONS" :key="item.key" :value="item.key">{{ item.label }}</option>
              </select>
            </div>
            <button class="btn btn-primary btn-sm" :disabled="uploading || !selectedFile" @click="upload">
              <span v-if="uploading" class="spinner light"></span>
              {{ uploading ? '上传中…' : '上传并索引' }}
            </button>
          </div>
          <div v-if="uploadError" class="form-error" style="margin-top: 10px">{{ uploadError }}</div>
          <div class="alert alert-info" style="margin-top: 12px; font-size: 12px">
            教师上传的资料作用域为「本班」，仅影响当前班级的检索；停用后立即不再命中，删除不可恢复。
          </div>
        </div>
      </section>

      <section class="panel" style="margin-bottom: 16px">
        <div class="panel-heading"><div><h3>知识库分布</h3><p>按知识库类别统计文档切块数</p></div></div>
        <div v-if="byKbRows.length" class="grid-4">
          <div v-for="row in byKbRows" :key="row.key" class="stat-card" style="padding: 14px">
            <div class="mini-badge">{{ row.label }}</div>
            <div class="stat-number small">{{ row.count || 0 }}</div>
            <div class="progress-track" style="margin-top: 8px">
              <div
                class="progress-fill"
                :style="{ width: Math.min(100, ((Number(row.count) || 0) / Math.max(1, Number(stats.chunkCount) || totalChunksFromDocs || 1)) * 100) + '%' }"
              ></div>
            </div>
          </div>
        </div>
        <EmptyState v-else icon="▤" title="暂无知识库统计" description="知识库文档加载后显示分布。" />
      </section>

      <section class="panel">
        <div class="panel-heading">
          <div><h3>文档列表</h3><p>共 {{ documents.length }} 份文档</p></div>
          <button class="text-button" :disabled="loading" @click="load">刷新</button>
        </div>
        <div v-if="documents.length" class="table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th>文档名称</th>
                <th>知识库</th>
                <th>作用域</th>
                <th>切块</th>
                <th>大小</th>
                <th>状态</th>
                <th>上传时间</th>
                <th style="width: 150px">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="doc in documents" :key="doc.documentId">
                <td>
                  <div class="text-strong" style="font-size: 12px">{{ doc.name }}</div>
                  <div class="muted" style="font-size: 10px">{{ doc.documentId }}</div>
                </td>
                <td><span class="tag purple">{{ KB_LABEL[doc.kb] || doc.kb }}</span></td>
                <td>
                  <span class="tag gray">{{ doc.scope === 'CLASS' ? '本班（' + (doc.classId || '—') + '）' : '全局' }}</span>
                </td>
                <td class="muted">{{ doc.chunks || 0 }}</td>
                <td class="muted">{{ formatSize(doc.size) }}</td>
                <td>
                  <span class="tag" :class="doc.enabled ? 'green' : 'gray'">{{ doc.enabled ? '已启用' : '已停用' }}</span>
                </td>
                <td class="muted" style="font-size: 11px">{{ doc.uploadedAt ? formatDateTime(doc.uploadedAt) : '内置' }}</td>
                <td>
                  <div style="display: flex; gap: 6px">
                    <button class="btn btn-ghost btn-sm" :disabled="togglingId === doc.documentId" @click="toggle(doc)">
                      {{ togglingId === doc.documentId ? '…' : doc.enabled ? '停用' : '启用' }}
                    </button>
                    <button class="btn btn-ghost btn-sm text-button danger" style="padding: 4px 6px" :disabled="deletingId === doc.documentId" @click="remove(doc)">
                      {{ deletingId === doc.documentId ? '…' : '删除' }}
                    </button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <EmptyState v-else icon="▤" title="知识库为空" description="上传 .md / .txt 资料后即可用于答疑与出题。" />
      </section>
    </template>
  </div>
</template>
