<script setup>
/**
 * 个人信息 A5 / A4
 * PUT /users/me 更新资料；PUT /auth/password 修改密码。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { auth, student } from '../../api'
import { toast } from '../../toast'
import { percentText } from '../../utils/format'
import AiModelSettings from '../../components/AiModelSettings.vue'

const props = defineProps({
  user: { type: Object, required: true },
  navigate: { type: Function, required: true },
})
const emit = defineEmits(['refresh-health'])

const profile = reactive({
  displayName: '',
  email: '',
  phone: '',
  targetSchool: '',
  examYear: '',
})
const savedProfile = ref({ ...profile })
const profileSaving = ref(false)
const profileError = ref('')
const profileLoaded = ref(false)
const mastery = ref(null)

const password = reactive({ oldPassword: '', newPassword: '', confirmPassword: '' })
const passwordSaving = ref(false)
const passwordError = ref('')

const profileDirty = computed(() => JSON.stringify(profile) !== JSON.stringify(savedProfile.value))
const passwordValid = computed(
  () => password.oldPassword && password.newPassword && password.newPassword === password.confirmPassword
)

function assignProfile(source) {
  const next = {
    displayName: (source && source.displayName) || '',
    email: (source && source.email) || '',
    phone: (source && source.phone) || '',
    targetSchool: (source && source.targetSchool) || '',
    examYear: (source && source.examYear) || '',
  }
  Object.assign(profile, next)
  savedProfile.value = { ...next }
}

onMounted(async () => {
  try {
    const fresh = await auth.me()
    assignProfile(fresh || props.user)
  } catch {
    assignProfile(props.user)
  } finally {
    profileLoaded.value = true
  }
  try {
    const dashboard = await student.dashboard()
    if (dashboard && dashboard.mastery) mastery.value = dashboard.mastery.avg
  } catch {
    /* 概览接口未就绪时，掌握度显示为 — */
  }
})

async function saveProfile() {
  if (profileSaving.value || !profileDirty.value) return
  profileError.value = ''
  if (!profile.displayName.trim()) {
    profileError.value = '昵称不能为空。'
    return
  }
  if (profile.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(profile.email)) {
    profileError.value = '邮箱格式不正确。'
    return
  }
  if (profile.phone && !/^1\d{10}$/.test(profile.phone)) {
    profileError.value = '手机号格式不正确（11 位数字）。'
    return
  }
  profileSaving.value = true
  try {
    const updated = await auth.updateProfile({
      displayName: profile.displayName.trim(),
      email: profile.email.trim(),
      phone: profile.phone.trim(),
      targetSchool: profile.targetSchool.trim(),
      examYear: profile.examYear ? Number(profile.examYear) : null,
    })
    if (updated) {
      assignProfile(updated)
      toast.success('个人资料已保存')
    } else {
      assignProfile({ ...profile })
      toast.success('个人资料已保存')
    }
  } catch (err) {
    profileError.value = err.message || '保存失败'
  } finally {
    profileSaving.value = false
  }
}

async function changePassword() {
  if (passwordSaving.value) return
  passwordError.value = ''
  if (!password.oldPassword || !password.newPassword) {
    passwordError.value = '请填写原密码与新密码。'
    return
  }
  if (password.newPassword.length < 6) {
    passwordError.value = '新密码长度不能少于 6 位。'
    return
  }
  if (password.newPassword !== password.confirmPassword) {
    passwordError.value = '两次输入的新密码不一致。'
    return
  }
  passwordSaving.value = true
  try {
    await auth.changePassword(password.oldPassword, password.newPassword)
    password.oldPassword = ''
    password.newPassword = ''
    password.confirmPassword = ''
    toast.success('密码修改成功，下次登录请使用新密码')
  } catch (err) {
    passwordError.value = err.message || '密码修改失败'
  } finally {
    passwordSaving.value = false
  }
}

function resetForm() {
  assignProfile(savedProfile.value)
  profileError.value = ''
}
</script>

