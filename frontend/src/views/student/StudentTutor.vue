<script setup>
/**
 * 答疑辅导 S9（v1.3 会话式 + 图片答疑 + 前置自测）
 * - GET /conversations 会话列表、GET /conversations/{id} 载入历史
 * - POST /chat 携带 conversationId，回答带 mode/modelSource 小标签与 gate 前置自测卡片
 * - 图片：原生 canvas 压缩后 POST /student/chat/vision 识别文字，只回填文字、不发原图、不落库
 * - 前置自测：气泡内 GateCard 提交 /student/gate/check，历史会话只读摘要
 * - 来源按 chunkId 去重后展示，标题写「知识库来源（N 段）」并注明已去重
 * - 接口未就绪（404）时降级为单轮问答/手动输入，不白屏
 */
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { student } from '../../api'
import { toast } from '../../toast'
import { KB_LABEL, formatDateTime } from '../../utils/format'
import { answerModeTags } from '../../utils/aiMode'
import { isGateAction, normalizeGate } from '../../utils/gate'
import {
  ACCEPT_ATTR,
  MAX_IMAGE_BYTES,
  compressImageFile,
  formatFileSize,
  validateImageFile,
} from '../../utils/vision'
import MarkdownView from '../../components/MarkdownView.vue'
import GateCard from '../../components/GateCard.vue'

const props = defineProps({
  user: { type: Object, required: true },
  navigate: { type: Function, required: true },
  initialConversationId: { type: [String, Number], default: null },
})

const messages = reactive([])
const draft = ref('')
const sending = ref(false)
const chatBody = ref(null)
const greeting = computed(() => ({ displayName: '知学 AI' }))

/* v1.3 图片答疑：压缩 → 识别 → 回填文字（图片本身不发送、不保存） */
const visionInput = ref(null)
const vision = reactive({
  status: 'idle',
  previewUrl: '',
  fileName: '',
  sizeText: '',
  message: '',
  model: '',
  error: false,
})
let compressedFile = null
const visionBusy = computed(() => vision.status === 'compressing' || vision.status === 'uploading')

const conversations = ref([])
const convLoading = ref(false)
const convError = ref('')
const activeId = ref(null)
const activeTitle = ref('新对话')
const historyLoading = ref(false)
const historyError = ref('')
const renamingId = ref(null)
const deletingId = ref(null)
let createFallbackHinted = false
let seq = 0
function nextId(prefix) {
  seq += 1
  return prefix + '-' + Date.now() + '-' + seq
}

const ACTION_LABEL = { DIAGNOSE: '去做一次诊断', PLAN: '生成学习计划', PRACTICE: '去分层练习' }
const ACTION_PAGE = { DIAGNOSE: 'diagnose', PLAN: 'plan', PRACTICE: 'practice' }

const SUGGESTIONS = [
  '洛必达法则的使用条件是什么？',
  '帮我讲讲定积分的换元法，并给一个例子。',
  '拉格朗日中值定理如何构造辅助函数？',
  '求极限时等价无穷小替换有哪些常见错误？',
]

const WELCOME = computed(
  () =>
    `你好，${props.user.displayName || '同学'}！我是你的高数学习助教。\n\n- 可以直接提问概念、定理与解题方法，我会结合课程知识库回答；\n- 同一会话内可以连续追问，我会参考上文；\n- 回答末尾会给出 **知识库来源**，方便你回看；\n- 如果问题超出当前教学范围，我会明确提示。\n\n试着从下面的问题开始，或者直接输入你的疑问。`
)

