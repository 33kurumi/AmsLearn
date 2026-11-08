<script setup>
/**
 * App.vue —— 应用外壳
 * 不使用 vue-router：负责登录态（localStorage.ams_token / ams_user）、角色导航与页面切换。
 * 学生端 8 个页面、教师端 5 个页面；页面组件通过 props 接收 user 与 navigate。
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { auth, clearAuth, common, getStoredUser, getToken, saveAuth, saveUser, setUnauthorizedHandler } from './api'
import { toast } from './toast'
import { todayText } from './utils/format'
import { readAiStatus } from './utils/aiMode'
import ToastHost from './components/ToastHost.vue'
import LoginView from './views/LoginView.vue'
import StudentHome from './views/student/StudentHome.vue'
import StudentTutor from './views/student/StudentTutor.vue'
import StudentDiagnose from './views/student/StudentDiagnose.vue'
import StudentPlan from './views/student/StudentPlan.vue'
import StudentPractice from './views/student/StudentPractice.vue'
import StudentRecords from './views/student/StudentRecords.vue'
import StudentWrong from './views/student/StudentWrong.vue'
import StudentProfile from './views/student/StudentProfile.vue'
import TeacherHome from './views/teacher/TeacherHome.vue'
import TeacherConfig from './views/teacher/TeacherConfig.vue'
import TeacherAnalysis from './views/teacher/TeacherAnalysis.vue'
import TeacherKnowledge from './views/teacher/TeacherKnowledge.vue'
import TeacherStudents from './views/teacher/TeacherStudents.vue'
import TeacherProfile from './views/teacher/TeacherProfile.vue'

const STUDENT_NAV = [
  { key: 'home', label: '首页概览', icon: '⌂', desc: '掌握度、统计与当前计划' },
  { key: 'tutor', label: '答疑辅导', icon: '✳', desc: 'AI 智能答疑 · 知识库溯源' },
  { key: 'diagnose', label: '知识诊断', icon: '▥', desc: '快速 / 全面诊断与报告' },
  { key: 'plan', label: '学习计划', icon: '▤', desc: '每日学习 · 练习 · 复盘' },
  { key: 'practice', label: '分层练习', icon: '✎', desc: 'A / B / C 分层出题' },
  { key: 'records', label: '学习记录', icon: '◷', desc: '答疑、诊断、练习记录' },
  { key: 'wrong', label: '错题复盘', icon: '⚑', desc: '错因分析与复盘标记' },
  { key: 'profile', label: '个人信息', icon: '☺', desc: '资料、密码与 AI 模型设置' },
]

const TEACHER_NAV = [
  { key: 'home', label: '学情总览', icon: '⌂', desc: '班级规模、掌握度与动态' },
  { key: 'config', label: '班级配置', icon: '⚙', desc: '回答模式、范围与边界规则' },
  { key: 'analysis', label: '班级学情', icon: '▥', desc: '7D / 30D / 学期分析' },
  { key: 'knowledge', label: '知识库管理', icon: '▤', desc: '文档上传、启停与重建索引' },
  { key: 'students', label: '学生记录', icon: '☺', desc: '学生列表与个人记录' },
  { key: 'profile', label: '个人信息', icon: '✿', desc: '资料、密码与 AI 模型设置' },
]

const PAGE_COMPONENTS = {
  home: null,
  tutor: StudentTutor,
  diagnose: StudentDiagnose,
  plan: StudentPlan,
  practice: StudentPractice,
  records: StudentRecords,
  wrong: StudentWrong,
  profile: StudentProfile,
}

const TEACHER_COMPONENTS = {
  home: TeacherHome,
  config: TeacherConfig,
  analysis: TeacherAnalysis,
  knowledge: TeacherKnowledge,
  students: TeacherStudents,
  profile: TeacherProfile,
}

const user = ref(getStoredUser())
const page = ref('home')
const pageParams = ref({})
const health = ref(null)
const healthLoading = ref(false)
/** 当前登录用户的个人 AI 配置（GET /api/profile/ai）；用于顶栏徽标显示「我的 Key」 */
const userAiConfig = ref(null)
const isStudent = computed(() => (user.value && user.value.role) === 'STUDENT')
const isTeacher = computed(() => (user.value && user.value.role) === 'TEACHER')
const navItems = computed(() => (isTeacher.value ? TEACHER_NAV : STUDENT_NAV))
const currentNav = computed(() => navItems.value.find((item) => item.key === page.value) || navItems.value[0])
const currentComponent = computed(() => {
  if (isTeacher.value) return TEACHER_COMPONENTS[page.value] || TeacherHome
  if (page.value === 'home') return StudentHome
  return PAGE_COMPONENTS[page.value] || StudentHome
})
const today = todayText()

