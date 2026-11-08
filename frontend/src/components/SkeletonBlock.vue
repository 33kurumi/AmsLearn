<script setup>
defineProps({
  rows: { type: Number, default: 4 },
  cards: { type: Number, default: 3 },
  showCards: { type: Boolean, default: true },
})
</script>

<template>
  <div aria-busy="true" aria-label="加载中">
    <div v-if="showCards" class="stats-grid mt-8">
      <div v-for="i in cards" :key="i" class="skeleton-card"></div>
    </div>
    <div class="panel mt-16">
      <div class="skeleton">
        <div v-for="i in rows" :key="i" class="skeleton-line" :class="i === 1 ? 'w-40' : i % 3 === 0 ? 'w-60' : 'w-80'"></div>
      </div>
    </div>
  </div>
</template>