function scrollToBottom() {
  nextTick(() => {
    const el = chatBody.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

function mapHistoryMessage(item) {
  const role = item && item.role === 'user' ? 'user' : 'assistant'
  return {
    id: nextId(role === 'user' ? 'u' : 'h'),
    recordId: item && item.recordId,
    role,
    content: (item && item.content) || '',
    sources: (item && item.sources) || [],
    blocked: !!(item && item.blocked),
    blockReason: (item && item.blockReason) || '',
    knowledgeCovered: !item || item.knowledgeCovered !== false,
    scopeWarning: (item && item.scopeWarning) || '',
    kpNames: (item && item.kpNames) || [],
    action: (item && item.action) || null,
    mode: (item && item.mode) || '',
    model: (item && item.model) || '',
    modelSource: (item && item.modelSource) || '',
    createdAt: (item && item.createdAt) || new Date().toISOString(),
    conversationId: (item && item.conversationId) || activeId.value,
    gate: normalizeGate(item && item.gate),
    fromHistory: true,
  }
}

async function loadConversations(silent = false) {
  if (!silent) convLoading.value = true
  convError.value = ''
  try {
    const data = await student.conversations({ page: 1, size: 20 })
    conversations.value = (data && data.items) || []
  } catch (err) {
    conversations.value = []
    convError.value =
      err && (err.status === 404 || err.status === 501)
        ? '当前后端暂未提供会话列表接口，已自动降级为单轮问答。'
        : err.message || '会话列表加载失败'
  } finally {
    convLoading.value = false
  }
}

async function init() {
  await loadConversations()
  const target = props.initialConversationId
  if (target !== null && target !== undefined && target !== '') {
    await openConversation(target)
  } else if (conversations.value.length) {
    await openConversation(conversations.value[0].id)
  } else {
    startNewLocal()
  }
  scrollToBottom()
}

onMounted(init)

function startNewLocal() {
  messages.splice(0, messages.length)
  activeId.value = null
  activeTitle.value = '新对话'
  historyError.value = ''
  scrollToBottom()
}

async function openConversation(id) {
  if (id === null || id === undefined || id === '') return
  if (String(activeId.value) === String(id) && !historyError.value && !historyLoading.value) return
  historyLoading.value = true
  historyError.value = ''
  activeId.value = id
  try {
    const data = await student.conversation(id)
    messages.splice(0, messages.length)
    const list = (data && data.messages) || []
    list.forEach((item) => messages.push(mapHistoryMessage(item)))
    activeTitle.value = (data && data.title) || '历史对话'
    if (!conversations.value.some((conv) => String(conv.id) === String(id))) {
      await loadConversations(true)
    }
  } catch (err) {
    messages.splice(0, messages.length)
    historyError.value =
      err && err.status === 404
        ? '该会话不存在或已被删除，可从左侧选择其他会话。'
        : err.message || '会话历史加载失败'
    toast.error(historyError.value)
  } finally {
    historyLoading.value = false
    scrollToBottom()
  }
}

function selectConversation(conv) {
  if (!conv || conv.id === null || conv.id === undefined) return
  if (String(conv.id) === String(activeId.value)) return
  openConversation(conv.id)
}

async function newConversation() {
  if (sending.value) return
  startNewLocal()
  let created = null
  try {
    created = await student.createConversation()
  } catch (err) {
    if (!createFallbackHinted) {
      createFallbackHinted = true
      if (err && (err.status === 404 || err.status === 501)) {
        toast.info('后端暂不支持新建空会话，将在首次提问时自动创建。')
      }
    }
  }
  if (created && created.id !== undefined && created.id !== null) {
    activeId.value = created.id
    activeTitle.value = created.title || '新对话'
    conversations.value.unshift({
      id: created.id,
      title: created.title || '新对话',
      messageCount: 0,
      updatedAt: created.createdAt || new Date().toISOString(),
    })
  }
}

async function renameConversation(conv) {
  if (!conv || conv.id === null || conv.id === undefined || renamingId.value !== null) return
  const next = window.prompt('重命名对话', conv.title || '')
  if (next === null) return
  const title = next.trim()
  if (!title || title === conv.title) return
  renamingId.value = conv.id
  try {
    await student.renameConversation(conv.id, title)
    conv.title = title
    if (String(activeId.value) === String(conv.id)) activeTitle.value = title
    toast.success('对话已重命名')
  } catch (err) {
    toast.error(err.message || '重命名失败')
  } finally {
    renamingId.value = null
  }
}

async function deleteConversation(conv) {
  if (!conv || conv.id === null || conv.id === undefined || deletingId.value !== null) return
  if (!window.confirm('确认删除对话「' + (conv.title || '未命名') + '」？删除后聊天记录将无法恢复。')) return
  deletingId.value = conv.id
  try {
    await student.deleteConversation(conv.id)
    conversations.value = conversations.value.filter((item) => String(item.id) !== String(conv.id))
    if (String(activeId.value) === String(conv.id)) startNewLocal()
    toast.success('对话已删除')
  } catch (err) {
    toast.error(err.message || '删除失败')
  } finally {
    deletingId.value = null
  }
}

function upsertConversation(id, text) {
  const list = conversations.value
  const found = list.find((conv) => String(conv.id) === String(id))
  const now = new Date().toISOString()
  if (found) {
    found.lastMessage = text
    found.messageCount = (found.messageCount || 0) + 2
    found.updatedAt = now
    return
  }
  list.unshift({
    id,
    title: text.slice(0, 20),
    messageCount: 2,
    lastMessage: text,
    updatedAt: now,
  })
}

function handleEnter(event) {
  if (event.shiftKey) return
  event.preventDefault()
  send()
}

/* ------------------------------ 图片答疑 ------------------------------ */
function triggerVisionPick() {
  if (sending.value || visionBusy.value) return
  if (visionInput.value) visionInput.value.click()
}

function revokePreview() {
  if (vision.previewUrl) {
    URL.revokeObjectURL(vision.previewUrl)
    vision.previewUrl = ''
  }
}

function resetVision() {
  revokePreview()
  compressedFile = null
  vision.status = 'idle'
  vision.fileName = ''
  vision.sizeText = ''
  vision.message = ''
  vision.model = ''
  vision.error = false
}

async function onImagePicked(event) {
  const input = event && event.target
  const file = input && input.files && input.files[0]
  if (input) input.value = ''
  if (!file) return
  await handleImageFile(file)
}

/* 剪贴板粘贴 / 拖拽 / 按钮选择 → 同一条识别链路 */
function onComposePaste(event) {
  if (sending.value || visionBusy.value) return
  const items = (event.clipboardData && event.clipboardData.items) || []
  for (const item of items) {
    if (item.kind === 'file' && /^image\//.test(item.type || '')) {
      const file = item.getAsFile()
      if (file) {
        event.preventDefault()
        handleImageFile(file)
        return
      }
    }
  }
}

function onComposeDrop(event) {
  if (sending.value || visionBusy.value) return
  const files = (event.dataTransfer && event.dataTransfer.files) || []
  const file = files[0]
  if (file && /^image\//.test(file.type || '')) {
    event.preventDefault()
    handleImageFile(file)
  }
}

async function handleImageFile(file) {
  if (!file || sending.value || visionBusy.value) return
  const check = validateImageFile(file)
  if (!check.ok) {
    toast.error(check.message)
    return
  }
  resetVision()
  vision.fileName = file.name || '粘贴的图片'
  vision.sizeText = formatFileSize(file.size)
  vision.status = 'compressing'
  let finalFile = file
  try {
    finalFile = await compressImageFile(file)
  } catch (err) {
    // 压缩失败时回退原图（仍受 5MB 上限约束），不让流程中断
    finalFile = file
  }
  if (finalFile.size > MAX_IMAGE_BYTES) {
    vision.status = 'error'
    vision.error = true
    vision.message = '图片压缩后仍超过 5MB，请换一张分辨率更低的截图。'
    toast.error(vision.message)
    return
  }
  compressedFile = finalFile
  vision.previewUrl = URL.createObjectURL(finalFile)
  vision.sizeText = formatFileSize(finalFile.size)
  await uploadVision(finalFile)
}

async function uploadVision(file) {
  vision.status = 'uploading'
  vision.message = ''
  vision.error = false
  try {
    const data = await student.chatVision(file)
    const text = (data && data.text) || ''
    vision.model = (data && data.model) || ''
    if (!text.trim()) {
      vision.status = 'error'
      vision.error = true
      vision.message = '未识别到文字，请换一张更清晰的图片，或直接输入问题。'
      return
    }
    vision.status = 'done'
    draft.value = draft.value.trim() ? text.trim() + '\n' + draft.value.trim() : text.trim()
    toast.success('已识别图片文字，可修改后发送')
  } catch (err) {
    vision.status = 'error'
    vision.error = true
    if (err && err.code === 'TIMEOUT') {
      vision.message = '图片识别超时（已等待 60 秒），请重试或手动输入。'
    } else if (err && err.status === 404) {
      vision.message = '后端暂未提供图片识别接口（404），请先手动输入问题。'
    } else {
      vision.message = '图片识别失败：' + (err && err.message ? err.message : '请稍后重试')
    }
    toast.error('图片识别失败，可手动输入问题')
  }
}

function retryVision() {
  if (compressedFile && !visionBusy.value) uploadVision(compressedFile)
}

async function send() {
  const text = draft.value.trim()
  if (!text || sending.value || visionBusy.value) return
  draft.value = ''
  resetVision()
  await ask(text)
}

async function ask(text) {
  const userMessage = {
    id: nextId('u'),
    role: 'user',
    content: text,
    createdAt: new Date().toISOString(),
  }
  messages.push(userMessage)
  const assistantMessage = {
    id: nextId('a'),
    role: 'assistant',
    loading: true,
    content: '',
    prompt: text,
    sources: [],
    kpNames: [],
  }
  messages.push(assistantMessage)
  sending.value = true
  scrollToBottom()

  try {
    const data = await student.chat({ message: text, conversationId: activeId.value })
    assistantMessage.loading = false
    assistantMessage.content = data.reply || '（AI 未返回内容）'
    assistantMessage.sources = data.sources || []
    assistantMessage.blocked = !!data.blocked
    assistantMessage.blockReason = data.blockReason || ''
    assistantMessage.action = data.action || null
    assistantMessage.kpNames = data.kpNames || []
    assistantMessage.recordId = data.recordId
    assistantMessage.createdAt = data.createdAt || new Date().toISOString()
    assistantMessage.intent = data.intent
    // v1.1：字段缺失时按「已覆盖」兼容处理，避免旧后端导致误报
    assistantMessage.knowledgeCovered = data.knowledgeCovered !== false
    assistantMessage.scopeWarning = data.scopeWarning || ''
    // v1.2：模式与 Key 来源标签
    assistantMessage.mode = data.mode || ''
    assistantMessage.model = data.model || ''
    assistantMessage.modelSource = data.modelSource || ''
    // v1.3：前置自测卡片（action=GATE 时 gate.state 通常为 QUIZ）
    assistantMessage.gate = normalizeGate(data.gate)
    if (assistantMessage.gate) assistantMessage.conversationId = data.conversationId || activeId.value
    if (data.conversationId !== undefined && data.conversationId !== null) {
      const isNew = activeId.value === null
      activeId.value = data.conversationId
      assistantMessage.conversationId = data.conversationId
      if (isNew && (!activeTitle.value || activeTitle.value === '新对话') && data.conversationTitle) {
        activeTitle.value = data.conversationTitle
      }
      upsertConversation(data.conversationId, text)
      loadConversations(true)
    }
  } catch (error) {
    assistantMessage.loading = false
    assistantMessage.error = true
    assistantMessage.content =
      error.code === 'TIMEOUT'
        ? `AI 回答超时（已等待 90 秒）。请稍后点击「重试」，或缩短问题描述后再试。`
        : `提问失败：${error.message}`
    toast.error(error.message || '答疑请求失败')
  } finally {
    sending.value = false
    scrollToBottom()
  }
}

async function retry(message) {
  const index = messages.indexOf(message)
  const prompt = message.prompt
  if (index >= 0) messages.splice(index, 1)
  const prev = messages[messages.length - 1]
  if (prompt && prev && prev.role === 'user' && prev.content === prompt) messages.pop()
  if (prompt) await ask(prompt)
}

function handleAction(action) {
  if (!action || !action.type) return
  const page = ACTION_PAGE[action.type]
  if (page) {
    toast.info(action.label || ACTION_LABEL[action.type] || '正在跳转')
    props.navigate(page)
  }
}

/** 前置自测状态变化后刷新会话列表（会话标题/消息数可能已更新） */
function handleGateChecked() {
  loadConversations(true)
}

/** 检索得分：0~1 归一化分数转百分比，其余原样展示 */
function scoreText(score) {
  const value = Number(score)
  if (!Number.isFinite(value) || value <= 0) return ''
  if (value <= 1) return (value * 100).toFixed(1) + '%'
  return value.toFixed(2)
}

/** 来源按 chunkId 去重（同一片段重复命中只保留最高分一条），无 chunkId 时按文档+摘要兜底 */
function dedupeSources(sources) {
  if (!Array.isArray(sources)) return []
  const best = new Map()
  sources.forEach((source) => {
    if (!source || typeof source !== 'object') return
    const chunkId = source.chunkId !== undefined && source.chunkId !== null ? source.chunkId : source.chunk_id
    const key =
      chunkId !== undefined && chunkId !== null
        ? 'c:' + chunkId
        : 'k:' + [source.documentId, source.title, source.excerpt].join('|')
    const score = Number(source.score)
    const existing = best.get(key)
    if (!existing || (Number.isFinite(score) && score > Number(existing.score || 0))) {
      best.set(key, source)
    }
  })
  return Array.from(best.values())
}

async function copyMessage(message) {
  try {
    await navigator.clipboard.writeText(message.content || '')
    toast.success('已复制回答内容')
  } catch {
    toast.error('当前浏览器不支持自动复制，请手动选择文本。')
  }
}

function useSuggestion(text) {
  draft.value = text
}
</script>

<template>
  <div>
    <div class="module-intro">
      <p class="eyebrow">答疑辅导 · AI TUTOR</p>
      <h1>随时提问，回答有据可查</h1>
      <p>会话式答疑：同一对话内可连续追问，AI 会结合上文与课程知识库回答；支持 Markdown 与数学公式。</p>
    </div>

    <section class="tutor-panel panel">
      <div class="chat-header">
        <div class="assistant-avatar">知</div>
        <div class="chat-head-main">
          <strong>知学 AI 助教 · {{ activeTitle }}</strong>
          <span>DeepSeek 驱动 · 课程知识库检索增强 · 会话上下文</span>
        </div>
        <button class="btn btn-outline btn-sm" type="button" :disabled="sending" @click="newConversation">
          ＋ 新建对话
        </button>
      </div>

      <div class="tutor-body">
        <aside class="conversation-rail">
          <div class="rail-head">
            <strong>我的对话</strong>
            <button class="text-button" type="button" :disabled="sending" @click="newConversation">＋ 新建</button>
          </div>
          <div v-if="convLoading" class="skeleton rail-skeleton">
            <div class="skeleton-line w-80"></div>
            <div class="skeleton-line w-60"></div>
            <div class="skeleton-line w-80"></div>
          </div>
          <div v-else-if="convError" class="rail-note">{{ convError }}</div>
          <div v-else-if="!conversations.length" class="rail-note">
            还没有历史对话，发送第一条问题后会自动保存到这里。
          </div>
          <div v-else class="conversation-list">
            <div
              v-for="conv in conversations"
              :key="conv.id"
              class="conversation-item"
              :class="{ active: String(conv.id) === String(activeId) }"
              role="button"
              tabindex="0"
              @click="selectConversation(conv)"
              @keydown.enter="selectConversation(conv)"
            >
              <div class="conv-main">
                <strong>{{ conv.title || '未命名对话' }}</strong>
                <span>{{ conv.messageCount || 0 }} 条 · {{ formatDateTime(conv.updatedAt || conv.createdAt) }}</span>
              </div>
              <div class="conv-actions">
                <button class="text-button" type="button" :disabled="renamingId === conv.id" @click.stop="renameConversation(conv)">
                  {{ renamingId === conv.id ? '…' : '改名' }}
                </button>
                <button class="text-button danger" type="button" :disabled="deletingId === conv.id" @click.stop="deleteConversation(conv)">
                  {{ deletingId === conv.id ? '…' : '删除' }}
                </button>
              </div>
            </div>
          </div>
        </aside>

        <div class="tutor-main">
          <div ref="chatBody" class="chat-body">
            <div v-if="historyLoading" class="thinking">
              <span class="spinner"></span>
              正在加载会话历史…
            </div>
            <div v-else-if="historyError" class="alert alert-error">
              <div>{{ historyError }}</div>
              <button class="btn btn-ghost btn-sm" style="margin-left: 10px" @click="openConversation(activeId)">重试</button>
            </div>
            <template v-else>
              <div v-if="!messages.length" class="welcome-block">
                <div class="assistant-message">
                  <strong>{{ greeting.displayName }} · 学习助教</strong>
                  <MarkdownView :content="WELCOME" />
                </div>
                <div class="suggestions" style="display: grid; gap: 8px">
                  <button v-for="item in SUGGESTIONS" :key="item" type="button" @click="useSuggestion(item)">
                    {{ item }}
                  </button>
                </div>
              </div>
            </template>

            <template v-for="message in messages" :key="message.id">
              <div v-if="message.role === 'user'" class="user-message">{{ message.content }}</div>

              <div v-else class="assistant-message">
                <strong>{{ greeting.displayName }} · 学习助教</strong>

                <div v-if="message.loading" class="thinking">
                  <span class="spinner"></span>
                  正在检索知识库并生成回答…
                </div>

                <div v-else-if="message.blocked" class="blocked-message">
                  <div class="blocked-title">该问题超出当前教学范围</div>
                  <p class="blocked-text">{{ message.content || '该内容超出当前教学范围，暂时无法解答。' }}</p>
                  <p v-if="message.blockReason" class="blocked-reason">判定依据：{{ message.blockReason }}</p>
                </div>

                <template v-else>
                  <div v-if="message.scopeWarning" class="alert alert-warn scope-warning">
                    <span class="scope-warning-label">范围提示</span>
                    <span class="scope-warning-text">{{ message.scopeWarning }}</span>
                  </div>
                  <div v-if="message.knowledgeCovered === false" class="alert alert-warn knowledge-hint">
                    <span class="scope-warning-label">知识库未覆盖</span>
                    <span class="scope-warning-text">以下为模型通用回答，未引用课程知识库，请结合教材核对。</span>
                  </div>
                  <MarkdownView :content="message.content" />
                </template>

                <GateCard
                  v-if="message.gate"
                  :gate="message.gate"
                  :conversation-id="message.conversationId || activeId"
                  :readonly="!!message.fromHistory"
                  @checked="handleGateChecked"
                />

                <div v-if="message.kpNames && message.kpNames.length" class="chip-group" style="margin-top: 10px">
                  <span v-for="name in message.kpNames" :key="name" class="chip selected">{{ name }}</span>
                </div>

                <details v-if="dedupeSources(message.sources).length" class="sources">
                  <summary>
                    知识库来源（{{ dedupeSources(message.sources).length }} 段）
                    <span class="source-note">已按片段去重</span>
                  </summary>
                  <div
                    v-for="(source, index) in dedupeSources(message.sources)"
                    :key="source.chunkId || source.chunk_id || index"
                    class="source-card"
                  >
                    <div class="source-title">
                      <span class="source-citation">{{ source.citation || source.title || '知识库文档' }}</span>
                      <span class="source-tags">
                        <span class="tag purple">{{ KB_LABEL[source.kb] || source.kb || '知识库' }}</span>
                        <span v-if="scoreText(source.score)" class="source-score">检索得分 {{ scoreText(source.score) }}</span>
                      </span>
                    </div>
                    <div v-if="source.citation && (source.title || source.chapter || source.section)" class="source-origin">
                      {{ source.title || '' }}<template v-if="source.chapter"> · {{ source.chapter }}</template><template v-if="source.section"> · {{ source.section }}</template>
                    </div>
                    <p>{{ source.excerpt || '（无摘要）' }}</p>
                  </div>
                </details>

                <div class="msg-tools">
                  <span class="muted">{{ formatDateTime(message.createdAt) }}</span>
                  <button v-if="!message.loading && !message.error" type="button" @click="copyMessage(message)">复制</button>
                  <button v-if="message.error" type="button" class="msg-retry" @click="retry(message)">重试</button>
                  <button
                    v-if="message.action && message.action.type && message.action.type !== 'NONE' && !isGateAction(message.action)"
                    type="button"
                    @click="handleAction(message.action)"
                  >
                    {{ message.action.label || ACTION_LABEL[message.action.type] || '下一步' }}
                  </button>
                </div>
                <div v-if="!message.loading && answerModeTags(message).length" class="answer-mode">
                  <span v-for="tag in answerModeTags(message)" :key="tag.text" class="tag" :class="tag.tone">{{ tag.text }}</span>
                  <span v-if="message.fromHistory" class="tag gray">历史消息</span>
                </div>
              </div>
            </template>
          </div>

          <div class="chat-input-area" @dragover.prevent @drop.prevent="onComposeDrop">
            <div v-if="vision.status !== 'idle'" class="vision-preview" :class="{ 'has-error': vision.error }">
              <div class="vision-thumb">
                <img v-if="vision.previewUrl" :src="vision.previewUrl" alt="待识别图片缩略图" />
                <span v-else class="vision-thumb-placeholder">🖼️</span>
                <span v-if="visionBusy" class="spinner vision-spinner"></span>
              </div>
              <div class="vision-meta">
                <strong v-if="vision.status === 'compressing'">正在压缩图片…</strong>
                <strong v-else-if="vision.status === 'uploading'">正在识别图片文字…</strong>
                <strong v-else-if="vision.status === 'done'">已识别文字，已填入输入框</strong>
                <strong v-else>图片识别失败</strong>
                <span class="vision-sub">
                  {{ vision.fileName }}<template v-if="vision.sizeText"> · {{ vision.sizeText }}</template>
                  <template v-if="vision.model"> · {{ vision.model }}</template>
                </span>
                <span v-if="vision.message" class="vision-status" :class="vision.error ? 'error' : 'ok'">{{ vision.message }}</span>
              </div>
              <div class="vision-actions">
                <button v-if="vision.status === 'error'" class="btn btn-outline btn-sm" type="button" :disabled="visionBusy" @click="retryVision">重试识别</button>
                <button class="text-button" type="button" :disabled="visionBusy" @click="resetVision">移除</button>
              </div>
            </div>
            <div class="compose-row">
              <button
                class="btn btn-outline image-btn"
                type="button"
                :disabled="sending || historyLoading || visionBusy"
                :title="'上传题目截图（png/jpeg/webp/gif，自动压缩到最长边 1600px）'"
                @click="triggerVisionPick"
              >
                🖼️ 图片
              </button>
              <textarea
                v-model="draft"
                rows="2"
                placeholder="输入你的问题，例如「洛必达法则的使用条件是什么？」（Enter 发送，Shift+Enter 换行；可直接粘贴/拖入截图或点「图片」按钮识别文字）"
                :disabled="sending || historyLoading"
                @keydown.enter="handleEnter"
                @paste="onComposePaste"
              ></textarea>
              <button
                class="btn btn-primary"
                :disabled="sending || historyLoading || visionBusy || !draft.trim()"
                @click="send"
              >
                <span v-if="sending" class="spinner light"></span>
                {{ sending ? '生成中…' : '发送' }}
              </button>
            </div>
            <input ref="visionInput" class="hidden-file" type="file" :accept="ACCEPT_ATTR" @change="onImagePicked" />
          </div>
          <p class="chat-footnote">
            AI 回答由大模型生成，可能存在不准确之处；数学公式使用 KaTeX 渲染，请结合教材核对。图片仅用于识别文字，不保存原图。
          </p>
        </div>
      </div>
    </section>
  </div>
</template>