/** 顶栏 AI 模式徽标：real（系统 Key / 我的 Key）或 mock；个人 Key 生效时优先显示「我的 Key」 */
const aiStatus = computed(() => readAiStatus(health.value, userAiConfig.value))

/** 仅答疑页需要携带会话 id 作为组件 props，其余页面不传 */
const pageProps = computed(() =>
  page.value === 'tutor' ? { initialConversationId: pageParams.value.conversationId ?? null } : {}
)

function displayInitial(name) {
  return String(name || '知').slice(0, 1)
}

function navigate(nextPage, params = {}) {
  if (!navItems.value.some((item) => item.key === nextPage)) return
  pageParams.value = params && typeof params === 'object' ? params : {}
  page.value = nextPage
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

function handleLoggedIn(payload) {
  user.value = payload.user
  saveAuth(payload.token, payload.user)
  page.value = 'home'
  pageParams.value = {}
  toast.success(`欢迎回来，${payload.user.displayName || payload.user.username}`)
  loadHealth()
  loadUserAiConfig()
}

function switchRole(nextRole) {
  if (!user.value) return
  if ((nextRole === 'TEACHER' && isTeacher.value) || (nextRole === 'STUDENT' && isStudent.value)) return
  toast.info(
    nextRole === 'TEACHER'
      ? '教师端请退出后使用演示账号 teacher1 / 123456 登录。'
      : '学生端请退出后使用演示账号 student1 / 123456 登录。'
  )
}

async function handleLogout() {
  try {
    await auth.logout()
  } catch (error) {
    /* 退出接口失败也继续本地清理 */
  }
  clearAuth()
  user.value = null
  page.value = 'home'
  pageParams.value = {}
  health.value = null
  userAiConfig.value = null
  toast.info('已退出登录')
}

async function refreshUser() {
  try {
    const fresh = await auth.me()
    if (fresh) {
      user.value = fresh
      saveUser(fresh)
    }
  } catch (error) {
    if (error.code !== 'UNAUTHORIZED') {
      /* 后端未启动时保留本地登录态，页面内部展示友好错误 */
    }
  }
}

async function loadHealth() {
  if (!getToken()) return
  healthLoading.value = true
  try {
    health.value = await common.health()
  } catch {
    health.value = { status: 'DOWN', java: 'UNKNOWN', ai: 'UNKNOWN', mode: 'UNKNOWN' }
  } finally {
    healthLoading.value = false
  }
}

/** 拉取个人 AI 配置：用于顶栏徽标判断 Key 来源；接口 404/网络失败时静默保持 health 现状 */
async function loadUserAiConfig() {
  if (!getToken()) {
    userAiConfig.value = null
    return
  }
  try {
    userAiConfig.value = await auth.aiConfig()
  } catch {
    /* /profile/ai 未实现（404）或暂时不可用时保持 health 的默认展示 */
    userAiConfig.value = null
  }
}

/** 个人信息页保存/清除 Key 后刷新 health 与个人配置，让顶栏徽标立即更新 */
function refreshAiStatus() {
  loadHealth()
  loadUserAiConfig()
}

let healthTimer = null

onMounted(() => {
  setUnauthorizedHandler((message) => {
    user.value = null
    page.value = 'home'
    toast.error(message || '登录状态已过期，请重新登录。')
  })
  if (getToken()) {
    refreshUser()
    loadHealth()
    loadUserAiConfig()
    healthTimer = setInterval(loadHealth, 60000)
  }
})

onBeforeUnmount(() => {
  if (healthTimer) clearInterval(healthTimer)
})

const healthLabel = computed(() => {
  if (!health.value) return healthLoading.value ? '连接中…' : '未连接'
  if (health.value.status === 'UP') return '服务已连接'
  return '服务不可用'
})
const healthWarn = computed(() => !health.value || health.value.status !== 'UP')
</script>

<template>
  <ToastHost />
  <LoginView v-if="!user" @logged-in="handleLoggedIn" />

  <div v-else class="app-shell">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-icon">知</div>
        <div>
          <div class="brand-name">知学 AI</div>
          <div class="brand-subtitle">PERSONAL LEARNING TUTOR</div>
        </div>
      </div>

      <p class="role-label">当前角色</p>
      <div class="role-switch">
        <button :class="{ selected: isStudent }" @click="switchRole('STUDENT')">学生端</button>
        <button :class="{ selected: isTeacher }" @click="switchRole('TEACHER')">教师端</button>
      </div>

      <p class="nav-label">功能导航</p>
      <nav class="navigation">
        <button
          v-for="item in navItems"
          :key="item.key"
          class="nav-item"
          :class="{ active: page === item.key }"
          :title="item.desc"
          @click="navigate(item.key)"
        >
          <span class="nav-icon">{{ item.icon }}</span>
          <span>{{ item.label }}</span>
          <span v-if="page === item.key" class="active-dot"></span>
        </button>
      </nav>

      <div class="sidebar-tip">
        <div class="tip-icon">✦</div>
        <div class="tip-title">{{ isTeacher ? '教学督导提示' : 'AI 学习提示' }}</div>
        <p>
          {{ isTeacher ? '班级配置调整后立即生效，可在变更记录中追溯。' : '先诊断掌握度，再生成计划，练习与答疑会更有针对性。' }}
        </p>
        <button @click="navigate(isTeacher ? 'config' : 'diagnose')">
          {{ isTeacher ? '去调整班级配置 →' : '去做一次诊断 →' }}
        </button>
      </div>

      <div class="sidebar-footer">
        <div class="avatar">{{ displayInitial(user.displayName || user.username) }}</div>
        <div class="profile-text">
          <strong>{{ user.displayName || user.username }}</strong>
          <span>{{ isTeacher ? (user.subject || '数学') + '教师' : user.className || '高等数学' }}</span>
        </div>
        <button class="sidebar-logout" title="退出登录" @click="handleLogout">退出</button>
      </div>
    </aside>

    <div class="main-area">
      <header class="topbar">
        <div class="breadcrumb">
          <span>{{ isTeacher ? '教师端' : '学生端' }}</span>
          <span class="crumb-divider">/</span>
          <strong>{{ currentNav.label }}</strong>
          <span class="muted" style="margin-left: 10px">{{ currentNav.desc }}</span>
        </div>
        <div class="topbar-right">
          <span class="today-label">{{ today }}</span>
          <span class="ai-badge" :class="aiStatus.tone" :title="aiStatus.detail">
            <i class="dot"></i>{{ aiStatus.label }}
          </span>
          <span class="health-pill" :class="{ warn: healthWarn }" :title="health ? `Java: ${health.java} · AI: ${health.ai}` : '未获取服务状态'">
            <i class="dot"></i>{{ healthLabel }}
          </span>
          <div class="top-avatar">{{ displayInitial(user.displayName || user.username) }}</div>
        </div>
      </header>

      <main class="page-content">
        <component
          :is="currentComponent"
          :key="page + ':' + (pageParams.conversationId ?? '')"
          v-bind="pageProps"
          :user="user"
          :navigate="navigate"
          :health="health"
          @logout="handleLogout"
          @refresh-health="refreshAiStatus"
        />
      </main>

      <footer class="page-footer">
        知学 AI · 个性化学习导师（高等数学考研辅导） · 数据来自智能学习服务
      </footer>
    </div>
  </div>
</template>
