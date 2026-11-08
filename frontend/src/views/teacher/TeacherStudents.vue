<script setup>
/**
 * 学生记录 T7 / T8
 * GET /teacher/students；GET /teacher/students/{studentId}/records（非本班 403）
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { teacher } from '../../api'
import { toast } from '../../toast'
import { RECORD_TYPE_ICON, RECORD_TYPE_LABEL, formatDateTime, percentText, truncate } from '../../utils/format'
import SkeletonBlock from '../../components/SkeletonBlock.vue'
import ErrorState from '../../components/ErrorState.vue'
import EmptyState from '../../components/EmptyState.vue'

const props = defineProps({
  user: { type: Object, required: true },
  navigate: { type: Function, required: true },
})

const students = ref([])
const studentsLoading = ref(true)
const studentsError = ref('')

const selected = ref(null)
const records = ref([])
const recordsLoading = ref(false)
const recordsError = ref('')
const page = ref(1)
const size = ref(10)
const total = ref(0)
const hasNext = ref(false)
const filters = reactive({ type: '' })

const drawerOpen = ref(false)
const drawerRecord = ref(null)

/* v1.4 重置学生密码弹窗 */
const pwdModalOpen = ref(false)
const pwdSaving = ref(false)
const pwdForm = reactive({ newPassword: '', confirmPassword: '' })
const pwdErrors = reactive({ newPassword: '', confirmPassword: '' })
const pwdError = ref('')

const selectedTitle = computed(() => (selected.value ? selected.value.displayName || selected.value.username : ''))

async function loadStudents() {
  studentsLoading.value = true
  studentsError.value = ''
  try {
    const list = await teacher.students()
    students.value = Array.isArray(list) ? list : []
    if (!selected.value && students.value.length) selectStudent(students.value[0])
  } catch (err) {
    studentsError.value = err.message || '学生列表加载失败'
  } finally {
    studentsLoading.value = false
  }
}

function selectStudent(student) {
  selected.value = student
  page.value = 1
  loadRecords(1)
}

async function loadRecords(targetPage = 1) {
  if (!selected.value) return
  recordsLoading.value = true
  recordsError.value = ''
  try {
    const data = await teacher.studentRecords(selected.value.id, {
      type: filters.type || undefined,
      page: targetPage,
      size: size.value,
    })
    const list = (data && data.items) || []
    records.value = list
    page.value = (data && data.page) || targetPage
    total.value = (data && data.total) || list.length
    hasNext.value = !!(data && data.hasNext)
  } catch (err) {
    recordsError.value =
      err.status === 403 ? '该学生不在当前教师班级，无法查看学习记录。' : err.message || '学习记录加载失败'
    records.value = []
  } finally {
    recordsLoading.value = false
  }
}

function openDrawer(item) {
  drawerRecord.value = item
  drawerOpen.value = true
}

function openPasswordModal() {
  if (!selected.value) {
    toast.info('请先在左侧选择一名学生。')
    return
  }
  pwdForm.newPassword = ''
  pwdForm.confirmPassword = ''
  pwdErrors.newPassword = ''
  pwdErrors.confirmPassword = ''
  pwdError.value = ''
  pwdModalOpen.value = true
}

function closePasswordModal() {
  if (pwdSaving.value) return
  pwdModalOpen.value = false
}

function validatePasswordForm() {
  pwdErrors.newPassword = ''
  pwdErrors.confirmPassword = ''
  pwdError.value = ''
  const password = pwdForm.newPassword
  if (!password) pwdErrors.newPassword = '请输入新密码。'
  else if (password.length < 6 || password.length > 32) pwdErrors.newPassword = '密码长度需为 6~32 位。'
  if (!pwdForm.confirmPassword) pwdErrors.confirmPassword = '请再次输入新密码。'
  else if (pwdForm.confirmPassword !== password) pwdErrors.confirmPassword = '两次输入的密码不一致。'
  return !pwdErrors.newPassword && !pwdErrors.confirmPassword
}

async function submitPassword() {
  if (!selected.value || pwdSaving.value) return
  if (!validatePasswordForm()) return
  pwdSaving.value = true
  try {
    await teacher.resetStudentPassword(selected.value.id, pwdForm.newPassword)
    toast.success('密码已重置')
    pwdModalOpen.value = false
  } catch (error) {
    pwdError.value = error.message || '密码重置失败，请稍后重试。'
  } finally {
    pwdSaving.value = false
  }
}

