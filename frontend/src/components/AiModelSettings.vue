<script setup>
/**
 * AiModelSettings —— v1.2 用户 AI 模型设置卡（学生/教师个人信息页共用）
 * 接口：GET/PUT/DELETE /api/profile/ai（契约 §4.1）
 * 已保存的 Key 只回显掩码；apiKey 缺省=不变，空串=清除。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { auth } from '../api'
import { toast } from '../toast'

const emit = defineEmits(['refresh-health'])

const PRESET_MODELS = [
  { value: 'deepseek-flash', label: 'deepseek-flash（默认，速度快）' },
  { value: 'deepseek-v4-pro', label: 'deepseek-v4-pro（能力更强）' },
  { value: '__custom__', label: '自定义模型名…' },
]

const loading = ref(true)
const loadError = ref('')
const unsupported = ref(false)
const saving = ref(false)
const clearing = ref(false)

const config = reactive({
  enabled: false,
  baseUrl: 'https://api.deepseek.com',
  model: 'deepseek-flash',
  hasApiKey: false,
  apiKeyMasked: '',
})

const form = reactive({
  enabled: false,
  baseUrl: 'https://api.deepseek.com',
  modelChoice: 'deepseek-flash',
  customModel: '',
  apiKey: '',
})

const replacing = ref(false)
const formError = ref('')
const savedTip = ref('')

const currentModel = computed(() =>
  form.modelChoice === '__custom__' ? form.customModel.trim() : form.modelChoice
)

const maskedLabel = computed(() => {
  if (config.apiKeyMasked) return config.apiKeyMasked
  if (config.hasApiKey) return '已保存（掩码不可用）'
  return ''
})

function assignConfig(data) {
  const next = data && typeof data === 'object' ? data : {}
  config.enabled = !!next.enabled
  config.baseUrl = next.baseUrl || 'https://api.deepseek.com'
  config.model = next.model || 'deepseek-flash'
  config.hasApiKey = !!next.hasApiKey
  config.apiKeyMasked = next.apiKeyMasked || ''

  form.enabled = config.enabled
  form.baseUrl = config.baseUrl
  if (PRESET_MODELS.some((item) => item.value === config.model)) {
    form.modelChoice = config.model
    form.customModel = ''
  } else {
    form.modelChoice = '__custom__'
    form.customModel = config.model
  }
  form.apiKey = ''
  replacing.value = false
}

async function load() {
  loading.value = true
  loadError.value = ''
  unsupported.value = false
  try {
    const data = await auth.aiConfig()
    assignConfig(data)
  } catch (err) {
    if (err && (err.status === 404 || err.status === 501 || err.code === 'HTTP_404')) {
      unsupported.value = true
    } else {
      loadError.value = err.message || 'AI 配置加载失败'
    }
  } finally {
    loading.value = false
  }
}

function validate() {
  formError.value = ''
  const baseUrl = form.baseUrl.trim()
  if (!baseUrl) {
    formError.value = '请填写 Base URL。'
    return false
  }
  if (!/^https:\/\//i.test(baseUrl)) {
    formError.value = 'Base URL 必须以 https:// 开头。'
    return false
  }
  if (!currentModel.value) {
    formError.value = '请选择或填写模型名称。'
    return false
  }
  if (form.enabled && !config.hasApiKey && !form.apiKey.trim()) {
    formError.value = '开启「使用我的 Key」后，需要填写 API Key。'
    return false
  }
  return true
}

async function save() {
  if (saving.value || loading.value) return
  if (!validate()) return
  saving.value = true
  savedTip.value = ''
  try {
    const payload = {
      enabled: form.enabled,
      baseUrl: form.baseUrl.trim(),
      model: currentModel.value,
    }
    const key = form.apiKey.trim()
    if (key) payload.apiKey = key
    const updated = await auth.saveAiConfig(payload)
    assignConfig(updated || {
      ...config,
      enabled: payload.enabled,
      baseUrl: payload.baseUrl,
      model: payload.model,
      hasApiKey: config.hasApiKey || !!key,
    })
    toast.success('AI 模型设置已保存')
    savedTip.value = '已保存，下一次提问立即生效。'
    emit('refresh-health')
  } catch (err) {
    formError.value = err.message || '保存失败'
  } finally {
    saving.value = false
  }
}

async function clearKey() {
  if (clearing.value) return
  if (!window.confirm('确认清除已保存的 API Key？清除后将使用系统默认 Key。')) return
  clearing.value = true
  formError.value = ''
  try {
    await auth.clearAiConfig()
    config.hasApiKey = false
    config.apiKeyMasked = ''
    config.enabled = false
    form.enabled = false
    form.apiKey = ''
    replacing.value = false
    toast.success('已清除 API Key，将使用系统默认 Key')
    emit('refresh-health')
  } catch (err) {
    formError.value = err.message || '清除失败'
  } finally {
    clearing.value = false
  }
}

onMounted(load)
</script>

<template>
  <section class="panel ai-config-panel">
    <div class="panel-heading">
      <div>
        <h3>AI 模型设置</h3>
        <p>默认使用系统 DeepSeek Key；也可填写自己的 Key，仅本次账号生效。</p>
      </div>
      <span class="tag" :class="config.hasApiKey ? 'green' : 'gray'">
        {{ config.hasApiKey ? '已配置我的 Key' : '使用系统 Key' }}
      </span>
    </div>

    <div v-if="loading" class="skeleton">
      <div class="skeleton-line w-60"></div>
      <div class="skeleton-line w-80"></div>
      <div class="skeleton-line w-40"></div>
    </div>

    <div v-else-if="unsupported" class="alert alert-info">
      当前后端版本暂未提供「用户 AI 配置」接口（/api/profile/ai），页面已降级：你仍可正常使用系统默认 Key 提问。
    </div>

    <div v-else-if="loadError" class="alert alert-error">
      <div>{{ loadError }}</div>
      <button class="btn btn-ghost btn-sm" style="margin-left: 10px" @click="load">重试</button>
    </div>

    <template v-else>
      <div class="form-grid">
        <div class="form-field full">
          <label>使用我的 Key</label>
          <div class="switch-row">
            <label class="switch">
              <input v-model="form.enabled" type="checkbox" :disabled="saving" />
              <span class="slider"></span>
            </label>
            <span class="form-hint">
              {{ form.enabled ? '已开启：提问时优先使用你的 Key 与模型' : '已关闭：使用系统默认 Key' }}
            </span>
          </div>
        </div>

        <div class="form-field">
          <label>Base URL</label>
          <input v-model="form.baseUrl" class="input" placeholder="https://api.deepseek.com" :disabled="saving" />
          <span class="form-hint">需以 https:// 开头，兼容 DeepSeek / OpenAI 协议服务</span>
        </div>

        <div class="form-field">
          <label>模型</label>
          <select v-model="form.modelChoice" class="select" :disabled="saving">
            <option v-for="item in PRESET_MODELS" :key="item.value" :value="item.value">{{ item.label }}</option>
          </select>
          <input
            v-if="form.modelChoice === '__custom__'"
            v-model="form.customModel"
            class="input"
            style="margin-top: 8px"
            placeholder="例如 deepseek-chat"
            :disabled="saving"
          />
        </div>

        <div class="form-field full">
          <label>API Key</label>
          <div v-if="config.hasApiKey && !replacing" class="api-key-masked">
            <span class="tag purple">{{ maskedLabel }}</span>
            <button class="text-button" type="button" :disabled="saving" @click="replacing = true">替换</button>
            <button class="text-button danger" type="button" :disabled="clearing" @click="clearKey">
              {{ clearing ? '清除中…' : '清除' }}
            </button>
          </div>
          <template v-else>
            <input
              v-model="form.apiKey"
              class="input"
              type="password"
              autocomplete="off"
              :placeholder="config.hasApiKey ? '输入新的 Key（留空保持原 Key 不变）' : 'sk-...（留空则使用系统默认 Key）'"
              :disabled="saving"
            />
            <span class="form-hint">Key 仅加密保存在本机数据库，不写入日志、不回显明文。</span>
          </template>
          <button
            v-if="replacing"
            class="text-button"
            type="button"
            style="margin-top: 6px"
            @click="replacing = false"
          >
            取消替换
          </button>
        </div>
      </div>

      <div v-if="formError" class="alert alert-error" style="margin-top: 14px">{{ formError }}</div>
      <div v-else-if="savedTip" class="alert alert-success" style="margin-top: 14px">{{ savedTip }}</div>

      <div class="exam-actions">
        <button class="btn btn-primary" :disabled="saving || loading" @click="save">
          <span v-if="saving" class="spinner light"></span>
          {{ saving ? '保存中…' : '保存 AI 设置' }}
        </button>
        <span class="form-hint" style="align-self: center">留空 API Key 即使用系统默认 Key；未启用时忽略上方配置。</span>
      </div>
    </template>
  </section>
</template>