<template>
  <div>
    <div class="module-intro">
      <p class="eyebrow">个人信息 · PROFILE</p>
      <h1>账号与资料</h1>
      <p>维护个人资料与目标院校信息，学习报告会使用这些信息做针对性建议。</p>
    </div>

    <div class="profile-grid">
      <div>
        <section class="panel" style="margin-bottom: 16px">
          <div class="panel-heading">
            <div><h3>基本资料</h3><p>修改后点击保存，立即生效</p></div>
            <span class="tag gray">账号 {{ user.username }}</span>
          </div>
          <div v-if="profileError" class="alert alert-error" style="margin-bottom: 14px">{{ profileError }}</div>
          <div class="form-grid">
            <div class="form-field">
              <label>昵称 <span class="required">*</span></label>
              <input v-model="profile.displayName" class="input" maxlength="20" :disabled="profileSaving" />
            </div>
            <div class="form-field">
              <label>邮箱</label>
              <input v-model="profile.email" class="input" type="email" placeholder="name@example.com" :disabled="profileSaving" />
            </div>
            <div class="form-field">
              <label>手机号</label>
              <input v-model="profile.phone" class="input" maxlength="11" placeholder="11 位手机号" :disabled="profileSaving" />
            </div>
            <div class="form-field">
              <label>目标院校</label>
              <input v-model="profile.targetSchool" class="input" placeholder="例如：华东师范大学" :disabled="profileSaving" />
            </div>
            <div class="form-field">
              <label>考研年份</label>
              <input v-model="profile.examYear" class="input" type="number" min="2024" max="2100" placeholder="例如 2027" :disabled="profileSaving" />
            </div>
          </div>
          <div class="exam-actions">
            <button class="btn btn-primary" :disabled="profileSaving || !profileDirty" @click="saveProfile">
              <span v-if="profileSaving" class="spinner light"></span>
              {{ profileSaving ? '保存中…' : '保存资料' }}
            </button>
            <button class="btn btn-outline" :disabled="!profileDirty || profileSaving" @click="resetForm">撤销修改</button>
          </div>
        </section>

        <section class="panel">
          <div class="panel-heading">
            <div><h3>修改密码</h3><p>修改成功后当前登录态仍然有效</p></div>
          </div>
          <div v-if="passwordError" class="alert alert-error" style="margin-bottom: 14px">{{ passwordError }}</div>
          <div class="form-grid">
            <div class="form-field full">
              <label>原密码 <span class="required">*</span></label>
              <input v-model="password.oldPassword" class="input" type="password" autocomplete="current-password" :disabled="passwordSaving" />
            </div>
            <div class="form-field">
              <label>新密码 <span class="required">*</span></label>
              <input v-model="password.newPassword" class="input" type="password" autocomplete="new-password" :disabled="passwordSaving" />
              <span class="form-hint">至少 6 位</span>
            </div>
            <div class="form-field">
              <label>确认新密码 <span class="required">*</span></label>
              <input v-model="password.confirmPassword" class="input" type="password" autocomplete="new-password" :disabled="passwordSaving" />
            </div>
          </div>
          <div class="exam-actions">
            <button class="btn btn-primary" :disabled="passwordSaving || !passwordValid" @click="changePassword">
              <span v-if="passwordSaving" class="spinner light"></span>
              {{ passwordSaving ? '提交中…' : '修改密码' }}
            </button>
          </div>
        </section>

        <AiModelSettings @refresh-health="emit('refresh-health')" />
      </div>

      <section class="profile-card">
        <div class="profile-avatar">{{ (user.displayName || user.username || '知').slice(0, 1) }}</div>
        <h3>{{ user.displayName || user.username }}</h3>
        <p>{{ user.className || '高等数学' }} · {{ user.subject || '数学' }}</p>
        <div class="profile-facts">
          <div class="profile-fact"><span>学号 / 用户名</span><strong>{{ user.username }}</strong></div>
          <div class="profile-fact"><span>班级</span><strong>{{ user.className || '—' }}（{{ user.classId || '—' }}）</strong></div>
          <div class="profile-fact"><span>目标院校</span><strong>{{ profile.targetSchool || '未设置' }}</strong></div>
          <div class="profile-fact"><span>考研年份</span><strong>{{ profile.examYear || '未设置' }}</strong></div>
          <div class="profile-fact"><span>掌握度均值</span><strong>{{ mastery !== null ? percentText(mastery) : '—' }}</strong></div>
        </div>
        <div class="alert alert-info" style="margin-top: 14px">
          资料仅用于生成学习建议与报告展示，不会公开展示给其他同学。
        </div>
      </section>
    </div>
  </div>
</template>
