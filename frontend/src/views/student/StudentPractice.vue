<script setup>
/**
 * 分层练习 S12 / S13
 * POST /practice/generate {layer, count, kpIds} 出题；
 * POST /practice/hint {batchId, questionId, studentAnswer} 获取解题思路（只给思路不给答案）。
 */
import { onMounted, reactive, ref } from 'vue'
import { common, student } from '../../api'
import { toast } from '../../toast'
import { KB_LABEL, LAYER_META, percentText } from '../../utils/format'
import SkeletonBlock from '../../components/SkeletonBlock.vue'
import EmptyState from '../../components/EmptyState.vue'
import MarkdownView from '../../components/MarkdownView.vue'

const props = defineProps({
  user: { type: Object, required: true },
  navigate: { type: Function, required: true },
})

const layer = ref('A')
const count = ref(3)
const kpIds = ref([])
const knowledgePoints = ref([])
const kpLoading = ref(false)

const generating = ref(false)
const genError = ref('')
const batch = ref(null)
const hints = reactive({})
const hintLoading = reactive({})
const hintError = reactive({})
const draftAnswers = reactive({})

const COUNT_OPTIONS = [3, 5, 10]

async function loadKnowledgePoints() {
  kpLoading.value = true
  try {
    knowledgePoints.value = (await common.knowledgePoints()) || []
  } catch {
    knowledgePoints.value = []
  } finally {
    kpLoading.value = false
  }
}

onMounted(loadKnowledgePoints)

function toggleKp(kpId) {
  const index = kpIds.value.indexOf(kpId)
  if (index >= 0) kpIds.value.splice(index, 1)
  else kpIds.value.push(kpId)
}

async function generate() {
  if (generating.value) return
  genError.value = ''
  generating.value = true
  try {
    const data = await student.practiceGenerate({
      layer: layer.value,
      count: Number(count.value),
      kpIds: kpIds.value.slice(),
    })
    if (!data || !Array.isArray(data.questions) || !data.questions.length) {
      throw new Error('练习接口未返回题目，请检查 AI 服务是否正常。')
    }
    batch.value = data
    Object.keys(hints).forEach((key) => delete hints[key])
    Object.keys(hintError).forEach((key) => delete hintError[key])
    Object.keys(draftAnswers).forEach((key) => delete draftAnswers[key])
    toast.success(`已生成 ${data.questions.length} 道 ${layer.value} 层练习题`)
  } catch (error) {
    genError.value =
      error.code === 'TIMEOUT' ? '出题超时（已等待 90 秒），请重试或减少题目数量。' : error.message || '出题失败'
  } finally {
    generating.value = false
  }
}

async function loadHint(question) {
  if (!batch.value || hintLoading[question.questionId]) return
  hintLoading[question.questionId] = true
  hintError[question.questionId] = ''
  try {
    const data = await student.practiceHint({
      batchId: batch.value.batchId,
      questionId: question.questionId,
      studentAnswer: String(draftAnswers[question.questionId] || ''),
    })
    hints[question.questionId] = data
  } catch (error) {
    hintError[question.questionId] =
      error.code === 'TIMEOUT' ? '思路生成超时（90 秒），请重试。' : error.message || '获取思路失败'
  } finally {
    hintLoading[question.questionId] = false
  }
}

function optionList(question) {
  if (question && Array.isArray(question.options) && question.options.length) return question.options
  if (question && question.type === 'JUDGE') {
    return [
      { key: 'A', text: '正确' },
      { key: 'B', text: '错误' },
    ]
  }
  return []
}

function qid(question, index) {
  return question.questionId || question.id || `q-${index}`
}
</script>