let filterTimer = null
function onTypeChange() {
  if (filterTimer) clearTimeout(filterTimer)
  filterTimer = setTimeout(() => loadRecords(1), 200)
}

onMounted(loadStudents)
</script>

<template>
  <div>
    <div class="module-intro">
      <p class="eyebrow">学生记录 · STUDENT RECORDS</p>
      <h1>本班学生学习轨迹</h1>
      <p>查看每位学生的答疑、诊断、练习与计划记录，定位需要重点关注的学生。</p>
    </div>

    <SkeletonBlock v-if="studentsLoading" :rows="4" :cards="3" />
    <ErrorState
      v-else-if="studentsError"
      title="学生列表加载失败"
      :message="studentsError"
      hint="请确认业务服务已启动，并使用教师账号登录。"
      @retry="loadStudents"
    />
    <div v-else class="config-layout">
      <aside class="panel" style="height: fit-content">
        <div class="panel-heading"><div><h3>本班学生</h3><p>共 {{ students.length }} 人</p></div></div>
        <div v-if="students.length">
          <button
            v-for="student in students"
            :key="student.id"
            type="button"
            class="plan-list-item"
            :class="{ active: selected && selected.id === student.id }"
            style="width: 100%; text-align: left; cursor: pointer"
            @click="selectStudent(student)"
          >
            <div class="flex-between">
              <strong style="font-size: 13px">{{ student.displayName }}</strong>
              <span class="tag" :class="(Number(student.mastery) || 0) < 0.3 ? 'red' : (Number(student.mastery) || 0) < 0.7 ? 'orange' : 'green'">
                {{ percentText(student.mastery) }}
              </span>
            </div>
            <div class="muted" style="font-size: 11px; margin-top: 4px">
              薄弱 {{ student.weakCount || 0 }} 个 · 互动 {{ student.interactionCount || 0 }} 次
            </div>
            <div class="muted" style="font-size: 10px; margin-top: 2px">
              最近活跃：{{ formatDateTime(student.lastActiveAt) }}
            </div>
          </button>
        </div>
        <EmptyState v-else icon="◎" title="暂无学生" description="班级还没有学生加入。" />
      </aside>

      <section class="panel">
        <div class="panel-heading">
          <div>
            <h3>{{ selectedTitle || '学习记录' }}</h3>
            <p v-if="selected">
              {{ selected.username }} · 掌握度 {{ percentText(selected.mastery) }} · 薄弱 {{ selected.weakCount || 0 }} 个知识点
            </p>
          </div>
          <div class="flex-row">
            <button class="btn btn-outline btn-sm" :disabled="!selected || recordsLoading" @click="openPasswordModal">
              重置密码
            </button>
            <select v-model="filters.type" class="select" style="width: 140px" @change="onTypeChange">
              <option value="">全部类型</option>
              <option value="QA">答疑</option>
              <option value="DIAGNOSIS">诊断</option>
              <option value="PRACTICE">练习</option>
              <option value="PLAN">计划</option>
            </select>
          </div>
        </div>

        <SkeletonBlock v-if="recordsLoading" :show-cards="false" :rows="6" />
        <ErrorState
          v-else-if="recordsError"
          :message="recordsError"
          hint="若提示非本班学生，请切换到该学生所在班级的教师账号再试。"
          :show-cards="false"
          @retry="loadRecords(page)"
        />
        <template v-else-if="records.length">
          <div v-for="item in records" :key="item.id" class="record-item" @click="openDrawer(item)">
            <div class="record-icon">{{ RECORD_TYPE_ICON[item.type] || '✳' }}</div>
            <div class="record-main">
              <div class="flex-between">
                <span class="tag gray">{{ RECORD_TYPE_LABEL[item.type] || item.type }}</span>
                <span class="record-time">{{ formatDateTime(item.createdAt) }}</span>
              </div>
              <p class="record-snippet" style="margin: 6px 0 0">{{ truncate(item.userMessage, 120) }}</p>
              <p v-if="item.aiResponse" class="record-snippet muted" style="margin: 4px 0 0; font-size: 12px">
                {{ truncate(item.aiResponse, 90) }}
              </p>
              <div class="record-meta">
                <span v-if="item.blocked" class="tag red">超范围拦截</span>
                <span v-for="name in (item.kpNames || []).slice(0, 3)" :key="name" class="tag green">{{ name }}</span>
                <span v-if="(item.sources || []).length" class="tag purple">来源 {{ item.sources.length }} 条</span>
              </div>
            </div>
          </div>

          <div class="pager">
            <span class="muted">第 {{ page }} 页 · 共 {{ total }} 条</span>
            <div class="pager-actions">
              <button class="btn btn-ghost btn-sm" :disabled="page <= 1 || recordsLoading" @click="loadRecords(page - 1)">上一页</button>
              <button class="btn btn-ghost btn-sm" :disabled="!hasNext || recordsLoading" @click="loadRecords(page + 1)">下一页</button>
            </div>
          </div>
        </template>
        <EmptyState
          v-else
          icon="▤"
          title="暂无学习记录"
          description="该学生在当前筛选条件下没有记录。"
        />
      </section>
    </div>

    <div v-if="drawerOpen" class="mask" @click.self="drawerOpen = false">
      <div class="drawer">
        <div class="drawer-header">
          <div>
            <h3>学习记录详情</h3>
            <p v-if="drawerRecord">{{ RECORD_TYPE_LABEL[drawerRecord.type] || drawerRecord.type }} · {{ formatDateTime(drawerRecord.createdAt) }}</p>
          </div>
          <button class="drawer-close" @click="drawerOpen = false">✕</button>
        </div>
        <div v-if="drawerRecord" class="drawer-body">
          <div class="detail-block">
            <h4>学生提问</h4>
            <p style="white-space: pre-wrap; line-height: 1.8">{{ drawerRecord.userMessage || '—' }}</p>
          </div>
          <div class="detail-block">
            <h4>AI 回答</h4>
            <p style="white-space: pre-wrap; line-height: 1.8">{{ drawerRecord.aiResponse || '—' }}</p>
          </div>
          <div v-if="drawerRecord.blocked" class="alert alert-warn">
            该提问被教学边界拦截：{{ drawerRecord.blockReason || '超出当前教学范围' }}
          </div>
          <div v-if="(drawerRecord.kpNames || []).length" class="detail-block">
            <h4>涉及知识点</h4>
            <div>
              <span v-for="name in drawerRecord.kpNames" :key="name" class="tag green" style="margin: 0 6px 6px 0">{{ name }}</span>
            </div>
          </div>
          <div v-if="(drawerRecord.sources || []).length" class="detail-block">
            <h4>知识库来源</h4>
            <div v-for="(source, index) in drawerRecord.sources" :key="index" class="source-card">
              <div class="doc-name">{{ source.title || source.documentId }}</div>
              <p v-if="source.excerpt">{{ truncate(source.excerpt, 200) }}</p>
            </div>
          </div>
        </div>
        <div class="drawer-footer">
          <button class="btn btn-outline" @click="drawerOpen = false">关闭</button>
        </div>
      </div>
    </div>

    <div v-if="pwdModalOpen" class="mask" @click.self="closePasswordModal">
      <div class="modal-card">
        <div class="modal-head">
          <div>
            <h3>重置学生密码</h3>
            <p v-if="selected">{{ selectedTitle }} · {{ selected.username }}</p>
          </div>
          <button class="drawer-close" :disabled="pwdSaving" @click="closePasswordModal">✕</button>
        </div>
        <div class="modal-body">
          <div class="form-field">
            <label for="reset-new-password">新密码 <span class="required">*</span></label>
            <input
              id="reset-new-password"
              v-model="pwdForm.newPassword"
              class="input"
              type="password"
              autocomplete="new-password"
              placeholder="6~32 位密码"
              :disabled="pwdSaving"
            />
            <p v-if="pwdErrors.newPassword" class="form-error">{{ pwdErrors.newPassword }}</p>
          </div>
          <div class="form-field">
            <label for="reset-confirm-password">确认新密码 <span class="required">*</span></label>
            <input
              id="reset-confirm-password"
              v-model="pwdForm.confirmPassword"
              class="input"
              type="password"
              autocomplete="new-password"
              placeholder="再次输入新密码"
              :disabled="pwdSaving"
              @keyup.enter="submitPassword"
            />
            <p v-if="pwdErrors.confirmPassword" class="form-error">{{ pwdErrors.confirmPassword }}</p>
          </div>
          <p v-if="pwdError" class="login-error">{{ pwdError }}</p>
          <p class="form-hint">重置后请通知学生使用新密码登录；仅可重置本班学生密码。</p>
        </div>
        <div class="modal-foot">
          <button class="btn btn-outline" :disabled="pwdSaving" @click="closePasswordModal">取消</button>
          <button class="btn btn-primary" :disabled="pwdSaving" @click="submitPassword">
            <span v-if="pwdSaving" class="spinner light"></span>
            {{ pwdSaving ? '正在重置…' : '确认重置' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
