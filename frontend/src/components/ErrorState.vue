<script setup>
defineProps({
  title: { type: String, default: '数据加载失败' },
  message: { type: String, default: '' },
  hint: { type: String, default: '请确认业务服务（http://localhost:8080）与智能服务（http://localhost:8000）已启动，然后点击重试。' },
  retryLabel: { type: String, default: '重新加载' },
  loading: { type: Boolean, default: false },
})
defineEmits(['retry'])
</script>

<template>
  <div class="panel error-state">
    <div class="empty-icon">!</div>
    <strong>{{ title }}</strong>
    <p v-if="message">{{ message }}</p>
    <p>{{ hint }}</p>
    <button class="btn btn-outline btn-sm" :disabled="loading" @click="$emit('retry')">
      <span v-if="loading" class="spinner"></span>
      {{ loading ? '正在重试…' : retryLabel }}
    </button>
  </div>
</template>
