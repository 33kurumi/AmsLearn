<script setup>
import { computed } from 'vue'
import { percentText } from '../utils/format'

const props = defineProps({
  items: { type: Array, default: () => [] },
  labelKey: { type: String, default: 'kpName' },
  valueKey: { type: String, default: 'mastery' },
  suffix: { type: String, default: '' },
  emptyText: { type: String, default: '暂无数据' },
})

const rows = computed(() =>
  (props.items || []).map((item) => {
    const raw = Number(item[props.valueKey]) || 0
    const percent = Math.max(0, Math.min(100, raw * 100))
    let fill = ''
    if (percent < 30) fill = 'red-fill'
    else if (percent < 60) fill = 'orange-fill'
    return {
      key: item.kpId || item.range || item.label || item[props.labelKey],
      label: item[props.labelKey] || item.label || '—',
      extra: item.extra || '',
      percent,
      fill,
      text: props.suffix ? `${percent.toFixed(0)}${props.suffix}` : percentText(raw),
    }
  })
)
</script>

<template>
  <div v-if="rows.length" class="mastery-bars">
    <div v-for="row in rows" :key="row.key" class="knowledge-row">
      <div class="knowledge-label">
        <span>{{ row.label }}<em v-if="row.extra" class="muted"> · {{ row.extra }}</em></span>
        <strong>{{ row.text }}</strong>
      </div>
      <div class="progress-track">
        <div class="progress-fill" :class="row.fill" :style="{ width: row.percent + '%' }"></div>
      </div>
    </div>
  </div>
  <div v-else class="empty-state" style="padding: 24px 10px">
    <p>{{ emptyText }}</p>
  </div>
</template>
