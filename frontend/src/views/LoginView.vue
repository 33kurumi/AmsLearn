<script setup>
/**
 * LoginView —— 登录 / 注册页（A1 POST /auth/login，v1.4 POST /auth/register）
 * - 登录 / 注册双 tab；注册成功后直接返回登录态，由 App.vue 按 role 进入学生端
 * - 演示账号一键填充；服务健康检查与 AI 模式徽标保留
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { auth, common } from '../api'
import { readAiStatus } from '../utils/aiMode'

const emit = defineEmits(['logged-in'])

const mode = ref('login')
const form = reactive({ username: '', password: '' })
const registerForm = reactive({ username: '', displayName: '', password: '', confirmPassword: '' })
const fieldErrors = reactive({ username: '', displayName: '', password: '', confirmPassword: '' })
const loading = ref(false)
const errorMessage = ref('')
const healthText = ref('正在检测服务…')
const healthOk = ref(false)
const aiStatus = ref(readAiStatus(null))

const DEMO_ACCOUNTS = [
  { username: 'student1', password: '123456', label: '学生 · 张同学', sub: 'C-GS-01 · 高数强化班' },
  { username: 'teacher1', password: '123456', label: '教师 · 王老师', sub: 'C-GS-01 · 高等数学' },
]

const canSubmit = computed(() => form.username.trim() && form.password && !loading.value)
const canSubmitRegister = computed(
  () =>
    registerForm.username.trim() &&
    registerForm.displayName.trim() &&
    registerForm.password &&
    registerForm.confirmPassword &&
    !loading.value
)

function clearErrors() {
  errorMessage.value = ''
  Object.keys(fieldErrors).forEach((key) => {
    fieldErrors[key] = ''
  })
}

function switchMode(next) {
  if (mode.value === next || loading.value) return
  mode.value = next
  clearErrors()
}

function fill(account) {
  form.username = account.username
  form.password = account.password
  errorMessage.value = ''
}

function validateRegister() {
  clearErrors()
  const username = registerForm.username.trim()
  if (!username) fieldErrors.username = '请输入用户名。'
  else if (!/^[A-Za-z0-9_]{4,20}$/.test(username)) {
    fieldErrors.username = '用户名需为 4~20 位字母、数字或下划线。'
  }

  const displayName = registerForm.displayName.trim()
  if (!displayName) fieldErrors.displayName = '请输入昵称。'
  else if (displayName.length > 20) fieldErrors.displayName = '昵称不能超过 20 个字符。'

  const password = registerForm.password
  if (!password) fieldErrors.password = '请输入密码。'
  else if (password.length < 6 || password.length > 32) fieldErrors.password = '密码长度需为 6~32 位。'

  const confirmPassword = registerForm.confirmPassword
  if (!confirmPassword) fieldErrors.confirmPassword = '请再次输入密码。'
  else if (confirmPassword !== password) fieldErrors.confirmPassword = '两次输入的密码不一致。'

  return Object.values(fieldErrors).every((message) => !message)
}

async function submit() {
  if (!canSubmit.value) return
  loading.value = true
  errorMessage.value = ''
  try {
    const data = await auth.login(form.username.trim(), form.password)
    if (!data || !data.token || !data.user) {
      throw new Error('登录返回数据不完整，请联系管理员检查后端实现。')
    }
    emit('logged-in', { token: data.token, user: data.user })
  } catch (error) {
    errorMessage.value = error.message || '登录失败，请稍后重试。'
  } finally {
    loading.value = false
  }
}

async function submitRegister() {
  if (loading.value) return
  if (!validateRegister()) return
  loading.value = true
  try {
    const data = await auth.register({
      username: registerForm.username.trim(),
      password: registerForm.password,
      displayName: registerForm.displayName.trim(),
    })
    if (!data || !data.token || !data.user) {
      throw new Error('注册返回数据不完整，请联系管理员检查后端实现。')
    }
    // 注册用户为学生；若后端未返回 role，则由前端补全，确保直接进入学生端
    emit('logged-in', { token: data.token, user: { ...data.user, role: data.user.role || 'STUDENT' } })
  } catch (error) {
    errorMessage.value = error.message || '注册失败，请稍后重试。'
  } finally {
    loading.value = false
  }
}

async function checkHealth() {
  try {
    const data = await common.health()
    healthOk.value = true
    aiStatus.value = readAiStatus(data)
    healthText.value = `服务已连接 · Java ${data.java || 'UP'} · AI ${data.ai || 'UP'}`
  } catch (error) {
    healthOk.value = false
    aiStatus.value = readAiStatus(null)
    healthText.value = error.code === 'TIMEOUT' ? '服务响应超时' : '业务服务未连接（登录后仍可查看界面，数据需服务启动）'
  }
}

onMounted(checkHealth)
</script>

<template>
  <div class="login-page">
    <section class="login-visual">
      <div class="login-brand">
        <div class="brand-icon">知</div>
        <div>
          <div class="brand-name">知学 AI</div>
          <div class="brand-subtitle">PERSONAL LEARNING TUTOR</div>
        </div>
      </div>
      <div class="login-visual-main">
        <p class="eyebrow">高等数学考研辅导 · 个性化学习导师</p>
        <h1>把每一次提问，<br />都变成看得见的进步。</h1>
        <p>智能答疑、知识诊断、分层练习与学习计划，围绕你的薄弱知识点持续迭代。</p>
        <div class="login-features">
          <div class="login-feature">
            <span class="f-icon">✳</span>
            <div><strong>知识库溯源答疑</strong><span>回答附带来源片段，教师可配置教学边界</span></div>
          </div>
          <div class="login-feature">
            <span class="f-icon">▥</span>
            <div><strong>诊断与掌握度</strong><span>快速 5 题 / 全面 15 题，输出错因与报告</span></div>
          </div>
          <div class="login-feature">
            <span class="f-icon">▤</span>
            <div><strong>每日学习计划</strong><span>学习 · 练习 · 复盘，按天打卡推进</span></div>
          </div>
        </div>
      </div>
      <div class="login-visual-foot">
        课程实训项目 · Vue3 + Spring Boot + FastAPI + DeepSeek
      </div>
    </section>

    <section class="login-panel">
      <div class="login-card">
        <div class="login-mode">
          <span class="ai-badge" :class="aiStatus.tone" :title="aiStatus.detail">
            <i class="dot"></i>{{ aiStatus.label }}
          </span>
          <span class="muted">答疑模式由后端 /api/health 提供</span>
        </div>

        <div class="tab-bar login-tabs">
          <button type="button" class="tab" :class="{ selected: mode === 'login' }" @click="switchMode('login')">登录</button>
          <button type="button" class="tab" :class="{ selected: mode === 'register' }" @click="switchMode('register')">注册</button>
        </div>

        <template v-if="mode === 'login'">
          <h2>欢迎回来</h2>
          <p class="login-sub">请使用课程演示账号登录，或填写你的账号密码。</p>

          <form class="login-form" @submit.prevent="submit">
            <div class="form-field">
              <label for="login-username">用户名 <span class="required">*</span></label>
              <input
                id="login-username"
                v-model="form.username"
                class="input"
                type="text"
                autocomplete="username"
                placeholder="例如 student1 / teacher1"
                :disabled="loading"
              />
            </div>
            <div class="form-field">
              <label for="login-password">密码 <span class="required">*</span></label>
              <input
                id="login-password"
                v-model="form.password"
                class="input"
                type="password"
                autocomplete="current-password"
                placeholder="演示账号密码 123456"
                :disabled="loading"
              />
            </div>

            <p v-if="errorMessage" class="login-error">{{ errorMessage }}</p>

            <button class="btn btn-primary btn-block login-submit" type="submit" :disabled="!canSubmit">
              <span v-if="loading" class="spinner light"></span>
              {{ loading ? '正在登录…' : '登 录' }}
            </button>
          </form>

          <div class="demo-accounts">
            <p>演示账号（点击自动填充）</p>
            <div class="demo-account-grid">
              <button
                v-for="account in DEMO_ACCOUNTS"
                :key="account.username"
                type="button"
                class="demo-account"
                @click="fill(account)"
              >
                <span class="role-dot" :class="account.username.startsWith('teacher') ? 'purple' : 'green'"></span>
                <span class="demo-main">
                  <strong>{{ account.label }}</strong>
                  <span>{{ account.sub }}</span>
                </span>
                <span class="fill-hint">填充</span>
              </button>
            </div>
          </div>
        </template>

        <template v-else>
          <h2>创建学生账号</h2>
          <p class="login-sub">注册后自动登录并进入学生端，可开始答疑、诊断与练习。</p>

          <form class="login-form" @submit.prevent="submitRegister">
            <div class="form-field">
              <label for="register-username">用户名 <span class="required">*</span></label>
              <input
                id="register-username"
                v-model="registerForm.username"
                class="input"
                type="text"
                autocomplete="username"
                placeholder="4~20 位字母、数字或下划线"
                :disabled="loading"
              />
              <p v-if="fieldErrors.username" class="form-error">{{ fieldErrors.username }}</p>
            </div>
            <div class="form-field">
              <label for="register-display-name">昵称 <span class="required">*</span></label>
              <input
                id="register-display-name"
                v-model="registerForm.displayName"
                class="input"
                type="text"
                autocomplete="nickname"
                placeholder="例如 李同学（1~20 个字符）"
                :disabled="loading"
              />
              <p v-if="fieldErrors.displayName" class="form-error">{{ fieldErrors.displayName }}</p>
            </div>
            <div class="form-field">
              <label for="register-password">密码 <span class="required">*</span></label>
              <input
                id="register-password"
                v-model="registerForm.password"
                class="input"
                type="password"
                autocomplete="new-password"
                placeholder="6~32 位密码"
                :disabled="loading"
              />
              <p v-if="fieldErrors.password" class="form-error">{{ fieldErrors.password }}</p>
            </div>
            <div class="form-field">
              <label for="register-confirm">确认密码 <span class="required">*</span></label>
              <input
                id="register-confirm"
                v-model="registerForm.confirmPassword"
                class="input"
                type="password"
                autocomplete="new-password"
                placeholder="再次输入密码"
                :disabled="loading"
              />
              <p v-if="fieldErrors.confirmPassword" class="form-error">{{ fieldErrors.confirmPassword }}</p>
            </div>

            <p v-if="errorMessage" class="login-error">{{ errorMessage }}</p>

            <button class="btn btn-primary btn-block login-submit" type="submit" :disabled="!canSubmitRegister">
              <span v-if="loading" class="spinner light"></span>
              {{ loading ? '正在注册…' : '注 册' }}
            </button>
          </form>
        </template>

        <p class="login-tip" :class="{ 'text-strong': healthOk }">{{ healthText }}</p>
      </div>
    </section>
  </div>
</template>