<template>
  <div>
    <div class="module-intro">
      <p class="eyebrow">分层练习 · PRACTICE</p>
      <h1>按层练习，逐步进阶</h1>
      <p>选择 A / B / C 层与知识点生成练习题；「查看思路」只提供解题方向与策略，不直接给出答案。</p>
    </div>

    <section class="panel">
      <div class="panel-heading">
        <div><h3>练习配置</h3><p>难度由层决定：A 基础、B 提升、C 拓展</p></div>
        <span class="tag green">AI 出题</span>
      </div>

      <div class="layer-grid">
        <button
          v-for="(meta, key) in LAYER_META"
          :key="key"
          type="button"
          class="layer-card"
          :class="{ selected: layer === key }"
          @click="layer = key"
        >
          <strong>{{ meta.label }}</strong>
          <span>{{ meta.desc }}</span>
        </button>
      </div>

      <div class="form-grid cols-3" style="margin-top: 18px">
        <div class="form-field">
          <label>题目数量</label>
          <select v-model.number="count" class="select">
            <option v-for="option in COUNT_OPTIONS" :key="option" :value="option">{{ option }} 道</option>
          </select>
        </div>
        <div class="form-field full">
          <label>知识点范围（可多选，不选则由系统按掌握度挑选）</label>
          <div v-if="kpLoading" class="loading-inline"><span class="spinner"></span> 正在加载知识点…</div>
          <div v-else class="chip-group kp-picker">
            <button
              v-for="kp in knowledgePoints"
              :key="kp.kpId"
              type="button"
              class="chip"
              :class="{ selected: kpIds.includes(kp.kpId) }"
              :title="kp.chapter"
              @click="toggleKp(kp.kpId)"
            >
              {{ kp.kpName }} <span class="muted">{{ percentText(kp.mastery) }}</span>
            </button>
          </div>
        </div>
      </div>

      <div v-if="genError" class="alert alert-error" style="margin-top: 14px">{{ genError }}</div>

      <div class="exam-actions">
        <button class="btn btn-primary" :disabled="generating" @click="generate">
          <span v-if="generating" class="spinner light"></span>
          {{ generating ? 'AI 正在出题（最长 90 秒）…' : batch ? '重新生成题目' : '生成练习题' }}
        </button>
        <button v-if="batch" class="btn btn-outline" :disabled="generating" @click="generate">换一批</button>
      </div>
    </section>

    <SkeletonBlock v-if="generating" :show-cards="false" :rows="6" />

    <template v-else-if="batch">
      <div class="alert alert-info" style="margin-bottom: 14px">
        <strong>{{ LAYER_META[batch.layer] ? LAYER_META[batch.layer].label : batch.layer + ' 层' }}</strong>
        · {{ (batch.kpNames || []).join('、') || '综合练习' }}
        <span v-if="batch.guidance"> · {{ batch.guidance }}</span>
      </div>

      <article v-for="(question, index) in batch.questions" :key="qid(question, index)" class="practice-card">
        <div class="question-head">
          <span class="question-index">{{ index + 1 }}</span>
          <div class="flex-row" style="gap: 8px; flex-wrap: wrap">
            <span class="tag green">{{ question.kpName || question.kpId || '综合' }}</span>
            <span class="tag gray">难度 {{ question.difficulty }}</span>
            <span class="tag purple">{{ question.type === 'SINGLE' ? '单选' : question.type === 'JUDGE' ? '判断' : question.type === 'FILL' ? '填空' : '题目' }}</span>
          </div>
        </div>

        <div class="question-stem">
          <MarkdownView :content="question.stem || question.questionText || ''" />
        </div>

        <div v-if="optionList(question).length" class="option-list">
          <div v-for="option in optionList(question)" :key="option.key" class="option-item" style="cursor: default">
            <span class="option-key">{{ option.key }}</span>
            <span>{{ option.text }}</span>
          </div>
        </div>

        <div class="form-field" style="margin-top: 14px">
          <label>我的思路 / 答案（可选，提交后思路会更贴合你的做法）</label>
          <input v-model="draftAnswers[question.questionId]" class="input" placeholder="写下你的解法或答案，再查看思路" />
        </div>

        <div v-if="hints[question.questionId]" class="practice-hint">
          <h5>解题思路</h5>
          <span v-if="hints[question.questionId].strategy" class="strategy">
            策略：{{ hints[question.questionId].strategy }}
          </span>
          <MarkdownView :content="hints[question.questionId].hint || '暂无思路内容'" />
          <details v-if="(hints[question.questionId].sources || []).length" class="sources">
            <summary>参考资料（{{ hints[question.questionId].sources.length }}）</summary>
            <div v-for="(source, sourceIndex) in hints[question.questionId].sources" :key="sourceIndex" class="source-card">
              <div class="source-title">
                {{ source.title || '知识库文档' }}
                <span>{{ KB_LABEL[source.kb] || source.kb || '知识库' }}</span>
              </div>
              <p>{{ source.excerpt || '' }}</p>
            </div>
          </details>
        </div>

        <div v-if="hintError[question.questionId]" class="alert alert-error" style="margin-top: 12px">
          {{ hintError[question.questionId] }}
        </div>

        <div class="flex-between" style="margin-top: 14px">
          <button
            class="btn btn-outline btn-sm"
            :disabled="!!hintLoading[question.questionId]"
            @click="loadHint(question)"
          >
            <span v-if="hintLoading[question.questionId]" class="spinner"></span>
            {{ hintLoading[question.questionId] ? '正在生成思路…' : hints[question.questionId] ? '重新获取思路' : '查看思路' }}
          </button>
          <span class="muted" style="font-size: 11px">提示不直接给出答案，请先独立尝试</span>
        </div>
      </article>

      <EmptyState
        v-if="!batch.questions || !batch.questions.length"
        icon="✎"
        title="本批没有题目"
        description="请调整层或知识点范围后重新生成。"
      />
    </template>

    <EmptyState
      v-else
      icon="✎"
      title="还没有练习题"
      description="选择层与知识点后点击「生成练习题」，AI 会为你组一份分层练习。"
    />
  </div>
</template>

<style scoped>
.kp-picker { display: flex; flex-wrap: wrap; gap: 8px; max-height: 200px; overflow-y: auto; }
</style>
