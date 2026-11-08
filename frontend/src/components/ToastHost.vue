<script setup>
import { toastState, dismissToast } from '../toast'

const icons = { success: '✓', error: '!', info: 'i' }
</script>

<template>
  <div class="toast-host" aria-live="polite">
    <TransitionGroup name="toast">
      <div
        v-for="item in toastState.items"
        :key="item.id"
        class="toast"
        :class="`toast-${item.type}`"
        role="status"
        @click="dismissToast(item.id)"
      >
        <span class="toast-icon">{{ icons[item.type] || 'i' }}</span>
        <span>{{ item.message }}</span>
      </div>
    </TransitionGroup>
  </div>
</template>
